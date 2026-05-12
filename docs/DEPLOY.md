# Deploying terminal.army on a remote host

This guide gets you from "blank Linux box" to "terminal.army serving HTTPS".

The backend runs in Docker (compose). What you decide is how the public
internet reaches port 9931:

- **Caddy** (recommended): single config file, automatic HTTPS
- **Cloudflare Tunnel**: no public IP needed, works behind NAT
- **Tailscale**: friends-only access without DNS at all
- **Plain HTTP**: for LAN / dev, no TLS

---

## 1. Prerequisites

On the server (assumed Ubuntu/Debian; adjust as needed):

```bash
# Docker + compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER  # log out + back in

# (optional) Caddy for TLS termination
sudo apt install -y caddy
```

Plus a DNS A/AAAA record `terminal.army` -> your server IP. (Skip if using
Tunnel or Tailscale.)

## 2. Clone + configure

```bash
git clone git@github.com:cobanov/terminal.army.git /opt/terminal-army
cd /opt/terminal-army
cp .env.example .env
```

Edit `/opt/terminal-army/.env`. At minimum set the **required** values
(see `.env.example` for the full list):

```env
ENV=prod
POSTGRES_PASSWORD=<openssl rand -hex 16>
JWT_SECRET=<openssl rand -hex 32>
CORS_ORIGINS=https://terminal.army
HOST_BIND=127.0.0.1
HOST_PORT=9931
ADMIN_USERNAME=<your_username>    # this account gets the admin panel
```

`JWT_SECRET` must be random and **persistent**: changing it invalidates every
existing session/token. `ENV=prod` enables the production safety gate that
refuses to boot with placeholder secrets or wildcard CORS.

## 3. Start

```bash
make server-up
# health: curl http://localhost:9931/health
```

Backend is now serving HTTP on the host's loopback at port 9931
(because `HOST_BIND=127.0.0.1`). Nothing public yet; pick an ingress
below.

## 4. Public ingress

### Option A: Caddy (recommended)

Drop the bundled config into Caddy and let it auto-issue Let's Encrypt:

```bash
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo sed -i "s/TERMINAL_ARMY_DOMAIN/terminal.army/g" /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

The bundled config (`deploy/Caddyfile.example`):

```Caddyfile
TERMINAL_ARMY_DOMAIN {
    encode gzip
    reverse_proxy 127.0.0.1:9931
}
```

That's it: Caddy gets a cert for `terminal.army`, terminates TLS, and
proxies to docker on 9931. The backend doesn't need any TLS config.

Verify: `curl https://terminal.army/health` -> `{"status":"ok"}`.

Players use:

```bash
export TA_BACKEND="https://terminal.army"
tarmy
```

### Option B: Cloudflare Tunnel (no public IP)

```bash
# On the server:
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

cloudflared tunnel login                  # opens browser
cloudflared tunnel create terminal-army
cloudflared tunnel route dns terminal-army terminal.army
cloudflared tunnel run --url http://localhost:9931 terminal-army
```

Stick that last line behind systemd for auto-start. TLS is provided by
Cloudflare's edge.

### Option C: Tailscale (friends-only LAN over WAN)

```bash
sudo tailscale up
# Note the device's Tailscale IPv4 (100.x.y.z) or MagicDNS name
```

Players (also on your tailnet):

```bash
export TA_BACKEND="http://100.x.y.z:9931"
tarmy
```

No DNS, no TLS hassle. Only the people you invite to the tailnet can reach
it. To let tailnet clients see the loopback-bound backend you may need
`HOST_BIND=0.0.0.0` in `.env` (and a tight firewall, see below).

### Option D: Plain HTTP (LAN / dev)

Set `HOST_BIND=0.0.0.0` in `.env`, expose the host's port 9931 to your
LAN/router, and tell players:

```bash
export TA_BACKEND="http://<your-ip>:9931"
tarmy
```

In dev (`ENV=dev`) the cookie is non-Secure so plain-HTTP login works.
In `ENV=prod` the cookie is always Secure and plain HTTP will not
preserve sessions; use Caddy / Cloudflare / Tailscale instead.

---

## 5. Auto-start at boot

If you used `make server-up`, the containers already have
`restart: unless-stopped` set. They come back on reboot.

If using cloudflared/caddy: enable them with systemctl:

```bash
sudo systemctl enable --now caddy
sudo systemctl enable --now cloudflared
```

## 6. Updates

```bash
cd /opt/terminal-army
git pull
make server-reload       # = `docker compose up -d backend` (recreates with new image + env)
```

`server-reload` forces a recreate so `.env` changes take effect.
`server-restart` only restarts the existing container (keeps old env).

## 7. Backups

```bash
docker compose exec postgres pg_dump -U tarmy tarmy > "terminal-army-$(date +%Y%m%d).sql"
```

Cron it nightly:

```
0 3 * * * cd /opt/terminal-army && docker compose exec -T postgres pg_dump -U tarmy tarmy | gzip > "/var/backups/terminal-army-$(date +\%Y\%m\%d).sql.gz" && find /var/backups -name 'terminal-army-*.sql.gz' -mtime +14 -delete
```

## 8. Resetting the universe

**Irreversible.** Wipes all players, planets, fleets:

```bash
docker compose down -v
make server-up
```

### Migrating from a pre-rename deployment

Older deployments used the postgres user and database `ogame`. The
current compose hardcodes `tarmy` instead, which is incompatible with
an existing pgdata volume. To preserve data:

```bash
# 1. Dump the old DB
docker compose exec -T postgres pg_dump -U ogame ogame > pre-rename.sql

# 2. Stop everything and wipe the volume
docker compose down -v

# 3. Boot just postgres so the new tarmy DB is created
docker compose up -d postgres

# 4. Restore (the dump's CREATE TABLEs land in the new tarmy DB)
docker compose exec -T postgres psql -U tarmy tarmy < pre-rename.sql

# 5. Start the backend
docker compose up -d backend
```

If you don't need the data, `docker compose down -v && make server-up`
is faster.

## 9. Admin & runtime tuning

The admin account is **not** created by signing up; signup refuses any
name matching `ADMIN_USERNAME` so nobody can squat it. Bootstrap it
once after first boot:

```bash
docker compose exec backend python -m backend.scripts.create_admin
```

Then sign in as that user. You'll see:

- `[admin]` link in the dashboard topbar
- A web panel at `/admin` to set universe speed (1..100), tune any user's
  tech levels, planet resources, buildings, ships, defenses, and create new
  planets

The admin panel is the **only** way to tune the universe in production: the
TUI client has no admin commands by design.

## 10. Firewall

Open inbound:

- **22/tcp**: SSH
- **80/tcp + 443/tcp**: Caddy (TLS, ACME challenges)
- 9931 should NOT be exposed publicly when fronted by Caddy/Cloudflare;
  Caddy already proxies it locally

```bash
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

## 11. Verify end-to-end

From your laptop:

```bash
curl https://terminal.army/health
# {"status":"ok"}

export TA_BACKEND="https://terminal.army"
tarmy
# -> device flow URL -> browser -> sign in -> TUI starts
```

If the TUI's top bar shows `commander <username>` and the planet card
loads, you're live.
