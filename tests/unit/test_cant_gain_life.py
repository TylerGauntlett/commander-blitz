"""A player who can't gain life: "Your opponents can't gain life."

Erebos, God of the Dead is the witness. A "can't" is not a replacement: it does
not rewrite the gain into something else, it makes the gain not happen, and rule
101.2 puts it above every effect that would make it happen -- an Alhammarret's
Archive's "you gain twice that much life instead" included. So the order inside
`primitives.gain_life` is the rules argument: the prohibition is asked *before*
the multiplier, and a forbidden gain doubled is still no gain.

What would be wrong without it: `lock_life_total` is the near miss and is a
different card three ways -- a one-shot op with a duration rather than a static
that lifts when Erebos leaves, it names one player, and it forbids *losing* life
too, so Erebos written with it would make its opponents immune to their own
Phyrexian mana.

Two things beyond the life total that an implementation could miss while every
life assertion passed: lifelink is a gain like any other (702.15b), so a
lifelinking attacker under Erebos gains nothing while its damage is still dealt;
and a forbidden gain fires no `LIFE_GAINED`, so "whenever you gain life"
(Marauding Blight-Priest) does not trigger off a gain that never happened.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import player_cant_gain_life
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import damage_player, gain_life
from automtg.engine.zones import move_object
from tests.conftest import action_for_card, pass_until

EREBOS = "t_erebos"  # Your opponents can't gain life.
SELF_EREBOS = "t_self_erebos"  # You can't gain life.
TURN_EREBOS = "t_turn_erebos"  # During your turn, your opponents can't gain life.
ARCHIVE = "t_archive"  # If you would gain life, you gain twice that much instead.
GAIN_SPELL = "t_gain_spell"  # You gain 3 life.
LIFELINK_BEAR = "t_lifelink_bear"
BLIGHT_PRIEST = "marauding_blight_priest"  # Whenever you gain life, each opponent loses 1 life.


def position(builder, mine=(), theirs=(), *, active: int = 0, hand=()):
    """Two players at 40; ``mine`` on player 0's battlefield, ``theirs`` on player 1's."""
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 4 + list(mine))
        .battlefield(1, ["plains"] * 4 + list(theirs))
        .hand(1, list(hand))
        .life(0, 40)
        .life(1, 40)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    game.state.active_idx = active
    return game


def oid_of(game, def_id: str, controller: int | None = None) -> int:
    return next(
        oid
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == def_id
        and (controller is None or game.state.objects[oid].controller == controller)
    )


class TestWhoItNames:
    def test_it_names_the_opponent(self, builder):
        game = position(builder, mine=[EREBOS])
        assert player_cant_gain_life(game.state, 1)

    def test_not_its_controller(self, builder):
        """"Your *opponents*" -- Erebos's controller gains life as normal."""
        game = position(builder, mine=[EREBOS])
        assert not player_cant_gain_life(game.state, 0)
        assert gain_life(game.state, 0, 3) == 3

    def test_affects_player_you_points_the_other_way(self, builder):
        game = position(builder, mine=[SELF_EREBOS])
        assert player_cant_gain_life(game.state, 0)
        assert not player_cant_gain_life(game.state, 1)

    def test_nobody_without_the_static(self, builder):
        game = position(builder)
        assert not player_cant_gain_life(game.state, 0)
        assert not player_cant_gain_life(game.state, 1)


class TestTheGainDoesNotHappen:
    def test_a_gain_moves_nothing(self, builder):
        game = position(builder, mine=[EREBOS])
        assert gain_life(game.state, 1, 5) == 0
        assert game.state.players[1].life == 40

    def test_no_life_gained_event_is_fired(self, builder):
        game = position(builder, mine=[EREBOS])
        mark = len(game.state.events)
        gain_life(game.state, 1, 5)
        assert "life_gained" not in [e.type for e in game.state.events[mark:]]

    def test_a_life_gain_trigger_does_not_fire(self, builder):
        """Marauding Blight-Priest must not drain for a gain that never happened."""
        game = position(builder, mine=[EREBOS], theirs=[BLIGHT_PRIEST])
        gain_life(game.state, 1, 2)
        assert game.state.pending_triggers == []
        assert game.state.players[0].life == 40

    def test_without_erebos_the_trigger_does_fire(self, builder):
        """Pins that the silence above is Erebos's, not a trigger that never could."""
        game = position(builder, theirs=[BLIGHT_PRIEST])
        gain_life(game.state, 1, 2)
        assert game.state.pending_triggers

    def test_a_gain_spell_gains_nothing(self, builder):
        game = position(builder, mine=[EREBOS], active=1, hand=(GAIN_SPELL,))
        game.apply(action_for_card(game, ActionKind.CAST, GAIN_SPELL))
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.players[1].life == 40


class TestLifelink:
    """702.15b -- lifelink is a life gain, and the damage is still dealt."""

    def test_lifelink_gains_nothing(self, builder):
        game = position(builder, mine=[EREBOS], theirs=[LIFELINK_BEAR])
        bear = oid_of(game, LIFELINK_BEAR)
        assert damage_player(game.state, 0, 2, bear) == 2
        assert game.state.players[0].life == 38, "the damage is still dealt"
        assert game.state.players[1].life == 40, "and its controller gains nothing"


class TestItFollowsItsSource:
    def test_it_lifts_when_erebos_leaves(self, builder):
        game = position(builder, mine=[EREBOS])
        move_object(game.state, oid_of(game, EREBOS), Zone.GRAVEYARD)
        assert not player_cant_gain_life(game.state, 1)
        assert gain_life(game.state, 1, 3) == 3

    def test_a_condition_beside_it_is_read(self, builder):
        on = position(builder, mine=[TURN_EREBOS], active=0)
        off = position(builder, mine=[TURN_EREBOS], active=1)
        assert player_cant_gain_life(on.state, 1)
        assert not player_cant_gain_life(off.state, 1)


class TestCantBeatsTheDoubler:
    """101.2: "can't" wins over an effect that would make the gain happen."""

    def test_a_forbidden_gain_is_not_doubled_into_one(self, builder):
        game = position(builder, mine=[EREBOS], theirs=[ARCHIVE])
        assert gain_life(game.state, 1, 3) == 0
        assert game.state.players[1].life == 40

    def test_the_doubler_still_works_for_a_player_erebos_does_not_name(self, builder):
        game = position(builder, mine=[EREBOS, ARCHIVE])
        assert gain_life(game.state, 0, 3) == 6


class TestTheLoaderRefusesWhatIsNotACard:
    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))

    def test_affects_player_is_required(self):
        card = _card()
        card["abilities"][0].pop("affects_player")
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(card))

    @pytest.mark.parametrize(
        "extra",
        [{"affects": {"types": ["Creature"]}}, {"amount": {"const": 1}}],
    )
    def test_a_filter_or_an_amount_is_refused(self, extra):
        """Nothing reads either; a filtered "can't" would load clean and stop everything."""
        card = _card()
        card["abilities"][0].update(extra)
        with pytest.raises(DslError, match="cant_gain_life"):
            compile_card(CardModel.model_validate(card))


def _card() -> dict:
    return {
        "id": "t_bad_erebos",
        "name": "Test Bad Erebos",
        "oracle_text": "Your opponents can't gain life.",
        "mana_cost": "{3}{B}",
        "types": ["Enchantment"],
        "colors": ["B"],
        "color_identity": ["B"],
        "abilities": [
            {
                "kind": "static",
                "text": "Your opponents can't gain life.",
                "effect": "cant_gain_life",
                "affects_player": "opponent",
            }
        ],
    }
