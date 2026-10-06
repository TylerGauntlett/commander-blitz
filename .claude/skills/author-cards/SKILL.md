---
name: author-cards
description: Implement more Magic cards in the engine's DSL, in bulk or by name. Use when asked to author, import, or add cards; to raise card coverage; to work the card queue; or to make one specific card playable ("I need Rhystic Study for this deck"). Runs the free template tier, fans the rest out to concurrent workers, verifies every card through the six gates, and commits. Cards the DSL cannot express become gap records for /extend-dsl.
---

# Authoring cards

The pipeline already exists and is good. This skill drives it; it does not replace
any part of it. Read `docs/card-authoring.md` once if you have not.

The thing that must not go wrong: **`compile_card` validates vocabulary, not
meaning.** A card whose ops all exist can still say "draw a card" and gain life
instead. So nothing here trusts a generator or a worker — `verify.py`'s six gates
decide what ships, and a card that cannot prove its behaviour does not get written.

## Invocations

| | |
|---|---|
| `/author-cards` | 12 cards from the top of the queue |
| `/author-cards 100` | 100 cards, in waves |
| `/author-cards "Rhystic Study" "Smothering Tithe"` | targeted, by name |
| `/author-cards --report` | read-only status; writes nothing, stop after step 1 |

Targeted mode is the same loop with a different selection step. It is the mode to
use from another agentic loop, or when a specific card is needed for work in
progress.

## Hard rules

1. **Workers write exactly one file each**, either
   `data/authoring/answers/<card_id>.json` or `data/authoring/gaps/<card_id>.json`.
   Never both, never anything else.
2. **Only `--collect` writes cards.** Never hand-edit `data/cards/`, never merge
   card JSON yourself. It rewrites the pool atomically after re-running all six
   gates; doing it by hand skips the gates entirely.
3. **Never invent an op.** If the DSL cannot say a card, that is a gap record and
   a `/extend-dsl` job. Approximating it is the one failure this pipeline exists
   to prevent, and this skill never edits `src/automtg/engine/`.
4. **Never push.**

## The loop

### 1 · Baseline

```bash
git status --short
python scripts/author_cards.py --report
```

Keep the numbers — the final message is a delta against them. If the tree is dirty
outside `data/` and `docs/unsupported-cards.md`, stop and say so: the run ends in a
commit and must be able to commit only its own work.

For `--report`, stop here.

### 2 · Free tier first, always

```bash
python scripts/author_cards.py --tier templates --limit 400          # bulk
python scripts/author_cards.py --tier templates --card "Rhystic Study"   # targeted
```

Deterministic, exact, costs nothing. **Never spend a worker on a card
`templates.py` can already finish** — this is the biggest single lever on both cost
and speed. In targeted mode this often ends the run.

### 3 · Hand out work

```bash
python scripts/author_cards.py --tier agent --limit N
python scripts/author_cards.py --tier agent --card "Rhystic Study"    # targeted
```

Writes one packet per card to `data/authoring/packets/`. The queue is already
priority-ordered — cards from imported decks, then EDHREC rank — so the top of the
batch is the most-played unimplemented card in Magic.

`ls data/authoring/packets/` for the actual ids. Do not assume which came out.

### 4 · Fan out — one worker per card, waves of 6

One `Agent` per packet, `subagent_type: general-purpose`. Its prompt is the full
text of `references/worker-brief.md` plus the one packet path it owns.

One card per worker, not a batch per worker. The packet is entirely self-contained
— oracle text, what the free tiers already worked out, the sentences still
outstanding, why the templates gave up, the whole DSL vocabulary, and worked
examples from the live pool. A worker needs no repo context, which is what makes
the fan-out cheap, and a worker that goes wrong costs one card instead of ten.

Wait for each wave before launching the next. Note which packet each worker owns —
step 6 needs to reach the same worker again.

### 5 · Collect — the single edit

```bash
python scripts/author_cards.py --collect
```

The one place the card pool changes. Re-verifies every answer on disk through all
six gates and atomically rewrites `templates.cards.json`, `expectations.json` and
`queue.json`. Prints `accept <id>` or `REJECT <id>: <gate> -- <reason>` per card.

**An accepted card's answer and packet are deleted** once the pool is written.
From then on `data/cards/auto/` is the card's only source of truth, and
`answers/` holds nothing but work in progress. The collect starts from the
`templates.cards.json` already on disk and only adds or replaces, so a card whose
answer is gone stays collected. Rejected answers stay for step 6.

Packets are gitignored: `--tier agent` regenerates one whenever it is needed, so
a packet is never committed.

### 6 · Repair, once

For each `REJECT`, `SendMessage` the gate and reason back to **the same worker**,
which still has its packet in context. Then `--collect` again.

Then stop chasing it. A card that fails twice gets one of two endings, and **its
answer file must not stay on disk either way**:

- genuinely inexpressible → replace the answer with a gap record
- wrong for some other reason → `rm data/authoring/answers/<card_id>.json`

This matters more than it looks. `--collect` globs the whole answers directory
every run, so a rejected answer left behind is re-verified and re-rejected on every
future run forever, re-marking its queue entry `failed` each time. Deleting it leaves the
queue entry carrying its gate and reason, which is the signal `--report` aggregates.

### 7 · Normalize gaps, then report

Read the gap records this run produced. Workers cannot see each other, so the same
capability arrives under different slugs — merge them by editing the `capability`
field to one spelling. Prefer names already in `docs/unsupported-cards.md`, then
the known backlog in `docs/card-authoring.md`: `cycling`, `crew`, `flashback`,
`kicker`, `convoke`, `ward`, `modal-targets`.

This merging is the main agent's job precisely because it is the only vantage point
that sees the whole wave.

A record with `kind: "token"` is a token the packet's `token_ids` does not have
(the packet tells workers to file exactly that rather than pick a near miss). It
is the cheapest gap there is: one entry in `data/cards/tokens.cards.json`, added
under `/extend-dsl` (its Tier 0), never by this skill — rule 2 still holds.

```bash
python scripts/report_gaps.py
```

### 8 · Gate

```bash
python -m ruff check src scripts tests
python -m pytest tests/cards -q
python -m pytest tests/unit -q
```

`tests/cards` re-runs all six gates over every auto card, so an engine change that
quietly invalidated an *older* card surfaces here rather than in somebody's game.

Any failure: stop, report, do not commit.

### 9 · Commit

Data and the generated report only:

```bash
git add data/cards/auto data/authoring docs/unsupported-cards.md
git commit -m "author N cards (agent tier)"
```

If `git status` shows changes outside those paths, stop and report instead —
something in the run did more than it should have.

### 10 · Report

- cards playable and coverage %, before → after
- accepted, rejected, and gap records written
- the top capabilities now blocking work, each with its card count and the
  `/extend-dsl <slug>` command that clears it

## When something is off

| | |
|---|---|
| `no card catalog` | `python scripts/build_card_index.py` first |
| every card fails gate 4 or 5 | suspect the harness, not the cards — check `tests/cards -q` passes on a clean tree before blaming the workers |
| a worker edits `src/` or `data/cards/` | discard that answer; rule 3 |
| `--collect` rejects cards nobody authored this run | stale answers from an earlier run; step 6's deletion rule was skipped |