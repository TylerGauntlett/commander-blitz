""""Choose three. You may choose the same mode more than once." -- 700.2d.

Rootcast Apprenticeship, and the Confluence cycle before it. The answer is a
**multiset** of exactly three modes, and every chosen *instance* is its own
mode: 601.2b chooses the instances as the spell is cast, 601.2c declares each
one's targets, and three "put two +1/+1 counters on target creature" are three
targets, possibly the same creature, possibly three different ones.

`count` cannot say it (it picks distinct modes), and `budget` -- the other
multiset, Season of Weaving -- is asked on resolution, where a mode can no
longer declare a target. Without `repeatable` the card would be either a
"choose three different" spell, weaker and wrong, or a resolution-time loop
whose bullets point at nothing.

The claims, each a wrong card if it breaks:

* one mode chosen three times declares **three** targets and puts its counters
  where each instance pointed;
* mixed modes run in **printed** order (700.2e), however they were clicked;
* each instance's target is re-checked **on its own** (608.2b): one that left
  skips that instance and nothing else;
* the count is **exact** -- the third question has no "done";
* the shapes that cannot work are refused when the card loads.

The multiset is asked one instance at a time, every mode still on offer after
it is taken, so the action list stays one control per mode (ADR 0015) rather
than one per multiset.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, hand_ids, oids_of, plus_one_counters, settle

SPELL = "t_repeat_modes"
COUNTERS = "Put two +1/+1 counters on target creature."
LIFE = "Target player gains 3 life."
DRAW = "Draw a card."


def position(builder, *, bears: int = 2):
    """The caster with bears to grow, and an opponent holding an instant.

    The instant gives player 1 a real decision, so the spell waits on the stack
    after the cast instead of resolving inside the same ``apply`` -- the window
    a test needs to move a target away in.
    """
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * 2 + ["t_bear"] * bears)
        .hand(0, [SPELL])
        .library(0, ["forest"] * 10)
        .hand(1, ["t_bolt"])
        .battlefield(1, ["mountain"])
        .library(1, ["forest"] * 10)
        .build()
    )


def pick_mode(game, label: str) -> None:
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_MODE, decision
    labels = [o.label for o in decision.options]
    assert label in labels, f"{label!r} not offered; got {labels}"
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and a.choice == labels.index(label)
        )
    )


def pick_target(game, *, oid: int | None = None, player: int | None = None) -> None:
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS, decision
    for index, option in enumerate(decision.options):
        ref = option.ref
        if ref is None:
            continue
        if (oid is not None and ref.kind == "object" and ref.id == oid) or (
            player is not None and ref.kind == "player" and ref.id == player
        ):
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
            return
    raise AssertionError(f"target not offered: oid={oid} player={player}")


def cast(game) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, SPELL))


class TestOneModeThreeTimes:
    def test_three_instances_three_targets_six_counters(self, builder):
        """The same bullet three times, aimed twice at one bear and once at the
        other: six counters in all, split the way the instances pointed."""
        game = position(builder)
        first, second = oids_of(game, "t_bear", 0)
        cast(game)
        for _ in range(3):
            pick_mode(game, COUNTERS)
        pick_target(game, oid=first)
        pick_target(game, oid=second)
        pick_target(game, oid=first)
        item = game.state.stack[-1]
        assert item.modes == (0, 0, 0)
        assert len(item.targets) == 3
        settle(game)
        assert plus_one_counters(game, first) == 4
        assert plus_one_counters(game, second) == 2

    def test_each_instance_is_offered_every_creature(self, builder):
        """601.2c forbids repeating an object within one "target"; three
        instances are three words, so a creature already taken is offered again."""
        game = position(builder, bears=1)
        (bear,) = oids_of(game, "t_bear", 0)
        cast(game)
        for _ in range(3):
            pick_mode(game, COUNTERS)
        # Forced each time -- the one bear is every instance's only choice.
        assert game.state.stack[-1].targets == tuple(game.state.stack[-1].targets[:1]) * 3
        settle(game)
        assert plus_one_counters(game, bear) == 6


class TestPrintedOrder:
    def test_mixed_modes_resolve_in_printed_order(self, builder):
        """Clicked draw, life, counters; recorded and run counters, life, draw
        (700.2e), and the targets declared in that printed order too."""
        game = position(builder)
        first, _ = oids_of(game, "t_bear", 0)
        cast(game)
        for label in (DRAW, LIFE, COUNTERS):
            pick_mode(game, label)
        pick_target(game, oid=first)
        pick_target(game, player=1)
        assert game.state.stack[-1].modes == (0, 1, 2)
        start = len(game.state.events)
        life = [p.life for p in game.state.players]
        hand = len(game.state.players[0].hand)
        settle(game)
        kinds = [
            e.type
            for e in game.state.events[start:]
            if e.type in ("counter_placed", "life_gained", "draw")
        ]
        assert kinds == ["counter_placed", "life_gained", "draw"]
        assert game.state.players[1].life == life[1] + 3
        assert game.state.players[0].life == life[0]
        assert len(game.state.players[0].hand) == hand + 1
        assert plus_one_counters(game, first) == 2

    def test_two_life_instances_pay_two_different_players(self, builder):
        game = position(builder)
        cast(game)
        for label in (LIFE, DRAW, LIFE):
            pick_mode(game, label)
        pick_target(game, player=1)
        pick_target(game, player=0)
        life = [p.life for p in game.state.players]
        settle(game)
        assert [p.life for p in game.state.players] == [life[0] + 3, life[1] + 3]


class TestEachInstanceIsCheckedAlone:
    def test_one_illegal_target_skips_only_its_instance(self, builder):
        """608.2b, per instance: the bear that left takes no counters, and the
        two instances aimed at the other bear still resolve."""
        game = position(builder)
        first, second = oids_of(game, "t_bear", 0)
        cast(game)
        for _ in range(3):
            pick_mode(game, COUNTERS)
        pick_target(game, oid=first)
        pick_target(game, oid=second)
        pick_target(game, oid=second)
        move_object(game.state, first, Zone.EXILE, to_player=0)
        settle(game)
        assert plus_one_counters(game, second) == 4
        assert hand_ids(game) == []

    def test_a_later_instance_s_target_leaving_spares_the_first(self, builder):
        """The renamed second instance is the one that loses its target here,
        so the printed-id instance must not borrow its empty bucket."""
        game = position(builder)
        first, second = oids_of(game, "t_bear", 0)
        cast(game)
        for _ in range(3):
            pick_mode(game, COUNTERS)
        pick_target(game, oid=first)
        pick_target(game, oid=second)
        pick_target(game, oid=first)
        move_object(game.state, second, Zone.EXILE, to_player=0)
        settle(game)
        assert plus_one_counters(game, first) == 4


class TestTheCountIsExact:
    def test_every_question_has_no_done(self, builder):
        """"Choose three" is three: no "Done" on any of the three questions, and
        exactly three are asked."""
        game = position(builder)
        cast(game)
        asked = 0
        while game.pending() is not None and game.pending().kind is DecisionKind.CHOOSE_MODE:
            kinds = {a.kind for a in game.legal_actions()}
            assert ActionKind.FINISH_DECLARATION not in kinds
            assert len([a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]) == 3
            pick_mode(game, DRAW)
            asked += 1
        assert asked == 3
        assert game.state.stack[-1].modes == (2, 2, 2)

    def test_a_mode_with_no_target_is_struck_and_the_rest_fill_the_count(self, builder):
        """601.2b: with no creature anywhere the counters bullet is not offered,
        and one remaining mode may fill every instance."""
        game = position(builder, bears=0)
        cast(game)
        labels = [o.label for o in game.pending().options]
        assert labels == [LIFE, DRAW]
        # Three questions still, though only two modes are on offer.
        for _ in range(3):
            pick_mode(game, DRAW)
        assert game.state.stack[-1].modes == (2, 2, 2)


class TestTheLoaderRefusals:
    def base(self, **over):
        effect = {
            "op": "choose_mode",
            "count": 3,
            "repeatable": True,
            "modes": [
                {
                    "label": "Counters.",
                    "effects": [
                        {
                            "op": "add_counters",
                            "counter": "+1/+1",
                            "amount": {"const": 2},
                            "objects": {"target": "c"},
                        }
                    ],
                },
                {"label": "Draw.", "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}]},
            ],
        }
        effect.update(over.pop("effect", {}))
        card = {
            "id": "x_repeat",
            "name": "X Repeat",
            "oracle_text": "Choose three. You may choose the same mode more than once.",
            "mana_cost": "{G}",
            "types": ["Sorcery"],
            "targets": [
                {"id": "c", "kind": "permanent", "mode": 0, "selector": {"types": ["Creature"]}}
            ],
            "spell_effects": [effect],
        }
        card.update(over)
        return card

    def test_the_base_card_loads(self):
        compile_card(CardModel.model_validate(self.base()))

    @pytest.mark.parametrize(
        "change",
        [
            {"effect": {"repeatable": "yes"}},
            {"effect": {"count": 1}},
            {"effect": {"count": {"x": True}}},
            {"effect": {"budget": 5}},
            {"effect": {"or_more": True, "count": 1}},
            {"effect": {"random": True}},
        ],
    )
    def test_malformed_choose_mode_is_refused(self, change):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(self.base(**change)))

    def test_a_single_mode_is_refused(self):
        card = self.base()
        card["spell_effects"][0]["modes"] = card["spell_effects"][0]["modes"][:1]
        with pytest.raises(DslError, match="repeat"):
            compile_card(CardModel.model_validate(card))

    def test_a_nested_repeatable_is_refused(self):
        card = self.base()
        inner = card["spell_effects"][0]
        card["spell_effects"] = [{"op": "if", "condition": {"exists": {"zone": "battlefield", "types": ["Creature"]}}, "then": [inner]}]
        card["targets"] = []
        inner["modes"][0]["effects"][0]["objects"] = {"zone": "battlefield", "types": ["Creature"]}
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(card))

    def test_repeatable_off_a_spell_is_refused(self):
        card = self.base(
            types=["Creature"],
            power=1,
            toughness=1,
            targets=[],
            spell_effects=[],
            abilities=[
                {
                    "kind": "triggered",
                    "trigger": {"event": "self_enters"},
                    "effects": [
                        {
                            "op": "choose_mode",
                            "count": 2,
                            "repeatable": True,
                            "modes": [
                                {"effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}]},
                                {"effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}]},
                            ],
                        }
                    ],
                }
            ],
        )
        with pytest.raises(DslError, match="repeatable"):
            compile_card(CardModel.model_validate(card))

    def test_a_sizeless_mode_target_is_refused(self):
        card = self.base()
        card["targets"][0]["optional"] = True
        with pytest.raises(DslError, match="fixed size"):
            compile_card(CardModel.model_validate(card))

    def test_a_hash_in_a_target_id_is_refused(self):
        card = self.base()
        card["targets"][0]["id"] = "c#1"
        card["spell_effects"][0]["modes"][0]["effects"][0]["objects"] = {"target": "c#1"}
        with pytest.raises(DslError, match="#"):
            compile_card(CardModel.model_validate(card))
