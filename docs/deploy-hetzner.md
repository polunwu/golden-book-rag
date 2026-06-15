# Deploy to a Hetzner VPS (shared reverse proxy + Cloudflare DNS)

Beginner runbook. Target shape: one small Hetzner VPS running Docker; a shared
Caddy reverse proxy (`deploy/edge/`) owns 80/443 and auto-issues HTTPS; each
project (this one + future ones) registers itself by docker labels. Cloudflare
holds DNS.

```
internet ──443──► [shared Caddy] ──► books.example.com → web:3000 → api:8000 → db
 (proxy network)                  └─► (other projects by their own domains)
```

You only ever expose the shared Caddy. Everything else is on private docker nets.

---

## Phase 0 — Before you start (have these ready)

- A domain you control, added to Cloudflare (free plan is fine).
- Your `GEMINI_API_KEY`.
- An SSH key on your laptop (`ls ~/.ssh/id_ed25519.pub`; if missing:
  `ssh-keygen -t ed25519`).
- Decide the hostname for this app, e.g. `books.example.com`.

---

## Phase 1 — Create the Hetzner server

1. hetzner.com/cloud → Console → New Project → **Add Server**.
2. Location: pick near your users. Image: **Ubuntu 24.04**.
3. Type: **CX22** (x86, 2 vCPU / 4 GB, ~€4/mo) is a safe default. (CAX11 ARM is
   cheaper and our images support arm64, but CX22 avoids any arch surprises.)
4. **SSH keys**: add your `~/.ssh/id_ed25519.pub` (paste its contents). This is
   how you log in — no password.
5. Create. Note the server's **public IPv4** (and IPv6).

---

## Phase 2 — First login + secure the box

```bash
ssh root@<SERVER_IP>          # first login as root via your SSH key
```

Create a non-root sudo user and harden SSH:

```bash
adduser deploy               # set a password when prompted
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy   # copy your SSH key
```

Open a SECOND terminal and confirm the new user works before locking root out:

```bash
ssh deploy@<SERVER_IP>       # must succeed
```

Back as root, disable root SSH + password auth:

```bash
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
```

Firewall (only SSH + web):

```bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable
```

From here on, work as `deploy`: `ssh deploy@<SERVER_IP>`.

---

## Phase 3 — Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # run docker without sudo
exit                                # log out and back in for the group to apply
```

Re-login and verify: `docker run --rm hello-world`.

---

## Phase 4 — Get the code onto the server (GitHub deploy key)

The repo is private, so create a **read-only deploy key** on the server:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
```

Copy that public key → GitHub repo → **Settings → Deploy keys → Add deploy key**
(read-only, no write access needed). Then tell SSH to use it for GitHub:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
EOF

git clone git@github.com:polunwu/golden-book-rag.git
cd golden-book-rag
```

To update later: `git pull` (read-only key is enough).

---

## Phase 5 — Bring up the shared reverse proxy (once per machine)

```bash
docker network create proxy          # the shared network all apps join

cd ~/golden-book-rag/deploy/edge
cp .env.example .env
nano .env                            # set ACME_EMAIL=you@example.com
docker compose up -d
docker compose logs -f caddy         # leave running; watch for errors (Ctrl-C to stop tailing)
```

This is set up **once**. Future projects just join the `proxy` network and add
`caddy.*` labels — you never touch this again.

---

## Phase 6 — Point DNS at the server (Cloudflare)

In Cloudflare → your domain → **DNS → Records**:

- Add **A** record: name `books` (→ `books.example.com`), value `<SERVER_IPv4>`.
- Add **AAAA** record: name `books`, value `<SERVER_IPv6>` (optional but nice).
- **Proxy status: DNS only (grey cloud)** for now — so Caddy can fetch a
  Let's Encrypt cert directly. (You can switch to orange later, see Phase 9.)

Verify it resolves to your IP (wait a minute):

```bash
dig +short books.example.com
```

---

## Phase 7 — Configure + launch this app

```bash
cd ~/golden-book-rag
nano .env
```

Put this in `.env` (generate secrets with `openssl rand -hex 32`):

```dotenv
DOMAIN=books.example.com
POSTGRES_PASSWORD=<openssl rand -hex 32>
GEMINI_API_KEY=<your key>
ADMIN_SECRET=<openssl rand -hex 32>
```

Build and start (first build of the Next app takes a few minutes):

```bash
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml ps        # db healthy, api/web/up
docker compose -f docker-compose.prod.yml logs -f api
```

The `api` container runs `alembic upgrade head` on start, so the schema is created
automatically.

---

## Phase 8 — Verify

```bash
curl -I https://books.example.com            # expect HTTP/2 200, valid cert
```

Open `https://books.example.com` in a browser, upload a PDF, ask a question.
If the cert isn't ready yet, watch `deploy/edge` logs:
`cd ~/golden-book-rag/deploy/edge && docker compose logs -f caddy`.

---

## Phase 9 — (Optional) Turn on Cloudflare proxy

Once it works end-to-end with grey cloud, you can enable Cloudflare's proxy
(orange cloud) for caching/DDoS/hiding your IP:

1. Cloudflare → SSL/TLS → set mode to **Full (strict)** (origin has a real
   Let's Encrypt cert, so strict is correct).
2. Flip the DNS record to **Proxied (orange)**.

Caveat: on the **free** plan Cloudflare caps proxied uploads at **100 MB** — same
as this app's `MAX_UPLOAD_MB`, so very large books are borderline. If that bites,
keep the record grey (DNS only).

---

## Day-2 operations

Redeploy after pushing code:

```bash
cd ~/golden-book-rag
git pull
docker compose -f docker-compose.prod.yml up --build -d   # rebuilds changed images
```

- Changed the backend URL / `DOMAIN`? The Next `/api/*` rewrite is baked at build
  time, so a `DOMAIN` change only affects routing (label) — but a `BACKEND_ORIGIN`
  change needs `--build`. `up --build` covers both.
- Logs: `docker compose -f docker-compose.prod.yml logs -f api`
- DB shell: `docker compose -f docker-compose.prod.yml exec db psql -U bookrag -d bookrag`
- **Backups** (do this!): the data lives in two docker volumes,
  `golden-book-rag_bookrag_pgdata` (DB) and `golden-book-rag_bookrag_uploads`
  (PDFs). Dump the DB on a schedule, e.g.:
  ```bash
  docker compose -f docker-compose.prod.yml exec -T db \
    pg_dump -U bookrag bookrag | gzip > ~/backup-$(date +%F).sql.gz
  ```
  Also keep the edge `caddy_data` volume (your TLS certs).

## Adding another project later (why we set it up this way)

1. Its compose: put `web` on the external `proxy` network + add the same
   `caddy: <its-domain>` / `caddy.reverse_proxy: "{{upstreams <port>}}"` labels.
2. Add its DNS record in Cloudflare → the server IP.
3. `docker compose up -d`. The shared Caddy auto-detects it and issues a cert.

No edits to the proxy, no port conflicts.
