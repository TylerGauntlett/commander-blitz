""""You and permanents you control gain hexproof until end of turn." -- 702.11d

    Lazotep Plating -- "Amass Zombies 1. You and permanents you control gain
    hexproof until end of turn."
    Everybody Lives! -- "... Players gain hexproof until end of turn. ..."

Hexproof on a *player* existed only as the `player_hexproof` static, which
lives on a permanent: an Instant leaves nothing behind to carry it, and an
emblem holding it would never end. `grant_keyword` wrote its `TempEffect` onto
objects chosen by `choose_objects`, and a seat is not one. The near miss,
`grant_protection`'s player half, is the wrong card: protection also prevents
damage and stops the player's *own* spells targeting them.

So `grant_keyword` takes a ``player`` recipient beside ``objects``, writing a
`PlayerHexproof` to a timed table that `player_statics.player_has_hexproof`
reads beside the static -- the one question `targeting._player_allowed` asks.

The rules points, each with a test:

- An opponent's spell cannot target the player; the player's own still can.
- The permanents half still lands from the same op.
- It ends in the cleanup step: next turn the player is a target again.
- The loader refuses any keyword but hexproof, and any clock but end of turn,
  on the player half.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import player_has_hexproof
from commanderblitz.engine.temp_effects import grant_player_hexproof
from tests.conftest import _default_answer, action_for_card, oids_of

GRANT = "t_player_hexproof_grant"  # you and permanents you control gain hexproof
BOLT = "t_bolt"  # deals 3 damage to any target
BEAR = "t_bear"


def position(builder, *, granted: bool = True):
    """Seat 1 has cast the grant (or not); seat 0 holds a Bolt on its turn."""
    game = (
        builder(players=2)
        .battlefield(0, ["mountain"] * 4)
        .battlefield(1, ["island", BEAR])
        .hand(0, [BOLT])
        .hand(1, [GRANT])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .active(1)
        .build()
    )
    if granted:
        game.apply(action_for_card(game, ActionKind.CAST, GRANT))
        settle(game)
    return game


def settle(game, limit: int = 100) -> None:
    """Let the stack empty, answering passively."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None or not game.state.stack:
            return
        game.apply(_default_answer(game, decision))


def run_to_next_turn(game, limit: int = 400) -> None:
    turn = game.state.turn
    for _ in range(limit):
        if game.over or game.state.turn != turn:
            return
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        preferred = (
            [a for a in actions if a.kind is ActionKind.PASS]
            or [a for a in actions if a.kind is ActionKind.FINISH_DECLARATION]
            or [a for a in actions if a.kind is ActionKind.NO]
            or actions
        )
        game.apply(preferred[0])


def bolt_targets(game, caster: int) -> set[tuple[str, int]]:
    """Every ``(kind, id)`` ``caster`` is offered for the Bolt."""
    return {
        (ref.kind, ref.id)
        for action in game.legal_actions()
        if action.kind is ActionKind.CAST
        and action.source is not None
        and game.state.objects[action.source].def_id == BOLT
        and game.state.objects[action.source].controller == caster
        for ref in action.targets
    }


class TestTheGrant:
    def test_resolving_it_gives_the_caster_hexproof(self, builder):
        game = position(builder)
        assert player_has_hexproof(game.state, 1)
        assert not player_has_hexproof(game.state, 0)

    def test_without_it_the_player_has_none(self, builder):
        """The control: the hexproof comes from the spell and nothing else."""
        game = position(builder, granted=False)
        assert not player_has_hexproof(game.state, 1)

    def test_the_permanents_half_still_lands(self, builder):
        game = position(builder)
        bear = oids_of(game, BEAR)[0]
        assert "hexproof" in chars(game.state, bear).keywords


class TestOpponentsCannotTarget:
    """Read at legality on seat 0's turn, with the record the op writes."""

    def _hexproof_on(self, builder, pid: int):
        game = (
            builder(players=2)
            .battlefield(0, ["mountain"] * 4)
            .battlefield(1, [BEAR])
            .hand(0, [BOLT])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .active(0)
            .build()
        )
        grant_player_hexproof(game.state, pid)
        return game

    def test_an_opponents_spell_cannot_target_the_player(self, builder):
        targets = bolt_targets(self._hexproof_on(builder, 1), 0)
        assert ("player", 1) not in targets
        assert ("player", 0) in targets

    def test_the_player_may_still_target_themself(self, builder):
        """The line between hexproof and shroud or protection."""
        assert ("player", 0) in bolt_targets(self._hexproof_on(builder, 0), 0)


class TestTheWearingOff:
    def test_it_ends_in_the_cleanup_step(self, builder):
        game = position(builder)
        run_to_next_turn(game)
        assert game.state.active_idx == 0
        assert not player_has_hexproof(game.state, 1)
        assert ("player", 1) in bolt_targets(game, 0)


class TestTheLoaderRefusesNonsense:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_bad_player_hexproof",
                "name": "Bad Player Hexproof",
                "oracle_text": "Bad.",
                "mana_cost": "{U}",
                "types": ["Instant"],
                "colors": ["U"],
                "color_identity": ["U"],
                "spell_effects": [effect],
            }
        )

    def test_the_player_half_alone_loads(self):
        compile_card(self._card({"op": "grant_keyword", "keywords": ["hexproof"], "player": "each_player"}))

    def test_a_keyword_a_player_cannot_have(self):
        with pytest.raises(DslError, match="exactly"):
            compile_card(self._card({"op": "grant_keyword", "keywords": ["flying"], "player": "you"}))

    def test_hexproof_beside_another_word(self):
        with pytest.raises(DslError, match="exactly"):
            compile_card(
                self._card(
                    {"op": "grant_keyword", "keywords": ["hexproof", "indestructible"], "player": "you"}
                )
            )

    def test_a_clock_past_the_turn(self):
        with pytest.raises(DslError, match="until end of turn"):
            compile_card(
                self._card(
                    {
                        "op": "grant_keyword",
                        "keywords": ["hexproof"],
                        "player": "you",
                        "duration": "until_your_next_turn",
                    }
                )
            )
