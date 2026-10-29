---
id: damage-redirection
title: Damage redirected to a chosen creature until end of turn
area: cards
effort: M
impact: medium
why: Heroic Sacrifice, the last card the Avengers Assemble precon lacks, waits on it, and every redirection card after it
depends_on: []
status: proposed
---

## Today

Damage can be prevented, multiplied or increased, never dealt to something
else. [rules-coverage.md](../rules-coverage.md) lists "Damage redirection
effects" under "Not implemented". Every damage event goes through
`primitives.damage_player` or `primitives.damage_permanent`, which ask
`player_statics.replaced_damage` for the amount (the `replace_damage` static's
`damage_multiplier` and `damage_addend`) and the prevention hooks
(`prevent_damage`, `prevent_damage_permanent`, `prevented_player_damage`) for
what is left. None of them can change the recipient, and the primitives are not
generators, so they cannot ask a player anything mid-combat.

One gap record names the capability, `damage-redirection`:
`data/authoring/gaps/heroic_sacrifice.json`, the last card the Avengers Assemble
precon lacks. Heroic Sacrifice reads "Choose target creature you control. Until
end of turn, all damage that would be dealt to you and creatures you control is
dealt to the chosen creature instead (if it's still on the battlefield). When
that creature dies this turn, put its counters on up to one target creature you
control and draw a card." Its second sentence is reachable already:
`delayed_trigger` watches a subject's own death, and `move_counters` with
`all_kinds` and `from_had_counters` moves a dead creature's counters off the
leave event's snapshot (The Ozolith); the gap record files that half as
`delayed-trigger-on-target-dies-move-counters`.

## The change

1. A one-shot op that installs an until-end-of-turn redirection (a
   `TempEffect` kind in `engine/structs.py`): damage that would be dealt to a
   named player and to the permanents a selector names is dealt to one bound
   object instead, while that object is on the battlefield (614.9, a
   replacement effect). Damage already aimed at the chosen creature is not
   redirected, and the redirected damage keeps its source, so lifelink,
   deathtouch, infect and wither apply as the source has them (120.3).
2. The damage primitives read the redirection before `replaced_damage` and the
   preventions, in the order 616.1 leaves to the affected player, and the
   choice is recorded in `docs/rules-coverage.md` as the doubler-and-addend
   order already is.
3. Harvest Heroic Sacrifice through `/author-cards`, whose second sentence
   composes `delayed_trigger` and `move_counters` as **Today** says (or names
   the narrow gap if it does not), then finish
   [precon-msc-avengers-assemble](precon-msc-avengers-assemble.md), which
   depends on this item.

It does not build a general replacement system (616), which stays under "Not
implemented".

## Gate

A unit test under `tests/unit/damage/` that casts the redirection and asserts:
combat and noncombat damage to you and to another creature you control lands on
the chosen creature; damage to the chosen creature is dealt once, not twice;
lifelink and deathtouch on the source still apply to the redirected damage; once
the chosen creature leaves, damage goes where it was aimed; the effect ends at
cleanup. `tests/cards` with Heroic Sacrifice through the six gates.

## Open questions

- **Where the replacement is read:** inside `damage_player` and
  `damage_permanent`, or one level up in the callers that build each damage
  event (combat damage assignment and the `damage` op). Recommended: inside the
  primitives, because every damage event already passes through them and a
  caller-side hook would miss the next one written.
- **Order against prevention and the multipliers (616.1):** the affected player
  chooses, but the primitives cannot ask. Recommended: redirect first, then
  apply the new recipient's multipliers, addends and preventions, so damage is
  replaced once for the object that actually receives it; record the choice in
  `docs/rules-coverage.md` beside the doubler-and-addend order.
- **Scope of the pull request:** the capability, Heroic Sacrifice and the
  Avengers Assemble deck file, titled `feat(cards):`, so
  [precon-msc-avengers-assemble](precon-msc-avengers-assemble.md) retires in
  the same pull request. Recommended, so the review stays one mechanic and the
  precon item retires with it.
