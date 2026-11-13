---
id: secret-choices
title: Secret choices
area: cards
effort: M
impact: medium
why: every card where players secretly choose and then reveal waits on it, Expert-Level Safe in the Science! precon and Menacing Ogre among them
depends_on: []
status: proposed
---

## Today

Every choice the engine asks is one player's, one at a time. An op asks
through `ask_mode` in `engine/effects/context.py`, which yields a
`PendingDecision` (`engine/actions.py`) for a single `player`, and binds the
answer in the effect context as soon as it comes back. `choose_number` in
`engine/effects/ops_control.py` asks only `ctx.controller`, and nothing
asks a second player the same question. Wrap it in `for_each_player` and the
players answer in turn, each answer bound before the next is asked. The
view does hide some things: `serialize._pending` puts card faces only on the
seat that has to answer, `event_log_for` drops object ids from
`_PRIVATE_EVENTS`, and face-down exile has `hidden_in_exile` and
`revealed_to`. But no seat can hold an answer the other players must not
see until everyone has chosen. [rules-coverage.md](../rules-coverage.md#not-implemented)
does not mention secret choices. It lists voting as not implemented, and
secret council is the secret form of voting.

So "you and target opponent each secretly choose 1, 2, or 3. Then those
choices are revealed" cannot be written. Neither can "each player secretly
chooses a number", "secretly choose an opponent", or a secret vote. Asked in
turn, the later chooser answers after seeing the earlier choice, and that
changes the card. The Science! precon found it through Expert-Level Safe,
whose gap record is `data/authoring/gaps/expert_level_safe.json`. The
catalog has a few dozen cards printing "secretly", among them Menacing Ogre,
Prisoner's Dilemma, Círdan the Shipwright, Elrond of the White Council,
Stalking Leonin, The Toymaker's Trap and the secret council cards (Vault 11:
Voter's Dilemma, Marchesa's Surprise Party, Mob Verdict).

## The change

1. A secret answer. Each chooser is asked in turn through `ask_mode`, as
   today, but the answers are held unrevealed until the last chooser has
   answered. Until then a later chooser's decision context and every other
   seat's view show only that a choice has been made, never what it is. The
   reveal is one event carrying every answer.
2. An op for the shape the cards print: a number, or one of a fixed set of
   labels, chosen secretly by a named set of players (you and a target
   opponent, each player, each opponent). Each answer is bound per player,
   so a later `condition` can compare the answers ("if they match", "the
   player who chose the highest number").
3. The CPUs answer through the label path the heuristic agent already uses
   for `choose_number`. A strategy reads only what its own seat's view
   shows, so it never sees an unrevealed answer.
4. The loader's `_validate_effect` refuses the op without choosers or
   without `as`. The authoring verifier answers it the way it answers
   `choose_number`.
5. Harvest: Expert-Level Safe through `/author-cards`, then one wave over the
   catalog's other secret-choice cards that need nothing else.

It does not build voting. Secret council is
[voting](voting.md) with its votes cast secretly; once both items land, it
is the vote op asking through this one's secret answer.

## Gate

A unit test under `tests/unit/` for the secret choice:

- every named chooser is asked;
- a later chooser's decision and every other seat's `player_view` and
  `event_log_for` do not carry an earlier answer before the reveal;
- the reveal event carries all answers, and each answer is bound per player
  for a condition to compare;
- an eliminated player is not asked;
- the loader refuses the op with no choosers.

Expert-Level Safe passes its six gates, and the generated DSL reference
(`tests/cards/test_dsl_reference.py`) lists the new op.

## Open questions

- **How an answer is kept secret.** An unrevealed answer can live in the
  effect context's bindings, which no view serializes, or in a field on
  `GameState` that `player_view` redacts per seat. Recommended: the
  bindings, with the reveal as one event, because nothing serializes them
  today. That makes "not leaked" a property the test can check, not a
  redaction someone has to remember.
- **One decision kind or `ask_mode`.** Recommended: `ask_mode` with
  `purpose: "secret_choice"`. The client and the CPUs already answer a
  labelled choice, and a new `DecisionKind` would need its frontend label,
  its auto-answer and an e2e path, with no new rule to show for it.
- **What the client shows while others choose.** Recommended: nothing new.
  Each chooser sees their own prompt, and the reveal is narrated from its
  event in the log. A surface beyond that would need its story and floor
  ([ADR 0013](../adr/0013-handheld-floors-are-ci-gates.md)).
- **Is it an ADR.** Recommended: no, if the answer stays in the bindings,
  because it is an additive op. Yes, if it adds per-seat redaction of game
  state, because that is a rule the views would be built around from then on.
