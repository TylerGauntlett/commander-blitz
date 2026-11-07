""""…each player draws cards equal to the amount of damage dealt to Grothama
this turn by sources **they** controlled."

    Grothama, All-Devouring — Legendary Creature — Wurm
    "When Grothama leaves the battlefield, each player draws cards equal to
    the amount of damage dealt to Grothama this turn by sources they
    controlled."

The question is asked as Grothama leaves the battlefield, which is exactly
when the answer is wiped off the permanent: `reset_permanent_state` zeroes the
marked damage on the way out (and 514.2 would at cleanup). So it is read off
`TurnLedger.damage_to_permanents`, folded off every DAMAGE_DEALT, keyed by the
permanent's oid and split by the source's controller.

What each near miss gets wrong, and the claim below that pins it:

* **``damage_taken_this_turn``** counts damage to players.
* **``GameState.damage_ledger``** records who damaged a permanent, never how
  much.
* **The source's controller now** rather than as the damage was dealt (120.1,
  608.2h): a creature that hit Grothama and was then stolen would hand its blow
  to the thief.
* **Damage that would have been dealt** rather than damage dealt (120.3,
  615): a prevented blow draws nothing.
* **Keyed by oid with no 400.7 boundary**: an oid survives a zone change, so a
  Grothama that was flickered would carry the old object's damage into the new
  one's leave trigger.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import change_control, damage_permanent
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.zones import move_object
from tests.conftest import advance_to_step, only_oid, settle

GROTHAMA = "dd_grothama"  # 10/8; leaves: each player draws their share
WARDED = "dd_grothama_pro_red"  # the same, with protection from red
OX = "dd_ox"  # a green 2/2 to deal the damage
RED_OX = "dd_red_ox"  # a red 2/2, for protection

LINE = (
    "When Grothama leaves the battlefield, each player draws cards equal to the "
    "amount of damage dealt to Grothama this turn by sources they controlled."
)

SHARE = {
    "damage_dealt_to_this_turn": {"to": {"self": True}, "by": {"binding": "each_player"}}
}


def _grothama(card_id: str, statics: list[dict] = ()) -> dict:
    return {
        "id": card_id,
        "name": card_id.replace("_", " ").title(),
        "oracle_text": LINE,
        "mana_cost": "{6}{G}",
        "types": ["Creature"],
        "supertypes": ["Legendary"],
        "subtypes": ["Wurm"],
        "power": 10,
        "toughness": 8,
        "abilities": [
            *statics,
            {
                "kind": "triggered",
                "text": LINE,
                "trigger": {"event": "leaves_battlefield", "source": "self"},
                "effects": [
                    {
                        "op": "for_each_player",
                        "players": "each_player",
                        "effects": [
                            {"op": "draw", "player": {"binding": "each_player"},
                             "amount": SHARE}
                        ],
                    }
                ],
            },
        ],
    }


def _ox(card_id: str, color: str) -> dict:
    return {
        "id": card_id,
        "name": card_id.replace("_", " ").title(),
        "oracle_text": "{T}: You gain 1 life.",
        "mana_cost": "{1}{" + color + "}",
        "colors": [color],
        "types": ["Creature"],
        "subtypes": ["Ox"],
        "power": 2,
        "toughness": 2,
        # Something to do with priority, so the engine stops and asks rather
        # than auto-passing its controller through the turn.
        "abilities": [
            {
                "kind": "activated",
                "text": "{T}: You gain 1 life.",
                "cost": {"tap": True},
                "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
            }
        ],
    }


PRO_RED = {
    "kind": "static",
    "text": "Protection from red",
    "effect": "protection",
    "from_colors": ["R"],
    "affects": {"self_only": True},
}


@pytest.fixture(scope="module")
def pool(registry) -> CardRegistry:
    cards = {card.id: card for card in registry}
    for spec in (
        _grothama(GROTHAMA),
        _grothama(WARDED, [PRO_RED]),
        _ox(OX, "G"),
        _ox(RED_OX, "R"),
    ):
        compiled = compile_card(CardModel.model_validate(spec))
        cards[compiled.id] = compiled
    return CardRegistry(cards)


def position(pool, grothama: str = GROTHAMA, theirs: str = OX):
    """Grothama and an ox on seat 0, an ox on seat 1, seat 0's main phase.

    Returns ``(game, grothama, my_ox, their_ox)``.
    """
    game = (
        GameBuilder(pool, players=2, seed=0)
        .battlefield(0, [grothama, OX])
        .battlefield(1, [theirs])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    return (
        game,
        only_oid(game, grothama, 0),
        only_oid(game, OX, 0),
        only_oid(game, theirs, 1),
    )


def hand(game, pid: int) -> int:
    return len(game.state.zone_list(Zone.HAND, pid))


def run(game) -> None:
    """Let the engine drain what a direct board change triggered, and resolve it.

    The position is built without advancing, so the first `Game._advance`
    starts the engine; after that a decision is standing, it returns at once,
    and `settle`'s first pass is what drains the trigger.
    """
    game._advance()
    settle(game)


def leave(game, oid: int, to: Zone = Zone.GRAVEYARD) -> tuple[int, int]:
    """Move Grothama off the battlefield, resolve its trigger; who drew what."""
    before = hand(game, 0), hand(game, 1)
    move_object(game.state, oid, to)
    run(game)
    return hand(game, 0) - before[0], hand(game, 1) - before[1]


class TestEachPlayerDrawsTheirOwnShare:
    def test_split_by_whose_source_dealt_it(self, pool):
        game, wurm, mine, theirs = position(pool)
        damage_permanent(game.state, wurm, 2, mine)
        damage_permanent(game.state, wurm, 3, theirs)

        assert leave(game, wurm) == (2, 3)

    def test_blows_from_one_player_add_up(self, pool):
        game, wurm, _, theirs = position(pool)
        damage_permanent(game.state, wurm, 2, theirs)
        damage_permanent(game.state, wurm, 2, theirs)

        assert leave(game, wurm) == (0, 4)

    def test_undamaged_draws_nothing(self, pool):
        game, wurm, _, _ = position(pool)
        assert leave(game, wurm) == (0, 0)

    def test_read_after_it_leaves_for_any_zone(self, pool):
        """Exile, not death: the leave trigger is the same, and so is the read."""
        game, wurm, _, theirs = position(pool)
        damage_permanent(game.state, wurm, 3, theirs)

        assert leave(game, wurm, Zone.EXILE) == (0, 3)


class TestTheControllerAsTheDamageWasDealt:
    def test_a_source_stolen_afterwards_keeps_its_blow(self, pool):
        """120.1 / 608.2h: whose source it was is fixed as the damage is dealt."""
        game, wurm, _, theirs = position(pool)
        damage_permanent(game.state, wurm, 2, theirs)
        change_control(game.state, theirs, 0)

        assert leave(game, wurm) == (0, 2)


class TestOnlyDamageActuallyDealt:
    def test_prevented_damage_draws_nothing(self, pool):
        """Protection prevents the damage (702.16e), so none was dealt (120.3)."""
        game, wurm, mine, red = position(pool, grothama=WARDED, theirs=RED_OX)
        damage_permanent(game.state, wurm, 3, red)
        damage_permanent(game.state, wurm, 1, mine)

        assert leave(game, wurm) == (1, 0)


class TestANewObjectStartsClean:
    def test_a_flickered_grothama_does_not_inherit_the_old_damage(self, pool):
        """400.7. The oid survives the trip; the object, and its damage, do not.

        Its first departure still reads the 3 (last-known information), and the
        Grothama that comes back has been dealt nothing.
        """
        game, wurm, _, theirs = position(pool)
        damage_permanent(game.state, wurm, 3, theirs)
        assert leave(game, wurm, Zone.EXILE) == (0, 3)

        move_object(game.state, wurm, Zone.BATTLEFIELD)
        assert leave(game, wurm) == (0, 0)

    def test_last_turns_damage_is_forgotten(self, pool):
        """"This turn": the ledger is cleared at cleanup, with the marked damage (514.2)."""
        game, wurm, _, theirs = position(pool)
        damage_permanent(game.state, wurm, 3, theirs)
        turn = game.state.turn
        game._advance()
        advance_to_step(game, Step.UPKEEP)
        assert game.state.turn == turn + 1

        assert leave(game, wurm) == (0, 0)


class TestTheValue:
    def _ctx(self, game, source: int) -> EffectContext:
        return EffectContext(state=game.state, controller=0, source_oid=source)

    def test_without_by_it_is_all_of_it(self, pool):
        game, wurm, mine, theirs = position(pool)
        damage_permanent(game.state, wurm, 2, mine)
        damage_permanent(game.state, wurm, 3, theirs)
        ctx = self._ctx(game, wurm)

        assert evaluate_value(ctx, {"damage_dealt_to_this_turn": {"to": {"self": True}}}) == 5
        assert evaluate_value(
            ctx, {"damage_dealt_to_this_turn": {"to": {"self": True}, "by": "you"}}
        ) == 2
        assert evaluate_value(
            ctx, {"damage_dealt_to_this_turn": {"to": {"self": True}, "by": "each_opponent"}}
        ) == 3

    def test_another_permanent_reads_its_own(self, pool):
        game, wurm, mine, theirs = position(pool)
        damage_permanent(game.state, wurm, 3, theirs)

        assert evaluate_value(
            self._ctx(game, mine), {"damage_dealt_to_this_turn": {"to": {"self": True}}}
        ) == 0


class TestTheLoader:
    @pytest.mark.parametrize(
        "spec, message",
        [
            ({}, "needs 'to'"),
            ({"by": "you"}, "needs 'to'"),
            ({"to": True}, "object reference"),
            ({"to": {"self": True}, "by": "they"}, "player spec"),
            ({"to": {"self": True}, "combat": True}, "unsupported keys"),
            ("self", "must be an object"),
        ],
    )
    def test_malformed_is_refused(self, spec, message):
        with pytest.raises(DslError, match=message):
            validate_value({"damage_dealt_to_this_turn": spec}, "probe")

    def test_the_card_compiles(self):
        compile_card(CardModel.model_validate(_grothama("dd_probe")))
