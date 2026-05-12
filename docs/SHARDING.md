# Multi-server (sharding) deployment

sakusen scales horizontally by running **one backend stack per universe**.
Each shard is fully independent — its own Postgres, its own players, its
own galaxy. There is no cross-server communication. A single **lobby**
page at `sakusen.space` lists all servers so new players can pick one.

Recommended per-shard capacity:

- 500 concurrent active users
- 5000 registered total (enforced at signup)
- 2 vCPU, 2 GB RAM, 10 GB disk
- ~$5–10/month VPS

This guide assumes you've already read `docs/DEPLOY.md` (basic single-server
deploy with Caddy / Docker).

---

## Naming convention

Servers are named **s1, s2, s3, ...** and reachable at `<id>.sakusen.space`:

- `s1.sakusen.space` — first shard
- `s2.sakusen.space` — second shard
- … etc

Each shard advertises itself by `SERVER_NAME` (env var) and gets its own
subdomain. New shards just continue the numbering.

---

## Topology

```
                  https://sakusen.space
                       (lobby only)
                              │
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
  s1.sakusen.space      s2.sakusen.space      s3.sakusen.space
   s1 (482/5000)         s2 (201/5000)         s3 (12/5000)
   own Postgres          own Postgres          own Postgres
```

- The lobby is a sakusen instance with `IS_LOBBY=true` and `LOBBY_SERVERS`
  configured. It polls each known shard's `/stats` endpoint and renders the
  picker. Signup/login on the lobby itself are disabled — users get
  redirected to a shard.
- Shards have `LOBBY_URL=https://sakusen.space` so signed-in players see
  "← lobby" in their topbar.
- Each shard has its own admin (`ADMIN_USERNAME` env), own universe speed,
  etc. — they don't share anything.

---

## Per-shard `.env`

```env
# Identity
SERVER_NAME=s1
SERVER_DESCRIPTION=the first universe
SERVER_MAX_USERS=5000
LOBBY_URL=https://sakusen.space
IS_LOBBY=false

# Standard
DATABASE_URL=postgresql+asyncpg://ogame:ogame@postgres:5432/ogame
JWT_SECRET=<unique per shard — openssl rand -hex 32>
JWT_EXPIRE_MINUTES=10080
DEFAULT_UNIVERSE_NAME=s1             # shows in galaxy text
DEFAULT_UNIVERSE_SPEED=1
ADMIN_USERNAME=<your username>
HOST_PORT=9931
```

Each shard's `JWT_SECRET` must be unique — otherwise tokens issued by one
shard could be replayed against another.

---

## Lobby `.env`

The lobby is a sakusen instance with **no players** — `IS_LOBBY=true`
turns off local signup/login and turns the `/` route into the server picker.

```env
# Lobby identity
IS_LOBBY=true
SERVER_NAME=lobby
SERVER_MAX_USERS=0

# Server list — id=url with optional :coming-soon suffix
LOBBY_SERVERS=s1=https://s1.sakusen.space,s2=https://s2.sakusen.space:coming-soon,s3=https://s3.sakusen.space:coming-soon

# Standard — Postgres still required (FastAPI needs a DB to start). A tiny
# instance is fine; the lobby holds zero game data.
DATABASE_URL=postgresql+asyncpg://ogame:ogame@postgres:5432/ogame
JWT_SECRET=<openssl rand -hex 32>
HOST_PORT=9931
```

The lobby renders cards at `https://sakusen.space/` listing each server
with live registered/max counts. Servers marked `:coming-soon` show as
disabled placeholders.

---

## Deployment patterns

### Pattern A — One shard per host

Recommended. Each shard is on its own $5–10 VPS.

- `sakusen.space` → 1 small VPS hosting the lobby instance
- `s1.sakusen.space` → 1 VPS hosting shard s1 (clone the repo, set
  per-shard `.env`, `make server-up`)
- `s2.sakusen.space` → 1 VPS hosting shard s2
- … etc

Each VPS has its own Caddy reverse-proxy pointing to its single docker
backend on `127.0.0.1:9931`. Use `deploy/Caddyfile.example` per host.

### Pattern B — All shards on one host

For tight budgets, stack everything on a single bigger machine (4 vCPU,
8 GB RAM). Use distinct `HOST_PORT` per shard:

```bash
# s1/
HOST_PORT=9931 docker compose -p s1 up -d

# s2/  (separate clone, separate volume)
HOST_PORT=9932 docker compose -p s2 up -d

# lobby/
HOST_PORT=9939 docker compose -p lobby up -d
```

Then Caddy on the same host:

```Caddyfile
s1.sakusen.space  { reverse_proxy 127.0.0.1:9931 }
s2.sakusen.space  { reverse_proxy 127.0.0.1:9932 }
sakusen.space     { reverse_proxy 127.0.0.1:9939 }
```

Note: `docker compose -p <name>` gives each stack its own project namespace
so their Postgres volumes don't collide. Without `-p` they'd share volumes
and corrupt each other.

---

## Adding a new shard

1. Pick the next id (s4, s5, …)
2. Provision a host (or reuse one with a free port)
3. Clone the repo to `/opt/sakusen-s4/`
4. Set its `.env` (unique `SERVER_NAME=s4`, unique `JWT_SECRET`)
5. `make server-up`
6. Add a Caddy block: `s4.sakusen.space { reverse_proxy 127.0.0.1:9931 }`
7. **Update the lobby's `LOBBY_SERVERS`** to mark s4 as live (or add it):
   ```
   LOBBY_SERVERS=s1=...,s2=...,s3=...,s4=https://s4.sakusen.space
   ```
8. `make server-reload` on the lobby (recreates the container so it reads
   the new env)

The new server appears in the lobby immediately.

---

## Removing / archiving a shard

When a universe is "dead" (no activity for 6 months, say):

1. Backup: `docker compose exec postgres pg_dump -U ogame ogame > s1-final.sql.gz`
2. Remove from lobby's `LOBBY_SERVERS`, `make server-reload` on lobby
3. Shut down the shard: `make server-down`
4. Optionally release the VPS

---

## Per-player capacity sizing

| Active users | RAM | CPU | Postgres conn pool | uvicorn workers |
|--------------|-----|-----|--------------------|--|
| 50 | 1 GB | 1 vCPU | 10 | 1 |
| 200 | 2 GB | 2 vCPU | 30 | 2 |
| 500 | 2 GB | 2 vCPU | 50 | 4 |
| 1000+ | 4 GB | 4 vCPU | 100 + pgbouncer | 4–8 |

At ~500 concurrent, a single shard usually consumes <30% CPU and <1 GB
RAM. The bottleneck is Postgres write contention on hot paths
(`refresh_planet_resources`, build queue). Pessimistic locking
(`SELECT … FOR UPDATE`) is already enabled in the codebase.

If a single shard saturates (sustained >70% CPU or DB IO at p95),
**split it** rather than scaling up — that's the entire point of
sharding.
