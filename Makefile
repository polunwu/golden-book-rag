.PHONY: db-up db-down db-logs db-shell db-reset db-status db-migrate db-migrate-down api-dev test

db-up:
	docker compose up -d
	@docker compose ps

db-down:
	docker compose down

db-logs:
	docker compose logs -f db

db-shell:
	docker compose exec db psql -U $${POSTGRES_USER:-bookrag} -d $${POSTGRES_DB:-bookrag}

db-status:
	docker compose ps

# Destroys the postgres volume — all data lost. Use when schema changes.
db-reset:
	docker compose down -v
	docker compose up -d
	@docker compose ps

db-migrate:
	uv run alembic upgrade head

db-migrate-down:
	uv run alembic downgrade -1

api-dev:
	uv run uvicorn api.main:app --reload --port 8000

# Needs `make db-up` + `make db-migrate`. No Gemini calls — embed_chunks is patched.
test:
	uv run pytest tests/ -v
