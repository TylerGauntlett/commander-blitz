"""Which *players* a creature dealt combat damage to this turn -- Steel Hellkite.

"{X}: Destroy each nonland permanent with mana value X **whose controller was
dealt combat damage by this creature this turn**." The question is about one
creature and asks *whom*, and is asked in the second main phase, after
`state.combat` has gone. Nothing else in the engine answers it:

- `TurnLedger.players_attacked_by` is the near miss and is wrong both ways: a
  Hellkite that was blocked attacked a player and dealt them nothing.
- `state.damage_ledger` records damage to *objects* only.
- The `combat_damage_by` condition is prowl's table-wide "a player was dealt
  combat damage by a Faerie", which names neither the player nor the source.

So `TurnLedger.players_dealt_combat_damage_by` (source oid -> seats), folded off
COMBAT_DAMAGE_TO_PLAYER -- which fires only for damage actually dealt (120.3,
510.2) -- and the player spec `{"dealt_combat_damage_by": "self"}`, used here as
a selector's `controller`.

400.7 shapes the record: the oid survives a zone change and the object does
not. A Hellkite flickered after combat is a new object that dealt nobody
anything, so the record is dropped when the oid **enters** the battlefield. It
is *not* dropped when the creature leaves, so an ability already on the stack
still resolves off what its source did (last-known information, 113.7a). It
wears off with the rest of the ledger at cleanup.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import select_players
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, activations, find_action, oids_of, only_oid, pass_until

HELLKITE = "t_dcd_hellkite"  # 5/5 flyer; {X}: the Steel Hellkite line
REACH = "t_dcd_reach"  # 0/7 reach, blocks it and survives
TWO = "t_dcd_two"  # noncreature artifact, mana value 2
THREE = "t_dcd_three"  # noncreature artifact, mana value 3
BEAR = "t_bear"  # {1}{G} 2/2
BOLT = "t_bolt"  # an instant, so priority stops in every step
SPEC = {"dealt_combat_damage_by": "self"}


def board(builder, *, players: int = 3, theirs: dict[int, list[str]] | None = None):
    b = (
        builder(players=players)
        .battlefield(0, ["mountain"] * 4 + [HELLKITE, BEAR])
        .hand(0, [BOLT])
        .library(0, ["mountain"] * 10)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid in range(1, players):
        b.battlefield(pid, (theirs or {}).get(pid, []))
        b.library(pid, ["mountain"] * 10)
    game = b.build()
    return game, only_oid(game, HELLKITE, 0), only_oid(game, BEAR, 0)


def declare(game, attacks: dict[int, TargetRef]) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    for oid, ref in attacks.items():
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(ref,)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def until(game, predicate, limit: int = 300) -> None:
    """Answer every decision with its default until ``predicate`` holds."""
    for _ in range(limit):
        if predicate(game) or game.over:
            return
        decision = game.pending()
        assert decision is not None, "nothing left to pass with"
        game.apply(_default_answer(game, decision))
    raise AssertionError("did not reach the condition")


def to_second_main(game) -> None:
    until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN and g.pending() is not None
          and g.pending().kind is DecisionKind.PRIORITY and g.pending().player == 0)


def dealt_by(game, oid: int) -> list[int]:
    return select_players(EffectContext(state=game.state, controller=0, source_oid=oid), SPEC)


def activate_with_x(game, hellkite: int, x: int) -> None:
    game.apply(activations(game, hellkite)[0])
    pick = next(
        a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x
    )
    game.apply(pick)
    until(game, lambda g: not g.state.stack and g.pending() is not None
          and g.pending().kind is DecisionKind.PRIORITY and g.pending().player == 0)


class TestTheLedger:
    def test_it_records_whom_each_creature_dealt_combat_damage(self, builder):
        game, kite, bear = board(builder)
        declare(game, {kite: TargetRef.player(1), bear: TargetRef.player(2)})
        to_second_main(game)
        assert game.state.combat is None
        assert game.state.turn_ledger.players_dealt_combat_damage_by == {kite: {1}, bear: {2}}
        assert dealt_by(game, kite) == [1]

    def test_a_blocked_creature_dealt_the_player_nothing(self, builder):
        # Attacked them, yes -- `players_attacked_by` says so -- but no damage.
        game, kite, _ = board(builder, theirs={1: [REACH]})
        wall = only_oid(game, REACH, 1)
        declare(game, {kite: TargetRef.player(1)})
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
        )
        game.apply(
            find_action(game, ActionKind.ADD_BLOCKER, source=wall, targets=(TargetRef.obj(kite),))
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        to_second_main(game)
        assert game.state.turn_ledger.players_attacked_by[kite] == {1}
        assert dealt_by(game, kite) == []

    def test_a_creature_that_did_not_attack_dealt_nobody_anything(self, builder):
        game, kite, bear = board(builder)
        declare(game, {bear: TargetRef.player(1)})
        to_second_main(game)
        assert dealt_by(game, kite) == []


class TestANewObject:
    """400.7, and the last-known information it must not destroy."""

    def test_coming_back_forgets_it(self, builder):
        game, kite, _ = board(builder)
        declare(game, {kite: TargetRef.player(1)})
        to_second_main(game)
        move_object(game.state, kite, Zone.EXILE)
        move_object(game.state, kite, Zone.BATTLEFIELD)
        assert dealt_by(game, kite) == []

    def test_leaving_alone_keeps_it_for_what_is_on_the_stack(self, builder):
        game, kite, _ = board(builder)
        declare(game, {kite: TargetRef.player(1)})
        to_second_main(game)
        move_object(game.state, kite, Zone.GRAVEYARD)
        assert dealt_by(game, kite) == [1]

    def test_it_is_cleared_with_the_ledger(self, builder):
        game, kite, _ = board(builder)
        declare(game, {kite: TargetRef.player(1)})
        to_second_main(game)
        game.state.turn_ledger.clear()
        assert dealt_by(game, kite) == []


class TestTheCard:
    THEIRS = {1: [BEAR, TWO, THREE, "forest"], 2: [BEAR, TWO]}

    def test_x_destroys_mana_value_x_of_the_players_it_hit(self, builder):
        game, kite, bear = board(builder, theirs=self.THEIRS)
        declare(game, {kite: TargetRef.player(1)})
        to_second_main(game)
        activate_with_x(game, kite, 2)
        assert oids_of(game, BEAR, 1) == [] and oids_of(game, TWO, 1) == []
        assert oids_of(game, THREE, 1), "mana value 3 is not X"
        assert oids_of(game, "forest", 1), "a land is spared"
        assert oids_of(game, BEAR, 2) and oids_of(game, TWO, 2), "player 2 was not hit"
        assert oids_of(game, BEAR, 0) == [bear], "you were not hit either"

    def test_once_each_turn(self, builder):
        game, kite, _ = board(builder, theirs=self.THEIRS)
        declare(game, {kite: TargetRef.player(1)})
        to_second_main(game)
        activate_with_x(game, kite, 3)
        assert not activations(game, kite)

    def test_after_no_damage_it_destroys_nothing(self, builder):
        game, kite, _ = board(builder, theirs=self.THEIRS)
        to_second_main(game)
        activate_with_x(game, kite, 2)
        assert oids_of(game, BEAR, 1) and oids_of(game, TWO, 1)


class TestTheLoader:
    def probe(self, player) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "Probe.",
                "mana_cost": "{W}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "Probe.",
                        "cost": {"mana": "{1}"},
                        "effects": [
                            {
                                "op": "destroy",
                                "objects": {"zone": "battlefield", "controller": player},
                            }
                        ],
                    }
                ],
            }
        )

    def test_self_loads(self):
        compile_card(self.probe(SPEC))

    @pytest.mark.parametrize(
        "bad", [{"dealt_combat_damage_by": "subject"}, {**SPEC, "not": "you"}]
    )
    def test_anything_else_is_refused(self, bad):
        with pytest.raises(DslError, match="dealt_combat_damage_by"):
            compile_card(self.probe(bad))
