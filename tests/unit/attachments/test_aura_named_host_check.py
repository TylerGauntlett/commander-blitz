"""An Aura put onto the battlefield attached to a host the effect names must be
able to enchant it, or it stays where it was (303.4f, 303.4g).

    303.4f ... If the effect putting it onto the battlefield specifies the
    object or player the Aura will enchant, ... [it] must be legal according
    to the Aura's enchant ability and any other applicable effects.

    303.4g If an Aura is entering the battlefield and there is no legal object
    or player for it to enchant, the Aura remains in its current zone, unless
    that zone is the stack.

Unfinished Business prints it: "...then return up to two target Aura and/or
Equipment cards from your graveyard to the battlefield attached to that
creature. (If the Auras can't enchant that creature, they remain in your
graveyard.)" ``host_named`` on `return_from_graveyard` and
`put_onto_battlefield` is that host, as a selector, and
`zones.offer_named_host` holds it to the test `zones.offer_aura_host` builds
its choice from: the Aura's first target spec, read for the player it enters
under, less protection (702.16c). Without it the host was trusted -- an
"Enchant land" Aura came back hanging on a creature, and one that a creature's
protection should have refused entered, triggered and went to the graveyard by
state-based action, a zone change the rules never allow.

What would be wrong without each claim below:

- **A legal host is enchanted as the Aura enters**, with no question asked and
  before ENTERS_BATTLEFIELD, so no enters trigger sees it unattached.
- **An illegal one keeps the Aura in its zone**: an enchant clause the host
  fails ("Enchant land", "Enchant opponent"), protection, or no host at all.
  The Aura never enters, so no ENTERS_BATTLEFIELD is emitted for it.
- **An Equipment always enters**, attached when it can be and unattached when
  the named host is gone.
- **The loader refuses** a boolean, the old spelling that named no host, and a
  target the card does not declare.

The witnesses are Unfinished Business, and Forum Filibuster ("...attached to
that token") and Gift of Immortality ("...attached to that creature"), which
name their host the same way.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import TempEffect
from tests.conftest import declare_targets, only_oid, settle

UNFINISHED = "unfinished_business"
AURA = "t_eb_aura"  # white, "Enchant creature"
LAND_AURA = "t_wild_growth"  # "Enchant land"
CURSE = "t_encumber"  # "Enchant opponent"
GEAR = "t_gear_shield"  # Equipment, "Equipped creature gets +0/+3"
BEAR = "t_bear"


def return_named(*, host=None, op="return_from_graveyard", zone="graveyard"):
    """Return every Aura and Equipment card in ``zone`` attached to the
    creature bound as ``host`` -- Unfinished Business's second half."""
    spec = {
        "op": op,
        "host_named": {"binding": "host", "zone": "battlefield"},
        "objects": {"zone": zone, "subtypes": ["Aura", "Equipment"], "count": "all"},
    }
    if op == "return_from_graveyard":
        spec["destination"] = "battlefield"
    return [spec]


def position(builder, *, mine=(), theirs=(), graveyard=(), hand=()):
    b = builder(players=2).battlefield(0, list(mine)).battlefield(1, list(theirs))
    if graveyard:
        b.graveyard(0, list(graveyard))
    if hand:
        b.hand(0, list(hand))
    return b.active(0).step(Step.PRECOMBAT_MAIN).build(advance=False)


def run(game, effects, host: int | None):
    """Resolve ``effects`` for player 0 with ``host`` bound, then the
    state-based actions. Returns every decision asked."""
    ctx = EffectContext(
        state=game.state, controller=0, bindings={"host": [] if host is None else [host]}
    )
    gen = execute(ctx, effects)
    asked, answer = [], None
    while True:
        try:
            decision = gen.send(answer)
        except StopIteration:
            break
        asked.append(decision)
        answer = [0]
    sba.run(game.state)
    return asked


def card(game, card_id: str):
    (obj,) = [o for o in game.state.objects.values() if o.def_id == card_id]
    return obj


def entered(game, card_id: str) -> bool:
    oid = card(game, card_id).oid
    return any(
        e.type == EventType.ENTERS_BATTLEFIELD and e.source == oid for e in game.state.events
    )


class TestALegalHostIsEnchanted:
    def test_the_aura_enters_attached_and_nothing_is_asked(self, builder):
        game = position(builder, mine=[BEAR], theirs=[BEAR], graveyard=[AURA])
        theirs = only_oid(game, BEAR, 1)

        asked = run(game, return_named(), host=theirs)

        aura = card(game, AURA)
        assert asked == []
        assert aura.zone is Zone.BATTLEFIELD and aura.attached_to == theirs

    def test_put_onto_battlefield_reads_it_too(self, builder):
        game = position(builder, mine=[BEAR], hand=[AURA])
        bear = only_oid(game, BEAR, 0)

        run(game, return_named(op="put_onto_battlefield", zone="hand"), host=bear)

        assert card(game, AURA).attached_to == bear


class TestAnIllegalHostLeavesTheAuraWhereItWas:
    @pytest.mark.parametrize("aura", [LAND_AURA, CURSE], ids=["enchant_land", "enchant_opponent"])
    def test_a_clause_the_host_fails(self, builder, aura):
        game = position(builder, mine=[BEAR, "forest"], graveyard=[aura])

        run(game, return_named(), host=only_oid(game, BEAR, 0))

        assert card(game, aura).zone is Zone.GRAVEYARD
        assert not entered(game, aura), "it never entered, so nothing saw it arrive"

    def test_protection(self, builder):
        """702.16c: protection from white can't be enchanted by a white Aura."""
        game = position(builder, mine=[BEAR], graveyard=[AURA])
        bear = only_oid(game, BEAR, 0)
        game.state.objects[bear].until_eot.append(
            TempEffect(kind="protection", keyword="W", timestamp=game.state.alloc_timestamp())
        )
        game.state.bump_chars()

        run(game, return_named(), host=bear)

        assert card(game, AURA).zone is Zone.GRAVEYARD
        assert not entered(game, AURA)

    def test_no_host_at_all(self, builder):
        """The named creature never arrived: there is nothing legal to enchant."""
        game = position(builder, graveyard=[AURA])

        run(game, return_named(), host=None)

        assert card(game, AURA).zone is Zone.GRAVEYARD


class TestAnEquipmentAlwaysEnters:
    def test_attached_to_the_named_host(self, builder):
        game = position(builder, mine=[BEAR], graveyard=[GEAR])
        bear = only_oid(game, BEAR, 0)

        run(game, return_named(), host=bear)

        assert card(game, GEAR).attached_to == bear

    def test_unattached_when_the_host_is_gone(self, builder):
        game = position(builder, graveyard=[GEAR])

        run(game, return_named(), host=None)

        gear = card(game, GEAR)
        assert gear.zone is Zone.BATTLEFIELD and gear.attached_to is None


class TestUnfinishedBusiness:
    def cast(self, builder, *returned):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 5)
            .hand(0, [UNFINISHED])
            .graveyard(0, [BEAR, *returned])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST)
        game.apply(action)
        declare_targets(game, *(card(game, c).oid for c in returned))
        settle(game)
        return game

    def test_the_creature_returns_wearing_both(self, builder):
        game = self.cast(builder, AURA, GEAR)
        bear = card(game, BEAR)

        assert bear.zone is Zone.BATTLEFIELD
        assert card(game, AURA).attached_to == bear.oid
        assert card(game, GEAR).attached_to == bear.oid

    def test_the_aura_it_cant_wear_stays_in_the_graveyard(self, builder):
        game = self.cast(builder, LAND_AURA, GEAR)

        assert card(game, LAND_AURA).zone is Zone.GRAVEYARD
        assert card(game, GEAR).attached_to == card(game, BEAR).oid


class TestTheLoader:
    @pytest.mark.parametrize(
        ("named", "match"),
        [
            (True, "selector naming the host"),
            ({"target": "t9", "zone": "battlefield"}, "does not declare"),
        ],
        ids=["boolean", "undeclared_target"],
    )
    def test_refuses(self, named, match):
        model = CardModel.model_validate(
            {
                "id": "t_bad_named_host",
                "name": "Bad Named Host",
                "types": ["Sorcery"],
                "mana_cost": "{1}",
                "spell_effects": [
                    {
                        "op": "return_from_graveyard",
                        "destination": "battlefield",
                        "host_named": named,
                        "objects": {"zone": "graveyard", "subtypes": ["Aura"]},
                    }
                ],
            }
        )
        with pytest.raises(DslError, match=match):
            compile_card(model)
