# CLAUDE.md

Bu dosya, Claude Code'un bu repoda calistigi zaman izleyecegi rehberdir. Proje OGame'in TUI tabanli, online (multiplayer) bir klonudur. Backend bilincli olarak web'e tasinabilir sekilde tasarlanir: TUI yalnizca bir istemcidir.

## Proje ozeti

OGame'in temel mekaniklerini (galaksi/sistem/gezegen kosulleri, maden uretimi, enerji dengesi, deuterium sentezi, arastirma agaci, gemi/savunma uretimi, filo gorevleri) Python ile yeniden yazmak. MVP'de TUI istemci ile oynanir, fakat ayni REST/WebSocket API daha sonra web istemcisine de hizmet edecek.

## Resmi referans kaynagi: OGame Fandom Wiki

**Bu projenin tek dogru kaynagi (single source of truth) icin OGame mekanikleri:** [https://ogame.fandom.com/wiki/OGame_Wiki](https://ogame.fandom.com/wiki/OGame_Wiki)

Bu CLAUDE.md icindeki formuller, tablolar ve sabitler OGame Fandom'dan alinmistir. **Bilgi eksikligi veya supheli durum oldugunda her zaman ilk once OGame Fandom Wiki'ye git ve oradan dogrula.** Hafizadan veya tahminden formul yazma; Fandom'da kontrol et.

### Ne zaman Fandom'a basvur

- Bu CLAUDE.md'de tablosu/formulu olmayan herhangi bir mekanik (gemi hizlari, savas formulleri, espionage olasiliklari, ay olusum sansi, expedition tablolari, vs.)
- Bir formul tutarsiz duruyorsa veya test edilen sonuc beklenmediyse
- Yeni bir bina/arastirma/gemi/savunma turu eklerken cost, prereq, ozellik dogrulamasi
- Tech tree prerekizit zinciri belirsizken
- OGame redesigned vs eski universe farklari (redesigned'i baz al)
- Speed universe carpanlarinin (ekonomi/filo/arastirma) hangi formule nasil girdigi
- Bir sayisal sabit (sabit deger gibi gorunen seyler, orn: solar satellite max 65 enerji, deuterium production'in T=340'ta sifirlanmasi gibi) sorgulaniyorsa

### Faydali sayfalar (sik basvurulanlar)

- [Formulas](https://ogame.fandom.com/wiki/Formulas) - tum temel formuller bir arada
- [Metal Mine](https://ogame.fandom.com/wiki/Metal_Mine), [Crystal Mine](https://ogame.fandom.com/wiki/Crystal_Mine), [Deuterium Synthesizer](https://ogame.fandom.com/wiki/Deuterium_Synthesizer)
- [Solar Plant](https://ogame.fandom.com/wiki/Solar_Plant), [Solar Satellite](https://ogame.fandom.com/wiki/Solar_Satellite), [Fusion Reactor](https://ogame.fandom.com/wiki/Fusion_Reactor)
- [Temperature](https://ogame.fandom.com/wiki/Temperature), [Position](https://ogame.fandom.com/wiki/Position), [Colonization](https://ogame.fandom.com/wiki/Colonization)
- [Colonizing in Redesigned Universes](https://ogame.fandom.com/wiki/Colonizing_in_Redesigned_Universes) - pozisyon bonuslari, alan araliklari
- [Technology](https://ogame.fandom.com/wiki/Technology) - tech tree
- [Research](https://ogame.fandom.com/wiki/Research) - arastirma maliyet/zaman formulleri
- [Ships](https://ogame.fandom.com/wiki/Ships), [Defense](https://ogame.fandom.com/wiki/Defense) - Faz 7+ icin
- [Combat](https://ogame.fandom.com/wiki/Combat) - savas mekanikleri

### Davranis kurali

Iki adimli yaklasim:

1. **Yeni mekanik implementasyonu oncesi:** Ilgili Fandom sayfasini oku (web_fetch veya browser ile). Forma alinan formulu/tabloyu kod yorumunda kaynakla birlikte belirt:
   ```python
   # Source: https://ogame.fandom.com/wiki/Metal_Mine
   # Production = 30 * level * 1.1^level * speed * (1 + plasma * 0.01)
   def metal_mine_production(level: int, ...) -> float:
       ...
   ```

2. **Implementasyon sirasinda supheli durumda:** Sessizce devam etme. Fandom'a git, dogrula, sonra implemente et. Eger Fandom'da da net olmayan bir konu varsa (orn: redesigned universe'lerde formul versiyonu), bunu kullaniciyla acikca konus.

**Asla** uydurma; **asla** "muhtemelen soyledir" diyerek formul yazma. Bilgi yoksa, Fandom'a git.

## Teknoloji yigini

- **Dil:** Python 3.12+
- **Backend cerceve:** FastAPI (REST + WebSocket)
- **ORM:** SQLAlchemy 2.x (async)
- **Migration:** Alembic
- **Veritabani:** PostgreSQL 16+ (asyncpg surucusu)
- **Validation/serialization:** Pydantic v2
- **TUI:** Textual (rich tabanli, modern, async dostu)
- **Auth:** JWT (python-jose) + bcrypt (passlib)
- **Background tasks:** APScheduler (MVP) -> ileride Celery/Redis veya Postgres-tabanli queue
- **HTTP istemci (TUI -> backend):** httpx (async)
- **Test:** pytest, pytest-asyncio, httpx ile entegrasyon testleri
- **Lint/format:** ruff, mypy
- **Paket yoneticisi:** uv (pyproject.toml)
- **Container:** docker-compose (postgres + backend)

## Mimari prensipleri

### 1. Backend headless'tir, TUI sadece bir istemci

TUI hicbir oyun mantigi icermez. Tum hesaplamalar (uretim, savas, filo varis suresi) backend'de yapilir. TUI:

- HTTP cagrilari ile state alir
- WebSocket uzerinden push event dinler (filo varisi, saldiri uyarisi, insaat tamamlandi)
- Sadece sunum + input toplama yapar

Bu, ayni API'nin daha sonra React/Next.js frontend'e hizmet etmesini saglar.

### 2. Time-based "lazy" simulasyon

OGame'de uretim sureklidir ama biz her saniye DB yazmayiz. Bunun yerine:

- Her gezegenin `resources_last_updated_at` timestamp'i vardir
- Birisi gezegene baktiginda veya bir aksiyon yaptiginda, `now - last_updated` araligi icin uretim formulu calistirilir, kaynaklar guncellenir, timestamp ileri sarilir
- "Lazy evaluation" pattern. Battle/fleet arrival gibi olaylar icin scheduled job kullanilir

Bu pattern OGame'in 20+ yildir kullandigi yaklasimdir; trustable.

### 3. Schema-first, deterministic formuller

Tum oyun sabitleri (`game_constants.py`) tek bir yerde tanimlanir. Formuller saf fonksiyonlardir (input -> output, side effect yok). Bu test edilebilirligi maksimize eder.

### 4. Universe (evren) konsepti

Bir "universe" = bir oyun dunyasi. Birden fazla universe paralel calisabilir (farkli hizlar, farkli ayarlar). Tum oyuncular ve gezegenler bir universe'e bagliyidir. Galaksi yapisi:

- 1 universe = N galaksi (default 9)
- 1 galaksi = M sistem (default 499)
- 1 sistem = 15 gezegen slotu

Bir oyuncu universe'e kayit olurken sistem rasgele bir gezegen atar (4-12 araligi default, astrofizik gerektirmez).

## OGame oyun mekanikleri (kritik formuller)

> **Kaynak:** Bu bolumdeki tum formuller ve tablolar [OGame Fandom Wiki](https://ogame.fandom.com/wiki/Formulas)'den derlenmistir. Bir deger tutarsiz duruyorsa veya eksik bir mekanik gerekiyorsa, **once Fandom'a git, dogrula, sonra implemente et.** (Yukaridaki "Resmi referans kaynagi" bolumune bak.)

Tum formuller `1.1x` evren hizi icin temel; `speed` carpani uretim ve insaat suresine etki eder.

### Maden uretimi (saatlik, base)

Sabitler:
- `T` = gezegenin maksimum sicakligi (°C)
- `L` = bina seviyesi
- `speed` = universe ekonomi hizi (default 1)
- `plasma` = Plasma Technology seviyesi (advanced; MVP'de 0)
- `position_bonus_metal`, `position_bonus_crystal` = pozisyona gore yuzdesel bonus

Base formuller:

```
metal_per_hour    = 30 * L * 1.1^L * speed * (1 + plasma * 0.01) * (1 + position_bonus_metal)
crystal_per_hour  = 20 * L * 1.1^L * speed * (1 + plasma * 0.0066) * (1 + position_bonus_crystal)
deuterium_per_hour = 10 * L * 1.1^L * (1.28 - 0.002 * T) * speed * (1 + plasma * 0.0033)
```

Base passive uretim (level 0 madenler dahi uretir):
```
base_metal    = 30 * speed
base_crystal  = 15 * speed
base_deuterium = 0
```

Tum uretim sonuclari floor edilir.

### Enerji

```
solar_plant_output    = floor(20 * L * 1.1^L)
solar_satellite_output = floor((avg_temp + 160) / 6)   # max 65 per sat
fusion_reactor_output = floor(30 * L * (1.05 + energy_tech * 0.01)^L)
fusion_deut_consumption = floor(10 * L * 1.1^L)        # saatlik deut tuketimi

mine_energy_consumption(building, L) = ceil(coeff * L * 1.1^L)
  # coeff: metal=10, crystal=10, deuterium=20
```

**Enerji dengesi:**
```
production_factor = min(1.0, total_energy_produced / total_energy_consumed)
```
Negatif enerji => `production_factor < 1.0` => tum madenler bu oranda uretir.

### Sicaklik (gezegene pozisyona gore)

Sicaklik aralik halinde: `[T_min, T_max]` ve `T_max = T_min + 40`. Pozisyona gore yaklasik aralik:

| Position | T_max range  |
|----------|--------------|
| 1        | 220 to 260   |
| 2        | 170 to 210   |
| 3        | 120 to 160   |
| 4        | 70 to 110    |
| 5        | 60 to 100    |
| 6        | 50 to 90     |
| 7        | 40 to 80     |
| 8        | 30 to 70     |
| 9        | 20 to 60     |
| 10       | 10 to 50     |
| 11       | 0 to 40      |
| 12       | -10 to 30    |
| 13       | -50 to -10   |
| 14       | -90 to -50   |
| 15       | -130 to -90  |

Kolonizasyon aninda T_max bu araliktan rasgele secilir, T_min = T_max - 40. Uretim formullerinde `T = T_max` kullanilir.

### Pozisyon bonuslari (uretim)

| Position | Metal bonus | Crystal bonus |
|----------|-------------|---------------|
| 1        | 0%          | +40%          |
| 2        | 0%          | +30%          |
| 3        | 0%          | +20%          |
| 6        | +17%        | 0%            |
| 7        | +23%        | 0%            |
| 8        | +35%        | 0%            |
| 9        | +23%        | 0%            |
| 10       | +17%        | 0%            |
| Other    | 0%          | 0%            |

Deuterium bonusu yok; soguk slotlar (13-15) zaten dusuk T sayesinde dogal olarak fazla deuterium uretir.

### Gezegen alan (field) sayisi

Pozisyona gore typical range:

| Position | Fields range |
|----------|--------------|
| 1        | 40 to 80     |
| 2        | 45 to 90     |
| 3        | 50 to 100    |
| 4        | 90 to 175    |
| 5        | 120 to 230   |
| 6-9      | 140 to 260   |
| 10-12    | 100 to 200   |
| 13-15    | 50 to 110    |

Kolonizasyonda rasgele secilir, daha sonra Terraformer ile artirilabilir (MVP scope disi).

### Insaat maliyeti

Genel formul: `cost(L+1) = base_cost * factor^L`, sadece base ve factor degisir:

| Building              | Base Metal | Base Crystal | Base Deut | Cost Factor |
|-----------------------|-----------:|-------------:|----------:|------------:|
| Metal Mine            | 60         | 15           | 0         | 1.5         |
| Crystal Mine          | 48         | 24           | 0         | 1.6         |
| Deuterium Synthesizer | 225        | 75           | 0         | 1.5         |
| Solar Plant           | 75         | 30           | 0         | 1.5         |
| Fusion Reactor        | 900        | 360          | 180       | 1.8         |
| Robotics Factory      | 400        | 120          | 200       | 2.0         |
| Shipyard              | 400        | 200          | 100       | 2.0         |
| Research Lab          | 200        | 400          | 200       | 2.0         |
| Metal Storage         | 1000       | 0            | 0         | 2.0         |
| Crystal Storage       | 1000       | 500          | 0         | 2.0         |
| Deuterium Tank        | 1000       | 1000         | 0         | 2.0         |

### Arastirma maliyeti

`cost(L+1) = base_cost * 2^L` (cogu arastirma icin; Astrophysics 1.75, Graviton 3.0).

MVP icin gerekli teknolojiler:

| Tech                    | Base M | Base C | Base D | Lab req | Prereq                  |
|-------------------------|-------:|-------:|-------:|--------:|-------------------------|
| Energy Technology       | 0      | 800    | 400    | 1       | -                       |
| Laser Technology        | 200    | 100    | 0      | 1       | Energy 2                |
| Ion Technology          | 1000   | 300    | 100    | 4       | Energy 4, Laser 5       |
| Hyperspace Technology   | 0      | 4000   | 2000   | 7       | Energy 5                |
| Plasma Technology       | 2000   | 4000   | 1000   | 4       | Energy 8, Laser 10, Ion 5 |
| Computer Technology     | 0      | 400    | 600    | 1       | -                       |
| Astrophysics            | 4000   | 8000   | 4000   | 3       | Espionage 4, Impulse 3  |
| Espionage Technology    | 200    | 1000   | 200    | 3       | -                       |

(Drive ve combat tech'leri filo asamasinda eklenir, su asamada scope disi.)

### Insaat ve arastirma suresi

```
build_time_hours = (metal + crystal) / (2500 * (1 + robotics_factory_level) * speed * 2^nanite_factory_level)
research_time_hours = (metal + crystal) / (1000 * speed * (1 + research_lab_level))
```

Saniyeye cevirip queue'da `finished_at` olarak saklarsin.

## Project layout

```
ogame/
├── pyproject.toml
├── docker-compose.yml
├── alembic.ini
├── .env.example
├── README.md
├── CLAUDE.md
├── tasks.md
├── alembic/
│   └── versions/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app
│   │   ├── config.py               # pydantic-settings
│   │   ├── db.py                   # async engine, sessionmaker
│   │   ├── deps.py                 # FastAPI dependencies (get_db, get_current_user)
│   │   ├── security.py             # JWT, password hashing
│   │   ├── models/                 # SQLAlchemy ORM
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── universe.py
│   │   │   ├── planet.py
│   │   │   ├── building.py
│   │   │   ├── research.py
│   │   │   └── queue.py
│   │   ├── schemas/                # Pydantic
│   │   │   ├── auth.py
│   │   │   ├── planet.py
│   │   │   └── ...
│   │   ├── game/                   # SAF oyun mantigi (DB free)
│   │   │   ├── constants.py        # Tum sabitler, tablolar
│   │   │   ├── formulas.py         # Saf hesaplama fonksiyonlari
│   │   │   ├── production.py       # Maden + enerji uretimi
│   │   │   ├── colonization.py     # Planet generation logic
│   │   │   └── tech_tree.py        # Prereq checking
│   │   ├── services/               # ORM + game logic kopru
│   │   │   ├── resource_service.py # Lazy resource update
│   │   │   ├── build_service.py
│   │   │   ├── research_service.py
│   │   │   └── universe_service.py
│   │   ├── api/                    # FastAPI routers
│   │   │   ├── auth.py
│   │   │   ├── universe.py
│   │   │   ├── planet.py
│   │   │   ├── galaxy.py
│   │   │   ├── building.py
│   │   │   ├── research.py
│   │   │   └── ws.py               # WebSocket events
│   │   └── scheduler.py            # APScheduler: queue completion
│   └── tests/
├── tui/
│   ├── pyproject.toml              # Ayri paket
│   └── ogame_tui/
│       ├── __main__.py
│       ├── client.py               # httpx wrapper
│       ├── app.py                  # Textual App
│       └── screens/
│           ├── login.py
│           ├── overview.py
│           ├── buildings.py
│           ├── research.py
│           └── galaxy.py
└── shared/
    └── api_models.py               # TUI ve backend ortak Pydantic modelleri
```

## Veri modeli (high-level)

- `User`: id, username, email, password_hash, created_at, current_universe_id
- `Universe`: id, name, speed_economy, speed_fleet, speed_research, galaxies_count, systems_count, created_at
- `Planet`: id, owner_user_id, universe_id, galaxy, system, position, name, fields_used, fields_total, temp_min, temp_max, resources_metal, resources_crystal, resources_deuterium, resources_last_updated_at, energy_used, energy_produced
- `Building`: id, planet_id, building_type (enum), level
- `Research`: id, user_id, tech_type (enum), level  *(arastirma oyuncu bazli; gezegen bazli degil)*
- `BuildQueue`: id, planet_id, item_type (building/research/ship), item_key, target_level, started_at, finished_at
- `Coordinate`: PRIMARY KEY (universe_id, galaxy, system, position) UNIQUE => o slotta sadece bir gezegen olabilir

Bir oyuncu birden fazla universe'e kayit olabilir (her birinde ayri ilerleme). MVP'de tek universe yeterli ama schema buna hazir olsun.

## Gelistirme kurallari

### Kod stili

- **Em dash kullanma.** Em dash kullanma hicbir yerde.
- Async/await her zaman. Senkron DB cagrisi yok.
- Type hint her fonksiyonda zorunlu.
- Pydantic v2 syntax (`Field`, `model_config`, `ConfigDict`).
- SQLAlchemy 2.x syntax (`Mapped`, `mapped_column`, `select()`).
- Ruff + mypy strict mode CI'da pass etmeli.
- Saf oyun mantigi (`game/` altinda) DB modeline veya FastAPI'ye dokunmamali; pure function olmali.

### Test

- Tum formuller (`game/formulas.py`, `game/production.py`) icin birim test zorunlu.
- API endpoint'leri icin entegrasyon testi (httpx + TestClient).
- Lazy resource update icin time-travel testi: sahte `now` ile 1 saat ileri sar, kaynaklarin dogru hesaplandigini dogrula.

### Git

- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
- PR oncesi `ruff check`, `mypy`, `pytest` green olmali.

### Migration

- Schema degisikligi her zaman Alembic migration ile. `alembic revision --autogenerate -m "..."`, ardindan elle gozden gecir.

### Sirlar

- `.env` git'e girmez. `.env.example` template'i guncel tut.

## Onemli operasyonel notlar

- **Lazy update tetikleyicileri:** Her API cagrisi (overview goruntule, bina insa et, vs.) once `resource_service.refresh(planet_id)` cagirmali. Bu, son guncelleme tarihinden bu yana gecen sureyi hesaplar, uretim formulunu calistirir, DB'yi gunceller.
- **Race condition:** Ayni gezegene es zamanli iki insaat istegi gelirse, DB-level row lock (`SELECT ... FOR UPDATE`) ile build_queue kontrol edilmeli.
- **Scheduler:** APScheduler `finished_at <= now()` olan queue kayitlarini iceren bir job her 5-10 saniyede bir tarar ve uygular. WebSocket uzerinden oyuncuya event push'lar.
- **Coordinate unique:** Gezegen yaratimi `INSERT ... ON CONFLICT DO NOTHING` veya unique constraint exception yakalama ile yapilir; race-safe.

## Faz planlamasi

Detaylar `tasks.md` icinde. Faz hiyerarsisi:

1. Faz 0: Proje iskeleti
2. Faz 1: Auth + universe + ilk gezegen yaratimi
3. Faz 2: Maden + enerji uretimi (lazy update)
4. Faz 3: Bina insaati (queue + scheduler)
5. Faz 4: Arastirma agaci
6. Faz 5: Galaksi gorunumu
7. Faz 6: TUI istemci
8. Faz 7+: Filo, savas, ittifak (post-MVP)

Her faz icin tasks.md'de cikti, kabul kriterleri ve test gereksinimleri var. Sirayla ilerle, faz sonunda demo edebilecek durumda olmali.
