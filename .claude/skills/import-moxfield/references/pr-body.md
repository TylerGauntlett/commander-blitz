# PR body template

Fill every `<...>`. Numbers come from `before.json` and a fresh `deck_status.py` /
`author_cards.py --report` run. Delete a section only if it is genuinely empty, and
say so in one line rather than deleting "Not done".

```markdown
Makes every card in [*<deck name>*](<moxfield url>) playable — **<N> of <N>**, from a
starting point of <before>.

Driven through the two existing pipelines: `/author-cards` for the card definitions,
`/extend-dsl` for the engine capabilities that unblocked them. <K> commits, one per
capability or authoring wave.

## Coverage

| | before | after |
|---|---|---|
| Deck cards native | <before> / <N> | **<N> / <N>** |
| Registry | <cards> | <cards> |
| Catalog coverage | <x.x>% | <y.y>% |
| Open gap records | <capabilities> | <capabilities> |

## What shipped

**<M> engine capabilities.** The larger ones:

- **<slug>** — <one sentence: what it says, and the near miss it is not>. Unblocked <cards>.
- ...

<One paragraph per rules subsystem built under rule 2, if any.>

**<T> new unit test files**, each with a rules argument naming the printed card.
**<P> per-card behavioural tests** in `tests/cards/test_<slug>_deck.py` for what the six
authoring gates cannot reach. `tests/cards/test_<slug>_import.py` pins the import at
<N>/<N> native.
<Frontend / e2e tests, if the branch touched a UI surface; otherwise one line saying no
UI surface changed and the three CI Playwright projects are the e2e coverage.>

## Bugs found by the tests

<Each: what was wrong, which card exposed it, the commit. Or: none.>

## Not done

<Empty. If not: the card, why it is not native, and what it would take.>

## Verification

- `pytest tests/unit tests/cards tests/server tests/ai` — green; `tests/cards` re-runs
  all six authoring gates over every machine-authored card
- `ruff check src scripts tests` — clean
- `scripts/verify.py` — all stages pass locally
- changed files under `src/commanderblitz` — <lowest>% to <highest>% line coverage; the
  repo-wide floor is held by `verify-slow`
- `scripts/audit_cards.py` — no deck card has an open fidelity deficit

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```
