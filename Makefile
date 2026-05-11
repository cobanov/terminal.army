.PHONY: up down logs install sync migrate seed test lint typecheck dev run tui clean \
        server-up server-down server-logs server-build server-restart server-ps

# --- Ana backend (container, port 9931) ------------------------------------
server-up:
	docker compose up -d --build

server-down:
	docker compose down

server-restart:
	docker compose restart backend

server-build:
	docker compose build backend

server-logs:
	docker compose logs -f backend

server-ps:
	docker compose ps

# --- Sadece postgres (dev backend disardan kosacak) ------------------------
up:
	docker compose up -d postgres

down:
	docker compose down

logs:
	docker compose logs -f postgres

# --- Python env (uv) -------------------------------------------------------
install:
	uv venv --python 3.12
	uv pip install -e ".[dev,tui]"

sync:
	uv pip install -e ".[dev,tui]"

# --- Backend ---------------------------------------------------------------
migrate:
	uv run alembic upgrade head

seed:
	uv run python -m backend.scripts.seed_universe

dev:
	uv run uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

run: migrate seed dev

# --- TUI -------------------------------------------------------------------
tui:
	uv run python -m ogame_tui

# --- Quality ---------------------------------------------------------------
test:
	uv run pytest -q

lint:
	uv run ruff check backend tui
	uv run ruff format --check backend tui

typecheck:
	uv run mypy backend

# --- Cleanup ---------------------------------------------------------------
clean:
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
