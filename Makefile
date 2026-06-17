.PHONY: db-up db-down db-logs db-shell db-schema db-reset db-status db-migrate db-migrate-down api-dev test web full-up full-down full-logs full-ps \
	deploy deploy-api deploy-rollback kamal-config logs-web logs-api logs-proxy buildkit-stop

# Full containerized stack (db + api + web) — pre-deploy rehearsal.
FULL := docker compose -f docker-compose.full.yml

db-up:
	docker compose up -d
	@docker compose ps

db-down:
	docker compose down

db-logs:
	docker compose logs -f db

db-shell:
	docker compose exec db psql -U $${POSTGRES_USER:-bookrag} -d $${POSTGRES_DB:-bookrag}

# Print the live DB schema (migrations source of truth). Read-only; nothing written.
db-schema:
	docker compose exec -T db pg_dump -U $${POSTGRES_USER:-bookrag} -d $${POSTGRES_DB:-bookrag} --schema-only --no-owner --no-privileges

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

# Frontend dev server (Next.js). Run alongside `make api-dev` (uvicorn) in another shell.
web:
	cd frontend && yarn dev

# --- Full containerized stack (db + api + web) ---
# Stop the dev DB (`make db-down`) first so ports/containers don't clash.
# Builds images and starts everything detached. Secrets come from .env.
full-up:
	$(FULL) up --build -d
	@$(FULL) ps

full-down:
	$(FULL) down

full-logs:
	$(FULL) logs -f

full-ps:
	$(FULL) ps

# --- Kamal deploy (Hetzner). See docs/deploy-hetzner-kamal.md ---
# This Kamal version does NOT auto-load .kamal/secrets into the env, so SERVER_IP
# (read by deploy.yml via ERB) must be exported for every command. KAMAL bakes that
# in — use it instead of bare `kamal` so you never hit the empty-host config error.
KAMAL := SERVER_IP=$$(awk -F= '/^SERVER_IP=/{print $$2}' .kamal/secrets) kamal
API_IMAGE := ghcr.io/polunwu/golden-book-rag-api:latest

# Deploy a FRONTEND change: build web on this laptop, zero-downtime swap.
deploy:
	$(KAMAL) deploy

# Deploy a BACKEND change: rebuild+push the api image (amd64), then reboot the accessory.
# The api is a Kamal accessory, so it doesn't build via `kamal deploy` — hence the buildx.
deploy-api:
	docker buildx build --platform linux/amd64 -t $(API_IMAGE) --push .
	$(KAMAL) accessory reboot api

# Roll the web app back to the previous image version.
deploy-rollback:
	$(KAMAL) rollback

# Stop the buildx/BuildKit builder container after you're done deploying — frees ~170MB RAM.
# Kamal restarts it automatically on the next deploy/deploy-api build.
buildkit-stop:
	-docker buildx stop kamal-local-docker-container

# Render the deploy config locally (no server contact) — quickest drift/secret check.
kamal-config:
	$(KAMAL) config

logs-web:
	$(KAMAL) app logs -f

logs-api:
	$(KAMAL) accessory logs api -f

logs-proxy:
	$(KAMAL) proxy logs -f
