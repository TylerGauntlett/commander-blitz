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
