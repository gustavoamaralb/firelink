#!/usr/bin/env python3
"""Installs the Firelink theme in Kavita and makes it the server default.

Uses Kavita's own API (no database edits, no restart). It logs in as an admin,
uploads firelink.css (or finds the copy already there), marks it as the default
theme for new accounts and switches the admin's own account to it. Other existing accounts
keep the theme they chose; each person picks Firelink under Settings -> Theme.

    python3 instalar.py                         # http://localhost:5000, asks user and password
    python3 instalar.py --url http://firelink.local:5000 --usuario NAME

Standard library only. Run build.sh first so firelink.css exists.
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
NOME = "firelink"


def pedir(url, metodo="GET", token=None, json_corpo=None, corpo=None, tipo=None):
    cab = {"Accept": "application/json"}
    if token:
        cab["Authorization"] = "Bearer " + token
    if json_corpo is not None:
        corpo = json.dumps(json_corpo).encode()
        tipo = "application/json"
    if tipo:
        cab["Content-Type"] = tipo
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            dados = r.read()
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:300]
        sys.exit(f"Kavita respondeu {e.code} em {metodo} {url}: {msg}")
    except urllib.error.URLError as e:
        sys.exit(f"Não consegui falar com o Kavita em {url}: {e.reason}")
    if not dados:
        return None
    try:
        return json.loads(dados)
    except ValueError:
        return dados.decode(errors="replace")


def enviar_arquivo(api, token, caminho):
    fronteira = uuid.uuid4().hex
    with open(caminho, "rb") as f:
        conteudo = f.read()
    corpo = (
        f"--{fronteira}\r\n"
        f'Content-Disposition: form-data; name="formFile"; filename="{NOME}.css"\r\n'
        "Content-Type: text/css\r\n\r\n"
    ).encode() + conteudo + f"\r\n--{fronteira}--\r\n".encode()
    return pedir(api + "theme/upload-theme", "POST", token, corpo=corpo,
                 tipo="multipart/form-data; boundary=" + fronteira)


def principal():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://localhost:5000", help="endereço do Kavita")
    ap.add_argument("--usuario", help="usuário administrador do Kavita")
    a = ap.parse_args()

    css = os.path.join(AQUI, "firelink.css")
    if not os.path.isfile(css):
        sys.exit("firelink.css não existe: rode build.sh antes.")

    api = a.url.rstrip("/") + "/api/"
    usuario = a.usuario or input("Usuário administrador do Kavita: ")
    senha = os.environ.get("KAVITA_SENHA") or getpass.getpass("Senha: ")
    conta = pedir(api + "account/login", "POST", json_corpo={"username": usuario, "password": senha})
    token = conta["token"]
    if "Admin" not in conta.get("roles", []):
        sys.exit(f"{usuario} não é administrador do Kavita.")

    # Kavita refuses a second upload with the same name, but it reads the theme
    # from config/themes/ on every request. So an existing copy is kept (nobody
    # loses their choice) and its content is updated by overwriting that file.
    temas = pedir(api + "theme", token=token)
    tema = next((t for t in temas if t["name"].lower() == NOME), None)
    ja_existia = tema is not None
    if not ja_existia:
        tema = enviar_arquivo(api, token, css)
    pedir(api + "theme/update-default", "POST", token, json_corpo={"themeId": tema["id"]})
    prefs = pedir(api + "users/get-preferences", token=token)
    prefs["theme"] = tema
    pedir(api + "users/update-preferences", "POST", token, json_corpo=prefs)

    if ja_existia:
        atual = pedir(api + f"theme/download-content?themeId={tema['id']}", token=token)
        with open(css, encoding="utf-8") as f:
            novo = f.read()
        if (atual or "").strip() != novo.strip():
            print("O Kavita tem uma versão diferente do tema. Para atualizar o conteúdo, no servidor:")
            print(f"  sudo install -o kavita -g kavita -m 644 {css} <pasta do Kavita>/config/themes/{tema['fileName']}")
    feito = "já estava instalado" if ja_existia else "enviado"
    print(f"Tema {tema['name']} {feito}; agora é o padrão do servidor e está ativo para {usuario}.")
    print("Contas que já existiam mantêm o tema escolhido: cada pessoa troca em Configurações -> Tema.")

if __name__ == "__main__":
    principal()
