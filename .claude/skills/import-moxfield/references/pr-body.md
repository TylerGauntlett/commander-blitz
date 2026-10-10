# What a deck import's PR body says

The structure, the diagram rule and the checks all come from `/create-pr`. They are the
same for every PR. This file only lists the deck-specific facts and where each one goes.
Take the numbers from `before.json` and a fresh `deck_status.py` /
`author_cards.py --report` run, not from memory.

- **Summary.** The deck, linked to Moxfield. **<N> of <N>** cards native, up from <before>.
  How many engine capabilities were added.
- **Risks.**
  - Blast radius: the engine subsystems the new capabilities touch, and which existing
    cards share them.
  - Rollback: reverting returns the new cards to proxies.
- **What.**
  - The diagram: the import that used to stop at <before>/<N> (dotted), and the new
    capabilities leading to <N>/<N> (solid).
  - Bullets: the largest capabilities, and the per-card test file plus the import pin.
- **Why.** How many cards were proxies, and what the most reusable capability unblocks
  beyond this deck.
- **How.** `/author-cards` and `/extend-dsl`, one commit per capability or wave, and the
  six authoring gates plus `tests/cards/test_<slug>_deck.py`.
- **Details.**
  - The coverage table (before → after): deck cards native, registry size, catalog
    coverage, open gap records.
  - One line per capability.
  - Bugs the tests found, with the commit that fixed each, or "none".
  - "Not done", left empty if nothing is outstanding.
  - Verification: pytest suites, `ruff check`, `scripts/verify.py`, coverage on the
    changed files, and `scripts/audit_cards.py`.
