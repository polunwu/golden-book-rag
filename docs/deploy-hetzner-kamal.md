# Deploy to a Hetzner VPS with Kamal

Self-contained beginner runbook. Destination: one small Hetzner VPS running Docker;
[**Kamal 2**](https://kamal-deploy.org) builds your images, ships them to the server,
and runs a built-in proxy (**kamal-proxy**) that owns 80/443 and auto-issues HTTPS.
Cloudflare holds DNS. Multiple projects can share the one box. You can follow this
top to bottom without reading any other doc.

```
your laptop ──kamal deploy──► builds images, pushes to a registry, SSHes to the server,
                               boots kamal-proxy (TLS) + the app + accessories
internet ──443──► [kamal-proxy] ──► books.example.com → web:3000 → api:8000 → db
```

> The same destination can also be reached with hand-written docker-compose + a
> Caddy proxy instead of Kamal. A comparison of the two approaches is at the very end;
> you don't need anything but this doc to deploy.

---

## How Kamal sees this app (read this first — it shapes everything below)

Kamal's sweet spot is a **single application image** (the Rails monolith it was born
from). This project is **three tiers**: a public Next.js `web`, a private FastAPI
`api`, and a `db` (pgvector). Kamal maps them like this:

| Our piece | Kamal role | Why |
|---|---|---|
| `web` (Next, :3000) | **the app** (primary) | It's the only thing the internet touches, so it gets the domain + auto-TLS from kamal-proxy. |
| `db` (pgvector) | **accessory** | Off-the-shelf image, persistent volume — exactly what accessories are for. |
| `api` (FastAPI, :8000) | **accessory** | ⚠️ The friction. `api` is **our own** image, but Kamal accessories don't build from a Dockerfile — only the *app* builds. So we build + push the `api` image by hand and reference it as an accessory. |

> **The one wart, stated plainly:** because `api` is a second build, you run one
> extra manual `docker buildx … --push` for it on each backend change (Phase 7).
> This is the price of using a single-app tool on a multi-tier app. A cleaner
> (but heavier) two-Kamal-apps layout is sketched near the end.

Containers on Kamal's network resolve each other by the name `{service}-{accessory}`.
With `service: golden-book-rag`, `web` reaches the others at `golden-book-rag-db:5432`
and `golden-book-rag-api:8000`. We rely on this in the config.

---

## Phase 0 — Before you start (have these ready)

- A domain you control, added to **Cloudflare** (free plan is fine).
- Your `GEMINI_API_KEY`.
- A **GitHub account** (we use GitHub's container registry, GHCR).
- An SSH key on your laptop. Check: `ls ~/.ssh/id_ed25519.pub`. If missing:
  `ssh-keygen -t ed25519` (press Enter through the prompts).
- Decide the hostname for this app, e.g. `books.example.com`.

---

## Phase 1 — Create the Hetzner server

1. hetzner.com/cloud → Console → New Project → **Add Server**.
2. Location: pick near your users. Image: **Ubuntu 24.04**.
3. Type: **CX22** (x86, 2 vCPU / 4 GB, ~€4/mo) is a safe default. (See the
   architecture note in Phase 3 — x86 avoids a build gotcha for Apple-Silicon laptops.)
4. **SSH keys**: add your `~/.ssh/id_ed25519.pub` (paste its contents). This is how
   you log in — no password.
5. Create. Note the server's **public IPv4** (you'll use it as `<SERVER_IP>` below).

---

## Phase 2 — First login + secure the box

```bash
ssh root@<SERVER_IP>          # first login as root via your SSH key
```

Create a non-root sudo user (Kamal will log in as this user) and copy your key to it:

```bash
adduser deploy               # set a password when prompted
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy   # copy your SSH key
```

Open a SECOND terminal and confirm the new user works **before** locking root out:

```bash
ssh deploy@<SERVER_IP>       # must succeed
```

Back as root, disable root SSH + password auth:

```bash
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
```

Firewall — only SSH + web:

```bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable
```

That's all you do on the server by hand. **You do NOT install Docker** — Kamal
installs it for you in Phase 6. From here, work from your **laptop**.

---

## Phase 3 — Install Kamal + log into a registry (on your laptop)

Kamal builds images **on your laptop** and pushes them to a container registry; the
server pulls from there. So set up two things.

### 3a. Install Kamal (a Ruby gem)

```bash
gem install kamal          # needs Ruby 3.x — check with `ruby -v`. macOS has one built in.
kamal version              # confirm it runs
```

If your system Ruby is too old, install `rbenv` + a recent Ruby first, or run Kamal
via its Docker image (see kamal-deploy.org). The gem is the simplest start.

### 3b. A container registry — GitHub's (GHCR)

1. GitHub → **Settings → Developer settings → Personal access tokens → Tokens
   (classic)** → **Generate new token** with the **`write:packages`** scope. Copy it
   (this is your "PAT").
2. Log Docker into GHCR from your laptop:
   ```bash
   echo <YOUR_PAT> | docker login ghcr.io -u <your-github-username> --password-stdin
   ```

Your images will live at `ghcr.io/<your-github-username>/golden-book-rag-web` and
`…-api`.

### 3c. ⚠️ Architecture: Apple Silicon laptop → x86 server

If your laptop is an **M-series Mac (arm64)** and the server is **CX22 (amd64/x86)**,
the image must be built **for amd64** or it won't run on the server. The config below
pins `builder: arch: amd64` to handle this. On an Intel Mac / amd64 laptop you can
drop that line.

---

## Phase 4 — Point DNS at the server (Cloudflare)

In Cloudflare → your domain → **DNS → Records**:

- Add an **A** record: name `books` (→ `books.example.com`), value `<SERVER_IP>`.
- **Proxy status: DNS only (grey cloud)** for now. kamal-proxy needs to reach Let's
  Encrypt directly to issue your HTTPS certificate; Cloudflare's orange-cloud proxy
  would get in the way during issuance. (You switch it to orange later — Phase 9.)

Verify it resolves (wait a minute for DNS):

```bash
dig +short books.example.com        # should print <SERVER_IP>
```

---

## Phase 5 — Configuration files (in the repo, on your laptop)

Kamal reads `config/deploy.yml` from the repo root. Create it, replacing every
`<…>` placeholder:

```yaml
# config/deploy.yml — Kamal 2 deployment for golden-book-rag.
# `web` (Next) is the app the internet hits; `api` + `db` are accessories.
service: golden-book-rag

# The PRIMARY app image = the Next.js frontend.
image: <your-github-username>/golden-book-rag-web

servers:
  web:
    - <SERVER_IP>          # the Hetzner box

ssh:
  user: deploy             # the non-root user you made in Phase 2

# kamal-proxy owns 80/443 and issues a real Let's Encrypt cert for ${host}.
proxy:
  host: books.example.com  # your domain
  app_port: 3000           # Next listens here
  ssl: true                # automatic Let's Encrypt (needs 443 open + grey-cloud DNS)
  healthcheck:
    path: /                # Next serves / ; adjust if you add a /up route
  response_timeout: 60
  buffering:
    requests: true
    max_request_body: 110_000_000   # ~100MB PDF uploads (matches MAX_UPLOAD_MB)

registry:
  server: ghcr.io
  username: <your-github-username>
  password:
    - KAMAL_REGISTRY_PASSWORD        # read from .kamal/secrets (your PAT)

builder:
  arch: amd64                        # build x86 images from an arm64 Mac (Phase 3c)
  args:
    # Next bakes the /api/* rewrite target at BUILD time -> point it at the api accessory.
    BACKEND_ORIGIN: http://golden-book-rag-api:8000

# The web container needs no secrets of its own (it only proxies to api).
env:
  clear:
    NODE_ENV: production

# --- accessories: api (our build) + db (off-the-shelf) ---
accessories:
  db:
    image: pgvector/pgvector:pg17
    host: <SERVER_IP>
    env:
      clear:
        POSTGRES_USER: bookrag
        POSTGRES_DB: bookrag
      secret:
        - POSTGRES_PASSWORD
    directories:
      - data:/var/lib/postgresql/data   # persistent DB volume

  api:
    # Accessories don't build — we build+push this image ourselves (Phase 7).
    image: ghcr.io/<your-github-username>/golden-book-rag-api:latest
    host: <SERVER_IP>
    env:
      clear:
        UPLOAD_DIR: /data/uploads
        # host = {service}-{accessory} on the kamal network:
        DATABASE_URL: postgresql://bookrag:${POSTGRES_PASSWORD}@golden-book-rag-db:5432/bookrag
      secret:
        - POSTGRES_PASSWORD
        - GEMINI_API_KEY
        - ADMIN_SECRET
    directories:
      - uploads:/data/uploads           # uploaded PDFs survive restarts
```

> `DATABASE_URL` references `${POSTGRES_PASSWORD}` — Kamal interpolates secrets into
> clear env at deploy time, so the password itself lives only in `.kamal/secrets`.

Now the secrets. Create `.kamal/secrets` (it maps secret **names** to values pulled
from your shell environment):

```bash
# .kamal/secrets
KAMAL_REGISTRY_PASSWORD=$KAMAL_REGISTRY_PASSWORD
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
GEMINI_API_KEY=$GEMINI_API_KEY
ADMIN_SECRET=$ADMIN_SECRET
```

**Never commit `.kamal/secrets`.** Add it to `.gitignore`:

```bash
echo ".kamal/secrets" >> .gitignore
```

Then export the real values in the shell you'll deploy from (generate the random ones
with `openssl rand -hex 32`):

```bash
export KAMAL_REGISTRY_PASSWORD=<your-github-PAT>
export POSTGRES_PASSWORD=<openssl rand -hex 32>
export GEMINI_API_KEY=<your key>
export ADMIN_SECRET=<openssl rand -hex 32>
```

---

## Phase 6 — Let Kamal install Docker on the server

Kamal can prepare a bare Ubuntu box (install Docker, set up its network) for you:

```bash
kamal server bootstrap
```

(`kamal setup` in Phase 8 also does this automatically, but running it once now makes
failures easier to read.)

---

## Phase 7 — Build + push the `api` image (the manual accessory step)

Because `api` is an accessory, Kamal won't build it — you do, once per backend change:

```bash
# from the repo root (the api Dockerfile is ./Dockerfile)
docker buildx build --platform linux/amd64 \
  -t ghcr.io/<your-github-username>/golden-book-rag-api:latest \
  --push .
```

The api image's `CMD` already runs `alembic upgrade head` on start, so the DB schema
is created automatically once the `db` accessory is up.

---

## Phase 8 — First deploy

```bash
kamal setup
```

`kamal setup` does, in order: ensure Docker on the server, log into the registry,
build + push the **web** image from your laptop, boot the `db` and `api` accessories,
boot kamal-proxy, and start `web` behind it with TLS. Watch the output for errors.

If accessories didn't come up, boot them explicitly:

```bash
kamal accessory boot db
kamal accessory boot api
```

---

## Phase 9 — Verify

```bash
curl -I https://books.example.com        # expect HTTP/2 200, valid cert
kamal proxy logs                          # cert issuance / routing
kamal app logs -f                         # the web app
kamal accessory logs api -f               # the FastAPI backend (incl. alembic)
```

Open `https://books.example.com`, upload a PDF, ask a question. If the cert isn't
ready, give kamal-proxy a minute and re-check `kamal proxy logs`.

---

## Phase 10 — (Optional) Turn on Cloudflare proxy

Once it works end-to-end with grey cloud, you can enable Cloudflare's proxy (orange
cloud) for caching / DDoS protection / hiding your IP:

1. Cloudflare → **SSL/TLS** → set mode to **Full (strict)** (your origin has a real
   Let's Encrypt cert, so strict is correct).
2. Flip the DNS record to **Proxied (orange)**.

Caveat: on the **free** Cloudflare plan, proxied uploads are capped at **100 MB** —
the same as this app's `MAX_UPLOAD_MB`, so very large books are borderline. If that
bites, keep the record grey (DNS only).

---

## Day-2 operations

| Task | Command |
|---|---|
| Deploy a **frontend** change | `kamal deploy` (builds web on your laptop, **zero-downtime** swap) |
| Deploy a **backend** change | `docker buildx … --push` (Phase 7) **then** `kamal accessory reboot api` |
| Tail logs | `kamal app logs -f` / `kamal accessory logs api -f` / `kamal proxy logs` |
| DB shell | `kamal accessory exec db -- psql -U bookrag -d bookrag` |
| Roll back the web app | `kamal rollback` (Kamal keeps prior image versions) |

- **Zero-downtime**: `kamal deploy` health-checks the new `web` container and swaps
  traffic only when it's healthy — no restart gap.
- **Backups (do this!)**: the data lives in two server-side Kamal volumes —
  `golden-book-rag-db` (Postgres) and the api's `uploads`. Schedule a dump:
  ```bash
  kamal accessory exec db -- pg_dump -U bookrag bookrag | gzip > ~/backup-$(date +%F).sql.gz
  ```
  kamal-proxy re-issues certs automatically, but back up its volume too if you want
  zero-friction recovery.

---

## Adding another project later (multi-project on one box)

kamal-proxy routes by `host`, so each project is independent:

1. In the other repo, give it its own `config/deploy.yml` with a different `service:`
   and `proxy.host:` (e.g. `notes.example.com`), pointed at the **same** `<SERVER_IP>`.
2. Add its Cloudflare A record → the server IP (grey cloud first, as in Phase 4).
3. `kamal setup` from that repo. kamal-proxy adds the new host and issues its cert.

No edits to the first project, no port conflicts — kamal-proxy multiplexes 80/443
across every Kamal app on the host.

---

## The cleaner-but-heavier alternative: two Kamal apps

The accessory wart (Phase 7) exists because we forced `api` into an accessory. The
fully-idiomatic Kamal layout is **two separate Kamal projects**, each building its own
image:

- `golden-book-rag-web` — app, `proxy.host: books.example.com`, builds `frontend/`.
- `golden-book-rag-api` — app, **no `proxy`** (private) *or* `proxy.host:
  api.example.com`, builds `./` (the FastAPI Dockerfile). `db` is its accessory.

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
| Deploy downtime | a few seconds during `up --build` | **none** (health-checked swap) |
| Backend change | one `docker compose up --build` | `buildx --push` + `accessory reboot` (extra step) |
| Rollback | re-checkout + rebuild by hand | `kamal rollback` |
| Apple-Silicon laptop | irrelevant (builds on server) | must pin `arch: amd64` |
| Transparency | every moving part is visible | more is abstracted away |

**To actually choose, run each once and measure five things on *your* setup:**

1. **Time-to-first-deploy** — blank server → live HTTPS. Note which felt longer *and*
   which felt more understandable.
2. **Redeploy + downtime** — change one line of frontend copy, redeploy, and `curl`
   the site in a loop during the swap; count seconds of non-200.
3. **Backend-change friction** — change a Python file and ship it; feel Kamal's extra
   `buildx --push` step and decide if it bugs you.
4. **"What broke?" recoverability** — break an env var on purpose, fix it; see whose
   logs got you to the cause faster.
5. **Rollback** — ship a good deploy, then a bad one, then revert; time both.

**Heuristic:** pick **compose/Caddy** if you value seeing every moving part, are fine
building on the server, and ship the stack together (it's the better learning
substrate). Pick **Kamal** if zero-downtime deploys and one-command `rollback` matter,
you're happy building on your laptop + a registry, and you'll run several apps on the
box long-term. For *this* three-tier app, Kamal carries the api-build wart — a
first-timer often gets live with compose, then tries Kamal as a deliberate exercise
once the Docker concepts have clicked.

---

Sources: [kamal-deploy.org/docs](https://kamal-deploy.org/docs/configuration/overview/),
[proxy config](https://kamal-deploy.org/docs/configuration/proxy/),
[accessories](https://kamal-deploy.org/docs/configuration/accessories/).
