# Deploy to a Hetzner VPS with Kamal

Self-contained beginner runbook. Destination: one small Hetzner VPS running Docker;
[**Kamal 2**](https://kamal-deploy.org) builds your images, ships them to the server,
and runs a built-in proxy (**kamal-proxy**) that owns ports 80/443 and auto-issues
HTTPS. Cloudflare holds DNS. Multiple projects can share the one box. Follow this top
to bottom — you don't need any other doc.

```
your laptop ──kamal deploy──► builds images, pushes to a registry, SSHes to the server,
                               boots kamal-proxy (TLS) + the app + accessories
internet ──443──► [kamal-proxy] ──► books.example.com → web:3000 → api:8000 → db
```

> The same destination can also be reached with hand-written docker-compose + a Caddy
> proxy instead of Kamal. A comparison is at the very end; you don't need it to deploy.

---

## How Kamal sees this app (read this first — it shapes everything below)

Kamal's sweet spot is a **single application image** (the Rails monolith it was born
from). This project is **three tiers**: a public Next.js `web`, a private FastAPI
`api`, and a `db` (pgvector). Kamal maps them like this:

| Our piece | Kamal role | Why |
|---|---|---|
| `web` (Next, :3000) | **the app** (primary) | The only thing the internet touches, so it gets the domain + auto-TLS from kamal-proxy. Kamal **builds it for you**. |
| `db` (pgvector) | **accessory** | Off-the-shelf image, persistent volume — exactly what accessories are for. |
| `api` (FastAPI, :8000) | **accessory** | ⚠️ The friction. `api` is **our own** image, but Kamal accessories don't build from a Dockerfile — only the *app* builds. So we build + push the `api` image by hand (Phase 7) and reference it as an accessory. |

> **The one wart, stated plainly:** because `api` is a second build, you run one extra
> manual `docker buildx … --push` for it on each backend change. That's the price of a
> single-app tool on a multi-tier app. A cleaner (heavier) two-Kamal-apps layout is
> sketched near the end.

Containers Kamal starts all share a Docker network called `kamal`, and they resolve
each other by the name `{service}-{accessory}`. With `service: golden-book-rag`, `web`
reaches the others at `golden-book-rag-db:5432` and `golden-book-rag-api:8000`. The
config relies on this — don't rename things without updating both places.

---

## Phase 0 — Before you start (have these ready)

- A domain you control, already added to **Cloudflare** (free plan is fine).
- Your `GEMINI_API_KEY`.
- A **GitHub account** (we use GitHub's container registry, GHCR).
- **Docker running on your laptop** — Kamal builds images locally. Install Docker
  Desktop (macOS/Windows) or Docker Engine (Linux) and confirm `docker ps` works.
- An SSH key on your laptop. Check `ls ~/.ssh/id_ed25519.pub`; if missing, create one:
  ```bash
  ssh-keygen -t ed25519        # press Enter through every prompt (no passphrase is fine)
  ```
- Decide this app's hostname, e.g. `books.example.com`. Below, replace
  `books.example.com`, `<SERVER_IP>`, and `<your-github-username>` everywhere.

---

## Phase 1 — Create the Hetzner server

1. hetzner.com/cloud → Console → New Project → **Add Server**.
2. Location: pick one near your users. Image: **Ubuntu 24.04**.
3. Type: **CAX11** (ARM/arm64, 2 vCPU / 4 GB, ~€3.8/mo). On an Apple-Silicon laptop
   (M1–M4, also arm64) this matches your CPU, so images build **natively — no slow
   emulation** (Phase 3c). All of this app's images support arm64.
   *(On an Intel/AMD laptop, pick **CX22** (x86/amd64) instead and use the amd64
   variants flagged in Phases 3c, 5, and 7.)*
4. **SSH keys**: add your `~/.ssh/id_ed25519.pub` — paste its full contents. This is
   how you log in; there is no password login.
5. Create the server and note its **public IPv4** — that's `<SERVER_IP>` everywhere below.

---

## Phase 2 — Secure the box + install Docker (one-time, as root)

Log in as root (your SSH key was installed at create time):

```bash
ssh root@<SERVER_IP>
```

**Create a non-root sudo user** (Kamal logs in as this user) and copy your SSH key to it:

```bash
adduser deploy                                              # set a password when asked
usermod -aG sudo deploy                                     # let it use sudo
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy   # copy your authorized key
```

**Install Docker now, while you're root** — this is simpler than letting Kamal install
it later (Kamal's auto-install would need passwordless sudo, an easy thing to get
wrong). The official convenience script handles everything:

```bash
curl -fsSL https://get.docker.com | sh     # installs Docker Engine
usermod -aG docker deploy                  # let `deploy` run docker without sudo
```

**Verify the new user works** — open a SECOND terminal and confirm before locking root
out:

```bash
ssh deploy@<SERVER_IP>      # must succeed
docker ps                   # must work without sudo (proves the docker group applied)
```

Back in the **root** terminal, harden SSH (disable root login + password auth):

```bash
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
```

Firewall — allow only SSH + web. (The `api`/`db` accessories never publish ports to
the host; they're reachable only on the internal `kamal` network, so they need no
firewall rule.)

```bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable
```

That's all the by-hand server work. Everything below runs from your **laptop**.

---

## Phase 3 — Install Kamal + log into the registry (on your laptop)

Kamal builds images **on your laptop** and pushes them to a container registry; the
server pulls from there. Set up two things.

### 3a. Install Kamal (a Ruby gem, needs Ruby 3.x)

> ⚠️ macOS ships an **old** system Ruby (2.6) that Kamal won't run on. Install a modern
> Ruby first.

```bash
# macOS, simplest path: Homebrew Ruby
brew install ruby
echo 'export PATH="/opt/homebrew/opt/ruby/bin:$PATH"' >> ~/.zshrc   # Apple Silicon path
exec zsh                                                            # reload your shell
ruby -v                                                             # expect 3.x

gem install kamal
kamal version                                                      # confirm it runs
```

(Alternative if you don't want to manage Ruby: run Kamal from its official Docker
image — see the "Docker-based install" on kamal-deploy.org. The gem is simpler to
start.)

### 3b. Container registry — GitHub's (GHCR)

1. GitHub → **Settings → Developer settings → Personal access tokens → Tokens
   (classic)** → **Generate new token (classic)** → tick the **`write:packages`**
   scope → generate → **copy the token** (starts with `ghp_…`). This is your "PAT";
   you can't view it again.
2. Log your laptop's Docker into GHCR (so `buildx --push` and Kamal can push):
   ```bash
   echo <YOUR_PAT> | docker login ghcr.io -u <your-github-username> --password-stdin
   # expect: "Login Succeeded"
   ```

Your images will live at `ghcr.io/<your-github-username>/golden-book-rag-web` and
`…-api`. They start out **private**; the server pulls them using the same token (Kamal
logs the server into the registry during `setup`).

### 3c. Architecture: match the image to the server's CPU

A Docker image is built for a specific CPU architecture and won't start on a different
one (you'd see `exec format error`). So the image you build must match the server:

- **Apple-Silicon laptop (M1–M4 = arm64) + CAX11 (arm64)** — the recommended pairing.
  Both are arm64, so you build **natively**: fast, no emulation. The config below pins
  `builder: arch: arm64` and Phase 7 uses `--platform linux/arm64`.
- **Intel/AMD laptop (amd64) + CX22 (amd64)** — same idea, native: use
  `builder: arch: amd64` and `--platform linux/amd64`.
- **Mismatched on purpose** (e.g. arm64 laptop building for an x86 server) — it still
  works via QEMU **emulation**, but the **first build is noticeably slower**. Avoid
  this by matching the server to your laptop, as above.

---

## Phase 4 — Point DNS at the server (Cloudflare)

Cloudflare → your domain → **DNS → Records → Add record**:

- Type **A**, Name `books` (becomes `books.example.com`), IPv4 address `<SERVER_IP>`.
- **Proxy status: DNS only (grey cloud).** kamal-proxy must reach Let's Encrypt
  directly to issue your certificate; Cloudflare's orange-cloud proxy gets in the way
  during issuance. You switch it to orange later (Phase 10).

Confirm it resolves to your server (DNS can take a minute):

```bash
dig +short books.example.com        # must print <SERVER_IP>
```

---

## Phase 5 — Configuration + secrets (in the repo, on your laptop)

From the repo root you can scaffold the two files Kamal expects, then overwrite them:

```bash
kamal init        # creates config/deploy.yml and .kamal/secrets stubs
```

### 5a. `config/deploy.yml` (committed — contains no secrets)

Replace every `<…>` placeholder:

```yaml
# config/deploy.yml — Kamal 2 deployment for golden-book-rag.
# `web` (Next) is the app the internet hits; `api` + `db` are accessories.
service: golden-book-rag

# PRIMARY app image = the Next.js frontend. No registry host here — Kamal prepends
# `registry.server` below, giving ghcr.io/<user>/golden-book-rag-web.
image: <your-github-username>/golden-book-rag-web

servers:
  web:
    - <%= ENV["SERVER_IP"] %>   # the Hetzner box — value read from .kamal/secrets (see below)

ssh:
  user: deploy             # the non-root user from Phase 2

# kamal-proxy owns 80/443 and issues a real Let's Encrypt cert for `host`.
proxy:
  host: books.example.com  # your domain (must match the DNS A record)
  app_port: 3000           # the port `web` (Next) listens on
  ssl: true                # automatic Let's Encrypt (needs 443 open + grey-cloud DNS)
  healthcheck:
    path: /                # Next serves / with 200; Kamal waits for this before swapping
  response_timeout: 60     # /ask calls Gemini and can be slow; don't cut it off early
  buffering:
    requests: true
    max_request_body: 110_000_000   # ~100MB PDF uploads (matches the app's MAX_UPLOAD_MB)

registry:
  server: ghcr.io
  username: <your-github-username>
  password:
    - KAMAL_REGISTRY_PASSWORD        # value comes from .kamal/secrets (your PAT)

builder:
  arch: arm64                        # native build: M-series Mac (arm64) -> CAX11 (arm64). Use amd64 for an x86 server.
  # The "app" is the Next.js frontend, which lives in frontend/ — NOT the repo root.
  # Kamal's defaults (context ".", dockerfile "Dockerfile") would build the repo-root
  # Dockerfile, which is the *API* image: the web container then runs alembic, has no
  # DATABASE_URL, and fails its healthcheck. Point both at frontend/ explicitly.
  context: ./frontend
  dockerfile: frontend/Dockerfile
  args:
    # Next bakes the /api/* rewrite target at BUILD time -> point it at the api accessory.
    BACKEND_ORIGIN: http://golden-book-rag-api:8000

env:
  clear:
    NODE_ENV: production             # web needs no secrets; it only proxies to api

# --- accessories: db (off-the-shelf) + api (our own image) ---
accessories:
  db:
    image: pgvector/pgvector:pg17
    host: <%= ENV["SERVER_IP"] %>
    env:
      clear:
        POSTGRES_USER: bookrag
        POSTGRES_DB: bookrag
      secret:
        - POSTGRES_PASSWORD          # initializes the DB superuser password
    directories:
      - data:/var/lib/postgresql/data   # persistent DB storage on the host

  api:
    # Accessories don't build — you build + push this image yourself (Phase 7).
    image: ghcr.io/<your-github-username>/golden-book-rag-api:latest
    host: <%= ENV["SERVER_IP"] %>
    env:
      clear:
        UPLOAD_DIR: /data/uploads
      secret:
        - DATABASE_URL               # full connection string (built in .kamal/secrets)
        - GEMINI_API_KEY
        - ADMIN_SECRET
    directories:
      - uploads:/data/uploads        # uploaded PDFs persist on the host
```

Why `DATABASE_URL` is a **secret**, not a `clear:` value with `${POSTGRES_PASSWORD}`
inside it: Kamal does **not** interpolate secrets into clear values, so we assemble the
whole connection string (password included) in `.kamal/secrets`, where it stays out of
git.

Why the three `host:` lines read `<%= ENV["SERVER_IP"] %>` instead of a literal IP:
`config/deploy.yml` is **committed** and ERB-evaluated, while `.kamal/secrets` is loaded
into the environment via dotenv. Putting `SERVER_IP` there keeps the server's address
out of the public repo. Confirm it resolves before deploying with `kamal config` (run
locally — it renders the config without touching the server). If `kamal config` errors
with an empty host, `SERVER_IP` isn't set in `.kamal/secrets`.

### 5b. `.kamal/secrets` (NOT committed — holds real values)

First make sure it can never be committed:

```bash
echo ".kamal/secrets" >> .gitignore
```

Then put the real values in `.kamal/secrets`. Generate the random ones with
`openssl rand -hex 32`. **The password inside `DATABASE_URL` must be the exact same
string as `POSTGRES_PASSWORD`** (the db is created with that password; the api connects
with it):

```bash
# .kamal/secrets — real values, gitignored. Do not share.
SERVER_IP=your_hetzner_ipv4        # read by deploy.yml via ERB; keeps the IP out of git
KAMAL_REGISTRY_PASSWORD=ghp_your_github_PAT_here
POSTGRES_PASSWORD=paste_output_of_openssl_rand_hex_32
GEMINI_API_KEY=your_gemini_api_key
ADMIN_SECRET=paste_another_openssl_rand_hex_32
DATABASE_URL=postgresql://bookrag:THE_SAME_POSTGRES_PASSWORD@golden-book-rag-db:5432/bookrag
```

> Host in `DATABASE_URL` is `golden-book-rag-db` — the `{service}-{accessory}` name the
> api resolves on the `kamal` network, **not** `localhost`.

---

## Phase 6 — Confirm Kamal can reach the server

This connects over SSH and checks prerequisites. Because you already installed Docker
in Phase 2, it finds Docker present and finishes quickly (it won't need sudo):

```bash
kamal server bootstrap
```

If this errors on SSH, fix that first (can you `ssh deploy@<SERVER_IP>` by hand?) —
nothing below will work until Kamal can log in.

---

## Phase 7 — Build + push the `api` image (the manual accessory step)

Kamal won't build accessories, so you build the api image yourself and push it to GHCR.
Run this from the repo root (the api Dockerfile is `./Dockerfile`); you do it again on
every backend change:

```bash
docker buildx build --platform linux/arm64 \
  -t ghcr.io/<your-github-username>/golden-book-rag-api:latest \
  --push .
```

- `--platform linux/arm64` — match the server's CPU (CAX11). On an x86 server use
  `linux/amd64` instead. This must agree with `builder: arch:` in `deploy.yml`.
- `--push` — upload straight to GHCR after building.
- The api image's `CMD` runs `alembic upgrade head` on start, so the DB schema is
  created automatically — **once the `db` accessory is already up** (handled by the
  boot order in Phase 8).

Do this **before** the first `kamal setup`, or the api accessory will have no image to
pull.

---

## Phase 8 — First deploy

`kamal setup` does the whole first run: logs the server into the registry, boots the
accessories, builds + pushes the **web** image from your laptop, boots kamal-proxy, and
starts `web` behind it with TLS.

To avoid the api starting before the database is ready (its `alembic upgrade head`
would fail against a not-yet-running db), boot the db first, then run setup:

```bash
kamal accessory boot db          # start Postgres first
kamal accessory boot api         # start the FastAPI backend (runs migrations now)
kamal setup                      # build+push web, boot proxy, go live with TLS
```

If the api logs show it died because the db wasn't ready yet, just restart it once the
db is up:

```bash
kamal accessory reboot api
```

---

## Phase 9 — Verify it's live

```bash
curl -I https://books.example.com        # expect HTTP/2 200 and a valid certificate
```

Watch the moving parts (each `-f`/`--follow` streams live; Ctrl-C to stop):

```bash
kamal proxy logs                 # TLS cert issuance + routing
kamal app logs -f                # the web (Next) app
kamal accessory logs api -f      # the FastAPI backend, incl. the alembic migration line
kamal accessory logs db          # Postgres
```

Then open `https://books.example.com` in a browser, upload a PDF, and ask a question.
If the cert isn't ready, give kamal-proxy a minute and re-check `kamal proxy logs`
(cert issuance fails if the DNS record is still orange-cloud — see Phase 4).

---

## Phase 10 — (Optional) Turn on Cloudflare proxy

Once it works end-to-end with grey cloud, you can enable Cloudflare's proxy (orange
cloud) for caching / DDoS protection / hiding your origin IP:

1. Cloudflare → **SSL/TLS → Overview** → set encryption mode to **Full (strict)** (your
   origin has a real Let's Encrypt cert, so strict is correct).
2. Edit the `books` DNS record → flip Proxy status to **Proxied (orange)**.

Caveat: on the **free** Cloudflare plan, proxied request bodies are capped at **100 MB**
— the same as the app's `MAX_UPLOAD_MB`, so very large books sit right at the edge. If
that bites, keep the record grey (DNS only).

---

## Day-2 operations

> ⚠️ Every bare `kamal …` below needs `SERVER_IP` exported first (this Kamal version
> doesn't auto-load `.kamal/secrets`): `export SERVER_IP=$(awk -F= '/^SERVER_IP=/{print $2}' .kamal/secrets)`.
> The **`make` targets** in the right column bake that in — prefer them.

| Task | Command(s) |
|---|---|
| Deploy a **frontend** change | `make deploy` (= `kamal deploy`; builds web on your laptop, **zero-downtime** swap) |
| Deploy a **backend** change | `make deploy-api` (= Phase 7 `docker buildx … --push` **then** `kamal accessory reboot api`) |
| Re-deploy web only (skip registry login/bootstrap) | `kamal redeploy` |
| Tail logs | `make logs-web` · `make logs-api` · `make logs-proxy` |
| Render config / drift check | `make kamal-config` |
| Roll the web app back | `make deploy-rollback` (= `kamal rollback`) |
| Open a DB shell | `kamal accessory exec db -- psql -U bookrag -d bookrag` |
| Run any one-off in the db | `kamal accessory exec db -- pg_isready -U bookrag` |
| Roll back the web app | `kamal rollback` (reverts to the previous image version) |

**Zero-downtime**: `kamal deploy` starts the new `web` container, waits for the
`proxy.healthcheck.path` to return 200, and only then swaps traffic — no gap. (This
applies to the *app* / `web`; the api is rebooted in place, so a backend deploy has a
brief blip.)

**Backups (do this!).** Your data is in two host directories created by the accessories'
`directories:` mounts. Two things to capture:

```bash
# 1) Logical DB dump (run from your laptop; streams over SSH):
kamal accessory exec db -- pg_dump -U bookrag bookrag | gzip > ~/backup-$(date +%F).sql.gz

# 2) Uploaded PDFs — tar the host directory on the server (run on the server):
ssh deploy@<SERVER_IP> 'tar czf - golden-book-rag-api/uploads' > ~/uploads-$(date +%F).tar.gz
```

kamal-proxy re-issues TLS certs automatically, so they're not critical to back up.

---

## Troubleshooting (the failures you're most likely to hit)

- **Cert never issues / `curl` shows a TLS error.** The DNS record is probably still
  orange-cloud, or port 443 isn't open. Set the record to **grey cloud** (Phase 4),
  confirm `ufw status` lists 443, then `kamal proxy logs`.
- **api container keeps restarting.** Almost always the db wasn't ready when it ran
  migrations, or `DATABASE_URL` is wrong. Check `kamal accessory logs api`; confirm the
  password in `DATABASE_URL` matches `POSTGRES_PASSWORD` and the host is
  `golden-book-rag-db`. Fix `.kamal/secrets`, then `kamal accessory reboot api`.
- **`exec format error` in the api or web logs.** The image was built for the wrong CPU.
  Make the build match the server: for CAX11, `--platform linux/arm64` (api) and
  `builder: arch: arm64` (web); for an x86 server, the `amd64` variants.
- **Uploading a larger PDF returns 500, but `kamal accessory logs api` shows no
  `POST /books/upload` at all.** The 500 comes from the **web (Next.js) proxy**, not the
  backend — `kamal app logs` shows `Request body exceeded 10MB for /api/books/upload`
  then `Failed to proxy … socket hang up (ECONNRESET)`. Next buffers the proxied request
  body with a **10MB default cap** and truncates past it, so the rewrite to the api dies
  mid-stream. Fix in `frontend/next.config.ts`: set `experimental.proxyClientMaxBodySize`
  (e.g. `"110mb"`, matching `proxy.buffering.max_request_body` and the app's
  `MAX_UPLOAD_MB`), then `kamal deploy`. Debugging rule of thumb: walk the request path
  **proxy → web → api**; the layer where the status code first goes bad owns the failure.
- **`kamal setup`/`deploy` fails: the web container runs alembic / logs `DATABASE_URL
  missing` / "target failed to become healthy".** The app image was built from the
  repo-root Dockerfile (the API), not the frontend. Confirm `deploy.yml`'s `builder` has
  `context: ./frontend` and `dockerfile: frontend/Dockerfile`, then `kamal deploy`.
- **`kamal config` errors `servers/web/0: should be a string or a hash`.** ERB read an
  empty `SERVER_IP` — this Kamal version does **not** auto-load `.kamal/secrets` into the
  environment for `ENV[...]` interpolation. Export it for each invocation, e.g.
  `export SERVER_IP=$(awk -F= '/^SERVER_IP=/{print $2}' .kamal/secrets)` before any
  `kamal` command (or `set -a; source .kamal/secrets; set +a`).
- **Registry push/pull denied.** Re-run `docker login ghcr.io` (Phase 3b) and confirm
  `KAMAL_REGISTRY_PASSWORD` in `.kamal/secrets` is your PAT with `write:packages`.
- **`kamal` commands hang or refuse SSH.** Test `ssh deploy@<SERVER_IP>` by hand; the
  `ssh.user` in `deploy.yml` must be `deploy`, and that user must be in the `docker`
  group (Phase 2).

---

## Adding another project later (multi-project on one box)

kamal-proxy routes by `host`, so each project is independent:

1. In the other repo, give it its own `config/deploy.yml` with a different `service:`
   and `proxy.host:` (e.g. `notes.example.com`), pointed at the **same** `<SERVER_IP>`.
2. Add its Cloudflare A record → the server IP (grey cloud first, as in Phase 4).
3. `kamal setup` from that repo. kamal-proxy picks up the new host and issues its cert.

No edits to the first project, no port conflicts — kamal-proxy multiplexes 80/443
across every Kamal app on the host.

---

## The cleaner-but-heavier alternative: two Kamal apps

The accessory wart (Phase 7) exists because we forced `api` into an accessory. The
fully-idiomatic Kamal layout is **two separate Kamal projects**, each building its own
image:

- `golden-book-rag-web` — app, `proxy.host: books.example.com`, builds `frontend/`.
- `golden-book-rag-api` — app, **no `proxy`** (private) *or* `proxy.host:
  api.example.com`, builds `./` (the FastAPI Dockerfile); `db` is its accessory.

Both `kamal deploy` build + push their own image — no manual `buildx`. The cost: two
config files, two deploy commands, and you must put both on a shared Docker network so
`web` can resolve `api` (Kamal app→app DNS needs a `network-alias`, which is fiddly —
see kamal-deploy.org). For a first deploy on one box, the single-config + accessory
layout above is the gentler start; graduate to two apps if the manual api build annoys
you.

---

## How this compares to a docker-compose + Caddy setup

The same live site can be reached with hand-written docker-compose + a shared Caddy
proxy (building on the server, no registry) instead of Kamal. The real differences:

| | compose + Caddy | Kamal |
|---|---|---|
| Where images build | **on the server** (CX22 can strain) | **on your laptop**, pushed to a registry |
| Deploy downtime | a few seconds during `up --build` | **none** for the app (health-checked swap) |
| Backend change | one `docker compose up --build` | `buildx --push` + `accessory reboot` (extra step) |
| Rollback | re-checkout + rebuild by hand | `kamal rollback` |
| Apple-Silicon laptop | irrelevant (builds on server) | match server arch (CAX11 arm64 = native, fast) |
| Transparency | every moving part is visible | more is abstracted away |

**To actually choose, run each once and measure five things on *your* setup:**

1. **Time-to-first-deploy** — blank server → live HTTPS. Note which felt longer *and*
   which felt more understandable.
2. **Redeploy + downtime** — change one line of frontend copy, redeploy, and `curl` the
   site in a loop during the swap; count seconds of non-200.
3. **Backend-change friction** — change a Python file and ship it; feel Kamal's extra
   `buildx --push` step and decide if it bugs you.
4. **"What broke?" recoverability** — break an env var on purpose, fix it; see whose
   logs got you to the cause faster.
5. **Rollback** — ship a good deploy, then a bad one, then revert; time both.

**Heuristic:** pick **compose/Caddy** if you value seeing every moving part, are fine
building on the server, and ship the stack together (it's the better learning
substrate). Pick **Kamal** if zero-downtime app deploys and one-command `rollback`
matter, you're happy building on your laptop + a registry, and you'll run several apps
on the box long-term. For *this* three-tier app, Kamal carries the api-build wart —
many first-timers get live with compose, then try Kamal as a deliberate exercise once
the Docker concepts have clicked.

---

Sources: [kamal-deploy.org/docs](https://kamal-deploy.org/docs/configuration/overview/) ·
[proxy](https://kamal-deploy.org/docs/configuration/proxy/) ·
[accessories](https://kamal-deploy.org/docs/configuration/accessories/) ·
[environment variables](https://kamal-deploy.org/docs/configuration/environment-variables/) ·
[commands](https://kamal-deploy.org/docs/commands/view-all-commands/).
