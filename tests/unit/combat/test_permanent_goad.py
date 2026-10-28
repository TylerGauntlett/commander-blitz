"""Goad "for the rest of the game": the second clock, and a mark that outlives control.

Dack Fayden, Helping Hand -- "…Put those creature cards onto the battlefield,
then shuffle. They're goaded for the rest of the game. For each of those
permanents, choose a different opponent. Each opponent gains control of the
permanent for which they were chosen."

Rule 701.15a (goad) gives a goad "until your next turn" and `turn._untap_step`
clears the goader's marks there. A goad with no clock is the same mark that
step must leave alone, so it lives in `GameObject.goaded_permanently_by`, a
subset of `goaded_by` that `clear_goad` spares. Without it Dack's creatures stop
being goaded the moment he untaps, and the card is a worse political card for
every turn after the first.

The mark is the **goader's**, whoever controls the creature. Dack goads
creatures his own controller has just put onto the battlefield, then gives them
away: the goad has to be recorded while he still controls them -- which a timed
goad refuses as vacuous -- so that each opponent's new creature must attack a
player other than Dack's controller.

"The rest of the game" is the goader's game. When the goader leaves, 800.4a ends
what that player's effects did; a mark nobody could clear would compel the
creature every combat while its target restriction pointed at a seat `alive()`
never offers again. So `sba` clears it with `clear_goad(..., leaving=True)`. And
400.7 still ends it when the creature leaves the battlefield.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine import sba
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import change_control
from commanderblitz.engine.temp_effects import clear_goad, goad_creature
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until
from tests.unit.combat.test_goad import (
    BEAR,
    cast,
    defenders_offered,
    position,
    probe,
    to_declare_attackers,
)

LASTING = "t_pg_goader"


class TestTheUntapStepLeavesItAlone:
    def test_it_survives_the_goaders_untap_step(self, builder):
        game = position(builder, active=0)
        bear = only_oid(game, BEAR, 1)
        assert goad_creature(game.state, bear, 0, permanent=True)
        pass_until(game, lambda g: g.state.active_player == 0 and g.state.turn >= 4)
        assert game.state.objects[bear].goaded_by == {0}, "player 0 untapped and it stayed"
        assert game.state.objects[bear].goaded_permanently_by == {0}

    def test_a_timed_goad_beside_it_still_wears_off(self, builder):
        """The two clocks are per goader: player 2's ordinary goad ends at player
        2's untap step while player 0's lasting one stands."""
        game = position(builder, active=0)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0, permanent=True)
        goad_creature(game.state, bear, 2)
        clear_goad(game.state, 2)
        clear_goad(game.state, 0)
        assert game.state.objects[bear].goaded_by == {0}

    def test_it_compels_every_later_turn(self, builder):
        game = position(builder, active=0)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0, permanent=True)
        pass_until(game, lambda g: g.state.active_player == 1 and g.state.turn >= 5)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]
        assert defenders_offered(game, bear) == [2]


class TestATimedAndALastingGoadMeet:
    def test_a_lasting_goad_upgrades_a_timed_one(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        assert goad_creature(game.state, bear, 0, permanent=True), "the clock was lifted"
        clear_goad(game.state, 0)
        assert game.state.objects[bear].goaded_by == {0}

    def test_a_timed_goad_adds_nothing_to_a_lasting_one(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0, permanent=True)
        assert not goad_creature(game.state, bear, 0)
        assert not goad_creature(game.state, bear, 0, permanent=True)
        assert game.state.objects[bear].goaded_permanently_by == {0}


class TestTheMarkOutlivesControl:
    """Dack's order of operations: goad what you control, then give it away."""

    def test_a_lasting_goad_marks_a_creature_its_goader_controls(self, builder):
        game = position(builder, mine=(BEAR,), active=0, theirs=())
        mine = only_oid(game, BEAR, 0)
        assert not goad_creature(game.state, mine, 0), "a timed one is still refused"
        assert goad_creature(game.state, mine, 0, permanent=True)
        assert game.state.objects[mine].goaded_by == {0}

    def test_handed_to_an_opponent_it_attacks_around_the_goader(self, builder):
        game = position(builder, mine=(BEAR,), active=0, theirs=())
        mine = only_oid(game, BEAR, 0)
        goad_creature(game.state, mine, 0, permanent=True)
        assert change_control(game.state, mine, 1)
        assert game.state.objects[mine].goaded_by == {0}, "control changed, the mark did not"
        pass_until(game, lambda g: g.state.active_player == 1)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [mine]
        assert defenders_offered(game, mine) == [2], "player 0 goaded it"

    def test_back_under_its_goader_it_still_attacks_each_combat(self, builder):
        """701.15a's compulsion names no controller: a creature goaded for the
        rest of the game attacks each combat if able, whoever has it."""
        game = position(builder, mine=(BEAR,), active=0, theirs=())
        mine = only_oid(game, BEAR, 0)
        goad_creature(game.state, mine, 0, permanent=True)
        game.state.objects[mine].entered_turn = -1
        assert combat_mod.attack_required(game.state, mine)
        to_declare_attackers(game)
        assert defenders_offered(game, mine) == [1, 2]


class TestItEndsWithTheGoaderOrTheCreature:
    def test_an_eliminated_goader_takes_the_lasting_goad_with_them(self, builder):
        """800.4a. Player 1 owns the creature, so it stays when player 0 leaves --
        the case where the mark itself is the question."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0, permanent=True)
        game.state.players[0].life = 0
        sba.run(game.state)
        assert game.state.players[0].has_lost
        assert game.state.objects[bear].goaded_by == set()
        assert game.state.objects[bear].goaded_permanently_by == set()
        assert not combat_mod.attack_required(game.state, bear)

    def test_another_goaders_lasting_goad_stays(self, builder):
        game = position(builder, players=4)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0, permanent=True)
        goad_creature(game.state, bear, 2, permanent=True)
        game.state.players[0].life = 0
        sba.run(game.state)
        assert game.state.objects[bear].goaded_by == {2}
        assert game.state.objects[bear].goaded_permanently_by == {2}

    def test_leaving_the_battlefield_clears_it(self, builder):
        """400.7: the creature that comes back is a new object nobody goaded."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0, permanent=True)
        move_object(game.state, bear, Zone.HAND)
        assert game.state.objects[bear].goaded_by == set()
        assert game.state.objects[bear].goaded_permanently_by == set()


class TestTheOp:
    def test_duration_permanent_writes_a_lasting_mark(self, builder):
        game = position(builder, active=0, hand=(LASTING,))
        cast(game, LASTING)
        theirs = only_oid(game, BEAR, 1)
        assert game.state.objects[theirs].goaded_permanently_by == {0}
        pass_until(game, lambda g: g.state.active_player == 0 and g.state.turn >= 4)
        assert game.state.objects[theirs].goaded_by == {0}

    def test_the_lasting_goad_compiles(self):
        probe(
            {
                "op": "goad",
                "objects": {"controller": "opponent", "types": ["Creature"]},
                "duration": "permanent",
            }
        )

    @pytest.mark.parametrize("duration", ["this_turn", "until_your_next_turn", "forever"])
    def test_every_other_duration_is_refused(self, duration):
        with pytest.raises(DslError, match="goad takes no 'duration' but 'permanent'"):
            probe(
                {
                    "op": "goad",
                    "objects": {"controller": "opponent", "types": ["Creature"]},
                    "duration": duration,
                }
            )
