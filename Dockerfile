# terminal.army backend — production container
# Build:
#   docker build -t terminal-army-backend .
# Run (standalone, SQLite):
#   docker run -p 9931:8000 -v $(pwd)/data:/data \
#       -e DATABASE_URL="sqlite+aiosqlite:////data/terminal-army.db" \
#       terminal-army-backend
# Run via docker compose (postgres + backend): docker compose up -d

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy

# uv binary
COPY --from=ghcr.io/astral-sh/uv:0.4.20 /uv /usr/local/bin/uv

WORKDIR /app

# 1. Bagimliliklari install et (cache friendly: source kopyalanmadan once)
COPY pyproject.toml uv.lock README.md /app/

# Stub package dirs so hatch can read metadata
RUN mkdir -p /app/backend /app/tui/terminal_army /app/alembic \
    && touch /app/backend/__init__.py /app/tui/terminal_army/__init__.py

# 2. Tum kaynak kodu kopyala
COPY backend /app/backend
COPY tui /app/tui
COPY alembic /app/alembic
COPY alembic.ini /app/

# 3. Install (system Python, no venv inside container)
RUN uv pip install --system --no-cache .

# Sirf backend portuna ihtiyac var, ama compose icinde overrided olabilir
EXPOSE 8000

# Health check (compose buna bakar)
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" || exit 1

# terminal-army-server reads DATABASE_URL from env, accepts --host/--port.
CMD ["terminal-army-server", "--host", "0.0.0.0", "--port", "8000"]
