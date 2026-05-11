# Space Galactic

OGame'in TUI tabanli, online (multiplayer) Python klonu. Terminalden oynanir, backend FastAPI'dir, ayni API ileride bir web istemcisine de hizmet edecektir.

## Mimari ozeti

```
+---------+        +---------+        +---------+
| ogame   |  ...   | ogame   |  ...   | ogame   |    <- oyuncular (her makinada TUI)
| (Mert)  |        | (Ali)   |        | (Veli)  |
+----+----+        +----+----+        +----+----+
     |                  |                  |
     +---- HTTPS / HTTP-+------------------+
                        |
                        v
            +-----------------------------+
            | ana backend (container)     |
            | http://operator-host:9931   |
            | (FastAPI + Postgres)        |
            +-----------------------------+
```

- **Operator** (siz) `docker compose up -d` ile container'i kalici calistirir
- **Oyuncular** `ogame` komutuyla baglanir; `OGAME_BACKEND` env var'i ile sunucu adresini set ederler
- Solo mod hala mevcut: `ogame --solo` ile internet gerekmeden lokal SQLite

---

## Oyuncu kurulumu (tek komut)

### 1. uv kur (yoksa)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. ogame'i tool olarak kur

Private repo donemi (SSH ile):

```bash
uv tool install --python 3.12 "git+ssh://git@github.com/cobanov/space-galactic-tui.git"
```

Public olunca:

```bash
uv tool install --python 3.12 "git+https://github.com/cobanov/space-galactic-tui.git"
# veya
curl -fsSL https://raw.githubusercontent.com/cobanov/space-galactic-tui/main/scripts/install.sh | sh
```

### 3. Backend URL'ini set et

`.zshrc` veya `.bashrc` dosyana ekle:

```bash
export OGAME_BACKEND="http://OPERATOR-HOST:9931"
```

### 4. Hesap ac ve oyna

```bash
ogame
```

Ilk calistirmada terminal sana bir URL gosterir:

```
Space Galactic
--------------

Oynamak icin bir key gerekiyor.

1. Tarayicinda bu URL'i ac:
   http://operator-host:9931/signup

2. Formu doldur, cikan key'i kopyala.

3. Asagiya yapistir:

Key>
```

Tarayicida formu doldur, cikan uzun JWT key'i kopyala, terminale yapistir Enter. Key
`~/.config/ogame/credentials.json` icine 0o600 izniyle kaydedilir, bir daha sormaz.

### 5. Oyna - slash commands

TUI tek bir REPL ekranidir, Claude Code tarzi slash komutlar:

```
> /help                            # tum komutlar
> /planet                          # mevcut gezegen detayi
> /buildings                       # bina seviyeleri + cost
> /upgrade metal_mine              # 1 seviye yukselt
> /research                        # tum teknolojiler
> /research energy                 # tek seviye yukselt
> /galaxy 4:28                     # sistem gorunumu
> /queue                           # aktif insaat/arastirma
> /cancel 42                       # queue id 42 iptal et
> /planets                         # tum gezegenlerim
> /switch 7                        # aktif gezegeni 7'ye degistir
> /me                              # kim oldugum
> /logout                          # key sil ve cik
> /q                               # cikis
```

Kisaltmalar: `/b` = `/buildings`, `/r` = `/research`, `/g` = `/galaxy`, `/p` = `/planet`,
`/u` = `/upgrade`. Slash yazmasan da olur (`buildings` aynisi).

Status bar (ust): gezegen, kaynaklar, +M/+C/+D per saat, enerji dengesi.

### Solo (offline)

```bash
ogame --solo                       # lokal SQLite, ~/.local/share/ogame/
ogame --logout                     # backend'den kayitli key'i sil
```

### Komut ozet

```bash
ogame                              # OGAME_BACKEND'e bagla
ogame --remote http://host:9931    # explicit URL
ogame --solo                       # offline solo
ogame --logout                     # bu backend icin key'i unut
ogame-server                       # backend'i sun (operator icin)
ogame --help
```

---

## Operator kurulumu (ana backend host)

Container 9931 portunda calisir, postgres ile birlikte.

```bash
git clone git@github.com:cobanov/space-galactic-tui.git
cd space-galactic-tui

# 1. .env yarat ve JWT secret uret
cp .env.example .env
sed -i.bak "s|change-me-generate.*|$(openssl rand -hex 32)|" .env

# 2. Container'i baslat
make server-up                # docker compose up -d --build
make server-logs              # tail -f

# 3. Health check
curl http://localhost:9931/health
```

`make server-up` postgres + backend'i ayaga kaldirir, host port `9931` -> container port `8000`. Ayar gerekirse `HOST_PORT=9000 docker compose up -d`.

### Operator komutlari

| Komut                  | Aciklama                          |
|------------------------|-----------------------------------|
| `make server-up`       | postgres + backend (build + start)|
| `make server-down`     | her ikisini durdur                |
| `make server-restart`  | sadece backend'i restart          |
| `make server-build`    | backend image'i tekrar build et   |
| `make server-logs`     | backend logs -f                   |
| `make server-ps`       | durum                             |

### Backend'i internete acmak

LAN icin: TUI'lerden `http://YOUR-LAN-IP:9931` kullanir.

Internet icin (tavsiye):

- **Tailscale**: `tailscale up`, sonra herkes `OGAME_BACKEND=http://your-tailnet-host:9931`
- **Cloudflare Tunnel**: kalici subdomain ile, TLS dahil
- **Caddy + DNS**: reverse proxy + Let's Encrypt

Tailscale en pratigi: kurulum 5 dk, statik IP yok problemi yok, JWT secret yine de set et.

### Verileri yedekle / sifirla

```bash
docker compose exec postgres pg_dump -U ogame ogame > backup.sql       # backup
docker compose down -v                                                 # sifirla (volume sil)
```

---

## Gelistirme

```bash
git clone git@github.com:cobanov/space-galactic-tui.git
cd space-galactic-tui
make install      # uv venv + dev deps
make up           # sadece postgres
make dev          # uv run uvicorn --reload (host'ta, port 8000)
make test         # 30 test
```

`make dev` 8000'de calisir; container 9931'de paralel calisabilir (port catismasi yok).

| Komut           | Aciklama                          |
|-----------------|-----------------------------------|
| `make install`  | uv venv + dev bagimliliklari      |
| `make dev`      | host'ta uvicorn reload (8000)     |
| `make tui`      | TUI (lokal dev backend'e baglanir)|
| `make test`     | pytest                            |
| `make lint`     | ruff check + format check         |
| `make typecheck`| mypy                              |
| `make clean`    | .venv + cache temizle             |

---

## Mimari prensipleri

- **Backend headless**, TUI yalnizca istemci. Ayni REST API ileride web frontend'e de hizmet edecek.
- **Lazy update**: kaynaklar tick-tick yazilmaz, view edildiginde son guncellemeden bu yana gecen sure icin uretim formulu calistirilir.
- **Pure formuller**: tum oyun matematigi `backend/app/game/` altinda, DB-free, test edilebilir.
- **Schema-first sabitler**: tum OGame sabitleri (`game/constants.py`) tek yerde.

Detay: `CLAUDE.md` (formul kaynaklari, single source of truth) ve `tasks.md` (faz planlamasi).

## Faz durumu

- [x] Faz 0 - Iskelet (uv, docker, alembic)
- [x] Faz 1 - Auth + universe + ilk gezegen
- [x] Faz 2 - Maden + enerji uretimi (lazy update)
- [x] Faz 3 - Bina insaati (queue + scheduler)
- [x] Faz 4 - Arastirma agaci
- [x] Faz 5 - Galaksi gorunumu
- [x] Faz 6 - TUI istemci
- [ ] Faz 7+ post-MVP: filo, savas, espionage, ittifak, ay (tasks.md)

## Sorun giderme

**`ogame: command not found`** -> `~/.local/bin` PATH'de degil. `.bashrc/.zshrc`'ye ekle:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

**TUI acilmiyor, "baglanamiyor"** -> `OGAME_BACKEND` set mi? `curl $OGAME_BACKEND/health` cevap veriyor mu? Operator'a sor: container hala healthy mi (`make server-ps`).

**`uv tool install` git auth hatasi** -> SSH key'in GitHub'a ekli mi? `ssh -T git@github.com` ile dogrula.

**Verileri sifirla (solo)** -> `rm -rf ~/.local/share/ogame/`.

**Verileri sifirla (operator)** -> `docker compose down -v` (postgres volume silinir, butun veri gider, dikkat).
