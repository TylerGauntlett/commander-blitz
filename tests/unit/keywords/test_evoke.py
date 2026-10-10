"""Evoke — an alternative cost that *replaces* the printed one.

    Mulldrifter — "Flying. When this creature enters, draw two cards. Evoke
    {2}{U} (You may cast this spell for its evoke cost. If you do, it's
    sacrificed when it enters.)"

`kicker` was the only card-level mana cost besides `mana_cost`, and it is
explicitly *additive*. Evoke points the other way: it is the whole cost, and the
card is cheaper for it. Both stay out of `mana_cost` for the same reason — mana
value must remain what is printed, so an evoked Mulldrifter is still a five-drop
to Sphinx of Uthuun and to anything else that counts.

The two halves only mean anything together, exactly as with kicker: a cheaper
cast that never dies is a strictly better card, and a sacrifice clause that can
never fire is a worse one. Both would load cleanly, so both are load errors.

The sacrifice is an *enters* trigger, so it depends on the flag outliving the
spell — the same lifetime `cast_kicked` needed for Slinn Voda. `cast_evoked` is
written on the same line for the same reason.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid

EVOKER = {
    "id": "t_evoker_probe",
    "name": "Test Evoker Probe",
    "oracle_text": (
        "When this creature enters, draw two cards.\n"
        "Evoke {2}{U} (You may cast this spell for its evoke cost. If you do, "
        "it's sacrificed when it enters.)"
    ),
    "mana_cost": "{4}{U}",
    "evoke": "{2}{U}",
    "types": ["Creature"],
    "subtypes": ["Elemental"],
    "power": 2,
    "toughness": 2,
    "abilities": [
        {
            "kind": "triggered",
            "text": "When this creature enters, draw two cards.",
            "trigger": {"event": "self_enters"},
            "effects": [{"op": "draw", "player": "you", "amount": {"const": 2}}],
        },
        {
            "kind": "triggered",
            "text": (
                "Evoke {2}{U} (You may cast this spell for its evoke cost. If you "
                "do, it's sacrificed when it enters.)"
            ),
            "trigger": {"event": "self_enters", "condition": {"evoked": True}},
            "effects": [{"op": "sacrifice", "objects": {"self_only": True}}],
        },
    ],
}


def board(builder, lands: int = 8):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * lands)
        .hand(0, ["t_evoker"])
        .library(0, ["forest"] * 20)
        .build()
    )


def casts(game) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == "t_evoker"
    ]


def cast_it(game, *, evoked: bool) -> None:
    wanted = [a for a in casts(game) if a.evoked is evoked]
    assert wanted, f"no {'evoked' if evoked else 'full-price'} variant offered"
    game.apply(wanted[0])


def settle(game) -> None:
    for _ in range(60):
        if game.pending() is not None:
            choose = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind in (ActionKind.YES, ActionKind.CHOOSE)
                ),
                None,
            )
            if choose is None:
                return
            game.apply(choose)
            continue
        if not game.state.stack:
            return
        action = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.PASS), None
        )
        if action is None:
            return
        game.apply(action)


class TestItIsOfferedAsASecondWayToCast:
    def test_both_lines_appear(self, builder):
        game = board(builder)
        assert {a.evoked for a in casts(game)} == {False, True}

    def test_the_evoke_line_is_reachable_on_less_mana(self, builder):
        """The whole point of an alternative cost: three lands is not five."""
        game = board(builder, lands=3)
        variants = {a.evoked for a in casts(game)}
        assert variants == {True}, "only the evoke line should be affordable"

    def test_with_nothing_it_is_not_castable_at_all(self, builder):
        game = board(builder, lands=1)
        assert not casts(game)


class TestTheEvokedCopyDies:
    def test_it_draws_and_then_is_sacrificed(self, builder):
        """Both triggers fire. Evoke does not replace the card's ETB, it adds a
        second one -- which is why Mulldrifter is played for the cards."""
        game = board(builder)
        before = len(game.state.players[0].library)
        cast_it(game, evoked=True)
        settle(game)
        assert len(game.state.players[0].library) == before - 2, "it did not draw"
        assert not [
            o for o in game.state.battlefield_objects(0) if o.def_id == "t_evoker"
        ], "the evoked copy survived"
        assert [
            oid
            for oid in game.state.players[0].graveyard
            if game.state.objects[oid].def_id == "t_evoker"
        ], "it is not in the graveyard either"

    def test_cast_for_full_price_it_stays(self, builder):
        """The pair. A sacrifice clause that fires either way is not evoke, it
        is a drawback the printed card does not have."""
        game = board(builder)
        cast_it(game, evoked=False)
        settle(game)
        oid = only_oid(game, "t_evoker")
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert game.state.objects[oid].cast_evoked is False


class TestManaValueIsUnchanged:
    def test_an_evoked_creature_still_costs_what_it_prints(self, builder):
        """Evoke is not a discount on the card, it is another way to pay. Folding
        it into `mana_cost` would quietly change every mana-value reading."""
        game = board(builder)
        oid = game.state.players[0].hand[0]
        card = game.state.card(oid)
        assert card.mana_cost.mana_value() == 5
        assert card.evoke is not None and card.evoke.mana_value() == 3
        cast_it(game, evoked=True)
        settle(game)
        # Still 5 after being cast for 3: the cost paid and the mana value are
        # different questions, and only the first one changed.
        assert game.state.card(oid).mana_cost.mana_value() == 5


class TestLoadTimeGuards:
    def test_a_cost_nothing_reads_is_refused(self):
        card = copy.deepcopy(EVOKER)
        card["abilities"].pop(1)
        with pytest.raises(DslError, match="no effect reads via 'evoked'"):
            compile_card(CardModel.model_validate(card))

    def test_a_reader_with_no_cost_is_refused(self):
        card = copy.deepcopy(EVOKER)
        card.pop("evoke")
        with pytest.raises(DslError, match="reads the 'evoked' condition"):
            compile_card(CardModel.model_validate(card))

    def test_an_evoke_cost_that_is_not_cheaper_is_refused(self):
        """An alternative cost nobody would take is dead weight that reads as a
        mechanic."""
        card = copy.deepcopy(EVOKER)
        card["evoke"] = "{5}{U}"
        with pytest.raises(DslError, match="not cheaper"):
            compile_card(CardModel.model_validate(card))

    def test_the_card_itself_loads(self):
        card = compile_card(CardModel.model_validate(EVOKER))
        assert card.evoke is not None
        assert card.mana_cost.mana_value() == 5
