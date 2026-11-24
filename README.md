<h1 align="center"><img src="assets/banner.png" alt="firelink" width="600"></h1>

A home server built on an old laptop: shared folders for the family, movies and
classes on the TV and phones, comics and books in the browser, and a pixel-art home
page with a bonfire, a hooded keeper and Akali, the house cat.

Everything runs on the local network only. Nothing is exposed to the internet.

The home page interface is in Brazilian Portuguese, the language of the household.

## Hardware

| Item | Value |
|---|---|
| Laptop | ASUS X550C (2013) |
| CPU | Intel Core i5-3317U (Ivy Bridge, 4 threads), Intel HD 4000 graphics |
| Memory | 6 GB |
| Disk | 2.5" 500 GB HDD (451 GiB usable) |
| Network | Gigabit Ethernet (RTL8111), wired to the router |
| Power draw | ~7–12 W idle, lid closed |

## Services

| Service | Purpose | Where |
|---|---|---|
| Debian 13 (no desktop) | operating system | — |
| Samba + wsdd2 + Avahi | a shared `bau` folder plus one personal folder per person; shows up under *Network* on Windows and as `firelink.local` | `\\firelink`, `smb://firelink.local` |
| Jellyfin | movies, animations, series and recorded classes, with VA-API (i965) hardware acceleration for H.264, MPEG-2 and VC-1 | `:8096` |
| Kavita | comics (CBZ/CBR/PDF) and books (EPUB/PDF) with per-person reading progress | `:5000` |
| Caddy | home page and `/api/` proxy | `:80` |
| firelink-api | service status and Akali's scoreboard (Python, standard library only) | `127.0.0.1:8091` |
| nftables | accepts new connections from the home network only | — |
| smartd + firelink-smart | disk self-tests (short daily, long weekly) and a summary for the home page | — |
| unattended-upgrades | automatic security updates | — |

## Repository layout

```
page/         home page (a single HTML file) and the household config example
api/          firelink-api, its systemd unit (template) and the install script
scripts/      firelink-disk.sh (disk usage) and firelink-smart (disk health)
config/       samba, caddy, nftables, ssh, systemd, cron, apt and disks
assets/       README banner (rendered from the home page itself)
```

## The home page

A single HTML file with no dependencies besides two Google Fonts.

- **Pixel-art scene:** a procedurally generated bonfire, rising embers, a hooded keeper
  holding a candle, and Akali sleeping in a loaf pose.
- **The Keeper of the Flame:** on each device's first visit she asks who is there
  ("Quem se aproxima da fogueira?"), remembers the answer (`localStorage`) and greets
  that person by name, with lines that change with the time of day and on special dates.
- **Akali:** her eyes follow the cursor, her tail wags, she purrs (synthesized with the
  Web Audio API) when petted, swats when the cursor gets too close to her face or when
  someone touches her tail, accepts at most three pets in a row, and calls for attention
  ("Rrrrruuuuuuu!!!") when the page sits idle.
- **Server panel:** status lights for Jellyfin and Kavita, uptime, a disk usage bar, disk
  health (SMART, temperature, last self-test) and Akali's scoreboard of pets and swats per
  person, shared across devices.
- **Day and night:** a starry sky at night, warm light in the morning.
- **Special dates:** birthdays, Christmas (a twinkling tree all December), New Year and
  Mother's Day, with pixel confetti.

All artwork is original. The mood is inspired by Dark Souls; this project is not
affiliated with the game or its creators.

## Rebuilding the server

1. Install Debian 13 *netinst* without a desktop environment, selecting "SSH server" and
   "standard system utilities".
2. Packages: `samba wsdd2 avahi-daemon smartmontools acl hdparm nftables caddy
   unattended-upgrades i965-va-driver`, plus Jellyfin from its official repository
   (`config/apt/jellyfin.sources`).
3. Copy the files under `config/` to the matching paths in `/etc`. First adjust the
   home network range (`192.168.15.0/24`), the network interface name in `smb.conf`
   and the disk path in `config/disks/`.
4. Create the folders under `/srv/firelink` (`bau` plus one per person), a `bau` group
   with a default `rwx` ACL on `bau`, and read access for the `jellyfin` and `kavita`
   system users where needed; set Samba passwords with `smbpasswd -a`.
5. Kavita: extract the latest release `.tar.gz` into `/opt/Kavita` and use
   `config/systemd/kavita.service`.
6. Home page: copy `page/index.html` to `/srv/www/firelink/` and create `config.js` next
   to it from `config.example.js`, listing the household members, their birthdays and who
   gets Mother's Day greetings. The API reads the names from the same file.
7. Scripts and API: put `scripts/firelink-disk.sh` in `~/bin` with the crontab in
   `config/cron/crontab-user`; put the `api/` files and `scripts/firelink-smart` in
   `~/firelink-api`; then run `sudo sh ~/firelink-api/install.sh`.

## Configuration decisions

- **Firewall on the server itself.** The laptop gets a public IPv6 address; with no NAT
  on IPv6, protection would otherwise depend on the router. `nftables` accepts new
  connections only from `192.168.15.0/24` and `fe80::/10` and rejects everything else.
- **SSH accepts keys only** (`config/ssh/10-key-only.conf`): password login is disabled;
  a local console login still works if the key is lost.
- **Caddy's network filter lives inside a `route` block.** In Caddy's default directive
  order `handle` runs before `respond`, so a `reverse_proxy` inside `handle` would bypass
  the filter for `/api/`. Inside `route`, the written order applies. The filter accepts
  the same sources as the firewall (home IPv4 range, loopback and IPv6 link-local).
- **Disk with `apm = 254`.** The drive was parking its heads very often (325 thousand load
  cycles recorded); on an always-on server that accelerates wear.
- **Closing the lid does not suspend** (`logind`), and the sleep targets are masked.
- **Kavita needs one subfolder per series or book**, and the volume number must sit
  outside brackets (`Series Vol. 1`), otherwise the file is treated as a one-off special.
- **Household data stays out of Git:** names, birthdays and Mother's Day live in
  `config.js` on the server only. The repository ships a fictional example.

## Copyright

© 2026 Gustavo Brandão Amaral. All rights reserved.

No license is granted for this repository, including the code and the pixel art
(Akali and the Keeper of the Flame). You are welcome to read it; reuse or
redistribution requires permission.
