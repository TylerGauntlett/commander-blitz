# How this is verified

```bash
python scripts/verify.py        # everything, in order, exits non-zero on failure
```

## The suites

| Suite | Count | What it holds |
|---|---|---|
| `tests/unit/` | 122 | Mana, zones, casting, the stack, priority, turn structure, combat, keywords, triggers, static abilities, state-based actions, the commander rules, multiplayer |
| `tests/cards/` | 514 | Schema and vocabulary validation, deck legality, the every-card gate, and the card index + art resolution |
| `tests/ai/` | 71 | Action-space correctness, the environment, agents, the arena, the model and trainer |
| `tests/server/` | 53 | The HTTP API end to end, including hidden information, image serving and the catalog |
| `frontend/tests/` | 330 | The client's pure logic modules, the palette ladders, and the card face |
| `frontend/e2e/` | 44 | Playwright: full games, combat, stacking, card art, greyscale, layout |

`scripts/verify.py` runs 12 stages in dependency order and stops at the first failure:
lint, deck validation, **is the committed card index current**, each Python suite, a
160-game arena, **a real uvicorn process playing full games at 2 and 4 players**, then
the frontend build, lint and tests.

Playwright is still invoked separately (`cd frontend && npx playwright test`).

## Card art has its own gates

Three of them, because the failure modes are all silent:

- **The token naming rule.** `tests/cards/test_image_resolution.py` freezes the set
  of cards with no printing at exactly five. A *sixth* means a real card stopped
  resolving and quietly started rendering a blank plate, which nothing else notices.
- **The greyscale ladder.** `frontend/tests/palette.test.ts` checks the type-ring
  tones stay separable by luminance; `frontend/e2e/greyscale.spec.ts` checks the same
  thing against the *rendered* board, where an override from `theme.css` or a media
  query would show up and a stylesheet parse would not.
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
python scripts/smoke_http.py --players 4  # against a running server
cd frontend && npm test && npm run build && npm run lint
```
