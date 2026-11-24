#!/bin/sh
# Writes firelink disk usage for the home page (http://firelink.local) to read.
set -e
DEST=/srv/www/firelink/disco.json
set -- $(df -B1 --output=size,used,avail / | tail -1)
printf "{\"total\":%s,\"usado\":%s,\"livre\":%s,\"atualizado\":\"%s\"}\n" "$1" "$2" "$3" "$(date -Iseconds)" > "$DEST.tmp"
mv "$DEST.tmp" "$DEST"
