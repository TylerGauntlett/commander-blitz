"""A player dealt combat damage by *three or more* Pirates -- Admiral Beckett Brass.

"At the beginning of your end step, gain control of target nonland permanent
controlled by a player who was dealt combat damage by **three or more Pirates**
this turn." A count of distinct creatures per seat, asked after `state.combat`
has gone. `{"dealt_combat_damage_by": {"subtypes": ["Pirate"]}}` is the near
miss: its seat set (`TurnLedger.players_dealt_combat_damage_by_subtype`) says
only that *a* Pirate got through, so one Pirate would unlock the steal -- a
much stronger card.

So `TurnLedger.combat_damagers_by_subtype` (subtype -> seat -> dealers), folded
off COMBAT_DAMAGE_TO_PLAYER from the attacker's derived subtypes as the damage
lands, and the subject takes `"at_least": N`. What that has to mean:

- **Distinct creatures, per seat.** Three Pirates on one player count; three
  split across two players do not; one Pirate hitting twice (two combats, or
  first strike and double strike) is one Pirate.
- **400.7.** A Pirate that hit, left and came back is a new object: the old one
  still counts, and the new one hitting again is a second Pirate.
- **Combat damage only**, and it wears off with the ledger.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import select_players
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_player
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until

ADMIRAL = "t_dcc_admiral"  # the end-step steal, on an enchantment
PIRATE = "t_bpd_pirate"  # 2/2 Pirate
BEAR = "t_bear"  # 2/2, not a Pirate
SPEC = {"dealt_combat_damage_by": {"subtypes": ["Pirate"], "at_least": 3}}


def board(builder, mine: list[str], *, players: int = 3):
    """Player 0 with ``ADMIRAL`` and ``mine``; every opponent has a Bear."""
    b = (
        builder(players=players)
        .battlefield(0, [ADMIRAL, *mine])
        .library(0, ["mountain"] * 10)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid in range(1, players):
        b.battlefield(pid, [BEAR])
        b.library(pid, ["mountain"] * 10)
    return b.build()


def oids(game, card: str, pid: int = 0) -> list[int]:
    return sorted(o.oid for o in game.state.battlefield_objects(pid) if o.def_id == card)


def seats(game) -> list[int]:
    return select_players(EffectContext(state=game.state, controller=0, source_oid=None), SPEC)


def hit(game, pid: int, *dealers: int, combat: bool = True) -> None:
    for oid in dealers:
        damage_player(game.state, pid, 1, oid, is_combat=combat)


class TestTheCount:
    def test_three_pirates_on_one_player_count(self, builder):
        game = board(builder, [PIRATE] * 3)
        hit(game, 1, *oids(game, PIRATE))
        assert seats(game) == [1]

    def test_two_pirates_do_not(self, builder):
        game = board(builder, [PIRATE] * 3)
        hit(game, 1, *oids(game, PIRATE)[:2])
        assert seats(game) == []

    def test_three_pirates_split_across_two_players_do_not(self, builder):
        game = board(builder, [PIRATE] * 3)
        a, b, c = oids(game, PIRATE)
        hit(game, 1, a, b)
        hit(game, 2, c)
        assert seats(game) == []

    def test_one_pirate_hitting_three_times_is_one_pirate(self, builder):
        game = board(builder, [PIRATE] * 3)
        a = oids(game, PIRATE)[0]
        hit(game, 1, a, a, a)
        assert seats(game) == []

    def test_a_non_pirate_is_not_one_of_them(self, builder):
        game = board(builder, [PIRATE, PIRATE, BEAR])
        hit(game, 1, *oids(game, PIRATE), only_oid(game, BEAR, 0))
        assert seats(game) == []

    def test_noncombat_damage_does_not_count(self, builder):
        game = board(builder, [PIRATE] * 3)
        hit(game, 1, *oids(game, PIRATE), combat=False)
        assert seats(game) == []

    def test_it_is_cleared_with_the_ledger(self, builder):
        game = board(builder, [PIRATE] * 3)
        hit(game, 1, *oids(game, PIRATE))
        game.state.turn_ledger.clear()
        assert seats(game) == []


class TestANewObjectIsANewPirate:
    def test_the_returned_pirate_counts_again_and_the_old_one_still_counts(self, builder):
        """400.7: the oid comes back as a new object, so two hits from "it"
        are two Pirates -- the one that left still dealt its damage."""
        game = board(builder, [PIRATE] * 2)
        a, b = oids(game, PIRATE)
        hit(game, 1, a, b)
        game.state.turn_ledger.retire_combat_damager(a)
        assert seats(game) == []
        hit(game, 1, a)
        assert seats(game) == [1]

    def test_retiring_an_oid_that_dealt_nothing_changes_nothing(self, builder):
        game = board(builder, [PIRATE] * 3)
        a, b, c = oids(game, PIRATE)
        hit(game, 1, a, b)
        game.state.turn_ledger.retire_combat_damager(c)
        assert game.state.turn_ledger.retired_combat_damagers == 0


def swing_to_end_step(game, attackers: dict[int, int]) -> None:
    """Attack with ``attackers`` (oid -> seat), nobody blocks, and play on into
    the next turn with every decision defaulted."""
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    for oid, seat in attackers.items():
        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(seat),))
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    turn = game.state.turn
    # The steal is permanent, so the next turn reads it -- and by then the
    # ledger has been cleared, which is the end step's question answered once.
    pass_until(game, lambda g: g.state.turn != turn)


class TestTheEndStepSteal:
    def test_three_pirates_through_unlock_the_steal(self, builder):
        game = board(builder, [PIRATE] * 3)
        bear = only_oid(game, BEAR, 1)
        swing_to_end_step(game, {oid: 1 for oid in oids(game, PIRATE)})
        assert game.state.players[1].life == 40 - 6
        assert game.state.objects[bear].controller == 0

    def test_two_pirates_through_leave_nothing_to_target(self, builder):
        game = board(builder, [PIRATE] * 3)
        bear1, bear2 = only_oid(game, BEAR, 1), only_oid(game, BEAR, 2)
        a, b, c = oids(game, PIRATE)
        swing_to_end_step(game, {a: 1, b: 1, c: 2})
        assert game.state.objects[bear1].controller == 1
        assert game.state.objects[bear2].controller == 2


def _model(subject) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Probe.",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "Probe.",
                    "trigger": {"event": "end_step", "controller": "you"},
                    "effects": [
                        {
                            "op": "draw",
                            "player": {"dealt_combat_damage_by": subject},
                            "amount": {"const": 1},
                        }
                    ],
                }
            ],
        }
    )


class TestTheLoader:
    def test_at_least_loads_beside_subtypes(self):
        compile_card(_model({"subtypes": ["Pirate"], "at_least": 3}))

    @pytest.mark.parametrize("bad", [0, -1, True, "3", 2.5])
    def test_at_least_must_be_a_positive_whole_number(self, bad):
        with pytest.raises(DslError, match="at_least"):
            compile_card(_model({"subtypes": ["Pirate"], "at_least": bad}))

    def test_at_least_needs_subtypes(self):
        with pytest.raises(DslError):
            compile_card(_model({"at_least": 3}))
