""""Up to three target cards from **their** graveyard", owned by one mode --
601.2b, 601.2c, 608.2b and 706.10.

    Quandrix Command -- "Choose two --
    * Return target creature or planeswalker to its owner's hand.
    * Counter target artifact or enchantment spell.
    * Put two +1/+1 counters on target creature.
    * Target player shuffles up to three target cards from their graveyard
      into their library."

The fourth bullet owns two targets: a player, and a caster-sized set of cards
whose pool *is* that player's graveyard -- ``{"controller": {"target":
"shuffler"}}``, a link to a sibling of the same mode. Two things have to hold:

* **the link is read at declaration.** `Game._ask_mode_targets` asks a mode's
  specs one at a time; without handing over the player it just declared, the
  cards' selector reads nobody, offers nothing, and the bullet silently shuffles
  a library and moves no card at all.
* **the variable size does not disturb the other mode.** 0-3 refs for the cards
  are stored after every fixed-size ref (`CardDef.specs_for_modes`), so the
  counters bullet keeps its creature however many cards were picked.

608.2b then re-checks the cards against the same link: a player who has become
an illegal target performs nothing, so their cards stay where they are rather
than being put on top of a library nobody shuffles. Each nearer spelling is a
different card: a fixed ``count: 3`` strikes the bullet below three cards and
forbids fewer; a card-level target is declared under every pair of bullets.
"""

from __future__ import annotations

import json

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.ops_stack import put_copy_on_stack
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import TEST_CARD_DIR, action_for_card, only_oid, plus_one_counters

COMMAND = "t_quandrix_command"
BEAR = "t_bear"
REFORMER = "t_ph_reformer"  # "You have hexproof."
BOUNCE = "Return target creature"
GROW = "Put two +1/+1 counters"
SHUFFLE = "Target player shuffles"


def board(builder):
    """Player 0 holds the Command beside a bear; player 1 has a bear and four
    cards in their graveyard, and a hexproof-granting creature in hand.

    Player 1 also holds an instant and the land for it: without a decision of
    their own the engine auto-passes and the spell resolves inside the cast's
    last ``apply``, leaving no window to change the board in.

    Returns ``(game, their_graveyard)``.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 2 + ["island"] * 2 + [BEAR])
        .hand(0, [COMMAND])
        .graveyard(0, [BEAR])
        .battlefield(1, [BEAR, "mountain"])
        .hand(1, [REFORMER, "t_bolt"])
        .graveyard(1, [BEAR, "forest", "forest", "forest"])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .build()
    )
    return game, list(game.state.players[1].graveyard)


def cast(game, *bullets: str) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, COMMAND))
    for bullet in bullets:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.label.startswith(bullet)
            )
        )


def pick(game, ids: list[int]) -> None:
    """Answer one target question with ``ids`` (seats or object ids)."""
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_OBJECTS, decision
    for wanted in ids:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.targets and a.targets[0].id == wanted
            )
        )
    if game.pending() is decision:
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )


def resolve(game) -> None:
    for _ in range(40):
        if not game.state.stack:
            return
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    raise AssertionError("the spell never resolved")


def mine(game) -> int:
    return only_oid(game, BEAR, 0)


def theirs(game) -> int:
    return only_oid(game, BEAR, 1)


def zones(game, oids) -> list[Zone]:
    return [game.state.objects[oid].zone for oid in oids]


class TestTheLinkReadsTheDeclaredPlayer:
    def test_the_cards_are_that_players_graveyard(self, builder):
        game, grave = board(builder)
        cast(game, GROW, SHUFFLE)
        pick(game, [mine(game)])
        pick(game, [1])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert (decision.min_count, decision.max_count) == (0, 3)
        offered = {a.targets[0].id for a in game.legal_actions() if a.targets}
        assert offered == set(grave)

    def test_naming_yourself_offers_your_own(self, builder):
        game, _ = board(builder)
        cast(game, GROW, SHUFFLE)
        pick(game, [mine(game)])
        pick(game, [0])
        offered = {a.targets[0].id for a in game.legal_actions() if a.targets}
        assert offered == set(game.state.players[0].graveyard)


class TestTheCasterPicksTheSize:
    @pytest.mark.parametrize("picked", [0, 1, 3])
    def test_each_count_shuffles_exactly_those(self, builder, picked):
        """Zero through three: the chosen cards go into their owner's library,
        and the other bullet's creature still gets its counters."""
        game, grave = board(builder)
        cast(game, GROW, SHUFFLE)
        pick(game, [mine(game)])
        pick(game, [1])
        pick(game, grave[:picked])
        resolve(game)
        assert zones(game, grave[:picked]) == [Zone.LIBRARY] * picked
        assert zones(game, grave[picked:]) == [Zone.GRAVEYARD] * (4 - picked)
        assert len(game.state.players[1].library) == 10 + picked
        assert plus_one_counters(game, mine(game)) == 2

    def test_the_earlier_bullet_keeps_its_target(self, builder):
        """Bounce beside the shuffle: three caster-sized refs stored after the
        bounce's one leave the bounce reading its own creature."""
        game, grave = board(builder)
        bear = theirs(game)
        cast(game, BOUNCE, SHUFFLE)
        pick(game, [bear])
        pick(game, [1])
        pick(game, grave[1:])
        resolve(game)
        assert game.state.objects[bear].zone is Zone.HAND
        assert zones(game, grave[1:]) == [Zone.LIBRARY] * 3


class TestOnResolution:
    def test_a_card_gone_leaves_the_rest(self, builder):
        game, grave = board(builder)
        cast(game, GROW, SHUFFLE)
        pick(game, [mine(game)])
        pick(game, [1])
        pick(game, grave[:3])
        move_object(game.state, grave[0], Zone.EXILE)
        resolve(game)
        assert zones(game, grave[:3]) == [Zone.EXILE, Zone.LIBRARY, Zone.LIBRARY]

    def test_an_illegal_player_moves_none_of_their_cards(self, builder):
        """608.2b: the player gained hexproof, so they shuffle nothing -- and
        the cards, chosen from *their* graveyard, are no longer legal either.
        The counters bullet still resolves."""
        game, grave = board(builder)
        cast(game, GROW, SHUFFLE)
        pick(game, [mine(game)])
        pick(game, [1])
        pick(game, grave[:3])
        reformer = next(
            oid for oid in game.state.players[1].hand if game.state.objects[oid].def_id == REFORMER
        )
        move_object(game.state, reformer, Zone.BATTLEFIELD)
        resolve(game)
        assert zones(game, grave) == [Zone.GRAVEYARD] * 4
        assert len(game.state.players[1].library) == 10
        assert plus_one_counters(game, mine(game)) == 2


class TestACopy:
    def test_the_copy_keeps_both_buckets(self, builder):
        """706.10: the copy keeps the modes and refs. It resolves first and
        shuffles the cards; the original finds them gone and still grows."""
        game, grave = board(builder)
        cast(game, GROW, SHUFFLE)
        pick(game, [mine(game)])
        pick(game, [1])
        pick(game, grave[:2])
        put_copy_on_stack(game.state, 0, game.state.stack[-1])
        resolve(game)
        assert zones(game, grave[:2]) == [Zone.LIBRARY] * 2
        assert plus_one_counters(game, mine(game)) == 4


def _variant(mutate) -> CardModel:
    data = json.loads((TEST_CARD_DIR / "modal_variable_targets.cards.json").read_text())
    card = data["cards"][0]
    mutate(card)
    return CardModel.model_validate(card)


class TestTheLoaderRefusals:
    def test_the_printed_card_loads(self):
        compile_card(_variant(lambda card: None))

    def test_a_link_to_another_modes_target(self):
        def mutate(card):
            card["targets"][4]["selector"]["controller"] = {"controller_of_target": "grown"}

        with pytest.raises(DslError, match="same mode"):
            compile_card(_variant(mutate))

    def test_a_link_from_a_card_level_target(self):
        def mutate(card):
            card["targets"][4].pop("mode")

        with pytest.raises(DslError):
            compile_card(_variant(mutate))
