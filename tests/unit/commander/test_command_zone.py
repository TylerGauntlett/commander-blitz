"""The command zone as a place an effect can *send* a permanent.

Hellkite Courser — "When this creature enters, you may put a commander you own
from the command zone onto the battlefield. It gains haste. **Return it to the
command zone** at the beginning of the next end step."

Every zone but this one already had a mover. `return_to_hand` is the hand,
`put_onto_battlefield` the battlefield, `sacrifice` and `destroy` the graveyard,
`exile` exile, `put_on_top` either end of a library; `DESTINATIONS` names those
six and the loader validates every written `destination` against it. Nothing at
all reached a command zone, so the last clause of the Courser had nowhere to go
and the card could not be written.

**The trap, and why this test is shaped the way it is.** The one spelling that
produces the right board today is `return_to_hand` over the same binding. It
works because `zones.move_object` applies rule 903.9a — the commander
zone-change replacement — unconditionally, to every commander told to go to a
hand, a graveyard, a library or exile. So a test that only put a commander down
and read the command zone afterwards passes against the *wrong op*, and the
card's printed sentence would say "hand" for the rest of its life.

So both halves are asserted here:

- a **commander** goes home, which is the Courser's actual line of play and the
  case 903.9a would also have covered; and
- a **permanent that is nobody's commander** goes to the command zone too, which
  the replacement would never do — that is the claim that the op names the zone
  rather than borrowing a redirect.

The two do not fight, and the reason is structural rather than a guard:
`zones.COMMANDER_REPLACED_ZONES` is the four zones a commander is redirected
*out of*, and the command zone is not one of them. An object handed straight to
``Zone.COMMAND`` walks past the replacement untouched — one move, one
``ZONE_CHANGE``, one arrival. `TestItDoesNotRideTheReplacement` pins that
frozenset, because widening it to include the command zone would turn every one
of these returns into an infinite redirect onto itself.
"""

from __future__ import annotations

import pytest

from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Zone
from automtg.engine.events import EventType
from automtg.engine.zones import COMMANDER_REPLACED_ZONES
from tests.conftest import only_oid, pass_until

COURSER = "t_cz_courser"
GENERAL = "t_cz_general"
BEAR = "t_cz_bear"


def board(builder, *, with_commander: bool = True):
    """The Courser already standing, the General in the command zone.

    Placed rather than cast: `GameBuilder.battlefield` fires no enters trigger,
    which is what lets `courser_trigger` run the printed ability at a moment the
    test chooses. Both seats hold a land so `pass_until` always has a decision
    to answer — an empty hand makes whole turns roll by without stopping.
    """
    builder_ = (
        builder(players=2)
        .battlefield(0, [COURSER, BEAR])
        .hand(0, ["forest"])
        .hand(1, ["forest"])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
    )
    if with_commander:
        builder_ = builder_.commander(0, [GENERAL])
    return builder_.build()


def drive(game, effects, *, controller: int = 0, answer: int = 0):
    """Run an effect list to exhaustion, answering every question with ``answer``.

    ``0`` is "yes" to a `may` (`ask_yes_no` reads option 0 as yes) and "the
    first one" to a choice of objects, which is the only commander on offer.
    """
    state = game.state
    ctx = EffectContext(state=state, controller=controller, source_oid=only_oid(game, COURSER))
    gen = execute(ctx, effects)
    send = None
    while True:
        try:
            gen.send(send)
        except StopIteration:
            return game
        send = [answer]


def courser_trigger(game, *, answer: int = 0):
    """Resolve the Courser's printed enters ability."""
    state = game.state
    card = state.card_of(state.objects[only_oid(game, COURSER)])
    return drive(game, card.abilities[0].effects, answer=answer)


def send_the_bear_home(game):
    """The op on its own, over the one permanent that is nobody's commander."""
    return drive(
        game,
        [
            {
                "op": "return_to_command_zone",
                "objects": {"zone": "battlefield", "controller": "you", "subtypes": ["Bear"]},
            }
        ],
    )


def oid_of(game, card_id: str) -> int:
    """Find one object wherever it is.

    `conftest.only_oid` walks the battlefield only, and every claim here is
    about a card that has just left it.
    """
    found = [oid for oid, obj in game.state.objects.items() if obj.def_id == card_id]
    assert len(found) == 1, f"expected exactly one {card_id}, found {len(found)}"
    return found[0]


def run_to_next_main(game):
    """Run past the end step the delay is due at, to the next observable moment.

    An end step offers no priority in this position, so the first instant a test
    can read afterwards is the following main phase — the pattern
    `test_delay_your_turn` established.
    """
    turn = game.state.turn
    pass_until(game, lambda g: g.state.turn > turn)


def ids(oids, state):
    return sorted(state.card(o).id for o in oids)


class TestTheCourserPutsItsCommanderDown:
    def test_the_commander_leaves_the_command_zone(self, builder):
        game = courser_trigger(board(builder))
        assert game.state.players[0].command == []

    def test_it_arrives_on_the_battlefield_with_haste(self, builder):
        from automtg.engine.characteristics import chars

        game = courser_trigger(board(builder))
        general = oid_of(game, GENERAL)
        assert game.state.objects[general].zone is Zone.BATTLEFIELD
        assert "haste" in chars(game.state, general).keywords

    def test_declining_leaves_it_in_the_command_zone(self, builder):
        """The "may" is real: answering no schedules nothing at all."""
        game = courser_trigger(board(builder), answer=1)
        assert ids(game.state.players[0].command, game.state) == [GENERAL]
        assert not game.state.delayed_triggers

    def test_an_empty_command_zone_is_not_an_error(self, builder):
        """The sandbox the authoring gates cast this card in has no commander
        for player 0, so the pool the `may` offers is empty."""
        game = courser_trigger(board(builder, with_commander=False))
        assert game.state.players[0].command == []


class TestTheDelayedReturn:
    def test_it_is_scheduled_for_the_end_step(self, builder):
        game = courser_trigger(board(builder))
        assert [d.step for d in game.state.delayed_triggers] == ["end_step"]

    def test_the_commander_goes_back_at_the_end_step(self, builder):
        game = courser_trigger(board(builder))
        run_to_next_main(game)
        assert ids(game.state.players[0].command, game.state) == [GENERAL]
        assert game.state.objects[oid_of(game, GENERAL)].zone is Zone.COMMAND

    def test_it_does_not_stay_on_the_battlefield(self, builder):
        game = courser_trigger(board(builder))
        run_to_next_main(game)
        assert GENERAL not in [o.def_id for o in game.state.battlefield_objects(0)]

    def test_and_it_does_not_land_in_a_hand(self, builder):
        """`return_to_hand` over the same binding reaches the command zone by
        way of 903.9a, so the hand is the assertion that separates the two."""
        game = courser_trigger(board(builder))
        run_to_next_main(game)
        assert ids(game.state.players[0].hand, game.state) == ["forest"]


class TestTheOpNamesTheZoneItself:
    def test_a_permanent_that_is_no_commander_goes_there_too(self, builder):
        """The claim 903.9a cannot make. The Bear is nobody's commander, so a
        `return_to_hand` here would put it in a hand and stop."""
        game = send_the_bear_home(board(builder))
        assert BEAR in ids(game.state.players[0].command, game.state)
        assert game.state.objects[oid_of(game, BEAR)].zone is Zone.COMMAND

    def test_it_is_not_in_a_hand(self, builder):
        game = send_the_bear_home(board(builder))
        assert ids(game.state.players[0].hand, game.state) == ["forest"]

    def test_it_is_off_the_battlefield(self, builder):
        game = send_the_bear_home(board(builder))
        assert BEAR not in [o.def_id for o in game.state.battlefield_objects(0)]

    def test_it_is_not_castable_from_there(self, builder):
        """A card parked in a command zone that is not a commander is inert:
        `casting._cast_actions` skips every object there whose `is_commander` is
        false. Asserted rather than assumed, because the op can now put one
        there."""
        game = send_the_bear_home(board(builder))
        assert not any(
            action.source == oid_of(game, BEAR) for action in game.legal_actions()
        )

    def test_the_move_is_reported_as_one_zone_change(self, builder):
        game = send_the_bear_home(board(builder))
        bear = oid_of(game, BEAR)
        moves = [
            e
            for e in game.state.events
            if e.type == EventType.ZONE_CHANGE and e.data.get("oid") == bear
        ]
        assert [e.data["to"] for e in moves] == ["command"]
        assert moves[0].data["from"] == "battlefield"


class TestItDoesNotRideTheReplacement:
    def test_the_command_zone_is_not_a_replaced_zone(self):
        """903.9a redirects a commander *out of* four zones. Adding the command
        zone to that set would make this op redirect every return onto its own
        destination — and the redirect would then be the thing doing the work
        again, which is the failure this op exists to end."""
        assert Zone.COMMAND not in COMMANDER_REPLACED_ZONES
        assert set(COMMANDER_REPLACED_ZONES) == {
            Zone.GRAVEYARD,
            Zone.EXILE,
            Zone.HAND,
            Zone.LIBRARY,
        }

    def test_an_object_already_there_is_left_alone(self, builder):
        """What a delayed return finds when the permanent died in the meantime
        and 903.9a already put it away. Moving it onto itself would fire a
        second `ZONE_CHANGE` out of the zone it is in."""
        game = board(builder)
        general = oid_of(game, GENERAL)
        before = len(game.state.events)
        drive(game, [{"op": "return_to_command_zone", "objects": {"zone": "command"}}])
        moves = [
            e
            for e in game.state.events[before:]
            if e.type == EventType.ZONE_CHANGE and e.data.get("oid") == general
        ]
        assert moves == []
        assert ids(game.state.players[0].command, game.state) == [GENERAL]


class TestTheLoaderChecksIt:
    def test_a_return_with_nothing_selected_is_refused(self):
        """An omitted selector resolves to nothing, so the op would be a silent
        no-op: the delay fires, no permanent moves, and the commander stands on
        the battlefield for ever with nothing to say so."""
        from automtg.cards.loader import compile_card
        from automtg.cards.schema import CardModel
        from automtg.engine.errors import DslError

        with pytest.raises(DslError, match="nothing to return"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_bad_command_return",
                        "name": "Test Bad Command Return",
                        "oracle_text": "Return it to the command zone.",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "spell_effects": [{"op": "return_to_command_zone"}],
                    }
                ),
                source="test",
            )
