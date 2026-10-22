# Deployment

Operating the site: what runs on the droplet, how to self-host it, how to
provision and roll back, and what keeps HTTPS alive. How a commit gets here --
the gate, what ships, the image build, the deploy job and the Steam Deck
release -- is [ci-cd.md](ci-cd.md). Nothing is deployed or released by hand in
the normal course of things; the hand-run paths below exist for recovery.

- **Pipeline** -- [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml), described in [ci-cd.md](ci-cd.md)
- **Image** -- [`Dockerfile`](../Dockerfile), published to `ghcr.io/tylergauntlett/commander-blitz`
- **Runtime** -- [`docker-compose.yml`](../docker-compose.yml) and [`Caddyfile`](../Caddyfile), which live at `/opt/automtg/` on the droplet
- **Infrastructure** -- [`terraform/`](../terraform/)
- **Desktop releases** -- [`.github/workflows/release.yml`](../.github/workflows/release.yml)

## How it fits together

The image serves the API *and* the built client from one process on one origin.
That is not a stylistic choice: the client calls same-origin `/api` and `/art`
(`frontend/src/api/client.ts`), so two hosts would mean inventing a base-URL
setting and opening up CORS. `get_app()` already passes `serve_client=True`, and
the Dockerfile points `COMMANDERBLITZ_CLIENT_DIR` at the built assets.

Two environment variables are set in the image and both are load-bearing.
`COMMANDERBLITZ_DATA_DIR` and `COMMANDERBLITZ_CLIENT_DIR` default to a walk up
from `__file__` that only resolves inside a source checkout; under a site-packages
install that walk lands nowhere, so the container sets both explicitly.

The droplet keeps the directory it was first provisioned with, `/opt/automtg/`,
from before the project was renamed. The compose project name comes from that
directory and names the volumes, so moving it would orphan the certificate store
and the imported decks; it stays.

## Self-hosting

You do not need DigitalOcean, Terraform or GitHub to run the site. The image is
public, and the compose file at the root is the whole runtime:

```bash
mkdir commanderblitz && cd commanderblitz
curl -fsSLO https://raw.githubusercontent.com/TylerGauntlett/commander-blitz/main/docker-compose.yml
curl -fsSLO https://raw.githubusercontent.com/TylerGauntlett/commander-blitz/main/Caddyfile
echo "IMAGE_TAG=latest" > .env
# Edit the Caddyfile: replace commanderblitz.com with your own name, or with
# `:80` for plain HTTP on a LAN.
docker compose up -d
```

Caddy terminates TLS for whatever name the Caddyfile holds and proxies to the app
on the compose network; the app itself listens on 8000 and knows nothing about
TLS or the host name. One named volume, `generated`, holds everything written at
runtime (imported decks and their art). Building the image yourself is
`docker build -t commanderblitz .` at the repository root.

## The hosted site

### Provisioning, once

Credentials go in `.claude/.env` (copy `.env.example`; the bare-name `.env`
rule gitignores it). Nothing reads that file automatically: the steps below load
it into the shell, and the `digitalocean` Terraform provider picks
`DIGITALOCEAN_TOKEN` up from the environment.

| Variable | Where to get it | Scopes |
| --- | --- | --- |
| `DIGITALOCEAN_TOKEN` | [DO API tokens](https://cloud.digitalocean.com/account/api/tokens) | read + write |
| `GH_TOKEN` | GitHub → Settings → Developer settings → PAT | Writes Actions secrets: a fine-grained PAT with Contents r/w, Workflows r/w and **Secrets r/w** on this repository |

Terraform failing every API call with `401 Unable to authenticate you` means the
file was never loaded into the session, or the token expired (DO tokens carry an
expiry). Check with:

```powershell
(Invoke-RestMethod -Uri https://api.digitalocean.com/v2/account `
  -Headers @{Authorization = "Bearer $env:DIGITALOCEAN_TOKEN"}).account.email
```

Tooling: `winget install --id Hashicorp.Terraform -e` and
`winget install --id GitHub.cli -e` (or your package manager's equivalents).
Docker is **not** required locally; the image is built by GitHub Actions and run
on the droplet.

The CI deploy key is separate from your own SSH key so it can be rotated without
locking you out, generated outside the working tree, and has no passphrase
because CI cannot type one:

```bash
ssh-keygen -t ed25519 -C commanderblitz-ci -N '' -f ~/.ssh/commanderblitz_ci
```

Then provision:

```bash
# Load the credentials into the session (every terraform run, not just the first).
set -a; . .claude/.env; set +a

cd terraform
cp terraform.tfvars.example terraform.tfvars
# Fill in admin_ssh_public_key and ci_ssh_public_key, then:
terraform init
terraform apply
```

This creates the droplet, a reserved IP, a firewall (the rules are in `terraform/`), and
runs a cloud-init bootstrap that installs Docker and creates the `deploy` user.
Bootstrap takes a couple of minutes after `apply` returns; the deploy job waits
for it. Terraform state is local and gitignored: the `terraform/` directory on the
machine that ran `apply` is the only record of what exists, so back it up.

### Repository secrets

| Secret | Purpose |
| --- | --- |
| `DROPLET_HOST` | Where to SSH. The health check curls the public domain, not this address, so that DNS and TLS are proven too |
| `DROPLET_SSH_KEY` | Private half of the CI deploy key |

```bash
gh secret set DROPLET_HOST --repo TylerGauntlett/commander-blitz --body "$(terraform -chdir=terraform output -raw reserved_ip)"
gh secret set DROPLET_SSH_KEY --repo TylerGauntlett/commander-blitz < ~/.ssh/commanderblitz_ci
```

Set the key from a POSIX shell. PowerShell 5.1 re-encodes native-command pipes
and the key arrives corrupted, which surfaces as `ssh: no key found` at deploy
time with no hint about where the damage happened.

**Neither side of the registry needs a stored token.** The build job pushes with
the `GITHUB_TOKEN` Actions injects automatically, and the deploy job hands that
same token to the droplet for the pull (`permissions: packages: read`). The
credential dies with the workflow run, so no long-lived registry token exists on
the droplet or in the repository's secrets.

The apex A record is a prerequisite and is not managed here: the zone is hosted at
the registrar, and the record pointing `commanderblitz.com` at the reserved IP
(`terraform -chdir=terraform output -raw reserved_ip`) is edited there.

### Operating it

```bash
ssh admin@<ip>
cd /opt/automtg
docker compose ps
docker compose logs -f --tail=100
cat .env                     # the SHA currently deployed
```

**Rolling back.** The live version is one line in `/opt/automtg/.env`, and every
deploy leaves an immutable `sha-<commit>` tag in GHCR.

```bash
ssh deploy@<ip>
cd /opt/automtg
docker images ghcr.io/tylergauntlett/commander-blitz --format '{{.Tag}}'   # what is cached
echo "IMAGE_TAG=sha-abc1234" > .env                                        # pick one of those
docker compose up -d
```

Confirm with `curl https://commanderblitz.com/health`. The image is public, so a tag
the nightly prune has dropped from the droplet's cache pulls again anonymously;
the deploy job's `docker logout` only discards the run's own token. If a tag is
gone from the registry too, re-run the pipeline at that commit:
`gh run list --workflow deploy.yml --limit 20`, then `gh run rerun <run-id>`.

### HTTPS

A [`caddy`](../Caddyfile) sidecar is the only container bound to a host port; it
terminates TLS and reverse-proxies to `web:8000` on the compose network. Renewal
is automatic and there is no cron job: Caddy renews at roughly 30 days remaining
and reloads without dropping connections. Three things make that work, and each
is a way to break it:

- **`caddy_data` must persist.** It holds the certificate and the ACME account
  key. An ephemeral volume re-issues on every restart, and Let's Encrypt
  rate-limits duplicate certificates to five a week.
- **Port 80 must stay open.** It carries the HTTP-01 challenge as well as the
  redirect to 443. Closing it breaks renewal roughly 60 days later.
- **The A record must keep pointing here.**

[`tls-check.yml`](../.github/workflows/tls-check.yml) runs weekly and fails,
mailing the maintainer, if the certificate is under 21 days from expiry, `/health`
stops answering over TLS, or port 80 stops redirecting. No contact address is
registered with Let's Encrypt, so nothing else would warn us.

When issuance fails, `docker compose logs caddy | grep -i -e certificate -e acme`
names the reason, which is almost always the challenge not reaching port 80 (the
firewall, or DNS pointing elsewhere). While iterating on a fix, add
`acme_ca https://acme-staging-v02.api.letsencrypt.org/directory` to a global
options block at the top of the `Caddyfile` so retries do not burn the production
rate limit, and remove it once the challenge succeeds. A `Caddyfile` edit alone
does not take effect on redeploy, because a bind-mounted file changing does not
make compose recreate the container; the deploy job runs
`docker compose exec -T caddy caddy reload`, and by hand it is the same command.

## Desktop releases

The Steam Deck build ([steamdeck.md](steamdeck.md)) is released by every push to
main that ships, behind the same green gate as the site; how the version is
formed, when the AppImage is rebuilt versus carried forward, and why a release
is published as a draft first are in [ci-cd.md](ci-cd.md#release). Major and
minor come from `desktop/package.json`; change them with a pull request when a
release deserves the number.

To release by hand, for example after a merge that did not ship or a release that
failed:

```bash
gh workflow run release.yml --ref main
```

A release carries three things, published together as a GitHub Release of this
repository:

| asset | what it is | who reads it |
|---|---|---|
| `CommanderBlitz-<v>.AppImage`, `latest-linux.yml` | the Electron shell, with the content package inside it; rebuilt only when the shell changed, otherwise the previous one carried forward | `install.sh` (first install), `electron-updater` (shell updates, installed on quit) |
| `content-<v>.tar.gz`, `content-latest.json` | the frozen server, the built client and the card data, versioned as one | the shell's own updater, which restarts the server in place |
| `steam-assets.tar.gz`, `install.sh`, `SHA256SUMS` | the library artwork and launcher; the one-line installer | `install.sh` itself, and anybody checking a download |

Everything the Deck fetches is a `releases/latest/download/<file>` URL, so it needs
no API, no token and no rate limit. There is no pre-release channel, because
`install.sh` and both updaters read only `latest`. To hold a risky change back
from Decks, merge it under a type that does not ship, build the AppImage locally
(`desktop/README.md`) and try it on a Deck, then release it with `gh workflow run`.

**Rolling back:** revert the change. The revert ships, and its release has a higher
version. `latest` is a pointer to the highest release, so deleting a release moves it
back for *new* installs. A Deck that already took the bad version keeps it, because the
shell never downgrades on its own. (It does roll back by itself when a new server fails
to start; see ADR 0009.)

**Testing without a Deck:** `desktop/README.md`. The pure modules under
`desktop/src/` run under vitest on any OS; the Electron wiring has a `--smoke`
mode that boots the sidecar and reads `/api/config`; the frozen server builds
natively on Windows and in a Linux container; `install.sh` runs against a stub
Steam in a scratch home (`desktop/steam/test/install.test.sh`, which the gate
runs).

## Things to know

**A redeploy drops in-flight games.** `server/sessions.py` keeps games in
process memory, so replacing the container ends every game in progress. Same
reason the container runs `--workers 1`: a second worker would serve half the
requests from a process that has never heard of the game being played. This
also rules out horizontal scaling without a shared session store.

**One Docker volume holds everything durable.** `generated` carries cards and
decks from deck imports plus the card art lazily fetched from Scryfall
(`data/generated/art`): a card's own art as `{card_id}.jpg`, and a printing a
deck or a catalog hover chose as `{scryfall_id}.jpg`, so it is shared across
decks and seats that chose the same illustration. Everything else in `/app/data`, the
committed art, the art store and the catalog index, comes from the image and is replaced
wholesale by every deploy.

**A volume must never be mounted over repository content.** There used to be a
second volume at `/app/data/art`, over the committed jpgs. A named volume seeds
itself from the image only the first time it is created and no later image
re-seeds it, so every one of those files stayed frozen at whatever the first
deploy shipped: a corrected illustration could be committed, built and deployed
and never appear. `tests/server/test_art_api.py::TestTheDeployedShape` is the
guard. A droplet that predates this still has the orphan `automtg_art` volume;
nothing reads it, and `docker volume rm automtg_art` reclaims it.

**`terraform destroy` deletes the volume** along with the droplet. Nothing in it
is irreplaceable (art re-downloads) but imported decks are not recoverable from
the repository.
