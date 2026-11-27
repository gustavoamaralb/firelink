#!/usr/bin/env python3
"""Small API for the firelink home page (listens on 127.0.0.1 only; Caddy proxies /api/*).

GET  /api/status   -> services up/down and uptime (checked on each request)
GET  /api/sistema  -> Debian release, kernel and versions of the main services (cached for 1 h)
GET  /api/monitor  -> live system monitor: CPU (total and per core), memory, swap, network speed,
                      CPU temperature and disk space (read from /proc and /sys on each request, nothing stored)
GET  /api/placar   -> Akali's pets ("carinho") and swats ("tapa") per person
POST /api/placar   -> {"quem": "<name>", "tipo": "carinho" | "tapa"} adds 1
GET  /api/chat?desde=<id> -> household chat messages after that id (the last 200) and who has read up to where
     (also the pinned messages)
POST /api/chat     -> {"quem": "<name>", "texto": "..."} or {"quem": "<name>", "figurinha": "<sticker>"} sends a message
POST /api/chat/lido -> {"quem": "<name>", "id": <id>} marks messages as read up to that id
POST /api/chat/fixar -> {"quem": "<name>", "id": <id>, "fixa": true | false} pins or unpins a text message
POST /api/chat/apagar -> {"quem": "<name>", "id": <id>} deletes one's own message
POST /api/escudo  -> {"quem": "<name>", "acao": "baixar" | "erguer"} pauses AdGuard Home's blocking for
                     10 minutes, or turns it back on (the "shield")

The shield state in /api/status comes from a DNS question to AdGuard Home on 127.0.0.1:53: a blocked
domain answered with 0.0.0.0 means the shield is up. Pausing, and the time left on a pause, use
AdGuard Home's own API with the credentials in ~/.config/firelink/adguard.json (created by
guardar-senha-adguard.py, mode 600). AdGuard Home keeps no query log or statistics on firelink.

A deleted message is rewritten in the file as {"id": <id>, "apagada": true}: its content is gone and
its id is never reused, so the pages learn about the deletion and never mix up two messages.

Messages are appended to a JSON Lines file only when someone sends one (polling never writes to the disk).

Valid names come from /srv/www/firelink/config.js (the same file the page uses).
Standard library only.
"""
import base64, json, os, platform, re, socket, sqlite3, struct, subprocess, threading, time, urllib.request
from urllib.parse import parse_qs, urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONFIG = "/srv/www/firelink/config.js"


def pessoas():
    """Read the names from the page's config.js (JSON between the first '{' and the last '}')."""
    try:
        with open(CONFIG, encoding="utf-8") as f:
            t = f.read()
        return tuple(json.loads(t[t.index("{"):t.rindex("}") + 1]).get("people", {}))
    except (OSError, ValueError):
        return ()


TIPOS = ("carinho", "tapa")
DADOS = os.path.expanduser("~/.local/share/firelink/placar.json")
SERVICOS = {"jellyfin": "http://127.0.0.1:8096/health", "kavita": "http://127.0.0.1:5000/"}
trava = threading.Lock()
trava_monitor = threading.Lock()
ultimo_post = {}          # simple per-IP rate limit


def ler_placar():
    try:
        with open(DADOS) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return {p: {t: int(d.get(p, {}).get(t, 0)) for t in TIPOS} for p in pessoas()}


def gravar_placar(d):
    os.makedirs(os.path.dirname(DADOS), exist_ok=True)
    tmp = DADOS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, DADOS)


MENSAGENS = os.path.expanduser("~/.local/share/firelink/chat.jsonl")
LIDOS = os.path.expanduser("~/.local/share/firelink/chat-lidos.json")
FIXADAS = os.path.expanduser("~/.local/share/firelink/chat-fixadas.json")
MAX_TEXTO = 2000
MAX_FIXADAS = 12
# stickers of Akali, drawn by the page
FIGURINHAS = ("akali-dormindo", "akali-ronrona", "akali-tapa", "akali-arrepiada", "akali-capuz",
              "akali-deitada", "akali-barriga")
CONTROLE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
memoria = {"mensagens": None, "indice": None, "lidos": None, "fixadas": None}     # loaded on first use, then kept in memory


def mensagens():
    if memoria["mensagens"] is None:
        lista = []
        try:
            with open(MENSAGENS, encoding="utf-8") as f:
                for linha in f:
                    try:
                        r = json.loads(linha)
                    except ValueError:
                        continue
                    if isinstance(r, dict) and isinstance(r.get("id"), int):
                        lista.append(r)
        except OSError:
            pass
        memoria["mensagens"] = lista
        memoria["indice"] = {r["id"]: r for r in lista}
    return memoria["mensagens"]


def gravar_json(caminho, d):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, caminho)


def reescrever_mensagens():
    tmp = MENSAGENS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in mensagens():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, MENSAGENS)


def apagar_mensagem(ident):
    lista = mensagens()
    for i, r in enumerate(lista):
        if r["id"] == ident:
            lista[i] = memoria["indice"][ident] = {"id": ident, "apagada": True}
            break
    reescrever_mensagens()
    if fixadas().pop(str(ident), None):
        gravar_json(FIXADAS, fixadas())


def fixadas():
    """{"<id>": {"por": <name>, "t": <when>}} of pinned messages."""
    if memoria["fixadas"] is None:
        try:
            with open(FIXADAS, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        memoria["fixadas"] = {k: v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}
    return memoria["fixadas"]


def fixadas_lista():
    """Pinned messages in full (they may be older than what the page has loaded), newest pin first."""
    mensagens()
    lista = []
    for k, v in fixadas().items():
        r = memoria["indice"].get(int(k)) if k.isdigit() else None
        if r and not r.get("apagada"):
            lista.append(dict(r, por=v.get("por"), fixada_em=v.get("t", 0)))
    return sorted(lista, key=lambda r: -r["fixada_em"])


def lidos():
    if memoria["lidos"] is None:
        try:
            with open(LIDOS) as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        memoria["lidos"] = {k: v for k, v in d.items() if isinstance(v, int)} if isinstance(d, dict) else {}
    return memoria["lidos"]


def nova_mensagem(quem, campo, valor):
    lista = mensagens()
    r = {"id": (lista[-1]["id"] + 1) if lista else 1, "quem": quem, campo: valor, "t": int(time.time())}
    os.makedirs(os.path.dirname(MENSAGENS), exist_ok=True)
    with open(MENSAGENS, "a", encoding="utf-8") as f:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
    lista.append(r)
    memoria["indice"][r["id"]] = r
    return r


def marcar_lido(quem, ate):
    d = lidos()
    if ate <= d.get(quem, 0):
        return
    d[quem] = ate
    gravar_json(LIDOS, d)


def no_ar(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def status():
    with open("/proc/uptime") as f:
        ligado = int(float(f.read().split()[0]))
    return {"ligado_seg": ligado, "servicos": {k: no_ar(u) for k, u in SERVICOS.items()},
            "escudo": escudo(), "agora": int(time.time())}


# ---------- the shield (AdGuard Home) ----------
TESTE_DNS = "doubleclick.net"          # on AdGuard's default list; answered with 0.0.0.0 while blocking
ADGUARD = "http://127.0.0.1:3000"
CREDENCIAIS = os.path.expanduser("~/.config/firelink/adguard.json")
PAUSA_MS = 10 * 60 * 1000


def pergunta_dns(nome):
    """A records for nome from 127.0.0.1:53, or None if nobody answers."""
    ident = int(time.monotonic() * 1000) & 0xFFFF
    q = struct.pack(">HHHHHH", ident, 0x0100, 1, 0, 0, 0)
    q += b"".join(bytes([len(p)]) + p.encode() for p in nome.split(".")) + b"\0" + struct.pack(">HH", 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(1.5)
        try:
            s.sendto(q, ("127.0.0.1", 53))
            r = s.recv(1500)
        except OSError:
            return None
    if len(r) < 12 or struct.unpack(">H", r[:2])[0] != ident:
        return None
    respostas = struct.unpack(">H", r[6:8])[0]
    i = len(q)                                         # the question comes back unchanged
    ips = []
    for _ in range(respostas):
        if i >= len(r):
            break
        if r[i] & 0xC0 == 0xC0:                        # compressed name
            i += 2
        else:
            while i < len(r) and r[i]:
                i += r[i] + 1
            i += 1
        if i + 10 > len(r):
            break
        tipo, _cls, _ttl, tam = struct.unpack(">HHIH", r[i:i + 10])
        i += 10
        if tipo == 1 and tam == 4:
            ips.append(socket.inet_ntoa(r[i:i + 4]))
        i += tam
    return ips


def credenciais():
    try:
        with open(CREDENCIAIS) as f:
            d = json.load(f)
        return f"{d['usuario']}:{d['senha']}"
    except (OSError, ValueError, KeyError, TypeError):
        return None


def adguard(caminho, dados=None):
    """Call AdGuard Home's API; None if there are no credentials or it fails."""
    auth = credenciais()
    if not auth:
        return None
    req = urllib.request.Request(ADGUARD + caminho, method="POST" if dados is not None else "GET")
    req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    if dados is not None:
        req.data = json.dumps(dados).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            corpo = r.read()
        return json.loads(corpo) if corpo.strip().startswith(b"{") else {}
    except Exception:
        return None


def escudo():
    """{"estado": "erguido" | "baixado" | "caido", "volta_seg": seconds left on a pause, "controle": bool}"""
    ips = pergunta_dns(TESTE_DNS)
    if ips is None:
        return {"estado": "caido", "volta_seg": None, "controle": False}
    st = adguard("/control/status")
    volta = None
    if st and not st.get("protection_enabled", True):
        ms = st.get("protection_disabled_duration") or 0
        volta = int(ms / 1000) if ms > 0 else None
    erguido = bool(ips) and all(ip == "0.0.0.0" for ip in ips)
    if st is not None:
        erguido = erguido and st.get("protection_enabled", True)
    return {"estado": "erguido" if erguido else "baixado", "volta_seg": volta, "controle": st is not None}


# ---------- live system monitor ----------
mon = {"antes": None, "ultimo": None, "sensor": None}


def amostra():
    """CPU counters per line of /proc/stat and network byte counters (all interfaces but lo)."""
    cpus = []
    with open("/proc/stat") as f:
        for linha in f:
            if not linha.startswith("cpu"):
                break
            v = [int(n) for n in linha.split()[1:9]]
            cpus.append((v[3] + v[4], sum(v)))        # (idle + iowait, total)
    rx = tx = 0
    with open("/proc/net/dev") as f:
        for linha in f.readlines()[2:]:
            nome, dados = linha.split(":", 1)
            if nome.strip() != "lo":
                d = dados.split()
                rx += int(d[0]); tx += int(d[8])
    return {"t": time.monotonic(), "cpus": cpus, "rx": rx, "tx": tx}


def sensor_cpu():
    """Path of the CPU package temperature (coretemp), or the x86_pkg_temp thermal zone."""
    if mon["sensor"] is None:
        mon["sensor"] = ""
        for h in sorted(os.listdir("/sys/class/hwmon")):
            base = "/sys/class/hwmon/" + h
            if ler(base + "/name").strip() == "coretemp":
                for arq in sorted(os.listdir(base)):
                    if arq.endswith("_label") and ler(base + "/" + arq).strip().startswith("Package"):
                        mon["sensor"] = base + "/" + arq.replace("_label", "_input")
                if not mon["sensor"] and os.path.exists(base + "/temp1_input"):
                    mon["sensor"] = base + "/temp1_input"
        if not mon["sensor"]:
            for z in sorted(os.listdir("/sys/class/thermal")):
                if ler("/sys/class/thermal/%s/type" % z).strip() == "x86_pkg_temp":
                    mon["sensor"] = "/sys/class/thermal/%s/temp" % z
    try:
        return round(int(ler(mon["sensor"])) / 1000, 1) if mon["sensor"] else None
    except ValueError:
        return None


def monitor():
    agora = amostra()
    antes = mon["antes"]
    if antes is None:                                   # first request: take a quick second reading
        time.sleep(0.25)
        antes, agora = agora, amostra()
    elif agora["t"] - antes["t"] < 0.3 and mon["ultimo"]:
        return mon["ultimo"]                            # two pages asking at the same moment
    dt = agora["t"] - antes["t"]
    usos = []
    for (i0, t0), (i1, t1) in zip(antes["cpus"], agora["cpus"]):
        total = t1 - t0
        usos.append(round(100 * (1 - (i1 - i0) / total), 1) if total > 0 else 0.0)
    mem = {k: int(v.split()[0]) * 1024 for k, v in re.findall(r"^(\w+):\s+(.+)$", ler("/proc/meminfo"), re.M)}
    fs = os.statvfs("/")
    mon["antes"] = agora
    mon["ultimo"] = {
        "cpu": usos[0] if usos else 0.0,
        "nucleos": usos[1:],
        "mem": {"total": mem.get("MemTotal", 0), "usado": mem.get("MemTotal", 0) - mem.get("MemAvailable", 0),
                "swap_total": mem.get("SwapTotal", 0), "swap_usado": mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)},
        "rede": {"rx": max(0, int((agora["rx"] - antes["rx"]) / dt)), "tx": max(0, int((agora["tx"] - antes["tx"]) / dt))},
        "temp": sensor_cpu(),
        "disco": {"total": fs.f_blocks * fs.f_frsize, "usado": (fs.f_blocks - fs.f_bfree) * fs.f_frsize,
                  "livre": fs.f_bavail * fs.f_frsize},
    }
    return mon["ultimo"]


def versao(texto):
    """First x.y.z(.w) in a string, or None."""
    m = re.search(r"\d+(?:\.\d+){1,3}", texto or "")
    return m.group(0) if m else None


def comando(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def versao_jellyfin():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8096/System/Info/Public", timeout=2) as r:
            return versao(json.load(r).get("Version"))
    except Exception:
        return None


def versao_kavita():
    """Kavita keeps its installed version in its own database (ServerSetting key 11, InstallVersion)."""
    for uri in ("file:/opt/Kavita/config/kavita.db?mode=ro", "file:/opt/Kavita/config/kavita.db?immutable=1"):
        try:
            with sqlite3.connect(uri, uri=True, timeout=2) as c:
                linha = c.execute("SELECT Value FROM ServerSetting WHERE Key = 11").fetchone()
            if linha:
                return versao(linha[0])
        except sqlite3.Error:
            continue
    return None


def ler(caminho):
    try:
        with open(caminho) as f:
            return f.read()
    except OSError:
        return ""


def sistema():
    os_release = dict(re.findall(r'^(\w+)="?([^"\n]*)"?$', ler("/etc/os-release"), re.M))
    return {
        "debian": ler("/etc/debian_version").strip() or os_release.get("VERSION_ID"),
        "codinome": os_release.get("VERSION_CODENAME"),
        "kernel": platform.release(),
        "versoes": {
            "Jellyfin": versao_jellyfin(),
            "Kavita": versao_kavita(),
            "Samba": versao(comando("/usr/sbin/smbd", "-V")),
            "Caddy": versao(comando("caddy", "version")),
            "AdGuard": versao(comando("/opt/AdGuardHome/AdGuardHome", "--version")),
        },
    }


cache_sistema = {"t": 0, "d": None}


def sistema_em_cache():
    agora = time.monotonic()
    if cache_sistema["d"] is None or agora - cache_sistema["t"] > 3600:
        cache_sistema.update(t=agora, d=sistema())
    return cache_sistema["d"]


class Api(BaseHTTPRequestHandler):
    server_version = "firelink-api"

    def _json(self, codigo, obj):
        corpo = json.dumps(obj).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/api/status":
            return self._json(200, status())
        if url.path == "/api/monitor":
            with trava_monitor:
                return self._json(200, monitor())
        if url.path == "/api/sistema":
            return self._json(200, sistema_em_cache())
        if url.path == "/api/placar":
            with trava:
                return self._json(200, ler_placar())
        if url.path == "/api/chat":
            try:
                desde = int(parse_qs(url.query).get("desde", ["0"])[0])
            except ValueError:
                desde = 0
            nomes = pessoas()
            with trava:
                novos = [r for r in mensagens() if r["id"] > desde][-200:]
                vistos = {k: v for k, v in lidos().items() if k in nomes}
                presas = fixadas_lista()
                apagadas = [r["id"] for r in mensagens() if r.get("apagada")]
            return self._json(200, {"mensagens": novos, "lidos": vistos, "fixadas": presas, "apagadas": apagadas})
        self._json(404, {"error": "not found"})

    def _pedido(self, limite):
        try:
            n = max(0, min(int(self.headers.get("Content-Length", 0)), limite))   # a negative length would block on read
            pedido = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return None
        return pedido if isinstance(pedido, dict) else None

    def do_POST(self):
        rotas = {"/api/placar": 0.4, "/api/chat": 0.5, "/api/chat/lido": 0.2, "/api/chat/fixar": 0.3, "/api/chat/apagar": 0.3,
                 "/api/escudo": 2}
        if self.path not in rotas:
            return self._json(404, {"error": "not found"})
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        agora = time.monotonic()
        if agora - ultimo_post.get((ip, self.path), 0) < rotas[self.path]:
            return self._json(429, {"error": "too fast"})
        ultimo_post[(ip, self.path)] = agora
        pedido = self._pedido(16384 if self.path == "/api/chat" else 200)
        if pedido is None or pedido.get("quem") not in pessoas():
            return self._json(400, {"error": "invalid request"})
        quem = pedido["quem"]

        if self.path == "/api/escudo":
            acao = pedido.get("acao")
            if acao not in ("baixar", "erguer"):
                return self._json(400, {"error": "invalid request"})
            dados = {"enabled": False, "duration": PAUSA_MS} if acao == "baixar" else {"enabled": True}
            if adguard("/control/protection", dados) is None:
                return self._json(503, {"error": "AdGuard Home did not accept the change"})
            return self._json(200, {"escudo": escudo()})

        if self.path == "/api/placar":
            tipo = pedido.get("tipo")
            if tipo not in TIPOS:
                return self._json(400, {"error": "invalid request"})
            with trava:
                d = ler_placar()
                d[quem][tipo] += 1
                gravar_placar(d)
                return self._json(200, d)

        if self.path == "/api/chat":
            figurinha = pedido.get("figurinha")
            if figurinha is not None:
                if figurinha not in FIGURINHAS:
                    return self._json(400, {"error": "invalid request"})
                with trava:
                    return self._json(200, {"mensagem": nova_mensagem(quem, "figurinha", figurinha)})
            texto = pedido.get("texto")
            if not isinstance(texto, str):
                return self._json(400, {"error": "invalid request"})
            texto = CONTROLE.sub("", texto.replace("\r\n", "\n")).strip()
            if not texto or len(texto) > MAX_TEXTO:
                return self._json(400, {"error": "invalid request"})
            with trava:
                return self._json(200, {"mensagem": nova_mensagem(quem, "texto", texto)})

        if self.path == "/api/chat/apagar":
            ident = pedido.get("id")
            if not isinstance(ident, int) or isinstance(ident, bool):
                return self._json(400, {"error": "invalid request"})
            with trava:
                mensagens()
                r = memoria["indice"].get(ident)
                if not r or r.get("apagada"):
                    return self._json(400, {"error": "invalid request"})
                if r.get("quem") != quem:
                    return self._json(403, {"error": "only the author can delete a message"})
                apagar_mensagem(ident)
                return self._json(200, {"apagada": ident, "fixadas": fixadas_lista()})

        if self.path == "/api/chat/fixar":
            ident, fixa = pedido.get("id"), pedido.get("fixa")
            if not isinstance(ident, int) or isinstance(ident, bool) or not isinstance(fixa, bool):
                return self._json(400, {"error": "invalid request"})
            with trava:
                mensagens()
                r = memoria["indice"].get(ident)
                if not r or "texto" not in r:
                    return self._json(400, {"error": "invalid request"})
                d, k = fixadas(), str(ident)
                if fixa and k not in d:
                    if len(d) >= MAX_FIXADAS:
                        return self._json(409, {"error": "too many pinned messages"})
                    d[k] = {"por": quem, "t": int(time.time())}
                    gravar_json(FIXADAS, d)
                elif not fixa and k in d:
                    del d[k]
                    gravar_json(FIXADAS, d)
                return self._json(200, {"fixadas": fixadas_lista()})

        ate = pedido.get("id")
        if not isinstance(ate, int) or isinstance(ate, bool):
            return self._json(400, {"error": "invalid request"})
        with trava:
            lista = mensagens()
            marcar_lido(quem, min(ate, lista[-1]["id"] if lista else 0))
            return self._json(200, {"lidos": lidos()})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8091), Api).serve_forever()
