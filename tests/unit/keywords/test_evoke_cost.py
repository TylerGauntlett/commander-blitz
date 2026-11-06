"""Evoke with a price the mana string cannot say.

Rule 702.74a: "Evoke [cost]" means "You may cast this card by paying [cost]
rather than paying its mana cost" and "When this permanent enters, if its evoke
cost was paid, its controller sacrifices it." The cost is any cost, and two
printed shapes are not a cheaper mana string:

* **Endurance** -- "Evoke—Exile a green card from your hand." No mana at all.
  Written as `alternative_cost` it would be Force of Will's pitch, offered and
  paid correctly, and never evoked: `cast_evoked` stays false, the
  `{"evoked": true}` sacrifice never fires, and a 3/4 reach flash creature costs
  one card and stays. So the evoke key takes a cost node, and the line it buys
  is the evoke line. 601.2a still holds: the spell is on the stack before its
  costs are paid, so Endurance in hand is not a green card it may pitch.
* **Slithermuse** -- printed {2}{U}{U}, evoke {3}{U}. The same mana value and a
  different cast: one Island and three other lands pay the evoke and not the
  printed cost. The loader's "one cast offered twice" refusal has to compare
  the symbols, or it refuses the printed card.

`t_pitch_evoker` and `t_slithermuse_probe` in `tests/data/evoke_cost.cards.json`
are the two shapes.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import TEST_CARD_DIR, settle

PITCH = "t_pitch_evoker"
MUSE = "t_slithermuse_probe"


def _raw(card_id: str) -> dict:
    cards = json.loads(Path(TEST_CARD_DIR / "evoke_cost.cards.json").read_text())["cards"]
    return copy.deepcopy(next(c for c in cards if c["id"] == card_id))


def position(builder, card_id: str, *, hand=(), lands=()):
    """``card_id`` in player 0's hand beside ``hand``, over ``lands``, and the oid.

    A Forest waits unplayed in hand as well. It keeps player 0 holding priority
    -- a player with nothing to do is auto-passed, and the assertions below
    would then be about the wrong seat -- and it is the boundary for "a green
    card": a land is colourless.
    """
    game = (
        builder(players=2)
        .hand(0, [card_id, "forest", *hand])
        .battlefield(0, list(lands))
        .library(0, ["forest"] * 10)
        .build()
    )
    oid = next(
        o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id
    )
    return game, oid


def casts(game, oid: int) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def evoke_lines(game, oid: int) -> list:
    return [a for a in casts(game, oid) if a.evoked]


def in_hand(game, card_id: str) -> int:
    return next(
        o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id
    )


def pitch(game, fodder: int) -> None:
    """Answer the evoke cost's "Exile from your hand" with ``fodder``.

    Asked only when there is a choice: a hand with one card that qualifies has
    paid already, with that card.
    """
    decision = game.pending()
    if decision is None or decision.kind is not DecisionKind.CHOOSE_OBJECTS:
        assert game.state.objects[fodder].zone is Zone.EXILE, "nothing was asked or exiled"
        return
    index = next(i for i, o in enumerate(decision.options) if o.ref and o.ref.id == fodder)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )
    if game.pending() is decision:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


class TestThePitchEvokeIsOffered:
    def test_another_green_card_in_hand_buys_the_line(self, builder):
        """No lands at all: the line is the pitch and nothing else."""
        game, oid = position(builder, PITCH, hand=["grizzly_bears"])
        assert [a.evoked for a in casts(game, oid)] == [True]

    def test_the_spell_may_not_pitch_itself(self, builder):
        """601.2a. Endurance is the only green card in hand, so there is no line."""
        game, oid = position(builder, PITCH)
        assert evoke_lines(game, oid) == []

    def test_a_card_of_another_colour_does_not(self, builder):
        game, oid = position(builder, PITCH, hand=["lightning_bolt"])
        assert evoke_lines(game, oid) == []

    def test_a_second_copy_is_a_green_card(self, builder):
        """The exclusion is the spell being cast, not every card with its name."""
        game, oid = position(builder, PITCH, hand=[PITCH])
        assert evoke_lines(game, oid)

    def test_the_printed_price_is_offered_beside_it(self, builder):
        game, oid = position(builder, PITCH, hand=["grizzly_bears"], lands=["forest"] * 3)
        assert {a.evoked for a in casts(game, oid)} == {False, True}

    def test_without_green_fodder_it_is_the_printed_cost_only(self, builder):
        """Without green fodder the card is an ordinary three-drop."""
        game, oid = position(builder, PITCH, lands=["forest"] * 3)
        assert [a.evoked for a in casts(game, oid)] == [False]


class TestThePitchEvokeIsPaidAndEvoked:
    def test_the_pitched_card_leaves_hand_for_exile(self, builder):
        game, oid = position(builder, PITCH, hand=["grizzly_bears"])
        fodder = in_hand(game, "grizzly_bears")
        game.apply(evoke_lines(game, oid)[0])
        pitch(game, fodder)
        assert fodder not in game.state.players[0].hand
        assert game.state.objects[fodder].zone is Zone.EXILE

    def test_with_two_candidates_the_chosen_one_goes(self, builder):
        game, oid = position(builder, PITCH, hand=["grizzly_bears", "llanowar_elves"])
        kept, fodder = in_hand(game, "grizzly_bears"), in_hand(game, "llanowar_elves")
        game.apply(evoke_lines(game, oid)[0])
        assert game.pending().kind is DecisionKind.CHOOSE_OBJECTS
        pitch(game, fodder)
        assert game.state.objects[fodder].zone is Zone.EXILE
        assert game.state.objects[kept].zone is Zone.HAND

    def test_the_cast_is_evoked_and_the_creature_is_sacrificed(self, builder):
        """The whole difference from `alternative_cost`: the flag, and the rule's
        sacrifice that reads it."""
        game, oid = position(builder, PITCH, hand=["grizzly_bears"])
        fodder = in_hand(game, "grizzly_bears")
        game.apply(evoke_lines(game, oid)[0])
        pitch(game, fodder)
        settle(game)
        obj = game.state.objects[oid]
        assert obj.cast_evoked is True
        assert obj.zone is Zone.GRAVEYARD, "an evoked creature is sacrificed when it enters"

    def test_no_mana_is_spent(self, builder):
        game, oid = position(builder, PITCH, hand=["grizzly_bears"], lands=["forest"] * 3)
        fodder = in_hand(game, "grizzly_bears")
        game.apply(evoke_lines(game, oid)[0])
        pitch(game, fodder)
        settle(game)
        assert not any(o.tapped for o in game.state.battlefield_objects(0))

    def test_cast_for_its_mana_cost_nothing_is_exiled_and_it_stays(self, builder):
        game, oid = position(builder, PITCH, hand=["grizzly_bears"], lands=["forest"] * 3)
        fodder = in_hand(game, "grizzly_bears")
        game.apply(next(a for a in casts(game, oid) if not a.evoked))
        settle(game)
        assert game.state.objects[fodder].zone is Zone.HAND
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert game.state.objects[oid].cast_evoked is False


class TestTheSameManaValueWithDifferentSymbols:
    def test_one_island_pays_the_evoke_and_not_the_printed_cost(self, builder):
        game, oid = position(builder, MUSE, lands=["island", "forest", "forest", "forest"])
        assert [a.evoked for a in casts(game, oid)] == [True]

    def test_with_two_islands_both_lines_are_offered(self, builder):
        game, oid = position(builder, MUSE, lands=["island", "island", "forest", "forest"])
        assert {a.evoked for a in casts(game, oid)} == {False, True}

    def test_evoked_it_is_sacrificed(self, builder):
        game, oid = position(builder, MUSE, lands=["island", "forest", "forest", "forest"])
        game.apply(evoke_lines(game, oid)[0])
        settle(game)
        assert game.state.objects[oid].cast_evoked is True
        assert game.state.objects[oid].zone is Zone.GRAVEYARD


class TestLoadTimeGuards:
    def test_both_shapes_load(self):
        pitch_card = compile_card(CardModel.model_validate(_raw(PITCH)))
        assert pitch_card.evoke is not None and pitch_card.evoke.mana_value() == 0
        assert pitch_card.evoke_payment is not None
        assert pitch_card.evoke_payment.exile_from_hand == {"colors": ["G"]}
        muse = compile_card(CardModel.model_validate(_raw(MUSE)))
        assert muse.evoke is not None and muse.evoke.mana_value() == muse.mana_cost.mana_value()
        assert muse.evoke_payment is None

    @pytest.mark.parametrize("same", ["{2}{U}{U}", "{U}{2}{U}"])
    def test_the_printed_symbols_are_refused_in_any_order(self, same):
        card = _raw(MUSE)
        card["evoke"] = same
        with pytest.raises(DslError, match="costs the same as the printed cost"):
            compile_card(CardModel.model_validate(card))

    def test_a_mana_only_node_compiles_as_the_string_does(self):
        as_string = compile_card(CardModel.model_validate(_raw(MUSE)))
        card = _raw(MUSE)
        card["evoke"] = {"mana": "{3}{U}"}
        as_node = compile_card(CardModel.model_validate(card))
        assert as_node.evoke == as_string.evoke and as_node.evoke_payment is None

    def test_a_node_that_charges_nothing_is_refused(self):
        card = _raw(PITCH)
        card["evoke"] = {}
        with pytest.raises(DslError, match="needs 'mana' or a non-mana payment"):
            compile_card(CardModel.model_validate(card))

    @pytest.mark.parametrize("key", [{"tap": True}, {"exile_self_from_hand": True}])
    def test_a_cost_on_the_source_permanent_is_refused(self, key):
        """A spell in hand has no {T} and is not a card it can exile from hand."""
        card = _raw(PITCH)
        card["evoke"] = {**card["evoke"], **key}
        with pytest.raises(DslError, match="charge the source permanent"):
            compile_card(CardModel.model_validate(card))

    def test_the_sacrifice_is_still_required(self):
        """A pitch evoke nothing reads is a free creature that never dies."""
        card = _raw(PITCH)
        card["abilities"] = []
        with pytest.raises(DslError, match="no effect reads via 'evoked'"):
            compile_card(CardModel.model_validate(card))
