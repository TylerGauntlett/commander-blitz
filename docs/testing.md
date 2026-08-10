# How this is verified

```bash
python scripts/verify.py        # everything, in order, exits non-zero on failure
```

## The suites

| Suite | Count | What it holds |
|---|---|---|
| `tests/unit/` | 395 | Mana, zones, casting, the stack, priority, turn structure, combat, keywords, triggers, static abilities, state-based actions, the commander rules, multiplayer |
| `tests/cards/` | 3513 | Schema and vocabulary validation, deck legality and metadata, the every-card gate, and the card index + art resolution |
| `tests/ai/` | 75 | Action-space correctness, the environment, agents, the arena, the model and trainer |
| `tests/server/` | 287 | The HTTP API end to end: hidden information, image serving, the catalog, the whole lobby, and serving the built client |
| `frontend/tests/` | 594 | The client's pure logic modules, the palette ladders, the card face, the lobby, and the routes |
| `frontend/src/**/*.stories.tsx` | 246 | Storybook, in a real Chromium: every component's states, and the geometry jsdom cannot see |
| `frontend/e2e/` | 112 | Playwright: full games, combat, stacking, card art, legibility, layout, deep links, and a two-browser pod |

`scripts/verify.py` runs 14 stages in dependency order and stops at the first failure:
lint, deck validation, **is the committed card index current**, each Python suite, a
160-game arena, **a real uvicorn process playing full games at 2 players, 4 players and
one pod driven entirely through the lobby**, then the frontend build, lint and tests,
the Storybook build, and the story interaction tests.

Playwright's own suite is still invoked separately (`cd frontend && npx playwright test`).

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
  encoded card type as colour — see `docs/mockup-fidelity.md` for why it went.)
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
pytest tests/cards -q                     # the every-card gate
pytest -m "not slow" -q                   # skip the training runs
python scripts/validate_decks.py
python scripts/run_arena.py --games 200 --pods 2,4 --max-draw-rate 0.2
python scripts/smoke_http.py --players 4        # against a running server
python scripts/smoke_http.py --pod --players 2 # the lobby, end to end, with tokens
cd frontend && npm test && npm run build && npm run lint
```
