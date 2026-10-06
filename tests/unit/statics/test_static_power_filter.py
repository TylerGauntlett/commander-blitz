"""A static ability that asks how big a creature is.

    "During your turn, spells you cast cost {1} less to cast for each creature
     you control with power 4 or greater."      -- Temur Battlecrier

Ferocious, and the whole family behind it: "as long as you control a creature
with power 4 or greater", "creatures with toughness 2 or less get…". Every word
of Temur Battlecrier but the counting filter was already sayable -- a
`spell_cost_reduction` static with `affects_spells`, an `is_your_turn` condition
and a `count` magnitude -- and `power` was not in `STATIC_FILTER_KEYS`, so
`_validate_static_count_filter` refused the card at load time.

**Why the key was excluded, and why that reason is real.** `characteristics`
applies continuous effects in a fixed order with no dependency analysis, and the
one constraint that makes that sound is that a static's filter may not read
another static's *output*. Power is an output: `set_pt` writes it at layer 3 and
every anthem adds to it at layer 4. A filter that read `chars()` would not
merely be imprecise, it would not terminate -- `_matches` is called *from*
`_compute`, and again from `_static_active` before `_compute` has applied a
single layer, so `chars -> _matches -> chars` is an unbounded recursion on the
very first anthem. `TestItDoesNotRecurse` is that claim, run rather than argued:
`t_spf_lord` is an anthem whose own filter reads power.

**The restriction that admits it.** What a static filter reads is
`characteristics._base_pt`: the size the object *starts* the pipeline with --
printed P/T, a copy exception's replacement of it (707.9b), bestow's 0/0, and
the 2/2 shell of a face-down permanent (707.2). Nothing a layer writes is
visible. The fixed order is therefore exactly as acyclic as it was, and
`_compute` opens by calling the same function, so the filter's idea of where a
creature's size begins cannot drift from the pipeline's.

**Why base P/T and not "every input a layer did not write".** Counters and
until-end-of-turn pumps are pipeline inputs like `tapped` or `owner`, and a
filter reading them would have been acyclic too. The stricter line is the one
this module already takes for keywords, and `_compute`'s layer 2b says why: a
static's `keywords` filter does not see a flying counter either, and "making
counters the one visible kind of grant would be the inconsistency". Base P/T is
that same rule pointed at size. `TestWhatTheRestrictionCosts` writes the price
out: an anthem-pumped 3/3 is not a creature with power 4 to a static.

**The two readers outside the pipeline are not restricted, and must not be.**
`triggers.matches_card_filter` has read derived power since Welcoming Vampire
("creatures you control with power 2 or less enter" must see the anthem), and
`cost_reduction._object_matches` already reads derived types and keywords
because pricing happens after every layer has applied. `t_spf_discounter` keeps
that divergence measured rather than asserted: the same JSON filter, counted the
other way, because it is asked somewhere a cycle cannot form.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import _base_pt, chars
from automtg.engine.cost_reduction import cost_reduction
from automtg.engine.errors import DslError
from automtg.engine.objects import PLUS_ONE
from automtg.engine.primitives import add_counters
from tests.conftest import only_oid

CRIER = "t_spf_battlecrier"  # 4/3; spells you cast cost {1} less for each 4-power
LORD = "t_spf_lord"  # creatures you control with power 4 or greater get +1/+1
ANTHEM = "t_spf_anthem"  # 1/1; creatures you control get +1/+1
TOUGH = "t_spf_tough"  # creatures with toughness 2 or less get +1/+0
DISCOUNTER = "t_spf_discounter"  # {9} sorcery, the card-level reduction
BRUTE = "t_spf_brute"  # printed 4/4
RUNT = "t_spf_runt"  # printed 3/3 -- 4 power under an anthem, and not before
BEAR = "t_spf_bear"  # printed 2/2


def board(builder, mine=(), *, active: int = 0, advance: bool = True):
    """A position with ``mine`` on your battlefield.

    ``advance=False`` is what an *opponent's* turn needs: `build()` runs the
    engine's auto-pass, and a seat with nothing to do rolls straight into the
    next turn -- which would be yours, and would quietly undo the one clause
    that test is about.
    """
    return (
        builder(players=2)
        .battlefield(0, list(mine) + ["forest"] * 8)
        .hand(0, [DISCOUNTER])
        .active(active)
        .max_turns(2)
        .build(advance=advance)
    )


def discount(game, card_id: str = BEAR, pid: int = 0) -> int:
    """What ``pid`` pays less for ``card_id`` right now, statics and all.

    Priced against a *vanilla* card by default, so the number is the
    Battlecrier's static alone. `t_spf_discounter` carries a card-level
    reduction of its own -- the other reader -- and `cost_reduction.cost_reduction` adds
    the two, so pricing it here would measure both at once and neither.
    """
    return cost_reduction(game.state, pid, game.state.registry.get(card_id))


def power(game, card_id: str, pid: int = 0) -> int:
    return chars(game.state, only_oid(game, card_id, pid)).power


class TestTheCardItUnblocks:
    """Temur Battlecrier's only printed line, counted on a board."""

    def test_no_creatures_no_discount(self, builder):
        game = board(builder, [CRIER])
        # The Battlecrier is a 4/3, so it satisfies its own filter and the
        # board is never empty while the static is on it. One, not nought.
        assert discount(game) == 1

    def test_one_less_for_each_qualifying_creature(self, builder):
        game = board(builder, [CRIER, BRUTE])
        assert discount(game) == 2, "the Battlecrier itself and the 4/4"

    def test_small_creatures_do_not_count(self, builder):
        game = board(builder, [CRIER, BEAR, RUNT])
        assert discount(game) == 1, (
            "a 2/2 and a 3/3 are not 'a creature with power 4 or greater'; "
            "dropping the power clause would have made this 3"
        )

    def test_it_is_off_on_an_opponents_turn(self, builder):
        """"**During your turn**" -- the clause `_static_active` gates."""
        game = board(builder, [CRIER, BRUTE], active=1, advance=False)
        assert discount(game) == 0

    def test_it_counts_only_your_creatures(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [CRIER] + ["forest"] * 8)
            .battlefield(1, [BRUTE, BRUTE])
            .hand(0, [DISCOUNTER])
            .active(0)
            .max_turns(2)
            .build()
        )
        assert discount(game) == 1, "two 4/4s across the table are not yours"


class TestItDoesNotRecurse:
    """An anthem whose own filter reads power -- the shape that must terminate.

    `t_spf_lord` is "creatures you control with power 4 or greater get +1/+1".
    Reading `chars()` in `_matches` would make computing the lord's own
    characteristics require computing them, so these tests fail by hanging
    rather than by asserting -- which is exactly why they are worth having.
    """

    def test_a_printed_four_power_creature_is_pumped(self, builder):
        game = board(builder, [LORD, BRUTE])
        assert power(game, BRUTE) == 5

    def test_the_pump_does_not_bootstrap_a_second_time(self, builder):
        """A 4/4 becomes a 5/5 and stops.

        The filter reads base power, so the anthem's own output cannot re-enter
        its own filter. Under a derived read this is where a fixed-order
        pipeline would give a different answer depending on how many times it
        happened to be run.
        """
        game = board(builder, [LORD, BRUTE])
        first = power(game, BRUTE)
        game.state.bump_chars()
        assert power(game, BRUTE) == first == 5

    def test_a_three_power_creature_is_untouched(self, builder):
        game = board(builder, [LORD, RUNT])
        assert power(game, RUNT) == 3

    def test_the_lord_does_not_pump_itself_into_range(self, builder):
        game = board(builder, [LORD])
        assert power(game, LORD) == 2


class TestWhatTheRestrictionCosts:
    """The divergence from printed Magic, written out rather than implied."""

    def test_an_anthem_does_not_push_a_runt_into_range(self, builder):
        game = board(builder, [CRIER, ANTHEM, RUNT])
        assert power(game, RUNT) == 4, "the board really is a 4-power creature"
        assert discount(game) == 1, (
            "and a static filter does not see it -- layers-lite reads base P/T, "
            "exactly as a `keywords` filter does not see a granted keyword"
        )

    def test_a_counter_does_not_either(self, builder):
        """+1/+1 counters are the loudest case, and they are refused too.

        A counter is a pipeline *input*, so admitting it would have been
        acyclic. It is refused to keep one rule rather than two: layer 2b
        already refuses a keyword counter to a `keywords` filter.
        """
        game = board(builder, [CRIER, RUNT])
        add_counters(game.state, only_oid(game, RUNT), PLUS_ONE, 1)
        assert power(game, RUNT) == 4
        assert discount(game) == 1

    def test_the_anthem_still_applies_to_the_board(self, builder):
        """The restriction is on what a filter *reads*, not on what anthems do."""
        game = board(builder, [ANTHEM, BRUTE])
        assert power(game, BRUTE) == 5


class TestBasePTIsWhereTheFilterStops:
    """`_base_pt` directly -- the one function both readers share."""

    def test_it_agrees_with_chars_on_a_bare_board(self, builder):
        game = board(builder, [BRUTE])
        obj = game.state.objects[only_oid(game, BRUTE)]
        assert _base_pt(game.state, obj) == (4, 4) == (
            chars(game.state, obj.oid).power,
            chars(game.state, obj.oid).toughness,
        )

    def test_a_face_down_permanent_is_a_two_two(self, builder):
        """707.2, and the reason the shell is in `_base_pt` and not only in
        `_compute`: a filter asking "power 4 or greater" about a manifested card
        must read the shell, or it answers off information no player can see."""
        game = board(builder, [CRIER, BRUTE])
        game.state.objects[only_oid(game, BRUTE)].face_down = True
        game.state.bump_chars()

        assert discount(game) == 1, "the Battlecrier alone; the 4/4 is a 2/2"

    def test_an_anthem_moves_chars_and_not_base(self, builder):
        game = board(builder, [ANTHEM, RUNT])
        obj = game.state.objects[only_oid(game, RUNT)]
        assert _base_pt(game.state, obj) == (3, 3)
        assert chars(game.state, obj.oid).power == 4


class TestTheToughnessTwin:
    def test_it_reads_the_other_number(self, builder):
        game = board(builder, [TOUGH, BEAR, BRUTE])
        assert power(game, BEAR) == 3, "a 2/2 has toughness 2 or less"
        assert power(game, BRUTE) == 4, "a 4/4 does not"

    def test_the_lord_reaches_itself_when_it_qualifies(self, builder):
        """No `exclude_self`, so a 3/3 lord is outside its own filter and a
        2-toughness one would be inside it -- the printed reading either way."""
        game = board(builder, [TOUGH])
        assert power(game, TOUGH) == 3


class TestTheReaderOutsideThePipelineIsNotRestricted:
    """`cost_reduction._object_matches`, which prices a spell after every layer.

    The same filter, and deliberately a different answer: nothing is
    half-computed at payment time, so restricting this reader would throw away
    accuracy to solve a problem it does not have. It is the divergence
    `keywords` already has between these two functions.
    """

    def test_it_counts_a_printed_four_power_creature(self, builder):
        game = board(builder, [BRUTE])
        assert discount(game, DISCOUNTER) == 1

    def test_it_counts_an_anthem_pumped_one_too(self, builder):
        game = board(builder, [ANTHEM, RUNT])
        assert discount(game, DISCOUNTER) == 1, (
            "priced outside the characteristics pipeline, where derived power "
            "is the whole and only truth"
        )

    def test_it_does_not_count_a_bear(self, builder):
        game = board(builder, [BEAR])
        assert discount(game, DISCOUNTER) == 0


class TestTheLoaderRefusesTheNearMisses:
    """A key validated by key set alone needs its *shape* checked too."""

    def _compile(self, spec):
        model = CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "mana_cost": "{1}{G}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Creatures you control with power N get +1/+1.",
                        "effect": "buff",
                        "power": 1,
                        "toughness": 1,
                        "affects": {"controller": "you", "types": ["Creature"], **spec},
                    }
                ],
            }
        )
        return compile_card(model)

    def test_a_bare_integer_is_equality(self):
        self._compile({"power": 4})

    def test_a_comparison_loads(self):
        self._compile({"power": {"op": ">=", "value": 4}})

    def test_a_string_is_refused(self):
        with pytest.raises(DslError, match="power"):
            self._compile({"power": ">=4"})

    def test_a_misspelled_comparison_key_is_refused(self):
        """`{"amount": 4}` would default `value` to 0 and match every creature
        on the board -- wider than printed, and invisible on a board."""
        with pytest.raises(DslError, match="unknown comparison keys"):
            self._compile({"power": {"op": ">=", "amount": 4}})

    def test_an_unknown_operator_is_refused(self):
        with pytest.raises(DslError, match="unknown comparison"):
            self._compile({"power": {"op": "=>", "value": 4}})

    def test_a_value_expression_is_refused(self):
        """A static filter tests one object and has no source to measure an
        expression against, so `{"const": 4}` is a language that is not here."""
        with pytest.raises(DslError, match="plain integer"):
            self._compile({"power": {"op": ">=", "value": {"const": 4}}})

    def test_the_count_filter_is_held_to_the_same_shape(self):
        model = CardModel.model_validate(
            {
                "id": "probe2",
                "name": "Probe Two",
                "mana_cost": "{1}{G}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Creatures you control get +X/+X.",
                        "effect": "buff",
                        "power": {
                            "count": {"types": ["Creature"], "power": {"value": "4"}}
                        },
                        "affects": {"controller": "you", "types": ["Creature"]},
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="plain integer"):
            compile_card(model)
