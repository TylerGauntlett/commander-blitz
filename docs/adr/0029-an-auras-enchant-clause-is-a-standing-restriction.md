# ADR 0029 — An Aura's enchant clause is a standing restriction

**Status:** accepted

## Context

An Aura's enchant ability (702.5) is its first target spec. The engine read it
only as an Aura arrived: the spell's target when cast, re-checked on resolution
(608.2b), and the host pool `zones.offer_aura_host` and `zones.offer_named_host`
build when it is put onto the battlefield uncast (303.4f). Once attached, nothing
asked again, and `sba` put an Aura away only when its host had left the
battlefield or its seat had left the game.

The rules make the clause standing. 303.4d restricts what an Aura may be
attached to for as long as it is on the battlefield, and 704.5m puts one
attached to an illegal object or player into its owner's graveyard. Daybreak
Coronet ("Enchant creature with another Aura attached to it") is the card the
arrival-only reading cannot express: once the other Aura leaves, the Coronet
must go. The same reading is wrong for every clause that can stop holding,
"enchant creature you control" on a stolen creature, "enchant opponent" on the
seat that gains control of it, and "enchant creature" on a host that stops being
a creature.

## Decision

`sba._tokens_and_attachments` asks `zones.enchant_clause_holds` of every printed
Aura on the battlefield, and puts one whose clause no longer holds into its
owner's graveyard. The clause is the Aura's first target spec, matched against
its one host for the Aura's controller now: a permanent host through
`selectors.matches`, a seat through the spec's player words.

Three Auras are not re-tested. One with no clause written (a Role, attached by
the op that made it); "enchant creature card in a graveyard" (Animate Dead),
whose battlefield clause is "the creature put onto the battlefield with this
Aura" and whose graveyard host stays `zones.graveyard_hosts`' question; and a
printed non-Aura that became one (`become_aura`, Necromancy), for the same
reason. Protection is not re-tested here; it is checked as the Aura attaches.

"Another Aura" is `enchanted_by: {"exclude_self": true}`, in the effect selector
only, where the reader knows the ability's source.

## Consequences

**Good.** Every enchant clause the pool writes holds for as long as the Aura
stays, so no Aura keeps granting its bonus to a host it may not enchant. The pool
was inspected before the change: every Aura's first target spec reads only
`types`, `any_types`, `subtypes`, `controller` and `zone`, which are all enchant
qualities, so no card's cast-time-only targeting restriction is made standing
by accident.

**Bad.** The first target spec is now a standing filter, so a card that wrote a
cast-only restriction there (a "target creature that attacked this turn" Aura)
would fall off when the restriction stopped holding. No printed Aura has such a
line; one that does must split the clause from the target. A test fixture that
attaches an Aura to a host its clause refuses sees it binned.

**Cost of reversing.** Small in code and wrong in play: dropping the
`enchant_clause_holds` call returns Daybreak Coronet to a permanent +3/+3 after
its other Aura is gone. `tests/unit/attachments/test_enchant_restriction.py`
pins the Coronet, the stolen host and the "enchant opponent" seat.

## Alternatives considered

**A check written for Daybreak Coronet alone.** Would leave "enchant creature
you control" and "enchant opponent" wrong and need a second mechanism for the
next clause that can stop holding.

**Re-testing protection in the same pass (702.16c).** Also 704.5m, but a
different reader with its own exceptions (`spares: "self"`), and no card waits
on it.
