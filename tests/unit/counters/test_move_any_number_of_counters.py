"""Moving **any number of counters**, of any kinds, from one target to another.

    Resourceful Defense -- "{4}{W}: Move any number of counters from target
    permanent you control onto a second target permanent you control."

122.1 lets a permanent carry any number of kinds, and "any number of
counters" lets the controller move any sub-multiset of them: two of three
+1/+1 counters and the shield counter, every counter, or none. `all_kinds`
would force the whole multiset and `any_kind` with an `amount` a fixed number,
both cards other than the printed one. `any_number` asks, on resolution, how
many of each kind on the source move (`ask_x`, 0 up to all of that kind,
harmful kinds first, then the most numerous), and each kind is one placement on the destination. With
either target gone (608.2b) nothing moves.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy
from tests.conftest import activations, only_oid, pass_until

MOVER = "t_resourceful_mover"
BEAR = "t_bear"


def position(builder, *, mine=None, other=None):
    """The mover and a Swamp for {1}; two of our Bears carrying ``mine`` and ``other``.

    The opponent's Bolt and Mountain keep the engine from auto-passing the
    stack away before a test can respond to the activation.
    """
    game = (
        builder(players=2)
        .battlefield(0, [MOVER, "swamp"])
        .battlefield(0, [BEAR], counters=mine or {})
        .battlefield(0, [BEAR], counters=other or {})
        .battlefield(1, ["mountain"])
        .hand(1, ["lightning_bolt"])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )
    game._advance()
    mover = only_oid(game, MOVER, 0)
    bears = sorted(
        oid
        for oid, obj in game.state.objects.items()
        if obj.on_battlefield and game.state.card(oid).id == BEAR
    )
    source = next(o for o in bears if counters(game, o) == dict(mine or {}))
    dest = next(o for o in bears if o != source)
    return game, mover, source, dest


def move_line(game, mover, source, dest):
    return next(
        (a for a in activations(game, mover) if [r.id for r in a.targets] == [source, dest]),
        None,
    )


def to_next_question(game):
    pass_until(
        game,
        lambda g: (
            (d := g.pending()) is not None and d.kind is DecisionKind.CHOOSE_X
        )
        or not g.state.stack,
    )
    decision = game.pending()
    return decision if decision is not None and decision.kind is DecisionKind.CHOOSE_X else None


def activate(game, mover, source, dest):
    game.apply(move_line(game, mover, source, dest))
    return to_next_question(game)


def answer_x(game, x: int):
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
    )
    return to_next_question(game)


def counters(game, oid) -> dict:
    return {k: n for k, n in game.state.objects[oid].counters.items() if n > 0}


class TestAnySubMultiset:
    def test_part_of_one_kind_and_all_of_another(self, builder):
        game, mover, source, dest = position(builder, mine={"+1/+1": 3, "shield": 1})
        decision = activate(game, mover, source, dest)
        assert decision.kind is DecisionKind.CHOOSE_X
        assert "+1/+1" in decision.prompt
        decision = answer_x(game, 2)
        assert "shield" in decision.prompt
        assert answer_x(game, 1) is None
        assert counters(game, source) == {"+1/+1": 1}
        assert counters(game, dest) == {"+1/+1": 2, "shield": 1}

    def test_none_at_all(self, builder):
        game, mover, source, dest = position(builder, mine={"+1/+1": 2, "charge": 1})
        activate(game, mover, source, dest)
        answer_x(game, 0)
        answer_x(game, 0)
        assert counters(game, source) == {"+1/+1": 2, "charge": 1}
        assert counters(game, dest) == {}

    def test_every_counter(self, builder):
        game, mover, source, dest = position(
            builder, mine={"+1/+1": 2, "charge": 3}, other={"+1/+1": 1}
        )
        decision = activate(game, mover, source, dest)
        while decision is not None:
            decision = answer_x(game, max(o.value for o in decision.options))
        assert counters(game, source) == {}
        assert counters(game, dest) == {"+1/+1": 3, "charge": 3}

    def test_the_ceiling_is_what_the_kind_has(self, builder):
        game, mover, source, dest = position(builder, mine={"charge": 2})
        decision = activate(game, mover, source, dest)
        assert [o.value for o in decision.options][-1] == 2

    def test_harmful_kinds_are_asked_first(self, builder):
        game, mover, source, dest = position(builder, mine={"+1/+1": 2, "stun": 1})
        decision = activate(game, mover, source, dest)
        assert "stun" in decision.prompt


class TestTheTargets:
    def test_the_two_targets_differ(self, builder):
        game, mover, source, _ = position(builder, mine={"charge": 1})
        assert move_line(game, mover, source, source) is None

    def test_a_vanished_destination_moves_nothing(self, builder):
        game, mover, source, dest = position(builder, mine={"charge": 1})
        game.apply(move_line(game, mover, source, dest))
        assert game.state.stack
        destroy(game.state, dest)
        pass_until(game, lambda g: not g.state.stack)
        assert counters(game, source) == {"charge": 1}

    def test_nothing_on_the_source_asks_nothing(self, builder):
        game, mover, source, dest = position(builder, mine={}, other={"charge": 1})
        assert activate(game, mover, source, dest) is None
        assert counters(game, dest) == {"charge": 1}


class TestTheLoaderGuardsIt:
    CARD = {
        "id": "t_probe",
        "name": "Probe",
        "oracle_text": "Move any number of counters from target permanent you control onto a second target permanent you control.",
        "types": ["Sorcery"],
        "mana_cost": "{1}",
        "targets": [
            {"id": "from", "kind": "permanent", "count": 1,
             "selector": {"zone": "battlefield", "controller": "you"}},
            {"id": "onto", "kind": "permanent", "count": 1,
             "selector": {"zone": "battlefield", "controller": "you"}},
        ],
        "spell_effects": [
            {"op": "move_counters", "from": {"target": "from"}, "objects": {"target": "onto"},
             "any_kind": True, "any_number": True}
        ],
    }

    def _with(self, op="move_counters", **changes):
        card = copy.deepcopy(self.CARD)
        effect = card["spell_effects"][0]
        effect["op"] = op
        for key, value in changes.items():
            if value is None:
                effect.pop(key, None)
            else:
                effect[key] = value
        return CardModel.model_validate(card)

    def test_the_card_loads(self):
        compile_card(CardModel.model_validate(self.CARD))

    def test_an_amount_beside_it_is_refused(self):
        with pytest.raises(DslError, match="'amount' beside it"):
            compile_card(self._with(amount={"const": 1}))

    def test_it_needs_any_kind(self):
        with pytest.raises(DslError, match="needs 'any_kind'"):
            compile_card(self._with(any_kind=None))

    def test_it_is_true_or_absent(self):
        with pytest.raises(DslError, match="true or absent"):
            compile_card(self._with(any_number=False))

    def test_other_ops_refuse_it(self):
        with pytest.raises(DslError, match="only means anything on move_counters"):
            compile_card(self._with(op="remove_counters", **{"from": None}))
