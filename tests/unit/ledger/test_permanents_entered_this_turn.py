"""Which permanents *entered the battlefield* this turn -- rules 603.4 and 400.7.

"At the beginning of combat on your turn, **if another Human entered the
battlefield under your control this turn**, create two 2/2 red Human Knight
creature tokens" -- Éowyn, Shieldmaiden, the commander of the Riders of Rohan
deck. An intervening-if (603.4), so the clause is checked twice: once when the
ability would trigger and again as it resolves.

Entering the battlefield is an **event**, and like every other event in
`TurnLedger` the board keeps no record that it happened. The near miss is
`exists`, and it is a *board* query -- and it is wrong in **both** directions,
which is what this file exists to pin:

* A Human that has sat on the battlefield since turn three makes
  `{"exists": {"subtypes": ["Human"], "zone": "battlefield"}}` true, and nothing
  entered. The trigger would fire every single combat.
* A Human that entered this turn and then died makes it false, and one did
  enter. The trigger would not fire on the turn it is printed for.

`set_flag`/`has_flag` is the other near miss and fails on lifetime: flags are
cleared only by `reset_permanent_state` on a zone change, never at cleanup, so a
word written the first time a Human entered leaves the gate open for the rest of
the game.

So `TurnLedger.permanents_entered` -- a list of `EnteredPermanent` snapshots
folded in `GameState.emit` from `ENTERS_BATTLEFIELD`, cleared at cleanup with
morbid, storm and raid -- read by one value expression,
`{"permanents_entered_this_turn": {"controller": …, "subtypes": […],
"exclude_self": true}}`, compared with an ordinary `cmp` the way morbid compares
`creatures_died_this_turn`.

A **snapshot** rather than an oid, and that is the design: the entered-and-died
case is precisely what the clause is for, and once a permanent has left there is
nothing to ask -- a token is popped out of `state.objects` entirely and a card in
a graveyard reports printed characteristics rather than the ones a static had
granted it.
"""

from __future__ import annotations

import pytest

from automtg.engine.effects.conditions import evaluate_condition
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.zones import move_object
from tests.conftest import action_for_card, count_on_battlefield, oids_of, only_oid, pass_until

HUMAN = "t_human_soldier"  # {1}{W} 2/2 Human Soldier
ELF = "t_elf_scout"  # {1}{G} 2/2 Elf Scout -- entered, and not a Human
BEAR = "t_bear"  # {1}{G} 2/2 Bear
MAIDEN = "t_shieldmaiden"  # Éowyn's shape, on a card the test suite owns
KNIGHT_TOKEN = "human_knight_2_2_r_trample_haste"

#: The printed clause, as a card writes it.
ANOTHER_HUMAN_ENTERED = {
    "cmp": ">=",
    "left": {
        "permanents_entered_this_turn": {
            "controller": "you",
            "subtypes": ["Human"],
            "exclude_self": True,
        }
    },
    "right": {"const": 1},
}

#: The board-shaped near miss, kept beside it so both can be measured on one
#: position. Every test that asserts a disagreement asserts both.
ANOTHER_HUMAN_IS_HERE = {
    "exists": {
        "zone": "battlefield",
        "controller": "you",
        "subtypes": ["Human"],
        "exclude_self": True,
    }
}


# ----------------------------------------------------------------------
# the position
# ----------------------------------------------------------------------


def board(builder, mine=(), theirs=(), hand=(), lands=6):
    """A position with mana up, so a creature can actually be cast and enter."""
    b = builder(players=2)
    b.battlefield(0, ["plains"] * lands)
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    if hand:
        b.hand(0, list(hand))
    return b.build()


def ctx(game, controller: int = 0, source: int | None = None) -> EffectContext:
    return EffectContext(state=game.state, controller=controller, source_oid=source)


def entered(game, spec, controller: int = 0, source: int | None = None) -> int:
    return evaluate_value(ctx(game, controller, source), {"permanents_entered_this_turn": spec})


def card_in_hand(game, card_id: str, pid: int = 0) -> int:
    """Put a card into a player's hand, for a test that only needs it to arrive."""
    from automtg.engine.state import new_object

    obj = new_object(game.state, card_id, owner=pid, zone=Zone.HAND)
    game.state.players[pid].hand.append(obj.oid)
    return obj.oid


def put_onto_battlefield(game, card_id: str, pid: int = 0) -> int:
    """Make a card in hand *enter* the battlefield, firing the real event.

    The event is what matters, not the route to it: a creature that is cast, one
    that is reanimated and one that is put onto the battlefield by another card
    all enter, and `_enter_battlefield` is the single funnel all three share.
    """
    oid = next(
        (
            obj.oid
            for obj in game.state.objects.values()
            if obj.def_id == card_id and obj.zone is Zone.HAND and obj.owner == pid
        ),
        None,
    )
    if oid is None:
        oid = card_in_hand(game, card_id, pid)
    move_object(game.state, oid, Zone.BATTLEFIELD)
    return oid


# ----------------------------------------------------------------------
# the record itself
# ----------------------------------------------------------------------


class TestTheLedgerRecordsWhatEntered:
    def test_a_permanent_that_entered_is_recorded(self, builder):
        game = board(builder, hand=(HUMAN,))
        oid = put_onto_battlefield(game, HUMAN)
        [record] = game.state.turn_ledger.permanents_entered
        assert record.oid == oid
        assert record.controller == 0
        assert "Human" in record.subtypes
        assert "Creature" in record.types

    def test_permanents_already_on_the_battlefield_did_not_enter(self, builder):
        """The boundary the whole clause turns on, and the case `exists` gets
        wrong first: a Human that has been there since turn three."""
        game = board(builder, mine=(HUMAN, HUMAN))
        assert game.state.turn_ledger.permanents_entered == []
        assert not evaluate_condition(game.state, ANOTHER_HUMAN_ENTERED, controller=0)
        assert evaluate_condition(game.state, ANOTHER_HUMAN_IS_HERE, controller=0), (
            "two Humans are standing right there -- which is why the board query "
            "is a strictly different question"
        )

    def test_the_record_survives_the_permanent_dying(self, builder):
        """The other direction, and the reason the record is a snapshot.

        A Human entered this turn and died before combat. `exists` says no Human
        is here; the printed clause says one entered, and it did.
        """
        game = board(builder, hand=(HUMAN,))
        oid = put_onto_battlefield(game, HUMAN)
        move_object(game.state, oid, Zone.GRAVEYARD)

        assert entered(game, {"controller": "you", "subtypes": ["Human"]}) == 1
        assert evaluate_condition(game.state, ANOTHER_HUMAN_ENTERED, controller=0)
        assert not evaluate_condition(game.state, ANOTHER_HUMAN_IS_HERE, controller=0), (
            "the board has forgotten it entirely -- the approximation this "
            "ledger refuses"
        )

    def test_the_snapshot_answers_after_the_object_is_gone(self, builder):
        """A token is popped out of `state.objects` altogether, so nothing but a
        snapshot taken at entry could be asked what it was."""
        game = board(builder, hand=(HUMAN,))
        oid = put_onto_battlefield(game, HUMAN)
        del game.state.objects[oid]

        [record] = game.state.turn_ledger.permanents_entered
        assert "Human" in record.subtypes
        assert entered(game, {"controller": "you", "subtypes": ["Human"]}) == 1

    def test_two_arrivals_of_the_same_permanent_are_two_arrivals(self, builder):
        """Rule 400.7 -- a permanent that leaves and comes back is a new object,
        so a flicker really did put two permanents onto the battlefield."""
        game = board(builder, hand=(HUMAN,))
        oid = put_onto_battlefield(game, HUMAN)
        move_object(game.state, oid, Zone.EXILE)
        move_object(game.state, oid, Zone.BATTLEFIELD)
        assert entered(game, {"controller": "you", "subtypes": ["Human"]}) == 2

    def test_it_clears_at_the_turn_boundary(self, builder):
        """The wearing-off, and the whole of why `set_flag` could not stand in:
        a flag is cleared on a zone change and never at cleanup, so a card
        written with one would fire every combat for the rest of the game."""
        game = board(builder, hand=(HUMAN,))
        put_onto_battlefield(game, HUMAN)
        assert evaluate_condition(game.state, ANOTHER_HUMAN_ENTERED, controller=0)

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        assert game.state.turn_ledger.permanents_entered == []
        assert not evaluate_condition(game.state, ANOTHER_HUMAN_ENTERED, controller=0)


# ----------------------------------------------------------------------
# the filter -- "another **Human** under **your** control"
# ----------------------------------------------------------------------


class TestTheFilterAsksWhichPermanentsEntered:
    def test_a_non_human_arrival_does_not_count(self, builder):
        game = board(builder, hand=(ELF,))
        put_onto_battlefield(game, ELF)
        assert entered(game, {"controller": "you"}) == 1, "something entered"
        assert entered(game, {"controller": "you", "subtypes": ["Human"]}) == 0, (
            "and it was not a Human -- a bare per-player tally would fire the "
            "trigger off this"
        )

    def test_a_land_drop_does_not_count_as_a_creature(self, builder):
        game = board(builder, hand=("plains",))
        put_onto_battlefield(game, "plains")
        assert entered(game, {"controller": "you"}) == 1
        assert entered(game, {"controller": "you", "types": ["Creature"]}) == 0

    def test_an_opponents_human_is_not_yours(self, builder):
        game = board(builder)
        put_onto_battlefield(game, HUMAN, pid=1)

        assert entered(game, {"controller": "you"}, controller=0) == 0
        assert entered(game, {"controller": "opponent"}, controller=0) == 1
        assert entered(game, {"controller": "all"}, controller=0) == 1
        assert entered(game, {"controller": "you"}, controller=1) == 1

    def test_controller_is_the_one_it_entered_under(self, builder):
        """"Under your control" is a fact about the arrival (109.5). A creature
        stolen afterwards did not retroactively enter under the thief."""
        from automtg.engine.primitives import change_control

        game = board(builder, hand=(HUMAN,))
        oid = put_onto_battlefield(game, HUMAN)
        change_control(game.state, oid, 1)

        assert game.state.objects[oid].controller == 1
        assert entered(game, {"controller": "you"}, controller=0) == 1, (
            "it entered under you; who controls it now is a different question"
        )
        assert entered(game, {"controller": "you"}, controller=1) == 0

    def test_subtypes_are_any_of_and_types_are_all_of(self, builder):
        """Spelled exactly as `selectors.matches` spells the same clauses."""
        game = board(builder, hand=(HUMAN,))
        put_onto_battlefield(game, HUMAN)
        assert entered(game, {"controller": "you", "subtypes": ["Elf", "Human"]}) == 1
        assert entered(game, {"controller": "you", "types": ["Creature"]}) == 1
        assert entered(game, {"controller": "you", "types": ["Creature", "Artifact"]}) == 0

    def test_colors_filter_the_arrival(self, builder):
        game = board(builder, hand=(HUMAN,))
        put_onto_battlefield(game, HUMAN)
        assert entered(game, {"controller": "you", "colors": ["W"]}) == 1
        assert entered(game, {"controller": "you", "colors": ["B"]}) == 0

    def test_exclude_self_is_the_word_another(self, builder):
        """Éowyn is herself a Human, and she may well have entered this turn --
        which is the case the word "another" exists to exclude."""
        game = board(builder, hand=(MAIDEN,))
        maiden = put_onto_battlefield(game, MAIDEN)

        spec = {"controller": "you", "subtypes": ["Human"]}
        assert entered(game, spec, source=maiden) == 1, "she is a Human, and she entered"
        assert entered(game, {**spec, "exclude_self": True}, source=maiden) == 0
        assert not evaluate_condition(
            game.state, ANOTHER_HUMAN_ENTERED, controller=0, source=maiden
        )

    def test_exclude_self_drops_only_her_own_arrival(self, builder):
        game = board(builder, hand=(MAIDEN, HUMAN))
        maiden = put_onto_battlefield(game, MAIDEN)
        put_onto_battlefield(game, HUMAN)
        assert (
            entered(
                game,
                {"controller": "you", "subtypes": ["Human"], "exclude_self": True},
                source=maiden,
            )
            == 1
        )
        assert evaluate_condition(
            game.state, ANOTHER_HUMAN_ENTERED, controller=0, source=maiden
        )


# ----------------------------------------------------------------------
# the trigger, played out
# ----------------------------------------------------------------------


def to_combat(game):
    pass_until(game, lambda g: g.state.step >= Step.BEGIN_COMBAT)


class TestTheInterveningIfGatesTheTrigger:
    """The whole card, in a real game: cast a Human, reach combat, get tokens."""

    def test_nothing_entered_so_the_trigger_does_not_fire(self, builder):
        game = board(builder, mine=(MAIDEN, HUMAN, HUMAN))
        to_combat(game)
        assert count_on_battlefield(game, KNIGHT_TOKEN, 0) == 0, (
            "two Humans are on the board and neither entered this turn -- the "
            "board query would have fired here, every combat, forever"
        )

    def test_a_human_that_entered_fires_it(self, builder):
        game = board(builder, mine=(MAIDEN,), hand=(HUMAN,))
        game.apply(action_for_card(game, ActionKind.CAST, HUMAN))
        pass_until(game, lambda g: not g.state.stack)
        to_combat(game)
        assert count_on_battlefield(game, KNIGHT_TOKEN, 0) == 2

    def test_a_human_that_entered_and_died_still_fires_it(self, builder):
        """The case `exists` gets wrong in the other direction, played out."""
        game = board(builder, mine=(MAIDEN,), hand=(HUMAN,))
        game.apply(action_for_card(game, ActionKind.CAST, HUMAN))
        pass_until(game, lambda g: not g.state.stack)
        move_object(game.state, only_oid(game, HUMAN, 0), Zone.GRAVEYARD)

        to_combat(game)
        assert count_on_battlefield(game, KNIGHT_TOKEN, 0) == 2, (
            "it entered and it died; the intervening-if asks about the arrival"
        )

    def test_her_own_arrival_does_not_fire_it(self, builder):
        """"*Another* Human." She is one, and she entered this turn."""
        game = board(builder, hand=(MAIDEN,))
        put_onto_battlefield(game, MAIDEN)
        to_combat(game)
        assert count_on_battlefield(game, KNIGHT_TOKEN, 0) == 0

    def test_an_opponents_human_does_not_fire_it(self, builder):
        game = board(builder, mine=(MAIDEN,))
        put_onto_battlefield(game, HUMAN, pid=1)
        to_combat(game)
        assert count_on_battlefield(game, KNIGHT_TOKEN, 0) == 0

    def test_it_does_not_fire_again_next_turn(self, builder):
        """The wearing-off, on the card rather than on the ledger."""
        game = board(builder, mine=(MAIDEN,), hand=(HUMAN,))
        game.apply(action_for_card(game, ActionKind.CAST, HUMAN))
        pass_until(game, lambda g: not g.state.stack)
        to_combat(game)
        assert count_on_battlefield(game, KNIGHT_TOKEN, 0) == 2

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn + 1 and g.state.active_idx == 0)
        pass_until(game, lambda g: g.state.step >= Step.BEGIN_COMBAT)
        assert count_on_battlefield(game, KNIGHT_TOKEN, 0) == 2, (
            "a new turn, and no Human has entered in it"
        )

    def test_the_then_clause_counts_the_tokens_it_just_made(self, builder):
        """"Then if you control six or more Humans" -- an `if` *inside* the
        effects, because the count happens after the tokens exist.

        Three Humans on the board, a fourth arriving this turn, plus two Knight
        tokens is six. Counted before the tokens it would be four.

        The Human is put onto the battlefield rather than cast, because casting
        it hands priority back and the engine's auto-pass runs the whole combat
        trigger before a `before` measured afterwards could be taken.
        """
        game = board(builder, mine=(MAIDEN, HUMAN, HUMAN), hand=(HUMAN,))
        put_onto_battlefield(game, HUMAN)
        before = len(game.state.players[0].hand)

        to_combat(game)
        assert count_on_battlefield(game, KNIGHT_TOKEN, 0) == 2
        assert len(game.state.players[0].hand) == before + 1

    def test_five_humans_do_not_draw(self, builder):
        """The boundary: two Humans plus the maiden plus the two tokens is five."""
        game = board(builder, mine=(MAIDEN, HUMAN), hand=(HUMAN,))
        put_onto_battlefield(game, HUMAN)
        before = len(game.state.players[0].hand)

        to_combat(game)
        assert count_on_battlefield(game, KNIGHT_TOKEN, 0) == 2
        assert len(game.state.players[0].hand) == before, "five Humans is not six"


# ----------------------------------------------------------------------
# load time
# ----------------------------------------------------------------------


class TestTheFilterIsCheckedAtLoadTime:
    """A misspelled clause that loads and counts the wrong arrivals is exactly
    what the key registries exist to refuse."""

    def validate(self, spec):
        from automtg.engine.effects.values import validate_value

        validate_value({"permanents_entered_this_turn": spec}, "test")

    def test_the_printed_shape_validates(self):
        self.validate({"controller": "you", "subtypes": ["Human"], "exclude_self": True})

    def test_the_key_itself_must_be_spelled_right(self):
        from automtg.engine.effects.values import validate_value

        with pytest.raises(DslError):
            validate_value({"permanents_entered_last_turn": {"controller": "you"}}, "test")

    def test_controller_is_required(self):
        """Omitted it would silently count the opponents' arrivals too, which is
        a strictly better card and a plausible-looking one."""
        with pytest.raises(DslError):
            self.validate({"subtypes": ["Human"]})

    def test_controller_must_be_a_player_spec(self):
        with pytest.raises(DslError):
            self.validate({"controller": "your"})

    def test_unknown_clauses_are_refused(self):
        with pytest.raises(DslError):
            self.validate({"controller": "you", "keywords": ["flying"]})

    def test_an_empty_subtype_list_is_refused(self):
        with pytest.raises(DslError):
            self.validate({"controller": "you", "subtypes": []})

    def test_exclude_self_must_be_a_boolean(self):
        """`"false"` is a non-empty string, so truthiness would turn "a Human
        entered" into "another Human did"."""
        with pytest.raises(DslError):
            self.validate({"controller": "you", "exclude_self": "false"})

    def test_the_test_card_compiles(self, registry):
        assert registry.get(MAIDEN) is not None

    def test_the_shipped_commander_reads_the_ledger(self, registry):
        """The card this capability was built for, as it ships."""
        card = registry.get("eowyn_shieldmaiden")
        [ability] = [a for a in card.abilities if a.trigger is not None]
        assert ability.trigger.event == "begin_combat"
        assert "permanents_entered_this_turn" in str(ability.trigger.condition)


class TestTheFixturesThemselves:
    """Every filtering assertion above is only meaningful if the non-Human
    really is not one."""

    def test_the_bear_enters_and_is_not_a_human(self, builder):
        game = board(builder, hand=(BEAR,))
        put_onto_battlefield(game, BEAR)
        assert oids_of(game, BEAR, 0), "it is on the battlefield"
        assert entered(game, {"controller": "you"}) == 1
        assert entered(game, {"controller": "you", "subtypes": ["Human"]}) == 0
