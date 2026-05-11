# tasks.md

OGame klonunun gelistirme yol haritasi. Her faz icindeki gorevler sirayla yapilir. Faz sonunda "Faz cikti" bolumundeki kriterleri kontrol et: hepsi yesilse faz tamamlanmistir.

Genel kural: her gorev tek bir PR/commit'e sigacak kadar kucuk olmali. Buyuk gorunenler alt gorevlere bolunmustur.

---

## Faz 0: Proje iskeleti

Hedef: bos ama calisan bir FastAPI + Postgres + Alembic + test ortami.

### 0.1 Repo iskelet

- [ ] `pyproject.toml` olustur (uv ile). Backend ve TUI ayri subproject olarak (workspace structure veya iki ayri pyproject).
- [ ] Bagimliliklar: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic`, `pydantic-settings`, `python-jose[cryptography]`, `passlib[bcrypt]`, `httpx`, `apscheduler`, `textual`, `rich`.
- [ ] Dev bagimliliklari: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `types-passlib`.
- [ ] `.gitignore` (Python standart + `.env`, `.venv`, `__pycache__`, vs.).
- [ ] `.env.example` (DATABASE_URL, JWT_SECRET, JWT_ALGORITHM, vs.).
- [ ] `README.md` (kurulum, calistirma, dev workflow).
- [ ] `CLAUDE.md` (bu repo ile beraber commit edilmis durumda).

### 0.2 Docker setup

- [ ] `docker-compose.yml`: `postgres:16` servisi (volume, port 5432, sample creds .env'den).
- [ ] `make up` / `make down` / `make logs` icin basit Makefile veya `just`file.

### 0.3 FastAPI bootstrap

- [ ] `backend/app/main.py`: FastAPI app instance, CORS, `/health` endpoint.
- [ ] `backend/app/config.py`: `pydantic-settings` ile `.env` okuma (DATABASE_URL, JWT_SECRET, JWT_EXPIRE_MINUTES).
- [ ] `backend/app/db.py`: async engine, sessionmaker, `get_db()` dependency.
- [ ] `uvicorn backend.app.main:app --reload` calismali, `/health` 200 donmeli.

### 0.4 Alembic setup

- [ ] `alembic init alembic` ile baslat.
- [ ] `alembic/env.py` icinde DATABASE_URL config'den okusun, async engine ile uyumlu olsun.
- [ ] Ilk bos migration olustur ve calistir, baglanti dogrulansin.

### 0.5 Test iskeleti

- [ ] `pytest.ini` veya `pyproject.toml` [tool.pytest.ini_options] config'i.
- [ ] `backend/tests/conftest.py`: test DB icin ayri schema veya transactional rollback fixture.
- [ ] `test_health.py`: `/health` 200 donduguna dair smoke test.

### 0.6 Lint + format

- [ ] `ruff.toml` veya pyproject icinde ruff config (line length, select rules).
- [ ] `mypy.ini`: strict mode, `disallow_untyped_defs = True`.
- [ ] `pre-commit` config (optional ama tavsiye).

### Faz 0 cikti

- `uvicorn` ile backend ayaga kalkar, `/health` 200 doner.
- `pytest` calisir, en az 1 test gecer.
- `alembic upgrade head` hatasiz calisir.
- `docker compose up postgres` calisir, backend ona baglanir.

---

## Faz 1: Auth + universe + ilk gezegen yaratimi

Hedef: bir kullanici kayit olur, login olur, varsayilan universe'e dahil olur ve rasgele bir baslangic gezegeni alir.

### 1.1 Universe modeli

- [ ] `models/universe.py`: Universe ORM modeli (id, name, speed_economy=1, speed_fleet=1, speed_research=1, galaxies_count=9, systems_count=499, created_at, is_active).
- [ ] Alembic migration.
- [ ] Seed script: `scripts/seed_universe.py` ile bir default universe yaratir (idempotent).

### 1.2 User modeli + auth

- [ ] `models/user.py`: User (id, username unique, email unique, password_hash, created_at).
- [ ] `security.py`: `hash_password`, `verify_password`, `create_access_token`, `decode_token`.
- [ ] `schemas/auth.py`: `RegisterRequest`, `LoginRequest`, `TokenResponse`, `UserPublic`.
- [ ] `api/auth.py`: 
  - `POST /auth/register` -> kullanici yarat, hata: username/email zaten var.
  - `POST /auth/login` -> JWT doner.
  - `GET /auth/me` -> current user (deps.get_current_user kullanir).
- [ ] `deps.py`: `get_current_user` (Bearer token cozer, DB'den user cekers).
- [ ] Migration.

### 1.3 Planet modeli (sade)

- [ ] `models/planet.py`: Planet (id, owner_user_id FK, universe_id FK, galaxy, system, position, name, fields_used, fields_total, temp_min, temp_max, resources_metal, resources_crystal, resources_deuterium, resources_last_updated_at, created_at).
- [ ] UNIQUE constraint: `(universe_id, galaxy, system, position)`.
- [ ] Migration.

### 1.4 Game constants ve colonization mantigi

- [ ] `game/constants.py`: 
  - `TEMPERATURE_RANGES_BY_POSITION`: dict[int, tuple[int, int]] (CLAUDE.md tablosu).
  - `FIELDS_RANGES_BY_POSITION`: dict[int, tuple[int, int]].
  - `METAL_BONUS_BY_POSITION`, `CRYSTAL_BONUS_BY_POSITION`: dict[int, float].
  - `STARTING_RESOURCES`: {metal: 500, crystal: 500, deuterium: 0}.
- [ ] `game/colonization.py`:
  - `generate_planet_attributes(position: int, rng: random.Random) -> PlanetAttributes` 
    - rasgele temp_max secer, temp_min = temp_max - 40
    - rasgele fields_total secer
  - Pure function, DB free.
- [ ] Test: `tests/game/test_colonization.py`: her pozisyon icin 1000 kez calistir, deger araliklari dogrulanmali.

### 1.5 Universe service: random spawn

- [ ] `services/universe_service.py`:
  - `async def assign_starting_planet(db, user_id, universe_id) -> Planet`
  - Mantik:
    1. Bos slot bul (galaxy random 1-N, system random 1-M, position random 4-12 araliginda).
    2. Insert dene; UNIQUE constraint patlarsa tekrar dene (max 50 tries).
    3. Bulunamazsa 409 Conflict.
  - Race-safe.
- [ ] `api/auth.py`'deki register endpoint'ini, kayit sonrasi default universe'e auto-assign yapacak sekilde guncelle.

### 1.6 Planet read endpoint

- [ ] `schemas/planet.py`: `PlanetRead` (Pydantic).
- [ ] `api/planet.py`:
  - `GET /planets` -> kullanicinin tum gezegenleri.
  - `GET /planets/{id}` -> tek gezegen detayi (sadece sahibi).

### Faz 1 cikti

- Register + login + me akisi calisir.
- Register edilen kullaniciya otomatik bir gezegen atanir (universe icinde gercek bir slotta).
- `GET /planets` o kullanicinin gezegenlerini doner.
- Iki kullanici ayni slota dusemez (test ile kanitla).
- Tum endpoint'ler icin entegrasyon testi var.

---

## Faz 2: Maden + enerji uretimi (lazy update)

Hedef: gezegene baktigimda, son guncellemeden bu yana gecen sure icin maden uretimi hesaplanmis ve kaynaklarima eklenmis olmali. Enerji dengesi production_factor'a yansimali.

### 2.1 Building modeli

- [ ] `models/building.py`: Building (id, planet_id FK, building_type enum, level int default 0).
- [ ] BuildingType enum (CLAUDE.md tablosundaki tum bina turleri).
- [ ] UNIQUE: (planet_id, building_type).
- [ ] Migration.
- [ ] Planet yaratildiginda tum BuildingType'lar level=0 olarak insert edilir (universe_service icinde).

### 2.2 Formuller (saf fonksiyonlar)

- [ ] `game/formulas.py`:
  - `metal_mine_production(level, speed, plasma_tech=0, position_bonus=0.0) -> float`
  - `crystal_mine_production(level, speed, plasma_tech=0, position_bonus=0.0) -> float`
  - `deuterium_synthesizer_production(level, temp_max, speed, plasma_tech=0) -> float`
  - `base_passive_production(speed) -> tuple[float, float, float]` (metal, crystal, deut)
  - `solar_plant_output(level) -> int`
  - `solar_satellite_output(count, avg_temp) -> int`
  - `fusion_reactor_output(level, energy_tech) -> int`
  - `fusion_deut_consumption(level) -> int`
  - `mine_energy_consumption(building_type, level) -> int`
  - `building_cost(building_type, target_level) -> tuple[int, int, int]` (m, c, d)
  - `research_cost(tech_type, target_level) -> tuple[int, int, int]`
  - `build_time_seconds(metal, crystal, robotics_level, nanite_level, speed) -> int`
  - `research_time_seconds(metal, crystal, lab_level, speed) -> int`
- [ ] Test: her formul icin OGame wiki'den alinmis bilinen degerlerle (orn: Metal Mine L20, T=30 => X metal/h) dogrulanir. En az 30 birim test.

### 2.3 Production aggregator

- [ ] `game/production.py`:
  - `compute_planet_production(planet, buildings_dict, researches_dict, universe_speed) -> ProductionReport`
    - tum mine'lari, satellite'lari topla
    - production_factor hesapla
    - net hourly rates (metal_per_hour, crystal_per_hour, deut_per_hour) doner
    - energy_used, energy_produced, production_factor doner
  - Saf fonksiyon, sicaklik ve pozisyon bonuslarini hesaba katar.
- [ ] Test: combination case'leri (level 0 her sey, level 10 mines, vs.).

### 2.4 Resource service: lazy update

- [ ] `services/resource_service.py`:
  - `async def refresh_planet_resources(db, planet_id) -> Planet`
    - SELECT FOR UPDATE ile gezegen kilitlenir.
    - `delta_seconds = now - resources_last_updated_at`.
    - production_report hesaplanir.
    - kaynaklar += rate * delta_seconds / 3600
    - storage cap'i (su asamada sonsuz kabul et veya storage building'lerinden cikar; MVP'de cap sonsuz olabilir, sonra eklenecek).
    - `resources_last_updated_at = now`.
    - DB'ye yaz.
  - Saf I/O wrapper.
- [ ] Test: time freeze ile (freezegun veya monkeypatch ile `datetime.now`) 1 saat ileri sar, dogru miktarda kaynak eklendigini dogrula.

### 2.5 API entegrasyonu

- [ ] `GET /planets/{id}` endpoint'i once `refresh_planet_resources` cagirsin sonra donsun. Cevap olarak `current_resources`, `production_rates`, `energy_status` da donsun.
- [ ] `schemas/planet.py`'a `PlanetDetailRead` ekle.

### Faz 2 cikti

- 2 dakika bekledikten sonra `GET /planets/{id}` cagirinca kaynaklar artmis olmali.
- Bina seviyeleri elle DB'den arttirilirsa, uretim hizi artmis goruluyor.
- Enerji negatifse production_factor < 1 ve uretim azalmis goruluyor.
- Tum formul ve production hesaplari test ile dogrulanmis.

---

## Faz 3: Bina insaati (queue + scheduler)

Hedef: oyuncu API'den bina insa istegi gonderir, kaynaklar dusulur, queue'ya eklenir, sure dolunca bina seviyesi artar.

### 3.1 BuildQueue modeli

- [ ] `models/queue.py`: BuildQueue (id, planet_id, queue_type enum (BUILDING/RESEARCH/SHIP), item_key str, target_level int, started_at, finished_at, cancelled bool default false).
- [ ] Index: (planet_id, finished_at), (cancelled, finished_at).
- [ ] Migration.

### 3.2 Build service

- [ ] `services/build_service.py`:
  - `async def queue_building_upgrade(db, planet_id, user_id, building_type) -> BuildQueue`
    - planet owner check.
    - `refresh_planet_resources` cagir.
    - bu gezegen icin BUILDING tipinde aktif queue var mi? Varsa 409.
    - target_level = current + 1.
    - cost hesapla, yetiyor mu? Yetmiyorsa 400.
    - kaynaklar dusulur.
    - duration hesapla (robotics, nanite, speed ile).
    - finished_at = now + duration.
    - queue insert.
    - DB transaction.
  - `async def cancel_queue_item(db, queue_id, user_id) -> None`
    - sahip dogrulamasi.
    - kaynaklari geri ver.
    - cancelled = true.
- [ ] Test: cost yetersizken 400, aktif queue varken 409, basarili case'te kaynak dusumu ve queue olusumu.

### 3.3 Scheduler: queue completion

- [ ] `app/scheduler.py`: APScheduler instance.
- [ ] `process_completed_queue` job, her 5 saniyede bir:
  - `SELECT * FROM build_queue WHERE NOT cancelled AND finished_at <= now() FOR UPDATE SKIP LOCKED`.
  - Her biri icin:
    - BUILDING ise ilgili Building.level += 1.
    - planet.fields_used += 1 (storage/factory icin).
    - kaydi sil veya `applied = true` isaretle.
  - Async session ile yapilir.
- [ ] main.py'de `startup` event'inde scheduler.start(), `shutdown`'da scheduler.shutdown().
- [ ] Test: queue manuel olarak finished_at = past olarak insert et, scheduler tetiklenince building.level += 1 oldugunu dogrula.

### 3.4 API endpoints

- [ ] `api/building.py`:
  - `GET /planets/{id}/buildings` -> tum bina seviyeleri + bir sonraki seviyenin cost'u + build_time'i.
  - `POST /planets/{id}/buildings/{building_type}/upgrade` -> queue'ya ekler.
  - `GET /planets/{id}/queue` -> aktif queue itemlarini doner (her tip).
  - `DELETE /queue/{id}` -> cancel.

### Faz 3 cikti

- Metal Mine level 1'e cikarma istegi gonderilir, kaynak duser, queue gozukur.
- 1-2 dakika sonra (test icin kisa duration ile), scheduler tetiklenir, level 2 olur, uretim artar.
- Bir gezegende iki aktif building queue ayni anda olamaz.
- Cancel ettiginde kaynak iade edilir.

---

## Faz 4: Arastirma agaci

Hedef: oyuncu arastirma yapar, prereq kontrol edilir, queue'da bekler, tamamlandiginda tech seviyesi artar. Arastirma oyuncu bazli, gezegen bazli degil.

### 4.1 Research modeli

- [ ] `models/research.py`: Research (id, user_id FK, tech_type enum, level int default 0).
- [ ] TechType enum (CLAUDE.md listesindeki teknolojiler).
- [ ] UNIQUE (user_id, tech_type).
- [ ] User yaratildiginda tum tech'ler level=0 olarak insert.
- [ ] Migration.

### 4.2 Tech tree

- [ ] `game/tech_tree.py`:
  - `TECH_PREREQUISITES`: dict[TechType, list[Requirement]] (CLAUDE.md tablosu).
  - `BUILDING_PREREQUISITES`: opsiyonel (Research Lab vs).
  - `def check_research_prerequisites(tech_type, user_buildings_max_levels, user_tech_levels) -> tuple[bool, list[str]]`
    - "Research Lab >= 4" gibi req'leri tum gezegenlerdeki max research lab seviyesine bakarak kontrol eder.
- [ ] Test: prereq case'leri.

### 4.3 Research service

- [ ] `services/research_service.py`:
  - `async def queue_research(db, user_id, planet_id, tech_type) -> BuildQueue`
    - planet'in research lab'i (en azindan 1) olmali.
    - prereq check.
    - aktif RESEARCH tipinde queue var mi (kullanici bazli, herhangi bir gezegende)? Varsa 409.
    - cost dusur (planet'ten).
    - duration hesapla (research_lab level + speed).
    - queue insert (queue_type=RESEARCH).
- [ ] Scheduler'a RESEARCH tipi handling ekle: completion'da Research.level += 1.

### 4.4 API

- [ ] `api/research.py`:
  - `GET /researches` -> kullanicinin tum tech seviyeleri + sonraki seviyenin cost'u + research_time'i + prereq durumu.
  - `POST /researches/{tech_type}/upgrade?planet_id=X` -> queue.

### Faz 4 cikti

- Energy Tech 1 -> 2 arastirilir, cost duser, queue gozukur, sure sonunda level artar.
- Prereq saglanmadan arastirma denenince 400 + acik hata mesaji doner.
- Bir kullanicinin ayni anda iki aktif research queue'su olamaz.

---

## Faz 5: Galaksi gorunumu

Hedef: oyuncu galaksi/sistem koordinati girer, o sistemdeki tum gezegenlerin listesini (sahip, isim, pozisyon) gorur.

### 5.1 Galaksi API

- [ ] `api/galaxy.py`:
  - `GET /galaxy?universe_id=X&galaxy=Y&system=Z` 
    - O sistemdeki tum (universe_id, galaxy, system, position) icin gezegen var mi yok mu kontrolu.
    - Sahibi olanlarin sahip username'i, gezegen ismi, pozisyonu doner.
    - Bos slotlarda null.
    - 1-15 pozisyonlarin hepsini doner (rendering icin).
  - Auth gerekli. Kendi gezegenini gormeye yetkili herkes herhangi bir sistemi gorebilir (espionage Faz 7+).
- [ ] Performans: tek SQL select, IN clause veya range.

### 5.2 Colonize endpoint (kosul: Astrophysics + colony ship Faz 7+'da)

- [ ] MVP'de auto-spawn yeterli. Manuel kolonizasyon Faz 7'de.

### Faz 5 cikti

- TUI veya curl ile galaxy view alinabiliyor.
- 1-15 pozisyon dogru sirayla doner.

---

## Faz 6: TUI istemci

Hedef: Textual ile terminalden oyun oynanabilir hale gelir.

### 6.1 Client wrapper

- [ ] `tui/ogame_tui/client.py`: httpx.AsyncClient wrapper.
  - Login (token sakla in memory + opsiyonel olarak ~/.ogame/token).
  - Auth header otomatik ekleme.
  - WebSocket bag (opsiyonel Faz 6 sonu).

### 6.2 Login screen

- [ ] `screens/login.py`: username/password input, login butonu, register linki.

### 6.3 Overview screen

- [ ] `screens/overview.py`: 
  - Ust bant: kaynaklar (metal/crystal/deut + per-hour rate).
  - Gezegen secici (sol kenar).
  - Orta panel: gezegen ozet (sicaklik, pozisyon, alan kullanim, enerji dengesi).
  - Aktif queue paneli (sag).
  - Refresh tusu (R) + auto-refresh her 10 saniyede.

### 6.4 Buildings screen

- [ ] `screens/buildings.py`:
  - Tum bina seviyeleri tablosu.
  - Her satirda "Upgrade" butonu (cost + sure ile birlikte).
  - Yetersiz kaynak/aktif queue durumunda buton disabled.

### 6.5 Research screen

- [ ] `screens/research.py`:
  - Tum tech'ler, prereq durumu (yesil/kirmizi), upgrade.
  - Hangi gezegende arastirilacagi secimi (en yuksek lab'i olan default).

### 6.6 Galaxy screen

- [ ] `screens/galaxy.py`:
  - Galaxy/system koordinat input.
  - 1-15 slot tablosu.

### 6.7 Routing

- [ ] `app.py`: tab/menu ile screenler arasi gecis. Keyboard bindings (1-5).

### Faz 6 cikti

- Oyuncu terminalden register/login, gezegen ozeti, bina insa, arastirma ve galaksi gorunumu yapabilir.
- Backend hic dokunmadan ayni APIler ile calisir (basit ama dogru bir TUI).

---

## Faz 7+: Post-MVP (yol haritasi)

Bu fazlar simdilik scope disinda ama backend tasarimini bunlara hazir tutmak gerekiyor.

- **Faz 7: Shipyard ve filolar.** Ship modeli, ship construction (queue type SHIP), filo gonderme (transport/attack/colonize/expedition), filo hareket simulasyonu (departure_at, arrival_at), event scheduler.
- **Faz 8: Savas.** Combat simulator, weapons/shielding/armor tech, rapid fire, debris field, plunder algorithm.
- **Faz 9: Espionage + sensor phalanx.** Casus probe filo gorevi, raporlar.
- **Faz 10: Ittifak.** Alliance modeli, mesajlasma, ACS (allied combat).
- **Faz 11: Ay.** Moon chance, ay binalari, jump gate, phalanx.
- **Faz 12: Premium / officers.** Commander, admiral vs (oyun balansi icin opsiyonel).
- **Faz 13: Web frontend.** Aynı backend'e React/Next.js frontend.

---

## Test stratejisi

- Her game/* modulu icin >90% test coverage zorunlu.
- Her API endpoint icin happy path + en az 2 error case testi.
- Lazy update icin time freeze testi (1 hour, 24 hour, 1 week).
- Scheduler icin past-finished_at insert et + tick simule et testi.
- Concurrent build request icin entegrasyon testi (asyncio.gather ile).

## Performans hedefleri (MVP)

- `GET /planets/{id}` p99 < 200ms (lazy update dahil).
- `GET /galaxy` p99 < 100ms.
- Scheduler tick < 1 saniye 1000 queue itemiyla.

## Guvenlik

- JWT secret env'den; rotate edilebilir.
- Bcrypt cost factor 12+.
- Tum gezegen/queue endpoint'lerinde owner check.
- SQL injection riski yok (ORM only); raw SQL kullanma.
- Rate limit (Faz 7+).
