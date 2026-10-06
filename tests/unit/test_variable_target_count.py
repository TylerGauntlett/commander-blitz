""""Return **up to X** target creature cards from your graveyard to the battlefield."

    Marshal's Anthem, and 601.2c — "the player announces their choice of an
    appropriate object or player for each target the spell requires" — read
    together with 603.3d, which is where that happens for a *triggered* ability:
    "the object's controller… chooses targets for it" as the ability is put on
    the stack.

`TargetModel.count` was `int | "any"`, so the number of targets was either
printed on the card or unbounded, and there was no third thing. Marshal's Anthem
needs the third thing: the number is X, and X is how many times the enchantment
was kicked. Both spellings the schema offered are a different card, and each is
wrong in its own direction — `"any"` unbinds the count from the kicker
altogether, so the {2}{W}{W} cast reanimates the whole graveyard, and a literal
is simply some other card with a number written on it.

Two independent halves, and the card needs both:

**A computed count.** `count` now takes a value expression, evaluated at the
moment the targets are declared. For this card that is `{"additional_paid":
true}`, which reads `obj.cast_additional` off the source — written by
`game._cast` when the kicks were paid and carried onto the battlefield on the
same oid, so the *permanent's* own record is what the trigger reads. That works
here precisely because the targets belong to a triggered ability: they are
declared at 603.3d, after the enchantment has entered. A **spell's** own targets
are declared at 601.2c, while legality is still enumerating cast lines and
before anything has been paid, where there is nothing to read — so the loader
refuses a computed count on a card's own `targets` rather than letting it
quietly evaluate to zero.

**"Up to".** `up_to` makes the count a ceiling: every size from zero through X.
This is the reading none of the existing three could give, and the file keeps all
four apart deliberately, because they overlap in pairs:

* `count: N` — exactly N.
* `count: N, optional: true` — exactly N, or none. `TargetModel.optional`, and
  the same word `selectors.pick_from_pool` spells for an untargeted pool
  (`min_count = 0`, `max_count` still N). Both forbid every size between 1 and
  N-1, which is what makes them *not* "up to".
* `count: "any"` — zero to the whole board, no ceiling at all.
* `count: N-or-a-value, up_to: true` — zero to N. "Up to one" is `optional`
  spelled a second way and is refused; "up to any number" has no ceiling to cap
  and is refused; `optional` alongside `up_to` is two answers to one question and
  is refused.

The witness card is `t_up_to_x` (Marshal's Anthem with the art filed off) and its
exactly-X sibling `t_exactly_x`, which shares the machinery and none of the "up
to" reading.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.carddef import TargetSpec
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.targeting import enumerate_target_tuples, filter_legal
from automtg.engine.zones import move_object
from tests.conftest import pass_until, settle

UP_TO = "t_up_to_x"  # multikicker {1}{W}; ETB returns up to X creature cards
EXACTLY = "t_exactly_x"  # the same card without the "up to"
BEAR = "t_bear"
PLAINS = "plains"

#: The graveyard selector both test cards target with.
GRAVE = {"zone": "graveyard", "controller": "you", "types": ["Creature"]}

CARD = {
    "id": "t_variable_count_probe",
    "name": "Test Variable Count Probe",
    "oracle_text": "Return up to two target creatures to their owners' hands.",
    "mana_cost": "{2}{U}",
    "types": ["Sorcery"],
    "targets": [{"id": "t1", "kind": "permanent", "count": 2, "up_to": True, "selector": {}}],
    "spell_effects": [{"op": "return_to_hand", "objects": {"target": "t1"}}],
}


def board(builder, card: str = UP_TO, *, lands: int = 12, graves: int = 2):
    """The anthem in hand, `graves` creature cards in the graveyard.

    Twelve Plains is four kicks' worth and then some, so what bounds the choice
    in these tests is whatever the test is about rather than the mana.
    """
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands)
        .graveyard(0, [BEAR] * graves)
        .hand(0, [card])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def cast_paying(game, times: int, card: str = UP_TO):
    """Cast the anthem paying its multikicker ``times`` times."""
    line = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card
        and a.additional_times == times
    )
    game.apply(line)


def the_choice(game):
    """Pass until the enters trigger asks who to return, and return the decision."""
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.CHOOSE_OBJECTS,
    )
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS
    return decision


def bounds(game) -> tuple[int, int]:
    """The (fewest, most) targets the trigger asks for.

    A trigger with more than one target asks for them one at a time (see
    `stack._choose_each_target`): every option is ONE card, and the size is
    the decision's min and max rather than a list of subsets to pick from.
    """
    decision = the_choice(game)
    assert all(o.ref is not None for o in decision.options), "an option named a subset"
    return decision.min_count, decision.max_count


def choose(game, how_many: int) -> None:
    """Pick the first ``how_many`` cards offered, then Done if any room is left."""
    decision = the_choice(game)
    for _ in range(how_many):
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
    if game.pending() is decision:
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )


def creatures_back(game) -> int:
    return len([o for o in game.state.battlefield_objects(0) if o.def_id == BEAR])


def in_graveyard(game) -> int:
    return len(game.state.players[0].graveyard)


class TestTheCountIsTheKickerCount:
    """X is read off the permanent, when the trigger declares its targets."""

    def test_no_kicks_returns_nothing(self, builder):
        """The whole point of binding the count: {1}{W} is not a reanimation."""
        game = board(builder)
        cast_paying(game, 0)
        settle(game)
        assert creatures_back(game) == 0
        assert in_graveyard(game) == 2

    def test_one_kick_returns_one(self, builder):
        game = board(builder)
        cast_paying(game, 1)
        settle(game)
        assert creatures_back(game) == 1
        assert in_graveyard(game) == 1

    def test_two_kicks_return_two(self, builder):
        game = board(builder)
        cast_paying(game, 2)
        choose(game, 2)
        settle(game)
        assert creatures_back(game) == 2
        assert in_graveyard(game) == 0

    def test_the_number_survives_the_zone_change(self, builder):
        """`cast_additional` is written to the object being cast and read back
        off the *permanent*: same oid, one zone later, which is the only reason
        an enters trigger can answer "how many times was this kicked"."""
        game = board(builder)
        cast_paying(game, 2)
        settle(game)
        anthem = next(o for o in game.state.battlefield_objects(0) if o.def_id == UP_TO)
        assert anthem.cast_additional == 2


class TestUpToIsZeroThroughX:
    """The reading `optional` and `"any"` between them cannot give."""

    def test_every_size_in_between_is_offered(self, builder):
        """Two kicks, three cards: two, one, or none — and `optional` would
        forbid the middle one."""
        game = board(builder, graves=3)
        cast_paying(game, 2)
        assert bounds(game) == (0, 2)
        assert len(the_choice(game).options) == 3

    def test_the_ceiling_is_the_value_not_the_graveyard(self, builder):
        """One kick with three cards in the yard is one card, not three."""
        game = board(builder, graves=3)
        cast_paying(game, 1)
        # Up to ONE is the single-target list (each card, or none), never a pair.
        assert all("," not in o.label for o in the_choice(game).options)

    def test_the_ceiling_is_the_graveyard_when_that_is_smaller(self, builder):
        """601.2c: choose as many as you can. Three kicks over one card is one."""
        game = board(builder, graves=1)
        cast_paying(game, 3)
        assert bounds(game) == (0, 1)

    def test_declining_is_done_before_any_pick(self, builder):
        """Declining is its own answer -- `Done` with nothing chosen -- rather
        than an empty subset sitting at the end of a list."""
        game = board(builder, graves=2)
        cast_paying(game, 2)
        the_choice(game)
        assert any(a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions())

    def test_declining_needs_no_optional_flag(self, builder):
        """"Up to X" includes zero by its own wording, exactly as "any number"
        does — the spec carries no `optional`."""
        game = board(builder, graves=2)
        cast_paying(game, 2)
        assert bounds(game)[0] == 0

    def test_returning_fewer_than_x_is_a_legal_answer(self, builder):
        game = board(builder, graves=3)
        cast_paying(game, 3)
        decision = the_choice(game)
        one = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE
            and decision.options[a.choice or 0].label.count(",") == 0
            and decision.options[a.choice or 0].label != "no targets"
        )
        game.apply(one)
        settle(game)
        assert creatures_back(game) == 1
        assert in_graveyard(game) == 2

    def test_zero_kicks_asks_nothing_at_all(self, builder):
        """X of zero is not "no legal target" — the trigger resolves, having
        returned nothing, rather than being unable to go on the stack."""
        game = board(builder)
        cast_paying(game, 0)
        settle(game)
        anthem = next(o for o in game.state.battlefield_objects(0) if o.def_id == UP_TO)
        assert anthem.zone is Zone.BATTLEFIELD


class TestAgainstTheNearMisses:
    """The two spellings the schema already had, on the same board."""

    def test_any_would_take_the_whole_graveyard(self, builder):
        """`count: "any"` unbinds the number from the kicker: the unkicked cast
        reanimates everything, which is the card this capability exists to
        avoid printing."""
        game = board(builder, graves=3)
        unbound = TargetSpec(id="t1", kind="card_in_graveyard", selector=GRAVE, count="any")
        assert max(len(t) for t in enumerate_target_tuples(game.state, 0, [unbound], None)) == 3

    def test_up_to_x_is_capped_by_the_kicks(self, builder):
        """The same board and the same selector, bound to a value of one."""
        game = board(builder, graves=3)
        bound = TargetSpec(
            id="t1",
            kind="card_in_graveyard",
            selector=GRAVE,
            count={"const": 1},
            up_to=True,
        )
        offered = enumerate_target_tuples(game.state, 0, [bound], None)
        assert max(len(t) for t in offered) == 1
        assert () in offered

    def test_optional_forbids_the_sizes_in_between(self, builder):
        """`count: 2, optional: true` is "exactly two, or none" — the shape
        `up_to` had to be added beside rather than folded into."""
        game = board(builder, graves=3)
        either_or = TargetSpec(
            id="t1", kind="card_in_graveyard", selector=GRAVE, count=2, optional=True
        )
        offered = enumerate_target_tuples(game.state, 0, [either_or], None)
        assert sorted({len(t) for t in offered}) == [0, 2]


class TestExactlyXWithoutUpTo:
    """A computed count is a count like any other; `up_to` is the modifier."""

    def test_it_forces_the_whole_number(self, builder):
        game = board(builder, card=EXACTLY, graves=3)
        cast_paying(game, 2, card=EXACTLY)
        assert bounds(game) == (2, 2)

    def test_and_offers_no_way_to_decline(self, builder):
        game = board(builder, card=EXACTLY, graves=3)
        cast_paying(game, 2, card=EXACTLY)
        the_choice(game)
        assert not any(a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions())

    def test_zero_still_resolves(self, builder):
        """An exact count of zero asks for no targets, which is a trigger that
        resolves doing nothing — not one that cannot be put on the stack."""
        game = board(builder, card=EXACTLY)
        cast_paying(game, 0, card=EXACTLY)
        settle(game)
        assert creatures_back(game) == 0
        assert next(
            o for o in game.state.battlefield_objects(0) if o.def_id == EXACTLY
        ).zone is Zone.BATTLEFIELD


class TestWhatHappensAfterTheChoice:
    """608.2b re-checks the targets, and `filter_legal` slices the stored refs
    spec by spec to do it. A variable-size spec has no printed length to slice
    by, so it takes whatever is left -- which is the whole reason there may be
    only one of them and it must come last."""

    def spec(self, count: Any = 2, **more: Any) -> TargetSpec:
        return TargetSpec(id="t1", kind="card_in_graveyard", selector=GRAVE, count=count, **more)

    def test_a_target_that_leaves_is_dropped_and_the_rest_survive(self, builder):
        game = board(builder, graves=2)
        spec = self.spec({"const": 2}, up_to=True)
        refs = enumerate_target_tuples(game.state, 0, [spec], None)[0]
        assert len(refs) == 2

        move_object(game.state, refs[0].id, Zone.EXILE, to_player=0)
        buckets, remains = filter_legal(game.state, 0, [spec], refs, None)
        assert remains
        assert [r.id for r in buckets["t1"]] == [refs[1].id]

    def test_all_of_them_leaving_fizzles_the_ability(self, builder):
        """608.2b: an ability whose every target is illegal is removed from the
        stack. The empty bucket has to be told apart from "it never had any"."""
        game = board(builder, graves=2)
        spec = self.spec({"const": 2}, up_to=True)
        refs = enumerate_target_tuples(game.state, 0, [spec], None)[0]
        for ref in refs:
            move_object(game.state, ref.id, Zone.EXILE, to_player=0)
        _, remains = filter_legal(game.state, 0, [spec], refs, None)
        assert not remains

    def test_choosing_none_is_not_a_fizzle(self, builder):
        """"Up to X" with none chosen is an ability with no targets at all, and
        608.2b has nothing to say about it -- it resolves."""
        game = board(builder, graves=2)
        spec = self.spec({"const": 2}, up_to=True)
        _, remains = filter_legal(game.state, 0, [spec], (), None)
        assert remains

    def test_a_fixed_spec_before_it_keeps_its_own_ref(self, builder):
        """The slice is by position: the fixed spec takes its printed number and
        the variable one swallows the rest."""
        game = board(builder, graves=2)
        first = TargetSpec(id="t0", kind="player", selector={}, count=1)
        rest = self.spec({"const": 2}, up_to=True)
        refs = enumerate_target_tuples(game.state, 0, [first, rest], None)[0]
        buckets, _ = filter_legal(game.state, 0, [first, rest], refs, None)
        assert len(buckets["t0"]) == 1 and len(buckets["t1"]) == 2


class TestTheSpellingsStayApart:
    """Every refusal below is a card that would otherwise read as a printing
    that does not exist."""

    def test_up_to_one_is_optional(self):
        card = copy.deepcopy(CARD)
        card["targets"][0]["count"] = 1
        with pytest.raises(DslError, match="'optional': true"):
            compile_card(CardModel.model_validate(card))

    def test_up_to_any_has_no_ceiling(self):
        card = copy.deepcopy(CARD)
        card["targets"][0]["count"] = "any"
        with pytest.raises(DslError, match="no ceiling"):
            compile_card(CardModel.model_validate(card))

    def test_up_to_with_optional_is_two_answers(self):
        card = copy.deepcopy(CARD)
        card["targets"][0]["optional"] = True
        with pytest.raises(DslError, match="same question"):
            compile_card(CardModel.model_validate(card))

    def test_up_to_zero_is_no_target_at_all(self):
        card = copy.deepcopy(CARD)
        card["targets"][0]["count"] = 0
        with pytest.raises(DslError, match="no target at all"):
            compile_card(CardModel.model_validate(card))

    def test_a_literal_up_to_two_is_fine(self):
        """The form is not tied to the value language: "up to two target
        creatures" is the same reading with a printed ceiling."""
        spec = compile_card(CardModel.model_validate(copy.deepcopy(CARD))).targets[0]
        assert spec.count == 2 and spec.up_to and spec.variable_size


class TestWhereTheValueCanBeRead:
    def test_a_spell_may_not_compute_its_own_target_count(self):
        """601.2c happens while legality is enumerating cast lines: X has not
        been chosen and no additional cost has been paid, so the expression
        would read 0 — or, on a second cast, the first cast's number."""
        card = copy.deepcopy(CARD)
        card["targets"][0]["count"] = {"additional_paid": True}
        with pytest.raises(DslError, match="ability's targets"):
            compile_card(CardModel.model_validate(card))

    def test_an_ability_may(self, registry):
        spec = registry.get(UP_TO).abilities[0].targets[0]
        assert spec.count == {"additional_paid": True} and spec.up_to

    def test_the_count_claims_the_multikicker(self, registry):
        """The loader refuses a multikicker no effect reads via
        `additional_paid` — "counting the kicks is what the mana buys". On this
        card the only reader is the *target count*, so `_mentions` had to learn
        to walk target specs or the one card the mechanic exists for would have
        been refused by the mechanic's own guard."""
        assert registry.get(UP_TO).multikicker is not None

    def test_a_computed_count_must_come_last(self):
        card = copy.deepcopy(CARD)
        card["id"] = "t_variable_count_order"
        card["targets"] = [
            {"id": "t1", "kind": "permanent", "count": 2, "up_to": True, "selector": {}},
            {"id": "t2", "kind": "player", "count": 1, "selector": {}},
        ]
        with pytest.raises(DslError, match="must come last"):
            compile_card(CardModel.model_validate(card))

    def test_two_variable_specs_cannot_be_told_apart(self):
        card = copy.deepcopy(CARD)
        card["targets"] = [
            {"id": "t1", "kind": "permanent", "count": 2, "up_to": True, "selector": {}},
            {"id": "t2", "kind": "permanent", "count": "any", "selector": {}},
        ]
        with pytest.raises(DslError, match="only one target"):
            compile_card(CardModel.model_validate(card))
