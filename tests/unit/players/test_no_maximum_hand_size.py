"""`no_maximum_hand_size` — 402.2 and 514.1, for the rest of the game.

"Draw cards equal to the number of cards in your hand plus one. **You have no
maximum hand size for the rest of the game.**" (Sea Gate Restoration.) The same
sentence closes Finale of Revelation's X-is-10 branch and Ancient Silver
Dragon's combat-damage trigger.

The words already existed as the static ``no_hand_limit`` — Reliquary Tower,
Thought Vessel — and that is exactly why the card could not be written: a
static lives only while the permanent printing it is on the battlefield, and a
sorcery never is. By the first cleanup step where the sentence matters the
spell is in its owner's graveyard, so any effect hung on the *object* has
already ended. Without this, Sea Gate Restoration draws its caster eight cards
and then makes them discard down to seven at end of turn — the card's whole
second half undone by 514.1.

So the effect lives on the **player**, one-way, beside `has_city_s_blessing`,
and it is read by the same `player_has_no_hand_limit` the statics answer
through, so the cleanup step has one question to ask rather than two rule paths
that could disagree. The claims below: a nine-card hand survives cleanup; the
opponent still discards; it outlives the spell by whole turns; and the static
path it shares is still the static path.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player import MAX_HAND_SIZE
from commanderblitz.engine.player_statics import player_has_no_hand_limit
from commanderblitz.engine.serialize import full_view
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

SEA_GATE = "t_sea_gate"  # {U} sorcery: you have no maximum hand size for the rest of the game
FOR_ALL = "t_hand_freedom_for_all"  # {U} sorcery: each player has no maximum hand size
BEAR = "t_bear"
TOWER = "reliquary_tower"


def position(builder, *, spell: str | None = SEA_GATE, mine: int = 9, theirs: int = 9, board=()):
    """Player 0 in their first main phase; ``mine`` and ``theirs`` are hand sizes.

    Every hand holds a Lightning Bolt beside a Mountain, counted in the size.
    Never cast -- the passive answer is always Pass -- but it keeps a priority
    window open in every step, so passing stops where it is told to instead of
    auto-passing the table through twenty turns inside one `apply`. Player 0
    also holds ``spell``, *not* counted: cast, it leaves exactly ``mine``.
    Both libraries are stocked so nobody loses to an empty draw.
    """
    hand = [*([spell] if spell else []), "lightning_bolt", *[BEAR] * (mine - 1)]
    return (
        builder(players=2)
        .hand(0, hand)
        .hand(1, ["lightning_bolt", *[BEAR] * (theirs - 1)])
        .library(0, [BEAR] * 10)
        .library(1, [BEAR] * 10)
        .battlefield(0, ["island", "mountain", *board])
        .battlefield(1, ["mountain"])
        .active(0)
        .turn(1)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def cast(game, card_id: str) -> int:
    """Cast ``card_id`` from player 0's hand and pass until it has resolved."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)
    return action.source


def until_turn(game, turn: int) -> None:
    pass_until(game, lambda g: g.state.turn == turn, limit=3000)


def hand_size(game, pid: int) -> int:
    return len(game.state.players[pid].hand)


class TestCleanupKeepsTheHand:
    def test_nine_cards_survive_cleanup(self, builder):
        game = position(builder)
        cast(game, SEA_GATE)
        assert game.state.turn == 1
        assert hand_size(game, 0) == 9
        until_turn(game, 2)
        assert hand_size(game, 0) == 9, "514.1 has nothing to discard down to"

    def test_without_it_cleanup_discards_to_seven(self, builder):
        """The control: the same nine cards, no spell, and 514.1 bites."""
        game = position(builder, spell=None)
        until_turn(game, 2)
        assert hand_size(game, 0) == MAX_HAND_SIZE


class TestOnlyThePlayerNamed:
    def test_the_opponent_still_discards(self, builder):
        game = position(builder)
        cast(game, SEA_GATE)
        until_turn(game, 3)
        assert hand_size(game, 1) == MAX_HAND_SIZE, "their own cleanup trimmed them"
        assert not game.state.players[1].has_no_maximum_hand_size
        assert not player_has_no_hand_limit(game.state, 1)

    def test_each_player_frees_everyone(self, builder):
        game = position(builder, spell=FOR_ALL)
        cast(game, FOR_ALL)
        until_turn(game, 3)
        assert hand_size(game, 1) == 10, "nine, plus their draw, and no discard"


class TestItOutlivesTheSpell:
    def test_the_spell_is_in_the_graveyard(self, builder):
        game = position(builder)
        oid = cast(game, SEA_GATE)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert player_has_no_hand_limit(game.state, 0)

    def test_it_still_holds_turns_later(self, builder):
        """Turn 3 is the caster's next turn: nine, plus the draw, kept."""
        game = position(builder)
        cast(game, SEA_GATE)
        until_turn(game, 4)
        assert hand_size(game, 0) == 10

    def test_it_is_on_the_player_view(self, builder):
        game = position(builder)
        cast(game, SEA_GATE)
        players = full_view(game.state)["players"]
        assert [p["has_no_maximum_hand_size"] for p in players] == [True, False]


class TestTheStaticPathIsUnchanged:
    """Both sources answer through `player_has_no_hand_limit`; neither eats the other."""

    def test_a_reliquary_tower_still_works_alone(self, builder):
        game = position(builder, spell=None, board=[TOWER])
        until_turn(game, 2)
        assert hand_size(game, 0) == 9

    def test_losing_the_tower_does_not_take_the_one_shot_with_it(self, builder):
        game = position(builder, board=[TOWER])
        cast(game, SEA_GATE)
        tower = next(
            oid for oid in game.state.battlefield if game.state.objects[oid].def_id == TOWER
        )
        move_object(game.state, tower, Zone.GRAVEYARD)
        assert player_has_no_hand_limit(game.state, 0)
        until_turn(game, 2)
        assert hand_size(game, 0) == 9


def probe(effect):
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{U}",
            "types": ["Sorcery"],
            "spell_effects": [effect],
        }
    )


class TestTheLoaderGuardsIt:
    def test_a_bare_op_compiles(self):
        card = compile_card(probe({"op": "no_maximum_hand_size"}))
        assert [e["op"] for e in card.spell_effects] == ["no_maximum_hand_size"]

    def test_a_player_spec_compiles(self):
        compile_card(probe({"op": "no_maximum_hand_size", "player": "each_player"}))

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("duration", "until_your_next_turn"),
            ("objects", {"self_only": True}),
            ("controller", "you"),
        ],
    )
    def test_a_near_miss_key_is_refused(self, key, value):
        """Enter the Infinite's "until your next turn" is the `duration` witness:
        accepted and ignored, it would be a permanent upgrade."""
        with pytest.raises(DslError, match=f"no_maximum_hand_size takes no '{key}'"):
            compile_card(probe({"op": "no_maximum_hand_size", key: value}))

    def test_an_unknown_player_is_refused(self):
        with pytest.raises(DslError):
            compile_card(probe({"op": "no_maximum_hand_size", "player": "the_table"}))
