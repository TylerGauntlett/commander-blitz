"""The fight keyword action (701.12).

    "Target creature you control fights another target creature."
        -- Ulvenwald Tracker, and Bridgeworks Battle's second sentence.

Two sequential `damage` ops are the near miss, and the reason this is an op of
its own rather than that shorthand is three separate rules:

- **701.12a is simultaneous.** Both powers are read before either blow lands, so
  a creature that dies in the exchange still deals its damage. Written as two
  ops in sequence, a 3/3 kills a 2/2 and walks away untouched -- a strictly
  better card than the one printed, which is the failure mode the authoring
  gates exist to catch.
- **701.12c is all-or-nothing.** If either creature has left the battlefield by
  the time the fight would happen, *neither* deals damage. The sequential
  spelling fires whichever half still has a legal subject.
- **The damage is dealt by the creatures**, not by the spell. That is what makes
  lifelink on a fighter gain its controller life and deathtouch on it lethal,
  and `damage`'s `source_object` can only name one dealer at a time.

701.12d -- a creature cannot fight itself. Targeting already refuses the same
permanent for two separate target slots, so the reachable mistake is a card that
points both halves of the op at one *binding*; `t_self_fighter` is that card,
kept in the pool so the rule is measured rather than assumed.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.ops_life import op_fight
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from automtg.engine.zones import destroy
from tests.conftest import oids_of, pass_until

SPELL = "t_fighter"  # "target creature you control fights another target creature"
SELF = "t_self_fighter"  # both halves of the op on one binding

BEAR = "t_f_2_2"
OGRE = "t_f_3_3"
DORK = "t_f_1_1"
WALL = "t_f_0_4"
LIFELINK = "t_f_lifelink"  # 3/3
ADDER = "t_f_deathtouch"  # 1/1


def position(builder, mine, theirs, spell=SPELL):
    """The spell in hand, ``mine`` on your board, ``theirs`` on the opponent's."""
    game = (
        builder(players=2)
        .battlefield(0, [*mine, "forest", "forest"])
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 10)
        .hand(0, [spell])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def put_on_stack(game, card_id: str, *targets: int) -> None:
    """Cast ``card_id`` at ``targets`` and stop, leaving it on the stack."""
    action = next(
        act
        for act in game.legal_actions()
        if act.kind is ActionKind.CAST
        and game.state.objects[act.source].def_id == card_id
        and [t.id for t in act.targets] == list(targets)
    )
    game.apply(action)


def cast_at(game, card_id: str, *targets: int) -> None:
    """Cast ``card_id`` with its targets, and let the stack settle."""
    put_on_stack(game, card_id, *targets)
    settle(game)


def settle(game) -> None:
    """Resolve the stack and stop, without letting the turn reach cleanup.

    Marked damage is wiped at cleanup (514.2), so a survivor's damage is only
    readable inside the turn it was dealt -- passing one step too far turns
    every "it took two and lived" assertion into a silent zero.
    """
    turn, step = game.state.turn, game.state.step
    pass_until(
        game,
        lambda g: (not g.state.stack)
        or g.state.turn != turn
        or g.state.step != step,
    )


def fight(game, a_id: str, b_id: str, *, spell=SPELL):
    """Cast the fight spell pointing ``a`` (yours) at ``b`` (theirs)."""
    a = oids_of(game, a_id, 0)[0]
    b = oids_of(game, b_id, 1)[0]
    cast_at(game, spell, a, b)
    return a, b


def alive(game, oid: int) -> bool:
    obj = game.state.objects.get(oid)
    return obj is not None and obj.zone is Zone.BATTLEFIELD


def marked(game, oid: int) -> int:
    obj = game.state.objects.get(oid)
    return obj.damage if obj is not None else -1


class TestBothDealDamage:
    def test_each_marks_the_other_with_its_power(self, builder):
        game = position(builder, [BEAR], [WALL])
        bear, wall = fight(game, BEAR, WALL)
        assert marked(game, wall) == 2, "the 2/2 dealt its two"
        assert marked(game, bear) == 0, "the 0/4 dealt nothing"

    def test_a_bigger_creature_kills_a_smaller_one(self, builder):
        game = position(builder, [OGRE], [BEAR])
        _, bear = fight(game, OGRE, BEAR)
        assert not alive(game, bear)

    def test_they_can_kill_each_other(self, builder):
        game = position(builder, [BEAR], [BEAR])
        mine, theirs = fight(game, BEAR, BEAR)
        assert not alive(game, mine)
        assert not alive(game, theirs)


class TestTheExchangeIsSimultaneous:
    """701.12a. The claim that two sequential `damage` ops would get wrong."""

    def test_the_creature_that_dies_still_dealt_its_damage(self, builder):
        game = position(builder, [OGRE], [BEAR])
        ogre, bear = fight(game, OGRE, BEAR)
        assert not alive(game, bear), "the 2/2 died to the 3/3"
        assert marked(game, ogre) == 2, "and dealt its two on the way out"

    def test_a_deathtoucher_trades_with_anything(self, builder):
        """The sharpest form: the 1/1 dies, and its one point is still lethal.

        Sequenced the other way round it would be dead before it struck.
        """
        game = position(builder, [OGRE], [ADDER])
        ogre, adder = fight(game, OGRE, ADDER)
        assert not alive(game, adder)
        assert not alive(game, ogre)


class TestTheDamageIsDealtByTheCreatures:
    def test_lifelink_on_a_fighter_gains_its_controller_life(self, builder):
        """Not the spell's controller by coincidence -- the creature's.

        If the spell were the source this would gain nothing at all, since the
        sorcery has no lifelink.
        """
        game = position(builder, [LIFELINK], [WALL])
        before = game.state.players[0].life
        fight(game, LIFELINK, WALL)
        assert game.state.players[0].life == before + 3

    def test_an_opponents_lifelinker_gains_the_opponent_life(self, builder):
        game = position(builder, [BEAR], [LIFELINK])
        before = game.state.players[1].life
        fight(game, BEAR, LIFELINK)
        assert game.state.players[1].life == before + 3


class TestNeitherDealsDamageIfOneIsGone:
    """701.12c, and the reason it is all-or-nothing rather than best-effort.

    Asserted against the op directly. The rule is about the moment the fight
    *would* happen, and a creature that has left the battlefield by then can no
    longer be targeted, so there is no way to cast the spell into this state --
    the removal has to land while the fight is already resolving, which is where
    a fight granted by a trigger or an ability on the stack really does arrive.
    """

    def run(self, game, a: int, b: int) -> None:
        op_fight(
            EffectContext(
                state=game.state,
                controller=0,
                targets={
                    "a": (TargetRef(kind="object", id=a),),
                    "b": (TargetRef(kind="object", id=b),),
                },
            ),
            {"objects": {"target": "a"}, "other": {"target": "b"}},
        )

    def test_the_survivor_takes_nothing(self, builder):
        """Sequenced as two `damage` ops the surviving half would still fire and
        the 2/2 would eat three from a creature already in the graveyard."""
        game = position(builder, [BEAR], [OGRE])
        mine = oids_of(game, BEAR, 0)[0]
        theirs = oids_of(game, OGRE, 1)[0]
        destroy(game.state, theirs, cause="test")

        self.run(game, mine, theirs)

        assert alive(game, mine)
        assert marked(game, mine) == 0

    def test_it_holds_whichever_half_is_gone(self, builder):
        """The guard is on the pair, not on the first one it happens to read."""
        game = position(builder, [BEAR], [OGRE])
        mine = oids_of(game, BEAR, 0)[0]
        theirs = oids_of(game, OGRE, 1)[0]
        destroy(game.state, mine, cause="test")

        self.run(game, mine, theirs)

        assert marked(game, theirs) == 0

    def test_both_present_really_does_deal_damage(self, builder):
        """The control: the same call with nothing removed is a real fight, so
        the two assertions above are measuring the guard and not a broken call.
        """
        game = position(builder, [BEAR], [OGRE])
        mine = oids_of(game, BEAR, 0)[0]
        theirs = oids_of(game, OGRE, 1)[0]

        self.run(game, mine, theirs)

        assert marked(game, theirs) == 2


class TestACreatureCannotFightItself:
    def test_one_binding_on_both_halves_does_nothing(self, builder):
        """701.12d, and the only way a card file can reach it.

        Targeting already refuses the same permanent for two separate target
        slots, so the reachable mistake is a card pointing both halves of the op
        at one binding -- `t_self_fighter`. Without the guard the creature would
        deal itself damage twice.
        """
        game = position(builder, [BEAR], [WALL], spell=SELF)
        bear = oids_of(game, BEAR, 0)[0]
        cast_at(game, SELF, bear)
        assert alive(game, bear)
        assert marked(game, bear) == 0


class TestTheLoaderRefusesHalfAFight:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Target creature you control fights another target creature.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "targets": [
                    {
                        "id": "a",
                        "kind": "permanent",
                        "selector": {"zone": "battlefield", "types": ["Creature"]},
                    },
                    {
                        "id": "b",
                        "kind": "permanent",
                        "selector": {"zone": "battlefield", "types": ["Creature"]},
                    },
                ],
                "spell_effects": [effect],
            }
        )

    def test_both_halves_load(self):
        compile_card(
            self._card({"op": "fight", "objects": {"target": "a"}, "other": {"target": "b"}})
        )

    @pytest.mark.parametrize("missing", ["objects", "other"])
    def test_one_half_is_refused(self, missing):
        """A missing half would resolve to nothing and drop a printed clause.

        And the half it drops is the one that hits *your* creature, so the card
        would be better than printed rather than merely weaker.
        """
        effect = {"op": "fight", "objects": {"target": "a"}, "other": {"target": "b"}}
        del effect[missing]
        with pytest.raises(DslError, match="fight"):
            compile_card(self._card(effect))
