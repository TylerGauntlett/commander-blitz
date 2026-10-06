# How this is verified

```bash
python scripts/verify.py        # everything, in order, exits non-zero on failure
```

## The suites

| Suite | Count | What it holds |
|---|---|---|
| `tests/unit/` | 8055 | Mana, zones, casting, the stack, priority, turn structure, combat, keywords, triggers, static abilities, state-based actions, the commander rules, multiplayer |
| `tests/cards/` | 14342 | Schema and vocabulary validation, deck legality and metadata, the every-card gate, and the card index + art resolution |
| `tests/ai/` | 80 | Action-space correctness, the environment, agents, the arena, the model and trainer |
| `tests/server/` | 352 | The HTTP API end to end: hidden information, image serving, the catalog, the whole lobby, and serving the built client |
| `frontend/tests/` | 1522 | The client's pure logic modules, the input layer, the palette ladders, the card face, the lobby, and the routes |
| `frontend/src/**/*.stories.tsx` | 405 + 52 | Storybook, in a real Chromium: every component's states, and the geometry jsdom cannot see. **Two projects** — see below |
| `frontend/e2e/` | 159 | Playwright: full games, combat, stacking, card art, legibility, layout, deep links, and a two-browser pod |

The Count column is what the runner *collects* -- parametrised cases included, so
`tests/cards/` counts every card the every-card gate is parametrised over, of which
a few thousand skip on a per-card condition. It is written by
`python scripts/test_counts.py --write` and checked by `--check`; `verify.py` prints
the check's verdict as a line rather than a stage, because a stale number is a
documentation bug, not a build break.

`tests/unit/` is split by mechanic, one package per area: `attachments/`,
`casting/`, `choices/`, `combat/`, `commander/`, `copies/`, `costs/`, `counters/`,
`damage/`, `effects/`, `engine/`, `faces/`, `keywords/`, `ledger/` (what happened
this turn), `mana/`, `modes/`, `named_cards/`, `planeswalkers/`, `players/`,
`protection/`, `replacement/`, `statics/`, `targets/`, `tokens/`, `triggers/`,
`turn/`, `values/` and `zones/`. A new test goes beside its nearest neighbours.
Helpers more than one file needs -- `settle`, `two_seat_board`, `activations`,
`pt`, `pass_until`, `find_action` and the rest -- live in `tests/conftest.py`;
import them rather than copying one in.

`scripts/verify.py` runs up to 15 stages in dependency order and stops at the first failure:
lint, deck validation, **is the committed card index current**, each Python suite, a
120-game arena (60 duels and 60 four-player pods), **a real uvicorn process playing full games at 2 players, 4 players and
one pod driven entirely through the lobby**, then the frontend build, lint and tests,
the Storybook build, and the story interaction tests **twice** — once at the desktop
canvas and once at a Steam Deck's.

> **The handheld story project is the only place the floors are gated by CI.**
> 16px of type, 44px of target and 96px of card have been asserted by
> `e2e/handheldAssert.ts` since Loop 3 — and Playwright is not run here, so
> nothing ever stopped a change putting a label back under the floor. It found
> `.hand__empty` at 14px the first time it ran: one selector missing from an
> alphabetical list of eighty, in a state the e2e suite never reaches because it
> never has an empty hand.

> **The tester canvas is 1200x900 whatever the project declares.** Storybook's
> Vitest addon sizes the iframe per story and wins: `browser.viewport`,
> `instances[].viewport`, a `--window-size` launch arg and a `page.viewport()`
> call from `beforeEach` were each measured and each reset before the play
> function ran. That was harmless until something branched on the viewport —
> `HANDHELD_QUERY` is `(max-width: 1366px)`, so at 1200 **every story matched
> it**, and the first component to render a different NODE on that query rendered
> its compact body in the project whose job is the desktop one. So the layout is
> decided by the toolbar rather than by the canvas: `preview.tsx` stamps
> `data-desktop` or `data-handheld`, and both `styles/handheld.css` and
> `state/useHandheld.ts` treat an explicit choice as beating the query.

### The two opt-in flags

```bash
python scripts/verify.py --coverage   # every suite under coverage, one floor each side
python scripts/verify.py --e2e        # the three Playwright projects, after the stories
```

Both are off by default because each costs tens of minutes, and both run on every
pull request — split across runners rather than in one job. See **How CI slices
this** below.

`--coverage` appends the four Python suites into one data file and holds the floor
**once**, at the end, over all of them — no single suite can reach it alone, which is
why there is no `fail_under` in `pyproject.toml`. On the frontend it runs every vitest
project in one process (`npm run test:coverage`), so the jsdom run and both Chromium
story runs merge into one report and one set of floors in `vite.config.ts`. The
`include: ["src/**"]` there is load-bearing: without it the provider instruments
`storybook-static/` beside `src/` and the total reads 7%.

`--e2e` runs `chromium`, `handheld` and `deckfit` as three stages with `E2E_SLOW=2`,
which doubles every budget in the suite because it runs after two Storybook browsers
on the same machine. It then reads Playwright's JSON report and prints the failures
sorted into **timed out** (a budget or a busy machine) and **failed an assertion**
(reproducible; a bug) — the separation that used to take four extra runs by hand —
plus any case marked `test.fail()` for a known open finding. A stage that produces no
JSON report **fails**, whatever Playwright's exit code was: until 2026-09-06 the stage
launched `npx` through `sh -c` with a list, which on Linux ran `npx` alone, exited zero
in 0.3 s, and passed all three projects on every CI run without executing a test. The
stage also hands its own interpreter to `playwright.config.ts` as `PYTHON`, because CI
has no `.venv` for the config's default path to find.

Playwright's own suite can still be invoked directly (`cd frontend && npx playwright test`).

### How CI slices this

The gate is one script and nine jobs. `.github/workflows/deploy.yml` runs
`verify.py` once per runner with `--only`, and a final `gate` job is the single
check that says whether all of it passed:

| job | slice | why it is its own runner |
|---|---|---|
| `lint` | `--only lint` | ~2 minutes in front of everything, so a superseded pull request wastes one runner and not nine — `cancel-in-progress` bills what was running |
| `python` | `--only pytest --coverage --jobs 2` | the four suites and the 92% floor, under xdist |
| `sim` | `--only sim` | the arena and the live server; no Node on the box at all |
| `frontend` | `--only frontend --coverage` | build, lint, and the one vitest process that merges jsdom with both story projects |
| `e2e` | `--only e2e --e2e-project P --e2e-shard i/n` | seven legs: chromium sharded five ways, plus handheld and deckfit |

**Sharding is the only parallelism this suite tolerates.** `workers` stays at 1 in
`playwright.config.ts` because the app's motion is frame-driven and the runner
draws ~11 fps under tracing, so a second worker on the same box produces timeouts
rather than speed. `--shard` partitions the test list *before* the run, so a
second *box* costs nothing: each leg boots its own uvicorn and vite, and the
server holds games in process memory, so there is no state to share.

**The e2e reports are per shard.** `--e2e-shard 2/4` writes
`frontend/test-results/e2e-chromium-2of4.json`, because a shard whose report
landed on a sibling's would have the verdict read for the wrong run. The stage
also counts the tests in that report and fails a slice that ran none: `--shard=5/4`
writes a valid report describing zero tests and exits 0, which the older
"did a report appear?" check would have passed. Summing the four chromium shards
is therefore the check worth making after touching any of this — they must add up
to the whole project.

Every job passes `--strict`, which turns the three self-skips (no npm/bun, no
`node_modules`, no Chromium) into failures. A skip that exits zero is right on a
fresh clone and wrong on a runner, and one silent job out of nine is exactly what
nobody notices.

Two things about this are known and deliberately left alone:

- **Shards are balanced by test count, not duration**, and Playwright keeps a
  file's tests together, so the big specs (`pod`, `cycle3`, `action-panel`) make
  the split lumpy. `--shard=i/4` left one leg carrying 42 of the 125 chromium
  tests — the same long pole `i/3` leaves, so the fourth runner bought nothing.
  Five legs put the longest at 31. Re-measure with
  `npx playwright test --project=chromium --shard=i/n --list` after adding specs;
  it costs nothing, because `--list` runs no tests.
- **`E2E_SLOW=2` is now headroom rather than necessity.** It doubles every budget
  because the suite used to run after two Storybook browsers on the same box; on a
  dedicated runner it no longer does. Lowering it is a separate change, made and
  observed on its own — FT-06's timeout class is not something to debug alongside
  a CI restructure.

It runs as **two projects at two viewports**, and the split is the safety
argument for the handheld work rather than a convenience:

```bash
npx playwright test --project=chromium   # 1600x950 -- the desktop board
npx playwright test --project=handheld   # 1280x800 -- a Steam Deck's panel
```

`chromium` ignores the handheld specs and `handheld` matches only them. Running
the compact specs at 1600x950 would test the wide layout while claiming to test
the other one.

### Re-taking a desktop baseline

The desktop project's numbers used to be "what proves the wide board is
unchanged, and they may never move". The full-height rail moved them
deliberately — the foot is inside the board's column now at every size — so the
rule needs restating rather than quoting:

> A change may move desktop **geometry**. It may not move desktop
> **invariants**. Every assertion that encodes a RELATIONSHIP — nothing under
> the foot, no panel flattens, action ids are unique, the bands run creatures →
> globals → lands, the dial overlaps the portrait — stays byte-identical and
> **must still pass**. Every assertion that is a bare NUMBER is re-taken once,
> in one commit, with the old value, the new value and a one-line reason in the
> diff. **A failing relationship assertion is a regression, not a baseline.**

Two chromium assertions were rewritten rather than re-taken, because the surface
they measured stopped existing: `acceptance.spec.ts`'s two life dials (an
opponent's life is a gauge on their seat now, not a dial) and `orb.spec.ts`'s
opponent pile row (a seat's zones are 20px marks, because a seat can spare one
row of a 96px budget and a 44px pile target does not fit in it).

The handheld project runs `e2e/handheld.spec.ts`, which asserts
`e2e/handheldAssert.ts` at every reachable state: **16px** on anything carrying
information, **96px** on any card the ring can land on, **44px** on any control,
a ring at least 3px *and not `outline-style: none`*, at most one cursor, zero
unreachable stops and zero `title` tooltips. Duplicate `data-testid`s are
counted and reported but deliberately not failed -- scoping a query to its
container, as `e2e/pod.spec.ts` does, makes a shared id on a repeated component
correct.

Three things about that gate are worth knowing before changing it, because each
one cost a confusing loop to find:

- **It walks clipping ancestors.** `getBoundingClientRect` reports an element's
  own box even when an ancestor has clipped it to nothing, and the handheld
  layout clips an opponent's lanes to `height: 0` deliberately — their cards
  must stay in the document for `FxLayer` to anchor to. Without the walk it
  reported 22 cards under the floor that nobody can see.
- **It waits for animations, but only finite ones.** Dialogs animate in from
  `scale: 0.96` and the scaled box fails the hit floor; the ring's sheen loops
  forever and waiting on it never returns.
- **It only demands a ring where a ring exists.** A mouse player has none by
  design.

`e2e/pad.spec.ts` drives a synthetic gamepad — Playwright cannot produce a real
one, so `navigator.getGamepads` is overridden through `addInitScript` and a
`gamepadconnected` event is dispatched.

Two of its cases exist because a synthetic pad is *too well behaved*, and both
were failures a real controller met on a desktop while the whole suite passed:
"a controller plugged in later" (a real pad is invisible until its first
gesture, so it is never there on the first frame) and "a second gamepad in front
of the real one" (`getGamepads()` is indexed by slot, and on Windows slot zero is
routinely a device nobody is touching).

`tests/pad.test.ts` covers the polling loop itself in jsdom — multiple pads, a
non-standard HID layout with its d-pad on a hat axis, analog triggers whose
driver never sets `pressed`, and a loop recovering after rAF stopped running.
It exists because the controller work was play-tested entirely through the
keyboard fallback, which shares everything *below* the button map and therefore
exercises none of the code that reads an actual gamepad.

## Where the four frontend suites divide

They split by what they can *see*, which is the only line worth drawing:

```
tests/*.test.ts     pure logic, no DOM                      ms
tests/*.test.tsx    DOM contract, no layout, no providers   ms
*.stories.tsx       real browser + real CSS, no backend     seconds
e2e/*.spec.ts       real browser + real uvicorn             minutes
```

jsdom is structurally blind to most of how this UI works, and the source says so:
`useZoomFit.ts` notes that "jsdom has no `ResizeObserver` at all", `useCardBase.ts`
that "jsdom returns `""` for a custom property it never resolved". The `@property`
registrations in `theme.css` exist precisely so a real engine resolves `--card-w`
to pixels. So `CombatArrows`, `HandFan`'s slot arithmetic, `CardStack`'s fan and
`FxLayer`'s anchors had no coverage at all between "a unit test that cannot see
them" and "an e2e run that needs a Python process".

**The rule.** A `tests/*.test.tsx` file owns anything provable without layout: text,
`data-*` attributes, the action-id invariant, callback wiring. A story owns anything
needing the real cascade, real box geometry, or a gesture spanning components.
Duplicate coverage on `ActionPanel` and `CardFace` is deliberate — the jsdom test is
the fast guard, the story is the honest one.

**"No providers" has exactly one exception**, and it is a narrow one. `routing.test.tsx`
mounts `<App/>` under a `MemoryRouter` and a `QueryClientProvider` through the
`renderApp` helper, because a deep link is not observable any other way. Every
*component* still renders bare, and stays able to: nothing under `components/` imports
react-router. Route wiring lives in `screens/`, which is what that file tests.

Its `fetch` stub answers each endpoint once and then blocks forever. That is not a
shortcut — the pod and the game are read by long polls that re-issue the instant one
lands, so a stub that answered every time spins the loop as fast as the event loop
allows. A poll that hangs is exactly a poll waiting for news.

And the symmetrical warning: **do not port `e2e/` into stories.** Those assert against
a real engine's legal-action list; a story asserts against a fixture and can only
prove the client renders what it is given. Different questions, both worth asking.

Stories need a browser binary that `npm install` does not fetch:

```bash
cd frontend && npx playwright install chromium   # one time
npm run storybook       # the browsable version, port 6006
npm run test:stories    # the same stories as tests
npm run test:all        # both vitest projects
```

`verify.py` skips the story stage with a message when that binary is absent, the same
way the whole frontend is skipped without `node_modules`. The Storybook *build* stage
needs no browser and always runs.

## Press budgets, which are a fifth kind of question

Every gate above answers something about a *state*: is this a stop, is it big
enough, is it on screen, does it hold its own action id. None of them can answer
how long a decision takes, and on a controller that is the property a player
actually feels — `docs/handheld-playtest.md` Loop 1 put it as "reachable and
reachable-in-under-a-second are different properties, and only the second is
playable". A journey that grew from two presses to nine would have passed every
check in this document.

```
src/testing/journey.ts                 walk a journey, return what it cost
Journeys.stories.tsx                   a budget per journey, 1280x800, in CI
e2e/journeys-handheld.spec.ts          the same journeys, against a real engine
```

**Budgets are ceilings, never exact counts.** `toBeLessThanOrEqual`, always: an
exact count fails on an improvement, which is the wrong direction to be strict
in, while a ceiling fails only when a journey gets worse.

**The split is about what a fixture can honestly stand in for.** The combat
shortcuts and the targeting follow-up stage into `uiStore` and are true the
moment the gesture is made, so a scenario is a faithful board and the story
belongs in CI. Playing a card is a mutation — the follow-up waits for the new
action list on purpose, and `fakeGame` never produces one — and the lobby is
five screens with a pod created over HTTP. Those two are e2e or they are
nothing.

Two things have to be right before a synthetic press means anything, and both
were wrong in the first draft:

- **`pad.ts` dispatches on the next frame.** A key goes into a latch and `wake()`
  starts the loop; the intent arrives inside the following `requestAnimationFrame`
  and the ring moves in the layout effect after the commit that follows. A press
  asserted immediately is asserted against a board that has not heard it, and a
  second press in the same frame lands on a ring that has not moved — which
  quietly makes a journey cost whatever number the assertion was written with.
- **`useCursorNav` is mounted by `Screen`, not by the board.** A story rendering
  `Table` alone presses `A` at nothing at all, and every direction with it. The
  journey stories mount the hook the way the app does, which is also why
  `Table.stories.tsx` says `A` and the directions are `e2e/pad.spec.ts`'s to own.

## Card art has its own gates

Three of them, because the failure modes are all silent:

- **The token naming rule.** `tests/cards/test_image_resolution.py` freezes the set
  of cards with no printing at exactly five. A *sixth* means a real card stopped
  resolving and quietly started rendering a blank plate, which nothing else notices.
- **Text over an unknown illustration.** The card is a full-bleed picture with its
  text on graded scrims, so white type over somebody's bright crop is the thing that
  can fail on one card and look fine on every other.
  `frontend/tests/palette.test.ts` checks both scrims are gradients whose opaque ends
  clear a darkness floor; `frontend/e2e/legibility.spec.ts` checks the same against the
  *rendered* board, where an override from `theme.css` or a media query would show up
  and a stylesheet parse would not. (This replaces a type-ring luminance ladder, which
  encoded card type as colour — see `docs/design-record.md` (Open fidelity findings) for why it went.)
- **Self-ownership.** `e2e/art.spec.ts` fails if the page fetches from any host but
  this server. That is the property the whole build-time download exists to buy, and
  it would be easy to give away by accident.

## The gates that actually matter

**Every card works.** `tests/cards/test_every_card_works.py` is parametrized over all
128 shipped cards. For each one it builds a sandbox with a deep mana base and a board
rich enough to satisfy targets, takes the legal action the engine offers, drives every
decision the resolution asks for, and asserts the card ended in the right zone. Cards
with a deterministic outcome also have an entry in `expectations.json` — Thragtusk must
leave you on 45 life, Cultivate must put one land on the battlefield and one in hand,
Avenger of Zendikar must make exactly one Plant per land you control.

This is what turns "the decks are curated so every card works" from an intention into
a fact.

**The action mask cannot lie.** A wrong mask poisons training silently, so
`tests/ai/test_action_space.py` walks real games and asserts, at every decision point:
every index in the table decodes to an action the engine considers legal;
`encode(decode(i)) == i`; the mask is never empty while the game runs; and
`len(by_index) + len(dropped) == len(legal_actions)` so nothing vanishes unnoticed.

**The heuristic beats random.** `test_heuristic_beats_random` runs 60 seeded duels and
requires a 65% win rate. It is a genuine canary: if a rules change quietly breaks
combat or mana, the heuristic stops converting its advantage and this test notices
before anything else does.

**Hidden information stays hidden.** Three server tests assert that other players'
hands come back as `null`, that no library is ever listed, and — the deliberate
exception — that `/debug` really does reveal what the player view hides.

Multiplayer added two more surfaces with the same shape, and each got the same class of
test. `TestDeckSecrecy` (`tests/server/test_lobby.py`) holds the lobby's rule: another
player's deck is invisible until they lock in, and no view ever carries a token or
another player's id. `TestEventRedaction` (`tests/server/test_multiplayer_game.py`)
holds the event log's: a `draw` by another seat carries no object id, but the event
itself is still there, because a client that silently received a shorter list than its
neighbour could not tell that from a bug.

**Geometry, measured rather than looked at.** The lobby's row of four is a *hand*,
and that is a claim about pixels: `e2e/pod.spec.ts` asserts all four `.slot__card`
boxes share width, height and top, and that height over width is 1.4. It exists
because the first version shipped with four different heights — `.card--big`'s
"every enlarged card is the same size" is enforced by its container, and the lobby
supplied none. Width alone would have passed even then, which is exactly the kind of
half-assertion that lets a layout bug through. The dossier gets the same treatment:
its panel must not scroll sideways *and* its prose column must clear 300px, because
the overflow check alone would also pass if the panel merely clipped.

**Two people doing the same thing at once.** `tests/server/test_pod_races.py` is the
file that finds the mistakes in the rest. Every handler is a sync `def`, so Starlette
runs it in a thread pool and two guests claiming the last chair are genuinely
concurrent. Each test fires N requests at one pod from N threads and asserts on the
*set* of outcomes — four joins produce exactly one 201 and three 409s; two
simultaneous deals produce exactly one 200, one 409 and one `GameSession`; a guest
unlocking while the host deals never yields a game with an unready seat. Every
`.result()` carries a timeout, because a deadlock is the failure mode the file exists
to catch and a hung test that never reports is not a caught deadlock.

**A summary that cannot be checked against the thing it summarises.**
the seat round (`docs/design-record.md#seat`) names this as the failure mode its whole family of
components had: five of six directions could not be WRONG about the board,
because lands were never in the payload, so nothing could contradict them.
`OpponentSeat` is the shipped answer, so `handheldAssert`'s `seatsDisagree`
re-derives all five counts from a different source — the rendered `.perm` cells
against a walk over that seat's own lanes — and fails the board if any two
disagree. It cannot import `musterOf`: `page.evaluate` sends the gate's source
alone, which is exactly what makes the two derivations independent. Two that
agreed by construction would be a gate agreeing with itself.

It counts `data-stack-count` rather than boxes, because the board collapses
duplicates — seven Forests are one card with a x7 on it — and a gate that
counted nodes would report six missing lands on every developed board.

**A row that runs past its box in silence.** `fanOverflow` measures every
`[data-fan]` — the lanes and the hand — for horizontal overflow. The mockup
round hit it: six cards at 176px is 1056px in the 947 the foot had, the hand ran
79px past it onto the commit panel's first control, and `overflow: hidden` meant
the page reported no overflow anywhere. **The only symptom was a button that had
quietly stopped being clickable.** `unguttered` is its sibling: a styled
scrollbar is a classic bar rather than an overlay, so it takes its width the
instant it appears and re-wraps every line under it.

**A stop the ring can reach and nobody can see.** `candidatesIn` dropped only
zero-SIZED stops, and an opponent's lanes are `height: 0; overflow: hidden` so
their cards stay in the document for `FxLayer` — a clipped card still reports its
own full box. So the ring could land there, and no gate disagreed, because
`handheldAssert`'s `unreachable` calls that very function. The ancestor-clip walk
existed in the gate and not in the navigation, and **the two being different is
what let it hide**. If a gate and the thing it grades share a helper, share the
helper; if they cannot, expect them to drift.

## Determinism

Every shuffle and random choice routes through `state.rng`. That is what lets
`test_event_logs_match_for_identical_seeds` assert two games with the same seed produce
byte-identical event logs, and `test_results_are_reproducible` assert an arena run
repeats exactly.

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

`build(advance=False)` freezes the position exactly as described. That option exists
because of a real trap: the engine **auto-passes** when a player's only legal action is
to pass, so `build()` on a quiet board can roll several turns forward before returning.
Assertions about the position itself need the frozen form; assertions about play need
the advanced one.

## Current results

Measured on this machine, CPU only:

| Measurement | Result |
|---|---|
| Heuristic vs random, 60 duels | **~85%** win rate |
| Heuristic vs random, 24 four-player pods | heuristic ahead, ~8% draws |
| Random vs random, 60 duels | 100% decisive, median 24 turns |
| Four-player heuristic pods, 25 games | 100% decisive, median 33 turns |
| Duel length under the heuristic | median 16–20 turns |
| Trained policy vs random, 60 duels | **60%** (95% CI 47–71%) |
| Trained policy vs heuristic, 40 duels | **10%** (95% CI 4–23%) |

The policy figures come from a 120-update CPU run (~61k environment steps, 871
episodes). **It has learned something real** — 60% against random is well clear of the
50% a coin flip would give — **but it is nowhere near the heuristic.** That is the
expected shape at this budget: an 825-wide action space, 15–40 turn episodes and a
terminal-only reward need orders of magnitude more experience than a CPU run in the
background of a build.

So the trainer is a working pipeline with sensible defaults, not a finished strong
player. `scripts/verify.py` deliberately does **not** gate on policy strength; it gates
on the heuristic, which is what the app actually plays against and what a rules
regression would break first.

## Running pieces

```bash
pytest tests/unit -q                      # fast: the rules
pytest tests/unit/combat -q               # one mechanic's slice of them
pytest tests/cards -q                     # the every-card gate
pytest -m "not slow" -q                   # skip the training runs
python scripts/validate_decks.py
python scripts/run_arena.py --games 200 --pods 2,4 --max-draw-rate 0.2
python scripts/smoke_http.py --players 4        # against a running server
python scripts/smoke_http.py --pod --players 2 # the lobby, end to end, with tokens
cd frontend && npm test && npm run build && npm run lint
```
