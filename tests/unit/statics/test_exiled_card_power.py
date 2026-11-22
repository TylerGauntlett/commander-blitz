"""Drach'Nyen -- a static magnitude read off the card this permanent exiled.

    Echo of the First Murder -- When Drach'Nyen enters, exile up to one target
    creature.
    Daemon Sword -- Equipped creature has menace and gets +X/+0, where X is the
    exiled card's power.

The `exiled_card_power` static value. "The exiled card" is the card the first
ability exiled -- 607.2a links the two -- so it is read off the source's own
`exiled_cards`, the link `link_exiled` writes and a zone change empties (400.7:
a re-cast or flickered Drach'Nyen is a new object with nothing exiled). The
power is the card's in exile, where its characteristic-defining abilities still
work (604.3), and X is 0 once that card has left exile, when a token ceased to
exist there, and when the trigger exiled nothing.

The near misses: the effect-side `power_of` is evaluated once, so a pump read
at the trigger would wear off and miss every re-equip; `extreme_value` reads
only mana value, and no counting filter can name the linked card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.zones import exile, move_object
from tests.conftest import only_oid, pass_until, settle, static_probe

SWORD = "t_daemon_sword"
STAR = "t_star_beast"
ANGEL = "serra_angel"
BEAR = "grizzly_bears"


def position(builder, theirs=(ANGEL,), *, take: str | None = ANGEL):
    """The Sword arrives on player 0's side, exiles ``take`` (or nothing) and is
    attached to player 0's Bear. Returns ``(game, sword, wielder)``."""
    game = (
        builder(players=2)
        .battlefield(0, [BEAR])
        .battlefield(1, list(theirs))
        .hand(0, [SWORD])
        .build()
    )
    sword = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == SWORD)
    wielder = only_oid(game, BEAR, 0)
    target = only_oid(game, take, 1) if take else None
    move_object(game.state, sword, Zone.BATTLEFIELD)

    def choose(g):
        decision = g.pending()
        if decision is None or decision.context.get("source") != sword:
            return False
        for action in g.legal_actions():
            wanted = (action.targets and action.targets[0].id == target) if target else not action.targets
            if wanted:
                g.apply(action)
                return True
        return False

    pass_until(game, choose)
    choose(game)
    settle(game)
    assert attach(game.state, sword, wielder)
    return game, sword, wielder


def power(game, oid: int) -> int:
    return chars(game.state, oid).power


class TestTheExiledCardsPower:
    def test_x_is_the_exiled_creature_s_power(self, builder):
        game, _, wielder = position(builder)
        assert power(game, wielder) == 2 + 4
        assert chars(game.state, wielder).toughness == 2

    def test_menace_comes_with_it(self, builder):
        game, _, wielder = position(builder)
        assert "menace" in chars(game.state, wielder).keywords

    def test_exiling_nothing_is_plus_zero_and_still_menace(self, builder):
        game, _, wielder = position(builder, take=None)
        assert power(game, wielder) == 2
        assert "menace" in chars(game.state, wielder).keywords

    def test_it_follows_a_re_equip(self, builder):
        """A static, not a one-shot pump: the next creature gets it too."""
        game, sword, wielder = position(builder, theirs=(ANGEL, BEAR), take=ANGEL)
        other = only_oid(game, BEAR, 1)
        assert attach(game.state, sword, other)
        assert power(game, wielder) == 2
        assert power(game, other) == 2 + 4


class TestTheLink:
    def test_a_card_that_leaves_exile_ends_it(self, builder):
        game, sword, wielder = position(builder)
        angel = game.state.objects[sword].exiled_cards[-1]
        move_object(game.state, angel, Zone.GRAVEYARD)
        assert power(game, wielder) == 2

    def test_exiled_again_by_something_else_is_not_the_exiled_card(self, builder):
        game, sword, wielder = position(builder)
        angel = game.state.objects[sword].exiled_cards[-1]
        move_object(game.state, angel, Zone.BATTLEFIELD)
        exile(game.state, angel)
        assert power(game, wielder) == 2

    def test_a_flickered_sword_is_a_new_object(self, builder):
        """400.7: the Angel stays in exile, and it is not this object's."""
        game, sword, wielder = position(builder)
        angel = game.state.objects[sword].exiled_cards[-1]
        move_object(game.state, sword, Zone.EXILE)
        move_object(game.state, sword, Zone.BATTLEFIELD)
        settle(game)
        attach(game.state, sword, wielder)
        assert game.state.objects[angel].zone is Zone.EXILE
        assert power(game, wielder) == 2


class TestThePowerInExile:
    def test_a_star_card_counts_in_exile(self, builder):
        """604.3, and its "you" is the card's owner: player 1 controls two Bears."""
        game, _, wielder = position(builder, theirs=(STAR, BEAR, BEAR), take=STAR)
        assert power(game, wielder) == 2 + 2


class TestTheLoaderRefuses:
    @pytest.mark.parametrize("bad", ["you", "target", 1, None])
    def test_only_self(self, bad):
        with pytest.raises(DslError, match="exiled_card_power"):
            compile_card(_probe(bad))

    def test_the_printed_shape_loads(self):
        compile_card(_probe("self"))


def _probe(who) -> CardModel:
    return CardModel.model_validate(
        static_probe(
            {
                "effect": "buff",
                "affects": {"attached": True},
                "power": {"exiled_card_power": who},
                "toughness": {"const": 0},
            }
        )
    )
