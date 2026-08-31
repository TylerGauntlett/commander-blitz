"""Replacing a life loss: "they lose twice that much life instead".

Bloodletter of Aclazotz — "If an opponent would lose life during your turn, they
lose twice that much life instead. (Damage causes loss of life.)" — is the
witness, and the parenthetical is the whole difficulty. Life goes down in this
engine in two unrelated places: `primitives.lose_life`, which every drain and
every paid life goes through, and the life-loss half of
`primitives.damage_player`, which is reached only by damage. A replacement wired
into one of them is a card that works against Village Rites and does nothing
against a Lightning Bolt, or the reverse, and both halves look completely normal
on a board.

Rule 120.3c is why damage counts: damage dealt to a player *causes that player to
lose that much life*, so a replacement of the loss applies to it. Rule 118.4 is
why paid life counts: paying life is losing life.

The property that is easiest to get wrong, and the reason this file exists
rather than one assertion on a life total: **only the loss is multiplied, never
the damage.** Lifelink gains life equal to the damage *dealt* (702.15b), which
the replacement never touched. An implementation that doubled `amount` at the top
of `damage_player` would pass every life-total assertion below except one, and
would quietly turn every lifelinking attacker into twice the lifegain it prints.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import life_loss_multiplier
from automtg.engine.enums import ActionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.primitives import damage_player, lose_life
from tests.conftest import action_for_card, pass_until


def position(
    builder,
    *doublers: str,
    active: int = 0,
    extra: str | None = None,
    hand: tuple[str, ...] = (),
):
    """Two players at 40, with ``doublers`` on player 0's battlefield.

    ``active`` is whose turn it is, which is the only thing Bloodletter's
    condition reads. ``extra`` is a non-doubling permanent the test needs an oid
    for -- the lifelinking source, and nothing else so far. ``hand`` is what
    player 0 holds, for the two tests that cast a real spell rather than calling
    a primitive.
    """
    ids = [*doublers] + ([extra] if extra else [])
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 4 + ["mountain"] * 2)
        .battlefield(0, ids)
        .hand(0, list(hand))
        .life(0, 40)
        .life(1, 40)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    game.state.active_idx = active
    return game


def cast_and_resolve(game, card_id: str) -> None:
    """Cast one spell from player 0's hand and let it resolve."""
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    pass_until(game, lambda g: not g.state.stack)


def oid_of(game, def_id: str) -> int:
    """The oid of the one battlefield permanent with this definition."""
    return next(
        oid
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == def_id
    )


class TestTheMultiplierItself:
    """`life_loss_multiplier` is the one thing both call sites read."""

    def test_no_doubler_is_one(self, builder):
        game = position(builder)
        assert life_loss_multiplier(game.state, 1) == 1

    def test_it_reaches_the_opponent_named(self, builder):
        game = position(builder, "t_bloodletter")
        assert life_loss_multiplier(game.state, 1) == 2

    def test_it_does_not_reach_its_own_controller(self, builder):
        """"If an *opponent* would lose life" — `affects_player` is not decoration."""
        game = position(builder, "t_bloodletter")
        assert life_loss_multiplier(game.state, 0) == 1

    def test_affects_player_you_points_the_other_way(self, builder):
        game = position(builder, "t_self_bloodletter")
        assert life_loss_multiplier(game.state, 0) == 2
        assert life_loss_multiplier(game.state, 1) == 1

    def test_two_doublers_quadruple(self, builder):
        """614.5: each replacement applies once, so a loss doubled twice is x4.

        Multiplied rather than summed, which is the whole reason the reader
        returns an int and seeds it at 1: summing would give 4 here too, and 3
        for a doubler beside a tripler -- the case that separates them.
        """
        game = position(builder, "t_always_bloodletter", "t_always_bloodletter")
        assert life_loss_multiplier(game.state, 1) == 4


class TestTheConditionIsRead:
    """"during your turn" is an ordinary `condition`, and must actually be asked."""

    def test_on_its_controllers_turn_it_applies(self, builder):
        game = position(builder, "t_bloodletter", active=0)
        assert life_loss_multiplier(game.state, 1) == 2

    def test_on_the_opponents_turn_it_does_not(self, builder):
        game = position(builder, "t_bloodletter", active=1)
        assert life_loss_multiplier(game.state, 1) == 1

    def test_the_unconditional_twin_applies_on_either_turn(self, builder):
        """Pins that the turn result above comes from the condition, not from
        `affects_player` or from the walk finding nothing."""
        for active in (0, 1):
            game = position(builder, "t_always_bloodletter", active=active)
            assert life_loss_multiplier(game.state, 1) == 2


class TestAPlainLifeLoss:
    """`primitives.lose_life` — every drain, and every life paid as a cost."""

    def test_the_loss_is_doubled(self, builder):
        game = position(builder, "t_bloodletter")
        lose_life(game.state, 1, 3)
        assert game.state.players[1].life == 34

    def test_it_returns_what_was_actually_lost(self, builder):
        """"You gain life equal to the life lost this way" reads this number."""
        game = position(builder, "t_bloodletter")
        assert lose_life(game.state, 1, 3) == 6

    def test_undoubled_without_the_static(self, builder):
        game = position(builder)
        assert lose_life(game.state, 1, 3) == 3
        assert game.state.players[1].life == 37

    def test_zero_stays_zero(self, builder):
        """The `amount <= 0` guard is above the multiplier: twice nothing is
        nothing, and a doubled 0 must not fire LIFE_LOST."""
        game = position(builder, "t_bloodletter")
        assert lose_life(game.state, 1, 0) == 0
        assert game.state.players[1].life == 40


class TestDamageIsALossOfLife:
    """120.3c, and the reminder text Bloodletter prints."""

    def test_damage_to_a_player_loses_double(self, builder):
        game = position(builder, "t_bloodletter")
        damage_player(game.state, 1, 3, None)
        assert game.state.players[1].life == 34

    def test_damage_dealt_is_not_itself_doubled(self, builder):
        """The return value is the *damage*, which the replacement never touched."""
        game = position(builder, "t_bloodletter")
        assert damage_player(game.state, 1, 3, None) == 3

    def test_lifelink_gains_the_damage_not_the_loss(self, builder):
        """702.15b — the sharpest way to get this wrong.

        A lifelinking source dealing 3 to a doubled opponent takes 6 life off
        them and gains its controller 3, not 6.
        """
        game = position(builder, "t_bloodletter", extra="t_lifelink_bear")
        bear = oid_of(game, "t_lifelink_bear")
        before = game.state.players[0].life
        damage_player(game.state, 1, 3, bear)
        assert game.state.players[1].life == 34
        assert game.state.players[0].life == before + 3


class TestTheLoaderRefusesWhatIsNotACard:
    """A multiplier of 1 or 0 loads clean and is a different card."""

    @pytest.mark.parametrize("bad", [0, 1, -2])
    def test_multiplier_below_two_is_refused(self, bad):

        with pytest.raises(DslError, match="loss_multiplier"):
            compile_card(CardModel.model_validate(_bad_card(loss_multiplier=bad)))

    def test_multiplier_is_required(self):

        card = _bad_card(loss_multiplier=None)
        card["abilities"][0].pop("loss_multiplier")
        with pytest.raises(DslError, match="loss_multiplier"):
            compile_card(CardModel.model_validate(card))


def _bad_card(*, loss_multiplier: int | None) -> dict:
    return {
        "id": "t_bad_letter",
        "name": "Test Bad Letter",
        "oracle_text": "If an opponent would lose life, they lose that much life instead.",
        "mana_cost": "{2}{B}",
        "types": ["Creature"],
        "subtypes": ["Vampire"],
        "power": 2,
        "toughness": 2,
        "colors": ["B"],
        "color_identity": ["B"],
        "abilities": [
            {
                "kind": "static",
                "text": (
                    "If an opponent would lose life, they lose that much life instead."
                ),
                "effect": "replace_life_loss",
                "affects_player": "opponent",
                "loss_multiplier": loss_multiplier,
            }
        ],
    }


class TestItReachesRealPlay:
    """The primitives above are reached through a cast spell, not only directly.

    Every assertion further up calls `lose_life` or `damage_player` by hand,
    which proves the replacement but not that anything in a game arrives there.
    These two cast a real spell off a real board: `t_drain` is the `lose_life`
    op, `t_drain_bolt` is the `damage` op, and they are the two routes a printed
    card actually takes to take life off a player.
    """

    def test_a_drain_spell_drains_double(self, builder):
        game = position(builder, "t_bloodletter", hand=("t_drain",))
        cast_and_resolve(game, "t_drain")
        assert game.state.players[1].life == 34

    def test_a_damage_spell_drains_double(self, builder):
        game = position(builder, "t_bloodletter", hand=("t_drain_bolt",))
        cast_and_resolve(game, "t_drain_bolt")
        assert game.state.players[1].life == 34

    def test_without_the_static_both_are_ordinary(self, builder):
        for card in ("t_drain", "t_drain_bolt"):
            game = position(builder, hand=(card,))
            cast_and_resolve(game, card)
            assert game.state.players[1].life == 37
