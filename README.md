# golden-book-rag

Upload a PDF book → parse/chunk/embed/store → semantic search + grounded Q&A
with citations. FastAPI + Postgres/pgvector + Gemini; Next.js frontend.

See `CLAUDE.md` for architecture, `docs/` for design notes.

## Running locally — two ways

### A) Dev mode (daily work: hot-reload, easy to debug)

Backend/frontend run on your machine; only Postgres runs in Docker.

```bash
make db-up          # start the pgvector Postgres container (docker-compose.yml)
make db-migrate     # apply Alembic migrations (run once after db-up)

make api-dev        # FastAPI on http://localhost:8000  (uvicorn --reload)
make web            # Next.js on http://localhost:3000  (next dev), in another shell
```

Stop the DB: `make db-down`. Other DB helpers: `make db-shell`, `make db-schema`,
`make db-reset` (⚠️ drops the volume — all data lost).

### B) Full containerized mode (pre-deploy rehearsal)

Everything (db + api + web) runs as Docker containers, the way it will in prod.
Use this to catch problems that only appear after packaging. Secrets come from
`.env` (`GEMINI_API_KEY`, `ADMIN_SECRET`).

```bash
make db-down        # stop the dev DB first, so ports/containers don't clash

make full-up        # build images + start db/api/web (detached), then show status
make full-ps        # status (db should be healthy, api/web Up)
make full-logs      # tail all logs (Ctrl-C to stop tailing)
make full-down      # stop everything (keeps the DB volume / data)
```

Smoke test once it's up:

```bash
curl -s http://localhost:8000/docs -o /dev/null -w "api: %{http_code}\n"
curl -s http://localhost:3000/api/books -w "\n"   # frontend -> backend proxy
```

> Quick reference: `docker-compose.yml` = dev (DB only, auto-loaded by `make`);
> `docker-compose.full.yml` = full stack (driven by the `make full-*` targets).
