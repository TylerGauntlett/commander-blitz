"""Remove a creature from combat (506.4).

Observed Stasis: "When this Aura enters, remove enchanted creature from combat.
Then draw a card for each tapped creature its controller controls." Nothing a
card could say reached combat membership: `redirect_attack` moves an attack,
`tap` leaves an attacker attacking, `cant_attack` / `cant_block` shape a
declaration still to come, and the fogs stop damage while leaving the creature
attacking or blocking. `remove_from_combat` puts the creatures it names in
`CombatState.removed`, the set regeneration, phasing and a change of control
already use.

What the rules make of it, each pinned below:

- **It stops being an attacking or blocking creature** (506.4), so it deals and
  is dealt no combat damage, and a defending player nobody attacks any more is
  not asked to block.
- **What it fought stays where it was** (506.4, 509.1h): an attacker whose
  blocker is removed is still blocked, so without trample it deals no damage;
  a blocker whose attacker is removed is still blocking, and deals no damage.
- **The declaration is not undone**: the turn ledger keeps the attack, and the
  creature cannot be declared again this combat.
- **It lasts one combat**, and outside combat the op does nothing.

The witness is Observed Stasis.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import (
    _default_answer,
    attack_with,
    find_action,
    oids_of,
    only_oid,
    pass_until,
    settle,
)

STASIS = "t_rfc_stasis"
TRICK = "t_rfc_trick"
BEAR = "t_bear"
TRAMPLER = "t_trampler"


def position(builder, *, mine=(BEAR,), theirs=(), hand0=(), hand1=(STASIS,)):
    """Player 0 attacks player 1 with everything in ``mine``.

    Returns ``(game, attacker)``, the first of ``mine``, with the declaration
    finished and the game in the declare attackers step. Each seat also holds a
    spare trick, so neither auto-passes through combat once the stack is empty
    and the test can read the combat it is about.
    """
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, [*hand0, TRICK])
        .hand(1, [*hand1, TRICK])
        .build()
    )
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    attackers = [o for o in game.state.battlefield if game.state.objects[o].controller == 0]
    for oid in attackers:
        attack_with(game, oid, defender=1)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    return game, attackers[0]


def cast_on(game, player: int, card_id: str, target: int, step: Step | None = None) -> None:
    """``player`` casts ``card_id`` at ``target`` and everything resolves."""

    def castable(g):
        d = g.pending()
        return (
            d is not None
            and d.kind is DecisionKind.PRIORITY
            and d.player == player
            and (step is None or g.state.step is step)
            and _cast_action(g, card_id, target) is not None
        )

    pass_until(game, castable)
    game.apply(_cast_action(game, card_id, target))
    settle(game)


def _cast_action(game, card_id: str, target: int):
    for a in game.legal_actions():
        if (
            a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == card_id
            and TargetRef.obj(target) in (a.targets or ())
        ):
            return a
    return None


def block(game, blocker: int, attacker: int) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    game.apply(
        find_action(
            game, ActionKind.ADD_BLOCKER, source=blocker, targets=(TargetRef.obj(attacker),)
        )
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def through_damage(game) -> None:
    start = game.state.turn
    for _ in range(100):
        if game.over or game.state.turn != start or game.state.step > Step.COMBAT_DAMAGE:
            return
        decision = game.pending()
        if decision is None:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("combat did not resolve")


class TestAnAttackerRemovedBeforeBlocks:
    def test_it_is_no_longer_attacking(self, builder):
        game, bear = position(builder)
        cast_on(game, 1, STASIS, bear)
        assert not game.state.combat.attacking(bear)

    def test_it_deals_no_combat_damage(self, builder):
        game, bear = position(builder)
        cast_on(game, 1, STASIS, bear)
        through_damage(game)
        assert game.state.players[1].life == 40

    def test_its_defender_is_not_asked_to_block(self, builder):
        game, bear = position(builder, theirs=(BEAR,))
        cast_on(game, 1, STASIS, bear)
        assert game.state.combat.pending_blockers == []

    def test_a_defender_still_attacked_is_still_asked(self, builder):
        game, bear = position(builder, mine=(BEAR, BEAR), theirs=(BEAR,))
        cast_on(game, 1, STASIS, bear)
        assert game.state.combat.pending_blockers == [1]
        through_damage(game)
        assert game.state.players[1].life == 38, "only the other bear connects"

    def test_the_declaration_stands(self, builder):
        """506.4 removes it from combat; it does not un-declare the attack."""
        game, bear = position(builder)
        cast_on(game, 1, STASIS, bear)
        assert bear in game.state.turn_ledger.creatures_attacked.get(0, [])
        assert bear in game.state.combat.attackers, "so it cannot be declared again"


class TestTheDrawHalf:
    def test_one_card_per_tapped_creature_its_controller_controls(self, builder):
        game, bear = position(builder, mine=(BEAR, BEAR))
        hand = len(game.state.players[1].hand)
        cast_on(game, 1, STASIS, bear)
        # The Aura leaves the hand; both attackers are tapped.
        assert len(game.state.players[1].hand) == hand - 1 + 2


class TestAfterBlocks:
    def test_a_removed_attacker_leaves_its_blocker_blocking_and_unhurt(self, builder):
        game, trampler = position(builder, mine=(TRAMPLER,), theirs=(BEAR,), hand1=(TRICK,))
        blocker = only_oid(game, BEAR, 1)
        block(game, blocker, trampler)
        cast_on(game, 1, TRICK, trampler, step=Step.DECLARE_BLOCKERS)
        combat = game.state.combat
        assert not combat.attacking(trampler)
        assert combat.blocking(blocker), "509.1h: it remains a blocking creature"
        through_damage(game)
        assert blocker in game.state.battlefield
        assert game.state.objects[trampler].damage == 0
        assert game.state.players[1].life == 40

    def test_a_removed_blocker_leaves_its_attacker_blocked(self, builder):
        game, bear = position(builder, theirs=(BEAR,), hand0=(TRICK,))
        blocker = only_oid(game, BEAR, 1)
        block(game, blocker, bear)
        cast_on(game, 0, TRICK, blocker, step=Step.DECLARE_BLOCKERS)
        assert not game.state.combat.blocking(blocker)
        through_damage(game)
        assert game.state.players[1].life == 40, "a blocked creature without trample"
        assert game.state.objects[blocker].damage == 0
        assert game.state.objects[bear].damage == 0

    def test_a_trampler_whose_blocker_is_removed_assigns_it_all_to_the_player(self, builder):
        """702.19e: a trampler blocked by nothing left in combat hits the player."""
        game, trampler = position(builder, mine=(TRAMPLER,), theirs=(BEAR,), hand0=(TRICK,))
        blocker = only_oid(game, BEAR, 1)
        block(game, blocker, trampler)
        cast_on(game, 0, TRICK, blocker, step=Step.DECLARE_BLOCKERS)
        through_damage(game)
        assert game.state.players[1].life == 35


class TestBoundaries:
    def test_outside_combat_it_does_nothing(self, builder):
        game = (
            builder(players=2).battlefield(1, [BEAR]).hand(0, [TRICK]).build()
        )
        bear = only_oid(game, BEAR, 1)
        cast_on(game, 0, TRICK, bear)
        assert game.state.combat is None or bear not in game.state.combat.removed
        assert bear in game.state.battlefield

    def test_it_lasts_one_combat(self, builder):
        game, bear = position(builder, hand1=(TRICK,))
        cast_on(game, 1, TRICK, bear)
        # Player 1's turn passes; player 0 attacks with the same bear again.
        pass_until(
            game,
            lambda g: g.state.active_player == 0
            and g.state.turn > 1
            and g.pending() is not None
            and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
            limit=800,
        )
        assert bear in oids_of(game, BEAR, 0)
        attack_with(game, bear, defender=1)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert game.state.combat.attacking(bear)


def probe(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{U}",
                "types": ["Instant"],
                "spell_effects": [effect],
            }
        )
    )


class TestLoadTime:
    def test_it_needs_objects(self):
        with pytest.raises(DslError, match="remove_from_combat"):
            probe({"op": "remove_from_combat"})
