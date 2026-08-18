"""``x_in_mana_cost`` — "Counter target spell **with {X} in its mana cost**."

Frontline Medic is the witness, and it is *still* unauthored: its second line
also needs `counter_unless_pays` ("unless its controller pays {3}"), which is a
different capability and a different run. So there is no card in the pool
exercising this key, and this file is the whole of its coverage. Every claim
below is written to be read that way.

**The rules argument.** Rule 107.3 makes the {X} in a mana cost a *mana symbol*.
601.2b has the caster announce a value for it as the spell is cast, and 202.3b
says X counts as 0 for mana value anywhere it is not on the stack — but neither
rule takes the symbol off the card. A Fireball announced for X = 0 is still "a
spell with {X} in its mana cost" and is still a legal target for the Medic.
So the filter reads the **printed cost** (`ManaCost.x_count`) and never
`StackItem.x`, and `TestTheAnnouncedXIsNotTheQuestion` is that decision cashed.

**Why `mana_value` could not stand in**, in either direction. `ManaCost.mana_value`
scores X as 0, so Fireball `{X}{R}` and Shock `{R}` are both mana value 1: one
comparison catches both or neither, which is what
`TestManaValueCannotSeparateThem` plays out on a real stack. And a 202.3b-correct
mana value would not rescue it — a Fireball for X = 0 has Shock's mana value
exactly, while remaining a legal target.

**The plumbing this needed.** A `kind: "spell"` target spec used to ignore its
`selector` outright, in `targeting.candidates` *and* in the 608.2b `still_legal`
re-check. The key would have loaded, validated and done nothing. That also meant
"Counter target **noncreature** spell" was Counterspell —
`TestASpellTargetsSelectorIsConsultedAtAll` pins the repair on Negate and Essence
Scatter, which are shipped cards and were both quietly wrong.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import STATIC_FILTER_KEYS
from automtg.engine.carddef import TargetSpec
from automtg.engine.effects.selectors import SELECTOR_KEYS, validate_selector
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from automtg.engine.targeting import still_legal
from tests.conftest import action_for_card, pass_until

#: "{X}{R}" instant, X damage to any target — the Fireball half of the pair.
FIREBALL = "t_fireball"
#: "{R}" instant, 3 damage — the Shock half. Mana value 1, exactly like Fireball.
BOLT = "t_bolt"
#: "{X}{G}" creature, a second X spell whose X is not red and not an instant.
HYDRA = "t_x_spell"

#: "{U}" instant, "Counter target spell with {X} in its mana cost."
X_COUNTER = "t_x_counter"
#: The negation: "…**without** {X} in its mana cost."
NO_X_COUNTER = "t_no_x_counter"
#: The near miss: "Counter target spell with mana value 1."
MV_COUNTER = "t_mv_counter"

BEAR = "t_bear"


def stack_with(builder, spell: str, *, x: int | None = None, counters=()):
    """P1 puts ``spell`` on the stack; P0 holds ``counters`` and the mana for them.

    Returns the game with **P0 holding priority** and the spell still on the
    stack, which is the one instant every claim here is about: targets are
    chosen as the counter is cast (601.2c), so the whole filter shows up in
    `legal_actions`.

    ``counters`` is never empty, even where the test does not cast one: a player
    holding nothing has no priority action but passing, the engine passes for
    them, and the spell resolves before `apply` returns — which would leave
    every assertion here looking at an empty stack.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * 4)
        .battlefield(1, ["mountain"] * 4 + ["forest"] * 4 + [BEAR])
        .hand(0, list(counters))
        .hand(1, [spell])
        .active(1)
        .build()
    )
    game.apply(action_for_card(game, ActionKind.CAST, spell))
    pending = game.pending()
    if pending is not None and pending.kind is DecisionKind.CHOOSE_X:
        assert x is not None, f"{spell} asked for X and the test did not say"
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == x
            )
        )
    pass_until(game, lambda g: g.state.priority_player == 0 and bool(g.state.stack))
    return game


def targets_offered(game, counter: str) -> list[str]:
    """Which spells on the stack ``counter`` is offered against, by card id."""
    return [
        game.state.card(game.state.stack_item(ref.id).oid).id
        for action in game.legal_actions()
        if action.kind is ActionKind.CAST
        and action.source is not None
        and game.state.objects[action.source].def_id == counter
        for ref in action.targets
        if ref.kind == "stack"
    ]


def cast_counter(game, counter: str) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, counter))


def settle(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


class TestTheKeyReadsThePrintedSymbol:
    def test_a_spell_with_x_in_its_cost_is_a_legal_target(self, builder):
        game = stack_with(builder, FIREBALL, x=2, counters=[X_COUNTER])
        assert targets_offered(game, X_COUNTER) == [FIREBALL]

    def test_a_spell_without_one_is_not(self, builder):
        game = stack_with(builder, BOLT, counters=[X_COUNTER])
        assert targets_offered(game, X_COUNTER) == []

    def test_with_no_legal_target_the_counter_is_not_castable_at_all(self, builder):
        """601.2c: a spell that requires a target it cannot legally choose
        cannot be cast. The counter should vanish from the action list rather
        than appear and fizzle."""
        game = stack_with(builder, BOLT, counters=[X_COUNTER])
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and a.source is not None
            and game.state.objects[a.source].def_id == X_COUNTER
        ]

    def test_it_is_the_cost_and_not_the_card_type(self, builder):
        """`{X}{G}` on a creature spell, so nothing about the match can be
        coming from Fireball being a red instant."""
        game = stack_with(builder, HYDRA, x=1, counters=[X_COUNTER])
        assert targets_offered(game, X_COUNTER) == [HYDRA]

    def test_the_counter_actually_counters_it(self, builder):
        """The claim end to end: the target survives the 608.2b re-check and the
        spell is countered rather than fizzling on resolution."""
        game = stack_with(builder, FIREBALL, x=2, counters=[X_COUNTER])
        cast_counter(game, X_COUNTER)
        settle(game)
        fireball = next(
            o for o in game.state.objects.values() if o.def_id == FIREBALL
        )
        assert fireball.zone is Zone.GRAVEYARD
        assert game.state.objects[
            next(o.oid for o in game.state.battlefield_objects(1) if o.def_id == BEAR)
        ].damage == 0, "countered, so it dealt no damage"


class TestTheNegationIsTheComplement:
    """`false` is a printed clause of its own — "target spell **without** {X}" —
    and it has to be the exact complement, not "some other cost"."""

    def test_it_takes_the_fixed_cost_spell(self, builder):
        game = stack_with(builder, BOLT, counters=[NO_X_COUNTER])
        assert targets_offered(game, NO_X_COUNTER) == [BOLT]

    def test_it_refuses_the_x_spell(self, builder):
        game = stack_with(builder, FIREBALL, x=2, counters=[NO_X_COUNTER])
        assert targets_offered(game, NO_X_COUNTER) == []

    @pytest.mark.parametrize("spell,x", [(FIREBALL, 2), (BOLT, None), (HYDRA, 1)])
    def test_exactly_one_of_the_two_ever_applies(self, builder, spell, x):
        """No spell is caught by both and none is caught by neither."""
        game = stack_with(builder, spell, x=x, counters=[X_COUNTER, NO_X_COUNTER])
        yes = targets_offered(game, X_COUNTER)
        no = targets_offered(game, NO_X_COUNTER)
        assert bool(yes) is not bool(no)


class TestManaValueCannotSeparateThem:
    """The reason this is a new key rather than a `mana_value` comparison."""

    def test_fireball_and_shock_have_the_same_mana_value(self, registry):
        """`{X}{R}` and `{R}`, both 1 — 202.3b scores X as 0. This is the whole
        near miss, stated as data before it is played out."""
        assert registry.get(FIREBALL).mana_value == registry.get(BOLT).mana_value == 1

    def test_and_they_differ_on_the_new_key(self, registry):
        assert registry.get(FIREBALL).mana_cost.x_count == 1
        assert registry.get(BOLT).mana_cost.x_count == 0

    @pytest.mark.parametrize("spell,x", [(FIREBALL, 2), (BOLT, None)])
    def test_a_mana_value_clause_catches_both(self, builder, spell, x):
        """`{"mana_value": 1}` is the closest thing the DSL had, and it is a
        strictly different card: it counters Shock too."""
        game = stack_with(builder, spell, x=x, counters=[MV_COUNTER])
        assert targets_offered(game, MV_COUNTER) == [spell]

    def test_the_new_key_catches_only_one(self, builder):
        with_x = stack_with(builder, FIREBALL, x=2, counters=[X_COUNTER])
        without = stack_with(builder, BOLT, counters=[X_COUNTER])
        assert targets_offered(with_x, X_COUNTER) == [FIREBALL]
        assert targets_offered(without, X_COUNTER) == []


class TestTheAnnouncedXIsNotTheQuestion:
    """The boundary, and the design decision this file exists to record.

    601.2b has X announced as the spell is cast; 107.3 leaves the *symbol* on
    the card either way. "With {X} in its mana cost" asks about the symbol, so
    the answer must not move when the number does — and X = 0 is where the two
    readings visibly disagree.
    """

    @pytest.mark.parametrize("x", [0, 1, 3])
    def test_the_answer_does_not_depend_on_the_value_chosen(self, builder, x):
        game = stack_with(builder, FIREBALL, x=x, counters=[X_COUNTER])
        assert targets_offered(game, X_COUNTER) == [FIREBALL]

    def test_x_announced_as_zero_still_has_x_in_its_mana_cost(self, builder):
        """The case that decides it. Reading `StackItem.x` instead of the
        printed cost would let a Fireball-for-0 walk past the Medic."""
        game = stack_with(builder, FIREBALL, x=0, counters=[X_COUNTER])
        assert game.state.stack[-1].x == 0, "the announced value really is 0"
        assert targets_offered(game, X_COUNTER) == [FIREBALL]

    def test_and_the_negation_still_refuses_it(self, builder):
        """The same boundary from the other side: a Fireball for 0 is not a
        spell *without* {X} in its mana cost either."""
        game = stack_with(builder, FIREBALL, x=0, counters=[NO_X_COUNTER])
        assert targets_offered(game, NO_X_COUNTER) == []

    def test_an_x_of_zero_is_indistinguishable_by_mana_value(self, builder):
        """Why a 202.3b-correct mana value on the stack would not have been a
        cheaper answer: at X = 0 the Fireball's mana value is Shock's."""
        game = stack_with(builder, FIREBALL, x=0, counters=[MV_COUNTER])
        assert targets_offered(game, MV_COUNTER) == [FIREBALL]


class TestASpellTargetsSelectorIsConsultedAtAll:
    """The plumbing, on two shipped cards that were quietly wrong without it.

    `targeting.candidates` returned every spell on the stack for a
    `kind: "spell"` spec and never looked at `spec.selector`, so Negate could
    counter a creature spell and Essence Scatter could counter anything.
    """

    def test_negate_cannot_target_a_creature_spell(self, builder):
        game = stack_with(builder, BEAR, counters=["negate"])
        assert targets_offered(game, "negate") == []

    def test_negate_can_target_a_noncreature_spell(self, builder):
        game = stack_with(builder, BOLT, counters=["negate"])
        assert targets_offered(game, "negate") == [BOLT]

    def test_essence_scatter_is_the_mirror(self, builder):
        creature = stack_with(builder, BEAR, counters=["essence_scatter"])
        instant = stack_with(builder, BOLT, counters=["essence_scatter"])
        assert targets_offered(creature, "essence_scatter") == [BEAR]
        assert targets_offered(instant, "essence_scatter") == []

    def test_an_empty_selector_still_takes_everything(self, builder):
        """The regression guard on the change itself: "Counter target spell"
        must not have acquired a filter, and a stack-zone default is what keeps
        it — `matches` defaults to the battlefield, which would match nothing."""
        game = stack_with(builder, BEAR, counters=["t_counterspell"])
        assert targets_offered(game, "t_counterspell") == [BEAR]

    def test_the_re_check_on_resolution_asks_the_same_question(self, builder):
        """608.2b. `still_legal` used to answer `is_spell` and nothing else, so
        a filter that held when the counter was cast stopped holding when it
        resolved."""
        game = stack_with(builder, FIREBALL, x=1, counters=[X_COUNTER])
        ref = TargetRef.stack(game.state.stack[-1].sid)
        yes = TargetSpec(id="t1", kind="spell", selector={"x_in_mana_cost": True})
        no = TargetSpec(id="t1", kind="spell", selector={"x_in_mana_cost": False})
        assert still_legal(game.state, 0, yes, ref, None)
        assert not still_legal(game.state, 0, no, ref, None)

    def test_a_target_that_left_the_stack_is_no_longer_legal(self, builder):
        """The wearing-off. A spell that has resolved is not a spell any more,
        and the selector branch must not resurrect it."""
        game = stack_with(builder, FIREBALL, x=1, counters=[X_COUNTER])
        ref = TargetRef.stack(game.state.stack[-1].sid)
        spec = TargetSpec(id="t1", kind="spell", selector={"x_in_mana_cost": True})
        settle(game)
        assert not still_legal(game.state, 0, spec, ref, None)


class TestTheLoaderRefusesTheWrongSpelling:
    """It sits beside `mana_value`, which *is* a comparison, so the natural
    mistake is to write one — and every non-bool passes silently through
    `bool()`."""

    def test_a_comparison_spec_is_a_load_error(self):
        with pytest.raises(DslError, match="true or false"):
            validate_selector({"x_in_mana_cost": {"op": ">=", "value": 1}}, "probe")

    def test_an_integer_is_a_load_error(self):
        """`1` would work by accident and `0` would silently mean `false`."""
        with pytest.raises(DslError, match="true or false"):
            validate_selector({"x_in_mana_cost": 1}, "probe")

    @pytest.mark.parametrize("value", [True, False])
    def test_both_booleans_load(self, value):
        validate_selector({"x_in_mana_cost": value}, "probe")

    def test_it_is_a_known_key(self):
        assert "x_in_mana_cost" in SELECTOR_KEYS


class TestItIsNotStaticVocabulary:
    def test_no_static_filter_may_ask_it(self):
        """Deliberate, and the same call `attacked_this_turn` got. A static
        filter matches **permanents**, where 202.3b makes X 0 and the question
        is nearly always about a spell instead; every printed line that reads
        {X} out of a cost — Frontline Medic, Ertai's Meddling — points at the
        stack. `mana_value` is not in this set either, so no static in the
        engine reads a cost at all. Vocabulary with no card asking for it is
        vocabulary that invites a card to be written wrongly."""
        assert "x_in_mana_cost" not in STATIC_FILTER_KEYS
