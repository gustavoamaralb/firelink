#!/bin/sh
# Builds firelink.css (the file uploaded to Kavita) from firelink.src.css,
# embedding the fonts (SIL Open Font License) and the pixel art, so the
# theme is one self-contained file that works offline.
set -e
cd "$(dirname "$0")"
get() { [ -f "$1" ] || curl -sfo "$1" "$2"; }
get cinzel-latin.woff2 https://fonts.gstatic.com/s/cinzel/v26/8vIJ7ww63mVu7gt79mT7.woff2
[ -f silkscreen-700-latin.woff2 ] || { echo "missing silkscreen-700-latin.woff2 (Google Fonts, Silkscreen 700, latin)"; exit 1; }
b64() { base64 -w0 "$1"; }
sed -e "s|@@CINZEL@@|$(b64 cinzel-latin.woff2)|" \
    -e "s|@@SILKSCREEN@@|$(b64 silkscreen-700-latin.woff2)|" \
    -e "s|@@AKALI@@|$(b64 img/akali-dormindo.png)|" \
    -e "s|@@FOGUEIRA@@|$(b64 img/fogueira.png)|" \
    -e "s|@@FOGUEIRA_PARADA@@|$(b64 img/fogueira-parada.png)|" \
    firelink.src.css > firelink.css
echo "firelink.css: $(wc -c < firelink.css) bytes"
