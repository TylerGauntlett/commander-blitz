"""An Aura that enchants a creature card in a graveyard: Animate Dead.

    303.4a An Aura spell requires a target, which is defined by its enchant
    ability.

    608.3b If the object that's resolving is an Aura spell, its resolution
    involves two steps. First, it checks whether the target specified by its
    enchant ability is still legal […]. If so, the spell card becomes a
    permanent and is put onto the battlefield under the control of the spell's
    controller attached to the object it was targeting.

    704.5m If an Aura is attached to an illegal object or player, or is not
    attached to an object or player, that Aura is put into its owner's
    graveyard.

"Enchant creature card in a graveyard" makes a *card* the host. The Aura is
cast targeting it, resolves attached to it in the graveyard, and is a legal
Aura there, so the state-based action leaves it alone while its enters trigger
waits on the stack. The trigger -- "if it's on the battlefield", an
intervening-if (603.4) -- returns that card under the Aura's controller and
attaches the Aura to it; the Aura's leaves-the-battlefield trigger has "that
creature's controller" sacrifice it, and "enchanted creature gets -1/-0" is an
ordinary static.

Without this an Aura's host had to be on the battlefield: `primitives.attach`
refused the card, `sba` binned the Aura before its trigger resolved, and
nothing linked the Aura's leaves trigger to the creature it returned.

The engine reads the printed swap of enchant abilities as two hosts in two
zones: `zones.graveyard_hosts` is the graveyard clause, asked only of a host in
a graveyard, and once the creature is on the battlefield nothing re-tests an
Aura's clause (`docs/rules-coverage.md`), which is what "enchant creature put
onto the battlefield with this Aura" amounts to. A card that leaves the
graveyard is a new object wherever it lands (400.7), so `move_object` takes
the Aura off it. "That creature" is `return_from_graveyard`'s ``link``, read
back by ``{"returned_with": "self"}``.

The Gatherer rulings this pins: a target card gone before the Aura resolves
counters it; Animate Dead not on the battlefield as its trigger resolves
returns nothing; a returned creature it can't legally enchant (protection from
black) still returns, the Aura goes to the graveyard, and the creature is
sacrificed by the leaves trigger. The witness is Animate Dead.
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
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.zones import destroy, move_object
from tests.conftest import pass_until, pt, settle

ANIMATE = "t_animate_dead"
PRO_BLACK = "t_ad_white_knight"
BEAR = "t_bear"  # a vanilla 2/2
PLAIN_AURA = "t_eb_aura"  # "Enchant creature" and nothing else
ISLAND = "island"
INSTANT = "t_plain_instant"  # {W}: you gain 1 life


def position(builder, *, mine=(), theirs=(), graveyard=(), their_graveyard=(), hand=(ANIMATE,)):
    """Player 0 with two Swamps and ``hand`` facing player 1, in a main phase.

    A Plains and an instant beside it, so player 0 has something to do with
    priority and the engine stops there with the Aura or its trigger on the
    stack instead of passing straight through.
    """
    b = (
        builder(players=2)
        .battlefield(0, ["swamp", "swamp", "plains", *mine])
        .battlefield(1, list(theirs))
        .hand(0, [*hand, INSTANT])
    )
    if graveyard:
        b.graveyard(0, list(graveyard))
    if their_graveyard:
        b.graveyard(1, list(their_graveyard))
    return b.active(0).step(Step.PRECOMBAT_MAIN).build()


def card_oid(game, card_id: str, owner: int = 0, zone: Zone | None = None) -> int:
    """The one ``card_id`` ``owner`` owns, in ``zone`` if one is named."""
    (oid,) = [
        o.oid
        for o in game.state.objects.values()
        if o.def_id == card_id and o.owner == owner and zone in (None, o.zone)
    ]
    return oid


def casts(game, aura: int) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == aura]


def cast_at(game, aura: int, host: int) -> None:
    (action,) = [a for a in casts(game, aura) if [r.id for r in a.targets] == [host]]
    game.apply(action)


def trigger_waiting(game, aura: int) -> None:
    """Pass until the Aura has resolved and its enters trigger is on the stack."""
    pass_until(
        game,
        lambda g: g.state.objects[aura].zone is Zone.BATTLEFIELD
        and any(item.source_oid == aura and not item.is_spell for item in g.state.stack),
    )


def run(game, effects, *, source=None):
    """Resolve ``effects`` for player 0, answering every question with its first
    option, then the state-based actions."""
    gen = execute(EffectContext(state=game.state, controller=0, source_oid=source), effects)
    answer = None
    while True:
        try:
            gen.send(answer)
        except StopIteration:
            break
        answer = [0]
    sba.run(game.state)


class TestCasting:
    def test_it_targets_a_creature_card_in_any_graveyard(self, builder):
        """Mine and the opponent's Bear in the graveyards are offered; the
        Bear on the battlefield and the Island in a graveyard are not."""
        game = position(builder, mine=[BEAR], graveyard=[BEAR, ISLAND], their_graveyard=[BEAR])
        aura = card_oid(game, ANIMATE)
        mine = card_oid(game, BEAR, 0, Zone.GRAVEYARD)
        theirs = card_oid(game, BEAR, 1)

        offered = {r.id for a in casts(game, aura) for r in a.targets}

        assert offered == {mine, theirs}

    def test_nothing_in_a_graveyard_no_cast(self, builder):
        game = position(builder, mine=[BEAR])
        assert casts(game, card_oid(game, ANIMATE)) == []


class TestResolution:
    def test_it_resolves_attached_to_the_card_and_survives_the_sba(self, builder):
        """608.3b: on the battlefield, enchanting the card in the graveyard, and
        a legal Aura there while its trigger waits (704.5m)."""
        game = position(builder, graveyard=[BEAR])
        aura, bear = card_oid(game, ANIMATE), card_oid(game, BEAR)
        cast_at(game, aura, bear)

        trigger_waiting(game, aura)
        sba.run(game.state)

        assert game.state.objects[aura].zone is Zone.BATTLEFIELD
        assert game.state.objects[aura].attached_to == bear
        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_the_trigger_returns_it_enchanted_and_minus_one(self, builder):
        game = position(builder, graveyard=[BEAR])
        aura, bear = card_oid(game, ANIMATE), card_oid(game, BEAR)
        cast_at(game, aura, bear)

        settle(game)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].controller == 0
        assert game.state.objects[aura].attached_to == bear
        assert pt(game, bear) == (1, 2)

    def test_an_opponents_card_returns_under_your_control(self, builder):
        game = position(builder, their_graveyard=[BEAR])
        aura, bear = card_oid(game, ANIMATE), card_oid(game, BEAR, 1)
        cast_at(game, aura, bear)

        settle(game)

        obj = game.state.objects[bear]
        assert obj.zone is Zone.BATTLEFIELD
        assert (obj.owner, obj.controller) == (1, 0)
        assert game.state.objects[aura].attached_to == bear


class TestTheLinkedPair:
    def _animated(self, builder, **kw):
        game = position(builder, **kw)
        aura = card_oid(game, ANIMATE)
        bear = next(
            o.oid
            for o in game.state.objects.values()
            if o.def_id == BEAR and o.zone is Zone.GRAVEYARD
        )
        cast_at(game, aura, bear)
        settle(game)
        return game, aura, bear

    def test_the_aura_leaving_sacrifices_the_creature(self, builder):
        game, aura, bear = self._animated(builder, their_graveyard=[BEAR])

        destroy(game.state, aura)
        settle(game)

        assert game.state.objects[aura].zone is Zone.GRAVEYARD
        assert bear in game.state.players[1].graveyard, "to its owner's graveyard"
        (sacrificed,) = [
            e for e in game.state.events if e.type == EventType.SACRIFICED and e.source == bear
        ]
        assert sacrificed.player == 0, "sacrificed by its controller, not its owner"

    def test_the_creature_leaving_puts_the_aura_into_the_graveyard(self, builder):
        game, aura, bear = self._animated(builder, graveyard=[BEAR])

        destroy(game.state, bear)
        sba.run(game.state)

        assert game.state.objects[aura].zone is Zone.GRAVEYARD
        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_a_creature_that_left_and_came_back_is_not_that_creature(self, builder):
        """400.7: flickered, it is a new object the Aura did not return."""
        game, aura, bear = self._animated(builder, graveyard=[BEAR])
        move_object(game.state, bear, Zone.EXILE)
        move_object(game.state, bear, Zone.BATTLEFIELD, to_player=0)
        settle(game)

        destroy(game.state, aura)
        settle(game)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_only_the_creature_it_returned(self, builder):
        """A second Bear on the battlefield is not "that creature"."""
        game, aura, bear = self._animated(builder, mine=[BEAR], graveyard=[BEAR])
        other = next(
            o.oid for o in game.state.objects.values() if o.def_id == BEAR and o.oid != bear
        )

        destroy(game.state, aura)
        settle(game)

        assert game.state.objects[other].zone is Zone.BATTLEFIELD


class TestIfItsOnTheBattlefield:
    def test_an_aura_gone_before_its_trigger_resolves_returns_nothing(self, builder):
        """603.4: the intervening-if is asked again, and the card stays put."""
        game = position(builder, graveyard=[BEAR])
        aura, bear = card_oid(game, ANIMATE), card_oid(game, BEAR)
        cast_at(game, aura, bear)
        trigger_waiting(game, aura)

        destroy(game.state, aura)
        settle(game)

        assert game.state.objects[aura].zone is Zone.GRAVEYARD
        assert game.state.objects[bear].zone is Zone.GRAVEYARD


class TestTheCardLeavesTheGraveyard:
    def test_before_the_spell_resolves_it_is_countered(self, builder):
        """608.2b: the only target is gone, so the Aura never enters."""
        game = position(builder, graveyard=[BEAR])
        aura, bear = card_oid(game, ANIMATE), card_oid(game, BEAR)
        cast_at(game, aura, bear)
        move_object(game.state, bear, Zone.EXILE)

        settle(game)

        assert game.state.objects[aura].zone is Zone.GRAVEYARD
        assert game.state.objects[bear].zone is Zone.EXILE
        assert not any(
            e.type == EventType.ENTERS_BATTLEFIELD and e.source == aura for e in game.state.events
        )

    def test_while_the_trigger_waits_the_aura_falls_off_and_nothing_returns(self, builder):
        game = position(builder, graveyard=[BEAR])
        aura, bear = card_oid(game, ANIMATE), card_oid(game, BEAR)
        cast_at(game, aura, bear)
        trigger_waiting(game, aura)

        move_object(game.state, bear, Zone.EXILE)
        settle(game)

        assert game.state.objects[aura].zone is Zone.GRAVEYARD
        assert game.state.objects[bear].zone is Zone.EXILE

    def test_reanimated_by_something_else_it_is_a_new_object(self, builder):
        """The card put onto the battlefield by another effect is not the card
        the Aura enchanted (400.7): the Aura is binned, the creature stays."""
        game = position(builder, graveyard=[BEAR])
        aura, bear = card_oid(game, ANIMATE), card_oid(game, BEAR)
        cast_at(game, aura, bear)
        trigger_waiting(game, aura)

        move_object(game.state, bear, Zone.BATTLEFIELD, to_player=0)
        settle(game)

        assert game.state.objects[aura].zone is Zone.GRAVEYARD
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert pt(game, bear) == (2, 2)


class TestProtection:
    def test_a_creature_it_cannot_enchant_returns_and_is_sacrificed(self, builder):
        """Protection from black: the card is targetable in the graveyard
        (protection works on the battlefield, 113.6) and returns, the attach is
        refused (702.16c), the Aura is put into the graveyard (704.5m), and its
        leaves trigger sacrifices the creature."""
        game = position(builder, graveyard=[PRO_BLACK])
        aura, knight = card_oid(game, ANIMATE), card_oid(game, PRO_BLACK)
        cast_at(game, aura, knight)

        settle(game)

        assert game.state.objects[aura].zone is Zone.GRAVEYARD
        assert game.state.objects[knight].zone is Zone.GRAVEYARD
        assert any(
            e.type == EventType.ENTERS_BATTLEFIELD and e.source == knight for e in game.state.events
        )


class TestPutOntoTheBattlefieldUncast:
    """303.4f: returned from a graveyard by an effect naming no host, the Aura
    chooses a creature card in a graveyard as it enters, and its trigger
    returns that card."""

    REANIMATE_AURA = [
        {
            "op": "return_from_graveyard",
            "destination": "battlefield",
            "objects": {"zone": "graveyard", "subtypes": ["Aura"], "count": 1},
        }
    ]

    def test_it_chooses_a_graveyard_card_and_returns_it(self, builder):
        game = position(builder, mine=[BEAR], graveyard=[ANIMATE], their_graveyard=[BEAR], hand=())
        aura, theirs = card_oid(game, ANIMATE), card_oid(game, BEAR, 1)

        run(game, self.REANIMATE_AURA)
        assert game.state.objects[aura].attached_to == theirs
        settle(game)

        assert game.state.objects[theirs].zone is Zone.BATTLEFIELD
        assert game.state.objects[theirs].controller == 0
        assert game.state.objects[aura].attached_to == theirs

    def test_with_no_creature_card_in_a_graveyard_it_stays(self, builder):
        """303.4g: the Bear on the battlefield is no host for this clause."""
        game = position(builder, mine=[BEAR], graveyard=[ANIMATE], hand=())
        aura = card_oid(game, ANIMATE)

        run(game, self.REANIMATE_AURA)

        assert game.state.objects[aura].zone is Zone.GRAVEYARD


class TestOnlyThisClause:
    def test_an_enchant_creature_aura_cannot_enchant_a_card(self, builder):
        game = position(builder, mine=[PLAIN_AURA], graveyard=[BEAR], hand=())
        plain, bear = card_oid(game, PLAIN_AURA), card_oid(game, BEAR)

        assert attach(game.state, plain, bear) is False
        assert game.state.objects[plain].attached_to is None


def _probe(effects):
    return CardModel.model_validate(
        {
            "id": "t_bad_link",
            "name": "Bad Link",
            "types": ["Sorcery"],
            "mana_cost": "{1}",
            "spell_effects": effects,
        }
    )


class TestTheLoaderRefuses:
    @pytest.mark.parametrize(
        "effect",
        [
            {"op": "return_from_graveyard", "destination": "hand", "link": True, "objects": {}},
            {"op": "return_from_graveyard", "destination": "battlefield", "link": "yes"},
        ],
    )
    def test_link_off_the_battlefield_or_not_a_boolean(self, effect):
        with pytest.raises(DslError, match="link"):
            compile_card(_probe([effect]))

    def test_returned_with_names_only_self(self):
        effect = {"op": "sacrifice", "objects": {"returned_with": 7}}
        with pytest.raises(DslError, match="returned_with"):
            compile_card(_probe([effect]))
