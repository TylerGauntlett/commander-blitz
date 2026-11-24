"""``enters_untapped`` -- "Other permanents enter untapped."

    Archelos, Lagoon Mystic -- "As long as Archelos is tapped, other
    permanents enter tapped. As long as Archelos is untapped, other permanents
    enter untapped."
    Horizon Explorer -- "Lands you control enter untapped."

`enters_tapped`'s mirror. Every way an arrival can be made tapped is a
replacement on the same event (614.12): an effect that puts it onto the
battlefield tapped, a board `enters_tapped` static, the card's own "enters
tapped". 616.1 lets the arriving permanent's controller order them with this
one, and applying it last is the order every controller would choose -- so
`zones._enter_battlefield` reads it after all three and it has the last word.

Without it Archelos's second line was unwritable, and writing only the first
made a card that taps the board and never untaps it.

A price that only avoids entering tapped ("pay 3 life or it enters tapped")
buys nothing on such an arrival, so it is neither offered as a second land drop
nor asked.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.state import new_object
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of, static_probe

ARCHELOS = "t_eu_archelos"
EXPLORER = "t_eu_explorer"
AUTHORITY = "t_authority"  # creatures your opponents control enter tapped
BEAR = "t_bear"
TAPLAND = "jungle_hollow"  # enters tapped, printed
SHOCK = "blood_crypt"  # pay 2 life or it enters tapped


def board(builder, mine=(ARCHELOS,), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build()
    )


def arrive(game, card_id: str, pid: int, *, tapped: bool = False) -> int:
    """Through `move_object`, the funnel every arrival shares."""
    obj = new_object(game.state, card_id, owner=pid, zone=Zone.HAND)
    game.state.players[pid].hand.append(obj.oid)
    move_object(game.state, obj.oid, Zone.BATTLEFIELD, tapped=tapped)
    return obj.oid


def is_tapped(game, oid: int) -> bool:
    return game.state.objects[oid].tapped


class TestUntappedArchelos:
    def test_a_printed_tapland_enters_untapped(self, builder):
        game = board(builder)
        assert not is_tapped(game, arrive(game, TAPLAND, 0))

    def test_an_opponents_tapland_does_too(self, builder):
        """"Other permanents": either side of the table."""
        game = board(builder)
        assert not is_tapped(game, arrive(game, TAPLAND, 1))

    def test_put_onto_the_battlefield_tapped_enters_untapped(self, builder):
        """A fetch or a ramp spell's "tapped" is replaced as well."""
        game = board(builder)
        assert not is_tapped(game, arrive(game, BEAR, 0, tapped=True))

    def test_a_token_created_tapped_enters_untapped(self, builder):
        game = board(builder)
        made = create_token(game.state, "cat_1_1_w", controller=1, tapped=True)
        made = made if isinstance(made, list) else [made]
        assert made and not any(is_tapped(game, o) for o in made)

    def test_it_beats_a_board_enters_tapped(self, builder):
        """Authority of the Consuls taps the arrival, Archelos untaps it: the
        controller orders them, and orders this one last."""
        game = board(builder, mine=(ARCHELOS,), theirs=(AUTHORITY,))
        assert not is_tapped(game, arrive(game, BEAR, 0))


class TestTappedArchelos:
    def test_a_permanent_enters_tapped(self, builder):
        game = board(builder)
        game.state.objects[oids_of(game, ARCHELOS)[0]].tapped = True
        assert is_tapped(game, arrive(game, BEAR, 1))

    def test_nothing_untaps_the_tapland(self, builder):
        game = board(builder)
        game.state.objects[oids_of(game, ARCHELOS)[0]].tapped = True
        assert is_tapped(game, arrive(game, TAPLAND, 0))


class TestTheFilter:
    def test_without_the_static_a_tapland_enters_tapped(self, builder):
        game = board(builder, mine=())
        assert is_tapped(game, arrive(game, TAPLAND, 0))

    def test_the_explorer_untaps_its_own_lands(self, builder):
        game = board(builder, mine=(EXPLORER,))
        assert not is_tapped(game, arrive(game, TAPLAND, 0))

    def test_the_explorer_leaves_an_opponents_land(self, builder):
        game = board(builder, mine=(EXPLORER,))
        assert is_tapped(game, arrive(game, TAPLAND, 1))

    def test_the_explorer_leaves_a_creature_put_in_tapped(self, builder):
        game = board(builder, mine=(EXPLORER,))
        assert is_tapped(game, arrive(game, BEAR, 0, tapped=True))

    def test_eu_archelos_does_not_untap_itself(self, builder):
        """Its own static is not applying to its own entrance."""
        game = board(builder, mine=())
        assert is_tapped(game, arrive(game, ARCHELOS, 0, tapped=True))


class TestTheShockLand:
    def drops(self, game):
        return [a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND]

    def test_it_is_one_drop_with_archelos_untapped(self, builder):
        game = builder(players=2).battlefield(0, [ARCHELOS]).hand(0, [SHOCK]).build()
        offered = self.drops(game)
        assert len(offered) == 1
        life = game.state.players[0].life
        game.apply(offered[0])
        land = oids_of(game, SHOCK)[0]
        assert not is_tapped(game, land)
        assert game.state.players[0].life == life, "paid for nothing"

    def test_it_is_two_drops_without_it(self, builder):
        game = builder(players=2).hand(0, [SHOCK]).build()
        assert len(self.drops(game)) == 2


class TestTheLoader:
    def _load(self, static: dict) -> None:
        compile_card(CardModel.model_validate(static_probe(static)))

    def test_the_fixture_loads(self, registry):
        assert len(registry.get(ARCHELOS).abilities) == 2

    def test_a_missing_filter_is_refused(self):
        with pytest.raises(DslError, match="affects"):
            self._load({"effect": "enters_untapped"})

    def test_an_amount_is_refused(self):
        with pytest.raises(DslError, match="quantity"):
            self._load(
                {
                    "effect": "enters_untapped",
                    "affects": {"controller": "any"},
                    "amount": {"const": 1},
                }
            )
