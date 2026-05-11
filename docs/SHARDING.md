# Multi-server (sharding) deployment

Sakusen scales horizontally by running **one backend stack per universe**.
Each shard is fully independent — its own Postgres, its own players, its
own galaxy. There is no cross-server communication. A single **lobby**
page lists all servers so new players can pick one.

Recommended per-shard capacity:

- 500 concurrent active users
- 5000 registered total (enforced at signup)
- 2 vCPU, 2 GB RAM, 10 GB disk
- ~$5–10/month VPS

This guide assumes you've already read `docs/DEPLOY.md` (basic single-server
deploy with Caddy / Docker).

---

## Naming convention

Pick a theme. The project ships with a Japanese set that pairs with the
策戦 brand:

- **Yamato** (大和) — "great harmony"
- **Tengu** (天狗) — sky spirit
- **Akatsuki** (暁) — dawn
- **Ryu** (龍) — dragon
- **Kaiju** (怪獣) — giant monster
- **Hoshi** (星) — star
- **Sora** (空) — sky
- **Tsuki** (月) — moon

Each shard advertises itself by `SERVER_NAME` (env var) and gets its own
subdomain — e.g. `yamato.sakusen.space`, `tengu.sakusen.space`.

---

## Topology

```
                  https://sakusen.space
                  (lobby + install page)
                              │
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
 yamato.sakusen.space   tengu.sakusen.space   akatsuki.sakusen.space
  Yamato (482/500)      Tengu (201/500)       Akatsuki (12/500)
  own Postgres          own Postgres          own Postgres
```

- The lobby is just a sakusen instance with `LOBBY_SERVERS` configured. It
  polls each known shard's `/stats` endpoint and renders the list.
- Shards have `LOBBY_URL` pointing back to `sakusen.space` so signed-in
  players see "← lobby" in their topbar.
- Each shard has its own admin (`ADMIN_USERNAME` env), own universe speed,
  etc. — they don't share anything.

---

## Per-shard `.env`

```env
# Identity (the only difference between shards)
SERVER_NAME=Yamato
SERVER_DESCRIPTION=the first universe
SERVER_MAX_USERS=5000
LOBBY_URL=https://sakusen.space

# Standard
DATABASE_URL=postgresql+asyncpg://ogame:ogame@postgres:5432/ogame
JWT_SECRET=<unique per shard — openssl rand -hex 32>
JWT_EXPIRE_MINUTES=10080
DEFAULT_UNIVERSE_NAME=Yamato         # shows in galaxy text
DEFAULT_UNIVERSE_SPEED=1
ADMIN_USERNAME=<your username>
HOST_PORT=9931                       # per host this stays 9931 if one
                                     # shard per host, or 9931/9932/... if
                                     # multiple shards share a host
```

Each shard's `JWT_SECRET` must be unique — otherwise tokens issued by one
shard could be replayed against another.

---

## Lobby `.env`

The lobby is a sakusen instance with **no players**. It exposes only `/`,
`/install`, and `/stats` itself.

```env
# Lobby identity
SERVER_NAME=Lobby
SERVER_MAX_USERS=0                   # nobody can sign up here

# Server list (this is the magic — sakusen.space polls these)
LOBBY_SERVERS=Yamato=https://yamato.sakusen.space,Tengu=https://tengu.sakusen.space,Akatsuki=https://akatsuki.sakusen.space

# Standard — Postgres still required (FastAPI needs a DB to start, even if
# unused). A tiny instance is fine.
DATABASE_URL=postgresql+asyncpg://ogame:ogame@postgres:5432/ogame
JWT_SECRET=<openssl rand -hex 32>
HOST_PORT=9931
```

The lobby will render a table at `https://sakusen.space/` listing each
server with live registered/max counts and an "enter →" link.

---

## Deployment patterns

### Pattern A — One shard per host

Recommended. Each shard is on its own $5–10 VPS.

- `lobby.sakusen.space` → 1 small VPS hosting the lobby instance
- `yamato.sakusen.space` → 1 VPS hosting Yamato (clone the repo, set
  per-shard `.env`, `make server-up`)
- `tengu.sakusen.space` → 1 VPS hosting Tengu
- … etc

Each VPS has its own Caddy reverse-proxy pointing to its single docker
backend on `127.0.0.1:9931`. Use `deploy/Caddyfile.example` per host.

### Pattern B — All shards on one host

For tight budgets, stack everything on a single bigger machine (4 vCPU,
8 GB RAM). Use distinct `HOST_PORT` per shard:

```bash
# yamato/
HOST_PORT=9931 docker compose -p yamato up -d

# tengu/  (separate clone, separate volume)
HOST_PORT=9932 docker compose -p tengu up -d

# lobby/
HOST_PORT=9939 docker compose -p lobby up -d
```

Then Caddy on the same host:

```Caddyfile
yamato.sakusen.space  { reverse_proxy 127.0.0.1:9931 }
tengu.sakusen.space   { reverse_proxy 127.0.0.1:9932 }
sakusen.space         { reverse_proxy 127.0.0.1:9939 }
```

Note: `docker compose -p <name>` gives each stack its own project namespace
so their Postgres volumes don't collide. Without `-p` they'd share volumes
and corrupt each other.

---

## Adding a new shard

1. Pick a name from the unused list (Ryu, Kaiju, Hoshi, …)
2. Provision a host (or reuse one with a free port)
3. Clone the repo to `/opt/sakusen-ryu/`
4. Set its `.env` (unique `SERVER_NAME`, unique `JWT_SECRET`)
5. `make server-up`
6. Add a Caddy block: `ryu.sakusen.space { reverse_proxy 127.0.0.1:9931 }`
7. **Update the lobby's `LOBBY_SERVERS`** to include the new shard:
   ```
   LOBBY_SERVERS=Yamato=...,Tengu=...,Ryu=https://ryu.sakusen.space
   ```
8. `make server-reload` on the lobby (recreates the container so it reads
   the new env)

The new server appears in the lobby immediately.

---

## Removing / archiving a shard

When a universe is "dead" (no activity for 6 months, say):

1. Backup: `docker compose exec postgres pg_dump -U ogame ogame > yamato-final.sql.gz`
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
