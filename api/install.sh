#!/bin/sh
# Installs on firelink: disk health report (root, hourly), the home page API (status + scoreboard) and the /api/ proxy in Caddy.
set -e
# user who ran sudo (owner of ~/firelink-api and of the API process)
USUARIO=${SUDO_USER:?run with sudo from your own user}
CASA=$(getent passwd "$USUARIO" | cut -d: -f6)
cd "$CASA/firelink-api"

# 1) disk health: root script + schedule
install -m 755 firelink-smart /usr/local/sbin/firelink-smart
printf '%s\n' '# firelink: disk health for the home page' \
  '17 * * * * root /usr/local/sbin/firelink-smart' \
  '@reboot root sleep 40 && /usr/local/sbin/firelink-smart' > /etc/cron.d/firelink-smart
/usr/local/sbin/firelink-smart

# 2) API (runs as your user, on 127.0.0.1:8091 only)
sed "s|%USUARIO%|$USUARIO|g; s|%HOME%|$CASA|g" firelink-api.service > /etc/systemd/system/firelink-api.service
chmod 644 /etc/systemd/system/firelink-api.service
systemctl daemon-reload
systemctl enable --now firelink-api
systemctl restart firelink-api

# 3) Caddy: the home-network filter also covers /api/
cp -n /etc/caddy/Caddyfile /etc/caddy/Caddyfile.antes-api
cat > /etc/caddy/Caddyfile <<'CADDY'
# firelink: home page + /api/, IPv4 only, home network only
{
	auto_https off
	admin off
}
:80 {
	bind 0.0.0.0
	root * /srv/www/firelink
	@fora not remote_ip 192.168.15.0/24 127.0.0.1/8 ::1 fe80::/10
	route {
		respond @fora 403
		reverse_proxy /api/* 127.0.0.1:8091
		file_server
	}
}
CADDY
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || { cp /etc/caddy/Caddyfile.antes-api /etc/caddy/Caddyfile; echo "Caddyfile ERROR; previous one restored"; exit 1; }
systemctl restart caddy

sleep 1
echo "smart.json: $(cat /srv/www/firelink/smart.json)"
echo "api/status: $(curl -s http://127.0.0.1/api/status)"
echo "INSTALL COMPLETE"
