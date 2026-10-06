"""A variable number of counters as a permanent enters (614.1c, 121.6).

"Éomer enters with a +1/+1 counter on it for each other Human you control."
Rule 614.1c makes that a *replacement* — the permanent is modified as it enters
and is never on the battlefield without the counters — and 121.6 says the
counters are put on it as it enters rather than by anything resolving
afterwards.

What was wrong without this: `replacements` has always been the right home for
the clause. `self_enters_with_counters` is what Mossborn Hydra uses for its
fixed "enters with a +1/+1 counter on it", and what
`loader._replacements_with_loyalty` compiles a planeswalker's starting loyalty
into. But `ReplacementModel.amount` was typed `int = 1` under a strict model
config, so a value expression was a validation error and **only a constant could
be printed**. A card whose count is "for each other Human you control" had no
honest constant to pick — 0 on an empty board and unbounded in play — so it
could not be written at all.

The nearest substitute is a `self_enters` triggered ability running
`add_counters`, and on Éomer in particular it is wrong three ways:

1. It is a trigger, not a replacement. The permanent is on the battlefield at
   its printed size first and grows later, which is exactly what 614.1c says
   never happens. `TestItIsAReplacementNotATrigger` is that contrast, run
   against `t_marshal_trigger`, the substitute written out as a card.
2. Éomer's *other* enters trigger deals damage equal to **its power**. With the
   counters arriving from a second simultaneous trigger, the card's whole
   payload would depend on which of the two his controller happened to order
   first: 2 damage or 2 + N, from printed text containing no such choice.
   `TestTheDamageDoesNotDependOnTriggerOrder` is that claim, on
   `t_marshal_striker`.
3. The op route fires `COUNTER_PLACED`; the replacement route calls
   `add_counter` directly and fires nothing. The substitute would additionally
   wake every `counter_placed` watcher on the board.

The witness is Éomer, King of Rohan, authored by this change. The family behind
him is large — `data/authoring/queue.json` defers thirty-nine cards on "enters
with a … counter on it for each …" (Diregraf Colossus, Gatekeeper Gargoyle,
Kinsbaile Borderguard, Golgari Grave-Troll, Ulasht, Verazol and the Converge
cycle), and every one is unblocked by widening this one field.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.zones import move_object
from tests.conftest import action_for_card, only_oid, pass_until

HUMAN = "t_human"
BEAR = "t_bear"
MARSHAL = "t_marshal"
MARSHAL_MODIFY = "t_marshal_modify"
MARSHAL_STRIKER = "t_marshal_striker"
MARSHAL_TRIGGER = "t_marshal_trigger"


def a_board(builder, card: str = MARSHAL, *, humans: int = 0, bears: int = 0):
    """A game with `card` in hand, enough Plains to cast it, and a board.

    The other permanents are the thing being counted, so they are the fixture's
    only parameter: every test here is "how many did it see?".
    """
    b = builder(players=2).battlefield(0, ["plains"] * 3).hand(0, [card])
    if humans:
        b = b.battlefield(0, [HUMAN] * humans)
    if bears:
        b = b.battlefield(0, [BEAR] * bears)
    return b.build()


def cast_it(game, card: str = MARSHAL) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, card))


def resolve(game, card: str = MARSHAL) -> int:
    """Cast `card` and let everything it caused finish; return its oid."""
    cast_it(game, card)
    pass_until(game, lambda g: not g.state.stack)
    return only_oid(game, card, 0)


def counters_of(game, oid: int) -> dict[str, int]:
    return dict(game.state.objects[oid].counters)


class TestTheCountIsTakenFromTheBoardItArrivesOn:
    """"…for each other Human you control", counted as it enters."""

    def test_no_other_humans_is_no_counters(self, builder):
        """The boundary the constant could never be, in the direction that
        looks like nothing happened: a zero count must leave no counter behind
        rather than an inert `{"+1/+1": 0}` tally."""
        game = a_board(builder)
        oid = resolve(game)
        assert counters_of(game, oid) == {}
        assert chars(game.state, oid).power == 2

    @pytest.mark.parametrize("humans", [1, 2, 5])
    def test_it_scales_with_the_board(self, builder, humans):
        """Parametrised because a constant passes any single case. Three
        numbers is what separates "counted" from "printed"."""
        game = a_board(builder, humans=humans)
        oid = resolve(game)
        assert counters_of(game, oid) == {"+1/+1": humans}
        assert chars(game.state, oid).power == 2 + humans

    def test_other_means_other(self, builder):
        """`exclude_self` is load-bearing: the permanent is already on the
        battlefield when the replacement is evaluated (`_add_to_zone` has run),
        so without it a lone Marshal would count itself and enter as a 3/3."""
        game = a_board(builder, humans=2)
        oid = resolve(game)
        assert counters_of(game, oid) == {"+1/+1": 2}

    def test_it_counts_the_subtype_and_not_the_creatures(self, builder):
        """The Bears are the control. A count that read "creature" instead of
        "Human" is the silent near-miss this asserts against."""
        game = a_board(builder, humans=1, bears=3)
        oid = resolve(game)
        assert counters_of(game, oid) == {"+1/+1": 1}

    def test_it_does_not_count_an_opponents_humans(self, builder):
        """"you control". Nothing in the selector defaults to the whole table,
        but a missing `controller` would read every Human in play."""
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 3)
            .battlefield(0, [HUMAN])
            .battlefield(1, [HUMAN] * 4)
            .hand(0, [MARSHAL])
            .build()
        )
        oid = resolve(game)
        assert counters_of(game, oid) == {"+1/+1": 1}

    def test_a_second_copy_counts_the_first(self, builder):
        """Two Marshals: the second sees the first, counters and all. The board
        is read live, so this is the whole difference from a constant said out
        loud."""
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 6)
            .battlefield(0, [HUMAN])
            .hand(0, [MARSHAL, MARSHAL_MODIFY])
            .build()
        )
        first = resolve(game, MARSHAL)
        second = resolve(game, MARSHAL_MODIFY)
        assert counters_of(game, first) == {"+1/+1": 1}
        assert counters_of(game, second) == {"+1/+1": 2}

    def test_the_modify_counters_spelling_evaluates_too(self, builder):
        """`modify: {"counters": {kind: amount}}` is the other spelling of the
        same clause and `zones._enter_battlefield` reads whichever is there. A
        widening that reached only the top-level `amount` would leave half the
        DSL taking constants, and nothing would say so."""
        game = a_board(builder, MARSHAL_MODIFY, humans=3)
        oid = resolve(game, MARSHAL_MODIFY)
        assert counters_of(game, oid) == {"+1/+1": 3}

    def test_a_constant_amount_still_works(self, builder):
        """Fading 2 and every planeswalker's starting loyalty go through this
        field. Widening a type must not change what the old shape means."""
        game = builder(players=2).battlefield(0, ["island"] * 3).hand(0, ["t_fader"]).build()
        oid = resolve(game, "t_fader")
        assert counters_of(game, oid) == {"fade": 2}

    def test_it_is_recounted_each_time_it_enters(self, builder):
        """121.2 takes the counters when it leaves, so a permanent that returns
        is recounted against the board it comes back to -- not restored to the
        number it had. Flickered with its two friends gone, the Marshal is a
        2/2 again."""
        game = a_board(builder, humans=2)
        oid = resolve(game)
        assert counters_of(game, oid) == {"+1/+1": 2}

        for human in list(game.state.battlefield):
            obj = game.state.objects[human]
            if obj.def_id == HUMAN:
                move_object(game.state, human, Zone.GRAVEYARD)
        move_object(game.state, oid, Zone.EXILE)
        move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0)

        assert counters_of(game, oid) == {}


class TestItIsAReplacementNotATrigger:
    """614.1c: the permanent is never seen at its printed size.

    `t_marshal_trigger` is the substitute the gap record forbids, written out as
    a card so the difference can be observed rather than argued. Both cards end
    the turn as 4/4s; only one of them was ever a 2/2 on the battlefield.
    """

    def land(self, builder, card: str, humans: int = 2):
        """Put `card` onto the battlefield and stop the instant it is there.

        `move_object` is the whole of entering: it applies the replacements and
        fires `ENTERS_BATTLEFIELD`, which only *queues* triggers onto
        `state.pending_triggers` -- they reach the stack the next time a player
        would get priority. Driving it here rather than through `game.apply`
        is what makes the moment observable at all; the game loop resolves
        straight through it.
        """
        game = (
            builder(players=2)
            .battlefield(0, [HUMAN] * humans)
            .hand(0, [card])
            .build()
        )
        oid = next(
            o.oid for o in game.state.objects.values()
            if o.def_id == card and o.zone is Zone.HAND
        )
        move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0)
        return game, oid

    def test_the_replacement_arrives_already_grown(self, builder):
        game, oid = self.land(builder, MARSHAL)
        assert chars(game.state, oid).power == 4
        assert counters_of(game, oid) == {"+1/+1": 2}

    def test_the_trigger_form_lands_as_a_two_two(self, builder):
        """The contrast that makes the previous test mean something. The
        substitute puts a 2/2 on the battlefield and a trigger in the queue;
        anything that looks in between -- another enters trigger, a static, a
        state-based action -- sees the printed creature."""
        game, oid = self.land(builder, MARSHAL_TRIGGER)
        assert chars(game.state, oid).power == 2
        assert counters_of(game, oid) == {}
        assert len(game.state.pending_triggers) == 1

    def test_the_replacement_queues_nothing(self, builder):
        """A replacement is not an ability. Nothing to order, nothing to hold
        priority for, nothing to respond to -- and, since `zones` calls
        `add_counter` directly rather than going through the `add_counters`
        primitive, no `counter_placed` for anything else to see either."""
        game, _ = self.land(builder, MARSHAL)
        assert game.state.pending_triggers == []

    def test_the_trigger_form_does_get_there_eventually(self, builder):
        """And it is not that the substitute is broken -- it reaches the same
        4/4. The whole difference is *when*, which is the difference Éomer's
        third printed line is paid in."""
        game = a_board(builder, MARSHAL_TRIGGER, humans=2)
        oid = resolve(game, MARSHAL_TRIGGER)
        assert chars(game.state, oid).power == 4


class TestTheDamageDoesNotDependOnTriggerOrder:
    """Éomer's third line: "…deals damage equal to its power to any target".

    `t_marshal_striker` is that shape reduced to what can be asserted without a
    target: the counters are a replacement, the damage is an enters trigger. If
    the counters were a trigger too there would be two simultaneous triggers and
    the number would be the controller's to choose. There is one, and the number
    is the board's.
    """

    def life_of(self, game, pid: int) -> int:
        return game.state.players[pid].life

    @pytest.mark.parametrize("humans,expected", [(0, 2), (1, 3), (4, 6)])
    def test_the_damage_is_the_grown_power(self, builder, humans, expected):
        game = a_board(builder, MARSHAL_STRIKER, humans=humans)
        start = self.life_of(game, 1)
        resolve(game, MARSHAL_STRIKER)
        assert start - self.life_of(game, 1) == expected

    def test_only_one_trigger_is_ever_queued(self, builder):
        """The claim underneath the numbers above. Two simultaneous triggers
        would be two orderings and two answers -- 2 damage or 2 + N, from
        printed text that offers no such choice. The count arriving as a
        replacement is what makes the second trigger not exist."""
        game = (
            builder(players=2)
            .battlefield(0, [HUMAN] * 2)
            .hand(0, [MARSHAL_STRIKER])
            .build()
        )
        oid = next(
            o.oid for o in game.state.objects.values()
            if o.def_id == MARSHAL_STRIKER and o.zone is Zone.HAND
        )
        move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0)
        assert len(game.state.pending_triggers) == 1


class TestTheLoaderChecksIt:
    """The expression is only evaluated when a permanent actually enters, so an
    unrecognised key is a mid-game crash unless it is refused at load."""

    def _card(self, replacement: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_variable_arrival",
                "name": "Test Variable Arrival",
                "mana_cost": "{1}{W}",
                "types": ["Creature"],
                "subtypes": ["Human"],
                "power": 2,
                "toughness": 2,
                "oracle_text": "This creature enters with a +1/+1 counter on it "
                "for each other Human you control.",
                "replacements": [replacement],
            }
        )

    def _amount(self, amount) -> dict:
        return {
            "event": "self_enters_with_counters",
            "counter": "+1/+1",
            "amount": amount,
        }

    def test_a_count_over_a_selector_is_the_form(self):
        compile_card(
            self._card(
                self._amount(
                    {"count": {"zone": "battlefield", "controller": "you",
                               "subtypes": ["Human"], "exclude_self": True}}
                )
            )
        )

    def test_a_plain_integer_is_still_accepted(self):
        compile_card(self._card(self._amount(2)))

    def test_an_unknown_value_key_is_refused(self):
        with pytest.raises(DslError, match="unknown value keys"):
            compile_card(self._card(self._amount({"count_of_humans": {}})))

    def test_a_bad_selector_inside_the_count_is_refused(self):
        """One level down, which is where a typo actually lands -- the value
        form is right and the thing it counts is nonsense."""
        with pytest.raises(DslError):
            compile_card(
                self._card(self._amount({"count": {"subtypez": ["Human"]}}))
            )

    def test_the_modify_counters_spelling_is_checked_too(self):
        with pytest.raises(DslError, match="unknown value keys"):
            compile_card(
                self._card(
                    {
                        "event": "self_enters_with_counters",
                        "modify": {"counters": {"+1/+1": {"count_of_humans": {}}}},
                    }
                )
            )

    def test_a_string_amount_is_refused(self):
        """`amount` is widened to `int | dict`, not to the whole value language:
        `"x"` is the only bare string a value may be, and there is no X when a
        permanent enters. The strict model refuses it before `validate_value`
        ever sees it, which is the earlier of the two load-time gates and the
        one that gives the better message."""
        with pytest.raises(ValidationError):
            compile_card(self._card(self._amount("each other Human")))
