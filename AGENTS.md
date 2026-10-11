# Working in this repository

Commander Blitz is a Magic: The Gathering Commander engine with a browser client
and a Steam Deck build. The rules live in exactly one place: a human clicking a
card, a CPU scoring the board and a training policy sampling an index all call
the same `Game.apply(action)`, and the client simulates nothing. Read
[docs/architecture.md](docs/architecture.md) first; the "If you are here to…"
routes in [docs/README.md](docs/README.md) take you to the rest.

## Map

| Path | What lives there | Read |
|---|---|---|
| `src/commanderblitz/engine` | The rules: a pure, deterministic state machine. No I/O, no HTTP | [architecture.md](docs/architecture.md), [engine-rules.md](docs/engine-rules.md) |
| `src/commanderblitz/cards` | The card DSL, its loader, the catalog and the authoring pipeline | [card-dsl.md](docs/card-dsl.md), [card-authoring.md](docs/card-authoring.md) |
| `src/commanderblitz/ai` | The Gymnasium environment, the agents and the per-deck CPU strategies | [ai-training.md](docs/ai-training.md), [cpus/](docs/cpus/README.md) |
| `src/commanderblitz/server` | The FastAPI app the browser and the desktop shell talk to | [server.md](docs/server.md), [api.md](docs/api.md) |
| `frontend/` | The React client | [client.md](docs/client.md) |
| `desktop/` | The Electron shell for the Steam Deck build | [desktop/README.md](desktop/README.md), [steamdeck.md](docs/steamdeck.md) |
| `data/` | Card definitions, decks, the catalog, art, authoring state | [data/README.md](data/README.md) |
| `tests/` | Unit, per-card, AI and server suites | [testing.md](docs/testing.md) |
| `scripts/` | The gate and every tool | [scripts.md](docs/scripts.md) |
| `.github/` | CI and CD | [ci-cd.md](docs/ci-cd.md) |
| `terraform/` | The droplet, applied by hand | [deployment.md](docs/deployment.md) |
| `.agents/skills/` | The agent skills; `.claude/skills/` are symlinks into it | [.agents/README.md](.agents/README.md) |
| `runs/` | Training output, gitignored | [ai-training.md](docs/ai-training.md) |

## Set up

Python 3.13 and Node 20+. [CONTRIBUTING.md](CONTRIBUTING.md) has the commands.
One step is easy to miss on Windows:

**Skills are symlinks.** The four skills live in `.agents/skills/`, which Cursor
reads directly. Claude Code reads `.claude/skills/`, so each entry there is a
symlink to its `.agents/skills/` twin. Git on macOS and Linux checks those out as
links with nothing to do. Git for Windows checks a symlink out as a plain text
file unless two things are true: the account may create symlinks (turn on
Developer Mode under Settings → For developers, or use an elevated shell) and
`core.symlinks` is on. Before cloning, or on an existing clone:

```bash
git config --global core.symlinks true      # or without --global, in this repo
git rm -r --cached .claude/skills && git checkout -- .claude/skills   # existing clone
git ls-files -s .claude/skills              # every entry shows mode 120000
```

Then Claude Code lists `/author-cards`, `/extend-dsl`, `/import-moxfield` and
`/create-pr`. Without the step, the links are text files and Claude Code sees no
skills; Cursor is unaffected.

## Conventions

- `python scripts/verify.py` before a pull request. It is the whole of CI, run
  locally ([testing.md](docs/testing.md)).
- Branch from a fresh `main`. One pull request per piece of work, with phased
  commits if it is big; a full gate costs runner-hours, so one PR that goes green
  beats three.
- The pull request title is a conventional commit and its type decides whether
  the merge deploys the site and releases to the Deck
  ([ci-cd.md](docs/ci-cd.md)). `/create-pr` writes the title and body the way CI
  checks them.
- Python is linted by `ruff check`; the repository is deliberately not
  `ruff format` clean, so never reformat a file you did not otherwise change.
- The frontend is linted by Biome, which fails on CRLF. Let git handle line
  endings rather than converting files by hand.
- Dependencies are pinned in `constraints.txt`, rewritten by
  `scripts/lock_deps.py`, never by hand.
- A decision with consequences a later change could reverse by accident gets an
  ADR in [docs/adr/](docs/adr/).

## Docs you must not hand-edit

| File | Regenerate with | Held by |
|---|---|---|
| `docs/unsupported-cards.md` | `python scripts/report_gaps.py` | the gap records in `data/authoring/gaps/` |
| `docs/card-dsl-reference.md` | `python scripts/gen_dsl_reference.py --write` | `tests/cards/test_dsl_reference.py` and the engine's registries |
| `docs/keywords.md` census tables | edit together with `engine/enums.py` | `tests/cards/test_keyword_census.py` |

## Which doc to touch

| Change | Update |
|---|---|
| A new op, cost, keyword, continuous effect or decision kind | the generator's curated map, then `docs/card-dsl.md` (concept) or `docs/card-dsl-cookbook.md` (worked mechanic), and the one-line row in `docs/rules-coverage.md` |
| A deck promoted or changed | `docs/decks.md` if the rules change; its page under `docs/cpus/` |
| A CI or release change | `docs/ci-cd.md`; `docs/deployment.md` only for operating the site |
| A client pattern | `docs/client.md`; a floor or budget is also an ADR |
| A server or lobby change | `docs/server.md`; the endpoint table in `docs/api.md` |
| A rules decision | an ADR; the matching row in `docs/rules-coverage.md` |

## How the docs are written

1. No counts, dates or measurements in a guide. A number appears only when it is
   a rule, and then it is named by where the code holds it.
2. Rules over examples, examples over history. A fixed bug is a test, not a
   paragraph. A war story becomes one rule or is deleted.
3. Symbols, not line numbers.
4. One owner per fact; everyone else links.
5. Generated or test-enforced docs say so at the top.
6. History is git. Nothing in `docs/` is a changelog; the why of a change is its
   commit message, and a decision with consequences is an ADR.
