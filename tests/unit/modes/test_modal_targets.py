"""A target that belongs to one mode -- 601.2b, then 601.2c, in that order.

"Choose up to two. Return those cards from your graveyard to your hand. * Target
artifact card. * Target creature card. * Target enchantment card. * Target land
card." (Call Damage Control.)

Four modes, four *different* targets, and two of them live at once. Nothing in
the engine could say that: `targets` is a flat card-level list fixed as part of
the cast **action**, which legality enumerates before `Game._ask_modes` runs --
the reverse of the printed order. One shared `optional` spec (the Simic Charm
idiom) works only when every mode points at the same object, and four
independent optional specs leave the mode-to-target pairing unenforced, so the
artifact mode could be taken having targeted a creature card.

So a mode-owned spec is declared *inside* the cast, after its mode is chosen.
The claims worth pinning, each of which is a wrong card if it breaks:

* the target a mode gets is **its own** -- the creature bullet returns a
  creature card and cannot be offered a land;
* a mode with no legal target is **not offered** (601.2b), rather than offered
  and then silently doing nothing;
* the refs a cast stored and the specs resolution splits them by are the **same
  list in the same order** -- `targeting.filter_legal` slices by position, so a
  mismatch puts one mode's target in another mode's bucket and the spell
  returns the wrong card while looking completely normal;
* "choose up to two" choosing *none* is an answer, not a question nobody asked
  -- `op_choose_mode` used to ask again on resolution, where the modes it
  offered could no longer declare the targets they own.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.targeting import filter_legal
from automtg.engine.zones import move_object
from tests.conftest import action_for_card

RECALL = "t_modal_recall"
CHOOSE_ONE = "t_modal_one_recall"
BOLT = "t_bolt"  # {R} instant -- gives the opponent a reason to hold priority


def board(builder, graveyard, *, opponent_responds: bool = False):
    """The caster, mana enough, and a graveyard stocked by the test.

    ``opponent_responds`` arms player 1 with an instant. Without a real decision
    of their own the engine auto-passes and the spell resolves inside the same
    ``apply``, which leaves no window to look at the stack in -- the same setup
    `test_copy_spell` uses for the same reason.
    """
    b = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4)
        .hand(0, [RECALL])
        .graveyard(0, graveyard)
        .library(0, ["forest"] * 20)
    )
    if opponent_responds:
        b = b.hand(1, [BOLT]).battlefield(1, ["mountain"])
    return b.build()


def cast(game, card_id=RECALL):
    game.apply(action_for_card(game, ActionKind.CAST, card_id))


def choose(game, *labels):
    """Answer the pending choice by label, then finish if it allows fewer.

    A forced choice is never asked -- `ask_mode` and `ask_targets` both resolve
    a question with one answer without stopping -- so a label the engine did not
    need to ask about is not an error here.
    """
    for label in labels:
        decision = game.pending()
        if decision is None or decision.kind not in _CHOICES:
            return
        options = [o.label for o in decision.options]
        assert label in options, f"{label!r} not offered; got {options}"
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == options.index(label)
            )
        )
    decision = game.pending()
    if decision is not None and decision.kind in _CHOICES:
        finish = [a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION]
        if finish:
            game.apply(finish[0])


_CHOICES = (DecisionKind.CHOOSE_MODE, DecisionKind.CHOOSE_OBJECTS)


def settle(game, limit: int = 60) -> None:
    """Pass priority until the stack is empty, declining everything else."""
    for _ in range(limit):
        if not game.state.stack or game.over:
            return
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        passes = [a for a in actions if a.kind is ActionKind.PASS]
        game.apply(passes[0] if passes else actions[0])
    raise AssertionError("stack never emptied")


def hand_ids(game, pid=0):
    return [game.state.objects[oid].def_id for oid in game.state.players[pid].hand]


def graveyard_ids(game, pid=0):
    return [game.state.objects[oid].def_id for oid in game.state.players[pid].graveyard]


class TestTheOfferedModes:
    def test_only_modes_with_a_legal_target_are_offered(self, builder):
        """601.2b: a mode whose target does not exist cannot be chosen."""
        game = board(builder, ["t_bear", "sol_ring"])
        cast(game)
        offered = [o.label for o in game.pending().options]
        assert offered == ["Target artifact card.", "Target creature card."]

    def test_an_empty_graveyard_chooses_nothing_and_is_not_asked_twice(self, builder):
        """"Up to two" has no floor, so the spell is castable and simply chooses
        nothing -- and having chosen nothing it is not asked again as it
        resolves, which is what `StackItem.modes_answered` is for."""
        game = board(builder, [])
        cast(game)
        settle(game)
        assert graveyard_ids(game) == [RECALL]
        assert hand_ids(game) == []

    def test_choose_one_is_not_castable_with_no_legal_mode(self, builder):
        """A floor of one and nothing to point at is a spell that cannot be cast."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4)
            .hand(0, [CHOOSE_ONE])
            .graveyard(0, ["t_bear"])  # a creature: neither bullet accepts it
            .library(0, ["forest"] * 20)
            .build()
        )
        casts = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == CHOOSE_ONE
        ]
        assert casts == []

    def test_choose_one_is_castable_once_a_mode_has_a_target(self, builder):
        """One legal mode and one legal target: forced all the way through, so
        nothing is asked and the artifact still comes back."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4)
            .hand(0, [CHOOSE_ONE])
            .graveyard(0, ["sol_ring"])
            .library(0, ["forest"] * 20)
            .build()
        )
        cast(game, CHOOSE_ONE)
        settle(game)
        assert hand_ids(game) == ["sol_ring"]


class TestTheTargetBelongsToItsMode:
    def test_one_mode_returns_the_card_of_that_mode_s_type(self, builder):
        game = board(builder, ["t_bear", "sol_ring"])
        cast(game)
        choose(game, "Target creature card.")
        settle(game)
        assert hand_ids(game) == ["t_bear"]
        assert graveyard_ids(game) == ["sol_ring", RECALL]

    def test_two_modes_bind_two_distinct_targets(self, builder):
        """The whole point: two live modes, two different cards, one spell.

        Also the sharpest test of the pairing. If the buckets were crossed, the
        artifact bullet would resolve holding the land's ref, `still_legal`
        would reject it against a ``types: [Artifact]`` selector, and one of
        these two cards would stay in the graveyard.
        """
        game = board(builder, ["t_bear", "sol_ring", "forest"])
        cast(game)
        choose(game, "Target artifact card.", "Target land card.")
        settle(game)
        assert sorted(hand_ids(game)) == ["forest", "sol_ring"]
        assert graveyard_ids(game) == ["t_bear", RECALL]

    def test_a_mode_is_only_offered_cards_of_its_own_type(self, builder):
        """Two creature cards, so the creature bullet has a real question to
        ask -- and an artifact and a land on the same board it must not offer."""
        game = board(builder, ["t_bear", "t_threshold_bear", "sol_ring", "forest"])
        cast(game)
        choose(game, "Target creature card.")
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.context["purpose"] == "target"
        assert sorted(o.label for o in decision.options) == ["Test Bear", "Test Threshold Bear"]

    def test_the_refs_are_stored_in_ascending_mode_order(self, builder):
        """`filter_legal` splits by position, so the cast and the resolution
        have to agree on the order -- which is the mode index, not the order
        the modes were clicked."""
        game = board(builder, ["sol_ring", "forest"], opponent_responds=True)
        cast(game)
        choose(game, "Target land card.", "Target artifact card.")
        item = game.state.stack[-1]
        # Clicked land-then-artifact; recorded in printed order (700.2e).
        assert item.modes == (0, 3)
        assert item.modes_answered
        card = game.state.registry.get(RECALL)
        specs = card.specs_for_modes(item.modes)
        assert [s.id for s in specs] == ["artifact", "land"]
        buckets, remains = filter_legal(game.state, 0, specs, item.targets, item.oid)
        assert remains
        assert [game.state.objects[buckets["artifact"][0].id].def_id] == ["sol_ring"]
        assert [game.state.objects[buckets["land"][0].id].def_id] == ["forest"]


class TestFizzling:
    def test_a_mode_whose_target_left_does_nothing_and_the_other_still_resolves(
        self, builder
    ):
        """608.2b re-checks each target on resolution, per spec. A spell only
        fizzles when *every* target is gone, so the surviving mode still runs."""
        game = board(builder, ["t_bear", "sol_ring"], opponent_responds=True)
        cast(game)
        choose(game, "Target artifact card.", "Target creature card.")
        gone = next(
            oid
            for oid in game.state.players[0].graveyard
            if game.state.objects[oid].def_id == "sol_ring"
        )
        move_object(game.state, gone, Zone.EXILE, to_player=0)
        settle(game)
        assert hand_ids(game) == ["t_bear"]


class TestTheLoaderRefusals:
    """Each one is a card that would otherwise load and read wrong."""

    def base(self, **over):
        card = {
            "id": "x_modal",
            "name": "X Modal",
            "oracle_text": "Choose one.\n* Target creature card.\n* Target land card.",
            "mana_cost": "{G}",
            "types": ["Sorcery"],
            "targets": [
                {
                    "id": "a",
                    "kind": "card_in_graveyard",
                    "mode": 0,
                    "selector": {"zone": "graveyard", "types": ["Creature"]},
                }
            ],
            "spell_effects": [
                {
                    "op": "choose_mode",
                    "modes": [
                        {
                            "label": "Target creature card.",
                            "effects": [
                                {"op": "return_to_hand", "objects": {"target": "a"}}
                            ],
                        },
                        {"label": "Target land card.", "effects": []},
                    ],
                }
            ],
        }
        card.update(over)
        return card

    def compile(self, card):
        compile_card(CardModel.model_validate(card))

    def test_the_shape_it_is_meant_to_allow_still_loads(self):
        self.compile(self.base())

    def test_a_mode_that_does_not_exist(self):
        card = self.base()
        card["targets"][0]["mode"] = 7
        with pytest.raises(DslError, match="mode 7 does not exist"):
            self.compile(card)

    def test_a_mode_owned_target_needs_a_cast_time_choose_mode(self):
        card = self.base(spell_effects=[{"op": "draw", "amount": {"const": 1}}])
        with pytest.raises(DslError, match="top-level 'choose_mode'"):
            self.compile(card)

    def test_a_caster_chosen_size_inside_a_mode(self):
        card = self.base()
        card["targets"][0]["count"] = 2
        card["targets"][0]["up_to"] = True
        with pytest.raises(DslError, match="fixed number"):
            self.compile(card)

    def test_an_optional_mode_owned_target(self):
        card = self.base()
        card["targets"][0]["optional"] = True
        with pytest.raises(DslError, match="cannot be 'optional'"):
            self.compile(card)

    def test_a_variable_card_level_target_beside_a_mode_owned_one(self):
        card = self.base()
        card["targets"].append(
            {
                "id": "b",
                "kind": "card_in_graveyard",
                "count": "any",
                "selector": {"zone": "graveyard", "types": ["Land"]},
            }
        )
        card["spell_effects"][0]["modes"][1]["effects"] = [
            {"op": "return_to_hand", "objects": {"target": "b"}}
        ]
        with pytest.raises(DslError, match="card-level variable-size target"):
            self.compile(card)

    def test_two_targets_sharing_an_id(self):
        card = self.base()
        card["targets"].append(dict(card["targets"][0], mode=1))
        with pytest.raises(DslError, match="share the id"):
            self.compile(card)
