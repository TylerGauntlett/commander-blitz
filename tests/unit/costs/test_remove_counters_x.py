"""An activated-ability cost of "Remove X <kind> counters from <a permanent>" (107.3, 601.2b).

    Molten Slagheap: "{1}, Remove X storage counters from this land: Add X
    mana in any combination of {B} and/or {R}."

107.3 lets a cost's number be X, and 601.2b (applied to abilities by 602.2b,
and to mana abilities by 605.3a) has the controller announce it as the ability
is activated, before any cost is paid. A cost is paid only by doing all of it
(601.2h), so X can be no more than the counters there are to remove -- and
"from this land" or "from an artifact or creature you control" is **one**
permanent, so counters on two of them are not added together (Moxite
Refinery's ruling). The ability's effects read the same X back: the size of a
storage land's yield, or the mana value Hourglass of the Lost returns.

Without this, `remove_counters` takes only an amount the card fixes and
`remove_counters_from_among` a fixed count split across permanents, so every
storage land's payoff had no spelling. `remove_counters_x` is `tap_x`'s shape
over counters: `costs.cost_x_ceiling` bounds X for `Game._activate`,
`Game._activate_mana` and legality alike, and the mana ability that takes X is
activated by hand, never by the payment solver.

Witness: Molten Slagheap. `t_rcx_slagheap`, `t_rcx_engine`, `t_rcx_hourglass`
and `t_rcx_refinery` are its shapes and its neighbours'.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import can_pay, solver_taps
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, find_action, only_oid, settle

SLAGHEAP = "t_rcx_slagheap"
ENGINE = "t_rcx_engine"
HOURGLASS = "t_rcx_hourglass"
REFINERY = "t_rcx_refinery"
SPLIT = ["B", "R"]


def position(builder, source: str = SLAGHEAP, *, counters=None, extra=(), graveyard=()):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 2 + [source] + list(extra))
        # A land to play keeps the main phase from passing itself: a window
        # holding only mana abilities is auto-passed.
        .hand(0, ["swamp"])
        .graveyard(0, list(graveyard))
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    oid = only_oid(game, source, 0)
    for kind, n in (counters or {}).items():
        game.state.objects[oid].counters[kind] = n
    return game, oid


def choose_x(game, x: int) -> None:
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_X, decision.kind
    game.apply(find_action(game, ActionKind.CHOOSE, choice=x))


def pick(game, oid: int) -> None:
    """Answer an object choice with ``oid``; a forced pick asks nothing."""
    decision = game.pending()
    if decision.kind is not DecisionKind.CHOOSE_OBJECTS:
        return
    for index, option in enumerate(decision.options):
        if option.ref is not None and option.ref.id == oid:
            game.apply(find_action(game, ActionKind.CHOOSE, choice=index))
            break
    if game.pending() is decision:
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def divide(game, colors: str) -> None:
    for color in colors:
        assert game.pending().kind is DecisionKind.CHOOSE_MODE
        game.apply(find_action(game, ActionKind.CHOOSE, choice=SPLIT.index(color)))


def pool(game) -> dict[str, int]:
    return {k: v for k, v in game.state.players[0].mana_pool.to_dict().items() if v}


def counters(game, oid: int) -> dict[str, int]:
    return {k: v for k, v in game.state.objects[oid].counters.items() if v}


class TestAStorageLand:
    def test_the_payoff_is_offered_by_hand_as_one_row(self, builder):
        """Not the solver's -- its cost is not tap-only -- and one row, because
        the yield is asked once X is known."""
        game, land = position(builder, counters={"storage": 3})
        ability = game.state.card(land).abilities[2]
        assert not solver_taps(ability)
        assert [a.mana_option for a in activations(game, land, 2)] == [None]

    def test_x_is_bounded_by_the_storage_counters(self, builder):
        game, land = position(builder, counters={"storage": 3})
        game.apply(activations(game, land, 2)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X
        assert decision.context["max_x"] == 3

    def test_another_kind_of_counter_does_not_raise_the_ceiling(self, builder):
        game, land = position(builder, counters={"storage": 1, "charge": 5})
        game.apply(activations(game, land, 2)[0])
        assert game.pending().context["max_x"] == 1

    @pytest.mark.parametrize(("x", "colors"), [(1, "R"), (3, "BRB")])
    def test_x_counters_come_off_and_x_mana_is_divided(self, builder, x, colors):
        """Parametrised because a constant passes any single case; "BRB" is a
        mix no one colour makes."""
        game, land = position(builder, counters={"storage": 3})
        game.apply(activations(game, land, 2)[0])
        choose_x(game, x)
        # The {1}: the solver may ask nothing (two Swamps, one {1}).
        divide(game, colors)
        assert counters(game, land).get("storage", 0) == 3 - x
        assert pool(game) == {c: colors.count(c) for c in colors}
        assert not game.state.objects[land].tapped
        assert not game.state.stack

    def test_x_can_be_zero(self, builder):
        """107.3: zero is a legal announcement, so the payoff is on offer with
        no counter and makes no mana."""
        game, land = position(builder)
        rows = activations(game, land, 2)
        assert rows
        game.apply(rows[0])
        assert game.pending().kind is not DecisionKind.CHOOSE_X
        assert pool(game) == {}

    def test_the_counter_ability_then_the_payoff(self, builder):
        """The whole card: two turns' worth of storage, spent at once."""
        game, land = position(builder, counters={"storage": 1})
        game.apply(activations(game, land, 1)[0])
        settle(game)
        assert counters(game, land) == {"storage": 2}


class TestAnAbilityOnTheStackReadsX:
    @pytest.mark.parametrize("x", [0, 2])
    def test_the_effect_reads_the_announced_x(self, builder, x):
        game, engine = position(builder, ENGINE, counters={"charge": 2})
        life = game.state.players[0].life
        game.apply(activations(game, engine)[0])
        choose_x(game, x)
        assert counters(game, engine).get("charge", 0) == 2 - x
        settle(game)
        assert game.state.players[0].life == life + x

    def test_it_reads_as_remove_x(self, registry):
        assert registry.get(ENGINE).abilities[0].cost.describe() == (
            "Remove X charge counters from this"
        )

    @pytest.mark.parametrize(
        ("x", "back", "stays"), [(1, "llanowar_elves", "grizzly_bears"), (2, "grizzly_bears", "llanowar_elves")]
    )
    def test_hourglass_returns_the_mana_value_it_announced(self, builder, x, back, stays):
        """The effect's graveyard selector reads X: the card of mana value X
        comes back and the other stays, and the source pays by exiling itself."""
        game, glass = position(
            builder,
            HOURGLASS,
            counters={"time": 3},
            graveyard=["grizzly_bears", "llanowar_elves"],
        )
        game.apply(activations(game, glass)[0])
        choose_x(game, x)
        assert game.state.objects[glass].zone is Zone.EXILE
        settle(game)
        names = {o.def_id for o in game.state.battlefield_objects(0)}
        assert back in names
        assert stays not in names


class TestFromOneChosenPermanent:
    def test_the_ceiling_is_one_permanents_counters_never_a_sum(self, builder):
        game, refinery = position(builder, REFINERY, extra=["grizzly_bears", "grizzly_bears"])
        bears = [o.oid for o in game.state.battlefield_objects(0) if o.def_id == "grizzly_bears"]
        game.state.objects[bears[0]].counters["+1/+1"] = 2
        game.state.objects[bears[1]].counters["+1/+1"] = 1
        game.state.objects[bears[1]].counters["-1/-1"] = 2
        game.apply(activations(game, refinery)[0])
        assert game.pending().context["max_x"] == 3

    def test_all_x_come_off_the_one_picked_in_any_mix(self, builder):
        game, refinery = position(builder, REFINERY, extra=["grizzly_bears", "grizzly_bears"])
        bears = [o.oid for o in game.state.battlefield_objects(0) if o.def_id == "grizzly_bears"]
        game.state.objects[bears[0]].counters["+1/+1"] = 2
        game.state.objects[bears[1]].counters["+1/+1"] = 1
        game.state.objects[bears[1]].counters["-1/-1"] = 2
        life = game.state.players[0].life
        game.apply(activations(game, refinery)[0])
        choose_x(game, 3)
        # Only the second Bear carries three, so the pick is forced; the kinds
        # are asked a counter at a time, harmful first by default.
        while game.pending().kind is DecisionKind.CHOOSE_MODE:
            game.apply(find_action(game, ActionKind.CHOOSE, choice=0))
        assert counters(game, bears[1]) == {}
        assert counters(game, bears[0]) == {"+1/+1": 2}
        settle(game)
        assert game.state.players[0].life == life + 3

    def test_the_payer_picks_which_permanent(self, builder):
        game, refinery = position(builder, REFINERY, extra=["grizzly_bears", "grizzly_bears"])
        bears = [o.oid for o in game.state.battlefield_objects(0) if o.def_id == "grizzly_bears"]
        for bear in bears:
            game.state.objects[bear].counters["+1/+1"] = 2
        game.apply(activations(game, refinery)[0])
        choose_x(game, 2)
        assert game.pending().kind is DecisionKind.CHOOSE_OBJECTS
        pick(game, bears[1])
        assert counters(game, bears[1]) == {}
        assert counters(game, bears[0]) == {"+1/+1": 2}

    def test_an_opponents_permanent_is_not_a_candidate(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["swamp", REFINERY])
            .battlefield(1, ["grizzly_bears"])
            .hand(0, ["swamp"])
            .library(0, ["swamp"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        theirs = only_oid(game, "grizzly_bears", 1)
        game.state.objects[theirs].counters["+1/+1"] = 4
        refinery = only_oid(game, REFINERY, 0)
        # The Refinery is itself an artifact you control, so X = 0 is payable;
        # the opponent's counters raise nothing.
        life = game.state.players[0].life
        game.apply(activations(game, refinery)[0])
        assert game.pending().kind is not DecisionKind.CHOOSE_X
        settle(game)
        assert counters(game, theirs) == {"+1/+1": 4}
        assert game.state.players[0].life == life

    def test_with_no_candidate_the_ability_is_not_offered(self, builder):
        """X = 0 still takes its none from one permanent: a ``from`` pool with
        nothing in it is a cost that can't be paid at all."""
        game = (
            builder(players=2)
            .battlefield(0, ["swamp", "t_rcx_slagheap"])
            .hand(0, ["swamp"])
            .library(0, ["swamp"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        land = only_oid(game, "t_rcx_slagheap", 0)
        cost = game.state.card(land).abilities[2].cost
        narrowed = replace(cost, remove_counters_x={"from": {"types": ["Creature"]}})
        assert not can_pay(game.state, 0, narrowed, land, x=0)
        assert can_pay(game.state, 0, cost, land, x=0)


class TestTheLoaderChecksIt:
    def _card(self, cost: dict, *, mana: bool = False) -> CardModel:
        if mana:
            ability = {
                "kind": "activated",
                "text": "Remove X storage counters from this land: Add X {R}.",
                "is_mana_ability": True,
                "cost": cost,
                "effects": [{"op": "add_mana", "mana": "{R}", "amount": {"x": True}}],
            }
        else:
            ability = {
                "kind": "activated",
                "text": "Remove X charge counters from this artifact: You gain X life.",
                "cost": cost,
                "effects": [{"op": "gain_life", "player": "you", "amount": {"x": True}}],
            }
        return CardModel.model_validate(
            {
                "id": "t_rcx_bad",
                "name": "Test Bad Remove X",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "oracle_text": ability["text"],
                "abilities": [ability],
            }
        )

    def test_the_forms(self):
        compile_card(self._card({"remove_counters_x": {"counter": "charge"}}))
        compile_card(self._card({"remove_counters_x": {"counter": "storage"}}, mana=True))
        compile_card(self._card({"remove_counters_x": {"from": {"types": ["Creature"]}}}))

    def test_the_source_form_names_its_kind(self):
        with pytest.raises(DslError, match="name the 'counter' kind"):
            compile_card(self._card({"remove_counters_x": {}}))

    @pytest.mark.parametrize("key", ["amount", "count"])
    def test_x_is_the_amount(self, key):
        with pytest.raises(DslError, match="takes only"):
            compile_card(self._card({"remove_counters_x": {"counter": "charge", key: 2}}))

    def test_a_malformed_selector_is_refused(self):
        with pytest.raises(DslError, match="remove_counters_x"):
            compile_card(self._card({"remove_counters_x": {"from": {"token": True}}}))

    def test_a_near_miss_keyword_kind_is_refused(self):
        with pytest.raises(DslError):
            compile_card(self._card({"remove_counters_x": {"counter": "Vigilance"}}))

    @pytest.mark.parametrize(
        "second", [{"mana": "{X}"}, {"discard_x": True}, {"tap_x": {"is_token": True}}]
    )
    def test_not_beside_a_second_x(self, second):
        with pytest.raises(DslError, match="second X"):
            compile_card(self._card({"remove_counters_x": {"counter": "charge"}, **second}))
