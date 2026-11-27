#!/bin/sh
# Gives Kavita's sign-in screens the Firelink look (no theme reaches them).
#   sudo sh instalar-login.sh [/opt/Kavita]
# Installs firelink-login.css and kavita-login-firelink, adds a systemd
# drop-in that re-links the style before every Kavita start (updates replace
# wwwroot/), and applies it now. Undo: remove the drop-in and the two files,
# then reinstall or update Kavita.
set -e
[ "$(id -u)" = 0 ] || { echo "rode com sudo"; exit 1; }
K="${1:-/opt/Kavita}"
AQUI=$(cd "$(dirname "$0")" && pwd)
[ -f "$AQUI/firelink-login.css" ] || { echo "rode build.sh antes"; exit 1; }
install -D -m 644 "$AQUI/firelink-login.css" /usr/local/share/firelink/firelink-login.css
install -m 755 "$AQUI/kavita-login-firelink" /usr/local/sbin/kavita-login-firelink
mkdir -p /etc/systemd/system/kavita.service.d
printf '[Service]\nExecStartPre=-+/usr/local/sbin/kavita-login-firelink %s\n' "$K" \
    > /etc/systemd/system/kavita.service.d/firelink-login.conf
systemctl daemon-reload
/usr/local/sbin/kavita-login-firelink "$K"
grep -q 'firelink-login.css' "$K/wwwroot/index.html" && echo "tela de login do Kavita no estilo Firelink"
