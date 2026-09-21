"""A search whose destination depends on what it found.

    "Search your library for a creature or land card and reveal it. **Put it
    onto the battlefield tapped if it's a land card. Otherwise, put it into your
    hand.** Then shuffle."                            -- Archdruid's Charm

`_search` resolved a single `DESTINATIONS[...]` and a single `tapped` **before**
it saw what was picked, and `_move_found` sent everything to that one zone. So a
card whose destination is a question *about the found card* could not be written
at all -- and the shapes that look like a workaround are all approximations the
brief forbids: `as` + `if` + `put_onto_battlefield` really does pass the land
through your hand, and it arrives after the search's shuffle.

`destination_if` is a list of branches tried in order, first match winning, with
the op's own `destination` as the fallthrough. In order and with a default,
rather than two mutually exclusive filters, because that is the shape of the
printed sentence -- "if it's a land … otherwise …" -- and two filters could both
miss.

The branches match the **printed** face, which is both what they are asking
about and all there is: the card is still in the library when the question is
put.

`t_sdi_plain` is the same search without the branch, kept live so that every
assertion below is measuring the branch rather than the search.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import pass_until

CHARM = "t_sdi_charm"  # land -> battlefield tapped, else hand
PLAIN = "t_sdi_plain"  # the same search, one destination
BEAR = "t_sdi_bear"  # Creature
WOOD = "t_sdi_wood"  # Land


def position(builder, spell: str, library):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4)
        .library(0, list(library))
        .hand(0, [spell])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def cast(game, card_id: str) -> None:
    """Cast ``card_id``, and actually take the search rather than declining it.

    A search asks with a minimum of zero, so the suite's passive auto-answerer
    answers "none" -- which is a legal way to play and tells this file nothing.
    Every assertion here is about where a found card goes, so the search has to
    be taken; this mirrors the authoring verifier's own rule of preferring a
    real CHOOSE so an optional effect is exercised rather than declined into a
    no-op that would pass any assertion.
    """
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    for _ in range(40):
        pending = game.pending()
        if pending is None or pending.kind is DecisionKind.PRIORITY:
            break
        choice = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None
        )
        if choice is None:
            break
        game.apply(choice)
    pass_until(
        game,
        lambda g: not g.state.stack
        and not g.state.pending_triggers
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def where(game, card_id: str):
    """``(zone, tapped)`` of the one copy of ``card_id``."""
    obj = next(o for o in game.state.objects.values() if o.def_id == card_id)
    return obj.zone, obj.tapped


class TestTheBranchIsTaken:
    def test_a_land_arrives_on_the_battlefield(self, builder):
        game = position(builder, CHARM, [WOOD])
        cast(game, CHARM)
        zone, _ = where(game, WOOD)
        assert zone is Zone.BATTLEFIELD

    def test_and_it_arrives_tapped(self, builder):
        """The branch carries its own `tapped`, not the op's."""
        game = position(builder, CHARM, [WOOD])
        cast(game, CHARM)
        _, tapped = where(game, WOOD)
        assert tapped is True


class TestTheFallthroughIsTaken:
    def test_a_creature_goes_to_hand(self, builder):
        game = position(builder, CHARM, [BEAR])
        cast(game, CHARM)
        zone, _ = where(game, BEAR)
        assert zone is Zone.HAND

    def test_it_is_not_put_onto_the_battlefield(self, builder):
        """The half of the sentence a single destination would have dropped."""
        game = position(builder, CHARM, [BEAR])
        cast(game, CHARM)
        assert where(game, BEAR)[0] is not Zone.BATTLEFIELD


class TestWithoutTheBranch:
    """The control. The same search sends a land to hand like everything else,
    so the assertions above are about `destination_if` and not about lands."""

    def test_a_land_goes_to_hand(self, builder):
        game = position(builder, PLAIN, [WOOD])
        cast(game, PLAIN)
        assert where(game, WOOD)[0] is Zone.HAND


class TestTheLoaderPlacesIt:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Search your library for a card.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def _search(self, **extra):
        return {
            "op": "search_library",
            "selector": {"any_types": ["Creature", "Land"]},
            "destination": "hand",
            **extra,
        }

    def test_a_well_formed_branch_loads(self):
        compile_card(
            self._card(
                self._search(
                    destination_if=[
                        {"selector": {"types": ["Land"]}, "to": "battlefield", "tapped": True}
                    ]
                )
            )
        )

    def test_an_unknown_destination_is_refused(self):
        with pytest.raises(DslError, match="unknown destination"):
            compile_card(
                self._card(
                    self._search(destination_if=[{"selector": {"types": ["Land"]}, "to": "bin"}])
                )
            )

    def test_a_branch_without_a_selector_is_refused(self):
        """A branch that catches everything is not a branch; it is the default
        wearing a hat, and it would swallow the fallthrough silently."""
        with pytest.raises(DslError, match="needs a 'selector'"):
            compile_card(self._card(self._search(destination_if=[{"to": "battlefield"}])))

    def test_it_is_refused_on_any_other_op(self):
        """Ignored elsewhere, the card would send everything to one place --
        the printed line with half its sentence missing."""
        with pytest.raises(DslError, match="read only by search"):
            compile_card(
                self._card(
                    {
                        "op": "draw",
                        "amount": {"const": 1},
                        "destination_if": [{"selector": {"types": ["Land"]}, "to": "hand"}],
                    }
                )
            )
