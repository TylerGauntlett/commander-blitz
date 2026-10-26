---
id: refusal-reasons
title: Why a press is refused
area: play
effort: S
impact: medium
why: every player who presses a permanent that does nothing and has to guess why
depends_on: []
status: proposed
---

## Today

Two of the three refusals a player meets already carry the engine's own
reason. A hand card that cannot be played arrives with one of
`UnplayableReason` in `PlayerView.hand_reasons`, from
`legality.unplayable_reason`, and `HandFan` draws it: priority, timing, the
land drop, mana, no legal target. A card that cannot be *targeted* carries
`LegalAction.untargetable` from the same `target_refusal` that
`can_be_targeted` answers with, and `logic/targetHint.ts` turns it into one
sentence in the foot. The third refusal is silent: a permanent whose
activated ability cannot be activated now (a tap ability on a tapped or
summoning-sick creature, a cost the pool cannot pay, a loyalty ability
already used this turn, a cast lock) is pressable and does nothing, and
`logic/abilities.ts` can only say that no `activate` action names it.

## The change

The same hint, for the same reasons, on a permanent. The engine already
decides every one of these refusals in `legality`; this item surfaces the
decision it made rather than re-deriving one in the client
([architecture.md](../architecture.md)).

- **The engine says why.** `PlayerView` gains `ability_reasons`, keyed by
  oid, built beside `hand_reasons` in `serialize.player_view` from a
  `legality.unactivatable_reason` that answers in the vocabulary
  `unplayable_reason` already uses, extended by the two reasons only an
  ability has: tapped (or summoning sick, for a tap cost) and already
  activated this turn. Only for the viewer's own permanents, and only the
  gates that are closed, so a permanent absent from the map is activatable
  and the map is empty on most boards.
- **The foot says it.** `targetHint` grows a sibling in `logic/` that reads
  `ability_reasons` for the hovered or ringed permanent while nothing is
  being targeted, in the sentence shape `targetHint` uses, and the foot's
  hint draws it as a refusal. `HandFan`'s reason rendering and this one read
  one label table in `logic/labels.ts`, so the same gate says the same thing
  from either zone.

What it does not do: offer an action that was not legal, or change what a
press on a refused permanent does. Pressing it still reads the card.

## Gate

An engine test per reason in `tests/unit/` that `unactivatable_reason`
names it and that an activatable permanent is absent from the map; a server
test that an opponent's seat gets `null`. `tests/targetHint.test.ts`'s
sibling for the new hint, one case per reason, and that it is silent while
targeting. A story in `HintBar.stories.tsx` or `TableFoot`'s nearest that
draws the refusal at the handheld floors.

## Open questions

- **Today no longer matches the code in three places.** The hand's reason
  table is `unplayableHint` in `logic/mana.ts`, not `logic/labels.ts`, and
  `HandFan` draws it itself, under the fan (`unplayable-hint`). The foot's
  hint is not a standing surface: `TableFoot` renders `.choices` only while
  `targeting` is non-empty, and `HintBar` deliberately shows button verbs and
  never a card's text. And a press on a permanent no action names is not a
  read: `abilityRoute` answers `none` and `useTableGestures.onBoardCard`
  returns without a cue. The lock the item calls a "cast lock" is an
  activation prohibition, `player_cant_activate` beside `abilities_locked`.
  Recommended: proceed on these facts and rewrite **Today** and **The
  change** to match in the decide commit.
- **Where is the refusal drawn, with no foot hint outside targeting?**
  Recommended: a line under the board the way `HandFan` draws one under the
  hand, in the same slot and class family (`unplayable-hint`), shown for the
  hovered or ringed permanent of your own while nothing is being targeted,
  portalled into the sheet on a phone exactly as `HandFan` does; not in
  `HintBar`, whose one-line, verbs-only rule is why it stopped echoing
  `data-hint`. The alternative, rendering `.choices` outside targeting, puts
  a Cancel button beside a sentence that has nothing to cancel.
- **What does a press on a refused permanent do?** Recommended: `cue("deny")`,
  the way a board pick refuses a card that is not an option, and nothing
  else; a silent `none` is the half of the problem the hint cannot fix on a
  pad, where nothing is hovered until the ring lands.
- **Which permanents enter the map?** A tap-only mana ability is the payment
  solver's and is never offered (`costs.offerable_mana_ability`), so "tapped"
  on every tapped land would fill the map on every board. Recommended: an
  oid is in `ability_reasons` only when it has an activated ability that is
  not a suppressed mana ability and no `activate` action names it; a
  permanent with one activatable ability and one refused one is absent,
  since its press already acts or opens `AbilityMenu` on what is offered.
  Battlefield only: cycling in hand and embalm in the graveyard are not this
  item.
- **Outside your priority window, is every such permanent `priority`?**
  `hand_reasons` marks every hand card `priority` then, so the map cannot be
  "empty on most boards" and mirror it. Recommended: mirror it, since a
  press on your own turn's permanent during an opponent's step is the same
  question with the same answer; drop the "empty on most boards" claim.
- **The vocabulary.** `_ability_aims` closes on more gates than the item
  lists. Recommended: `priority`, `timing` (sorcery speed, and
  `activate_steps` such as forecast's upkeep), `locked` (`abilities_locked`
  or `player_cant_activate`), `once_per_turn` (`once_each_turn` and 606.3's
  loyalty limit, The Chain Veil's extra counted), `condition`
  (`activation_condition`, a Class's level ladder), `tapped`,
  `summoning_sick`, `mana`, `cost` (any other unpayable part: sacrifice,
  discard, counters, life) and `targets`, as an `UNACTIVATABLE_REASONS` tuple
  beside `UNPLAYABLE_REASONS` and a `UnactivatableReason` type beside
  `UnplayableReason`. Where a permanent has several refused abilities, the
  reason of the first in card order.
- **Restated or shared with `_ability_aims`?** `unplayable_reason` restates
  its generator's gates and `tests/unit/engine/test_legality_reasons.py` pins
  the two together. `_ability_aims` has a dozen gates and is on the hot path
  of `legal_actions`. Recommended: restate, as `unplayable_reason` does,
  walking `_ability_aims`' gates in its order and calling `_ability_aims`
  itself as the final arbiter so "absent from the map" and "an action names
  it" cannot disagree; extend `test_legality_reasons.py` with the same
  invariant over the activate path. Factoring `_ability_aims` to return a
  reason would change the generator every RL step runs for a diagnostic.
- **One label table, where?** Recommended: `unplayableHint`'s sentences stay
  in `logic/mana.ts`, and the new `unactivatableHint` sits beside it sharing
  the shared reasons' wording (and `manaRow` for the mana case, which is why
  the table lives there), so the same gate says the same thing from either
  zone without moving a file the item does not otherwise change. The gate's
  `tests/targetHint.test.ts` sibling becomes a case table in the mana test,
  one case per reason.
- **The story.** `HintBar.stories.tsx` does not draw this surface under the
  recommended placement. Recommended: a board story (the board component's
  nearest stories file) with a refused permanent ringed, at the handheld
  floors and the phone viewport, asserting the line is drawn and that the
  board's box does not move when it appears (ADR 0016).
