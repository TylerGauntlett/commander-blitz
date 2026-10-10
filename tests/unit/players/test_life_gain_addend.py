"""Adding to a life gain: "you gain that much life plus 1 instead".

Angel of Vitality -- "If you would gain life, you gain that much life plus 1
instead." -- is the witness. Rule 614.1a makes it a replacement effect, the
same family as Alhammarret's Archive's "twice that much", and it could not be
written as one before: `replace_life_gain` carried only `gain_multiplier`, which
the loader refuses below 2, and "plus 1" is not a multiplier at any size. So the
static grew a second axis, `gain_addend`, exactly as `replace_counters` has
`counter_addend` beside `counter_multiplier`, and a card uses one or the other.

The near miss is a `you_gain_life` trigger that gains 1 more, and it is a
different card three ways: the extra point goes on the stack; it is a second
`LIFE_GAINED` event, so every "whenever you gain life" permanent pays out twice;
and it triggers itself, forever.

The claims, each of which an implementation could get wrong while a plain
"gain 3, have 44" assertion still passed:

* **Per event, not per point** (614.1a, and the Angel's ruling): a gain of 3 is
  4, a lifelink hit of 5 is 6, and a gain of 0 is no event at all, so nothing
  is added to it.
* **One event, carrying the replaced amount** -- "whenever you gain life, put
  that many +1/+1 counters" reads 4, agreeing with the life total.
* **Against a doubler the order is the gaining player's** (616.1), and here it
  shows: (3+1)*2 = 8 but 3*2+1 = 7. `primitives.gain_life` cannot ask --
  lifelink reaches it from inside combat damage -- so it applies the addend
  first, the larger gain and the order the gaining player picks, **whichever
  permanent arrived first**. Recorded as a divergence in rules-coverage.md: a
  player who wanted the smaller gain cannot have it.
* **"Can't" and a locked life total still win** (101.2, 118.5): plus 1 on a gain
  that cannot happen is still no gain.

And the Angel's other line, "this creature gets +2/+2 as long as you have 25 or
more life", which is a static `condition` reading its controller's own life
total -- `max_life_of: "you"`, one player, so the minimum and maximum agree. The
claim worth testing is that it **follows the life total as it moves**: the
characteristic cache is keyed on `char_version`, and a condition read once and
cached would leave the Angel a 4/4 at 10 life.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import life_gain_addend, life_gain_multiplier
from commanderblitz.engine.primitives import damage_player, gain_life, lose_life
from commanderblitz.engine.structs import LifeLock
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, pass_until

VITALITY = "t_vitality"
OPPONENT_VITALITY = "t_opponent_vitality"
BODY = "t_vitality_body"
ARCHIVE = "t_archive"
GAIN_SPELL = "t_gain_spell"
LIFELINK_BEAR = "t_lifelink_bear"


def position(builder, *ids: str, active: int = 0, hand=(), life: int = 40):
    """Two players, ``ids`` on player 0's battlefield in that (arrival) order."""
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 4)
        .battlefield(0, list(ids))
        .hand(0, list(hand))
        .life(0, life)
        .life(1, 40)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    game.state.active_idx = active
    return game


def oid_of(game, def_id: str) -> int:
    return next(
        oid for oid in game.state.battlefield if game.state.objects[oid].def_id == def_id
    )


def gained_events(game, mark: int) -> list:
    return [e for e in game.state.events[mark:] if e.type == "life_gained"]


class TestTheAddendItself:
    """`life_gain_addend` is what `gain_life` reads beside the multiplier."""

    def test_nothing_on_the_board_adds_nothing(self, builder):
        game = position(builder)
        assert life_gain_addend(game.state, 0) == 0

    def test_it_reaches_its_controller(self, builder):
        game = position(builder, VITALITY)
        assert life_gain_addend(game.state, 0) == 1

    def test_it_does_not_reach_the_opponent(self, builder):
        """"If *you* would gain life" -- `affects_player` is not decoration."""
        game = position(builder, VITALITY)
        assert life_gain_addend(game.state, 1) == 0

    def test_affects_player_opponent_points_the_other_way(self, builder):
        game = position(builder, OPPONENT_VITALITY)
        assert life_gain_addend(game.state, 0) == 0
        assert life_gain_addend(game.state, 1) == 1

    def test_two_angels_add_two(self, builder):
        """614.5: two replacements, each applied once -- plus 1, then plus 1."""
        game = position(builder, VITALITY, VITALITY)
        assert life_gain_addend(game.state, 0) == 2

    def test_an_addend_is_not_a_multiplier(self, builder):
        """The Angel's static reads as x1 on the other axis, never x0."""
        game = position(builder, VITALITY)
        assert life_gain_multiplier(game.state, 0) == 1

    def test_a_multiplier_is_not_an_addend(self, builder):
        game = position(builder, ARCHIVE)
        assert life_gain_addend(game.state, 0) == 0


class TestAPlainLifeGain:
    def test_three_becomes_four(self, builder):
        game = position(builder, VITALITY)
        assert gain_life(game.state, 0, 3) == 4
        assert game.state.players[0].life == 44

    def test_one_event_carrying_the_replaced_amount(self, builder):
        """One event of 4 -- not a 3 and then a 1, and not a 3 at all."""
        game = position(builder, VITALITY)
        mark = len(game.state.events)
        gain_life(game.state, 0, 3)
        events = gained_events(game, mark)
        assert len(events) == 1
        assert events[0].data["amount"] == 4

    def test_a_gain_of_zero_is_no_event_to_add_to(self, builder):
        """The Angel's ruling: an effect that would gain you 0 life gains you
        nothing, because there is no life-gain event for it to replace."""
        game = position(builder, VITALITY)
        mark = len(game.state.events)
        assert gain_life(game.state, 0, 0) == 0
        assert game.state.players[0].life == 40
        assert gained_events(game, mark) == []

    def test_each_gain_is_its_own_event(self, builder):
        game = position(builder, VITALITY)
        gain_life(game.state, 0, 1)
        gain_life(game.state, 0, 1)
        assert game.state.players[0].life == 44

    def test_the_opponents_gain_is_untouched(self, builder):
        game = position(builder, VITALITY)
        assert gain_life(game.state, 1, 3) == 3

    def test_a_locked_life_total_is_still_locked(self, builder):
        """118.5 wins: plus 1 on a gain that cannot happen is still no gain."""
        game = position(builder, VITALITY)
        game.state.life_locks.append(LifeLock(player=0))
        assert gain_life(game.state, 0, 3) == 0
        assert game.state.players[0].life == 40

    def test_it_stops_applying_when_the_angel_leaves(self, builder):
        game = position(builder, VITALITY)
        move_object(game.state, oid_of(game, VITALITY), Zone.GRAVEYARD)
        assert gain_life(game.state, 0, 3) == 3


class TestLifelink:
    """702.15b -- the gain nobody writes as a `gain_life`."""

    def test_lifelink_gains_the_damage_plus_one(self, builder):
        game = position(builder, VITALITY, LIFELINK_BEAR)
        damage_player(game.state, 1, 3, oid_of(game, LIFELINK_BEAR))
        assert game.state.players[0].life == 44

    def test_the_damage_itself_is_not_increased(self, builder):
        game = position(builder, VITALITY, LIFELINK_BEAR)
        assert damage_player(game.state, 1, 3, oid_of(game, LIFELINK_BEAR)) == 3
        assert game.state.players[1].life == 37


class TestAgainstADoubler:
    """616.1: the gaining player orders the two, and the order shows."""

    @pytest.mark.parametrize(
        "arrival", [(VITALITY, ARCHIVE), (ARCHIVE, VITALITY)], ids=["angel-first", "archive-first"]
    )
    def test_the_addend_applies_first_whatever_arrived_first(self, builder, arrival):
        """(3+1)*2 = 8, the larger gain and the gaining player's pick -- not
        3*2+1 = 7, and not a different answer depending on arrival order."""
        game = position(builder, *arrival)
        assert gain_life(game.state, 0, 3) == 8
        assert game.state.players[0].life == 48

    def test_every_addend_before_every_multiplier(self, builder):
        """Two Angels and an Archive: (3+1+1)*2 = 10."""
        game = position(builder, ARCHIVE, VITALITY, VITALITY)
        assert gain_life(game.state, 0, 3) == 10

    def test_lifelink_under_both(self, builder):
        game = position(builder, ARCHIVE, VITALITY, LIFELINK_BEAR)
        damage_player(game.state, 1, 2, oid_of(game, LIFELINK_BEAR))
        assert game.state.players[0].life == 46

    def test_one_event_under_both(self, builder):
        game = position(builder, ARCHIVE, VITALITY)
        mark = len(game.state.events)
        gain_life(game.state, 0, 3)
        assert [e.data["amount"] for e in gained_events(game, mark)] == [8]


class TestItReachesRealPlay:
    def test_a_gain_spell_gains_one_more(self, builder):
        game = position(builder, VITALITY, hand=(GAIN_SPELL,))
        game.apply(action_for_card(game, ActionKind.CAST, GAIN_SPELL))
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.players[0].life == 44


class TestTheBodyReadsYourOwnLife:
    """"This creature gets +2/+2 as long as you have 25 or more life.\""""

    def test_at_forty_it_is_four_four(self, builder):
        game = position(builder, BODY)
        c = chars(game.state, oid_of(game, BODY))
        assert (c.power, c.toughness) == (4, 4)

    def test_at_exactly_twenty_five_it_is_on(self, builder):
        game = position(builder, BODY, life=25)
        c = chars(game.state, oid_of(game, BODY))
        assert (c.power, c.toughness) == (4, 4)

    def test_at_twenty_four_it_is_off(self, builder):
        game = position(builder, BODY, life=24)
        c = chars(game.state, oid_of(game, BODY))
        assert (c.power, c.toughness) == (2, 2)

    def test_it_reads_its_controller_not_the_table(self, builder):
        """The opponent at 40 does not switch it on for a controller at 10."""
        game = position(builder, BODY, life=10)
        c = chars(game.state, oid_of(game, BODY))
        assert (c.power, c.toughness) == (2, 2)

    def test_it_wears_off_as_life_is_lost(self, builder):
        """Read at 40, then at 24: the cached 4/4 must not survive the loss."""
        game = position(builder, BODY)
        oid = oid_of(game, BODY)
        assert chars(game.state, oid).power == 4
        lose_life(game.state, 0, 16)
        assert game.state.players[0].life == 24
        assert (chars(game.state, oid).power, chars(game.state, oid).toughness) == (2, 2)

    def test_it_switches_back_on_as_life_is_gained(self, builder):
        game = position(builder, BODY, life=24)
        oid = oid_of(game, BODY)
        assert chars(game.state, oid).power == 2
        gain_life(game.state, 0, 1)
        assert chars(game.state, oid).power == 4

    def test_damage_to_its_controller_switches_it_off(self, builder):
        game = position(builder, BODY, life=26)
        oid = oid_of(game, BODY)
        assert chars(game.state, oid).power == 4
        damage_player(game.state, 0, 2, None)
        assert chars(game.state, oid).power == 2


class TestTheLoaderRefusesWhatIsNotACard:
    @pytest.mark.parametrize("bad", [0, -1])
    def test_addend_below_one_is_refused(self, bad):
        with pytest.raises(DslError, match="gain_addend"):
            compile_card(CardModel.model_validate(_card(gain_addend=bad)))

    def test_both_axes_on_one_static_are_refused(self):
        with pytest.raises(DslError, match="not both"):
            compile_card(CardModel.model_validate(_card(gain_addend=1, gain_multiplier=2)))

    def test_one_axis_is_required(self):
        with pytest.raises(DslError, match="gain_addend"):
            compile_card(CardModel.model_validate(_card()))

    def test_the_addend_is_refused_on_another_effect(self):
        card = _card(gain_addend=1)
        card["abilities"][0]["effect"] = "replace_life_loss"
        card["abilities"][0]["loss_multiplier"] = 2
        with pytest.raises(DslError, match="gain_addend"):
            compile_card(CardModel.model_validate(card))

    def test_the_printed_shape_loads(self):
        static = compile_card(CardModel.model_validate(_card(gain_addend=1))).abilities[0]
        assert static.static["gain_addend"] == 1


def _card(**fields) -> dict:
    ability = {
        "kind": "static",
        "text": "If you would gain life, you gain that much life plus 1 instead.",
        "effect": "replace_life_gain",
        "affects_player": "you",
        **fields,
    }
    return {
        "id": "t_bad_vitality",
        "name": "Test Bad Vitality",
        "oracle_text": "If you would gain life, you gain that much life plus 1 instead.",
        "mana_cost": "{3}",
        "types": ["Artifact"],
        "abilities": [ability],
    }
