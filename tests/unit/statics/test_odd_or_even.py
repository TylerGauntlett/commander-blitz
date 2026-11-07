"""Odd or even -- ``{"parity": "even"|"odd"}`` on a ``power`` clause.

    Kianne, Corrupted Memory -- "As long as Kianne's power is even, you may cast
    noncreature spells as though they had flash. As long as Kianne's power is
    odd, you may cast creature spells as though they had flash. Whenever you
    draw a card, put a +1/+1 counter on Kianne."

    Zimone's Hypothesis -- "You may put a +1/+1 counter on a creature. Then
    choose odd or even. Return each creature with power of the chosen quality
    to its owner's hand. (Zero is even.)"

An integer is even when it is divisible by two and odd otherwise; zero is even,
which Zimone's Hypothesis prints, and a negative power is odd or even by the
same rule. Power is a number with no upper bound, so "power is even" cannot be
written as a list of equalities, and every comparison the clause had (``op``
against a ``value``) is a different question.

Kianne's condition reads its **current** power (613.4: counters at 7c, pumps at
7c, anthems at 7c), because the third line is the whole engine of the card: each
draw puts a counter on it and flips which half of the deck has flash. A static's
plain `exists` reads base power -- the pipeline-input rule that keeps ADR 0001's
layer order acyclic -- so written with it the 2/2 would read even for ever.
`exists_derived` reads `chars`, and is admitted only on the statics whose reader
runs outside the layer pipeline (`STATIC_DERIVED_CONDITION_EFFECTS`).
`cast_as_though_flash` is one: `player_casts_as_though_flash` is asked by
`casting._timing_ok` at cast legality and never by a layer, so Kianne reading
its own derived power depends on nothing a layer is still computing. It walks
with ``derived``, and every pipeline walk still defers the leaf.

Zimone's Hypothesis needs no machinery beyond the clause: a `choose_mode` of two
`return_to_hand` modes, one per parity. The choice is made on resolution, after
the counter -- "then choose" -- which `chooser: "you"` gives it: a top-level
`choose_mode` without one is answered as the spell is cast (601.2b), which
would make it a modal spell announcing its parity on the stack.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import legality
from commanderblitz.engine.characteristics import (
    _compare_printed,
    _static_active,
    compare_pt,
    parity_matches,
)
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, pump
from commanderblitz.engine.triggers import _compare as trigger_compare
from tests.conftest import oids_of, only_oid, pass_until, pt

KIANNE = "t_oe_kianne"  # 2/2, the two parity-gated flash permissions
HYPOTHESIS = "t_oe_hypothesis"  # Zimone's Hypothesis
WALL = "t_oe_wall"  # 0/3
ONE = "t_oe_one"  # 1/1
TWO = "t_oe_two"  # 2/2
SORCERY = "t_sorcery"  # {R} sorcery: a noncreature spell
CREATURE = "t_flash_sorcery_target"  # {R} creature spell


def kianne_board(builder, *, active: int = 1):
    """Player 0 holds Kianne, a sorcery and a creature; by default it is player 1's turn.

    Off-turn is where a timing permission shows: in its own main phase player 0
    could cast both anyway.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["mountain"] * 4 + [KIANNE])
        .battlefield(1, ["mountain"] * 4)
        .hand(0, [SORCERY, CREATURE])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(active)
        .build(advance=False)
    )
    return game, only_oid(game, KIANNE, 0)


def can_cast(game, card_id: str, pid: int = 0) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in legality._priority_actions(game.state, pid)
    )


def flash_for(game) -> tuple[bool, bool]:
    """(noncreature spell castable off-turn, creature spell castable off-turn)."""
    return can_cast(game, SORCERY), can_cast(game, CREATURE)


class TestTheParity:
    @pytest.mark.parametrize(
        ("value", "even"), [(0, True), (1, False), (2, True), (7, False), (-1, False), (-2, True)]
    )
    def test_the_remainder_decides_and_zero_is_even(self, value, even):
        assert compare_pt(value, {"parity": "even"}) is even
        assert compare_pt(value, {"parity": "odd"}) is not even

    def test_a_comparison_is_not_a_parity(self):
        assert parity_matches(3, {"op": ">=", "value": 2}) is None

    def test_every_reader_of_the_clause_answers_it(self):
        """A parity read as a defaulted ``>= 0`` anywhere would match everything."""
        assert not _compare_printed(3, {"parity": "even"})
        assert not trigger_compare(3, {"parity": "even"})
        assert trigger_compare(0, {"parity": "even"})


class TestThePipelineStillDefers:
    def test_a_walk_without_derived_never_evaluates_it(self, builder):
        """`chars`' walks ask with no permanent: the leaf is deferred, not read."""
        game, kianne = kianne_board(builder)
        add_counters(game.state, kianne, "+1/+1", 1)
        obj = game.state.objects[kianne]
        even, odd = (a.static for a in game.state.card_of(obj).abilities)

        assert _static_active(game.state, obj, even)
        assert not _static_active(game.state, obj, even, derived=True)
        assert _static_active(game.state, obj, odd, derived=True)


class TestKianneFlipsWithItsPower:
    def test_even_power_gives_noncreature_spells_flash(self, builder):
        game, _ = kianne_board(builder)
        assert flash_for(game) == (True, False)

    def test_a_counter_makes_it_odd_and_creatures_get_flash(self, builder):
        game, kianne = kianne_board(builder)
        add_counters(game.state, kianne, "+1/+1", 1)

        assert pt(game, kianne) == (3, 3)
        assert flash_for(game) == (False, True)

    def test_a_second_counter_flips_it_back(self, builder):
        game, kianne = kianne_board(builder)
        add_counters(game.state, kianne, "+1/+1", 1)
        add_counters(game.state, kianne, "+1/+1", 1)

        assert flash_for(game) == (True, False)

    def test_a_pump_is_current_power_too(self, builder):
        """+1/+0 until end of turn makes the 2/2 odd as surely as a counter does."""
        game, kianne = kianne_board(builder)
        pump(game.state, kianne, 1, 0)

        assert flash_for(game) == (False, True)

    def test_zero_power_is_even(self, builder):
        game, kianne = kianne_board(builder)
        pump(game.state, kianne, -2, 0)

        assert pt(game, kianne) == (0, 2)
        assert flash_for(game) == (True, False)

    def test_negative_one_is_odd(self, builder):
        game, kianne = kianne_board(builder)
        pump(game.state, kianne, -3, 0)

        assert pt(game, kianne)[0] == -1
        assert flash_for(game) == (False, True)

    def test_it_is_scoped_to_its_controller(self, builder):
        game, _ = kianne_board(builder, active=0)
        assert not can_cast(game, SORCERY, pid=1)

    def test_without_kianne_neither_has_flash(self, builder):
        game, kianne = kianne_board(builder)
        game.state.battlefield.remove(kianne)
        game.state.bump_chars()

        assert flash_for(game) == (False, False)


class TestTheHypothesis:
    def board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["island"] * 5 + [WALL, ONE])
            .battlefield(1, [TWO])
            .hand(0, [HYPOTHESIS])
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .active(0)
            .max_turns(1)
            .build()
        )

    def resolve(self, game, *, counter_on: int | None, parity: str) -> list[DecisionKind]:
        """Cast it, put the counter on ``counter_on`` (or decline), choose ``parity``."""
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == HYPOTHESIS
            )
        )
        asked: list[DecisionKind] = []
        # Nothing is chosen as it is cast: the spell goes on the stack unmoded.
        assert game.pending().kind is not DecisionKind.CHOOSE_MODE
        for _ in range(50):
            decision = game.pending()
            if decision is None or (decision.kind is DecisionKind.PRIORITY and not game.state.stack):
                break
            if decision.kind is DecisionKind.CHOOSE_OBJECTS:
                asked.append(decision.kind)
                pick = next(
                    (
                        a
                        for a in game.legal_actions()
                        if a.kind is ActionKind.CHOOSE
                        and decision.options[a.choice].ref is not None
                        and decision.options[a.choice].ref.id == counter_on
                    ),
                    None,
                )
                game.apply(pick or next(
                    a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION
                ))
                continue
            if decision.kind is DecisionKind.CHOOSE_MODE:
                asked.append(decision.kind)
                assert decision.player == 0
                index = [o.label for o in decision.options].index(parity)
                game.apply(
                    next(
                        a
                        for a in game.legal_actions()
                        if a.kind is ActionKind.CHOOSE and a.choice == index
                    )
                )
                continue
            pass_until(game, lambda g, d=decision: g.pending() is not d, limit=5)
        return asked

    def test_even_returns_the_zero_and_the_two(self, builder):
        game = self.board(builder)
        wall, one, two = only_oid(game, WALL, 0), only_oid(game, ONE, 0), only_oid(game, TWO, 1)

        self.resolve(game, counter_on=None, parity="Even")

        assert game.state.objects[wall].zone is Zone.HAND
        assert game.state.objects[two].zone is Zone.HAND
        assert oids_of(game, ONE, 0) == [one]

    def test_odd_returns_the_one(self, builder):
        game = self.board(builder)
        one = only_oid(game, ONE, 0)

        self.resolve(game, counter_on=None, parity="Odd")

        assert oids_of(game, ONE, 0) == []
        assert game.state.objects[one].zone is Zone.HAND
        assert len(oids_of(game, WALL, 0)) == 1
        assert len(oids_of(game, TWO, 1)) == 1

    def test_the_counter_comes_first_and_the_parity_reads_it(self, builder):
        """The 2/2 given a counter is a 3/3 when "odd" is chosen: it goes too."""
        game = self.board(builder)
        two = only_oid(game, TWO, 1)

        asked = self.resolve(game, counter_on=two, parity="Odd")

        assert asked == [DecisionKind.CHOOSE_OBJECTS, DecisionKind.CHOOSE_MODE]
        assert oids_of(game, TWO, 1) == []
        assert oids_of(game, ONE, 0) == []
        assert len(oids_of(game, WALL, 0)) == 1


def probe(**power) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_oe_probe",
            "name": "Parity Probe",
            "mana_cost": "{1}",
            "types": ["Creature"],
            "power": 2,
            "toughness": 2,
            "abilities": [
                {
                    "kind": "static",
                    "text": "Probe.",
                    "effect": "cast_as_though_flash",
                    "affects_player": "you",
                    "condition": {"exists_derived": {"self_only": True, **power}},
                }
            ],
        }
    )


def selector_probe(spec) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_oe_selector_probe",
            "name": "Parity Selector Probe",
            "mana_cost": "{1}",
            "types": ["Sorcery"],
            "spell_effects": [
                {
                    "op": "return_to_hand",
                    "objects": {"types": ["Creature"], "controller": "any",
                                "count": "all", **spec},
                }
            ],
        }
    )


class TestTheLoader:
    def test_a_parity_condition_loads_on_cast_as_though_flash(self):
        compile_card(probe(power={"parity": "odd"}))

    @pytest.mark.parametrize("bad", ["Even", "zero", 0, True, None])
    def test_a_bad_parity_is_refused_in_a_static(self, bad):
        with pytest.raises(DslError, match="parity"):
            compile_card(probe(power={"parity": bad}))

    def test_parity_beside_a_comparison_is_refused_in_a_static(self):
        with pytest.raises(DslError, match="parity"):
            compile_card(probe(power={"parity": "even", "op": ">=", "value": 2}))

    @pytest.mark.parametrize("key", ["power", "toughness", "mana_value", "base_power"])
    def test_a_selector_takes_it(self, key):
        compile_card(selector_probe({key: {"parity": "even"}}))

    @pytest.mark.parametrize("bad", [{"parity": "prime"}, {"parity": "odd", "value": 1}])
    def test_a_bad_parity_is_refused_in_a_selector(self, bad):
        with pytest.raises(DslError, match="parity"):
            compile_card(selector_probe({"power": bad}))

    def test_a_layered_static_still_refuses_exists_derived(self):
        """The admission is the flash permission's reader, not the parity clause."""
        model = CardModel.model_validate(
            {
                "id": "t_oe_layered_probe",
                "name": "Layered Parity Probe",
                "mana_cost": "{1}",
                "types": ["Creature"],
                "power": 2,
                "toughness": 2,
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Probe.",
                        "effect": "buff",
                        "affects": {"self_only": True},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                        "condition": {"exists_derived": {"self_only": True,
                                                         "power": {"parity": "even"}}},
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="exists_derived"):
            compile_card(model)
