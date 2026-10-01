""""Any number of target creatures."

    Gallifrey Falls // No More, and every Cryptic Command cousin.

A spec's size was a compile-time constant: `TargetModel.count` was `int = 1`,
and `enumerate_target_tuples` built `combinations(options, spec.count)` — subsets
of *exactly* that size. There was no representation of a caster-chosen size at
any layer.

`count: N, optional: true` is the near-miss and is a different card. `optional`
adds precisely one extra option, the empty tuple, so it means "exactly N, or
none" — it forbids every size between 1 and N-1. And picking a large N and
calling it "any number" is an approximation twice over: it caps a printed
unbounded choice *and* it forbids the sizes in between.

Two ordering decisions, both load-bearing:

**Largest subset first.** Whatever takes a tuple without asking — an AI seat, a
trigger resolving on its own — takes `options[0]`, and "any number" defaulting
to *none* is a spell that resolves having done nothing. This is the same
argument the file already makes for putting the decline option last.

**The empty subset always exists, and comes last.** "Any number" includes zero
whether or not the spec is marked `optional`, so declining is a legal choice
here without the flag.

**At most one `"any"` spec, and it must come last.** `filter_legal` slices the
stored refs spec by spec; a variable-size spec in the middle leaves no way to
say where its refs end and the next spec's begin, so a spell would fizzle or
keep the wrong targets depending on how many the caster chose — a bug no board
would show. Refused at load time rather than left to bite.
"""

from __future__ import annotations

import copy

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import pass_until

SPELL = "t_any_number_bounce"  # "Return any number of target creatures…"
BEAR = "t_bear"

CARD = {
    "id": "t_any_number_probe",
    "name": "Test Any Number Probe",
    "oracle_text": "Return any number of target creatures to their owners' hands.",
    "mana_cost": "{2}{U}",
    "types": ["Sorcery"],
    "targets": [
        {"id": "t1", "kind": "permanent", "count": "any", "selector": {}},
    ],
    "spell_effects": [{"op": "return_to_hand", "objects": {"target": "t1"}}],
}


def board(builder, creatures: int):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 5)
        .battlefield(1, [BEAR] * creatures)
        .hand(0, [SPELL])
        .library(0, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def casts(game) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == SPELL
    ]


class TestEverySizeIsOffered:
    def test_three_creatures_give_every_subset(self, builder):
        """2**3 = 8: every subset of three, the empty one included."""
        game = board(builder, 3)
        assert len(casts(game)) == 8

    def test_including_the_sizes_in_between(self, builder):
        """What `count: 3, optional: true` cannot say."""
        game = board(builder, 3)
        sizes = sorted(len(a.targets) for a in casts(game))
        assert sizes == [0, 1, 1, 1, 2, 2, 2, 3]

    def test_zero_is_legal_without_the_optional_flag(self, builder):
        """"Any number" includes none, whatever the spec says."""
        game = board(builder, 2)
        assert any(len(a.targets) == 0 for a in casts(game))


class TestTheOrder:
    def test_the_whole_board_comes_first(self, builder):
        """Whatever takes a tuple without asking takes the first one, and "any
        number" defaulting to none is a spell that does nothing."""
        game = board(builder, 3)
        assert len(casts(game)[0].targets) == 3

    def test_declining_comes_last(self, builder):
        game = board(builder, 3)
        assert len(casts(game)[-1].targets) == 0


class TestABigBoardIsNotEnumerated:
    """Deepglow Skate: "…on any number of target permanents" -- any controller.

    Every subset of a forty-creature board is 2**40 of them, and the list was
    built in full before being cut to the option limit, so the authoring
    verifier hung on the card. Subsets are now generated lazily and stopped at
    the limit; the order guarantees above must survive that.
    """

    def test_forty_creatures_cap_at_the_option_limit(self, builder):
        from automtg.engine.targeting import MAX_TARGET_OPTIONS

        offered = casts(board(builder, 40))
        assert 0 < len(offered) <= MAX_TARGET_OPTIONS

    def test_the_whole_board_still_comes_first_and_none_last(self, builder):
        offered = casts(board(builder, 40))
        assert len(offered[0].targets) == 40
        assert offered[-1].targets == ()


class TestItActuallyResolves:
    def test_all_three_go_back_to_hand(self, builder):
        game = board(builder, 3)
        game.apply(casts(game)[0])
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)

        assert not [
            o for o in game.state.battlefield_objects(1) if o.def_id == BEAR
        ]
        in_hand = [
            oid
            for oid in game.state.players[1].hand
            if game.state.objects[oid].def_id == BEAR
        ]
        assert len(in_hand) == 3

    def test_one_of_three_leaves_the_others(self, builder):
        game = board(builder, 3)
        one = next(a for a in casts(game) if len(a.targets) == 1)
        game.apply(one)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)

        assert len(
            [o for o in game.state.battlefield_objects(1) if o.def_id == BEAR]
        ) == 2

    def test_choosing_none_leaves_the_board_alone(self, builder):
        game = board(builder, 3)
        none = next(a for a in casts(game) if not a.targets)
        game.apply(none)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)

        assert len(
            [o for o in game.state.battlefield_objects(1) if o.def_id == BEAR]
        ) == 3
        assert game.state.objects[
            next(
                o.oid
                for o in game.state.objects.values()
                if o.def_id == SPELL
            )
        ].zone is Zone.GRAVEYARD, "a spell with no targets still resolves"


class TestLoadTimeGuards:
    def test_two_variable_specs_are_refused(self):
        card = copy.deepcopy(CARD)
        card["targets"] = [
            {"id": "t1", "kind": "permanent", "count": "any", "selector": {}},
            {"id": "t2", "kind": "permanent", "count": "any", "selector": {}},
        ]
        with pytest.raises(DslError, match="only one target"):
            compile_card(CardModel.model_validate(card))

    def test_a_variable_spec_must_come_last(self):
        """`filter_legal` slices the stored refs spec by spec; one of unknown
        size in the middle makes the split unanswerable."""
        card = copy.deepcopy(CARD)
        card["targets"] = [
            {"id": "t1", "kind": "permanent", "count": "any", "selector": {}},
            {"id": "t2", "kind": "player", "count": 1, "selector": {}},
        ]
        with pytest.raises(DslError, match="must come last"):
            compile_card(CardModel.model_validate(card))

    def test_last_is_fine(self):
        card = copy.deepcopy(CARD)
        card["targets"] = [
            {"id": "t1", "kind": "player", "count": 1, "selector": {}},
            {"id": "t2", "kind": "permanent", "count": "any", "selector": {}},
        ]
        assert compile_card(CardModel.model_validate(card)).targets[-1].count == "any"
