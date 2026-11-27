#!/bin/sh
# Desliga o registro de consultas e as estatísticas do AdGuard Home e apaga o que já foi gravado.
# O bloqueio continua igual. Rodar com sudo.
set -eu
[ "$(id -u)" = 0 ] || { echo "rode com sudo"; exit 1; }
D=/opt/AdGuardHome
Y=$D/AdGuardHome.yaml
systemctl stop AdGuardHome
cp -p "$Y" "$Y.antes-privacidade"
awk '
  /^[a-z_]+:/ { bloco = $1 }
  (bloco == "querylog:" || bloco == "statistics:") && /^  (enabled|file_enabled): true$/ { sub(/true$/, "false") }
  { print }
' "$Y.antes-privacidade" > "$Y.novo"
chmod 600 "$Y.novo"
mv "$Y.novo" "$Y"
rm -f "$D"/data/querylog.json "$D"/data/querylog.json.1 "$D"/data/stats.db
systemctl start AdGuardHome
sleep 2
systemctl is-active AdGuardHome
sed -n '/^querylog:/,/^[a-z]/p;/^statistics:/,/^[a-z]/p' "$Y" | grep -E '^[a-z]|enabled'
ls "$D"/data
rm -f "$Y.antes-privacidade"
