"""Gravestorm's count -- permanents put into a graveyard from the battlefield.

    702.69a  Gravestorm is a triggered ability that functions on the stack.
    "Gravestorm" means "When you cast this spell, copy it for each permanent
    that was put into a graveyard from the battlefield this turn. If the spell
    has any targets, you may choose new targets for any of the copies."

The witness is Ominous Harvest. The ledger already kept two numbers that look
like this one, and each is wrong in its own direction:

- `cards_to_graveyard_this_turn` counts **cards** reaching a graveyard from
  **anywhere**. A discard or a mill is a card in a graveyard and no permanent
  leaving the battlefield, so it over-counts; a token is not a card, so it
  under-counts.
- `creatures_died_this_turn` counts only creatures, so a sacrificed Treasure, a
  destroyed enchantment or a land that was blown up is missing.

**Tokens count.** A token that leaves the battlefield for a graveyard really is
put there, and only then ceases to exist as a state-based action (111.7,
704.5d) -- so a token dying is a permanent put into a graveyard from the
battlefield, and on a token board it is most of the count. Excluding it is the
commonest way this number could be wrong, and it is the one way the existing
card tally is wrong on purpose.

So the tally is `TurnLedger.permanents_to_graveyard`, folded off ZONE_CHANGE in
`GameState._tally` where the move is battlefield to graveyard, whoever the
controller was and whatever the object is. It is read through
`{"permanents_to_graveyard_this_turn": true}`, which takes no player spec:
gravestorm's count is the whole table's.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token, discard_cards, mill_cards
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, action_for_card, only_oid, pass_until

BEAR = "t_bear"  # {1}{G} 2/2
RING = "sol_ring"  # a noncreature artifact
WARRIOR = "t_warrior_token"  # a creature token
BOLT = "t_bolt"  # {R} instant, 3 damage to any target
GRAVEBOLT = "t_gravebolt"  # {2}{R} instant, 1 damage to a player; gravestorm
VALUE = {"permanents_to_graveyard_this_turn": True}


def position(builder):
    """Player 0 has a bear and a Sol Ring, player 1 a bear, mid-turn, frozen."""
    game = (
        builder(players=2)
        .battlefield(0, [BEAR, RING])
        .battlefield(1, [BEAR])
        .hand(0, [BEAR])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    return game, game.state.turn_ledger


def gravestorm_count(game) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=0), VALUE)


class TestWhatCounts:
    def test_nothing_has_gone_yet(self, builder):
        game, ledger = position(builder)
        assert ledger.permanents_to_graveyard == 0
        assert gravestorm_count(game) == 0

    def test_a_creature_dying_counts(self, builder):
        game, _ = position(builder)
        move_object(game.state, only_oid(game, BEAR, 1), Zone.GRAVEYARD)
        assert gravestorm_count(game) == 1

    def test_a_noncreature_artifact_counts(self, builder):
        """The permanent `creatures_died_this_turn` misses."""
        game, ledger = position(builder)
        move_object(game.state, only_oid(game, RING, 0), Zone.GRAVEYARD)
        assert gravestorm_count(game) == 1
        assert ledger.creatures_died == {}, "and it is no creature's death"

    def test_a_token_counts(self, builder):
        """The permanent `cards_to_graveyard_this_turn` misses (111.7)."""
        game, ledger = position(builder)
        (oid,) = create_token(game.state, WARRIOR, 0)
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert gravestorm_count(game) == 1
        assert ledger.cards_to_graveyard == 0, "it is not a card"

    def test_every_controller_counts(self, builder):
        """"Each permanent", not "each permanent you controlled"."""
        game, _ = position(builder)
        move_object(game.state, only_oid(game, BEAR, 0), Zone.GRAVEYARD)
        move_object(game.state, only_oid(game, BEAR, 1), Zone.GRAVEYARD)
        move_object(game.state, only_oid(game, RING, 0), Zone.GRAVEYARD)
        assert gravestorm_count(game) == 3


class TestWhatDoesNot:
    def test_a_discarded_card_does_not(self, builder):
        game, ledger = position(builder)
        discard_cards(game.state, 0, [game.state.players[0].hand[0]])
        assert gravestorm_count(game) == 0
        assert ledger.cards_to_graveyard == 1, "the near miss counts it"

    def test_a_milled_card_does_not(self, builder):
        game, ledger = position(builder)
        mill_cards(game.state, 1, 2)
        assert gravestorm_count(game) == 0
        assert ledger.cards_to_graveyard == 2, "the near miss counts them"

    def test_a_permanent_exiled_does_not(self, builder):
        """From the battlefield, but not *into a graveyard*."""
        game, _ = position(builder)
        move_object(game.state, only_oid(game, BEAR, 1), Zone.EXILE)
        assert gravestorm_count(game) == 0

    def test_a_permanent_bounced_does_not(self, builder):
        game, _ = position(builder)
        move_object(game.state, only_oid(game, BEAR, 1), Zone.HAND)
        assert gravestorm_count(game) == 0


class TestItIsScopedToTheTurn:
    def test_the_next_turn_starts_empty(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, RING])
            .battlefield(1, [BEAR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        move_object(game.state, only_oid(game, BEAR, 1), Zone.GRAVEYARD)
        move_object(game.state, only_oid(game, RING, 0), Zone.GRAVEYARD)
        assert gravestorm_count(game) == 2
        pass_until(
            game,
            lambda g: g.state.turn == 2 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        assert game.state.turn_ledger.permanents_to_graveyard == 0
        assert gravestorm_count(game) == 0


def settle(game, limit: int = 60) -> None:
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def total_life(game) -> int:
    return sum(p.life for p in game.state.players)


class TestGravestormCopiesByIt:
    """The count driving `copy_spell`, cast in a real game."""

    def spell_position(self, builder):
        # The opponent's bolt keeps priority stopping, so the gravestorm
        # trigger is not resolved inside the `apply` that cast the spell --
        # see `test_copy_spell.position`.
        return (
            builder(players=2)
            .hand(0, [GRAVEBOLT])
            .battlefield(0, ["mountain"] * 3 + [BEAR, RING])
            .hand(1, [BOLT])
            .battlefield(1, ["mountain", BEAR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_no_deaths_no_copies(self, builder):
        game = self.spell_position(builder)
        before = total_life(game)
        game.apply(action_for_card(game, ActionKind.CAST, GRAVEBOLT))
        settle(game)
        assert before - total_life(game) == 1, "the spell alone"

    def test_a_creature_an_artifact_and_a_token_make_three_copies(self, builder):
        game = self.spell_position(builder)
        (token,) = create_token(game.state, WARRIOR, 1)
        move_object(game.state, only_oid(game, BEAR, 1), Zone.GRAVEYARD)
        move_object(game.state, only_oid(game, RING, 0), Zone.GRAVEYARD)
        move_object(game.state, token, Zone.GRAVEYARD)
        before = total_life(game)
        game.apply(action_for_card(game, ActionKind.CAST, GRAVEBOLT))
        settle(game)
        assert before - total_life(game) == 4, "the spell and three copies"

    def test_the_count_is_read_as_the_trigger_resolves(self, builder):
        """A permanent that dies in response to gravestorm still adds a copy."""
        game = self.spell_position(builder)
        before = total_life(game)
        game.apply(action_for_card(game, ActionKind.CAST, GRAVEBOLT))
        assert game.state.stack, "the gravestorm trigger is waiting"
        move_object(game.state, only_oid(game, BEAR, 1), Zone.GRAVEYARD)
        settle(game)
        assert before - total_life(game) == 2, "the spell and one copy"


class TestTheLoader:
    def test_the_witness_shape_validates(self):
        validate_value(VALUE, "probe")

    @pytest.mark.parametrize("bad", ["you", "all", 1, False, None])
    def test_anything_but_true_is_refused(self, bad):
        """A player spec would read as a filter the count does not apply."""
        with pytest.raises(DslError, match="permanents_to_graveyard_this_turn: takes `true`"):
            validate_value({"permanents_to_graveyard_this_turn": bad}, "probe")

    def test_the_gravestorm_card_compiles(self, registry):
        card = registry.get(GRAVEBOLT)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert Zone.STACK in ability.active_zones
        assert ability.effects[0]["amount"] == VALUE
