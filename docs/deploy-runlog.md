# Deploy run log — first production bring-up

A record of what was **actually done** to provision the production box, on top of the
generic guide in [`deploy-hetzner-kamal.md`](deploy-hetzner-kamal.md). The runbook is
the "how"; this is the "what we picked + ran" for *this* server, so it can be rebuilt
or audited later.

- **Date:** 2026-06-17
- **Server IP:** kept out of git by design — see `SERVER_IP` in `.kamal/secrets`.
  Every `<SERVER_IP>` below is that value.
- **No secrets in this file.** PAT / DB password / Gemini key / admin secret all live
  only in `.kamal/secrets` (gitignored).

## Choices made

| Decision | Value | Note |
|---|---|---|
| Provider / type | Hetzner Cloud **CX23** | x86 / **amd64** shared vCPU (~€7.25/mo incl. IPv4) |
| Image | **Ubuntu 26.04 LTS** | newer than the runbook's 24.04; Docker install script handled it |
| Networking | IPv4 + IPv6 | only IPv4 is used (DNS A record, `SERVER_IP`, SSH) |
| Build arch | **amd64** | arm64 Mac → amd64 server, so `buildx`/`builder` use QEMU emulation (slower first build) |
| Domain | `books.polunwu.com` | Cloudflare A record → `<SERVER_IP>`, **grey cloud** (DNS only) for Let's Encrypt |
| Deploy user | `deploy` | non-root, in `sudo` + `docker` groups |
| Login key | existing `~/.ssh/id_ed25519` | no passphrase (deferred — noted as a follow-up) |

## Phase 2 — server hardening + Docker (run on the box, as root)

```bash
# create the non-root deploy user, give it sudo, copy the SSH key to it
adduser deploy                                              # set a password at the prompt
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy

# install Docker, let deploy run it without sudo
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
# verified in a 2nd terminal BEFORE locking root out: `ssh deploy@<SERVER_IP>` + `docker ps`

# harden SSH: key-only, no root login
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
# verified deploy still logs in before closing the root session

# firewall: SSH + web only (api/db never publish ports to the host)
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable
```

Result: `ufw status` = active, allowing OpenSSH / 80 / 443 (v4 + v6).

**Not done (optional follow-ups):** unattended-upgrades, fail2ban, an SSH key passphrase.

## Deploy sequence (run from the laptop)

```bash
# secrets: SERVER_IP, random POSTGRES_PASSWORD/ADMIN_SECRET, matching DATABASE_URL,
# plus the GitHub PAT and Gemini key — all in .kamal/secrets (gitignored).
echo "$PAT" | docker login ghcr.io -u polunwu --password-stdin

export SERVER_IP=$(awk -F= '/^SERVER_IP=/{print $2}' .kamal/secrets)   # this Kamal doesn't auto-load secrets
kamal server bootstrap                                                  # SSH + Docker check

# api is an accessory → build + push it by hand (amd64 for the x86 server)
docker buildx build --platform linux/amd64 -t ghcr.io/polunwu/golden-book-rag-api:latest --push .

kamal accessory boot db          # Postgres first
kamal accessory boot api         # runs `alembic upgrade head` (4 migrations applied)
kamal deploy                     # build web from frontend/, boot proxy, go live with TLS
```

> `kamal setup` was tried first and **failed**: the app image built from the repo-root
> Dockerfile (the API), so the web container ran alembic and failed its healthcheck.
> Fix: `builder.context: ./frontend` + `builder.dockerfile: frontend/Dockerfile` in
> `config/deploy.yml`, then `kamal deploy`. Both this and the `SERVER_IP` export are now
> in the runbook's Troubleshooting + builder sections.

## Verified live (Phase 9)

- `curl -I https://books.polunwu.com` → **HTTP/2 200**
- TLS cert: **Let's Encrypt**, valid 2026-06-17 → 2026-09-15 (auto-renewed by kamal-proxy)
- `https://books.polunwu.com/api/books` → **200** (web → api → db all wired)

Containers on the box: `golden-book-rag-web`, `golden-book-rag-api`,
`golden-book-rag-db`, `kamal-proxy` — all Up.

## Day-2

Use the `make` targets (`make deploy`, `make deploy-api`, `make logs-*`,
`make kamal-config`, `make deploy-rollback`) — they auto-export `SERVER_IP`. See the
runbook's Day-2 table.
