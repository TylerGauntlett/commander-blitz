"""`modified_creatures_died_this_turn` -- the deaths that were modified as they happened.

"At the beginning of each end step, if a modified creature died under your
control this turn, create a 2/1 white and black Inkling creature token with
flying" (Intermediate Chirography, level 3). Rule 700.9: a permanent is
modified if it has one or more counters on it, is equipped, or is enchanted by
an Aura its controller controls. The question is asked at the end step about a
creature that may have died hours of game time earlier, and by then every limb
is gone: `zones._detach_all` has unattached its Equipment and Auras and
`reset_permanent_state` has emptied its counters. The `modified` selector key
reads the board and answers false of every dead creature, and
`creatures_died_this_turn` counts a bare token dying as readily as a creature
wearing three Auras.

`zones.move_object` therefore answers 700.9 from the departure's own
snapshots -- `had_counters`, `had_auras` measured against the creature's
controller, and the Equipment attached as it left (`zones._equipment_had`,
which keeps an Equipment that left earlier in the same simultaneous event in
`GameState.leaving_equipment`, as `leaving_auras` does for Auras) -- and puts
the answer on DIES as `was_modified`. `GameState._tally` folds it into
`TurnLedger.modified_creatures_died`, keyed by the controller the creature died
under, beside `creatures_died`.

The witness is Intermediate Chirography. `t_md_scribe` is its level-3 trigger
alone, gaining 1 life so the test reads a life total.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.zones import destroy, move_object
from tests.conftest import only_oid, pass_until, static_probe

SCRIBE = "t_md_scribe"  # Intermediate Chirography's level-3 trigger alone
AURA = "t_eb_aura"  # Enchant creature, and nothing else
BEAR = "t_eb_bear"
CUB = "t_eb_cub"
GEAR = "t_plain_gear"  # an Equipment with nothing printed
SWAMP = "swamp"


def position(builder, *, mine=(), theirs=(), watcher=None, hand=()):
    """Player 0's Bear wearing ``mine`` (player 0's) and ``theirs`` (player 1's),
    beside player 0's bare Cub, frozen in player 0's precombat main phase.

    Attached before the position advances, so the state-based action that bins
    an unattached Aura never sees one. Returns ``(game, bear, cub)``.
    """
    b = builder(players=2).battlefield(0, [BEAR, CUB, *mine])
    if watcher:
        b.battlefield(0, [watcher])
    if theirs:
        b.battlefield(1, list(theirs))
    if hand:
        b.hand(0, list(hand))
    for pid in range(2):
        b.library(pid, [SWAMP] * 20)
    game = b.active(0).step(Step.PRECOMBAT_MAIN).build(advance=False)
    bear, cub = only_oid(game, BEAR, 0), only_oid(game, CUB, 0)
    for oid in list(game.state.battlefield):
        if game.state.objects[oid].def_id in (AURA, GEAR):
            assert attach(game.state, oid, bear)
    return game, bear, cub


def modified_died(game) -> dict[int, int]:
    return game.state.turn_ledger.modified_creatures_died


class TestTheThreeLimbs:
    def test_a_counter_of_any_kind_modifies_it(self, builder):
        game, bear, _ = position(builder)
        game.state.objects[bear].add_counter("stun", 1)
        destroy(game.state, bear, cause="test")
        assert modified_died(game) == {0: 1}

    def test_an_equipment_modifies_it_whoever_controls_the_equipment(self, builder):
        """"Equipped" asks what is attached, not whose it is."""
        game, bear, _ = position(builder, theirs=(GEAR,))
        destroy(game.state, bear, cause="test")
        assert modified_died(game) == {0: 1}

    def test_an_aura_its_controller_controls_modifies_it(self, builder):
        game, bear, _ = position(builder, mine=(AURA,))
        destroy(game.state, bear, cause="test")
        assert modified_died(game) == {0: 1}

    def test_an_opponents_aura_does_not(self, builder):
        """The one asymmetric limb: an opponent's Pacifism modifies nothing."""
        game, bear, _ = position(builder, theirs=(AURA,))
        destroy(game.state, bear, cause="test")
        assert modified_died(game) == {}
        assert game.state.turn_ledger.creatures_died == {0: 1}

    def test_a_bare_creature_is_not_modified(self, builder):
        game, _, cub = position(builder, mine=(AURA,))
        destroy(game.state, cub, cause="test")
        assert modified_died(game) == {}
        assert game.state.turn_ledger.creatures_died == {0: 1}


class TestWhoseControl:
    def test_a_stolen_creature_is_measured_against_the_thief(self, builder):
        """Died under player 1's control, so player 0's Aura no longer counts
        and the death is player 1's."""
        game, bear, _ = position(builder, mine=(AURA,))
        game.state.objects[bear].controller = 1
        destroy(game.state, bear, cause="test")
        assert modified_died(game) == {}
        assert game.state.turn_ledger.creatures_died == {1: 1}

    def test_the_thiefs_own_aura_modifies_it(self, builder):
        game, bear, _ = position(builder, theirs=(AURA,))
        game.state.objects[bear].controller = 1
        destroy(game.state, bear, cause="test")
        assert modified_died(game) == {1: 1}


class TestWhatIsNotAModifiedDeath:
    def test_exile_is_not_dying(self, builder):
        game, bear, _ = position(builder, mine=(AURA,))
        move_object(game.state, bear, Zone.EXILE)
        assert modified_died(game) == {}

    def test_a_modified_noncreature_dying_is_not_a_creature(self, builder):
        game, _, _ = position(builder, mine=(AURA,))
        aura = only_oid(game, AURA, 0)
        game.state.objects[aura].add_counter("charge", 1)
        destroy(game.state, aura, cause="test")
        assert modified_died(game) == {}


class TestTheSimultaneousEvent:
    def test_equipment_leaving_in_the_same_event_is_still_attached(self, builder):
        """A "destroy all nonland permanents" may reach the Equipment first;
        within one simultaneous event its host was still equipped (603.10a)."""
        game, bear, _ = position(builder, mine=(GEAR,))
        destroy(game.state, only_oid(game, GEAR, 0), cause="test")
        destroy(game.state, bear, cause="test")
        assert modified_died(game) == {0: 1}

    def test_equipment_that_left_in_an_earlier_event_is_not(self, builder):
        game, bear, _ = position(builder, mine=(GEAR,))
        destroy(game.state, only_oid(game, GEAR, 0), cause="test")
        game.state.event_batch += 1
        destroy(game.state, bear, cause="test")
        assert modified_died(game) == {}

    def test_an_aura_leaving_in_the_same_event_is_still_attached(self, builder):
        game, bear, _ = position(builder, mine=(AURA,))
        destroy(game.state, only_oid(game, AURA, 0), cause="test")
        destroy(game.state, bear, cause="test")
        assert modified_died(game) == {0: 1}


class TestTheValue:
    @pytest.mark.parametrize(
        ("spec", "controller", "expected"),
        [("you", 0, 1), ("you", 1, 0), ("each_opponent", 1, 1), ("all", 1, 1)],
    )
    def test_it_sums_over_the_named_players(self, builder, spec, controller, expected):
        game, bear, _ = position(builder, mine=(AURA,))
        destroy(game.state, bear, cause="test")
        ctx = EffectContext(game.state, controller=controller, source_oid=None)
        assert evaluate_value(ctx, {"modified_creatures_died_this_turn": spec}) == expected

    def test_cleanup_empties_it(self, builder):
        game, bear, _ = position(builder, mine=(AURA,))
        destroy(game.state, bear, cause="test")
        game.state.turn_ledger.clear()
        assert modified_died(game) == {}


def through_the_end_step(game) -> None:
    """Play out the rest of player 0's turn -- its end step included -- and stop
    as turn 2 begins, before another end step can ask again."""
    game._advance()
    pass_until(game, lambda g: g.state.turn >= 2)


class TestTheEndStepTrigger:
    def life(self, game) -> int:
        return game.state.players[0].life

    def test_a_modified_death_earlier_in_the_turn_answers_it(self, builder):
        game, bear, _ = position(builder, mine=(AURA,), watcher=SCRIBE)
        before = self.life(game)
        destroy(game.state, bear, cause="test")
        through_the_end_step(game)
        assert self.life(game) == before + 1

    def test_a_bare_death_does_not(self, builder):
        game, _, cub = position(builder, mine=(AURA,), watcher=SCRIBE)
        before = self.life(game)
        destroy(game.state, cub, cause="test")
        through_the_end_step(game)
        assert self.life(game) == before

    def test_the_death_need_not_be_witnessed_by_the_scribe(self, builder):
        """The ledger counts the turn, not the time the reader was around:
        a modified creature that died before the Class reached level 3 still
        died this turn."""
        game, bear, _ = position(builder, mine=(GEAR,), hand=(SCRIBE,))
        destroy(game.state, bear, cause="test")
        (scribe,) = game.state.players[0].hand
        move_object(game.state, scribe, Zone.BATTLEFIELD)
        before = self.life(game)
        through_the_end_step(game)
        assert self.life(game) == before + 1


def _compile(amount) -> None:
    ability = {
        "kind": "triggered",
        "text": "Probe.",
        "trigger": {
            "event": "end_step",
            "controller": "any",
            "condition": {"cmp": ">=", "left": amount, "right": {"const": 1}},
        },
        "effects": [{"op": "gain_life", "amount": 1}],
    }
    compile_card(CardModel.model_validate(static_probe({}) | {"abilities": [ability]}))


class TestTheLoader:
    @pytest.mark.parametrize("spec", ["you", "all", "each_opponent"])
    def test_a_player_spec_loads(self, spec):
        _compile({"modified_creatures_died_this_turn": spec})

    @pytest.mark.parametrize("spec", ["nobody", 3, True])
    def test_anything_else_is_refused(self, spec):
        with pytest.raises(DslError, match="modified_creatures_died_this_turn"):
            _compile({"modified_creatures_died_this_turn": spec})
