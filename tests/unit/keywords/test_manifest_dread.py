"""`manifest_dread` -- "Look at the top two cards of your library. Put one onto
the battlefield face down as a 2/2 creature and the other into your graveyard."

Rule 701.62a: to manifest dread is to look at the top two cards of your
library, then manifest one of them and put the other into your graveyard.
Growing Dread, Curator Beastie, Glitch Interpreter, They Came from the Pipes,
Zimone and Experimental Lab are the witnesses.

`manifest` was the near miss, and the wrong card in both directions: it
manifests the top card blind, so the player loses the choice that is the whole
of the mechanic, and nothing goes to the graveyard, so a card that counts or
recurs what is there gets a card less. Chaining a `mill` and a `manifest`
picks for the player; `look_at_top` picks and bins but cannot put a card onto
the battlefield as a manifested 2/2.

The rules arguments the tests below make:

* **The manifesting player chooses**, between the two cards looked at, and the
  other is put into their graveyard -- a land manifested is as legal as a
  creature, and a creature manifested turns up for its own mana cost (701.34c),
  because the placement is `manifest`'s.
* **A short library.** With one card, that card is manifested and nothing is
  binned, with no question asked; with none, nothing happens and nobody loses,
  since manifest dread is not a draw (704.5b reads an attempted draw).
* **"That creature"** -- Experimental Lab's "then put two +1/+1 counters on that
  creature" -- is the `as` binding, which names the manifested permanent and
  never the binned card.
* **The arrival is face down.** It is the same arrival `manifest` makes, so
  "whenever a face-down creature you control enters" hears it and landfall does
  not hear a manifested land (708.2; see `test_face_down_filter.py`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card, pass_until, plus_one_counters, settle_completely

FOREST = "forest"
BEAR = "grizzly_bears"
DREAD = "t_md_dread"  # "When this enchantment enters, manifest dread."
TWICE = "t_md_twice"  # "...manifest dread twice."
LAB = "t_md_lab"  # "...manifest dread, then put two +1/+1 counters on that creature."
PIPES = "t_fdf_pipes"  # "Whenever a face-down creature you control enters, draw a card."
LANDFALL = "t_fdf_landfall"  # "Whenever a land you control enters, gain 1 life."


def board(builder, card=DREAD, *, library=(BEAR, FOREST, FOREST, FOREST), mine=()):
    """Player 0 with eight Forests and ``mine``, ``card`` in hand, and exactly
    ``library`` as their library, top first."""
    return (
        builder(players=2)
        .battlefield(0, [FOREST] * 8 + list(mine))
        .hand(0, [card, BEAR])
        .library(0, list(library))
        .library(1, [FOREST] * 20)
        .build()
    )


def dread_decision(game):
    """Cast the card in hand and run to the manifest-dread question, or to the
    end if none is asked. Returns the decision, or ``None``."""
    card = next(
        game.state.objects[oid].def_id
        for oid in game.state.players[0].hand
        if game.state.objects[oid].def_id != BEAR
    )
    game.apply(action_for_card(game, ActionKind.CAST, card))

    def asked_or_done(g) -> bool:
        d = g.pending()
        if d is not None and d.context.get("purpose") == "manifest_dread":
            return True
        return not g.state.stack and not g.state.pending_triggers

    pass_until(game, asked_or_done)
    d = game.pending()
    return d if d is not None and d.context.get("purpose") == "manifest_dread" else None


def choose(game, oid: int) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and a.targets and a.targets[0].id == oid
        )
    )


def manifest_dread(game, pick: int | None = None) -> None:
    """Cast, answer the question with ``pick`` (the top card if not given),
    and settle."""
    decision = dread_decision(game)
    if decision is not None:
        choose(game, pick if pick is not None else game.state.players[0].library[0])
    settle_completely(game)


def top_two(game) -> tuple[int, int]:
    library = game.state.players[0].library
    return library[0], library[1]


def graveyard(game) -> list[int]:
    return list(game.state.players[0].graveyard)


class TestTheChoice:
    def test_the_player_is_asked_between_the_top_two(self, builder):
        game = board(builder)
        bear, forest = top_two(game)

        decision = dread_decision(game)

        assert decision is not None
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.player == 0
        assert (decision.min_count, decision.max_count) == (1, 1)
        assert {o.value for o in decision.options} == {bear, forest}

    def test_the_chosen_card_is_manifested(self, builder):
        game = board(builder)
        bear, _ = top_two(game)

        manifest_dread(game, bear)

        assert game.state.objects[bear].face_down
        assert bear in [o.oid for o in game.state.battlefield_objects(0)]
        c = chars(game.state, bear)
        assert (c.power, c.toughness) == (2, 2)

    def test_the_other_goes_to_the_graveyard(self, builder):
        game = board(builder)
        bear, forest = top_two(game)

        manifest_dread(game, bear)

        assert graveyard(game) == [forest]

    def test_the_other_way_round(self, builder):
        """A land may be the one manifested (701.34a puts any card down)."""
        game = board(builder)
        bear, forest = top_two(game)

        manifest_dread(game, forest)

        assert game.state.objects[forest].face_down
        assert graveyard(game) == [bear]

    def test_a_manifested_creature_card_turns_up_for_its_mana_cost(self, builder):
        """The placement is `manifest`'s: 701.34c's turn-up comes with it."""
        game = board(builder)
        bear, _ = top_two(game)
        manifest_dread(game, bear)

        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == bear
            )
        )

        assert not game.state.objects[bear].face_down

    def test_twice_is_two_looks(self, builder):
        """They Came from the Pipes: the second look is at what the first left."""
        cards = (BEAR, FOREST, BEAR, FOREST, FOREST)
        game = board(builder, TWICE, library=cards)
        first = top_two(game)
        second = tuple(game.state.players[0].library[2:4])

        decision = dread_decision(game)
        assert {o.value for o in decision.options} == set(first)
        choose(game, first[0])
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None and d.context.get("purpose") == "manifest_dread",
        )
        assert {o.value for o in game.pending().options} == set(second)
        choose(game, second[1])
        settle_completely(game)

        assert game.state.objects[first[0]].face_down
        assert game.state.objects[second[1]].face_down
        assert sorted(graveyard(game)) == sorted([first[1], second[0]])
        assert len(game.state.players[0].library) == 1


class TestAShortLibrary:
    def test_one_card_is_manifested_without_a_question(self, builder):
        game = board(builder, library=(BEAR,))
        bear = game.state.players[0].library[0]

        assert dread_decision(game) is None
        settle_completely(game)

        assert game.state.objects[bear].face_down
        assert graveyard(game) == []

    def test_an_empty_library_does_nothing_and_loses_nobody(self, builder):
        """Not a draw: 704.5b never sees an attempted draw."""
        game = board(builder, library=())

        assert dread_decision(game) is None
        settle_completely(game)

        assert not any(o.face_down for o in game.state.battlefield_objects(0))
        assert not game.state.players[0].has_lost
        assert graveyard(game) == []


class TestThatCreature:
    def test_as_names_the_manifested_permanent(self, builder):
        """Experimental Lab: the counters go on the manifest, whichever card it is."""
        game = board(builder, LAB)
        bear, forest = top_two(game)

        manifest_dread(game, forest)

        assert plus_one_counters(game, forest) == 2
        assert plus_one_counters(game, bear) == 0

    def test_as_on_an_empty_library_names_nothing(self, builder):
        game = board(builder, LAB, library=())

        manifest_dread(game)

        assert all(plus_one_counters(game, o.oid) == 0 for o in game.state.battlefield_objects(0))


class TestTheArrival:
    def test_a_face_down_creature_entering_is_heard(self, builder):
        """They Came from the Pipes, even when the card underneath is a land."""
        game = board(builder, mine=[PIPES])
        _, forest = top_two(game)
        hand = len(game.state.players[0].hand)

        manifest_dread(game, forest)

        # The enchantment left the hand; the Pipes drew one.
        assert len(game.state.players[0].hand) == hand

    def test_a_manifested_land_is_not_landfall(self, builder):
        game = board(builder, mine=[LANDFALL])
        _, forest = top_two(game)
        life = game.state.players[0].life

        manifest_dread(game, forest)

        assert game.state.players[0].life == life


class TestTheLoaderGuards:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_md_probe",
                "name": "Test Dread Probe",
                "oracle_text": "Manifest dread.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "colors": ["G"],
                "color_identity": ["G"],
                "spell_effects": [effect],
            }
        )

    def test_the_test_cards_load(self):
        compile_card(self._card({"op": "manifest_dread"}))
        compile_card(self._card({"op": "manifest_dread", "as": "it"}))
        compile_card(self._card({"op": "manifest_dread", "amount": {"const": 2}}))

    @pytest.mark.parametrize(
        "key, value",
        [
            ("cloak", True),
            ("objects", {"types": ["Creature"]}),
            ("destination", "hand"),
            ("rest_to", "exile"),
        ],
    )
    def test_borrowed_keys_are_refused(self, key, value):
        with pytest.raises(DslError, match=f"manifest_dread .* takes no '{key}'"):
            compile_card(self._card({"op": "manifest_dread", key: value}))

    def test_as_is_a_name(self):
        with pytest.raises(DslError, match="'as'"):
            compile_card(self._card({"op": "manifest_dread", "as": 3}))
