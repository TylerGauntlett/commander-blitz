# Contributing

Thanks for looking. This page is the short version of how the project is built and
verified; the long version is in [docs/](docs/README.md).

## Set up

Python 3.13 and Node 20+ (npm or bun).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS / Linux: source .venv/bin/activate
pip install -c constraints.txt -e ".[dev]"

cd frontend && npm install && npx playwright install chromium && cd ..
```

`constraints.txt` pins every Python dependency so a test run on your machine is the
same run CI does; `scripts/lock_deps.py` rewrites it. Add `",train"` to the extras
for the PPO trainer (it pulls in PyTorch).

**On Windows, one more step.** The agent skills live in `.agents/skills/` and
`.claude/skills/` holds symlinks into it. Git for Windows checks a symlink out as a
text file unless the account may create symlinks (Developer Mode, or an elevated
shell) and `core.symlinks` is on:

```bash
git config --global core.symlinks true
git rm -r --cached .claude/skills && git checkout -- .claude/skills   # existing clone
```

[AGENTS.md](AGENTS.md) has the check that it worked.

## Verify

```bash
python scripts/verify.py            # every gate, in order; stops at the first failure
python scripts/verify.py --quick    # skip the slow simulation stages
python scripts/verify.py --e2e      # ...and the Playwright projects (tens of minutes)
```

CI runs the same script, sliced across runners, and the pull request is green only
when every slice is ([docs/ci-cd.md](docs/ci-cd.md)). [docs/testing.md](docs/testing.md)
says which suite owns which kind of question. Two conventions worth knowing:

- Python is linted by `ruff check`; the repo is deliberately not `ruff format`
  clean, so do not reformat files you did not otherwise touch.
- The frontend is linted by Biome, which fails on CRLF line endings. If you are on
  Windows, let git handle line endings (`core.autocrlf=true`) rather than converting
  files by hand.

## Where things are

| Path | What lives there |
|---|---|
| `src/commanderblitz/engine` | The rules: a pure, deterministic state machine. No I/O, no HTTP |
| `src/commanderblitz/cards` | The card DSL, its loader, the catalog and the authoring pipeline |
| `src/commanderblitz/ai` | The Gymnasium environment, the agents and the per-deck CPU strategies |
| `src/commanderblitz/server` | The FastAPI app the browser and the desktop shell talk to |
| `frontend/` | The React client |
| `desktop/` | The Electron shell for the Steam Deck build |
| `data/` | Card definitions, decks, the catalog, art and authoring state ([data/README.md](data/README.md)) |
| `tests/` | Unit, per-card, AI and server suites |
| `scripts/` | The gate and every tool ([docs/scripts.md](docs/scripts.md)) |
| `.github/` | CI and CD ([docs/ci-cd.md](docs/ci-cd.md)) |
| `terraform/` | The droplet, applied by hand ([docs/deployment.md](docs/deployment.md)) |
| `.agents/skills/` | The agent skills; `.claude/skills/` symlinks into it |
| `runs/` | Training output, gitignored |

[docs/architecture.md](docs/architecture.md) explains why there is exactly one
seam between the engine and everything that drives it, and
[docs/rules-coverage.md](docs/rules-coverage.md) says what the engine does and
does not implement.

## Adding cards and decks

Cards are JSON in a DSL the engine compiles at load time:
[docs/card-dsl.md](docs/card-dsl.md) is the reference and
[docs/card-authoring.md](docs/card-authoring.md) is the pipeline that gets a card
from Scryfall's oracle text to a definition that passes all six gates (schema,
compile, residual, playable, behaviour, registry).

The project is largely built with coding agents, and the skills under
[`.agents/skills/`](.agents/skills/) (which Cursor reads directly and Claude Code
reads through `.claude/skills/`) are the supported way to grow the card pool. Each
is a checklist a person can follow by hand just as well:

- **`/import-moxfield <url>`** takes a Moxfield deck and does not stop until every
  card in it is fully playable: it drives the two skills below, runs every suite,
  commits as it goes and opens the pull request.
- **`/author-cards`** implements cards the DSL can already express, in bulk or by
  name, and verifies each through the six gates. Cards it cannot express become gap
  records in `data/authoring/gaps/`, which [docs/unsupported-cards.md](docs/unsupported-cards.md)
  is generated from.
- **`/extend-dsl`** builds the one engine capability that unblocks a gap record (a
  new effect op, cost, keyword, continuous effect or decision kind), with its unit
  test and any UI work, so the next `/author-cards` run can harvest the cards that
  were waiting on it.

A deck becomes a shipped deck through `scripts/promote_deck.py` once every card in
it is native; [docs/decks.md](docs/decks.md) has the steps, and
[docs/cpus/](docs/cpus/README.md) is where its CPU strategy gets a page.

## Pull requests

- One pull request per piece of work, with phased commits if it is big. A full CI
  run costs runner-hours, so a PR that goes green once beats three that each need
  a run.
- The title is a conventional commit, `type(scope): summary`, and CI checks it.
  It becomes the squash merge's subject, and its type decides whether the merge
  deploys the site and releases a new Steam Deck version. The list of types that
  ship lives in `.github/scripts/conventional.sh` and nowhere else
  ([docs/ci-cd.md](docs/ci-cd.md), [ADR 0010](docs/adr/0010-release-every-main-build.md)).
- The body follows the template: a short summary, two risk bullets, one
  diagram (the old path dotted, the new one solid), then what, why and how in
  three bullets each, with everything else folded into Details. `/create-pr`
  writes it for you.
- Say what changed and how you verified it. The template asks for both.
- Rules questions are settled by the Comprehensive Rules, and the simplifications
  the engine makes on purpose are in [docs/rules-coverage.md](docs/rules-coverage.md).
  If a card behaves differently from paper Magic, that is a bug; if a mechanic is
  listed as absent, that is a feature request.
- New decisions with consequences get an ADR in [docs/adr/](docs/adr/).
