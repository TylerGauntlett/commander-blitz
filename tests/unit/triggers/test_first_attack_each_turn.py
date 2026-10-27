"""Attacking for the first time each turn, and attacking the player with the most life.

    "Whenever this creature attacks for the first time each turn, if it's
    attacking the player with the most life or tied for most life, untap all
    attacking creatures. After this phase, there is an additional combat
    phase."                                          -- Scourge of the Throne

Two clauses, and each had a near miss that is wrong at the card's own edge.

**"For the first time each turn"** is an ordinal of the creature's attacks, and
it is a fact about the event: `attacks` with `nth: 1`, the ordinal written onto
the ATTACKS event from `TurnLedger.attacks_by_creature`. `max_per_turn: 1` is
the near miss. It counts the ability's *queued* firings (`triggers._queue`), so
a first attack at a player without the most life leaves it unspent, and the
creature's second attack -- in an extra combat from somewhere else -- fires the
ability the printed card forbids. The ordinal counts every attack, triggered
on or not.

**"If it's attacking the player with the most life"** is an intervening-if
(603.4): asked as the ability triggers and again as it resolves. It is the
`attacking_player: "most_life"` selector key over the source, read off live
combat, so a creature attacking a planeswalker (506.2) never passes it and a
defender drained below another player before resolution fails the recheck.
Dethrone's `defending: "most_life"` is the same comparison
(`GameState.has_most_life`) asked as part of the event instead, because
dethrone has no "if".

The witness is Test First Attack Scourge, Scourge of the Throne's third
ability on a vanilla body.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.selectors import validate_selector
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import untap_permanent
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.turn import grant_extra_phases
from tests.conftest import find_action, only_oid, pass_until, settle

SCOURGE = "t_fa_scourge"  # 5/5; first attack each turn at the most life: untap, +1 combat
BEAR = "t_bear"  # 2/2
WALKER = "t_walker"  # loyalty 4
BOLT = "t_bolt"  # {R} instant, so priority stops while a trigger is on the stack


def position(builder, *, life=(20, 30, 25), theirs=None):
    b = (
        builder(players=len(life))
        .battlefield(0, ["mountain", SCOURGE, BEAR])
        .hand(0, [BOLT])
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid, total in enumerate(life):
        b.life(pid, total)
    for pid, cards in (theirs or {}).items():
        b.battlefield(pid, cards)
    game = b.build()
    return game, only_oid(game, SCOURGE, 0), only_oid(game, BEAR, 0)


def to_declaration(game) -> None:
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)


def declare(game, attacks: dict[int, TargetRef]) -> None:
    to_declaration(game)
    for oid, ref in attacks.items():
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(ref,)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def combats(game) -> int:
    return game.state.turn_ledger.combats


def at(pid: int) -> TargetRef:
    return TargetRef.player(pid)


class TestTheFirstAttack:
    def test_at_the_most_life_it_untaps_the_attackers_and_adds_a_combat(self, builder):
        game, scourge, bear = position(builder)
        declare(game, {scourge: at(1), bear: at(2)})
        assert game.state.stack, "the trigger is waiting to resolve"
        settle(game)
        assert not game.state.objects[scourge].tapped
        assert not game.state.objects[bear].tapped, "all attacking creatures, whomever they attack"
        assert game.state.extra_phases == ["combat"]

    def test_tied_for_the_most_life_counts(self, builder):
        game, scourge, _ = position(builder, life=(20, 30, 30))
        declare(game, {scourge: at(2)})
        settle(game)
        assert game.state.extra_phases == ["combat"]

    def test_at_less_life_it_does_not_trigger(self, builder):
        game, scourge, _ = position(builder)
        declare(game, {scourge: at(2)})
        assert not game.state.stack
        assert game.state.objects[scourge].tapped
        assert not game.state.extra_phases

    def test_the_attackers_controller_is_one_of_the_players(self, builder):
        game, scourge, _ = position(builder, life=(40, 30, 25))
        declare(game, {scourge: at(1)})
        assert not game.state.stack

    def test_attacking_the_top_life_players_planeswalker_does_not_trigger(self, builder):
        """506.2: the walker is attacked, not its controller."""
        game, scourge, _ = position(builder, theirs={1: [WALKER]})
        declare(game, {scourge: TargetRef.obj(only_oid(game, WALKER, 1))})
        assert not game.state.stack
        assert not game.state.extra_phases


class TestOnlyTheFirstAttack:
    def test_it_does_not_trigger_in_the_combat_it_made(self, builder):
        game, scourge, _ = position(builder)
        declare(game, {scourge: at(1)})
        settle(game)
        to_declaration(game)
        assert combats(game) == 2
        declare(game, {scourge: at(1)})
        assert not game.state.stack, "its second attack is not its first"
        assert not game.state.extra_phases, "so no third combat"

    def test_a_first_attack_that_failed_the_if_still_was_the_first(self, builder):
        """The case `max_per_turn: 1` gets wrong: nothing queued, the ordinal moved."""
        game, scourge, _ = position(builder)
        grant_extra_phases(game.state, ["combat"])  # another card's extra combat
        declare(game, {scourge: at(2)})
        assert not game.state.stack
        settle(game)
        to_declaration(game)
        assert combats(game) == 2
        untap_permanent(game.state, scourge)
        declare(game, {scourge: at(1)})
        assert not game.state.stack, "attacking the most life now, but not for the first time"
        assert game.state.turn_ledger.attacks_by_creature[scourge] == 2

    def test_another_creatures_attacks_are_not_its_own(self, builder):
        game, scourge, bear = position(builder)
        grant_extra_phases(game.state, ["combat"])
        declare(game, {bear: at(1)})
        settle(game)
        to_declaration(game)
        declare(game, {scourge: at(1)})
        assert game.state.stack, "the bear's attack was not the Scourge's"

    def test_the_count_clears_at_cleanup(self, builder):
        game, scourge, _ = position(builder)
        declare(game, {scourge: at(2)})
        game.state.turn_ledger.clear()
        assert scourge not in game.state.turn_ledger.attacks_by_creature


class TestTheInterveningIf:
    def test_a_defender_drained_below_another_before_resolution_fails_the_recheck(self, builder):
        """603.4: the "if" is asked again on resolution, unlike dethrone."""
        game, scourge, _ = position(builder)
        declare(game, {scourge: at(1)})
        assert game.state.stack
        game.state.players[1].life = 10
        settle(game)
        assert game.state.objects[scourge].tapped
        assert not game.state.extra_phases


class TestTheLoader:
    def _card(self, **trigger):
        return {
            "id": "t_fa_probe",
            "name": "First Attack Probe",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "trigger": trigger,
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }

    def test_nth_loads_on_attacks(self):
        compile_card(CardModel.model_validate(self._card(event="attacks", source="self", nth=1)))

    def test_nth_is_still_refused_on_an_event_with_no_ordinal(self):
        with pytest.raises(DslError, match="or an attacks trigger"):
            compile_card(CardModel.model_validate(self._card(event="blocks", source="self", nth=1)))

    def test_most_life_is_an_attacking_player_word(self):
        validate_selector({"zone": "battlefield", "attacking_player": "most_life"}, "test")

    def test_a_bare_true_is_still_refused(self):
        with pytest.raises(DslError, match="attacking_player"):
            validate_selector({"zone": "battlefield", "attacking_player": True}, "test")
