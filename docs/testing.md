# How this is verified

```bash
python scripts/verify.py        # everything, in order, exits non-zero on failure
```

This page is the strategy: which kind of test owns which kind of question, and
why each gate exists. It names files and rules, never counts or results, so that
nothing here has to be re-measured when the code moves. How CI slices the gate
across runners is in [ci-cd.md](ci-cd.md).

## One gate

`scripts/verify.py` is both the local "is it done?" check and the whole of CI.
It runs every stage in dependency order and stops at the first failure, so the
first thing it prints about a broken build is the thing that broke. The stages
are grouped as `lint`, `pytest`, `sim`, `frontend` and `e2e`, and CI runs one
group per runner with `--only`; a developer runs the lot.

The flags each buy one thing:

| Flag | What it buys |
|---|---|
| `--quick` | Skips the stages that play whole games (the arena, every precon through a game) and the Storybook build. The live-server stage still runs |
| `--coverage` | Holds the coverage floors. Python's floor is held **once**, over all four suites appended into one data file, which is why `pyproject.toml` has no `fail_under`: no single suite reaches it alone. The frontend runs every vitest project in one process so jsdom and both browser story projects merge into one report |
| `--e2e` | The Playwright projects, each as its own stage, after the stories. Off by default because it costs tens of minutes |
| `--jobs N` | pytest under xdist (`--dist loadfile`, so a file's tests stay together) and the arena across processes |
| `--only G` | One stage group. An unknown group is an argparse error, and a slice that selects no stages fails rather than reporting success |
| `--strict` | A stage that would skip itself (no `node_modules`, no npm or bun, no Chromium) fails instead. Right on a fresh clone, wrong on a runner, and CI passes it everywhere |

Three failure rules are deliberate and worth knowing before touching the script:

- **A skip is not a pass.** Under `--strict` every self-skip is a failure, because
  one silent job among many is exactly what nobody notices.
- **A Playwright stage must prove it ran.** It fails if no JSON report appears or
  if the report describes zero tests, whatever Playwright's exit code was. A
  stage once launched `npx` with no arguments, exited zero in a fraction of a
  second, and passed every project on every run without executing a test.
- **Timed out and failed are different verdicts.** The e2e stage reads the report
  and prints failures sorted into *timed out* (a budget, or a busy machine) and
  *failed an assertion* (reproducible; a bug), plus anything marked
  `test.fail()` as a known open finding. That separation used to cost extra runs
  by hand.

The script refuses an interpreter older than `requires-python` in `pyproject.toml`
rather than failing somewhere confusing later.

## The layers, by what each can see

Every suite answers one kind of question, and the split is by what the test can
*observe*. That is the only line worth drawing.

```
tests/unit/**            the rules, one package per mechanic      Python, ms
tests/cards/             the card pool and the authoring gates    Python
tests/ai/                the action space, the agents, the arena   Python
tests/server/            the HTTP contract and the lobby          Python
frontend/tests/*.test.ts     pure logic, no DOM                   ms
frontend/tests/*.test.tsx    DOM contract, no layout, no providers ms
frontend/src/**/*.stories.tsx  real browser + real CSS, no backend seconds
frontend/e2e/*.spec.ts       real browser + real uvicorn          minutes
desktop/test/                the Steam Deck shell's pure modules   Node, no Electron
desktop/steam/test/install.test.sh   the installer against a stub Steam   bash
```

**Python.** `tests/unit/` is one package per mechanic (`combat/`, `triggers/`,
`zones/` and the rest); a new test goes beside its nearest neighbours. Shared
helpers (`settle`, `two_seat_board`, `find_action`, `pass_until` and their
siblings) live in `tests/conftest.py`; import them rather than copying one.
`GameBuilder` itself lives in `commanderblitz.engine.sandbox`, because the
authoring verifier uses the same harness.

`tests/cards/` holds the pool to its claims, in several distinct ways:

- *Pool validity*: every card file loads, every deck is legal and carries its
  metadata.
- *The six authoring gates* (`cards/authoring/verify.py`): schema, compile,
  residual, playable, behaviour, registry. `test_auto_cards.py` re-runs them over
  the pipeline's output and `test_hand_written_cards.py` over the hand-written
  files, with an xfail list in `precon_deficits.json` that may only shrink.
- *Every card works* (`test_every_card_works.py`): parametrised over the whole
  registry; each card is cast in a sandbox rich enough to satisfy its targets,
  every decision it asks for is answered, and it must end in the right zone.
  Cards with a deterministic outcome also carry an expectation (Thragtusk leaves
  you on a known life total) in `expectations.json` beside the hand-written
  cards and in `data/cards/auto/expectations.json` beside the generated ones.
- *The golden pool*: a hash of the compiled pool and its vocabulary, re-pinned
  with `COMMANDERBLITZ_UPDATE_GOLDEN=1` when a change to it is intended.
- *Import pins* (`test_<deck>_import.py`): a pasted Moxfield-style list run
  through `importer.import_deck` as a dry run, asserting every card resolves
  `native`. One per shipped deck; this is the guarantee behind "paste a link".
- *Per-deck behaviour files* (`test_<deck>_deck*.py`): what the sandbox gate
  cannot reach, such as activated abilities and triggers that never fire in a
  one-cast sandbox.
- *Docs held to code*: `test_keyword_census.py` holds [keywords.md](keywords.md)
  to the engine's enums and `test_dsl_reference.py` holds
  [card-dsl-reference.md](card-dsl-reference.md) to the registries, which is why
  CI treats an edit to either file as a code change.
- *The two layers*: generated content stays out of the authored layer
  (`test_two_layer_registry.py`), and runtime writes land where the deploy volume
  expects them (`test_generated_dir.py`).

`tests/ai/` holds the environment, the action space, the agents and the trainer;
`tests/ai/strategy/` holds the baseline, the archetypes and one file per deck
strategy, plus the slow whole-game run every precon makes. `tests/server/` holds
the API end to end, the lobby, the multiplayer game, races, reconnects, art,
client serving and the desktop entry point.

**Frontend.** jsdom is structurally blind to most of how this UI works: no
`ResizeObserver`, no resolved custom properties, no layout. So the rule is:

> A `tests/*.test.tsx` file owns anything provable without layout: text, `data-*`
> attributes, the action-id invariant, callback wiring. A story owns anything
> needing the real cascade, real box geometry, or a gesture spanning components.

Duplicate coverage on a component is deliberate where it exists: the jsdom test is
the fast guard, the story is the honest one. Components render bare; a test
mounts a provider only when the provider *is* the thing under test (a deep link
needs a router, a long-poll hook needs a query client), and such a test's `fetch`
stub answers each endpoint once and then blocks, because a poll that re-issues
the instant one lands would otherwise spin the loop.

Stories run in a real Chromium under Vitest's browser mode as **three projects**:
the desktop one, `storybook-handheld` running the stories tagged `handheld`, and
`storybook-phone` running the stories tagged `phone`. A story's `viewport` global
names a screen from `src/testing/devices.ts` and the Vitest addon sizes the page
to it, so a phone story is laid out at the phone's real size with the phone query
matching; `.storybook/preview.tsx` stamps that screen's `data-layout`. A story
with no viewport runs on the addon's own canvas and is stamped `desktop`, which
the sheets and `state/useHandheld.ts` believe over the media query.
Mounts are mandatory and a layer may not state a size (`src/testing/mounts.tsx`,
`appGeometry.ts`); motion runs twice, once reduced under test and once real.

And the symmetrical warning: **do not port `e2e/` into stories.** A spec asserts
against a real engine's legal-action list; a story asserts against a fixture and
can only prove the client renders what it is given. Different questions, both
worth asking.

**Playwright** runs as five projects (`playwright.config.ts` and, for the desktop
build, `playwright.sidecar.config.ts`):

| Project | What it proves |
|---|---|
| `chromium` | The desktop board: the critical player path, a full game clicked to the end, the action panel's contract, art self-ownership, legibility, layout, stacking, routing, deck import, a two-browser pod |
| `handheld` | The Steam Deck panel: the floors at every reachable state, the synthetic gamepad, the press budgets against a real engine |
| `phone` | Every phone `testing/devices.ts` names, held both ways, by tap: the phone's floors and budgets, no sideways scroll, every stop reachable by tap, every decision answerable from the sheet, the tap budgets and a whole game per device |
| `deckfit` | Nothing scrolls at the handheld sizes |
| `sidecar` | The desktop build's own server serving the built client, with every request off the machine aborted; its hosted origin is `tests/server/stub_site.py`, switched off except while a deck is imported through it |

`chromium` ignores the handheld and phone specs, and `handheld` and `phone` match
only their own. `phone` is `fullyParallel` so its one spec shards by test. Running
the compact specs at the desktop size would test the wide layout while claiming
to test the other one. `workers` stays at 1: the app's motion is frame-driven, so
a second worker on the same box produces timeouts rather than speed. Sharding
across *boxes* is the parallelism the suite tolerates; see
[ci-cd.md](ci-cd.md).

**Desktop.** Everything under `desktop/src/` that decides something takes its
process, filesystem and network as arguments, and `desktop/test/` hands it fakes
(`helpers.ts`); there is no module-level mocking. The Electron wiring is thin and
is covered by the packaged AppImage's `--smoke` boot at release time. The
installer runs against a stub Steam in a scratch home, in the gate and again in
the release.

## The gates that matter, and why each exists

**Every card works.** Described above. It is what turns "the decks are curated so
every card works" from an intention into a fact.

**The action mask cannot lie.** A wrong mask poisons training silently, so
`tests/ai/test_action_space.py` walks real games and asserts at every decision:
every index decodes to an action the engine considers legal, encoding round-trips,
the mask is never empty while the game runs, and nothing vanishes between the
legal list and the table.

**The heuristic beats random.** A seeded run of duels in `tests/ai/test_agents.py`
requires the heuristic to win by a clear margin. It is a rules canary: if a
change quietly breaks combat or mana, the heuristic stops converting its
advantage and this notices first. `verify.py` gates on the heuristic and never
on the trained policy, because the heuristic is what the app plays against and
what a regression would break first.

**Hidden information stays hidden.** Server tests assert that other players'
hands come back empty, that no library is ever listed, and that `/debug` really
does reveal what the player view hides. Multiplayer has two siblings of the same
shape: a lobby test holds that another player's deck is invisible until they
lock in and that no view carries a token or another player's id; an event-log
test holds that a draw by another seat carries no object id but the event itself
is still there, because a client that silently received a shorter list than its
neighbour could not tell that from a bug.

**Two people doing the same thing at once.** Every handler is a sync `def`, so
Starlette runs it in a thread pool and two guests claiming the last chair are
genuinely concurrent. `tests/server/test_pod_races.py` fires N requests from N
threads and asserts on the *set* of outcomes. Every `.result()` carries a
timeout, because a deadlock is the failure this file exists to catch and a hung
test that never reports is not a caught deadlock.

**Geometry is measured, not looked at.** A claim about pixels is asserted as a
relationship: the lobby's row of cards share width, height and top; a panel must
not scroll sideways *and* its prose column must clear its floor, because the
overflow check alone passes if the panel merely clips. Half-assertions are how
layout bugs get through. The rule for changing a measured number is
[ADR 0014](adr/0014-measured-numbers-invariant-relationships.md): geometry may
move, invariants may not.

**The floors are gated twice, per mode.** The floors ([ADR 0013](adr/0013-handheld-floors-are-ci-gates.md),
a row per compact mode in `src/logic/floors.ts` since [ADR 0025](adr/0025-phone-is-a-layout-mode-touch-an-input-mode.md))
are asserted by the handheld and phone story projects over every story's states,
and by `e2e/handheldAssert.ts` in the `handheld` and `phone` Playwright projects at
every reachable state of a real game, each handed its layout's `GateSpec`. The story project reaches states the e2e suite never does
(an empty hand, for one); the e2e gate reaches states a fixture cannot honestly
stand in for. Three things about that gate cost a confusing loop each to learn:

- *It walks clipping ancestors.* An element's own box is reported even when an
  ancestor has clipped it to nothing, and the handheld layout clips an opponent's
  lanes deliberately so their cards stay in the document for the effects layer to
  anchor to.
- *It waits for animations, but only finite ones.* A dialog scaling in fails the
  hit floor mid-animation; the ring's sheen loops forever and waiting on it never
  returns.
- *It only demands a ring where a ring exists.* A mouse player has none by design.

**A gate and the thing it grades must not share a helper by accident.** The seat
summary is re-derived by the gate from a different source than the component
uses, so two derivations that agreed by construction cannot hide a wrong count.
When the navigation's reachability check and the gate's shared a function, a
stop the ring could reach and nobody could see hid for exactly that reason. If
they *can* share a helper, share it; if they cannot, expect them to drift and
test for it.

**Card art has its own gates**, because its failures are all silent. The set of
cards with no printing is asserted empty (`tests/cards/test_image_resolution.py`),
and that emptiness is the claim: an entry appearing means a real card stopped
resolving and started rendering a blank plate. The text scrims are checked both
as a stylesheet parse (`frontend/tests/palette.test.ts`) and against the rendered
board (`e2e/legibility.spec.ts`), where an override would show. And
`e2e/art.spec.ts` fails if the page fetches from any host but this server, which
is the property the whole build-time download exists to buy
([ADR 0012](adr/0012-art-fetched-once-served-locally.md)).

**Press budgets** are a fifth kind of question. Every gate above answers something
about a *state*; none can answer how long a decision takes on a controller, which
is the property a player feels. `src/testing/journey.ts` walks a journey and
returns what it cost; `Journeys.stories.tsx` holds a budget per journey in CI, and
`e2e/journeys-handheld.spec.ts` holds the same journeys against a real engine;
the audit's touch column, `TAP_BUDGET`, holds the journeys `e2e/phone.spec.ts`
walks by tap, never above the press ceiling.
The budgets live once, in `src/components/game/decisionAudit.ts`, the table of
every decision kind and purpose the engine can raise against the surface that
answers it ([client.md](client.md#surfaces-and-their-rules)); a story is held to
the ceiling under its own name, `tests/unit/choices/test_decision_audit.py` holds
the table to the engine's `DecisionKind` and purpose tags, and
`tests/decisionAudit.test.ts` holds every ceiling to a story that measures it.
Budgets are ceilings, never exact counts: an exact count fails on an improvement.
A journey whose follow-up depends on a new action list from the server is e2e or
it is nothing, because a fixture never produces one. Two things have to be right
before a synthetic press means anything: the pad dispatches on the *next* frame,
so a press asserted immediately is asserted against a board that has not heard
it; and the cursor hook is mounted by the screen, not the board, so a story
rendering the table alone presses at nothing.

## Determinism

Every shuffle and random choice routes through `state.rng`, and a test scans the
source to keep it that way. That is what lets two games with the same seed
produce byte-identical event logs and an arena run repeat exactly.

A seed only replays the game it was written against if the decks and the CPU are
the same too. So the seeded Playwright specs run against a server started with
two variables, which `playwright.config.ts` and `verify.py` set for the servers
they boot:

| Variable | Effect |
|---|---|
| `COMMANDERBLITZ_FIXTURE_DECKS=1` | Serves the retired fixture lists under their old ids and pins the CPU deck order ([decks.md](decks.md)) |
| `COMMANDERBLITZ_CPU=classic` | Every `heuristic` seat plays the pre-strategy agent ([cpus/](cpus/README.md)) |

A dev server you let Playwright reuse needs both, or the specs deal different
games; `/health` lists the deck ids, so a fixture id missing from it is the tell.
Python tests need neither: `default_registry()` always carries the fixtures.

## The test harness

`GameBuilder` puts the game into an exact position so a rules test can assert one
thing without playing ten turns first:

```python
game = (GameBuilder(registry, players=2, seed=7)
        .hand(0, ["t_counterspell", "island", "island"])
        .battlefield(0, ["island", "island"])
        .battlefield(1, ["t_bear"])
        .library(1, ["swords_to_plowshares"])   # exact top of library
        .life(1, 3)
        .build())
```

`build(advance=False)` freezes the position exactly as described. That option
exists because of a real trap: the engine **auto-passes** when a player's only
legal action is to pass, so `build()` on a quiet board can roll several turns
forward before returning. Assertions about the position need the frozen form;
assertions about play need the advanced one.

## Coverage is a ratchet

Floors, not targets. The Python floor is one number in `scripts/verify.py`, held
over all suites together. The frontend's floors in `vite.config.ts` are per file
and only ever raised; `include: ["src/**"]` there is load-bearing, because
without it the provider instruments the Storybook build beside `src/` and the
total collapses. `COVERAGE_FLOORS=off` exists for a machine without Chromium,
where the story projects cannot run and the floors would be meaningless.

## Running pieces

```bash
pytest tests/unit -q                      # fast: the rules
pytest tests/unit/combat -q               # one mechanic's slice of them
pytest tests/cards -q                     # the pool and its gates
pytest -m "not slow" -q                   # skip the whole-game and training runs
python scripts/validate_decks.py
python scripts/run_arena.py --games 200 --pods 2,4 --max-draw-rate 0.2
python scripts/smoke_http.py --players 4        # against a running server
python scripts/smoke_http.py --pod --players 2 # the lobby, end to end, with tokens
cd frontend && npm test && npm run build && npm run lint
cd frontend && npx playwright install chromium   # one time, for stories and e2e
cd frontend && npm run test:stories && npm run test:stories:handheld && npm run test:stories:phone
cd frontend && npx playwright test --project=chromium
cd desktop && npm test
```
