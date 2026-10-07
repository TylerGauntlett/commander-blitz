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
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.targeting import enumerate_target_tuples
from tests.conftest import declare_targets, pass_until

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


def tuples(game) -> list:
    """The enumerator's own answer for the spell's spec, undeferred.

    Triggers and activated abilities still take their "any number" targets
    from this list, so its order guarantees are still the ones that matter
    to an AI seat or a trigger resolving on its own.
    """
    oid = next(o.oid for o in game.state.objects.values() if o.def_id == SPELL)
    card = game.state.card(oid)
    return enumerate_target_tuples(game.state, 0, card.targets, oid)


def bears(game) -> list[int]:
    return [o.oid for o in game.state.battlefield_objects(1) if o.def_id == BEAR]


class TestTheCastIsOneLine:
    """A spell's "any number" is declared as the cast happens, not on the line.

    One line per subset was 2**n of them, capped at `MAX_TARGET_OPTIONS`: a
    six-permanent Clever Concealment offered eleven of sixty-three, and the
    set the player wanted was usually not on the list. `casting.
    deferred_target_spec` leaves the spec empty on the line and
    `Game._ask_deferred_targets` asks for it as one decision.
    """

    def test_three_creatures_are_one_cast(self, builder):
        offered = casts(board(builder, 3))
        assert len(offered) == 1
        assert offered[0].targets == ()

    def test_the_cast_asks_for_the_set(self, builder):
        game = board(builder, 3)
        game.apply(casts(game)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.context["purpose"] == "target"
        assert sorted(o.ref.id for o in decision.options) == sorted(bears(game))

    def test_any_size_from_none_to_all(self, builder):
        """What `count: 3, optional: true` cannot say: every size between."""
        game = board(builder, 3)
        game.apply(casts(game)[0])
        decision = game.pending()
        assert (decision.min_count, decision.max_count) == (0, 3)

    def test_a_big_board_offers_every_creature(self, builder):
        """Forty creatures: one line, and all forty in the decision -- not the
        twelve largest subsets the cap used to leave."""
        game = board(builder, 40)
        assert len(casts(game)) == 1
        game.apply(casts(game)[0])
        assert len(game.pending().options) == 40


class TestEverySizeIsOffered:
    """The enumerator, for the callers that still take a tuple from it."""

    def test_three_creatures_give_every_subset(self, builder):
        """2**3 = 8: every subset of three, the empty one included."""
        assert len(tuples(board(builder, 3))) == 8

    def test_including_the_sizes_in_between(self, builder):
        sizes = sorted(len(t) for t in tuples(board(builder, 3)))
        assert sizes == [0, 1, 1, 1, 2, 2, 2, 3]

    def test_zero_is_legal_without_the_optional_flag(self, builder):
        """"Any number" includes none, whatever the spec says."""
        assert any(len(t) == 0 for t in tuples(board(builder, 2)))


class TestTheOrder:
    def test_the_whole_board_comes_first(self, builder):
        """Whatever takes a tuple without asking takes the first one, and "any
        number" defaulting to none is a spell that does nothing."""
        assert len(tuples(board(builder, 3))[0]) == 3

    def test_declining_comes_last(self, builder):
        assert len(tuples(board(builder, 3))[-1]) == 0


class TestABigBoardIsNotEnumerated:
    """Deepglow Skate: "…on any number of target permanents" -- any controller.

    Every subset of a forty-creature board is 2**40 of them, and the list was
    built in full before being cut to the option limit, so the authoring
    verifier hung on the card. Subsets are now generated lazily and stopped at
    the limit; the order guarantees above must survive that.
    """

    def test_forty_creatures_cap_at_the_option_limit(self, builder):
        from automtg.engine.targeting import MAX_TARGET_OPTIONS

        offered = tuples(board(builder, 40))
        assert 0 < len(offered) <= MAX_TARGET_OPTIONS

    def test_the_whole_board_still_comes_first_and_none_last(self, builder):
        offered = tuples(board(builder, 40))
        assert len(offered[0]) == 40
        assert offered[-1] == ()


class TestASingleTargetIsNeverCapped:
    """Generous Gift: "Destroy target permanent." The option limit is for
    combinations; one target is one option per object, and cutting that list
    left every permanent past the twelfth unreachable -- a Sphinx of Uthuun on
    a busy board could not be chosen."""

    def test_every_permanent_is_offered(self, builder):
        from automtg.engine.enums import ActionKind, Step
        from tests.conftest import only_oid

        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 12)
            .battlefield(1, ["sphinx_of_uthuun"])
            .hand(0, ["generous_gift"])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        sphinx = only_oid(game, "sphinx_of_uthuun", 1)
        aims = [
            a.targets[0].id
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.targets
        ]
        assert len(aims) == 13
        assert sphinx in aims


class TestItActuallyResolves:
    def resolve(self, game) -> None:
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)

    def test_all_three_go_back_to_hand(self, builder):
        game = board(builder, 3)
        game.apply(casts(game)[0])
        declare_targets(game, *bears(game))
        self.resolve(game)

        assert not bears(game)
        in_hand = [
            oid
            for oid in game.state.players[1].hand
            if game.state.objects[oid].def_id == BEAR
        ]
        assert len(in_hand) == 3

    def test_one_of_three_leaves_the_others(self, builder):
        game = board(builder, 3)
        game.apply(casts(game)[0])
        declare_targets(game, bears(game)[0])
        self.resolve(game)

        assert len(bears(game)) == 2

    def test_choosing_none_leaves_the_board_alone(self, builder):
        game = board(builder, 3)
        game.apply(casts(game)[0])
        declare_targets(game)
        self.resolve(game)

        assert len(bears(game)) == 3
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
