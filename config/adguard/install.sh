#!/bin/sh
# Instala o AdGuard Home (binário oficial) em /opt/AdGuardHome como serviço do systemd.
# Rodar com sudo, na pasta onde estão o .tar.gz e o checksums.txt do release.
set -eu
[ "$(id -u)" = 0 ] || { echo "rode com sudo"; exit 1; }
cd "$(dirname "$0")"
D=/opt/AdGuardHome
[ -e "$D" ] && { echo "$D já existe; nada feito"; exit 1; }
grep " ./AdGuardHome_linux_amd64.tar.gz$" checksums.txt | sha256sum -c -
tar xzf AdGuardHome_linux_amd64.tar.gz -C /opt
chown -R root:root "$D"
"$D/AdGuardHome" -s install
systemctl is-enabled AdGuardHome
systemctl is-active AdGuardHome
