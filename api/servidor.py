#!/usr/bin/env python3
"""Small API for the firelink home page (listens on 127.0.0.1 only; Caddy proxies /api/*).

GET  /api/status   -> services up/down and uptime (checked on each request)
GET  /api/placar   -> Akali's pets ("carinho") and swats ("tapa") per person
POST /api/placar   -> {"quem": "<name>", "tipo": "carinho" | "tapa"} adds 1

Valid names come from /srv/www/firelink/config.js (the same file the page uses).
Standard library only.
"""
import json, os, threading, time, urllib.request
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
