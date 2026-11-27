#!/usr/bin/env python3
"""Installs the Firelink theme as Jellyfin's custom CSS (server-wide).

Uses Jellyfin's own API: logs in as an administrator and writes firelink.css
into the branding settings (Dashboard -> General -> Custom CSS). It applies to
every account and to the web-based apps (browser, LG webOS, Android); nothing
else in the branding settings is touched. Running it again updates the CSS.

    python3 instalar.py                              # http://localhost:8096, asks user and password
    python3 instalar.py --url http://firelink.local:8096 --usuario NAME
    python3 instalar.py --remover                    # back to Jellyfin's own look

Standard library only. Run build.sh first so firelink.css exists.
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
CLIENTE = 'MediaBrowser Client="firelink-tema", Device="instalar.py", DeviceId="firelink-tema", Version="1.0"'


def pedir(base, caminho, metodo="GET", token=None, corpo=None):
    auth = CLIENTE + (f', Token="{token}"' if token else "")
    req = urllib.request.Request(base + caminho, method=metodo,
                                 data=None if corpo is None else json.dumps(corpo).encode(),
                                 headers={"Authorization": auth, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            dados = r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"Jellyfin respondeu {e.code} em {metodo} {caminho}: {e.read().decode(errors='replace')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"Não consegui falar com o Jellyfin em {base}: {e.reason}")
    return json.loads(dados) if dados else None


def principal():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://localhost:8096", help="endereço do Jellyfin")
    ap.add_argument("--usuario", help="usuário administrador do Jellyfin")
    ap.add_argument("--remover", action="store_true", help="apaga o CSS personalizado")
    a = ap.parse_args()

    css = ""
    if not a.remover:
        caminho = os.path.join(AQUI, "firelink.css")
        if not os.path.isfile(caminho):
            sys.exit("firelink.css não existe: rode build.sh antes.")
        with open(caminho, encoding="utf-8") as f:
            css = f.read()

    base = a.url.rstrip("/")
    usuario = a.usuario or input("Usuário administrador do Jellyfin: ")
    senha = os.environ.get("JELLYFIN_SENHA") or getpass.getpass("Senha: ")
    sessao = pedir(base, "/Users/AuthenticateByName", "POST", corpo={"Username": usuario, "Pw": senha})
    token = sessao["AccessToken"]
    if not sessao["User"]["Policy"].get("IsAdministrator"):
        sys.exit(f"{usuario} não é administrador do Jellyfin.")
    try:
        marca = pedir(base, "/System/Configuration/branding", token=token)
        antes = marca.get("CustomCss") or ""
        marca["CustomCss"] = css
        pedir(base, "/System/Configuration/branding", "POST", token, marca)
    finally:
        pedir(base, "/Sessions/Logout", "POST", token)

    if a.remover:
        print("CSS personalizado removido: o Jellyfin voltou ao visual próprio.")
    elif antes.strip() == css.strip():
        print("O tema Firelink já estava instalado e igual a este.")
    else:
        print(f"Tema Firelink instalado ({len(css)} caracteres de CSS). Recarregue as páginas abertas.")
        if antes.strip() and "Firelink - Jellyfin theme" not in antes:
            print("Havia outro CSS personalizado antes; ele foi substituído.")


if __name__ == "__main__":
    principal()
