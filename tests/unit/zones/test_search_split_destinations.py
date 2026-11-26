"""One search, two destinations: one found card here, the rest there.

    "…search your library for a number of Plains cards equal to the
    difference, reveal those cards, **put one of them onto the battlefield
    tapped and the rest into your hand**, then shuffle."   -- Boreas Charger

701.19 makes a search one action, and Boreas Charger, Cultivate and Kodama's
Reach are each one search. Chaining two `search_library` ops (one card to the
battlefield without a shuffle, then the rest to hand) is a different card three
ways: it fires LIBRARY_SEARCHED twice (an Archivist of Oghma draws two), it
carries two independent "up to" counts, and it lets the player take every land
to hand and put none onto the battlefield, which "put one of them onto the
battlefield" forbids.

`rest_to` on the search splits what one search found: the searcher picks the
cards, then picks which one goes to `destination` (with `tapped`), and the rest
go to `rest_to`. A single find goes to `destination`. The shuffle happens once,
after both moves.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import ops_cards
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import find_action, pass_until

CULTIVATE = "t_ssd_cultivate"  # up to two basics: one battlefield tapped, other hand
GRAVE = "t_ssd_grave"  # three cards: one hand, the rest graveyard


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


def cast(game, card_id: str, *, take, first=None) -> None:
    """Cast ``card_id``, search for the oids in ``take``, and send ``first`` to
    the op's `destination` when the split is asked."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        )
    )
    pass_until(game, lambda g: g.pending() is not None and g.pending().kind is not DecisionKind.PRIORITY)
    for _ in range(40):
        pending = game.pending()
        if pending is None or pending.kind is not DecisionKind.CHOOSE_OBJECTS:
            break
        wanted = set(take) if pending.prompt.startswith("Search") else {first}
        index = next(
            (
                i
                for i, option in enumerate(pending.options)
                if option.ref is not None and option.ref.id in wanted
            ),
            None,
        )
        if index is None:
            game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
            continue
        if pending.prompt.startswith("Search"):
            take = [oid for oid in take if oid != pending.options[index].ref.id]
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
        )
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def resolve_with_counts(monkeypatch, game, card_id, **kw):
    """Cast and resolve, counting LIBRARY_SEARCHED events and shuffles."""
    searched: list[int] = []
    shuffles: list[int] = []
    real_fire, real_shuffle = ops_cards.fire, ops_cards.shuffle_library

    def fire(state, event_type, **payload):
        if event_type is EventType.LIBRARY_SEARCHED:
            searched.append(payload["player"])
        return real_fire(state, event_type, **payload)

    def shuffle(state, pid):
        shuffles.append(pid)
        return real_shuffle(state, pid)

    monkeypatch.setattr(ops_cards, "fire", fire)
    monkeypatch.setattr(ops_cards, "shuffle_library", shuffle)
    cast(game, card_id, **kw)
    return searched, shuffles


def oids_of(game, card_id: str, pid: int = 0) -> list[int]:
    """Every copy of ``card_id`` that ``pid`` owns, in any zone (the conftest
    helper reads only the battlefield, and these cards start in the library)."""
    return sorted(
        o.oid for o in game.state.objects.values() if o.def_id == card_id and o.owner == pid
    )


def obj(game, oid):
    return game.state.objects[oid]


class TestOneHereTheRestThere:
    def test_the_chosen_one_enters_tapped_and_the_other_goes_to_hand(self, builder):
        game = position(builder, CULTIVATE, ["forest", "island", "swamp"])
        island, swamp = oids_of(game, "island", 0)[0], oids_of(game, "swamp", 0)[0]
        cast(game, CULTIVATE, take=[island, swamp], first=swamp)
        assert obj(game, swamp).zone is Zone.BATTLEFIELD
        assert obj(game, swamp).tapped is True
        assert obj(game, island).zone is Zone.HAND

    def test_the_searcher_decides_which_one(self, builder):
        """The same find with the other card chosen: the split is the
        player's choice, not the order the library was in."""
        game = position(builder, CULTIVATE, ["forest", "island", "swamp"])
        island, swamp = oids_of(game, "island", 0)[0], oids_of(game, "swamp", 0)[0]
        cast(game, CULTIVATE, take=[island, swamp], first=island)
        assert obj(game, island).zone is Zone.BATTLEFIELD
        assert obj(game, swamp).zone is Zone.HAND

    def test_the_rest_is_not_tapped(self, builder):
        """`tapped` belongs to `destination` alone."""
        game = position(builder, CULTIVATE, ["island", "swamp"])
        island, swamp = oids_of(game, "island", 0)[0], oids_of(game, "swamp", 0)[0]
        cast(game, CULTIVATE, take=[island, swamp], first=swamp)
        assert obj(game, island).tapped is False

    def test_the_other_split_direction(self, builder):
        """One to hand, the rest to the graveyard -- Intuition's destinations."""
        game = position(builder, GRAVE, ["island", "swamp", "plains", "mountain"])
        island, swamp, plains = (oids_of(game, c, 0)[0] for c in ("island", "swamp", "plains"))
        cast(game, GRAVE, take=[island, swamp, plains], first=plains)
        assert obj(game, plains).zone is Zone.HAND
        assert obj(game, island).zone is Zone.GRAVEYARD
        assert obj(game, swamp).zone is Zone.GRAVEYARD
        assert obj(game, oids_of(game, "mountain", 0)[0]).zone is Zone.LIBRARY


class TestTheBoundary:
    def test_a_single_find_goes_to_the_first_destination(self, builder):
        """"Put one of them onto the battlefield" is satisfied first; the rest
        is then empty. No choice is asked of one card."""
        game = position(builder, CULTIVATE, ["island", "lightning_bolt"])
        island = oids_of(game, "island", 0)[0]
        cast(game, CULTIVATE, take=[island])
        assert obj(game, island).zone is Zone.BATTLEFIELD
        assert obj(game, island).tapped is True

    def test_finding_nothing_moves_nothing(self, builder):
        game = position(builder, CULTIVATE, ["island", "swamp"])
        cast(game, CULTIVATE, take=[])
        for oid in oids_of(game, "island", 0) + oids_of(game, "swamp", 0):
            assert obj(game, oid).zone is Zone.LIBRARY


class TestItIsOneSearch:
    def test_one_library_searched_event_and_one_shuffle(self, builder, monkeypatch):
        """The two-op approximation fires LIBRARY_SEARCHED twice; one op once."""
        game = position(builder, CULTIVATE, ["island", "swamp", "forest"])
        island, swamp = oids_of(game, "island", 0)[0], oids_of(game, "swamp", 0)[0]
        searched, shuffles = resolve_with_counts(
            monkeypatch, game, CULTIVATE, take=[island, swamp], first=island
        )
        assert searched == [0]
        assert shuffles == [0]


class TestTheLoaderPlacesIt:
    def _card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Search your library for two cards.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "spell_effects": [
                    {"op": "search_library", "count": 2, "destination": "battlefield", **extra}
                ],
            }
        )

    def test_a_well_formed_split_loads(self):
        compile_card(self._card(rest_to="hand", tapped=True))

    @pytest.mark.parametrize("rest", ["battlefield", "library_top", "bin"])
    def test_an_unsupported_rest_destination_is_refused(self, rest):
        with pytest.raises(DslError, match="'rest_to' is 'hand'"):
            compile_card(self._card(rest_to=rest))

    def test_the_same_zone_twice_is_refused(self):
        with pytest.raises(DslError, match="is the 'destination' too"):
            compile_card(self._card(rest_to="hand", destination="hand"))

    def test_a_second_answer_to_where_is_refused(self):
        with pytest.raises(DslError, match="'rest_to' or 'destination_if'"):
            compile_card(
                self._card(
                    rest_to="hand",
                    destination_if=[{"selector": {"types": ["Land"]}, "to": "graveyard"}],
                )
            )
