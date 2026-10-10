""""…get +1/+1 **for each charge counter on this artifact**" -- an anthem with a size.

    Door of Destinies -- "As this artifact enters, choose a creature type.
    Whenever you cast a spell of the chosen type, put a charge counter on this
    artifact. Creatures you control of the chosen type get +1/+1 for each charge
    counter on this artifact."

Rule 613.4 / 611.2c: a continuous effect from a static ability applies to
whatever objects match it at the moment characteristics are computed, and its
magnitude is read then too -- so a creature cast on turn nine is sized by the
counters that landed on turns four through eight, and every creature already on
the battlefield grows the instant a ninth counter arrives.

That is why this cannot be an op. `pump` wears off at end of turn, and
`add_counters` putting +1/+1 counters onto the creatures themselves is a
different card twice over: the creatures already out would not grow when a later
charge counter landed, and creatures cast afterwards would arrive unsized.

The static value language is deliberately narrower than the effect-side one --
it may read pipeline **inputs** only, or a static could come to depend on
another static's output and the fixed order of "layers-lite" would stop being
acyclic. A counter is an input: primitives place and remove them and no layer
can, which the `counters` *condition* head has relied on since Arixmethes. But
that head is a threshold -- it compares the count against a fixed amount and
yields on or off -- so it can switch a fixed anthem on and off and never size
one. `count` cannot stand in either: it counts *objects* matching a filter, and
counters are not objects, so no filter reaches "the number of charge counters on
this artifact".

The failure mode this file exists to pin is the quiet one.
`characteristics._static_value` used to `return 0` for vocabulary it did not
know, so `counters_on` in a static -- had the loader let it through -- would have
been an anthem that loaded clean, printed as the card does and gave +0/+0 for
ever. Both halves are covered: :class:`TestTheLoaderRefusesAWrongLeaf` for the
load-time guard, and :class:`TestNoLeafReadsZeroInSilence` for the engine's
refusal to shrug.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.statics import _validate_static_value
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects.values import validate_value
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, remove_counters

BANNER = "t_charge_banner"  # creatures you control get +1/+1 per charge counter on it
ENGINE = "t_charge_engine"  # */* equal to the charge counters on it
BEAR = "t_bear"  # a plain 2/2
DOOR = "door_of_destinies"

#: The leaf itself, spelled the way a card spells it.
CHARGES = {"counters_on": {"counter": "charge", "objects": {"self_only": True}}}


def board(builder, *, charges: int = 0, bears: int = 1, players: int = 2):
    """A Banner with ``charges`` counters on it and ``bears`` creatures beside it."""
    b = builder(players=players)
    b.battlefield(0, [BANNER], counters={"charge": charges} if charges else None)
    if bears:
        b.battlefield(0, [BEAR] * bears)
    return b.build(advance=False)


def oid_of(game, card_id: str, controller: int = 0) -> int:
    for obj in game.state.battlefield_objects(controller):
        if game.state.card_of(obj).id == card_id:
            return obj.oid
    raise AssertionError(f"no {card_id} on the battlefield")


def pt(game, card_id: str, controller: int = 0) -> tuple[int, int]:
    c = chars(game.state, oid_of(game, card_id, controller))
    return c.power, c.toughness


class TestTheAnthemHasASize:
    """The claim: the magnitude is the counter count, not a fixed number."""

    def test_no_counters_is_no_anthem(self, builder):
        """The boundary. Door of Destinies enters with nothing on it."""
        game = board(builder, charges=0)
        assert pt(game, BEAR) == (2, 2)

    def test_one_counter_is_plus_one(self, builder):
        game = board(builder, charges=1)
        assert pt(game, BEAR) == (3, 3)

    def test_five_counters_is_plus_five(self, builder):
        """Unbounded, which a ladder of threshold-conditioned statics is not."""
        game = board(builder, charges=5)
        assert pt(game, BEAR) == (7, 7)

    def test_a_counter_landing_grows_what_is_already_there(self, builder):
        """`add_counters` bumps `char_version`, so the cache cannot hold a stale size."""
        game = board(builder, charges=1)
        assert pt(game, BEAR) == (3, 3)
        add_counters(game.state, oid_of(game, BANNER), "charge", 1)
        assert pt(game, BEAR) == (4, 4), "the creature already out grew too"

    def test_a_counter_leaving_shrinks_it_again(self, builder):
        """The wearing-off. An "as long as" magnitude is re-read, not latched."""
        game = board(builder, charges=3)
        assert pt(game, BEAR) == (5, 5)
        remove_counters(game.state, oid_of(game, BANNER), "charge", 2)
        assert pt(game, BEAR) == (3, 3)
        remove_counters(game.state, oid_of(game, BANNER), "charge", 1)
        assert pt(game, BEAR) == (2, 2), "back to printed, with the static still there"

    def test_a_creature_arriving_later_is_sized_by_the_counters_already_there(
        self, builder
    ):
        """The whole reason this is a static and not an op.

        `add_counters` onto the creatures themselves would leave this one a 2/2:
        the counters were placed before it existed.
        """
        from commanderblitz.engine.enums import Zone
        from commanderblitz.engine.state import new_object

        game = board(builder, charges=4, bears=0)
        obj = new_object(game.state, BEAR, owner=0, zone=Zone.BATTLEFIELD)
        game.state.battlefield.append(obj.oid)
        game.state.bump_chars()

        assert pt(game, BEAR) == (6, 6)


class TestWhoseCountersAreRead:
    """`self_only` is scoped to the static's own source, one source at a time."""

    def test_a_second_banner_reads_its_own_counters(self, builder):
        """Two anthems, +2 and +3, and neither reads the other's five."""
        game = (
            builder(players=2)
            .battlefield(0, [BANNER], counters={"charge": 2})
            .battlefield(0, [BANNER], counters={"charge": 3})
            .battlefield(0, [BEAR])
            .build(advance=False)
        )
        assert pt(game, BEAR) == (7, 7), "2 + 3, not 5 + 5 and not 5"

    def test_an_opponents_banner_does_not_buff_your_creatures(self, builder):
        """`affects` still filters -- the leaf changes the size, not the reach."""
        game = (
            builder(players=2)
            .battlefield(1, [BANNER], counters={"charge": 4})
            .battlefield(0, [BEAR])
            .build(advance=False)
        )
        assert pt(game, BEAR) == (2, 2)

    def test_counters_of_another_kind_are_not_counted(self, builder):
        """The kind is looked up exactly, which is why the loader requires it."""
        game = board(builder, charges=0)
        add_counters(game.state, oid_of(game, BANNER), "quest", 6)
        assert pt(game, BEAR) == (2, 2)


class TestTheSetPtSlot:
    """The same leaf in the other magnitude slot -- Chimeric Mass's shape."""

    def engine_board(self, builder, charges: int):
        return (
            builder(players=2)
            .battlefield(0, [ENGINE], counters={"charge": charges})
            .build(advance=False)
        )

    def test_it_sets_rather_than_adds(self, builder):
        """Printed 4/4, so a `buff` reading would say 7/7."""
        game = self.engine_board(builder, 3)
        assert pt(game, ENGINE) == (3, 3)

    def test_it_tracks_the_counters(self, builder):
        game = self.engine_board(builder, 3)
        add_counters(game.state, oid_of(game, ENGINE), "charge", 2)
        assert pt(game, ENGINE) == (5, 5)

    def test_a_banner_stacks_on_top_of_it(self, builder):
        """Layer order: `set_pt` first, then the anthem. 2 set, then +3."""
        game = (
            builder(players=2)
            .battlefield(0, [ENGINE], counters={"charge": 2})
            .battlefield(0, [BANNER], counters={"charge": 3})
            .build(advance=False)
        )
        assert pt(game, ENGINE) == (5, 5)


class TestTheLoaderRefusesAWrongLeaf:
    """A near miss has to be a load error. Read as 0 it is an inert anthem."""

    def test_both_languages_accept_a_well_formed_leaf(self):
        validate_value(CHARGES, "test")
        _validate_static_value(CHARGES, "test")

    def test_a_missing_counter_kind_is_refused(self):
        """It defaults to `+1/+1` in the evaluator, which is never what was meant."""
        with pytest.raises(DslError, match="needs 'counter'"):
            _validate_static_value(
                {"counters_on": {"objects": {"self_only": True}}}, "test"
            )

    def test_a_missing_objects_is_refused(self):
        """An empty static filter is every permanent its controller has."""
        with pytest.raises(DslError, match="needs 'objects'"):
            _validate_static_value({"counters_on": {"counter": "charge"}}, "test")

    def test_a_keyword_near_miss_is_refused(self):
        """122.1c. `"vigilance counter"` is a tally nobody consults."""
        with pytest.raises(DslError, match="exact keyword name"):
            _validate_static_value(
                {
                    "counters_on": {
                        "counter": "vigilance counter",
                        "objects": {"self_only": True},
                    }
                },
                "test",
            )

    def test_a_misspelled_sub_key_is_refused(self):
        with pytest.raises(DslError, match="unsupported keys"):
            _validate_static_value(
                {"counters_on": {"countr": "charge", "objects": {"self_only": True}}},
                "test",
            )

    def test_the_static_language_applies_its_own_filter_rules(self):
        """Off the battlefield a card has a printed face and an owner, no more."""
        with pytest.raises(DslError, match="unsupported keys"):
            _validate_static_value(
                {
                    "counters_on": {
                        "counter": "charge",
                        "objects": {"zone": "graveyard", "tapped": True},
                    }
                },
                "test",
            )

    def test_the_effect_language_guards_the_same_leaf(self):
        """Both are validated separately, so a guard in one only is half a guard."""
        with pytest.raises(DslError, match="needs 'objects'"):
            validate_value({"counters_on": {"counter": "charge"}}, "test")


class TestNoLeafReadsZeroInSilence:
    """The reason this gap existed at all.

    `_static_value` returning 0 for vocabulary it did not know meant a leaf the
    loader had not been taught was an anthem that did nothing -- and nothing
    anywhere said so. It raises now, so the loader's whitelist and the engine's
    reader cannot drift apart without a test going red.
    """

    def test_an_unknown_leaf_raises_rather_than_reading_zero(self, builder):
        from commanderblitz.engine.characteristics import _static_value

        game = board(builder, charges=1)
        source = game.state.objects[oid_of(game, BANNER)]
        with pytest.raises(DslError, match="unknown static value"):
            _static_value(game.state, {"counters_of": "charge"}, source)

    def test_a_non_object_value_raises_too(self, builder):
        from commanderblitz.engine.characteristics import _static_value

        game = board(builder, charges=1)
        source = game.state.objects[oid_of(game, BANNER)]
        with pytest.raises(DslError, match="unparsable static value"):
            _static_value(game.state, "three", source)

    def test_an_absent_field_is_still_zero(self, builder):
        """A `buff` with no `toughness` is a real card, so None stays 0."""
        from commanderblitz.engine.characteristics import _static_value

        game = board(builder, charges=1)
        source = game.state.objects[oid_of(game, BANNER)]
        assert _static_value(game.state, None, source) == 0

    def test_an_empty_object_is_a_load_error(self):
        with pytest.raises(DslError, match="empty object"):
            _validate_static_value({}, "test")


class TestTheShippedCard:
    """Door of Destinies -- the card the leaf was built for."""

    def test_its_anthem_is_sized_by_its_counters(self, registry):
        card = registry.get(DOOR)
        static = next(a.static for a in card.abilities if a.is_static)
        assert static["power"] == {
            "counters_on": {"counter": "charge", "objects": {"self_only": True}}
        }, "not a `const`, which would be a fixed anthem"

    def test_it_buffs_the_chosen_type_and_scales(self, builder):
        """Charge counters on the Door, a Vampire beside it, the chosen type set."""
        game = (
            builder(players=2)
            .battlefield(0, [DOOR], counters={"charge": 3})
            .battlefield(0, [BEAR])
            .build(advance=False)
        )
        door = game.state.objects[oid_of(game, DOOR)]
        bear_subtype = next(iter(game.state.card_of(
            game.state.objects[oid_of(game, BEAR)]
        ).subtypes))
        door.chosen_type = bear_subtype
        game.state.bump_chars()

        assert pt(game, BEAR) == (5, 5)

    def test_a_creature_of_another_type_is_untouched(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [DOOR], counters={"charge": 3})
            .battlefield(0, [BEAR])
            .build(advance=False)
        )
        game.state.objects[oid_of(game, DOOR)].chosen_type = "Vampire"
        game.state.bump_chars()

        assert pt(game, BEAR) == (2, 2)
