""""Whenever you win a coin flip, create two tapped Treasure tokens."

Setzer, Wandering Gambler is the witness. Rule 705 makes a coin flip an act with
an outcome, and the card watches the *outcome* -- any flip its controller wins,
whatever made them flip. `flip_coin` already emitted `COIN_FLIPPED` carrying
``won``, but only into the log, and no trigger had a name for it.

The near miss is wrong rather than merely absent: Setzer's second ability flips
a coin, and hanging the Treasures on that flip's win branch makes a narrower
card -- it pays for the flips that one ability makes and never for a flip won
off Okaun, a Fiery Gambit or any other source.

So `op_flip_coin` fires the event through the trigger bus and `wins_coin_flip`
listens for it. The claims this file pins:

- **A win, and only a win.** A lost flip fires the same event and pays
  nothing; an event that forgot to say ``won`` pays nothing either.
- **One win, one trigger.** Two flips won in one resolution are two.
- **The flipper is the actor.** `controller: "you"` compares the player who
  flipped, never the source of the flip, so my win off an opponent's card
  counts and an opponent's win does not.
- **Any source.** The flip need not be the watcher's own.
- **It follows its source.** No watcher on the battlefield, no trigger.
"""

from __future__ import annotations

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.events import EventType
from commanderblitz.engine.rng import Rng
from commanderblitz.engine.triggers import fire
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of, only_oid, settle

GAMBLER = "t_coin_flip_gambler"  # Whenever you win a coin flip, create two tapped Treasures.
BEAR = "t_bear"
TREASURE = "treasure_token"

FLIP = {"op": "flip_coin", "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}]}


def seed_for(*outcomes: bool) -> int:
    """A seed whose first flips come down as ``outcomes`` (True is a win)."""
    for seed in range(1000):
        rng = Rng(seed)
        if all((rng.randint(0, 1) == 1) is won for won in outcomes):
            return seed
    raise AssertionError(f"no seed flips {outcomes}")


def position(builder, *, mine=(GAMBLER,), theirs=(BEAR,), outcomes=(True,)):
    """Player 0 holds the gambler, player 1 a bear; the rng flips ``outcomes``."""
    seed = seed_for(*outcomes)
    game = (
        builder(players=2, seed=seed)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build(advance=False)
    )
    game.state.rng = Rng(seed)
    return game


def flip(game, controller: int, *, source: int | None = None, times: int = 1) -> None:
    """``controller`` flips ``times`` coins, made to by ``source``."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    assert list(execute(ctx, [FLIP] * times)) == [], "a flip asks nobody anything"


def flips(game) -> list:
    return [e for e in game.state.events if e.type == EventType.COIN_FLIPPED]


def queued(game) -> int:
    """How many gambler triggers are waiting to go on the stack."""
    return sum(
        1 for t in game.state.pending_triggers if game.state.objects[t.source_oid].def_id == GAMBLER
    )


class TestAWinAndOnlyAWin:
    def test_a_won_flip_triggers(self, builder):
        game = position(builder, outcomes=(True,))
        flip(game, 0)
        assert [e.data["won"] for e in flips(game)] == [True]
        assert queued(game) == 1

    def test_a_lost_flip_does_not(self, builder):
        game = position(builder, outcomes=(False,))
        flip(game, 0)
        assert [e.data["won"] for e in flips(game)] == [False], "the coin was still flipped"
        assert queued(game) == 0

    def test_an_event_that_does_not_say_won_does_not(self, builder):
        """Wider is the dangerous direction: a silent outcome is no win."""
        game = position(builder)
        fire(game.state, EventType.COIN_FLIPPED, player=0)
        assert queued(game) == 0


class TestOneWinOneTrigger:
    def test_two_wins_in_one_resolution_are_two(self, builder):
        game = position(builder, outcomes=(True, True))
        flip(game, 0, times=2)
        assert queued(game) == 2

    def test_a_win_and_a_loss_are_one(self, builder):
        game = position(builder, outcomes=(False, True))
        flip(game, 0, times=2)
        assert len(flips(game)) == 2
        assert queued(game) == 1


class TestTheFlipperIsTheActor:
    def test_an_opponent_winning_does_not_trigger_mine(self, builder):
        game = position(builder, outcomes=(True,))
        flip(game, 1)
        assert queued(game) == 0

    def test_my_win_off_an_opponents_card_triggers(self, builder):
        """The source is their bear; the flip and the win are mine."""
        game = position(builder, outcomes=(True,))
        flip(game, 0, source=only_oid(game, BEAR))
        assert queued(game) == 1

    def test_their_gambler_ignores_my_win(self, builder):
        game = position(builder, mine=(), theirs=(GAMBLER,), outcomes=(True,))
        flip(game, 0)
        assert queued(game) == 0, "the gambler is player 1's; player 0 won"


class TestAnySource:
    def test_a_flip_with_no_source_still_counts(self, builder):
        game = position(builder, outcomes=(True,))
        flip(game, 0, source=None)
        assert queued(game) == 1

    def test_the_gamblers_own_flip_counts(self, builder):
        game = position(builder, outcomes=(True,))
        flip(game, 0, source=only_oid(game, GAMBLER))
        assert queued(game) == 1


class TestItFollowsItsSource:
    def test_no_gambler_no_trigger(self, builder):
        game = position(builder, mine=(), outcomes=(True,))
        flip(game, 0)
        assert len(flips(game)) == 1, "the event is the game's, not the card's"
        assert game.state.pending_triggers == []

    def test_it_stops_when_the_gambler_leaves(self, builder):
        game = position(builder, outcomes=(True,))
        move_object(game.state, only_oid(game, GAMBLER), Zone.GRAVEYARD)
        flip(game, 0)
        assert queued(game) == 0


class TestEndToEnd:
    def test_a_win_makes_two_tapped_treasures(self, builder):
        game = position(builder, outcomes=(True,))
        flip(game, 0)
        game._advance()
        settle(game)
        treasures = oids_of(game, TREASURE, 0)
        assert len(treasures) == 2
        assert all(game.state.objects[oid].tapped for oid in treasures)

    def test_a_loss_makes_none(self, builder):
        game = position(builder, outcomes=(False,))
        flip(game, 0)
        game._advance()
        settle(game)
        assert oids_of(game, TREASURE, 0) == []


class TestTheLoader:
    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card({"event": "wins_coin_flip"})))

    def test_an_opponent_shape_loads(self):
        trigger = {"event": "wins_coin_flip", "controller": "opponent"}
        compile_card(CardModel.model_validate(_card(trigger)))


def _card(trigger: dict) -> dict:
    text = "Whenever you win a coin flip, create two tapped Treasure tokens."
    return {
        "id": "t_bare_gambler",
        "name": "Test Bare Gambler",
        "oracle_text": text,
        "mana_cost": "{2}{R}",
        "types": ["Creature"],
        "power": 2,
        "toughness": 2,
        "abilities": [
            {
                "kind": "triggered",
                "text": text,
                "trigger": trigger,
                "effects": [
                    {
                        "op": "create_token",
                        "token": TREASURE,
                        "amount": {"const": 2},
                        "tapped": True,
                    }
                ],
            }
        ],
    }
