""""Whenever you investigate for the first time each turn, investigate an additional time."

Erdwal Illuminator is the witness. Rule 701.16a makes investigating a keyword
action -- *create a Clue token* -- and the card watches the action, not the
token, so the engine has to know an investigation happened:

- `token_created` filtered to Clues is the near miss, and it is wrong both
  ways. "Create a Clue token" (Overencumbered) is not investigating, and one
  investigation whose Clue a token doubler doubles is still one investigation.
- `max_per_turn: 1` is the near miss for "for the first time each turn", and it
  is wrong the moment the Illuminator arrives after you have already
  investigated: that turn has had its first time, and a per-permanent cap
  would fire on the second.

So `investigate` is an op, each investigation fires one `INVESTIGATED` after its
Clue, and the event carries the investigation's ordinal for its player this
turn, counted by the ledger whether or not anything listened.

The claims this file pins:

- **One investigation, one Clue, one event, in that order.** "Investigate
  twice" is two of each, ordinals 1 and 2.
- **Creating a Clue is not investigating**, and a doubled Clue is one event.
- **The investigator is `player`**, and the event is theirs.
- **The first time each turn is the turn's first**, not the Illuminator's: its
  own extra investigation is the second and does not re-trigger, a later one
  does not trigger, and one made before it arrived leaves it nothing.
- **"You" is you**: an opponent investigating does not trigger it.
- The loader refuses `create_token`'s spellings on the op.
"""

from __future__ import annotations

import json

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of, settle

ILLUMINATOR = "erdwal_illuminator"
CLUE = "clue_token"
DOUBLER = "doubling_season"
BEAR = "t_bear"


def position(builder, *, mine=(ILLUMINATOR,), theirs=(BEAR,)):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, [BEAR] * 10)
        .library(1, [BEAR] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def run(game, spec, *, controller=0) -> None:
    """Resolve one effect op outside any spell, as `test_connives` does."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    result = OPS[spec["op"]](ctx, spec)
    if result is not None:
        for _ in result:
            raise AssertionError("investigating asks no questions")


def investigate(game, *, amount=1, player="you", controller=0) -> None:
    run(
        game,
        {"op": "investigate", "amount": {"const": amount}, "player": player},
        controller=controller,
    )


def resolve(game) -> None:
    """Let queued triggers reach the stack and resolve (see `test_connives`).

    Nothing queued is nothing to do: with an empty stack, passing would walk
    the game into later turns, whose ledgers start again.
    """
    if not game.state.pending_triggers and not game.state.stack:
        return
    game._advance()
    settle(game)


def investigations(game) -> list:
    return [e for e in game.state.events if e.type == EventType.INVESTIGATED]


def clues(game, pid=0) -> int:
    return len(oids_of(game, CLUE, pid))


class TestOneInvestigationOneEvent:
    def test_an_investigation_makes_a_clue_then_fires(self, builder):
        game = position(builder, mine=())
        investigate(game)
        (event,) = investigations(game)
        assert event.player == 0
        assert event.data["nth"] == 1
        assert clues(game) == 1
        kinds = [e.type for e in game.state.events]
        assert EventType.TOKEN_CREATED in kinds[: kinds.index(EventType.INVESTIGATED)], (
            "the investigation is finished -- its Clue made -- when it is heard"
        )

    def test_investigate_twice_is_two_investigations(self, builder):
        game = position(builder, mine=())
        investigate(game, amount=2)
        assert [e.data["nth"] for e in investigations(game)] == [1, 2]
        assert clues(game) == 2

    def test_investigate_zero_times_is_none(self, builder):
        game = position(builder, mine=())
        investigate(game, amount=0)
        assert investigations(game) == []
        assert clues(game) == 0

    def test_the_ordinal_is_per_player(self, builder):
        game = position(builder, mine=())
        investigate(game)
        investigate(game, player="each_opponent")
        assert [(e.player, e.data["nth"]) for e in investigations(game)] == [(0, 1), (1, 1)]

    def test_the_count_starts_again_each_turn(self, builder):
        game = position(builder, mine=())
        investigate(game)
        game.state.turn_ledger.clear()  # what cleanup does
        investigate(game)
        assert [e.data["nth"] for e in investigations(game)] == [1, 1]


class TestCreatingAClueIsNotInvestigating:
    def test_create_token_naming_a_clue_fires_nothing(self, builder):
        game = position(builder, mine=())
        run(game, {"op": "create_token", "token": CLUE})
        assert clues(game) == 1
        assert investigations(game) == []

    def test_a_doubled_clue_is_one_investigation(self, builder):
        game = position(builder, mine=(DOUBLER,))
        investigate(game)
        assert clues(game) == 2, "Doubling Season doubles the Clue"
        assert len(investigations(game)) == 1

    def test_the_investigator_gets_the_clue(self, builder):
        game = position(builder, mine=())
        investigate(game, player="each_opponent")
        assert clues(game, 1) == 1
        assert clues(game, 0) == 0
        (event,) = investigations(game)
        assert event.player == 1


class TestTheFirstTimeEachTurn:
    def test_the_first_investigation_investigates_again(self, builder):
        game = position(builder)
        investigate(game)
        resolve(game)
        assert clues(game) == 2
        assert [e.data["nth"] for e in investigations(game)] == [1, 2], (
            "the Illuminator's own investigation is the second and does not "
            "trigger it again"
        )

    def test_a_later_investigation_does_not_trigger(self, builder):
        game = position(builder)
        investigate(game)
        resolve(game)
        investigate(game)
        resolve(game)
        assert clues(game) == 3

    def test_investigate_twice_triggers_once(self, builder):
        game = position(builder)
        investigate(game, amount=2)
        resolve(game)
        assert clues(game) == 3

    def test_an_investigation_before_it_arrived_spends_the_first_time(self, builder):
        game = (
            builder(players=2)
            .hand(0, [ILLUMINATOR])
            .library(0, [BEAR] * 10)
            .library(1, [BEAR] * 10)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        investigate(game)
        (card,) = game.state.players[0].hand
        move_object(game.state, card, Zone.BATTLEFIELD)
        investigate(game)
        resolve(game)
        assert clues(game) == 2, (
            "the turn's first investigation came before the Illuminator; a "
            "max_per_turn cap would have fired on the second"
        )

    def test_an_opponent_investigating_does_not_trigger(self, builder):
        game = position(builder)
        investigate(game, player="each_opponent", controller=0)
        resolve(game)
        assert clues(game, 0) == 0
        assert clues(game, 1) == 1


class TestTheLoader:
    def model(self, effect, trigger=None):
        return CardModel.model_validate(
            {
                "id": "t_investigator",
                "name": "Investigator",
                "oracle_text": "x",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "x",
                        "trigger": trigger or {"event": "self_enters", "source": "self"},
                        "effects": [effect],
                    }
                ],
            }
        )

    @pytest.mark.parametrize("key", ["token", "controller"])
    def test_create_tokens_spellings_are_refused(self, key):
        with pytest.raises(DslError, match="investigate names its own Clue"):
            compile_card(self.model({"op": "investigate", key: "you"}))

    def test_nth_loads_on_investigates(self):
        compile_card(
            self.model(
                {"op": "investigate"},
                {"event": "investigates", "controller": "you", "nth": 1},
            )
        )


class TestEveryShippedInvestigationIsOne:
    """A card that says "investigate" and spells it `create_token` would make
    its Clue and never be heard investigating -- Erdwal Illuminator silent
    beside it, and nothing else would notice."""

    def test_no_card_that_investigates_creates_its_clue_by_hand(self):
        from tests.conftest import CARD_DIR

        def clue_makers(node):
            if isinstance(node, dict):
                if node.get("op") == "create_token" and node.get("token") == CLUE:
                    yield node
                for value in node.values():
                    yield from clue_makers(value)
            elif isinstance(node, list):
                for value in node:
                    yield from clue_makers(value)

        offenders, investigators = [], 0
        for path in sorted(CARD_DIR.rglob("*.cards.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            for card in raw if isinstance(raw, list) else raw.get("cards", []):
                if "investigate" not in card.get("oracle_text", "").lower():
                    continue
                investigators += 1
                if any(clue_makers(card)):
                    offenders.append(card["id"])
        assert investigators, "no card investigates -- the scan read nothing"
        assert offenders == [], f"investigate with the `investigate` op: {offenders}"
