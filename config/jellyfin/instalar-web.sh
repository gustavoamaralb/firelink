#!/bin/sh
# Jellyfin's favicons and home-screen icons become the Videoteca magic lantern.
#   sudo sh instalar-web.sh [/usr/share/jellyfin/web]
# Installs the icons under /usr/local/share/firelink/jellyfin, the script
# jellyfin-firelink-web and an apt hook that re-applies them after every
# package operation (jellyfin-web updates replace the files), and applies
# them now. Undo: remove /etc/apt/apt.conf.d/99firelink-jellyfin, the script
# and that folder, then reinstall jellyfin-web.
set -e
[ "$(id -u)" = 0 ] || { echo "rode com sudo"; exit 1; }
W="${1:-/usr/share/jellyfin/web}"
AQUI=$(cd "$(dirname "$0")" && pwd)
F=/usr/local/share/firelink/jellyfin/icons
install -d "$F" && install -m 644 "$AQUI"/icons/* "$F/"
install -m 755 "$AQUI/jellyfin-firelink-web" /usr/local/sbin/jellyfin-firelink-web
printf 'DPkg::Post-Invoke { "/usr/local/sbin/jellyfin-firelink-web %s || true"; };\n' "$W" \
    > /etc/apt/apt.conf.d/99firelink-jellyfin
/usr/local/sbin/jellyfin-firelink-web "$W"
for i in "$W"/favicon.*.ico; do cmp -s "$F/favicon.ico" "$i" && echo "Jellyfin: ícones da Videoteca aplicados"; done
