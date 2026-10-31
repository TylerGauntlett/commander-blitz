""""You may choose two": no modes, or exactly two -- never one.

    Shadrix Silverquill -- "At the beginning of combat on your turn, you may
    choose two. Each mode must target a different player.
    * Target player creates a 2/1 white and black Inkling creature token with flying.
    * Target player draws a card and loses 1 life.
    * Target player puts a +1/+1 counter on each creature they control."

Rule 603.3c chooses a triggered ability's modes as it is put on the stack, and
700.2 lets the card say how many; Shadrix's ruling is that it takes two modes
or none. The modes own their targets, so the answer has to come at that moment
too -- the targets are declared right after it (603.3d, applying 601.2b then
601.2c).

Every near miss is a different card:

* `count: 2` forces two modes every combat, with no way to decline -- and both
  the life loss and the opponent's token are things a player wants to decline;
* `up_to: true` drops the floor to nothing, which also permits choosing exactly
  **one** mode, the half the card forbids;
* a `may` around the `choose_mode` stops it being the single top-level modal
  question, and the loader refuses its mode-owned targets.

So `optional: true` on `choose_mode` asks the printed "may" as a yes-or-no,
then an exact pick. "Each mode must target a different player" needs nothing
of its own: `targeting.enumerate_target_tuples` never lets one ref fill two
specs, and a pair of modes whose targets cannot be declared together is not
offered.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import _choice_actions
from commanderblitz.engine.stack import push_triggered_ability, resolve_top
from commanderblitz.engine.structs import TriggerInstance

QUILL = "t_silverquill"
SPLIT = "t_silverquill_split"  # the draw and counter modes target an opponent
INKLING = "inkling_2_1_wb_flying"
TOKEN = "Target player creates a 2/1 white and black Inkling creature token with flying."
DRAW = "Target player draws a card and loses 1 life."
GROW = "Target player puts a +1/+1 counter on each creature they control."


def board(builder, card: str = QUILL, *, hexproof_opponent: bool = False) -> tuple:
    """The dragon on our side of a two-player table. Returns ``(game, oid)``.

    ``hexproof_opponent`` puts Aegis of the Gods ("You have hexproof") under
    the opponent, leaving us the only player any mode can target.
    """
    theirs = ["aegis_of_the_gods"] if hexproof_opponent else []
    game = (
        builder(players=2)
        .battlefield(0, [card])
        .battlefield(1, [*theirs, "grizzly_bears"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    oid = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == card)
    return game, oid


def push(game, source: int, card: str = QUILL, answers: tuple = (), asked: list | None = None):
    """Put the trigger on the stack, answering each question in turn.

    Driven by hand, as `test_modal_triggered_targets` does, so the stack item
    can be looked at before it resolves. An answer is a label, or a tuple of
    labels for a multi-pick.
    """
    generator = push_triggered_ability(
        game.state, TriggerInstance(source_oid=source, ability_index=0, controller=0, def_id=card)
    )
    remaining = list(answers)
    send = None
    while True:
        try:
            decision = generator.send(send)
        except StopIteration as stop:
            assert not remaining, f"never asked about {remaining}"
            return stop.value
        if asked is not None:
            asked.append(decision)
        labels = [option.label for option in decision.options]
        assert remaining, f"unexpected question: {decision.prompt} {labels}"
        want = remaining.pop(0)
        wants = want if isinstance(want, tuple) else (want,)
        for one in wants:
            assert one in labels, f"{one!r} not offered; got {labels}"
        send = [labels.index(one) for one in wants]


def resolve(game) -> None:
    generator = resolve_top(game.state)
    send = None
    while True:
        try:
            generator.send(send)
        except StopIteration:
            return
        send = [0]


def inklings(game, pid: int) -> int:
    return sum(1 for o in game.state.battlefield_objects(pid) if o.def_id == INKLING)


class TestChoosingNone:
    def test_declining_takes_no_mode_and_declares_no_target(self, builder):
        game, oid = board(builder)
        asked: list = []
        item = push(game, oid, answers=("No",), asked=asked)
        assert [d.kind for d in asked] == [DecisionKind.MAY], "one question, the printed 'may'"
        assert item.modes == ()
        assert item.modes_answered, "or `op_choose_mode` asks again on resolution"
        assert item.targets == ()

    def test_and_resolving_it_does_nothing(self, builder):
        game, oid = board(builder)
        before = [(len(p.hand), p.life) for p in game.state.players]
        push(game, oid, answers=("No",))
        resolve(game)
        assert [(len(p.hand), p.life) for p in game.state.players] == before
        assert inklings(game, 0) == inklings(game, 1) == 0


class TestChoosingExactlyTwo:
    def test_the_pick_is_exactly_two(self, builder):
        game, oid = board(builder)
        asked: list = []
        push(game, oid, answers=("Yes", (TOKEN, DRAW), "P0, P1"), asked=asked)
        pick = asked[1]
        assert pick.kind is DecisionKind.CHOOSE_MODE
        assert (pick.min_count, pick.max_count) == (2, 2)
        assert [o.label for o in pick.options] == [TOKEN, DRAW, GROW]

    def test_each_mode_declares_its_own_player(self, builder):
        game, oid = board(builder)
        item = push(game, oid, answers=("Yes", (TOKEN, DRAW), "P1, P0"))
        assert item.modes == (0, 1)
        assert [ref.id for ref in item.targets] == [1, 0], "printed mode order (700.2e)"

    def test_both_modes_happen_to_their_own_targets(self, builder):
        game, oid = board(builder)
        me, them = game.state.players
        hand, life = len(me.hand), me.life
        push(game, oid, answers=("Yes", (TOKEN, DRAW), "P1, P0"))
        resolve(game)
        assert inklings(game, 1) == 1 and inklings(game, 0) == 0
        assert (len(me.hand), me.life) == (hand + 1, life - 1)
        assert len(them.hand) == 0


class TestChoosingOneIsRefused:
    """The half `up_to` gets wrong: after one pick there is no "Done"."""

    def pick(self, builder):
        game, oid = board(builder)
        generator = push_triggered_ability(
            game.state, TriggerInstance(source_oid=oid, ability_index=0, controller=0, def_id=QUILL)
        )
        assert generator.send(None).kind is DecisionKind.MAY
        return generator.send([0])

    def test_one_mode_cannot_be_finished(self, builder):
        decision = self.pick(builder)
        decision.selected.append(0)
        kinds = [a.kind for a in _choice_actions(decision)]
        assert ActionKind.FINISH_DECLARATION not in kinds
        assert not decision.allow_done

    def test_two_can(self, builder):
        decision = self.pick(builder)
        decision.selected.extend([0, 2])
        assert decision.allow_done and decision.is_complete, "the second pick completes it"


class TestEachModeTargetsADifferentPlayer:
    def test_the_target_pairs_never_repeat_a_player(self, builder):
        game, oid = board(builder)
        asked: list = []
        push(game, oid, answers=("Yes", (DRAW, GROW), "P0, P1"), asked=asked)
        assert sorted(o.label for o in asked[2].options) == ["P0, P1", "P1, P0"]

    def test_with_one_targetable_player_two_cannot_be_chosen(self, builder):
        """Aegis of the Gods leaves only us. Each mode alone has a legal target,
        but no pair does, so the "may" is answered "none" without asking."""
        game, oid = board(builder, hexproof_opponent=True)
        asked: list = []
        item = push(game, oid, asked=asked)
        assert asked == []
        assert item.modes == () and item.modes_answered

    def test_only_the_pairs_that_can_be_declared_are_offered(self, builder):
        """The split twin's draw and counter modes both target an opponent, and
        a two-player table has one: those two together are not a legal pair."""
        game, oid = board(builder, SPLIT)
        asked: list = []
        split_draw = "Target opponent draws a card and loses 1 life."
        split_grow = "Target opponent puts a +1/+1 counter on each creature they control."
        item = push(
            game, oid, SPLIT, answers=("Yes", f"{TOKEN} + {split_grow}"), asked=asked
        )
        assert [o.label for o in asked[1].options] == [
            f"{TOKEN} + {split_draw}",
            f"{TOKEN} + {split_grow}",
        ]
        assert item.modes == (0, 2)
        assert [ref.id for ref in item.targets] == [0, 1]


class TestANestedOneAsksOnResolution:
    """`op_choose_mode`'s own fallback, for a question nothing answered as the
    ability went on the stack. The same two halves: decline, or exactly two."""

    SPEC = {"op": "choose_mode", "count": 2, "optional": True, "modes": [
        {"label": "Draw.", "effects": [{"op": "draw", "amount": {"const": 1}}]},
        {"label": "Gain.", "effects": [{"op": "gain_life", "amount": {"const": 1}}]},
        {"label": "Lose.", "effects": [{"op": "lose_life", "amount": {"const": 1}}]},
    ]}

    def run(self, builder, answers):
        game, oid = board(builder)
        generator = execute(EffectContext(state=game.state, controller=0, source_oid=oid), [self.SPEC])
        asked, send = [], None
        while True:
            try:
                asked.append(generator.send(send))
            except StopIteration:
                return game.state.players[0], asked
            send = answers.pop(0)

    def test_declining(self, builder):
        me, asked = self.run(builder, [[1]])
        assert [d.kind for d in asked] == [DecisionKind.MAY]
        assert (len(me.hand), me.life) == (0, 40)

    def test_exactly_two(self, builder):
        me, asked = self.run(builder, [[0], [0, 2]])
        assert (asked[1].min_count, asked[1].max_count) == (2, 2)
        assert (len(me.hand), me.life) == (1, 39)


class TestTheLoaderRefusals:
    def ability(self, **over):
        mode = {"op": "choose_mode", "count": 2, "optional": True, "modes": [
            {"label": "Draw.", "effects": [{"op": "draw"}]},
            {"label": "Gain.", "effects": [{"op": "gain_life", "amount": {"const": 1}}]},
            {"label": "Lose.", "effects": [{"op": "lose_life", "amount": {"const": 1}}]},
        ]}
        mode.update(over)
        return {
            "kind": "triggered",
            "text": "At the beginning of combat on your turn, you may choose two.",
            "trigger": {"event": "begin_combat", "controller": "you"},
            "effects": [mode],
        }

    def compile(self, **card):
        compile_card(CardModel.model_validate({
            "id": "x_optional_modes", "name": "X Optional Modes", "mana_cost": "{2}",
            "types": ["Artifact"], **card,
        }))

    def test_the_trigger_loads(self):
        self.compile(abilities=[self.ability()])

    @pytest.mark.parametrize("clash", [
        {"up_to": True}, {"or_more": True}, {"random": True}, {"once_each": True},
        {"all_if": {"kicked": True}}, {"chooser": "controller"},
    ])
    def test_a_clause_that_reshapes_the_count(self, clash):
        with pytest.raises(DslError, match="cannot apply"):
            self.compile(abilities=[self.ability(**clash)])

    def test_choose_one_is_up_to(self):
        with pytest.raises(DslError, match="at least 2"):
            self.compile(abilities=[self.ability(count=1)])

    def test_more_than_there_are_modes(self):
        with pytest.raises(DslError, match="can never be chosen"):
            self.compile(abilities=[self.ability(count=4)])

    def test_not_a_boolean(self):
        with pytest.raises(DslError, match="boolean"):
            self.compile(abilities=[self.ability(optional="yes")])

    def test_on_a_spell(self):
        spell = self.ability()["effects"]
        with pytest.raises(DslError, match="spell chooses its modes"):
            self.compile(types=["Sorcery"], spell_effects=spell)

    def test_on_an_activated_ability(self):
        ability = self.ability()
        ability.update(kind="activated", cost={"mana": "{1}"}, trigger=None)
        with pytest.raises(DslError, match="activated ability"):
            self.compile(abilities=[ability])
