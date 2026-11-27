#!/usr/bin/env python3
"""Saves the AdGuard Home panel login for firelink-api (the shield button on the home page).

Run it as the user that runs firelink-api. It asks for the password without echoing it, checks it
against AdGuard Home on 127.0.0.1:3000 and writes ~/.config/firelink/adguard.json with mode 600.
"""
import base64
import getpass
import json
import os
import urllib.error
import urllib.request

DESTINO = os.path.expanduser("~/.config/firelink/adguard.json")

padrao = getpass.getuser()
usuario = input(f"Usuário do painel do AdGuard [{padrao}]: ").strip() or padrao
senha = getpass.getpass("Senha do painel do AdGuard: ")
req = urllib.request.Request("http://127.0.0.1:3000/control/status")
req.add_header("Authorization", "Basic " + base64.b64encode(f"{usuario}:{senha}".encode()).decode())
try:
    with urllib.request.urlopen(req, timeout=5) as r:
        versao = json.load(r).get("version")
except urllib.error.HTTPError as e:
    raise SystemExit("Usuário ou senha recusados pelo AdGuard." if e.code in (401, 403) else f"Erro do AdGuard: {e}")
except OSError as e:
    raise SystemExit(f"AdGuard não respondeu: {e}")

os.makedirs(os.path.dirname(DESTINO), mode=0o700, exist_ok=True)
fd = os.open(DESTINO, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump({"usuario": usuario, "senha": senha}, f)
os.chmod(DESTINO, 0o600)
print(f"Senha conferida (AdGuard {versao}) e guardada em {DESTINO}.")
