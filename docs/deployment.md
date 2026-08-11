# Deployment

Every commit to `main` that passes `scripts/verify.py` is built into a container
image and deployed to a DigitalOcean droplet. Nothing is deployed by hand.

```
push to main ──▶ verify ──▶ build image ──▶ push to GHCR ──▶ ssh + compose up ──▶ /health
                  │                                                                  │
                  └── a failure here stops everything ───────────────────────────────┘
```

- **Pipeline** — [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
- **Image** — [`Dockerfile`](../Dockerfile), published to `ghcr.io/tylergauntlett/auto-mtg`
- **Runtime** — [`docker-compose.yml`](../docker-compose.yml), which lives at `/opt/automtg/` on the droplet
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

Copy `.env.example` to `.env` at the repo root and fill in both values. `.env`
is gitignored; confirm with `git check-ignore -v .env` before you paste a real
token into it.

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
# Load .env into the session.
Get-Content .env | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
  $k, $v = $_ -split '=', 2; Set-Item "env:$($k.Trim())" $v.Trim()
}

cd terraform
Copy-Item terraform.tfvars.example terraform.tfvars
# Fill in admin_ssh_public_key and ci_ssh_public_key, then:
terraform init
terraform apply
```

This creates the droplet, a reserved IP, a firewall (22 and 80 inbound only),
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

Then open `http://<reserved_ip>`.

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

Confirm with `curl http://<ip>/health`.

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

**Two Docker volumes hold everything durable.** `art` accumulates card images
lazily fetched from Scryfall, `generated` holds cards and decks from deck
imports. Both survive redeploys. A named volume seeds itself from the image the
first time it is created, so `art` starts out holding the ~800 images baked into
the image; later images do not re-seed it, which is harmless because anything
missing is fetched on demand.

**`terraform destroy` deletes those volumes** along with the droplet. Nothing in
them is irreplaceable — art re-downloads and decks can be re-imported — but
imported decks are not recoverable from the repo.

**Terraform state is local and gitignored.** The `terraform/` directory on your
machine is the only record of what exists. Losing it means importing the
resources by hand, or deleting them in the DO console and re-applying.

**The verify gate has two silent skips**, both defused in the workflow and worth
remembering if you ever edit it. `verify.py` prints `SKIP frontend` and exits
zero when `frontend/node_modules` is missing, and skips the story tests when no
Chromium build is present. The workflow runs `npm ci` and
`npx playwright install --with-deps chromium` so that neither gate passes
vacuously.

## Adding HTTPS later

The app is served over plain HTTP on the droplet's IP. Adding TLS means owning
a domain, pointing an A record at the reserved IP, and adding a Caddy service to
`docker-compose.yml` that terminates TLS and proxies to `web:8000` — plus
opening 443 in `terraform/main.tf`. The image itself would not change.
