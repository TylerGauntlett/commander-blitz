---
id: voting
title: "Voting: will of the council and council's dilemma"
area: cards
effort: M
impact: medium
why: every voting card waits on it, Fateful Tempest in the Lorehold Spirit precon and Council's Judgment among them
depends_on: []
status: proposed
---

## Today

Voting (701.38) is absent. [rules-coverage.md](../rules-coverage.md#not-implemented)
lists "Voting — will of the council, council's dilemma" as not implemented, and
the shipped decks avoid it. The nearest shapes in
`engine/effects/ops_control.py` each miss one half of it: `join_forces` asks
every player in turn order starting with the controller, which is the order a
vote is cast in, but it adds up mana paid rather than tallying named choices;
`choose_mode` and `ask_mode` in `engine/effects/context.py` let one chooser
pick among labelled options, but bind no per-option count a later effect can
read. `for_each_player` around `choose_mode` asks the right people and keeps
nothing.

So every "each player votes for A or B" card is unwritable. Fateful Tempest,
in the Lorehold Spirit precon, is the card that found it; Council's Judgment,
Tivit, Seller of Secrets and the Conspiracy council cards are the same
sentence. Its gap record is `data/authoring/gaps/fateful_tempest.json`.

## The change

1. A `vote` op in `engine/effects/ops_control.py`: starting with the
   controller and in turn order (`GameState.turn_order`, as `join_forces`
   walks it), each player in the game chooses one of the spec's named options
   through `ask_mode`, with the votes so far in the decision's `context` so a
   later voter sees them (701.38a). It binds the tally under `as`, one count
   per option, read back as `{"binding": "<as>.<option>"}`, and the winners
   (the options with the most votes, all of them on a tie) for will of the
   council's "if X gets more votes or the vote is tied".
2. A `vote_cast` event emitted per vote, so "whenever a player votes" has an
   event to name later, without adding that trigger now.
3. `cards.loader`'s `_validate_effect` refuses a `vote` with fewer than two
   options or a missing `as`; the verifier's auto-answer table already answers
   `CHOOSE_MODE`, so the behaviour gate needs nothing new.
4. Harvest: Fateful Tempest, then the catalog's other voting cards through the
   template tier with `--retry` and one `/author-cards` wave.

It does not add extra votes (Brago's Representative, Grudge Keeper's
"whenever a player votes") or vote-changing effects; those are additions on
the `vote_cast` event once the op exists.

## Gate

A unit test under `tests/unit/` for `vote`: players asked in turn order from
the controller, each later voter's decision carrying the earlier votes, the
tally bound per option, the tie reported as every leading option, an eliminated
player not asked, and the loader refusing a one-option vote. Fateful Tempest's
six gates pass.

## Open questions

- **Where a vote is asked.** `ask_mode` per voter, or a decision kind of its
  own? Recommended: `ask_mode` with a `purpose: "vote"` tag, because the
  client and the CPUs already answer a labelled choice and a new decision kind
  would need its frontend label, its auto-answer and an e2e path for no new
  rule.
- **How the CPUs vote.** Recommended: the heuristic agent's existing label
  answer for now, with the `purpose` tag left for a strategy to read; voting
  well is a CPU item, not a rules one.
- **Is it an ADR.** Recommended: no; it is an additive op, and the line in
  rules-coverage.md moves from "not implemented" to the implemented table.
