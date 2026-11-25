"""Choosing a kind of counter, and putting one of that kind somewhere else.

    Contractual Safeguard -- "Choose a kind of counter on a creature you
    control. Put a counter of that kind on each other creature you control."

    Aven Courier -- "Whenever this creature attacks, choose a counter on a
    permanent you control. Put a counter of that kind on target permanent you
    control if it doesn't have a counter of that kind on it."

122.1 lets a permanent carry any number of kinds, and neither card names one:
the kind is whatever the controller picks from what is on the board as the
effect resolves. Without `choose_counter_kind` the only spellings were a
printed kind -- a +1/+1-only Safeguard, which is a weaker card on a board of
shield, flying or oil counters -- or a `choose_mode` with one mode per kind,
which cannot be narrowed to the kinds actually present.

The choice is of a counter where it sits: which permanent, then which kind on
it, so `holder_as` can name the permanent "each **other** creature" leaves
out. The kind is bound under `as`; `add_counters` puts it and `counters_on`
counts it through ``counter: {"binding": …}``. Nothing carrying a counter
binds nothing, and an absent kind puts and counts none (609.3).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import only_oid

MINE = {"zone": "battlefield", "controller": "you", "types": ["Creature"]}

SAFEGUARD = [
    {"op": "choose_counter_kind", "from": MINE, "as": "kind", "holder_as": "holder"},
    {
        "op": "add_counters",
        "counter": {"binding": "kind"},
        "objects": {**MINE, "count": "all", "exclude_binding": "holder"},
    },
]

COURIER = [
    {"op": "choose_counter_kind", "from": {"zone": "battlefield", "controller": "you"}, "as": "kind"},
    {
        "op": "if",
        "condition": {
            "cmp": "==",
            "left": {"counters_on": {"counter": {"binding": "kind"}, "objects": {"target": "t1"}}},
            "right": {"const": 0},
        },
        "then": [{"op": "add_counters", "counter": {"binding": "kind"}, "objects": {"target": "t1"}}],
    },
]


def position(builder, *, bear=None, elf=None, theirs=None):
    """Our Bear (with ``bear``), Elf (with ``elf``) and Big; their Menacer (``theirs``)."""
    game = (
        builder(players=2)
        .battlefield(0, ["t_bear"], counters=bear or {})
        .battlefield(0, ["t_elf"], counters=elf or {})
        .battlefield(0, ["t_big"])
        .battlefield(1, ["t_menacer"], counters=theirs or {})
        .library(0, ["island"] * 5)
        .library(1, ["island"] * 5)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    oids = {name: only_oid(game, f"t_{name}") for name in ("bear", "elf", "big", "menacer")}
    return game, oids


def resolve(game, effects, answers=(), targets=None):
    """Run ``effects`` for player 0, answering each question from ``answers``.

    An answer is an oid (for the permanent) or a kind (for the label); the
    questions asked come back so a test can say what was and was not asked.
    """
    ctx = EffectContext(state=game.state, controller=0, targets=targets or {})
    gen = execute(ctx, effects)
    asked = []
    pending = list(answers)
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            answer = pending.pop(0)
            if decision.kind is DecisionKind.CHOOSE_MODE:
                labels = [o.label for o in decision.options]
                index = next(i for i, label in enumerate(labels) if label.startswith(f"{answer} "))
                decision = gen.send([index])
            else:
                values = [o.value for o in decision.options]
                decision = gen.send([values.index(answer)])
    except StopIteration:
        pass
    return ctx, asked


def counters(game, oid) -> dict[str, int]:
    return {k: n for k, n in game.state.objects[oid].counters.items() if n > 0}


class TestTheChoice:
    def test_one_carrier_with_one_kind_asks_nothing(self, builder):
        game, o = position(builder, bear={"flying": 1})
        ctx, asked = resolve(game, SAFEGUARD)
        assert asked == []
        assert ctx.bindings["kind"] == "flying"
        assert ctx.bindings["holder"] == [o["bear"]]

    def test_only_permanents_carrying_a_counter_are_offered(self, builder):
        game, o = position(builder, bear={"+1/+1": 1}, elf={"shield": 1}, theirs={"oil": 2})
        _, asked = resolve(game, SAFEGUARD, [o["elf"]])
        (decision,) = asked
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.player == 0
        assert sorted(opt.value for opt in decision.options) == sorted([o["bear"], o["elf"]])

    def test_the_kind_is_asked_when_the_carrier_holds_two(self, builder):
        game, _ = position(builder, bear={"+1/+1": 2, "-1/-1": 1})
        ctx, asked = resolve(game, SAFEGUARD, ["+1/+1"])
        (decision,) = asked
        assert decision.kind is DecisionKind.CHOOSE_MODE
        labels = [opt.label for opt in decision.options]
        # Copied rather than removed, so the harmful kind is offered last.
        assert labels[0].startswith("+1/+1 ") and labels[-1].startswith("-1/-1 ")
        assert ctx.bindings["kind"] == "+1/+1"

    def test_nothing_carrying_a_counter_binds_nothing(self, builder):
        game, o = position(builder, theirs={"+1/+1": 1})
        ctx, asked = resolve(game, SAFEGUARD)
        assert asked == []
        assert "kind" not in ctx.bindings
        assert all(counters(game, o[name]) == {} for name in ("bear", "elf", "big"))


class TestEachOtherCreature:
    def test_every_other_creature_gets_one_of_the_kind(self, builder):
        game, o = position(builder, bear={"shield": 1})
        resolve(game, SAFEGUARD)
        assert counters(game, o["bear"]) == {"shield": 1}
        assert counters(game, o["elf"]) == {"shield": 1}
        assert counters(game, o["big"]) == {"shield": 1}
        assert counters(game, o["menacer"]) == {}

    def test_the_chosen_carrier_is_the_one_left_out(self, builder):
        """Two creatures carry the kind; the one chosen gets none, the other one more."""
        game, o = position(builder, bear={"+1/+1": 1}, elf={"+1/+1": 1})
        resolve(game, SAFEGUARD, [o["elf"]])
        assert counters(game, o["elf"]) == {"+1/+1": 1}
        assert counters(game, o["bear"]) == {"+1/+1": 2}
        assert counters(game, o["big"]) == {"+1/+1": 1}


class TestIfItDoesNotHaveOne:
    def test_a_permanent_without_the_kind_gets_one(self, builder):
        game, o = position(builder, bear={"flying": 1})
        resolve(game, COURIER, targets={"t1": (TargetRef.obj(o["big"]),)})
        assert counters(game, o["big"]) == {"flying": 1}

    def test_a_permanent_with_the_kind_gets_none(self, builder):
        game, o = position(builder, bear={"flying": 1}, elf={"flying": 1})
        resolve(game, COURIER, [o["bear"]], targets={"t1": (TargetRef.obj(o["elf"]),)})
        assert counters(game, o["elf"]) == {"flying": 1}

    def test_it_reads_the_chosen_kind_not_any_kind(self, builder):
        game, o = position(builder, bear={"flying": 1}, elf={"+1/+1": 1})
        resolve(game, COURIER, [o["bear"]], targets={"t1": (TargetRef.obj(o["elf"]),)})
        assert counters(game, o["elf"]) == {"+1/+1": 1, "flying": 1}

    def test_no_counter_anywhere_puts_none(self, builder):
        game, o = position(builder)
        resolve(game, COURIER, targets={"t1": (TargetRef.obj(o["big"]),)})
        assert counters(game, o["big"]) == {}


class TestTheLoader:
    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))

    def test_as_is_required(self):
        card = _card()
        card["spell_effects"][0].pop("as")
        with pytest.raises(DslError, match="choose_counter_kind needs an 'as'"):
            compile_card(CardModel.model_validate(card))

    def test_from_is_required(self):
        card = _card()
        card["spell_effects"][0].pop("from")
        with pytest.raises(DslError, match="choose_counter_kind needs 'from'"):
            compile_card(CardModel.model_validate(card))

    def test_the_placed_counter_name_is_refused(self):
        card = _card()
        card["spell_effects"][0]["as"] = "counter"
        with pytest.raises(DslError, match="may not be 'counter'"):
            compile_card(CardModel.model_validate(card))

    def test_a_kind_nothing_binds_is_refused(self):
        card = _card()
        card["spell_effects"][1]["counter"] = {"binding": "knid"}
        with pytest.raises(DslError, match=r"\['knid'\] is none of them"):
            compile_card(CardModel.model_validate(card))

    def test_a_bound_kind_on_another_op_is_refused(self):
        card = _card()
        card["spell_effects"][1] = {
            "op": "remove_counters",
            "counter": {"binding": "kind"},
            "objects": {**MINE, "count": "all"},
        }
        with pytest.raises(DslError, match="on 'remove_counters'"):
            compile_card(CardModel.model_validate(card))

    def test_holder_as_off_the_op_is_refused(self):
        card = _card()
        card["spell_effects"][1]["holder_as"] = "holder"
        with pytest.raises(DslError, match="only means anything on choose_counter_kind"):
            compile_card(CardModel.model_validate(card))

    def test_a_bound_kind_in_a_static_count_is_refused(self):
        card = {
            "id": "t_bound_anthem",
            "name": "Test Bound Anthem",
            "oracle_text": "This creature gets +1/+1 for each counter of the chosen kind on it.",
            "mana_cost": "{2}",
            "types": ["Artifact", "Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "static",
                    "effect": "buff",
                    "affects": {"self_only": True},
                    "power": {"counters_on": {"counter": {"binding": "kind"}, "objects": {"self_only": True}}},
                    "toughness": {"const": 0},
                }
            ],
        }
        with pytest.raises(DslError, match="choose_counter_kind bound"):
            compile_card(CardModel.model_validate(card))


def _card() -> dict:
    return {
        "id": "t_choose_counter_kind",
        "name": "Test Choose Counter Kind",
        "oracle_text": "Choose a kind of counter on a creature you control. Put a counter "
        "of that kind on each other creature you control.",
        "mana_cost": "{2}{W}",
        "types": ["Sorcery"],
        "spell_effects": [dict(SAFEGUARD[0]), {**SAFEGUARD[1], "objects": dict(SAFEGUARD[1]["objects"])}],
    }
