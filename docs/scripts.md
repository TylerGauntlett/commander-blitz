# Scripts and environment variables

Two tables. The first names every script in the repository, what it is for,
and the page that owns the workflow it belongs to — read that page before
running the script. The second names every environment variable the code
reads, which module reads it, and who sets it.

## Scripts

Every Python script under `scripts/` is run from the repository root with the
project's interpreter (`python scripts/<name>.py --help` prints its usage).
The ones marked *stdlib only* run without the venv.

| Script | What it does | Owning page |
|---|---|---|
| `scripts/verify.py` | The "is it done?" gate: every check in dependency order, stopping at the first failure. `--quick`, `--no-frontend`, `--coverage`, `--e2e`; CI runs one `--only` slice per runner under `--strict` | [testing.md](testing.md) |
| `scripts/author_cards.py` | Implement cards in batches and refuse to ship any that cannot prove they work: `--report`, `--tier templates`, `--tier agent --card`, `--collect` | [card-authoring.md](card-authoring.md) |
| `scripts/audit_cards.py` | Measure the hand-written pool against what its cards actually print; `--fix-oracle`, `--fix-text`, `--open-deficits`, `--update-baseline`, `--check-substitutions` | [card-authoring.md](card-authoring.md#repairing-a-hand-written-card) |
| `scripts/report_gaps.py` | Collapse the gap records in `data/authoring/gaps/` by the capability each names and regenerate `docs/unsupported-cards.md` wholesale; `--top`, `--json` | [card-authoring.md](card-authoring.md), [unsupported-cards.md](unsupported-cards.md) |
| `scripts/roadmap.py` | The feature backlog as data: validate the items under `docs/roadmap/`, derive the queue (`--next`), scaffold one (`--new`), move one (`--start`, `--done`, `--drop`) and regenerate `docs/roadmap.md` wholesale (`--write`); `--check` is the gate. *Stdlib only* | [roadmap.md](roadmap.md) |
| `scripts/build_card_index.py` | Turn a Scryfall bulk dump into the committed catalog (`cards.sqlite`, `registry_images.json`) and fetch missing art; `--refresh`, `--check`, `--no-download`, `--no-art`. *Stdlib only* | [card-catalog.md](card-catalog.md) |
| `scripts/fetch_card_art.py` | Download card art into `data/art/` once, keyed on the engine `card_id`; normally called by `build_card_index.py`. *Stdlib only* | [card-catalog.md](card-catalog.md) |
| `scripts/validate_decks.py` | Validate every card file and deck list; the authored layer by default, `--all` adds imports. Exits non-zero on the first problem | [decks.md](decks.md#checking-a-deck) |
| `scripts/promote_deck.py` | Copy an imported deck out of `data/generated/` into a committed precon under `data/decks/`, refusing if any card is not native | [decks.md](decks.md#bringing-your-own) |
| `scripts/play_cli.py` | Play a game in the terminal: the fastest way to poke at the engine. `--players`, `--auto` | [architecture.md](architecture.md) |
| `scripts/smoke_http.py` | Play a whole game against a running server exactly as the browser client does; `--pod` drives the lobby and the per-seat token boundary | [testing.md](testing.md) |
| `scripts/run_arena.py` | Headless duels and pods between agents, with a results table; `--decks precons` is the deck-strategy benchmark | [ai-training.md](ai-training.md#evaluating) |
| `scripts/train.py` | Train a self-play policy, one checkpoint per pod size. Needs the `train` extra | [ai-training.md](ai-training.md#the-trainer) |
| `scripts/lock_deps.py` | Rewrite `constraints.txt` from `pyproject.toml` for the platform CI and the image run on; `--check` is the CI gate | [deployment.md](deployment.md) |
| `frontend/scripts/fetch-symbols.py` | Pull the mana symbol SVGs from Scryfall's symbology endpoint into `frontend/public/symbols/`, once. *Stdlib only* | [client.md](client.md) |
| `frontend/scripts/make-icons.mjs` | Render every brand raster in `frontend/public/` from `favicon.svg` with Playwright's Chromium (`npm run icons`); `--steam` writes the Steam library artwork | [client.md](client.md) |
| `frontend/scripts/story-layout-audit.mjs` | Measure every Storybook story desktop vs handheld and report only the delta — bleed and clipping (`npm run audit:stories`) | [client.md](client.md#storybook-conventions) |
| `desktop/scripts/assemble-content.mjs` | Put a content package together (`manifest.json`, `server/`, `client/`, `data/` without the runtime and pipeline directories), optionally as a tarball with `content-latest.json` | [deployment.md](deployment.md#desktop-releases) |
| `.agents/skills/import-moxfield/scripts/deck_status.py` | Import a Moxfield deck the way a pasted link does and say what is not native; exit code is the answer, `--pin-list` prints the tuple for an import test | [deck-import.md](deck-import.md) |
| `desktop/steam/test/install.test.sh` | `install.sh` end to end in a scratch home against a stub Steam: a fresh install, a re-run, and the app-id fallback | [testing.md](testing.md), [steamdeck.md](steamdeck.md) |
| `.github/scripts/conventional.sh` | The conventional-commit rules in one place: `title`, `body` and `ships`, called by the PR gate, the ship decision on `main` and the `/create-pr` skill | [adr/0010-release-every-main-build.md](adr/0010-release-every-main-build.md), [deployment.md](deployment.md) |

## Environment variables

### `COMMANDERBLITZ_*`

Who sets each one is the column that matters. A variable the deploy image or
the desktop shell sets is configuration; a variable only a test harness sets
is a test switch, and a shipped build must never set it.

| Variable | Read by | What it does | Set by |
|---|---|---|---|
| `COMMANDERBLITZ_DATA_DIR` | `cards.registry.data_dir()`; `desktop/src/main.ts` in development, which passes it on as `--data-dir` | Where the authored cards, decks, catalog and art are; everything under `data/` resolves from it | the Dockerfile; `server.desktop.apply_env` from `--data-dir`; a developer running the shell against the checkout |
| `COMMANDERBLITZ_GENERATED_DIR` | `cards.registry.generated_dir()` | Where runtime writes land — imports, the generated pool, the art cache — apart from the data, so a read-only install still works. `tests/cards/test_generated_dir.py` holds every write path to it | `server.desktop.apply_env` from `--generated-dir`; the shell computes it from the per-user home (`desktop/src/paths.ts`); Playwright's sidecar config points it at a scratch directory |
| `COMMANDERBLITZ_CLIENT_DIR` | `server.app.create_app`; `desktop/src/main.ts` in development, which passes it on as `--client-dir` | The built client to serve at `/` when `serve_client` is on; the default is the checkout's `frontend/dist` | the Dockerfile; `server.desktop.apply_env` from `--client-dir`; a developer running the shell against the checkout |
| `COMMANDERBLITZ_MODE` | `server.settings.settings_from_env` | `hosted` or `desktop`; what `/api/config` reports and the client greys out on | `server.desktop.apply_env`, always `desktop`; unset (hosted) everywhere else |
| `COMMANDERBLITZ_REMOTE_ORIGIN` | `server.settings.settings_from_env` | The hosted server, from the desktop's point of view; the origin `connectivity.RemoteProbe` probes | `server.desktop.apply_env` from `--remote-origin` |
| `COMMANDERBLITZ_CONTENT_VERSION` | `server.settings.settings_from_env` | The content package version the shell is running, reported by `/api/config` | `server.desktop.apply_env` from `--content-version` |
| `COMMANDERBLITZ_EAGER_ART` | `server.settings.settings_from_env` | `1` fetches a freshly imported deck's art at once rather than on first display, because the desktop's next launch may be offline | `server.desktop.apply_env`, always `1` |
| `COMMANDERBLITZ_FIXTURE_DECKS` | `cards.registry.fixture_decks_enabled`, read by `server_registry()` | `1` loads `data/decks/fixtures/` into the server, so seeded browser specs deal the retired lists they were written against. Test switch | `frontend/playwright.config.ts`'s `webServer`; `scripts/verify.py` for the smoke stage. Deliberately absent from the sidecar config and from `apply_env` |
| `COMMANDERBLITZ_CPU` | `ai.agents.base.agent_by_name`; `ai.strategy` | `classic` makes plain `heuristic` mean the pre-strategy agent, so seeded games stay the games their specs recorded. Test switch | the same two places as `COMMANDERBLITZ_FIXTURE_DECKS`, and absent from the same two |
| `COMMANDERBLITZ_UPDATE_GOLDEN` | `tests/cards/test_golden_pool.py` | `1` re-pins the compiled-pool hash and vocabulary files beside the test instead of comparing against them | a developer, when a change to the pool is intended; see [testing.md](testing.md) |
| `COMMANDERBLITZ_CARD_CATALOG` | `scripts/build_card_index.py` | A bulk bundle to read when nothing is cached under `data/catalog/bulk/` and no path was given | a developer |
| `COMMANDERBLITZ_HOME` | `desktop/src/paths.ts` | The desktop app's per-user root (content packages, generated data, logs, downloads, state), overriding the platform default | `desktop/steam/test/install.test.sh` and the release smoke job, to run the whole app in a scratch directory |
| `COMMANDERBLITZ_SIDECAR_PYTHON` | `desktop/src/main.ts` | Development override: an interpreter with the package installed, which runs `-m commanderblitz.server.desktop` in the checkout instead of the frozen binary | a developer running the shell against the repo |
| `COMMANDERBLITZ_CONTENT` | `desktop/src/main.ts` | Where the bundled content directory is when the shell is not packaged | a developer; the default is `desktop/dev-content` |
| `COMMANDERBLITZ_REMOTE` | `desktop/src/main.ts` | The shell's remote origin (where pods with friends are), handed to the sidecar as `--remote-origin` | a developer; the default is the site. The sidecar Playwright config bypasses it and passes `--remote-origin` itself |
| `COMMANDERBLITZ_RELEASES` | `desktop/src/main.ts` | Where `content-latest.json` and content tarballs are published, for the update check | a developer; the default is the GitHub releases page |

Three names of the same shape are not environment variables but window
globals. `window.__COMMANDERBLITZ_SEED` and `window.__COMMANDERBLITZ_ZOOM_LOCK`
are set by `frontend/e2e/helpers.ts` with `addInitScript` so a spec can pin a
shuffle or the zoom without a control existing in a real player's build;
`window.__COMMANDERBLITZ_RING` is a diagnostic the input layer exposes and the
handheld specs read.

### Others the harnesses read

| Variable | Read by | What it does | Set by |
|---|---|---|---|
| `PYTHON` | `frontend/playwright.config.ts`, `frontend/playwright.sidecar.config.ts`, `desktop/steam/test/install.test.sh`, `desktop/sidecar/smoke.sh` | The interpreter that boots the server for the Playwright suites, and `python3`'s stand-in for the shell tests on Windows | `scripts/verify.py` hands its own interpreter; the CI setup action; otherwise the repo's `.venv` |
| `E2E_SLOW` | both Playwright configs | A multiplier on every press budget and timing assertion, for slow machines and tracing | `scripts/verify.py --e2e` sets `2`; a developer |
| `COVERAGE_FLOORS` | `frontend/vite.config.ts` | `off` drops the coverage thresholds for a jsdom-only run, since most floors are only reachable with the story projects in the same process | `scripts/verify.py` on a machine without Chromium |
