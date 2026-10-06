# Tech Debt

**Measured at:** the `tech-debt-sweep` branch (2026-10-06), after every S and M item
from the `adf05b8e` list was cleared.

This is a working list: every item here is **open**. When you fix one, delete its entry
in the same PR. Each item says why it matters, where to look, and what fixing it looks
like. Sizes: **S** is an afternoon, **M** a focused PR, **L** a multi-PR effort.

**Retired IDs.** Code and tests still cite IDs from the 2026-09-04 audit that are now
resolved (`CG-01`–`CG-06`, `FT-03`–`FT-07`, `FB-*`, `DC-01`, `LP-*`, `NF-01`, `UV-*` and
others). Their write-ups are in the last version of the old report:
`git show ab86d46f:TECH_DEBT.md`. `OF-01` is the one old ID still open.

## Suggested order

1. **Structural:** CD-01 (one card layer), OF-01.
2. **Decision:** RS-01 (rewrite history or not).

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

27 modules in `src/` are over 1,000 lines, and 8 are over 2,000:

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
already uses (now in `engine/effects/registry.py`). **Before you start:** the golden pool
pins only cards that load. About 318 `raises(DslError, match=...)` tests pin many of the
error messages invalid cards get; check that the ops you move are among them, or pin
them first.

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
