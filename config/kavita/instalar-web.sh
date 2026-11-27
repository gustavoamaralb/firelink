#!/bin/sh
# Firelink in Kavita's web files: the sign-in screens (no theme reaches them)
# and the favicons (the eBiblioteca tome from the home page).
#   sudo sh instalar-web.sh [/opt/Kavita]
# Installs the files under /usr/local/share/firelink/kavita, the script
# kavita-firelink-web and a systemd drop-in that re-applies them before every
# Kavita start (updates replace wwwroot/), and applies them now. Undo: remove
# the drop-in, the script and that folder, then reinstall or update Kavita.
set -e
[ "$(id -u)" = 0 ] || { echo "rode com sudo"; exit 1; }
K="${1:-/opt/Kavita}"
AQUI=$(cd "$(dirname "$0")" && pwd)
[ -f "$AQUI/firelink-login.css" ] || { echo "rode build.sh antes"; exit 1; }
F=/usr/local/share/firelink/kavita
install -D -m 644 "$AQUI/firelink-login.css" "$F/firelink-login.css"
install -d "$F/icons" && install -m 644 "$AQUI"/icons/* "$F/icons/"
install -m 755 "$AQUI/kavita-firelink-web" /usr/local/sbin/kavita-firelink-web
D=/etc/systemd/system/kavita.service.d
mkdir -p "$D"
printf '[Service]\nExecStartPre=-+/usr/local/sbin/kavita-firelink-web %s\n' "$K" > "$D/firelink-web.conf"
# earlier version (login only)
rm -f "$D/firelink-login.conf" /usr/local/sbin/kavita-login-firelink /usr/local/share/firelink/firelink-login.css
systemctl daemon-reload
/usr/local/sbin/kavita-firelink-web "$K"
grep -q 'firelink-login.css' "$K/wwwroot/index.html" && cmp -s "$F/icons/favicon.ico" "$K/wwwroot/assets/icons/favicon.ico" &&
    echo "Kavita: tela de login e ícones do Firelink aplicados"
