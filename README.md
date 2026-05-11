# sakusen 策戦

Terminal-native multiplayer space strategy. Python + FastAPI backend, Textual TUI client. The same REST API will later serve a web frontend.

> **策戦 / sakusen** — Japanese for "strategy, military operation".

## Architecture

```
+----------+      +----------+      +----------+
| sakusen  |  ..  | sakusen  |  ..  | sakusen  |    <- players (terminal TUI)
| (mert)   |      | (ali)    |      | (veli)   |
+----+-----+      +----+-----+      +----+-----+
     |                 |                 |
     +-- HTTPS/HTTP ---+-----------------+
                       |
            +----------v-----------+
            | main backend (host)  |
            | sakusen.space:9931   |
            | FastAPI + Postgres   |
            +----------------------+
```

- **Operator** runs `docker compose up -d` to host the backend permanently
- **Players** install the `sakusen` CLI and point it at the server via `SAKUSEN_BACKEND`
- **Solo offline mode** still works: `sakusen --solo` spawns a private SQLite backend

---

## Player install (one command)

### 1. Install uv (if missing)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install sakusen

Private repo (SSH):

```bash
uv tool install --python 3.12 "git+ssh://git@github.com/cobanov/space-galactic-tui.git"
```

Public (or use the install script):

```bash
uv tool install --python 3.12 "git+https://github.com/cobanov/space-galactic-tui.git"
# or:
curl -fsSL https://raw.githubusercontent.com/cobanov/space-galactic-tui/main/scripts/install.sh | sh
```

### 3. Point at the main server

```bash
export SAKUSEN_BACKEND="https://sakusen.space"   # production
# or: export SAKUSEN_BACKEND="http://localhost:9931" if you self-host
```

(The legacy `OGAME_BACKEND` env var still works as a fallback.)

### 4. Launch + sign in

```bash
sakusen
```

First run prints a URL like `https://sakusen.space/login?code=…`. Open it in
your browser, sign in or create an account; the terminal polls and picks up
your session within ~2 seconds. The token is saved to
`~/.config/sakusen/credentials.json` (mode 0600) so future runs are silent.

(`ogame` is kept as a transitional alias of `sakusen` and will be removed
in a future release.)

### 5. Play

The TUI is a single-screen REPL — Claude Code style slash commands:

```
> /help                            # all commands
> /planet                          # current planet detail
> /buildings                       # building levels + cost
> /upgrade metal_mine              # +1 level
> /research                        # tech list
> /tree                            # tech tree with prereqs
> /galaxy 4:28                     # system view
> /queue                           # active build/research queue
> /cancel 42                       # refund
> /ships                           # shipyard
> /build small_cargo 10            # batch construct
> /fleets                          # active fleet movements
> /espionage 1:42:8                # send probes
> /attack 1:42:8 cruiser:5         # attack
> /msg                             # conversation list
> /msg <user>                      # WhatsApp-style chat
> /logs                            # recent planet events
> /speed                           # universe speed (admin only)
> /logout                          # forget saved key
> /q                               # exit
```

Slash optional: typing `queue` is the same as `/queue`. Tab autocompletes.
Up/Down navigate command history (or popup, if visible). The autosuggester
shows a ghost completion from history; Right/End/Tab accept it.

### Solo (offline)

```bash
sakusen --solo                     # local SQLite at ~/.local/share/sakusen
sakusen --logout                   # forget the saved token
```

---

## Operator install (host the main server)

```bash
git clone git@github.com:cobanov/space-galactic-tui.git
cd space-galactic-tui

cp .env.example .env
# Edit .env:
#   JWT_SECRET=$(openssl rand -hex 32)
#   ADMIN_USERNAME=<your-username>   <- gives /admin + /speed access

make server-up                     # postgres + backend container, host port 9931
make server-logs
```

Health check: `curl http://localhost:9931/health` → `{"status":"ok"}`.

| Make target | What it does |
|-------------|--------------|
| `make server-up` | postgres + backend (build + start) |
| `make server-down` | stop both |
| `make server-restart` | restart backend (no env reread) |
| `make server-reload` | recreate backend (reads new `.env`) |
| `make server-build` | rebuild backend image |
| `make server-logs` | tail backend logs |
| `make server-ps` | status |

**`.env` changes need `make server-reload`, not `restart`** — `restart` keeps the old env.

### Exposing to the public

- **Tailscale**: easiest, no static IP, 5-minute setup
- **Cloudflare Tunnel**: TLS + named subdomain (e.g. `sakusen.space` → your home box)
- **Caddy / Nginx + DNS**: reverse proxy with Let's Encrypt

### Admin

If `ADMIN_USERNAME` is set in `.env`, that user sees:
- `[admin]` link in the dashboard topbar → `/admin` panel
- TUI `/speed N` command (universe speed multiplier, 1..100)
- Web admin: edit user tech levels, planet resources, buildings, ships, defenses; create planets; delete planets

### Backup / reset

```bash
docker compose exec postgres pg_dump -U ogame ogame > backup.sql
docker compose down -v             # WIPES the postgres volume (irreversible)
```

---

## Development

```bash
git clone git@github.com:cobanov/space-galactic-tui.git
cd space-galactic-tui
make install                       # uv venv + dev deps
make up                            # postgres only (run backend on host)
make dev                           # uvicorn --reload on :8000
make test                          # 32 tests
```

`make dev` runs on port 8000 (host process); the docker container runs on 9931.
They can coexist for testing.

## Mechanics

- **Backend headless**, TUI is one of many clients. Same REST API will serve a future web frontend.
- **Lazy resource update**: not tick-based; every API touch advances production
  from `resources_last_updated_at` using OGame formulas.
- **Pure formulas**: `backend/app/game/` is DB-free, mockable, unit-tested
  against published Fandom values (Metal Mine, Crystal Mine, Deuterium
  Synthesizer, Solar Plant, Solar Satellite, Fusion Reactor, energy
  consumption all match to the floor/ceil).
- **Schema-first**: all OGame constants live in `game/constants.py`.

See `CLAUDE.md` for the formula source-of-truth (OGame Fandom Wiki) and
`tasks.md` for the phased roadmap.

## Status

- [x] Auth + universe + planet spawn
- [x] Production + lazy resource update + energy throttling
- [x] Build queue + scheduler
- [x] Research tree
- [x] Galaxy view
- [x] Textual REPL TUI with slash commands + autocomplete
- [x] Docker compose for the main backend
- [x] Device-flow auth (CLI ↔ browser) + cookie-auth web dashboard
- [x] Messaging (threads, conversations, unread counts)
- [x] Planet activity logs
- [x] Ships (12 types), defenses (8 types), fleet missions, simplified combat, espionage
- [x] Web admin panel for tuning users/planets/universe
- [x] CLI command history + prefix-match autosuggest
- [ ] Full OGame rapid-fire combat chart (currently single-round simplified)
- [ ] Recycler debris collection
- [ ] Manual colonization (auto-spawn only)
- [ ] Alliances + ACS

## Troubleshooting

**`sakusen: command not found`** → `~/.local/bin` not in `PATH`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

**TUI says "can't reach backend"** → check `$SAKUSEN_BACKEND`:
```bash
echo $SAKUSEN_BACKEND
curl $SAKUSEN_BACKEND/health
```

**`uv tool install` git auth error** → check SSH:
```bash
ssh -T git@github.com
```

**Reset solo data** → `rm -rf ~/.local/share/sakusen/`
**Reset host data** → `docker compose down -v` (irreversible)
