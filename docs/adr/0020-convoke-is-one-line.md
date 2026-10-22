# ADR 0020 — Convoke and delve are one cast line; the pick is asked while paying

**Status:** accepted

[ADR 0002](0002-flat-action-space.md) makes every choice that changes an
action's price part of the action. This ADR is the one place that rule is
deliberately not applied, and why.

## Context

Convoke and delve were offered as one cast line per number spent — zero, one,
two… up to the generic cost — each multiplied by every target tuple. Which
creatures tapped, or which cards were exiled, was then asked as a separate pick
anyway. So the panel drew a card like Cleaver Concealment once per count, and
choosing a row still did not finish the choice. A tap cost with a fixed count
(Captivating Vampire's five Vampires) was always one action and a pick, and
read the way players expect.

## Decision

**One cast line, carrying the fewest the cast must spend; the creatures or
cards are a `CHOOSE_OBJECTS` asked by `Game._cast` as the spell is paid for.**

- `casting._cast_options` offers the printed line when the mana alone pays,
  and otherwise the line at the smallest spend that does, per target tuple.
  `Action.pay_generic` is that floor, not the amount spent.
- `Game._ask_pay_generic` asks between the floor and what the generic part can
  absorb, before X — X's ceiling is what the mana has left once this is spent.
- Convoked creatures are tapped **before** the mana is paid, so the payment
  cannot also tap one of them for mana. A pick that would leave the rest
  unpayable (it convoked the creature the mana needed) is asked again, a bounded
  number of times (`MAX_PAY_GENERIC_ASKS`), and then picked for the player,
  creatures that make no mana first.

## Consequences

- The panel draws one row per convoke or delve card, as ADR 0015 expects.
- A training policy no longer chooses the count as an action index; it answers
  the pick like any other `CHOOSE_OBJECTS`.
- Replicate and other repeatable additional costs keep one line per count:
  there the count changes what the spell *does*, not only what it costs.

## Rejected

- **Keep one line per count and collapse them in the client.** The client
  would be reconstructing a rules choice from several ids, which ADR 0015
  exists to stop.
- **Ask after the mana, as before.** The amount spent must be known before the
  mana is paid, and the mana payment would be free to tap a creature the
  player meant to convoke.
