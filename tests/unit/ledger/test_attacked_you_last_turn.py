"""Whom each player attacked on their last turn: the `attacked_you_last_turn` condition.

    "This spell costs {2} less to cast if **a player attacked you during their
    last turn**."                                                     -- Avenge

The question is asked on *your* turn about somebody else's, and nothing in the
engine kept the answer that long. Every attack tally lives on the turn ledger,
which cleanup clears (`attacked_this_turn` and its relatives), and a sorcery
cast in your main phase is never inside the attacker's turn. So the ledger
gains the seat-level record `TurnLedger.seats_attacked` (attacking player ->
the seats they declared an attacker against), and cleanup hands the active
player's entry to `GameState.attacked_last_turn` before clearing the rest.

What "attacked you" means, and each reading has a test class:

- **506.2 / 508.1b** -- a player attacks you by declaring an attacker that is
  attacking *you*. An attacker sent at a planeswalker or a battle you control
  is attacking that permanent, not its controller, so by the plain reading it
  does not count (the same line `players_attacked_by` draws for Angel of
  Destiny). Attacking a different player does not count either.
- **"Their last turn"** is that player's most recent completed turn, and each
  of their turns replaces the record: an attack two turns of theirs ago is
  forgotten as soon as they take a turn without one. While their turn is in
  progress, their last turn is still the previous one.
- **"A player"** is anyone at the table: at a pod one opponent of several
  attacking you is enough. The attack is a fact about the declaration, so an
  attacker that died in combat still attacked (`players_attacked_by` forgets
  it, which is why that record cannot answer this).
- **514.3a** -- cleanup can repeat, and the repeat finds the ledger already
  empty. The record carries its turn number, so the repeat leaves it alone.

Avenge is the witness; `t_aylt_wrath` in
`tests/data/attacked_you_last_turn.cards.json` is its first sentence on a
sorcery costing {4}{W}{W}.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.cost_reduction import cost_reduction
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.turn import _cleanup_step
from commanderblitz.engine.zones import move_object
from tests.conftest import find_action, only_oid, pass_until

WRATH = "t_aylt_wrath"  # {4}{W}{W}, {2} less if a player attacked you last turn
BEAR = "t_bear"  # 2/2
WALKER = "t_walker"  # loyalty 4
PLAINS = "plains"


def table(builder, *, players: int = 3, walker: bool = False):
    """Player 0 with the wrath, six Plains (and a walker); everyone else a bear.

    Starts in player 1's precombat main, so the turns run 1, 2, ..., then 0.
    Returns ``(game, wrath_oid, {pid: bear_oid})``.
    """
    b = (
        builder(players=players)
        .battlefield(0, [PLAINS] * 6 + ([WALKER] if walker else []))
        .hand(0, [WRATH])
        .library(0, [PLAINS] * 20)
        .active(1)
        .turn(2)
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid in range(1, players):
        b.battlefield(pid, [BEAR])
        b.library(pid, [PLAINS] * 20)
    game = b.build()
    bears = {pid: only_oid(game, BEAR, pid) for pid in range(1, players)}
    return game, game.state.players[0].hand[0], bears


def attack(game, pid: int, attacks: dict[int, TargetRef]) -> None:
    """Run to ``pid``'s declaration and declare ``attacks`` (or nothing)."""
    pass_until(
        game,
        lambda g: g.state.active_player == pid
        and g.pending() is not None
        and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
    )
    assert game.state.active_player == pid
    for oid, ref in attacks.items():
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(ref,)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def to_my_main(game) -> None:
    pass_until(
        game,
        lambda g: g.state.active_player == 0 and g.state.step is Step.PRECOMBAT_MAIN,
    )
    assert game.state.active_player == 0 and game.state.step is Step.PRECOMBAT_MAIN


def discount(game, oid: int) -> int:
    return cost_reduction(game.state, 0, game.state.card(oid))


def untapped_lands(game) -> int:
    return sum(
        1
        for oid in game.state.battlefield
        if game.state.objects[oid].controller == 0
        and not game.state.objects[oid].tapped
        and game.state.card(oid).is_land
    )


class TestAnAttackOnYouLastTurn:
    def test_it_takes_two_off(self, builder):
        game, wrath, bears = table(builder)
        attack(game, 1, {bears[1]: TargetRef.player(0)})
        attack(game, 2, {})
        to_my_main(game)
        assert discount(game, wrath) == 2

    def test_the_charge_is_the_discounted_price(self, builder):
        """`cost_reduction` both offers and charges, so six Plains pay four."""
        game, wrath, bears = table(builder)
        attack(game, 1, {bears[1]: TargetRef.player(0)})
        attack(game, 2, {})
        to_my_main(game)
        game.apply(find_action(game, ActionKind.CAST, source=wrath))
        pass_until(game, lambda g: not g.state.stack)
        assert untapped_lands(game) == 2

    def test_the_record_survives_into_your_turn(self, builder):
        game, _, bears = table(builder)
        attack(game, 1, {bears[1]: TargetRef.player(0)})
        attack(game, 2, {})
        to_my_main(game)
        assert game.state.turn_ledger.seats_attacked == {}, "the ledger is this turn only"
        assert game.state.attacked_last_turn[1][1] == {0}
        assert game.state.attacked_last_turn[2][1] == set()

    def test_an_attacker_that_died_still_attacked(self, builder):
        game, wrath, bears = table(builder)
        attack(game, 1, {bears[1]: TargetRef.player(0)})
        move_object(game.state, bears[1], Zone.GRAVEYARD)
        attack(game, 2, {})
        to_my_main(game)
        assert discount(game, wrath) == 2


class TestNoAttackOnYou:
    def test_nobody_attacked(self, builder):
        game, wrath, _ = table(builder)
        attack(game, 1, {})
        attack(game, 2, {})
        to_my_main(game)
        assert discount(game, wrath) == 0

    def test_full_price_is_charged(self, builder):
        game, wrath, _ = table(builder)
        attack(game, 1, {})
        attack(game, 2, {})
        to_my_main(game)
        game.apply(find_action(game, ActionKind.CAST, source=wrath))
        pass_until(game, lambda g: not g.state.stack)
        assert untapped_lands(game) == 0

    def test_attacking_another_player_is_not_attacking_you(self, builder):
        game, wrath, bears = table(builder)
        attack(game, 1, {bears[1]: TargetRef.player(2)})
        attack(game, 2, {})
        to_my_main(game)
        assert discount(game, wrath) == 0

    def test_attacking_your_planeswalker_is_not_attacking_you(self, builder):
        """506.2: the walker was attacked, and you defended it, but nobody
        attacked *you*."""
        game, wrath, bears = table(builder, walker=True)
        walker = only_oid(game, WALKER, 0)
        attack(game, 1, {bears[1]: TargetRef.obj(walker)})
        assert game.state.combat.attackers[bears[1]] == 0, "you still defend it"
        attack(game, 2, {})
        to_my_main(game)
        assert discount(game, wrath) == 0


class TestAPod:
    def test_one_attacker_among_several_is_enough(self, builder):
        game, wrath, bears = table(builder, players=4)
        attack(game, 1, {bears[1]: TargetRef.player(2)})
        attack(game, 2, {bears[2]: TargetRef.player(0)})
        attack(game, 3, {})
        to_my_main(game)
        assert discount(game, wrath) == 2

    def test_the_discount_does_not_stack(self, builder):
        """"If a player attacked you" -- two attackers are still one condition."""
        game, wrath, bears = table(builder)
        attack(game, 1, {bears[1]: TargetRef.player(0)})
        attack(game, 2, {bears[2]: TargetRef.player(0)})
        to_my_main(game)
        assert discount(game, wrath) == 2


class TestOnlyTheirLastTurn:
    def test_an_attack_two_turns_ago_is_forgotten(self, builder):
        """Player 1 attacked you, then took another turn without attacking: on
        your next turn their last turn is the quiet one."""
        game, wrath, bears = table(builder)
        attack(game, 1, {bears[1]: TargetRef.player(0)})
        attack(game, 2, {})
        to_my_main(game)
        assert discount(game, wrath) == 2
        attack(game, 1, {})
        attack(game, 2, {})
        to_my_main(game)
        assert discount(game, wrath) == 0

    def test_during_their_turn_their_last_turn_is_the_previous_one(self, builder):
        game, _, bears = table(builder)
        attack(game, 1, {bears[1]: TargetRef.player(0)})
        attack(game, 2, {})
        to_my_main(game)
        attack(game, 1, {})
        assert game.state.active_player == 1
        assert game.state.attacked_last_turn[1][1] == {0}, "this turn is not over"

    def test_a_player_who_has_taken_no_turn_attacked_nobody(self, builder):
        game, wrath, _ = table(builder)
        assert game.state.attacked_last_turn == {}
        assert discount(game, wrath) == 0


class TestACleanupRepeat:
    def test_a_second_pass_keeps_the_record(self, builder):
        """514.3a: the repeat finds the ledger cleared by the first pass."""
        game, _, _ = table(builder)
        state = game.state
        state.turn_ledger.seats_attacked[1] = {0}
        for _ in range(2):
            for _ in _cleanup_step(state):  # pragma: no cover - nothing to discard
                raise AssertionError("cleanup asked a question")
            assert state.attacked_last_turn[1] == (state.turn, frozenset({0}))


def probe(condition) -> dict:
    return {
        "id": "x_aylt_probe",
        "name": "Probe",
        "types": ["Sorcery"],
        "mana_cost": "{4}{W}",
        "cost_reduction": {"amount": 2, "condition": condition},
        "spell_effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
    }


class TestTheLoader:
    def test_a_player_spec_loads_in_a_cost_reduction(self):
        card = compile_card(
            CardModel.model_validate(probe({"attacked_you_last_turn": "each_opponent"}))
        )
        assert card.cost_reduction["condition"] == {"attacked_you_last_turn": "each_opponent"}

    @pytest.mark.parametrize("who", [True, None])
    def test_a_yes_or_no_is_refused(self, who):
        """`true` reads like the sentence and names nobody."""
        with pytest.raises(DslError, match="needs a player spec"):
            compile_card(CardModel.model_validate(probe({"attacked_you_last_turn": who})))

    def test_an_unknown_player_name_is_refused(self):
        with pytest.raises(DslError, match="must name one of"):
            compile_card(
                CardModel.model_validate(probe({"attacked_you_last_turn": "a_player"}))
            )
