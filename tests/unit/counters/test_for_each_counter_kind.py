"""A loop over the kinds of counter on some permanents or players.

    Bribe Taker -- "When this creature enters, for each kind of counter on
    permanents you control, you may put your choice of a +1/+1 counter or a
    counter of that kind on this creature."

    Skyship Plunderer -- "...for each kind of counter on target permanent or
    player, give that permanent or player another counter of that kind."

    Denry Klin, Editor in Chief -- "...put the same number of each kind of
    counter on that creature."

122.1 lets a permanent carry any number of kinds and a player carry poison
and energy. None of the three names a kind: each walks the kinds actually
there. Without `for_each_counter_kind` the only spellings were one printed
`add_counters` per kind the author thought of -- a Denry that drops the shield
counter it was proliferated onto, a Plunderer that grows +1/+1 counters and
never oil -- or `proliferate`, which chooses any number of recipients rather
than the one targeted.

Each kind present is one iteration (not each counter), bound under `as`; with
`count_as`, the number of that kind among the domain. The domain is read once
before the body runs, so a kind the body puts on is not a further iteration.
The kind is read through the `counter: {"binding": …}` that
`choose_counter_kind` introduced, and on a player through `add_counters`'
`player`. Nothing carrying a counter runs the body zero times (609.3).
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

YOURS = {"zone": "battlefield", "controller": "you"}


def onto(name: str, **extra) -> dict:
    """`add_counters` of the bound kind onto the binding ``name``."""
    return {"op": "add_counters", "counter": {"binding": "kind"}, "objects": {"binding": name}, **extra}


BRIBE = [
    {
        "op": "for_each_counter_kind",
        "objects": YOURS,
        "as": "kind",
        "effects": [
            {
                "op": "may",
                "effects": [
                    {
                        "op": "choose_mode",
                        "modes": [
                            {"effects": [{"op": "add_counters", "counter": "+1/+1", "objects": {"binding": "me"}}]},
                            {"effects": [onto("me")]},
                        ],
                    }
                ],
            }
        ],
    }
]

PLUNDER = [
    {
        "op": "for_each_counter_kind",
        "objects": {"target": "t1"},
        "players": {"target": "t1"},
        "as": "kind",
        "effects": [
            {"op": "add_counters", "counter": {"binding": "kind"}, "objects": {"target": "t1"}},
            {"op": "add_counters", "counter": {"binding": "kind"}, "player": {"target": "t1"}},
        ],
    }
]

DENRY = [
    {
        "op": "for_each_counter_kind",
        "objects": {"binding": "denry"},
        "as": "kind",
        "count_as": "n",
        "effects": [onto("newcomer", amount={"binding": "n"})],
    }
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


def resolve(game, effects, answer=None, *, targets=None, bindings=None):
    """Run ``effects`` for player 0; ``answer(decision)`` picks each option index."""
    ctx = EffectContext(
        state=game.state, controller=0, targets=targets or {}, bindings=dict(bindings or {})
    )
    gen = execute(ctx, effects)
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            decision = gen.send([answer(decision)])
    except StopIteration:
        pass
    return ctx, asked


def counters(game, oid) -> dict[str, int]:
    return {k: n for k, n in game.state.objects[oid].counters.items() if n > 0}


class TestEachKindOnce:
    def test_one_iteration_per_kind_not_per_counter(self, builder):
        """Bear's three +1/+1 and Elf's two shields are two kinds: two placements."""
        game, o = position(builder, bear={"+1/+1": 3}, elf={"shield": 2})
        resolve(game, [{"op": "for_each_counter_kind", "objects": YOURS, "as": "kind",
                        "effects": [onto("big")]}], bindings={"big": [o["big"]]})
        assert counters(game, o["big"]) == {"+1/+1": 1, "shield": 1}

    def test_only_the_domain_is_walked(self, builder):
        """Permanents you control: the opponent's oil counter is not a kind here."""
        game, o = position(builder, bear={"flying": 1}, theirs={"oil": 4})
        resolve(game, [{"op": "for_each_counter_kind", "objects": YOURS, "as": "kind",
                        "effects": [onto("big")]}], bindings={"big": [o["big"]]})
        assert counters(game, o["big"]) == {"flying": 1}

    def test_the_kinds_are_read_before_the_body_runs(self, builder):
        """A kind the body puts on is not a further iteration."""
        game, o = position(builder, bear={"flying": 1})
        body = [onto("big"), {"op": "add_counters", "counter": "shield", "objects": {"binding": "big"}}]
        resolve(game, [{"op": "for_each_counter_kind", "objects": YOURS, "as": "kind",
                        "effects": body}], bindings={"big": [o["big"]]})
        assert counters(game, o["big"]) == {"flying": 1, "shield": 1}

    def test_nothing_carrying_a_counter_runs_nothing(self, builder):
        game, o = position(builder, theirs={"+1/+1": 1})
        _, asked = resolve(game, BRIBE, bindings={"me": [o["big"]]})
        assert asked == []
        assert counters(game, o["big"]) == {}

    def test_the_bindings_are_the_loops_alone(self, builder):
        game, o = position(builder, bear={"flying": 1})
        ctx, _ = resolve(game, DENRY, bindings={"denry": [o["bear"]], "newcomer": [o["big"]],
                                                "n": 7})
        assert "kind" not in ctx.bindings
        assert ctx.bindings["n"] == 7


class TestYourChoiceOfTwo:
    """Bribe Taker: per kind, decline, a +1/+1 counter, or one of that kind."""

    def test_each_kind_asks_its_own_question(self, builder):
        game, o = position(builder, bear={"flying": 1}, elf={"shield": 1})
        answers = iter([0, 1, 0, 0])  # yes, that kind; yes, +1/+1

        def answer(decision):
            return next(answers)

        _, asked = resolve(game, BRIBE, answer, bindings={"me": [o["big"]]})
        assert [d.kind for d in asked] == [
            DecisionKind.MAY, DecisionKind.CHOOSE_MODE, DecisionKind.MAY, DecisionKind.CHOOSE_MODE,
        ]
        assert counters(game, o["big"]) == {"flying": 1, "+1/+1": 1}

    def test_declining_puts_nothing(self, builder):
        game, o = position(builder, bear={"flying": 1}, elf={"shield": 1})
        resolve(game, BRIBE, lambda d: 1, bindings={"me": [o["big"]]})
        assert counters(game, o["big"]) == {}


class TestThatPermanentOrPlayer:
    """Skyship Plunderer: one more of each kind on the one target."""

    def test_a_permanent_gets_one_more_of_each_kind(self, builder):
        game, o = position(builder, theirs={"+1/+1": 3, "flying": 1})
        resolve(game, PLUNDER, targets={"t1": (TargetRef.obj(o["menacer"]),)})
        assert counters(game, o["menacer"]) == {"+1/+1": 4, "flying": 2}
        assert game.state.players[1].poison == 0

    def test_a_player_gets_one_more_of_each_kind(self, builder):
        game, o = position(builder, theirs={"+1/+1": 3})
        game.state.players[1].poison = 2
        game.state.players[1].energy = 1
        resolve(game, PLUNDER, targets={"t1": (TargetRef.player(1),)})
        assert (game.state.players[1].poison, game.state.players[1].energy) == (3, 2)
        assert counters(game, o["menacer"]) == {"+1/+1": 3}

    def test_a_kind_the_player_lacks_is_not_started(self, builder):
        game, _ = position(builder)
        game.state.players[1].poison = 1
        resolve(game, PLUNDER, targets={"t1": (TargetRef.player(1),)})
        assert (game.state.players[1].poison, game.state.players[1].energy) == (2, 0)

    def test_the_other_side_of_the_board_is_untouched(self, builder):
        game, o = position(builder, bear={"shield": 1}, theirs={"oil": 1})
        game.state.players[0].poison = 1
        resolve(game, PLUNDER, targets={"t1": (TargetRef.obj(o["menacer"]),)})
        assert counters(game, o["bear"]) == {"shield": 1}
        assert counters(game, o["menacer"]) == {"oil": 2}
        assert game.state.players[0].poison == 1


class TestTheSameNumber:
    """Denry Klin: as many of each kind as Denry has, and Denry keeps them."""

    def test_each_kind_arrives_in_its_number(self, builder):
        game, o = position(builder, bear={"+1/+1": 2, "first_strike": 1})
        resolve(game, DENRY, bindings={"denry": [o["bear"]], "newcomer": [o["big"]]})
        assert counters(game, o["big"]) == {"+1/+1": 2, "first_strike": 1}
        assert counters(game, o["bear"]) == {"+1/+1": 2, "first_strike": 1}

    def test_the_count_is_the_whole_domains(self, builder):
        game, o = position(builder, bear={"+1/+1": 2}, elf={"+1/+1": 1, "shield": 1})
        resolve(game, [{**DENRY[0], "objects": {**YOURS, "types": ["Creature"]}}],
                bindings={"newcomer": [o["big"]]})
        assert counters(game, o["big"]) == {"+1/+1": 3, "shield": 1}


class TestTheLoader:
    def test_the_printed_shapes_load(self):
        compile_card(CardModel.model_validate(_card(BRIBE, "me")))
        compile_card(CardModel.model_validate(_plunderer()))

    def test_a_domain_is_required(self):
        loop = {**BRIBE[0]}
        loop.pop("objects")
        with pytest.raises(DslError, match="needs 'objects'"):
            compile_card(CardModel.model_validate(_card([loop], "me")))

    def test_as_is_required(self):
        loop = {**BRIBE[0]}
        loop.pop("as")
        with pytest.raises(DslError, match="for_each_counter_kind needs an 'as'"):
            compile_card(CardModel.model_validate(_card([loop], "me")))

    def test_the_placed_counter_name_is_refused(self):
        with pytest.raises(DslError, match="may not be 'counter'"):
            compile_card(CardModel.model_validate(_card([{**BRIBE[0], "as": "counter"}], "me")))

    def test_a_body_is_required(self):
        with pytest.raises(DslError, match="needs 'effects'"):
            compile_card(CardModel.model_validate(_card([{**BRIBE[0], "effects": []}], "me")))

    def test_the_kind_read_after_the_loop_is_refused(self):
        after = {"op": "add_counters", "counter": {"binding": "kind"}, "objects": {"self_only": True}}
        with pytest.raises(DslError, match=r"\['kind'\] is none of them"):
            compile_card(CardModel.model_validate(_card([BRIBE[0], after], "me")))

    def test_count_as_off_the_op_is_refused(self):
        stray = {"op": "draw", "amount": 1, "count_as": "n"}
        with pytest.raises(DslError, match="only means anything on for_each_counter_kind"):
            compile_card(CardModel.model_validate(_card([stray], "me")))

    def test_count_as_may_not_shadow_the_kind(self):
        with pytest.raises(DslError, match="'count_as' is a binding name of its own"):
            compile_card(CardModel.model_validate(_card([{**DENRY[0], "count_as": "kind"}], "me")))

    def test_a_printed_kind_on_a_player_is_refused(self):
        poison = {"op": "add_counters", "counter": "poison", "player": "each_opponent"}
        with pytest.raises(DslError, match="add_counters with 'player' puts a bound kind"):
            compile_card(CardModel.model_validate(_card([poison], "me")))

    def test_objects_beside_a_player_is_refused(self):
        plunder = _plunderer()
        body = plunder["abilities"][0]["effects"][0]["effects"]
        body[1] = {**body[1], "objects": {"target": "t1"}}
        with pytest.raises(DslError, match="not both"):
            compile_card(CardModel.model_validate(plunder))


def _card(effects: list, binding: str) -> dict:
    """A sorcery that binds ``binding`` to itself, then runs ``effects``."""
    return {
        "id": "t_for_each_counter_kind",
        "name": "Test For Each Counter Kind",
        "oracle_text": "For each kind of counter on permanents you control, you may put "
        "your choice of a +1/+1 counter or a counter of that kind on this.",
        "mana_cost": "{2}",
        "types": ["Sorcery"],
        "spell_effects": [
            {"op": "snapshot", "objects": {"self_only": True, "zone": "stack"}, "as": binding},
            *effects,
        ],
    }


def _plunderer() -> dict:
    return {
        "id": "t_plunderer",
        "name": "Test Plunderer",
        "oracle_text": "Whenever this creature deals combat damage to a player, for each kind "
        "of counter on target permanent or player, give that permanent or player another "
        "counter of that kind.",
        "mana_cost": "{1}{U}{U}",
        "types": ["Creature"],
        "power": 2,
        "toughness": 1,
        "abilities": [
            {
                "kind": "triggered",
                "trigger": {"event": "deals_combat_damage_to_player", "source": "self"},
                "targets": [{"id": "t1", "kind": "any", "selector": {}}],
                "effects": [
                    {
                        **PLUNDER[0],
                        "effects": [dict(e) for e in PLUNDER[0]["effects"]],
                    }
                ],
            }
        ],
    }
