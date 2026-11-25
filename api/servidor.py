#!/usr/bin/env python3
"""Small API for the firelink home page (listens on 127.0.0.1 only; Caddy proxies /api/*).

GET  /api/status   -> services up/down and uptime (checked on each request)
GET  /api/sistema  -> Debian release, kernel and versions of the main services (cached for 1 h)
GET  /api/placar   -> Akali's pets ("carinho") and swats ("tapa") per person
POST /api/placar   -> {"quem": "<name>", "tipo": "carinho" | "tapa"} adds 1

Valid names come from /srv/www/firelink/config.js (the same file the page uses).
Standard library only.
"""
import json, os, platform, re, sqlite3, subprocess, threading, time, urllib.request
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


def no_ar(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def status():
    with open("/proc/uptime") as f:
        ligado = int(float(f.read().split()[0]))
    return {"ligado_seg": ligado, "servicos": {k: no_ar(u) for k, u in SERVICOS.items()}, "agora": int(time.time())}


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
        if self.path == "/api/status":
            return self._json(200, status())
        if self.path == "/api/sistema":
            return self._json(200, sistema_em_cache())
        if self.path == "/api/placar":
            with trava:
                return self._json(200, ler_placar())
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/placar":
            return self._json(404, {"error": "not found"})
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        agora = time.monotonic()
        if agora - ultimo_post.get(ip, 0) < 0.4:
            return self._json(429, {"error": "too fast"})
        ultimo_post[ip] = agora
        try:
            n = min(int(self.headers.get("Content-Length", 0)), 200)
            pedido = json.loads(self.rfile.read(n) or b"{}")
            quem, tipo = pedido.get("quem"), pedido.get("tipo")
        except (ValueError, AttributeError):
            return self._json(400, {"error": "invalid request"})
        if quem not in pessoas() or tipo not in TIPOS:
            return self._json(400, {"error": "invalid request"})
        with trava:
            d = ler_placar()
            d[quem][tipo] += 1
            gravar_placar(d)
            return self._json(200, d)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8091), Api).serve_forever()
