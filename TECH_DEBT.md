# Tech Debt

**Measured at:** `adf05b8e` (2026-10-06).

This is a working list: every item here is **open**. When you fix one, delete its entry
in the same PR. Each item says why it matters, where to look, and what fixing it looks
like. Sizes: **S** is an afternoon, **M** a focused PR, **L** a multi-PR effort.

**Retired IDs.** Code and tests still cite IDs from the 2026-09-04 audit that are now
resolved (`CG-01`–`CG-06`, `FT-03`, `FT-05`, `FT-06`, `FB-08`, `DC-01`, `LP-*`, `NF-01`,
`UV-*` and others). Their write-ups are in the last version of the old report:
`git show ab86d46f:TECH_DEBT.md`. IDs that are still open keep their old names below
(`FB-02`, `FB-12`, `FB-13`, `FT-04`, `FT-07`, `OF-01`).

## Suggested order

1. **Card defects:** CD-07 (one engine fix), CD-08 (one card at a time).
2. **Structural:** CD-01 (one card layer), ST-01 (shims), OF-01.
3. **Decision:** RS-01 (rewrite history or not).
4. **UI defects:** FB-12, FB-13, FT-04, FT-07, one PR each.

---

## Card data and the authoring pipeline

### CD-01 · Two card layers where one would do — **L**

Cards live in two places:

| Layer | Where | Entries | Written by |
|---|---|---|---|
| hand-written | `data/cards/{aesi,edgar,isperia,zurgo,basics,core,tokens}.cards.json` | 285 (192 cards + 93 tokens) | a person or an agent, directly |
| pipeline | `data/cards/auto/templates.cards.json` | 2,854 | `scripts/author_cards.py --collect`, after the six gates |

The split made sense when the hand-written cards were paraphrases nothing could check.
That is no longer true. All 192 non-token hand-written cards pass the same six gates
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
  `scripts/author_cards.py:254-325`. These delete cards from hand-formatted JSON by
  matching braces.
- **`scripts/audit_cards.py`, and the deficit baseline it writes.** The baseline is
  now permanently empty.
- **Load order matters in one place:** `registry.py:29-43` loads the hand-written files
  first, so they win `by_name`.
- **`CardModel.source` (`schema.py:1403`) is written but never read.**
- **Two tests may skip the pipeline layer by accident.** `tests/ai/test_agents.py:80,98`
  and `tests/cards/test_schema.py:19` glob only the hand-written files.

**The blocker.** `authoring/verify.py:172-185` `_props` builds gate 5's sandbox board by
taking the alphabetically-first card for each role from **the pool it is given**, and
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

### CD-07 · "This or another creature dies" misses its own death — **S**

A trigger worded "whenever this creature or another creature you control dies" is
written as `creature_dies` with a controller filter. The leave-the-battlefield
look-back in `engine/triggers.py` (around `:906-931`) only collects `source: "self"`
triggers from the object that just left, so the card never sees **its own** death.
Confirmed with a probe on Zulaport Cutthroat; Blood Artist, Cruel Celebrant, Falkenrath
Noble, Kalastria Highborn and Cordial Vampire have the same shape. Pinned by the strict
xfail `tests/cards/test_zurgo_deck.py::TestZulaportCutthroat::test_its_own_death_drains`.

**Fix:** let the look-back also collect the departed object's dies triggers whose
filter it matches, then remove the xfail. Arena tables will move; that is the point.

### CD-08 · Hand-written cards that pass all six gates but are wrong — **S** each

Found while writing the CD-06 deck tests. The gates check vocabulary and a zone-only
expectation, so none of these fails one:

- **Sun Titan** (`isperia`): no "or attacks" trigger; the return is neither optional
  nor targeted.
- **Emeria Angel**: the Bird token is not optional.
- **Retreat to Kazandu** (auto): the counter mode picks among your own creatures
  instead of targeting any creature.
- **Kalastria Highborn**: `exclude_self` set, no "you may pay {B}", and it drains each
  opponent instead of a target player.
- **Falkenrath Noble**: `exclude_self` set (see CD-07 for why it matters).
- **Cruel Celebrant**: "or planeswalker" is missing.
- **Zurgo Stormrender**: Mobilize's Warrior is never sacrificed at the next end step
  (the test-only `t_mobilizer` has the same omission).
- **Timely Hordemate**: Raid is ignored; it returns a card with no attack this turn.
- **Secure the Wastes**: creates Soldiers; the card prints Warriors (read, not run).

**Fix:** correct each card, and add the failing case to its deck test.

---

## Repository size and CI cost

### RS-01 · About 395 MB of history — **decision**

The working-tree causes are settled: packets left git (`.gitignore`) and collect now
retires them; `queue.json` stays, because it records why each card failed and cannot
be regenerated; `cards.sqlite` stays committed, because CI cannot rebuild it
deterministically (its input is a dated, gitignored Scryfall dump) and Git LFS
bandwidth on the Free plan would cost more than it saves. What is left is the
history itself, and rewriting it is a separate, explicit decision.

---|---|---|
| `data/authoring/queue.json` | 11 MB | 365 (touched by 242 of 673 commits) |
| `data/catalog/cards.sqlite` | 15.7 MB, binary | 83 |
| `data/cards/auto/templates.cards.json` | — | 364 |
| `data/authoring/packets/` | 29 MB, 836 files | — |

**Fix options:**
- stop committing `packets/` (see CD-03), and decide whether `queue.json` must be in git;
- build `cards.sqlite` in CI, or keep it in Git LFS;
- update the stale comment.

Rewriting history is a separate, explicit decision.

---

## Code structure

### OF-01 · Oversized modules and functions — **L**

28 modules in `src/` are over 1,000 lines, and 8 are over 2,000:

| Module | Lines |
|---|---|
| `cards/loader/__init__.py` | 4,235 |
| `cards/loader/effects.py` | 2,750 |
| `engine/characteristics.py` | 2,417 |
| `engine/player_statics.py` | 2,239 |
| `engine/costs.py` | 2,193 |
| `engine/primitives.py` | 2,111 |
| `engine/effects/ops_cards.py` | 2,109 |
| `engine/triggers.py` | 2,092 |

The September splits brought every file under 2,000 lines. The DSL work since has
pushed eight back over.

The functions matter more than the files:

| Function | Lines |
|---|---|
| `loader/effects.py:570` `_validate_effect` | 2,181 (87 `op ==` guards; 58 a month ago) |
| `loader/__init__.py:2712` `_compile_static` | 1,524 |
| `loader/__init__.py:582` `compile_card` | 1,069 |
| `loader/__init__.py:1864` `_compile_printed_ability` | 718 |
| `cards/authoring/packet.py:440` `reference` | 577 |
| `engine/game.py:333` `_cast` | 538 |

25 functions are over 200 lines. Every `/extend-dsl` run adds a branch to
`_validate_effect`.

**Fix:** a per-op validator registry, like the effect-op `register()` the engine
already uses. **Before you start:** the golden pool pins only cards that load, so first
pin the error messages invalid cards get, or the move will change them without anyone
noticing.

### ST-01 · The September split's re-export shims are the only import path — **M**

- **`engine/characteristics.py:2332-2379`** re-exports 44 names from
  `player_statics`, imported at the bottom of the file "so every `from
  automtg.engine.characteristics import ...` keeps working". At least ten engine
  modules still import them through `characteristics`.
- **`cards/loader/__init__.py:104`** re-exports private names (`_validate_effect`,
  `_compile_target` and more). There are 365 `from automtg.cards.loader import` sites,
  and none of them imports from a `loader.*` submodule.
- **`tests/conftest.py`** re-exports `GameBuilder` the same way.

These shims account for most of the growth in `# noqa`: 36 now, 22 of them `F401`, up
from 22 in total a month ago. There are also 21 `biome-ignore`s in the frontend.

**Fix:** point the callers at the real modules, mechanically, then delete the shims.

### ST-02 · 433 function-local imports — **M**

56 of 95 modules import inside functions; the most are in `engine/game.py` (37),
`costs.py` (30), `triggers.py` (27) and `stack.py` (21). `pyproject.toml` also gives
`effects/__init__.py` and `characteristics.py` E402 exemptions. Both are workarounds
for import cycles.

**Fix:** map the cycle graph first. Most cycles probably break by moving shared types
into `structs.py`, or helpers out of `game.py`.

### ST-03 · Test helpers copied file by file — **M**

- **221 test files define their own `board(`**, 24 of them with the identical
  `board(builder)` signature. **120 define `_card(`.** `tests/conftest.py` has a
  `builder` fixture and some action helpers, but nothing for building a board.
- **`tests/unit/` is one flat directory of 537 files.**
- **18 test files are over 800 lines**, the largest `test_bard_king_of_dale_deck.py`
  at 2,376. The Myrel deck alone has four files over 1,400.

**Fix:** a shared board helper in `conftest.py` or `automtg.engine.sandbox`, then
subdirectories in `tests/unit/` by mechanic.

### ST-04 · Large frontend files — **M**

| File | Lines |
|---|---|
| `components/game/Table.tsx` | 1,361 |
| `testing/scenarios.ts` | 1,105 |
| `Table.stories.tsx` | 1,104 |
| `input/pad.ts` | 983 |
| `logic/events.ts` | 924 |

Stylesheets: `board.css` 2,343, `handheld.css` 1,855, `lobby.css` 1,756 and `ui.css`
1,693. `handheld.css` is mostly overrides of the other three, so a token or
container-query approach would shrink both sides.

---

## Open defects

These are known bugs, left open by decision. Each one is pinned or documented at its
code. Fix them in their own PRs.

| ID | Defect | Where | Pinned by |
|---|---|---|---|
| FB-12 | Settings popover is unreachable or escapable by the controller: there is no `data-modal-root` and no `B` binding | `components/game/SettingsMenu.tsx:4-9` | the comment there |
| FB-13 | The commander shows "Ready" only while the pointer is over the orb | `components/game/CommandZone.tsx` | `frontend/tests/commandZone.test.tsx:218` (`it.fails`) |
| FT-04 | The viewer's battlefield bands drift 9–41px as permanents enter, against a 6px budget | `frontend/e2e/layout.spec.ts:279` | conditional `test.fail` |
| FT-07 | Screen changes fade out, then fade in (`AnimatePresence mode="wait"`), so returning to a game is slow. `82900ae7` removed the blank frame but not the wait | `App.tsx:113`, `screens/GameRoute.tsx:133` | — |

---

## Docs, hygiene, environment

### DEP-01 · Dependency upgrades — **S**

- Upgrade candidates, nothing broken: `vite ^5.4` and `@biomejs/biome ^1.8`. Storybook
  10 already accepts vitest 4.
