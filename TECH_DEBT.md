# Tech Debt

This is a working list: every item here is **open**. When you fix one, delete its entry
in the same PR. Each item says why it matters, where to look, and what fixing it looks
like. Sizes: **S** is an afternoon, **M** a focused PR, **L** a multi-PR effort.

**Retired IDs.** Code and tests still cite IDs from an earlier audit that are now
resolved (`CG-01`–`CG-06`, `FT-03`–`FT-07`, `FB-*`, `DC-01`, `LP-*`, `NF-01`, `UV-*` and
others). Their write-ups are in this file's history (`git log -p -- TECH_DEBT.md`).
`OF-01` is the one old ID still open.

## Suggested order

0. **Cheap and worth doing first:** SV-01 (gate `/debug`).
1. **Cheap:** UI-02 (one accessibility pass).
2. **Structural:** CD-01 (one card layer), OF-01.

---

## Card data and the authoring pipeline

### CD-01 · Two card layers where one would do — **L**

Cards live in two places:

| Layer | Where | Written by |
|---|---|---|
| hand-written | `data/cards/{aesi,edgar,isperia,zurgo,basics,core,tokens}.cards.json` | a person or an agent, directly |
| pipeline | `data/cards/auto/templates.cards.json` | `scripts/author_cards.py --collect`, after the six gates |

The split made sense when the hand-written cards were paraphrases nothing could check.
That is no longer true. Every non-token hand-written card passes the same six gates
(`tests/cards/precon_deficits.json` is `{"cards": {}}`), and the two layers share no
ids or names. What the split still costs:

- **Two gate tests that do the same job:** `tests/cards/test_hand_written_cards.py` and
  `tests/cards/test_auto_cards.py`. They differ in small ways. Only the hand-written side
  checks `oracle_text` against the catalog. Only the auto side checks for orphaned
  expectations.
- **Two expectation files:** `tests/cards/expectations.json` and
  `data/cards/auto/expectations.json`, with overlapping keys (see CD-05).
- **Machinery that exists only to move cards from one layer to the other:**
  `--supersede`, plus `_drop_hand_written` and `_card_span` in
  `scripts/author_cards.py`. These delete cards from hand-formatted JSON by
  matching braces.
- **`scripts/audit_cards.py`, and the deficit baseline it writes.** The baseline is
  now permanently empty.
- **Load order matters in one place:** `authored_card_paths` in `cards/registry.py`
  loads the hand-written files first, so they win `by_name`.
- **`CardModel.source` (`cards/schema.py`) is written but never read.**
- **Two tests may skip the pipeline layer by accident.**
  `tests/ai/test_agents.py` (`test_it_always_makes_its_land_drop`,
  `test_it_never_points_removal_at_its_own_creature`) and `all_card_files` in
  `tests/cards/test_schema.py` glob only the hand-written files.

**The blocker.** `_props` in `authoring/verify.py` (with `OWN_BOARD_ROLES`,
`OPPONENT_BOARD_ROLES` and `OWN_GRAVEYARD_ROLES` beside it) builds gate 5's sandbox
board by taking the alphabetically-first card for each role from **the pool it is given**, and
that pool is the hand-written one. With the full pool, the board changes: your own
`acidic_slime ×2` becomes `a_i_m_bot ×2`, and the opponent's Azusa / Air Elemental
become Aang and Katara / A.I.M. Bot. That invalidates the measured counts in
expectations that were recorded against the old board.

**Fix, in order:**
1. Pin the sandbox props to explicit ids, so the board no longer depends on which pool
   is passed in.
2. Move the precon, basics and core cards into `auto/`, carrying their expectations
   across.
3. Delete `--supersede`, `_drop_hand_written`, `audit_cards.py`, the deficit baseline
   and the hand-first ordering.
4. Merge the two gate tests into one.

Keep `tokens.cards.json` hand-written (CD-02). `test_golden_pool` hashes the compiled
cards sorted by id, so moving a card between files does not change the hash.

---

## Code structure

### OF-01 · Oversized modules and functions — **L**

At the time of writing, 27 modules in `src/` are over 1,000 lines, and 8 are over
2,000:

| Module | Lines |
|---|---|
| `cards/loader/__init__.py` | 4,214 |
| `cards/loader/effects.py` | 2,746 |
| `engine/characteristics.py` | 2,390 |
| `engine/player_statics.py` | 2,238 |
| `engine/costs.py` | 2,159 |
| `engine/primitives.py` | 2,039 |
| `engine/effects/ops_cards.py` | 2,095 |
| `engine/triggers.py` | 2,062 |

The functions matter more than the files (also at the time of writing):

| Function | Lines |
|---|---|
| `loader/effects.py` `_validate_effect` | 2,181 (87 `op ==` guards) |
| `loader/__init__.py` `_compile_static` | 1,524 |
| `loader/__init__.py` `compile_card` | 1,069 |
| `loader/__init__.py` `_compile_printed_ability` | 718 |
| `cards/authoring/packet.py` `reference` | 577 |
| `engine/game.py` `Game._cast` | 538 |

25 functions are over 200 lines. Every `/extend-dsl` run adds a branch to
`_validate_effect`.

**Fix:** a per-op validator registry, like the effect-op `register()` the engine
already uses (`engine/effects/registry.py`). **Before you start:** the golden pool
pins only cards that load. Many `raises(DslError, match=...)` tests pin the error
messages invalid cards get; check that the ops you move are among them, or pin them
first.

---

## Accessibility

### UI-02 · Roles and ARIA that biome 2 flags, suppressed with reasons — **S**

The biome 2 upgrade surfaced real accessibility findings, each now carrying a
`biome-ignore` that says why it was not fixed in a refactor:

- **`useAriaPropsSupportedByRole`:** labelled readouts with no role (`CardFace`,
  `CardPreview`, `CardStack`, `OpeningHand`, `ReadyTrack`, and file-wide in
  `OpponentSeat`). The fix is a role (`img`, `group`, `status`...), which changes what
  a screen reader announces.
- **The settings menu's mute item** uses `aria-pressed`. The right shape is
  `menuitemcheckbox` with `aria-checked`; `e2e/action-panel.spec.ts` reads
  `aria-pressed` and changes with it.
- **`noStaticElementInteractions`:** pointer-only hover affordances on `HandFan`,
  `OpponentSeat`, `PlayerOrb`, `HomeScreen` and the `Table` root. They are not the
  keyboard or pad path (the ring is), but they want a decision rather than a comment.

**Fix:** one accessibility pass with a screen reader on, removing each suppression as
its element gets the right role.

---

## Server

### SV-01 · `/debug` is reachable on the hosted server — **S**

`GET /api/games/{id}/debug` returns the full state, hidden zones included. Its
docstring and [docs/api.md](docs/api.md) call it development only, and
`tests/server/test_api.py` asserts it reveals what the player view hides, but
nothing in `server/routes.py` gates it: no setting, mode or environment check. On
the site anyone holding a `game_id` can read every hand and library in a
multiplayer pod.

**Fix:** refuse it unless the app runs in a development or desktop mode
(`settings.py` already distinguishes hosted from desktop), and add the test that
asserts the hosted mode returns a 404. Found while writing
[docs/server.md](docs/server.md).

---

## Strategy gaps

Worked around in individual deck plans (`src/commanderblitz/ai/strategy/decks/`)
and worth lifting into `DefaultStrategy`:

- A modal spell's targets are chosen after its mode, so the cast action cannot
  see them; a "choose one" burn spell can still be pointed at our own creature.
- `classify` calls only destroy/exile "removal", so burn and bounce miss the
  "never at our own board" rule (Vivi's plan adds it).
- A spell that both draws and costs life (Sign in Blood) reads as harmful and
  goes at an opponent even with nothing to punish them (Sheoldred's plan aims it).
- A "may" is always answered yes before a strategy is asked (Blor's Assault
  Suit gives its creature away every time).
- Scute Swarm's landfall copies can trip `MAX_TRIGGERS_PER_STEP` in a long game,
  which the arena scores as a draw.
