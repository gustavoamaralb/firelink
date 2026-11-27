#!/bin/sh
# Builds firelink.css for Jellyfin (Dashboard -> General -> Custom CSS) from
# firelink.src.css, embedding the fonts and pixel art shared with the Kavita
# theme (config/kavita/). Paste the result, or send it with instalar.py.
set -e
cd "$(dirname "$0")"
A=../kavita
[ -f $A/cinzel-latin.woff2 ] || sh $A/build.sh >/dev/null
b64() { base64 -w0 "$1"; }
sed -e "s|@@CINZEL@@|$(b64 $A/cinzel-latin.woff2)|" \
    -e "s|@@SILKSCREEN@@|$(b64 $A/silkscreen-700-latin.woff2)|" \
    -e "s|@@AKALI@@|$(b64 $A/img/akali-dormindo.png)|" \
    -e "s|@@FOGUEIRA@@|$(b64 $A/img/fogueira.png)|" \
    -e "s|@@FOGUEIRA_PARADA@@|$(b64 $A/img/fogueira-parada.png)|" \
    firelink.src.css > firelink.css
echo "firelink.css: $(wc -c < firelink.css) bytes"
