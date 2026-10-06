"""Counters replaced on the way in.

    "If one or more +1/+1 counters would be put on a creature you control,
    **that many plus one** +1/+1 counters are put on it instead."
                                            -- High Score, Hardened Scales

`static_effects` had replacements for tokens, draws, life gain, life loss and
milling, and none at all for counters -- and not one of their fields could have
been borrowed. Every one is a *multiplier*, refused below 2 by the loader, and
"plus one" is not a multiplier at any size.

**Where.** `primitives.add_counters` is the single funnel every placement comes
through -- the `add_counters` op, `move_counters`, `proliferate`, the `counters`
key on `put_onto_battlefield` and entering with counters -- so the replacement
is applied once per batch there, *before* the `counter_placed` event is fired
and before a Saga chapter comparison reads the new total. A replacement that
fired the event with the pre-replacement number would be a card lying to every
trigger watching it.

**Not a `counter_placed` trigger**, which is the near miss the gap record named
and is the wrong sentence twice over: a trigger uses the stack, so the extra
counter would arrive after state-based actions and after anything else that read
the count, and its own `add_counters` would fire `counter_placed` again and
retrigger itself.

**An object, not a player.** The five replacements before this one are about a
player -- your life, your draws, their mill -- and take `affects_player`. Every
printed counter-replacement names what the counters would be put on instead, so
this one takes `affects`, and the filter is required: without it the card
replaces an opponent's counters too, which is a strictly better card than any
that has been printed.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.errors import DslError
from automtg.engine.primitives import add_counters, remove_counters
from tests.conftest import only_oid, two_seat_board

SCALES = "t_rc_scales"  # +1/+1 only, "that many plus one", creatures you control
SEASON = "t_rc_season"  # every kind, "twice that many", permanents you control
CHARGE = "t_rc_charge"  # charge only, "twice that many"
BEAR = "t_rc_bear"
ROCK = "t_rc_rock"


def put(game, oid: int, kind: str = "+1/+1", amount: int = 1) -> int:
    """Put counters on, returning how many actually arrived."""
    return add_counters(game.state, oid, kind, amount)


def counters(game, oid: int, kind: str = "+1/+1") -> int:
    return game.state.objects[oid].counter(kind)


class TestTheAddend:
    def test_one_becomes_two(self, builder):
        game = two_seat_board(builder, mine=[SCALES, BEAR])
        put(game, only_oid(game, BEAR))
        assert counters(game, only_oid(game, BEAR)) == 2

    def test_three_becomes_four(self, builder):
        """Once per *placement*, not once per counter. 614.1's "one or more …
        would be put" is one event however many counters it carries, which is
        what the printed "that many plus one" says."""
        game = two_seat_board(builder, mine=[SCALES, BEAR])
        put(game, only_oid(game, BEAR), amount=3)
        assert counters(game, only_oid(game, BEAR)) == 4

    def test_the_caller_is_told_the_real_number(self, builder):
        """`add_counters` returns what arrived, and several callers use it to
        report or to count. Returning the number asked for would make every one
        of them disagree with the board."""
        game = two_seat_board(builder, mine=[SCALES, BEAR])
        assert put(game, only_oid(game, BEAR)) == 2

    def test_with_no_replacement_on_the_table(self, builder):
        """The control."""
        game = two_seat_board(builder, mine=[BEAR])
        put(game, only_oid(game, BEAR))
        assert counters(game, only_oid(game, BEAR)) == 1


class TestTheMultiplier:
    def test_one_becomes_two(self, builder):
        game = two_seat_board(builder, mine=[SEASON, BEAR])
        put(game, only_oid(game, BEAR))
        assert counters(game, only_oid(game, BEAR)) == 2

    def test_three_becomes_six(self, builder):
        game = two_seat_board(builder, mine=[SEASON, BEAR])
        put(game, only_oid(game, BEAR), amount=3)
        assert counters(game, only_oid(game, BEAR)) == 6


class TestTheFilters:
    def test_a_kind_it_does_not_name_is_untouched(self, builder):
        """Hardened Scales says +1/+1 and means it."""
        game = two_seat_board(builder, mine=[SCALES, BEAR])
        put(game, only_oid(game, BEAR), kind="charge", amount=2)
        assert counters(game, only_oid(game, BEAR), "charge") == 2

    def test_a_kindless_replacement_takes_every_kind(self, builder):
        """Doubling Season names none, so it doubles the charge counters too."""
        game = two_seat_board(builder, mine=[SEASON, BEAR])
        put(game, only_oid(game, BEAR), kind="charge", amount=2)
        assert counters(game, only_oid(game, BEAR), "charge") == 4

    def test_a_permanent_the_affects_filter_misses(self, builder):
        """"a **creature** you control". The artifact is yours and is not one."""
        game = two_seat_board(builder, mine=[SCALES, ROCK])
        put(game, only_oid(game, ROCK), kind="charge", amount=1)
        assert counters(game, only_oid(game, ROCK), "charge") == 1

    def test_an_opponents_creature_is_untouched(self, builder):
        """"a creature **you control**" -- the half that makes this a card
        rather than a rule."""
        game = two_seat_board(builder, mine=[SCALES], theirs=[BEAR])
        put(game, only_oid(game, BEAR))
        assert counters(game, only_oid(game, BEAR)) == 1


class TestOnlyOnTheWayIn:
    def test_removing_counters_is_untouched(self, builder):
        """"would be **put** on" says nothing about counters coming off, and a
        doubled removal would be a different and much worse card."""
        game = two_seat_board(builder, mine=[SEASON, BEAR])
        bear = only_oid(game, BEAR)
        put(game, bear, amount=4)  # 8 after doubling
        remove_counters(game.state, bear, "+1/+1", 2)
        assert counters(game, bear) == 6


class TestSeveralCompound:
    def test_two_replacements_both_apply(self, builder):
        """614.5 applies each one once, each to the event as the last left it.
        Scales then Season on one counter is (1+1)*2 = 4.

        The order is `state.battlefield` order -- arrival order -- and 616.1
        gives the choice to the affected player, which this engine does not ask.
        That divergence is invisible between two multipliers and visible exactly
        here; `_replaced_counter_amount` owns it and `docs/rules-coverage.md`
        records it.
        """
        game = two_seat_board(builder, mine=[SCALES, SEASON, BEAR])
        put(game, only_oid(game, BEAR))
        assert counters(game, only_oid(game, BEAR)) == 4

    def test_a_replacement_does_not_re_apply_to_its_own_output(self, builder):
        """The other half of 614.5, and not an optimisation: this is the
        difference between Doubling Season and an infinite loop."""
        game = two_seat_board(builder, mine=[SEASON, BEAR])
        put(game, only_oid(game, BEAR))
        assert counters(game, only_oid(game, BEAR)) == 2

    def test_two_of_the_same_static_compound(self, builder):
        """Two Hardened Scales are two replacements of one event, not one."""
        game = two_seat_board(builder, mine=[SCALES, SCALES, BEAR])
        put(game, only_oid(game, BEAR))
        assert counters(game, only_oid(game, BEAR)) == 3


class TestTheEventReportsWhatArrived:
    def test_counter_placed_carries_the_replaced_amount(self, builder):
        """A trigger watching "whenever one or more +1/+1 counters are put on"
        has to be told the number that really arrived. Firing with the number
        asked for would be the card lying to everything listening."""
        game = two_seat_board(builder, mine=[SCALES, BEAR])
        mark = len(game.state.events)
        put(game, only_oid(game, BEAR), amount=2)
        placed = [
            e for e in game.state.events[mark:] if e.type == "counter_placed"
        ]
        assert [e.data["amount"] for e in placed] == [3]


class TestTheLoaderPlacesIt:
    def _card(self, ability):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "If one or more counters would be put on a creature you control…",
                "mana_cost": "{G}",
                "types": ["Enchantment"],
                "abilities": [ability],
            }
        )

    def _static(self, **extra):
        return {
            "kind": "static",
            "text": "If one or more counters would be put on a creature you control…",
            "effect": "replace_counters",
            "affects": {"controller": "you", "types": ["Creature"]},
            **extra,
        }

    def test_an_addend_loads(self):
        compile_card(self._card(self._static(counter_addend=1, counter="+1/+1")))

    def test_a_multiplier_loads(self):
        compile_card(self._card(self._static(counter_multiplier=2)))

    def test_without_a_filter_it_is_refused(self):
        """A replacement with no `affects` reaches every counter on the table,
        an opponent's included -- a strictly better card than any printed."""
        with pytest.raises(DslError, match="needs 'affects'"):
            compile_card(
                self._card(
                    {
                        "kind": "static",
                        "text": "…",
                        "effect": "replace_counters",
                        "counter_addend": 1,
                    }
                )
            )

    def test_without_a_magnitude_it_is_refused(self):
        """A replacement that says nothing about how many arrive is not this
        effect; it would load clean and replace a placement with itself."""
        with pytest.raises(DslError, match="needs 'counter_addend'"):
            compile_card(self._card(self._static()))

    def test_both_axes_at_once_are_refused(self):
        with pytest.raises(DslError, match="not both"):
            compile_card(
                self._card(self._static(counter_addend=1, counter_multiplier=2))
            )

    def test_a_multiplier_of_one_is_refused(self):
        """1 replaces a placement with itself and 0 puts none on -- a
        prevention, a different and much stronger sentence."""
        with pytest.raises(DslError, match="must be 2 or more"):
            compile_card(self._card(self._static(counter_multiplier=1)))

    def test_an_addend_of_zero_is_refused(self):
        with pytest.raises(DslError, match="must be 1 or more"):
            compile_card(self._card(self._static(counter_addend=0)))

    def test_a_negative_addend_is_refused(self):
        """"that many minus one" is no printed card, and it could take a
        placement to zero -- a prevention again."""
        with pytest.raises(DslError, match="must be 1 or more"):
            compile_card(self._card(self._static(counter_addend=-1)))

    def test_a_near_miss_counter_kind_is_refused(self):
        """The kind goes through `validate_counter_kind` like every other kind
        the DSL names. A counter vocabulary is open on purpose -- charge, quest,
        slumber -- so only the spellings that *nearly* name one the engine acts
        on are refused, and "Vigilance counter" is one: it normalises onto the
        keyword counter, so written here it would be a replacement pointed at a
        tally nobody keeps."""
        with pytest.raises(DslError):
            compile_card(
                self._card(self._static(counter_addend=1, counter="Vigilance counter"))
            )

    def test_the_fields_are_refused_on_another_static(self):
        """Ignored elsewhere, the card would print a replacement it never
        performs."""
        with pytest.raises(DslError, match="only mean anything on a replace_counters"):
            compile_card(
                self._card(
                    {
                        "kind": "static",
                        "text": "Creatures you control get +1/+1.",
                        "effect": "buff",
                        "affects": {"controller": "you"},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                        "counter_addend": 1,
                    }
                )
            )
