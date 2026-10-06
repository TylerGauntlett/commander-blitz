"""Reading, and showing, the top card of a library.

    Vampire Nocturnus — "Play with the top card of your library revealed. As
    long as the top card of your library is black, this creature and other
    Vampire creatures you control get +2/+1 and have flying."

Two halves that only work together, and each was missing for a different reason.

**The condition.** A static may ask about pipeline *inputs* only, so that no
static can come to depend on another's output. The top card of a library is
such an input — nothing in the characteristics pipeline can change what is on
top of a library — but the nearest thing the language had was `exists` over
`{"zone": "library", "colors": ["B"]}`, which asks whether *any* black card is
anywhere in ninety-nine. In this deck that is true essentially always, so the
card would have read as a permanent +2/+1 and flying: a strictly better card,
and one that would have passed every gate.

**The reveal.** Purely a visibility change — it grants no permission and moves
no card, which is the whole of what separates it from
`play_lands_from_library_top`. It is nonetheless load-bearing rather than
flavour: whether your team has flying is a fact you are meant to know *before*
declaring attackers, and without it the condition that decides it is invisible.
So it is sent to every seat, not just its controller's — the card is public, and
an opponent who cannot see it is playing against information they are entitled
to.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars, top_of_library
from automtg.engine.enums import Keyword
from automtg.engine.errors import DslError
from automtg.engine.player_statics import player_reveals_library_top
from automtg.engine.serialize import player_view

#: A black card and a non-black one, for stacking a library top.
BLACK = "t_deathtoucher"
NOT_BLACK = "t_bear"


def nocturnus(builder, *, top: str):
    """`t_nocturnus` out, with a chosen card on top of player 0's library."""
    game = (
        builder(players=2)
        .battlefield(0, ["t_nocturnus"])
        .library(0, [top, "island", "island"])
        .build()
    )
    return game, game.state.battlefield[0]


def test_the_props_are_the_colours_this_file_assumes(builder):
    """If the test pool's colours ever change, everything below lies quietly."""
    game, _ = nocturnus(builder, top=BLACK)
    top = top_of_library(game.state, 0)
    assert "B" in game.state.card_of(top).colors

    game, _ = nocturnus(builder, top=NOT_BLACK)
    top = top_of_library(game.state, 0)
    assert "B" not in game.state.card_of(top).colors


class TestTopOfLibrary:
    def test_it_reads_the_top_card_and_not_the_rest(self, builder):
        game, _ = nocturnus(builder, top=BLACK)
        assert game.state.card_of(top_of_library(game.state, 0)).id == BLACK

    def test_an_empty_library_has_no_top(self, builder):
        game = builder(players=2).battlefield(0, ["t_nocturnus"]).library(0, []).build()
        assert top_of_library(game.state, 0) is None


class TestTheConditionalStatic:
    def test_a_black_top_card_turns_it_on(self, builder):
        game, source = nocturnus(builder, top=BLACK)
        c = chars(game.state, source)
        assert (c.power, c.toughness) == (3 + 2, 3 + 1)
        assert Keyword.FLYING.value in c.keywords

    def test_a_non_black_top_card_leaves_it_off(self, builder):
        """The whole card. `exists` over the library would say yes here too,
        which is why it could not be written that way."""
        game, source = nocturnus(builder, top=NOT_BLACK)
        c = chars(game.state, source)
        assert (c.power, c.toughness) == (3, 3)
        assert Keyword.FLYING.value not in c.keywords

    def test_it_switches_the_instant_the_top_card_changes(self, builder):
        """Continuous, not measured once. Drawing the black card off the top
        takes the flying away mid-turn, which is the card people misplay."""
        game, source = nocturnus(builder, top=BLACK)
        assert Keyword.FLYING.value in chars(game.state, source).keywords

        from automtg.engine.primitives import draw_cards

        draw_cards(game.state, 0, 1)
        assert Keyword.FLYING.value not in chars(game.state, source).keywords

    def test_an_empty_library_leaves_it_off(self, builder):
        game = builder(players=2).battlefield(0, ["t_nocturnus"]).library(0, []).build()
        source = game.state.battlefield[0]
        assert (chars(game.state, source).power, chars(game.state, source).toughness) == (3, 3)


class TestTheReveal:
    def test_nothing_reveals_a_library_by_default(self, builder):
        game = builder(players=2).battlefield(0, ["t_bear"]).library(0, [BLACK]).build()
        assert player_reveals_library_top(game.state, 0) is False
        assert player_view(game.state, 0)["players"][0]["library_top"] is None

    def test_the_static_reveals_it(self, builder):
        game, _ = nocturnus(builder, top=BLACK)
        assert player_reveals_library_top(game.state, 0) is True
        top = player_view(game.state, 0)["players"][0]["library_top"]
        assert top is not None
        assert top["card_id"] == BLACK

    def test_the_opponent_sees_it_too(self, builder):
        """"Revealed" means revealed. An opponent who cannot see it is playing
        against information they are entitled to."""
        game, _ = nocturnus(builder, top=BLACK)
        top = player_view(game.state, 1)["players"][0]["library_top"]
        assert top is not None
        assert top["card_id"] == BLACK

    def test_it_does_not_reveal_anybody_else_s_library(self, builder):
        game, _ = nocturnus(builder, top=BLACK)
        assert player_view(game.state, 0)["players"][1]["library_top"] is None

    def test_it_stops_when_the_permanent_leaves(self, builder):
        game, source = nocturnus(builder, top=BLACK)
        from automtg.engine.zones import destroy

        destroy(game.state, source)
        assert player_reveals_library_top(game.state, 0) is False
        assert player_view(game.state, 0)["players"][0]["library_top"] is None


class TestTheLoaderRefuses:
    def _card(self, condition: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_reader",
                "name": "Test Reader",
                "mana_cost": "{1}{B}",
                "types": ["Creature"],
                "subtypes": ["Vampire"],
                "power": 1,
                "toughness": 1,
                "oracle_text": "As long as the top card of your library is black, "
                "this creature has flying.",
                "abilities": [
                    {
                        "kind": "static",
                        "text": "As long as the top card of your library is black, "
                        "this creature has flying.",
                        "effect": "grant_keyword",
                        "affects": {"self_only": True},
                        "condition": condition,
                        "keywords": ["flying"],
                    }
                ],
            }
        )

    def test_it_takes_the_ordinary_form(self):
        compile_card(self._card({"top_of_library": {"controller": "you", "colors": ["B"]}}))

    def test_board_state_keys_are_refused(self):
        """The top card of a library is not tapped, and a key that loads and
        matches nothing is how a card comes to do less than it prints."""
        with pytest.raises(DslError, match="printed face"):
            compile_card(self._card({"top_of_library": {"tapped": False}}))

    def test_a_zone_is_refused(self):
        """The zone is the whole point of the leaf; naming another would read
        as a knob that works."""
        with pytest.raises(DslError, match="printed face"):
            compile_card(self._card({"top_of_library": {"zone": "graveyard"}}))

    def test_a_bad_player_spec_is_refused(self):
        with pytest.raises(DslError, match="controller"):
            compile_card(self._card({"top_of_library": {"controller": "nobody"}}))
