"""A batched combat-damage trigger that fires once per damaged player.

    Parapet Thrasher — "Whenever one or more Dragons you control deal combat
    damage to an opponent, choose one … • Destroy target artifact **that
    opponent** controls. • This creature deals 4 damage to **each other
    opponent**."

`creatures_deal_combat_damage` fires once per damaging player per damage step,
which is "…to **one or more players**". The rulings on every "one or more
creatures you control deal combat damage to **a player**" card read it per seat
instead: hit two opponents in one step and the ability triggers twice, once for
each, and each firing knows which seat it is about. Without that the card has no
"that opponent" to point at — the batch folds every hit seat into one `damaged`
list — and "each other opponent" has nobody to exclude.

`per_player: true` is that reading. `triggers.collect` hands the trigger one
copy of the batch per entry in the event's `hits`, with `damaged`, `damagers`
and `defender` narrowed to one seat, so:

- two Wyrms through to the same seat are still **one** firing ("one or more");
- a Wyrm at one opponent and an Elf at another fire it only for the Wyrm's
  seat, because the filter is asked of the creatures that hit *that* seat;
- `{"binding": "defender"}` is "that player", `defending: "opponent"` is "to an
  opponent", and `{"not": {"binding": "defender"}, "except": "you"}` is "each
  other opponent".

The unflagged batch trigger (`t_bcd_flock`) is kept live as the contrast: the
same split swing draws it one card, not two.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, only_oid, pass_until

WYRM = "t_bcd_wyrm"  # 2/2 Wyrm
ELF = "t_bcd_elf"  # 1/1 Elf, which the Wyrm filter does not name
BATCH = "t_bcd_flock"  # the unflagged batch trigger: "to one or more players"
DRAW = "t_ppc_draw"  # per_player: draw a card
DRAIN = "t_ppc_drain"  # "that player loses 5 life"
OTHERS = "t_ppc_others"  # "4 damage to each other opponent"
SHATTER = "t_ppc_shatter"  # "destroy target artifact that opponent controls"
ARTIFACT = "sol_ring"


def pod(builder, *, mine=(), artifacts=False):
    """Three seats: we are 0, swinging at 1 and 2."""
    theirs = [ARTIFACT] if artifacts else []
    return (
        builder(players=3)
        .battlefield(0, ["swamp"] * 5 + list(mine))
        .battlefield(1, list(theirs))
        .battlefield(2, list(theirs))
        .hand(0, [])
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def swing(game, plan: dict[int, int]) -> None:
    """Declare each attacker (oid) at its seat, then run past combat damage."""
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    for attacker, seat in plan.items():
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == attacker
                and any(ref.kind == "player" and ref.id == seat for ref in a.targets)
            )
        )
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    pass_until(game, lambda g: (g.state.turn, g.state.step) >= mark)


def wyrms(game) -> list[int]:
    return oids_of(game, WYRM, 0)


class TestOnceForEachSeat:
    def test_two_opponents_hit_is_two_firings(self, builder):
        game = pod(builder, mine=[DRAW, WYRM, WYRM])
        first, second = wyrms(game)
        before = len(game.state.players[0].hand)
        swing(game, {first: 1, second: 2})
        assert len(game.state.players[0].hand) - before == 2

    def test_the_unflagged_batch_is_one_firing_for_the_same_swing(self, builder):
        """The contrast: "to one or more players" is one trigger for the batch."""
        game = pod(builder, mine=[BATCH, WYRM, WYRM])
        first, second = wyrms(game)
        before = len(game.state.players[0].hand)
        swing(game, {first: 1, second: 2})
        assert len(game.state.players[0].hand) - before == 1

    def test_two_wyrms_at_one_seat_are_still_one_firing(self, builder):
        """"One or more", per seat: the per-connection reading would draw two."""
        game = pod(builder, mine=[DRAW, WYRM, WYRM])
        first, second = wyrms(game)
        before = len(game.state.players[0].hand)
        swing(game, {first: 1, second: 1})
        assert len(game.state.players[0].hand) - before == 1

    def test_the_filter_is_asked_of_the_creatures_that_hit_that_seat(self, builder):
        """A Wyrm at seat 1 and an Elf at seat 2 are one firing, not two: the
        Elf is not "one or more Wyrms" for seat 2."""
        game = pod(builder, mine=[DRAIN, WYRM, ELF])
        swing(game, {only_oid(game, WYRM, 0): 1, only_oid(game, ELF, 0): 2})
        assert game.state.players[1].life == 40 - 2 - 5
        assert game.state.players[2].life == 40 - 1


class TestThatOpponent:
    def test_the_bound_seat_is_the_one_that_was_hit(self, builder):
        game = pod(builder, mine=[DRAIN, WYRM])
        swing(game, {only_oid(game, WYRM, 0): 2})
        assert game.state.players[2].life == 40 - 2 - 5
        assert game.state.players[1].life == 40

    def test_each_firing_binds_its_own_seat(self, builder):
        game = pod(builder, mine=[DRAIN, WYRM, WYRM])
        first, second = wyrms(game)
        swing(game, {first: 1, second: 2})
        assert game.state.players[1].life == 40 - 2 - 5
        assert game.state.players[2].life == 40 - 2 - 5

    def test_target_artifact_that_opponent_controls(self, builder):
        """Seat 1's artifact is a legal target for `controller: "opponent"`, and
        is not one here: the only artifact the trigger may point at is the hit
        seat's."""
        game = pod(builder, mine=[SHATTER, WYRM], artifacts=True)
        swing(game, {only_oid(game, WYRM, 0): 2})
        assert oids_of(game, ARTIFACT, 1)
        assert not oids_of(game, ARTIFACT, 2)
        assert any(
            game.state.objects[o].def_id == ARTIFACT for o in game.state.players[2].graveyard
        )


class TestEachOtherOpponent:
    def test_the_other_opponent_is_dealt_damage_and_nobody_else(self, builder):
        game = pod(builder, mine=[OTHERS, WYRM])
        swing(game, {only_oid(game, WYRM, 0): 1})
        assert game.state.players[1].life == 40 - 2
        assert game.state.players[2].life == 40 - 4
        assert game.state.players[0].life == 40

    def test_hitting_both_burns_each_for_the_other(self, builder):
        game = pod(builder, mine=[OTHERS, WYRM, WYRM])
        first, second = wyrms(game)
        swing(game, {first: 1, second: 2})
        assert game.state.players[1].life == 40 - 2 - 4
        assert game.state.players[2].life == 40 - 2 - 4
        assert game.state.players[0].life == 40


class TestTheLoader:
    def compile(self, trigger: dict):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "x",
                    "name": "X",
                    "types": ["Enchantment"],
                    "abilities": [
                        {
                            "kind": "triggered",
                            "text": "…",
                            "trigger": trigger,
                            "effects": [
                                {"op": "draw", "player": "you", "amount": {"const": 1}}
                            ],
                        }
                    ],
                }
            )
        )

    def test_per_player_elsewhere_is_refused(self):
        """Only the batch has seats to fan out over; anywhere else the flag
        would load and say nothing."""
        with pytest.raises(DslError, match="per_player"):
            self.compile({"event": "deals_combat_damage_to_player", "per_player": True})

    def test_per_player_with_or_battle_is_refused(self):
        """Each copy carries one seat and no battles, so the battle half would
        never fire."""
        with pytest.raises(DslError, match="or_battle"):
            self.compile(
                {"event": "creatures_deal_combat_damage", "per_player": True, "or_battle": True}
            )

    def test_defending_on_the_whole_batch_is_refused(self):
        """The unsplit batch names no one seat, so `defending` would match
        nothing, ever."""
        with pytest.raises(DslError, match="defending"):
            self.compile({"event": "creatures_deal_combat_damage", "defending": "opponent"})

    def test_defending_on_a_per_player_firing_is_accepted(self):
        assert self.compile(
            {"event": "creatures_deal_combat_damage", "per_player": True, "defending": "opponent"}
        )

