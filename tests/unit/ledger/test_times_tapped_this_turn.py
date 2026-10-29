"""How many times a permanent has become tapped this turn: `times_tapped_this_turn`.

    "Whenever a creature you control becomes tapped during your turn, **if
    it's the first time that creature has become tapped this turn**, untap
    it."                                  -- Captain America, Living Legend

The question is about the creature's whole turn, not about what the Captain
saw. A creature tapped for mana to cast the Captain has already become tapped
once, so its next tap is its second and stays tapped; a flag written by the
Captain's own trigger would remember only the taps it watched and untap that
creature wrongly. So the engine keeps the count itself,
`TurnLedger.taps_by_permanent`, folded off every TAPPED event from the start of
the turn whatever is on the battlefield, and the value reads it for one object.

What each reading rests on, and each has a test class:

- **"Becomes tapped"** is a TAPPED event, which `tap_permanent` fires only for
  an untapped permanent. Tapping for mana and attacking are both taps.
- **"The first time"** is a count of 1 that includes the tap that fired the
  trigger, and it is an intervening-if (603.4): asked as the event arms the
  ability and again on resolution. Untapped by the Captain and tapped again,
  the creature is on its second time and stays tapped; untapped and re-tapped
  in response, the first trigger's recheck fails too.
- **"During your turn"** is `is_your_turn`. On an opponent's turn the tap is
  still counted, but nothing untaps.
- **400.7** -- a permanent that leaves the battlefield and comes back is a new
  object, so its count starts from nought and its next tap is a first time.
- **"This turn"** -- the ledger is cleared at cleanup, so tomorrow's first tap
  is a first time again.

Captain America, Living Legend is the witness; `t_ttt_captain` in
`tests/data/times_tapped_this_turn.cards.json` is its second sentence on a {G}
1/1, so a Llanowar Elves can pay for it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import tap_permanent, untap_permanent
from commanderblitz.engine.zones import move_object
from tests.conftest import attack_with, find_action, only_oid, pass_until, settle

CAPTAIN = "t_ttt_captain"  # {G} 1/1: the first tap of your creature on your turn untaps it
ELF = "llanowar_elves"  # {T}: Add {G}
BEAR = "t_bear"  # 2/2
BOLT = "t_bolt"  # {R} instant, so priority stops while a trigger is on the stack


def position(builder, *, captain_in_hand: bool = False, theirs=(BEAR,)):
    """Player 0 with a bear and an elf (and the Captain); player 1 a bear.

    Returns ``(game, elf, bear)``, in player 0's precombat main.
    """
    mine = ["mountain", ELF, BEAR] + ([] if captain_in_hand else [CAPTAIN])
    game = (
        builder(players=2)
        .battlefield(0, mine)
        .battlefield(1, list(theirs))
        .hand(0, ([CAPTAIN] if captain_in_hand else []) + [BOLT])
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    return game, only_oid(game, ELF, 0), only_oid(game, BEAR, 0)


def taps(game, oid: int) -> int:
    return game.state.turn_ledger.taps_by_permanent.get(oid, 0)


def tapped(game, oid: int) -> bool:
    return game.state.objects[oid].tapped


def tap(game, oid: int) -> None:
    """Tap it the way every effect and cost does, then let the trigger resolve."""
    assert tap_permanent(game.state, oid)
    settle(game)


def declare(game, *oids: int) -> None:
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    for oid in oids:
        attack_with(game, oid)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


class TestTheFirstTap:
    def test_it_is_untapped(self, builder):
        game, _, bear = position(builder)
        tap(game, bear)
        assert not tapped(game, bear)
        assert taps(game, bear) == 1

    def test_attacking_is_a_tap(self, builder):
        """Declared as an attacker, the bear becomes tapped and is untapped again."""
        game, _, bear = position(builder)
        declare(game, bear)
        settle(game)
        assert not tapped(game, bear)
        assert bear in game.state.combat.attackers, "untapping does not remove it from combat"

    def test_tapping_for_mana_is_a_tap(self, builder):
        """The elf pays for a second Captain while the first one watches."""
        game = (
            builder(players=2)
            .battlefield(0, [ELF, CAPTAIN])
            .hand(0, [CAPTAIN])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        elf = only_oid(game, ELF, 0)
        game.apply(find_action(game, ActionKind.CAST, source=game.state.players[0].hand[0]))
        settle(game)
        assert not tapped(game, elf)
        assert taps(game, elf) == 1


class TestASecondTap:
    def test_a_creature_tapped_for_mana_before_the_captain_arrived(self, builder):
        """The elf pays for the Captain, so its next tap is its second."""
        game, elf, _ = position(builder, captain_in_hand=True)
        captain = game.state.players[0].hand[0]
        game.apply(find_action(game, ActionKind.CAST, source=captain))
        settle(game)
        assert game.state.objects[captain].zone is Zone.BATTLEFIELD
        assert tapped(game, elf) and taps(game, elf) == 1, "tapped with nothing watching"
        untap_permanent(game.state, elf)
        tap(game, elf)
        assert tapped(game, elf), "its second time this turn"
        assert taps(game, elf) == 2

    def test_a_second_tap_after_the_untap_stays_tapped(self, builder):
        game, _, bear = position(builder)
        tap(game, bear)
        assert not tapped(game, bear)
        tap(game, bear)
        assert tapped(game, bear)
        assert taps(game, bear) == 2

    def test_retapped_in_response_the_recheck_fails(self, builder):
        """603.4: untapped and tapped again with the trigger on the stack, the
        first trigger resolves against a count of 2 and does nothing."""
        game, _, bear = position(builder)
        assert tap_permanent(game.state, bear)
        pass_until(game, lambda g: bool(g.state.stack))
        untap_permanent(game.state, bear)
        assert tap_permanent(game.state, bear)
        settle(game)
        assert tapped(game, bear)
        assert taps(game, bear) == 2

    def test_each_creature_has_its_own_first_time(self, builder):
        """Not `max_per_turn`: the bear's first tap does not spend the elf's."""
        game, elf, bear = position(builder)
        tap(game, bear)
        tap(game, elf)
        assert not tapped(game, bear) and not tapped(game, elf)


class TestWhoseTurnAndWhoseCreature:
    def test_on_an_opponents_turn_nothing_untaps(self, builder):
        game, elf, _ = position(builder)
        pass_until(
            game,
            lambda g: g.state.active_player == 1 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        tap(game, elf)
        assert tapped(game, elf)
        assert taps(game, elf) == 1, "counted all the same"

    def test_an_opponents_creature_is_not_yours(self, builder):
        game, _, _ = position(builder)
        theirs = only_oid(game, BEAR, 1)
        tap(game, theirs)
        assert tapped(game, theirs)
        assert taps(game, theirs) == 1, "every permanent is counted, not only the Captain's"


class TestANewObject:
    def test_a_flickered_creature_starts_again(self, builder):
        """400.7: back from exile, the bear has never been tapped."""
        game, _, bear = position(builder)
        tap(game, bear)
        tap(game, bear)
        assert tapped(game, bear) and taps(game, bear) == 2
        move_object(game.state, bear, Zone.EXILE)
        assert taps(game, bear) == 0
        move_object(game.state, bear, Zone.BATTLEFIELD)
        assert not tapped(game, bear)
        tap(game, bear)
        assert not tapped(game, bear), "its first tap as the new object"


class TestTheTurnBoundary:
    def test_the_count_is_cleared_at_cleanup(self, builder):
        game, _, bear = position(builder)
        tap(game, bear)
        tap(game, bear)
        assert taps(game, bear) == 2
        pass_until(
            game,
            lambda g: g.state.active_player == 0
            and g.state.turn > 1
            and g.state.step is Step.PRECOMBAT_MAIN
            and g.state.turn_ledger.taps_by_permanent.get(bear, 0) == 0,
        )
        assert not tapped(game, bear), "untapped in the untap step"
        tap(game, bear)
        assert not tapped(game, bear), "the first time this turn"


def probe(left) -> dict:
    return {
        "id": "x_ttt_probe",
        "name": "Probe",
        "types": ["Creature"],
        "mana_cost": "{G}",
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "triggered",
                "text": "Whenever a creature you control becomes tapped, …",
                "trigger": {
                    "event": "becomes_tapped",
                    "controller": "you",
                    "condition": {"cmp": "==", "left": left, "right": {"const": 1}},
                },
                "effects": [{"op": "untap", "objects": {"binding": "subject"}}],
            }
        ],
    }


class TestTheLoader:
    @pytest.mark.parametrize(
        "ref", [{"binding": "subject"}, {"self": True}, {"target": "t1"}]
    )
    def test_an_object_reference_loads(self, ref):
        compile_card(CardModel.model_validate(probe({"times_tapped_this_turn": ref})))

    @pytest.mark.parametrize(
        "ref",
        [
            True,
            "subject",
            {},
            {"types": ["Creature"]},
            {"binding": "subject", "self": True},
            {"self": False},
            {"binding": ""},
        ],
    )
    def test_anything_else_is_refused(self, ref):
        """`true` reads like the sentence and names no object; a selector would
        read 0 for ever."""
        with pytest.raises(DslError, match="times_tapped_this_turn"):
            compile_card(CardModel.model_validate(probe({"times_tapped_this_turn": ref})))
