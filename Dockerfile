# Backend (FastAPI + uv). Builds an image that runs alembic migrations then uvicorn.

# uv's official image: Python 3.13 already inside + the `uv` binary. Saves us
# from installing Python/uv by hand. "slim" = small Debian base.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# --- Dependency layer (cached) ---
# Copy ONLY the lockfiles first. Docker caches each layer; as long as these two
# files don't change, the slow `uv sync` below is reused from cache even when you
# edit app code. --no-install-project: install deps but not our own package yet.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# --- App layer ---
# Now copy the source. (.dockerignore keeps junk like .venv/.git/uploads out.)
COPY . .
# Install our own package on top of the cached deps.
RUN uv sync --frozen --no-dev

# Railway/most platforms inject the port to listen on via $PORT.
ENV PORT=8000
EXPOSE 8000

# On every start: bring the DB schema up to date, then serve.
# --host 0.0.0.0 = listen on all interfaces (required inside a container).
# --timeout-keep-alive 75: keep idle connections open longer than the upstream
#   proxy's idle (Next/load balancers pool & reuse connections). The default 5s
#   lets the server drop a pooled connection the proxy still reuses -> ECONNRESET
#   "socket hang up" on the next (non-retried POST) request, e.g. /ask.
# No --reload in production.
CMD uv run alembic upgrade head && \
    uv run uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 75
