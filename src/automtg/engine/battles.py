"""Battles (rule 310) -- the defense counter, being attacked, and being defeated.

A Battle is the fifth permanent type, and like a Saga almost nothing that makes
one work is printed on the card. The card prints a number in a box and the
*rules* turn it into counters, make the permanent a third thing a creature may
be declared as attacking, send combat damage onto those counters, and bin it
when the last one comes off. So this module is where those behaviours live, in
the same sense that :mod:`sagas` holds a Saga's three, `turn` holds the
monarch's end-step draw and `sba` holds the legend rule -- see the Sagas entry
in ``docs/rules-coverage.md``, which is the worked precedent for a card type
whose behaviour is rules-supplied rather than compiled from any card.

The four pieces, and where each one had to go:

``DEFENSE`` as it enters (310.3)
    A ``self_enters_with_counters`` replacement compiled by the loader from
    ``defense``, exactly as a planeswalker's starting loyalty and a Saga's first
    lore counter are. Defense **is** counters (310.4), so `counters_on`,
    `proliferate`, `move_counters` and the client's counter badge all read a
    battle for free, and there is no new characteristic for anything to forget
    to read.

Being attacked (506.2, 508.1)
    `combat.legal_permanent_defenders` and `combat.attacking_permanent`, which
    already existed for planeswalkers and were named for them. A battle is the
    *same* declaration slot: `attackers[oid]` stays the defending player, and
    only damage assignment has to know which permanent is on the other end.

Damage removes defense (310.6)
    `primitives.damage_permanent`, beside the planeswalker's loyalty branch and
    for the same reason it is there: marking `obj.damage` on a battle would be
    invisible, because nothing compares a battle's damage to anything, so it
    would take damage for ever and never be defeated.

Being defeated (704.5x)
    :func:`defeated`, asked by the state-based-action pass. Not destruction, so
    it goes through `move_object` and indestructible does not save it -- the
    same shape as zero loyalty and zero toughness.

**What is deliberately not here: protectors** (310.7, 506.2b). A Siege enters
with an opponent designated as its protector, that protector is the defending
player when the Siege is attacked, and defeating it lets the Siege's controller
cast its back face. None of that is modelled. The consequences are written down
rather than papered over:

* A battle is attackable by the people who could attack **its controller**, the
  planeswalker rule applied unchanged. In a real game you attack the Siege you
  control, because its protector is your opponent; here your opponents attack
  it. This is loudly the wrong way round rather than quietly, and it is the one
  divergence that a protector would fix outright.
* Defeating a battle puts it in its owner's graveyard and nothing else happens.
  No back face is cast, because transforming battles are two-faced cards whose
  back is a *cast* trigger on defeat, and that is a second subsystem.
* A battle prints no abilities the engine supplies. Everything it does beyond
  arriving, being attacked, losing counters and dying is on the card.

So a battle here is an honest permanent with a life total that combat can chew
through -- enough for "deal combat damage to a player **or battle**" to mean
something, and not enough to call Sieges implemented.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .characteristics import chars

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState

#: The counter kind a battle's defense is measured in (310.4). A string like
#: every other counter kind, which is the whole reason proliferate and
#: `counters_on` need no change.
DEFENSE = "defense"

#: The one battle subtype in print. Recorded for the type line and for readers
#: looking for the protector rules this module does not implement; nothing here
#: branches on it, because 310 applies to every battle and the subtype is what
#: adds the protector, not what makes it a battle.
SIEGE = "Siege"


def is_battle(state: GameState, oid: int) -> bool:
    """Whether this permanent is a battle **now**.

    Read off `chars` rather than off the printed card, for the reason
    `sagas.is_saga` reads the subtype off `chars`: type is a characteristic and
    a continuous effect can add or remove one, so the printed face is the wrong
    thing to ask. There is no second half to this test the way there is for a
    Saga -- 310 needs no abilities on the card, only the type.
    """
    return "Battle" in chars(state, oid).types


def defeated(state: GameState, oid: int) -> bool:
    """704.5x: has this battle run out of defense counters?

    310.5 says a battle with no defense counters on it has defense 0, so "no
    counters" and "zero defense" are the same question -- the same equivalence
    306.5b makes for loyalty, and the reason the planeswalker state-based action
    is written this way too.

    A battle that entered with **no** defense counters is defeated the instant
    it resolves, and that is deliberate: a `defense` the card did not print is a
    card that cannot exist, and binning it is visible where letting it sit on the
    battlefield for ever is not. `proxy.starting_point` says so out loud for the
    same reason it says it about a planeswalker with no printed loyalty.

    **Divergence from 704.5x**: the rule spares a battle that "is the source of
    an ability that has triggered but not yet left the stack". Nothing in the
    engine's battles triggers on anything, so there is no such ability to wait
    for; when one exists, this is the line that has to learn about it.
    """
    obj = state.objects.get(oid)
    return obj is not None and obj.counter(DEFENSE) <= 0
