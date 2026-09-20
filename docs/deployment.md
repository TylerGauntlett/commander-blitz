# Deployment

Every commit to `main` that passes `scripts/verify.py` is built into a container
image and deployed to a DigitalOcean droplet. Nothing is deployed by hand.

```
                  ┌── python ──┐
push to main ──▶ lint ─ sim ───┼─▶ gate ──▶ build image ──▶ push to GHCR ──▶ ssh + compose up ──▶ /health
                  └── frontend ┘    │                                                                │
                                    └── a failure here stops everything ─────────────────────────────┘
```

A pull request runs the same jobs plus a six-leg `e2e` matrix; a push to main
skips that half, having already run it on the pull request that became the
merge. `gate` is the single check that judges them all, and the only one `build`
waits on.

- **Pipeline** — [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
- **Image** — [`Dockerfile`](../Dockerfile), published to `ghcr.io/tylergauntlett/auto-mtg`
- **Runtime** — [`docker-compose.yml`](../docker-compose.yml) and [`Caddyfile`](../Caddyfile), which live at `/opt/automtg/` on the droplet
- **Infrastructure** — [`terraform/`](../terraform/)

## How it fits together

The image serves the API *and* the built client from one process on one origin.
That is not a stylistic choice: the client calls same-origin `/api` and `/art`
(`frontend/src/api/client.ts`), so two hosts would mean inventing a base-URL
setting and opening up CORS. `get_app()` already passes `serve_client=True`, and
the Dockerfile points `AUTOMTG_CLIENT_DIR` at the built assets.

Two environment variables are set in the image and both are load-bearing.
`AUTOMTG_DATA_DIR` and `AUTOMTG_CLIENT_DIR` default to a walk up from
`__file__` that only resolves inside a source checkout; under a site-packages
install that walk lands nowhere, so the container sets both explicitly.

## First-time setup

### 1. Credentials

Copy `.env.example` to `.claude/.env` and fill in both values. Nothing reads
that path automatically -- the provisioning steps below load it into the shell
by hand, and the `digitalocean` provider then picks `DIGITALOCEAN_TOKEN` up from
the environment -- so the location only has to match the loader. `git check-ignore -v .claude/.env`
before you paste a real token in; the bare-name `.env` rule covers it.

Terraform failing every API call with `401 Unable to authenticate you` means
this file was never loaded into the session, or the token expired. DO tokens
carry an expiry now, so a setup that worked months ago can stop working with
nothing having changed locally. Check with:

```powershell
(Invoke-RestMethod -Uri https://api.digitalocean.com/v2/account `
  -Headers @{Authorization = "Bearer $env:DIGITALOCEAN_TOKEN"}).account.email
```

| Variable | Where to get it | Scopes |
| --- | --- | --- |
| `DIGITALOCEAN_TOKEN` | [DO API tokens](https://cloud.digitalocean.com/account/api/tokens) | read + write |
| `GH_TOKEN` | GitHub → Settings → Developer settings → PAT | Only needs to write Actions secrets. A fine-grained PAT with Contents r/w, Workflows r/w and **Secrets r/w** is enough; no package scope is required |

### 2. Tooling

```powershell
winget install --id Hashicorp.Terraform -e
winget install --id GitHub.cli -e
```

Both need a fresh shell before they are on `PATH`. Docker is **not** required
locally — the image is built by GitHub Actions and run on the droplet.

### 3. The CI deploy key

Separate from your own SSH key so it can be rotated without locking you out,
and generated outside the working tree so a private key never sits in the repo.
No passphrase: CI cannot type one.

```powershell
ssh-keygen -t ed25519 -C automtg-ci -N '""' -f $env:USERPROFILE\.ssh\automtg_ci
```

### 4. Provision

```powershell
# Load the credentials into the session. Needed for every terraform run, not
# just the first: the session, not the file, is what the provider reads.
Get-Content .claude\.env | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
  $k, $v = $_ -split '=', 2; Set-Item "env:$($k.Trim())" $v.Trim()
}

cd terraform
Copy-Item terraform.tfvars.example terraform.tfvars
# Fill in admin_ssh_public_key and ci_ssh_public_key, then:
terraform init
terraform apply
```

This creates the droplet, a reserved IP, a firewall (22, 80 and 443 inbound),
and runs a cloud-init bootstrap that installs Docker and creates the `deploy`
user. Bootstrap takes a couple of minutes after `apply` returns; the deploy job
waits for it.

### 5. Repository secrets

```powershell
cd ..
$ip = terraform -chdir=terraform output -raw reserved_ip

gh secret set DROPLET_HOST --repo TylerGauntlett/Auto-MTG --body $ip
```

The SSH key must be set from a shell that will not re-encode it. **Do not pipe
it in from PowerShell** — PowerShell 5.1 re-encodes native-command pipes and the
key arrives corrupted, which surfaces as `ssh: no key found` at deploy time with
no hint about where the damage happened. Use Git Bash and a redirect:

```bash
gh secret set DROPLET_SSH_KEY --repo TylerGauntlett/Auto-MTG < ~/.ssh/automtg_ci
```

| Secret | Purpose |
| --- | --- |
| `DROPLET_HOST` | Where to SSH, and what the health check curls |
| `DROPLET_SSH_KEY` | Private half of the CI deploy key |

**Neither side of the registry needs a stored token.** The build job pushes with
the `GITHUB_TOKEN` Actions injects automatically, and the deploy job hands that
same token to the droplet for the pull, which is why it declares
`permissions: packages: read`. The credential dies with the workflow run, so no
long-lived registry token exists on the droplet or in the repo's secrets.

A fine-grained PAT will *not* work here as a substitute: it authenticates to
`ghcr.io` and is issued a token, but that token is refused (403) when it tries
to read a private package. GHCR wants a classic PAT with `read:packages`, and
this setup avoids needing either.

### 6. Push

```powershell
git push origin main
gh run watch
```

Then open <https://commanderblitz.com>. The bare IP is not a way in — Caddy
serves that one name and answers anything else with a 404. See [HTTPS](#https).

## Operating it

```bash
ssh admin@<ip>
cd /opt/automtg
docker compose ps
docker compose logs -f --tail=100
cat .env                     # the SHA currently deployed
```

### Rolling back

The live version is one line in `/opt/automtg/.env`, and every deploy leaves an
immutable `sha-<commit>` tag in GHCR.

```bash
ssh deploy@<ip>
cd /opt/automtg
docker images ghcr.io/tylergauntlett/auto-mtg --format '{{.Tag}}'   # what is cached
echo "IMAGE_TAG=sha-abc1234" > .env                                 # pick one of those
docker compose up -d
```

Confirm with `curl https://commanderblitz.com/health`.

**This only works for a tag still in the droplet's local image cache** — which
is every recent deploy, since the nightly prune keeps 168h. The deploy job logs
out of `ghcr.io` when it finishes, deliberately, so nothing durable is left on
the box; a tag that has been pruned therefore cannot be re-pulled and
`docker compose up -d` fails with `denied`. `docker images` above is what tells
you which tags are actually reachable.

To go back further, re-run the pipeline at that commit instead — it rebuilds and
redeploys with a valid short-lived token, and leaves the box in the same clean
state:

```powershell
gh run list --workflow deploy.yml --limit 20     # find the run for that SHA
gh run rerun <run-id>
```

## Things to know

**A redeploy drops in-flight games.** `server/sessions.py` keeps games in
process memory, so replacing the container ends every game in progress. Same
reason the container runs `--workers 1`: a second worker would serve half the
requests from a process that has never heard of the game being played. This
also rules out horizontal scaling without a shared session store.

**One Docker volume holds everything durable.** `generated` carries cards and
decks from deck imports plus the card art lazily fetched from Scryfall
(`data/generated/art`). It is mounted at `/app/data/generated` and survives
redeploys. Art fetched for a *deck's chosen printing* lands there too, named
`{scryfall_id}.jpg` (or `{scryfall_id}_back.jpg`), so it grows by one file per
distinct printing an imported deck asks for — shared across decks and seats
that chose the same illustration. Everything else in `/app/data` — the committed art, the catalog
index — comes from the image and is replaced wholesale by every deploy.

**A volume must never be mounted over repository content.** There used to be a
second volume at `/app/data/art`, over the ~800 committed jpgs, on the reasoning
that anything missing is fetched on demand anyway. That holds for a *missing*
file and fails for a *changed* one. A named volume seeds itself from the image
only the first time it is created and no later image re-seeds it, so every one
of those files stayed frozen at whatever the first deploy shipped. When #36
pinned Sheoldred, the Apocalypse to her Dominaria United art, the new bytes were
committed, built into the image, deployed to the droplet — and unreachable,
because a file of that name was already in the volume and `ArtStore` serves any
file it finds. `tests/server/test_art_api.py::TestTheDeployedShape` is the guard.

If a droplet predates this, `automtg_art` is still there as an orphan holding
~63MB of stale images. Nothing reads it; `docker volume rm automtg_art` once the
new image is up.

**`terraform destroy` deletes the volume** along with the droplet. Nothing in it
is irreplaceable — art re-downloads — but imported decks are not recoverable
from the repo.

**Terraform state is local and gitignored.** The `terraform/` directory on your
machine is the only record of what exists. Losing it means importing the
resources by hand, or deleting them in the DO console and re-applying.

**The verify gate had three silent skips, and they are now enforced rather than
remembered.** `verify.py` prints `SKIP frontend` and exits zero when
`frontend/node_modules` is missing, when neither npm nor bun is on PATH, and
skips the story and Playwright stages when no Chromium build is present. The
workflow still runs `npm ci` and `npx playwright install --with-deps chromium`,
but every job now also passes `--strict`, which turns all three into failures —
so a job whose toolchain went missing fails instead of passing having asserted
nothing. Two further guards matter now that the gate is nine jobs rather than
one: an unknown `--only` group is an argparse error, and a slice that selects
zero stages exits 1 rather than reporting success.

## HTTPS

The site is <https://commanderblitz.com>. A [`caddy`](../Caddyfile) sidecar is
the only container bound to a host port; it terminates TLS and reverse-proxies
to `web:8000` on the compose network. The app image knows nothing about any of
this — the client is origin-relative throughout, so nothing in it has to learn
the scheme.

**The apex A record is a prerequisite and is not managed here.** The zone is not
hosted at DigitalOcean, so the record pointing `commanderblitz.com` at the
reserved IP is edited at the registrar. Terraform prints the IP:

```powershell
terraform -chdir=terraform output -raw reserved_ip
```

**Renewal is automatic and there is no cron job.** Caddy is a long-running
process that manages its own certificate lifecycle: it checks the store every
few minutes, renews at roughly 30 days remaining, and reloads without dropping
connections. Nothing has to be run by hand, ever.

Three things make that work, and each is a way to break it:

- **`caddy_data` must persist.** It holds the certificate and the ACME account
  key. An ephemeral volume re-issues on every restart, and Let's Encrypt
  rate-limits duplicate certificates to five a week.
- **Port 80 must stay open.** It carries the HTTP-01 challenge as well as the
  redirect to 443. Closing it breaks renewal roughly 60 days later, not
  immediately.
- **The A record must keep pointing here.**

[`tls-check.yml`](../.github/workflows/tls-check.yml) runs weekly and fails —
mailing you — if the certificate is under 21 days from expiry, `/health` stops
answering over TLS, or port 80 stops redirecting. It exists because no contact
address is registered with Let's Encrypt, so nothing else would warn us.

### When issuance fails

```bash
ssh admin@<ip>
cd /opt/automtg
docker compose logs caddy | grep -i -e certificate -e acme
```

The reason is named there, and it is almost always the challenge not reaching
port 80 — the firewall, or DNS pointing elsewhere. While iterating on a fix, add
`acme_ca https://acme-staging-v02.api.letsencrypt.org/directory` to a global
options block at the top of the `Caddyfile` so retries do not burn the
production rate limit; staging certificates are untrusted by browsers, so remove
it once the challenge succeeds.

A `Caddyfile` edit alone will not take effect on redeploy — a bind-mounted file
changing does not make compose recreate the container. The deploy job runs
`docker compose exec -T caddy caddy reload` for exactly this reason; by hand it
is the same command.
