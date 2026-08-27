"""Rolling dice — rule 705.1, and the first op that produces a *number*.

    "{1}, {T}: Roll X six-sided dice, where X is the number of Bobbleheads you
    control. Create a tapped Treasure token for each even result. If you rolled
    6 exactly seven times, you win the game."  — Luck Bobblehead

One roll, read twice. That is the whole design problem, and it is why `roll_dice`
records its results under an ``as`` name instead of returning a count: the
Treasures and the win condition are two questions about **the same faces**.
Rolling twice — once to count the evens, once to count the sixes — would be a
different and much worse card. On the printed one the sixes are a *subset* of
the evens it just paid out for; on a two-roll version the halves decorrelate,
so a hand that rolled seven 6s would create Treasures off some other roll
entirely and the card would be right only on average.

Nothing already in the engine could stand in. `clash` is the only other
randomness-consuming op and yields a win/lose boolean, never a value; the
`random` selector key picks *objects* and evaluates to a set; `for_each` and
`repeat` iterate over things that already exist. So the missing pieces were an
op that rolls and a value leaf that reads the roll back — `{"rolled": …}`.

Two boundaries are pinned below, both of which a plausible implementation gets
wrong in silence:

- **The binding is faces, not objects.** Every other recording op writes a list
  of oids, and `selectors._bound_oids` reads any bound list as exactly that. A
  bare ``[6, 3, 2]`` would make ``{"objects": {"binding": "roll"}}`` name
  objects 6, 3 and 2 — three real permanents with nothing to do with the roll.
- **Zero dice.** X is a board count, so it is 0 on an empty board. The binding
  still has to be written, or the reads after it answer whatever the *previous*
  resolution left behind.

Determinism is not optional: every face comes from ``state.rng``, the engine's
one seeded source, so a replay of the same seed rolls the same dice.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import resolve_pool
from automtg.engine.effects.values import evaluate_value
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.rng import Rng
from tests.conftest import battlefield_ids, oids_of, pass_until

BOBBLEHEAD = "t_bobblehead"


def table(builder, *, bobbleheads: int = 1, seed: int = 0, lands: int = 4):
    """A board with ``bobbleheads`` Bobbleheads and enough mana to activate one."""
    return (
        builder(players=2, seed=seed)
        .battlefield(0, ["island"] * lands + [BOBBLEHEAD] * bobbleheads)
        .build()
    )


def roll(game, *, count=1, sides=6, name="roll") -> EffectContext:
    """Run the op once against ``game``. Returns the context it wrote into."""
    ctx = EffectContext(state=game.state, controller=0)
    spec = {"op": "roll_dice", "count": count, "sides": sides, "as": name}
    result = OPS["roll_dice"](ctx, spec)
    assert result is None, "roll_dice asks nobody anything, so it is not a generator"
    return ctx


def faces(ctx, name: str = "roll") -> list[int]:
    return list(ctx.bindings[name]["results"])


def rolled(ctx, **predicate) -> int:
    """Evaluate ``{"rolled": {...}}`` against a context that has already rolled."""
    return evaluate_value(ctx, {"rolled": {"binding": "roll", **predicate}})


def with_faces(game, *results: int, sides: int = 6) -> EffectContext:
    """A context holding a roll that came up exactly ``results``.

    The tallies are a pure function of the faces, so the faces are handed over
    rather than fished out of the RNG — which is the only way to assert on a
    roll of "6, 6, 6, 6, 6, 6, 6" without a seed hunt.
    """
    ctx = EffectContext(state=game.state, controller=0)
    ctx.bindings["roll"] = {"results": list(results), "sides": sides}
    return ctx


class TestOneRollReadTwoWays:
    """The claim the whole capability exists for."""

    def test_evens_and_sixes_come_off_the_same_faces(self, builder):
        game = table(builder)
        ctx = with_faces(game, 1, 2, 3, 4, 5, 6, 6)
        assert rolled(ctx, parity="even") == 4, "2, 4, 6 and 6"
        assert rolled(ctx, face=6) == 2
        assert rolled(ctx) == 7, "…and seven dice were thrown"

    def test_the_sixes_are_a_subset_of_the_evens(self, builder):
        """True of one roll, and false half the time of two."""
        game = table(builder, bobbleheads=6)
        ctx = roll(game, count=40)
        assert rolled(ctx, face=6) <= rolled(ctx, parity="even")

    def test_reading_the_roll_does_not_re_roll_it(self, builder):
        game = table(builder)
        ctx = roll(game, count=8)
        before = game.state.rng.getstate()
        first = [rolled(ctx, parity="even"), rolled(ctx, face=6), rolled(ctx)]
        again = [rolled(ctx, parity="even"), rolled(ctx, face=6), rolled(ctx)]
        assert first == again
        assert game.state.rng.getstate() == before, "a read must not draw randomness"

    def test_every_face_is_counted_once(self, builder):
        game = table(builder)
        ctx = roll(game, count=25)
        evens, odds = rolled(ctx, parity="even"), rolled(ctx, parity="odd")
        assert evens + odds == rolled(ctx) == 25

    def test_the_printed_win_condition_is_exact(self, builder):
        """"6 exactly seven times" — not "at least", which eight sixes satisfy."""
        game = table(builder)
        seven = with_faces(game, *([6] * 7))
        eight = with_faces(game, *([6] * 8))
        assert rolled(seven, face=6) == 7
        assert rolled(eight, face=6) == 8, "the leaf reports the count, not a verdict"


class TestTheDice:
    def test_the_count_is_a_value_expression_not_a_literal(self, builder):
        """X is "the number of Bobbleheads you control", so it moves."""
        game = table(builder, bobbleheads=3)
        how_many = {
            "count": {"zone": "battlefield", "controller": "you", "subtypes": ["Bobblehead"]}
        }
        assert len(faces(roll(game, count=how_many))) == 3

    def test_every_face_is_on_the_die(self, builder):
        game = table(builder)
        assert set(faces(roll(game, count=300))) == {1, 2, 3, 4, 5, 6}

    def test_a_different_die_has_different_faces(self, builder):
        game = table(builder)
        assert max(faces(roll(game, count=300, sides=20))) > 6

    def test_the_binding_records_which_die_was_rolled(self, builder):
        game = table(builder)
        assert roll(game, count=1, sides=20).bindings["roll"]["sides"] == 20


class TestZeroDice:
    """"X is the number of Bobbleheads you control" is 0 on an empty board."""

    def test_no_bobbleheads_rolls_nothing(self, builder):
        game = table(builder, bobbleheads=0)
        how_many = {
            "count": {"zone": "battlefield", "controller": "you", "subtypes": ["Bobblehead"]}
        }
        ctx = roll(game, count=how_many)
        assert faces(ctx) == []
        assert rolled(ctx, parity="even") == 0

    def test_the_binding_is_written_even_so(self, builder):
        """Or the reads after it would answer off the previous resolution."""
        game = table(builder)
        ctx = roll(game, count=5)
        stale = faces(ctx)
        assert stale, "the first roll threw something"
        OPS["roll_dice"](ctx, {"op": "roll_dice", "count": 0, "as": "roll"})
        assert faces(ctx) == [], "the empty roll replaced it rather than leaving it"

    def test_no_event_is_logged_for_a_roll_of_nothing(self, builder):
        game = table(builder)
        before = len(game.state.events)
        roll(game, count=0)
        assert len(game.state.events) == before

    def test_a_negative_count_is_no_dice_rather_than_an_error(self, builder):
        game = table(builder)
        assert faces(roll(game, count={"minus": [{"const": 1}, {"const": 4}]})) == []


class TestRerolling:
    def test_a_second_roll_replaces_the_first(self, builder):
        """A binding is a record of *this* roll, not a running tape of all of them."""
        game = table(builder)
        ctx = roll(game, count=5)
        OPS["roll_dice"](ctx, {"op": "roll_dice", "count": 2, "as": "roll"})
        assert len(faces(ctx)) == 2

    def test_two_rolls_can_be_kept_apart_by_name(self, builder):
        game = table(builder)
        ctx = roll(game, count=5, name="first")
        OPS["roll_dice"](ctx, {"op": "roll_dice", "count": 2, "as": "second"})
        assert len(faces(ctx, "first")) == 5
        assert len(faces(ctx, "second")) == 2

    def test_a_binding_nothing_wrote_reads_zero(self, builder):
        game = table(builder)
        ctx = EffectContext(state=game.state, controller=0)
        assert rolled(ctx, parity="even") == 0


class TestTheBindingIsFacesNotObjects:
    """The trap a bare ``list[int]`` of faces would fall into, in silence."""

    def test_the_roll_names_no_objects(self, builder):
        game = table(builder, bobbleheads=2)
        ctx = roll(game, count=6)
        assert resolve_pool(ctx, {"binding": "roll"}) == []

    def test_counting_the_binding_as_objects_is_zero_not_the_faces(self, builder):
        """`{"count": …}` counts objects; a roll puts nothing on any board."""
        game = table(builder)
        ctx = roll(game, count=6)
        assert evaluate_value(ctx, {"count": {"binding": "roll"}}) == 0


class TestDeterminism:
    def test_the_faces_come_from_the_games_rng(self, builder):
        """Not `random`: `tests/unit/test_determinism_hygiene.py` scans for that."""
        game = table(builder)
        game.state.rng = Rng(1234)
        expected = [Rng(1234).randint(1, 6)]
        assert faces(roll(game, count=1)) == expected

    def test_the_same_seed_rolls_the_same_dice(self, builder):
        one = table(builder, seed=7)
        two = table(builder, seed=7)
        assert faces(roll(one, count=30)) == faces(roll(two, count=30))

    def test_a_different_seed_rolls_differently(self, builder):
        one = table(builder, seed=7)
        two = table(builder, seed=8)
        assert faces(roll(one, count=30)) != faces(roll(two, count=30))

    def test_the_rng_advances_once_per_die(self, builder):
        game = table(builder)
        game.state.rng = Rng(3)
        rolled_faces = faces(roll(game, count=4))
        reference = Rng(3)
        assert rolled_faces == [reference.randint(1, 6) for _ in range(4)]


class TestTheEvent:
    def test_it_says_what_was_rolled(self, builder):
        game = table(builder)
        ctx = roll(game, count=4)
        event = game.state.events[-1]
        assert event.type == EventType.DICE_ROLLED
        assert event.data["results"] == faces(ctx)
        assert event.data["sides"] == 6
        assert event.player == 0

    def test_one_event_for_the_whole_roll(self, builder):
        """"Whenever you roll **one or more** dice" — the act, not each die."""
        game = table(builder)
        before = len(game.state.events)
        roll(game, count=9)
        after = [e for e in game.state.events[before:] if e.type == EventType.DICE_ROLLED]
        assert len(after) == 1


DICE_SEED = 7  # Rng(7) rolls 3, 2, 4 on three six-sided dice: two evens, no six.


def activate_a_bobblehead(game, *, seed: int = DICE_SEED) -> list[int]:
    """Activate one Bobblehead, pinning the roll. Returns the faces it threw."""
    oid = oids_of(game, BOBBLEHEAD, 0)[0]
    activation = next(
        a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
    )
    game.state.rng = Rng(seed)
    game.apply(activation)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    event = next(e for e in game.state.events if e.type == EventType.DICE_ROLLED)
    return list(event.data["results"])


class TestThroughARealCard:
    """Luck Bobblehead's ability, both sentences, off one activation."""

    def test_one_die_per_bobblehead(self, builder):
        game = table(builder, bobbleheads=3, lands=6)
        assert activate_a_bobblehead(game) == [3, 2, 4]

    def test_a_treasure_for_each_even_result(self, builder):
        game = table(builder, bobbleheads=3, lands=6)
        results = activate_a_bobblehead(game)
        evens = sum(1 for f in results if f % 2 == 0)
        made = battlefield_ids(game, 0).count("treasure_token")
        assert made == evens == 2, f"a Treasure for each even result of {results}"

    def test_the_treasures_arrive_tapped(self, builder):
        game = table(builder, bobbleheads=3, lands=6)
        activate_a_bobblehead(game)
        treasures = [
            o for o in game.state.battlefield_objects(0) if o.def_id == "treasure_token"
        ]
        assert len(treasures) == 2
        assert all(o.tapped for o in treasures)

    def test_the_second_sentence_reads_the_same_roll(self, builder):
        """No 6 came up, so the "exactly seven times" clause must not fire."""
        game = table(builder, bobbleheads=3, lands=6)
        hand_before = len(game.state.players[0].hand)
        results = activate_a_bobblehead(game)
        assert 6 not in results
        assert len(game.state.players[0].hand) == hand_before, "the if did not fire"


def spell(*effects) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_roll_probe",
            "name": "Roll Probe",
            "mana_cost": "{1}",
            "types": ["Sorcery"],
            "spell_effects": list(effects),
        }
    )


ROLL = {"op": "roll_dice", "count": {"const": 3}, "sides": 6, "as": "roll"}
EVENS = {
    "op": "create_token",
    "token": "treasure_token",
    "tapped": True,
    "amount": {"rolled": {"binding": "roll", "parity": "even"}},
}


def reading(**predicate):
    return {**EVENS, "amount": {"rolled": {"binding": "roll", **predicate}}}


class TestTheLoaderGuards:
    def test_a_roll_and_a_read_load(self):
        compile_card(spell(ROLL, EVENS))

    def test_a_roll_nobody_reads_is_refused(self):
        """A roll is never the effect — it is what the next sentence reads."""
        with pytest.raises(DslError, match="no effect reads"):
            compile_card(spell(ROLL))

    def test_reading_a_roll_that_never_happens_is_refused(self):
        with pytest.raises(DslError, match="never rolls any dice"):
            compile_card(spell(EVENS))

    def test_a_roll_with_no_binding_name_is_refused(self):
        without = {k: v for k, v in ROLL.items() if k != "as"}
        with pytest.raises(DslError, match="needs an 'as'"):
            compile_card(spell(without, EVENS))

    def test_a_die_with_fewer_than_two_sides_is_refused(self):
        with pytest.raises(DslError, match="'sides'"):
            compile_card(spell({**ROLL, "sides": 1}, EVENS))

    def test_the_die_size_may_not_be_a_value_expression(self):
        """No printed card rolls a die whose size it does not name."""
        with pytest.raises(DslError, match="'sides'"):
            compile_card(spell({**ROLL, "sides": {"const": 6}}, EVENS))

    def test_a_read_with_no_binding_is_refused(self):
        with pytest.raises(DslError, match="needs 'binding'"):
            compile_card(spell(ROLL, {**EVENS, "amount": {"rolled": {"face": 6}}}))

    def test_a_misspelled_predicate_is_refused(self):
        """`{"even": true}` would fall through to the count of *dice*."""
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(spell(ROLL, reading(even=True)))

    def test_a_parity_that_is_not_a_parity_is_refused(self):
        with pytest.raises(DslError, match="parity"):
            compile_card(spell(ROLL, reading(parity="prime")))

    def test_two_predicates_over_one_roll_are_refused(self):
        """`face` wins in the evaluator, so the other half would be dropped."""
        with pytest.raises(DslError, match="two predicates"):
            compile_card(spell(ROLL, reading(face=6, parity="even")))

    def test_an_as_on_the_roll_is_allowed_because_it_records(self):
        """`roll_dice` is in RECORDING_OPS, or the generic `as` guard refuses it."""
        from automtg.engine.effects import RECORDING_OPS

        assert "roll_dice" in RECORDING_OPS
