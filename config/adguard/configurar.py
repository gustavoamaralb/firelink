#!/usr/bin/env python3
"""Configuração inicial do AdGuard Home pela API local (substitui o assistente web).

DNS na porta 53 e painel na 3000, em todas as interfaces (o nftables só deixa a
rede de casa entrar). Upstreams cifrados (DoH), log de consultas curto.
"""
import base64
import getpass
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:3000"
USUARIO = getpass.getuser()   # panel login = the user who runs this script


def chamar(metodo, caminho, dados=None, auth=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    if dados is not None:
        req.data = json.dumps(dados).encode()
        req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    with urllib.request.urlopen(req, timeout=15) as r:
        corpo = r.read()
        return json.loads(corpo) if corpo.strip().startswith((b"{", b"[")) else corpo


def esperar():
    for _ in range(60):
        try:
            chamar("GET", "/control/install/get_addresses")
            return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(1)
    raise SystemExit("AdGuard não respondeu na porta 3000")


def main():
    esperar()
    while True:
        s1 = getpass.getpass(f"Senha do painel do AdGuard (usuário {USUARIO}): ")
        s2 = getpass.getpass("Repita: ")
        if s1 == s2 and len(s1) >= 8:
            break
        print("Senhas diferentes ou com menos de 8 caracteres. De novo.")

    chamar("POST", "/control/install/configure", {
        "web": {"ip": "0.0.0.0", "port": 3000},
        "dns": {"ip": "0.0.0.0", "port": 53},
        "username": USUARIO,
        "password": s1,
    })
    time.sleep(3)
    auth = f"{USUARIO}:{s1}"
    for _ in range(30):
        try:
            chamar("GET", "/control/status", auth=auth)
            break
        except (urllib.error.URLError, ConnectionError):
            time.sleep(1)

    chamar("POST", "/control/dns_config", {
        "upstream_dns": [
            "https://dns.quad9.net/dns-query",
            "https://cloudflare-dns.com/dns-query",
        ],
        "bootstrap_dns": ["9.9.9.9", "1.1.1.1"],
    }, auth=auth)
    dia = 24 * 3600 * 1000
    chamar("PUT", "/control/querylog/config/update",
           {"enabled": True, "interval": dia, "anonymize_client_ip": False, "ignored": []}, auth=auth)
    chamar("PUT", "/control/stats/config/update",
           {"enabled": True, "interval": 7 * dia, "ignored": []}, auth=auth)

    st = chamar("GET", "/control/status", auth=auth)
    dns = chamar("GET", "/control/dns_info", auth=auth)
    filtros = chamar("GET", "/control/filtering/status", auth=auth)
    print("versão:", st.get("version"), "| rodando:", st.get("running"), "| proteção:", st.get("protection_enabled"))
    print("upstreams:", dns.get("upstream_dns"))
    for f in filtros.get("filters", []):
        print("lista:", f["name"], "| ativa:", f["enabled"], "| regras:", f.get("rules_count"))


if __name__ == "__main__":
    main()
