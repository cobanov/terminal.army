# Deploying sakusen on a remote host

This guide gets you from "blank Linux box" to "sakusen.space serving HTTPS".

The backend runs in Docker (compose). What you decide is how the public
internet reaches port 9931:

- **Caddy** (recommended) — single config file, automatic HTTPS
- **Cloudflare Tunnel** — no public IP needed, works behind NAT
- **Tailscale** — friends-only access without DNS at all
- **Plain HTTP** — for LAN / dev, no TLS

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

Plus a DNS A/AAAA record `sakusen.space` → your server IP. (Skip if using
Tunnel or Tailscale.)

## 2. Clone + configure

```bash
git clone git@github.com:cobanov/space-galactic-tui.git /opt/sakusen
cd /opt/sakusen
cp .env.example .env
```

Edit `/opt/sakusen/.env`:

```env
DATABASE_URL=postgresql+asyncpg://ogame:ogame@postgres:5432/ogame
JWT_SECRET=<openssl rand -hex 32>
JWT_EXPIRE_MINUTES=10080
DEFAULT_UNIVERSE_NAME=Galactica
DEFAULT_UNIVERSE_SPEED=1
SCHEDULER_INTERVAL_SECONDS=5
CORS_ORIGINS=*
HOST_PORT=9931
ADMIN_USERNAME=<your_username>    # this account gets the admin panel
```

Make `JWT_SECRET` random and **persistent** — changing it invalidates every
existing session/token.

## 3. Start

```bash
make server-up
# health: curl http://localhost:9931/health
```

Backend is now serving HTTP on the host's port 9931.

## 4. Public ingress

### Option A — Caddy (recommended)

Drop the bundled config into Caddy and let it auto-issue Let's Encrypt:

```bash
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo sed -i "s/SAKUSEN_DOMAIN/sakusen.space/g" /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

The bundled config (`deploy/Caddyfile.example`):

```Caddyfile
SAKUSEN_DOMAIN {
    encode gzip
    reverse_proxy 127.0.0.1:9931
}
```

That's it — Caddy gets a cert for `sakusen.space`, terminates TLS, and
proxies to docker on 9931. The backend doesn't need any TLS config.

Verify: `curl https://sakusen.space/health` → `{"status":"ok"}`.

Players use:

```bash
export SAKUSEN_BACKEND="https://sakusen.space"
sakusen
```

### Option B — Cloudflare Tunnel (no public IP)

```bash
# On the server:
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

cloudflared tunnel login                 # opens browser
cloudflared tunnel create sakusen
cloudflared tunnel route dns sakusen sakusen.space
cloudflared tunnel run --url http://localhost:9931 sakusen
```

Stick that last line behind systemd for auto-start. TLS is provided by
Cloudflare's edge.

### Option C — Tailscale (friends-only LAN over WAN)

```bash
sudo tailscale up
# Note the device's Tailscale IPv4 (100.x.y.z) or MagicDNS name
```

Players (also on your tailnet):

```bash
export SAKUSEN_BACKEND="http://100.x.y.z:9931"
sakusen
```

No DNS, no TLS hassle. Only the people you invite to the tailnet can reach
it.

### Option D — Plain HTTP (LAN / dev)

Just expose the host's port 9931 to your LAN/router and tell players:

```bash
export SAKUSEN_BACKEND="http://<your-ip>:9931"
sakusen
```

The cookie is configured with `secure=False` so plain-HTTP login works.

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
cd /opt/sakusen
git pull
make server-reload       # = `docker compose up -d backend` (recreates with new image + env)
```

`server-reload` forces a recreate so `.env` changes take effect.
`server-restart` only restarts the existing container (keeps old env).

## 7. Backups

```bash
docker compose exec postgres pg_dump -U ogame ogame > "sakusen-$(date +%Y%m%d).sql"
```

Cron it nightly:

```
0 3 * * * cd /opt/sakusen && docker compose exec -T postgres pg_dump -U ogame ogame | gzip > "/var/backups/sakusen-$(date +\%Y\%m\%d).sql.gz" && find /var/backups -name 'sakusen-*.sql.gz' -mtime +14 -delete
```

## 8. Resetting the universe

**Irreversible.** Wipes all players, planets, fleets:

```bash
docker compose down -v
make server-up
```

## 9. Admin & runtime tuning

Sign in as the user named in `ADMIN_USERNAME` (env var). You'll see:

- `[admin]` link in the dashboard topbar
- A web panel at `/admin` to set universe speed (1..100), tune any user's
  tech levels, planet resources, buildings, ships, defenses, and create new
  planets

The admin panel is the **only** way to tune the universe in production — the
TUI client has no admin commands by design.

## 10. Firewall

Open inbound:

- **22/tcp** — SSH
- **80/tcp + 443/tcp** — Caddy (TLS, ACME challenges)
- 9931 should NOT be exposed publicly when fronted by Caddy/Cloudflare —
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
curl https://sakusen.space/health
# {"status":"ok"}

export SAKUSEN_BACKEND="https://sakusen.space"
sakusen
# → device flow URL → browser → sign in → TUI starts
```

If the TUI's top bar shows `commander <username>` and the planet card
loads, you're live.
