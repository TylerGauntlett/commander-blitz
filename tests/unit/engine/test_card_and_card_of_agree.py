""""Which card is this object?" must have one answer.

    Malakir Rebirth // Malakir Mire, played as its land half.

`state.card_of(obj)` is the documented place double-faced cards are implemented:
it honours `showing_second_face`, `transformed` and a mutated pile's synthesised
card. `state.card(oid)` looked the `def_id` straight up in the registry and
ignored all three.

Nothing noticed until a game was played. `costs._sources_of` planned a mana
payment through `card_of` and saw Malakir Mire's mana ability; then
`costs.activate_mana_ability` executed it through `state.card` and saw Malakir
Rebirth, an instant with no abilities at all. `abilities[0]` on that is an
IndexError — the crash, not a wrong answer, which is the only reason it was
visible.

This is the seam every "one helper, two callers" note in this repo is about, and
the same fix: `card` delegates to `card_of`, so the plan and the payment cannot
be looking at different cards.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import Zone
from commanderblitz.engine.state import new_object

FRONT = "malakir_rebirth_malakir_mire"


@pytest.fixture
def game(builder):
    return builder(players=2).library(0, ["swamp"] * 20).build()


def place(game, card_id: str) -> int:
    obj = new_object(game.state, card_id, owner=0, zone=Zone.BATTLEFIELD)
    game.state.battlefield.append(obj.oid)
    game.state.bump_chars()
    return obj.oid


class TestTheyAgree:
    def test_on_an_ordinary_permanent(self, game):
        oid = place(game, "swamp")
        assert game.state.card(oid) is game.state.card_of(game.state.objects[oid])

    def test_on_a_second_face(self, game):
        """The land half of a modal DFC: an instant on the front, a land on the
        back, and the permanent on the battlefield is the land."""
        oid = place(game, FRONT)
        game.state.objects[oid].showing_second_face = True
        game.state.bump_chars()

        shown = game.state.card_of(game.state.objects[oid])
        assert game.state.card(oid) is shown
        assert shown.id != FRONT, "it is showing the other face"

    def test_the_face_it_shows_is_the_one_with_the_mana_ability(self, game):
        """What the crash actually was: the plan saw a land, the payment saw an
        instant, and `abilities[0]` on an instant with no abilities raised."""
        oid = place(game, FRONT)
        game.state.objects[oid].showing_second_face = True
        game.state.bump_chars()

        assert game.state.card(oid).abilities, "no mana ability to activate"

    def test_on_a_transformed_permanent(self, game):
        oid = place(game, "bloodline_keeper")
        game.state.objects[oid].transformed = True
        game.state.bump_chars()

        shown = game.state.card_of(game.state.objects[oid])
        assert game.state.card(oid) is shown
        assert shown.id != "bloodline_keeper"
