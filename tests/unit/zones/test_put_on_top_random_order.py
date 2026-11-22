"""Cards put into a library in a random order, and only those cards.

Triumph of Saint Katherine: "When this creature is put into your graveyard from
the battlefield, exile it and the top six cards of your library in a face-down
pile. If you do, shuffle that pile and put it back on top of your library."
Endurance: "…puts all the cards from their graveyard on the bottom of their
library in a random order."

Both are one key on `put_on_top`, `random_order`, and both have two near misses
that are different cards:

- **pool order** (no key) tells the owner exactly where each card sits. On
  Triumph that is where the miracle card is, which is the whole of what the
  shuffle hides;
- **a `shuffle` op afterwards** randomises the *whole* library, which turns a
  stacked top seven into a random draw from the deck and on Endurance would
  send the graveyard anywhere rather than under the library.

So the claims: the pile lands at the stated end, the rest of the library does
not move, the order is the RNG's rather than the pool's, and "if you do" holds
without a condition -- what was exiled goes back, and nothing more. The loader
refuses the key beside the owner's arrangement, a depth, a per-card choice of
end, and on any other op.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, settle_completely

PILE = "t_pile_back_on_top"
BOTTOM = "t_graveyard_to_bottom_random"
LIBRARY = ["plains", "island", "swamp", "mountain", "forest", "t_bear", "forest", "island"]


def a_dying_pile(builder, seed: int = 0, library=LIBRARY):
    """The creature on the battlefield over a known library; returns ``(game, oid)``."""
    game = (
        builder(players=2, seed=seed)
        .battlefield(0, [PILE])
        .library(0, list(library))
        .build(advance=False)
    )
    return game, only_oid(game, PILE, 0)


def kill(game, oid: int) -> None:
    move_object(game.state, oid, Zone.GRAVEYARD, cause="destroyed")
    resolve(game)


def resolve(game) -> None:
    """Hand the table priority so the waiting trigger goes on, then resolve it."""
    game._advance()
    settle_completely(game)


class TestThePileGoesBackOnTop:
    def test_the_top_seven_are_the_creature_and_the_six(self, builder):
        game, oid = a_dying_pile(builder)
        six = list(game.state.players[0].library[:6])
        kill(game, oid)

        library = game.state.players[0].library
        assert sorted(library[:7]) == sorted([*six, oid])

    def test_nothing_is_left_in_exile_or_the_graveyard(self, builder):
        game, oid = a_dying_pile(builder)
        kill(game, oid)

        assert game.state.players[0].exile == []
        assert oid not in game.state.players[0].graveyard
        assert game.state.objects[oid].zone is Zone.LIBRARY

    def test_the_cards_under_the_pile_do_not_move(self, builder):
        game, oid = a_dying_pile(builder)
        under = list(game.state.players[0].library[6:])
        kill(game, oid)

        assert game.state.players[0].library[7:] == under

    def test_the_order_is_random_rather_than_the_pools(self, builder):
        """Pool order would be the same seven every seed; a random one is not."""
        orders = set()
        for seed in range(8):
            game, oid = a_dying_pile(builder, seed=seed)
            kill(game, oid)
            orders.add(tuple(game.state.objects[o].def_id for o in game.state.players[0].library[:7]))
        assert len(orders) > 1

    def test_the_same_seed_is_the_same_order(self, builder):
        """Deterministic: the engine's RNG, not the interpreter's."""
        runs = []
        for _ in range(2):
            game, oid = a_dying_pile(builder, seed=3)
            kill(game, oid)
            runs.append([game.state.objects[o].def_id for o in game.state.players[0].library])
        assert runs[0] == runs[1]


class TestIfYouDo:
    def test_a_short_library_returns_what_was_exiled(self, builder):
        game, oid = a_dying_pile(builder, library=["plains", "island"])
        kill(game, oid)

        assert len(game.state.players[0].library) == 3
        assert game.state.players[0].exile == []

    def test_a_creature_gone_from_the_graveyard_still_returns_the_six(self, builder):
        """Only what this resolution exiled comes back; the creature is not fetched."""
        game, oid = a_dying_pile(builder)
        six = list(game.state.players[0].library[:6])
        move_object(game.state, oid, Zone.GRAVEYARD, cause="destroyed")
        move_object(game.state, oid, Zone.HAND)
        resolve(game)

        assert sorted(game.state.players[0].library[:6]) == sorted(six)
        assert oid in game.state.players[0].hand
        assert game.state.players[0].exile == []


class TestTheBottom:
    def test_the_graveyard_goes_under_in_a_random_order(self, builder):
        orders = set()
        for seed in range(8):
            game = (
                builder(players=2, seed=seed)
                .battlefield(0, ["forest"])
                .hand(0, [BOTTOM])
                .graveyard(0, ["plains", "island", "swamp", "mountain"])
                .library(0, ["t_bear"] * 3)
                .step(Step.PRECOMBAT_MAIN)
                .build(advance=False)
            )
            game._advance()
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BOTTOM
                )
            )
            settle_completely(game)
            library = [game.state.objects[o].def_id for o in game.state.players[0].library]
            assert library[:3] == ["t_bear"] * 3
            assert sorted(library[3:]) == ["island", "mountain", "plains", "swamp"]
            orders.add(tuple(library[3:]))
        assert len(orders) > 1


def compile_with(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_bad_random_tuck",
                "name": "Bad Random Tuck",
                "oracle_text": "Put the cards from your graveyard on the bottom of your library in a random order.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )
    )


class TestTheLoaderRefuses:
    POOL = {"zone": "graveyard", "player": "you", "count": "all"}

    @pytest.mark.parametrize("other", ["any_order", "owner_chooses"])
    def test_another_way_to_order_or_place_them(self, other):
        with pytest.raises(DslError, match="random_order"):
            compile_with(
                {"op": "put_on_top", "random_order": True, other: True, "objects": self.POOL}
            )

    def test_a_depth(self):
        with pytest.raises(DslError, match="random_order"):
            compile_with(
                {"op": "put_on_top", "random_order": True, "from_top": 2, "objects": self.POOL}
            )

    def test_a_non_boolean(self):
        with pytest.raises(DslError, match="random_order"):
            compile_with({"op": "put_on_top", "random_order": "yes", "objects": self.POOL})

    def test_another_op(self):
        with pytest.raises(DslError, match="random_order"):
            compile_with({"op": "mill", "random_order": True, "amount": 2})
