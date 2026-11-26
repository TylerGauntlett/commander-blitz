"""`modified` in a trigger's filter -- "whenever a modified creature you control…".

    "Whenever one or more modified creatures you control attack, untap all
    modified creatures you control…"            -- Akki Battle Squad
    "Whenever enchanted creature or another modified creature you control dies,
    create X 1/1 colorless Spirit creature tokens…"   -- One with the Kami

700.9: a permanent is modified when it has a counter on it, is equipped, or is
enchanted by an Aura its controller controls. The effect selector and a static's
filter had the word; a trigger filter did not, and `has_counters` with
`enchanted_by` misses the Equipment limb, which no trigger filter key reaches.

Two readings, because a trigger's subject may already be gone:

- **Live**, on an attack: `characteristics.is_modified_printed` asked with the
  creature's *own* controller, as the definition says.
- **Look-back**, on a departure: `zones._detach_all` has stripped its
  attachments and `reset_permanent_state` its counters before DIES goes out, so
  the board answers "not modified" of every dead creature. `zones.move_object`
  snapshots 700.9 as it leaves (`was_modified`, already folded into the turn
  ledger), and `triggers.departed_modified` hands that to the filter (603.10a).

`t_mt_mourner` and `t_mt_drummer` are the two witnesses' triggers alone,
gaining 1 life so the test reads a life total.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import destroy, move_object
from tests.conftest import find_action, only_oid, pass_until, settle

MOURNER = "t_mt_mourner"  # whenever a modified creature you control dies, gain 1
DRUMMER = "t_mt_drummer"  # whenever a modified creature you control attacks, gain 1
AURA = "t_eb_aura"  # Enchant creature, nothing else
BEAR = "t_eb_bear"
CUB = "t_eb_cub"
GEAR = "t_plain_gear"  # an Equipment with nothing printed
SWAMP = "swamp"


def position(builder, watcher, *, mine=(), theirs=()):
    """Player 0's watcher beside its Bear and Cub; ``mine`` and ``theirs`` are
    Auras and Equipment attached to the Bear before the game advances, so the
    state-based action that bins an unattached Aura never sees one. Returns
    ``(game, bear, cub)``."""
    b = builder(players=2).battlefield(0, [watcher, BEAR, CUB, *mine])
    b.battlefield(1, list(theirs))
    for pid in range(2):
        b.library(pid, [SWAMP] * 20)
    game = b.active(0).step(Step.PRECOMBAT_MAIN).build(advance=False)
    bear, cub = only_oid(game, BEAR, 0), only_oid(game, CUB, 0)
    for oid in list(game.state.battlefield):
        if game.state.objects[oid].def_id in (AURA, GEAR):
            assert attach(game.state, oid, bear)
    game._advance()
    return game, bear, cub


def life(game) -> int:
    return game.state.players[0].life


def dies(game, oid: int) -> int:
    """Destroy ``oid``, let the triggers resolve, and say how much life came of it."""
    before = life(game)
    destroy(game.state, oid, cause="test")
    settle(game)
    return life(game) - before


def attacks(game, *oids: int) -> int:
    """Declare ``oids`` at player 1, let the triggers resolve, and say how much
    life came of it."""
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    before = life(game)
    for oid in oids:
        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),))
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    settle(game)
    return life(game) - before


class TestADeathIsReadAsItLeft:
    def test_a_counter(self, builder):
        game, bear, _ = position(builder, MOURNER)
        game.state.objects[bear].add_counter("stun", 1)
        assert dies(game, bear) == 1

    def test_an_equipment_whoever_controls_it(self, builder):
        game, bear, _ = position(builder, MOURNER, theirs=(GEAR,))
        assert dies(game, bear) == 1

    def test_your_aura(self, builder):
        game, bear, _ = position(builder, MOURNER, mine=(AURA,))
        assert dies(game, bear) == 1

    def test_an_opponents_aura_is_not_a_modification(self, builder):
        game, bear, _ = position(builder, MOURNER, theirs=(AURA,))
        assert dies(game, bear) == 0

    def test_a_bare_creature(self, builder):
        game, _, cub = position(builder, MOURNER, mine=(AURA,))
        assert dies(game, cub) == 0

    def test_leaving_another_way_is_not_dying(self, builder):
        game, bear, _ = position(builder, MOURNER, mine=(AURA,))
        move_object(game.state, bear, Zone.EXILE)
        settle(game)
        assert life(game) == 40


class TestAnAttackIsReadLive:
    def test_a_modified_attacker(self, builder):
        game, bear, _ = position(builder, DRUMMER, mine=(GEAR,))
        assert attacks(game, bear) == 1

    def test_a_bare_attacker(self, builder):
        game, _, cub = position(builder, DRUMMER, mine=(GEAR,))
        assert attacks(game, cub) == 0

    def test_an_opponents_aura_does_not_modify_the_attacker(self, builder):
        game, bear, _ = position(builder, DRUMMER, theirs=(AURA,))
        assert attacks(game, bear) == 0


def _card(filt) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_mt_probe",
            "name": "Probe",
            "oracle_text": "",
            "mana_cost": "{R}",
            "types": ["Enchantment"],
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "",
                    "trigger": {"event": "dies", "controller": "you", "filter": filt},
                    "effects": [{"op": "gain_life", "amount": 1}],
                }
            ],
        }
    )


class TestTheLoader:
    def test_the_key_loads(self):
        compile_card(_card({"types": ["Creature"], "modified": True}))

    def test_inside_any_of(self):
        compile_card(_card({"any_of": [{"modified": True}, {"is_token": True}]}))

    @pytest.mark.parametrize("value", [False, {"counter": "+1/+1"}])
    def test_true_only(self, value):
        with pytest.raises(DslError, match="modified"):
            compile_card(_card({"types": ["Creature"], "modified": value}))
