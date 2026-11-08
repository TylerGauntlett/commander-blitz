""""Whenever you give a gift, draw a card."

Jolly Gerbils is the witness. Rule 702.174 makes giving a gift a moment of its
own, distinct from promising it: an instant or sorcery with a promised gift
gives it as the spell resolves, the gift's effect first, and a permanent's gift
is its enters trigger ("if you do, when it enters, they create an 8/8 blue
Octopus" -- Octomancer). The trigger watches that moment, so it needs an event
fired *where the gift is given*, which nothing in the engine had.

The near miss is wrong rather than merely early: `spell_cast` with a filter
fires on the **promise**, so it pays for a gift spell that is then countered
and for a permanent spell that never enters to give its gift.

So `GIFT_GIVEN` is fired from `stack`: as a gift spell resolves past its 608.2b
target check, or as the one triggered ability `CardDef.gift_ability` names
resolves past its intervening-if. The claims this file pins:

- **A promised gift fires once; an unpromised one never.** One gift spell, one
  event, naming the giver and the recipient.
- **A countered gift was never given.** A spell whose only target left
  resolves to nothing (608.2b) and gives nothing.
- **A permanent gives its gift as its gift trigger resolves**, and only that
  trigger: a second enters trigger that merely reads the promise (Scrapshooter's
  "if the gift was promised, destroy target artifact") is not a second gift.
- **The giver is the actor.** `controller: "you"` is the giver, never the
  recipient; an opponent's gift is `controller: "opponent"`.
- **`gift_to` is the recipient**, for a card that rewards or punishes them.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, only_oid

WATCHER = "t_gift_watcher"  # Whenever you give a gift, draw a card. -- Jolly Gerbils
RIVAL = "t_gift_rival_watcher"  # Whenever an opponent gives a gift, you gain 1 life.
TOLL = "t_gift_toll"  # ... the player you gave it to loses 1 life.
GIFT = "t_gift"  # {1}{W} instant, gift a tapped Fish -- Parting Gust
ENTERS = "t_gift_enters"  # {1}{G} 2/2, gift a card as its enters trigger
VICTIM = "grizzly_bears"


def position(builder, *, caster: int = 0, card: str = GIFT, mine=(WATCHER,), theirs=()):
    """``caster`` holds ``card`` and the mana for it, in their own main phase.

    Each side has a Grizzly Bears for Parting Gust to exile. The Bolt in hand
    is a priority stop, as in `tests/unit/keywords/test_gift.py`:
    ``full_control`` only holds a window open when something other than Pass
    is legal, and without one the spell resolves inside the cast's ``apply``.
    """
    lands = ["plains", "forest", "plains", "forest", "mountain"]
    game = (
        builder(players=2)
        .hand(caster, [card, "lightning_bolt"])
        .battlefield(caster, lands)
        .battlefield(0, [*mine, VICTIM])
        .battlefield(1, [*theirs, VICTIM])
        .active(caster)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game.state.players[caster].full_control = True
    game._advance()
    return game


def cast_line(game, card: str, *, promised: bool):
    """The cast of ``card`` on one side of the promise, aimed at a Bear if it aims."""
    bears = {oid for oid, obj in game.state.objects.items() if obj.def_id == VICTIM}
    return next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card
        and (a.gift_to is not None) == promised
        and all(ref.id in bears for ref in a.targets)
    )


def settle(game) -> None:
    """Answer everything until the stack and the trigger queue are both empty."""
    for _ in range(50):
        if not game.state.stack and not game.state.pending_triggers:
            return
        game.apply(_default_answer(game, game.pending()))
    raise AssertionError("the stack never emptied")


def gifts(game) -> list:
    return [e for e in game.state.events if e.type == EventType.GIFT_GIVEN]


def fired(game, card_id: str) -> int:
    """How many times ``card_id``'s trigger went on the stack."""
    oids = {oid for oid, obj in game.state.objects.items() if obj.def_id == card_id}
    return sum(
        1
        for e in game.state.events
        if e.type == EventType.ABILITY_TRIGGERED and e.source in oids
    )


class TestAPromisedGiftFiresOnce:
    def test_a_promised_instant_gives_one_gift(self, builder):
        game = position(builder)
        game.apply(cast_line(game, GIFT, promised=True))
        settle(game)
        (event,) = gifts(game)
        assert event.player == 0
        assert event.data["gift_to"] == 1
        assert event.data["card"] == GIFT
        assert fired(game, WATCHER) == 1

    def test_the_gift_is_given_before_the_spells_other_effects(self, builder):
        """702.174: "they create a tapped 1/1 blue Fish creature token **before
        its other effects**" -- the gift is given as the spell starts resolving."""
        game = position(builder)
        game.apply(cast_line(game, GIFT, promised=True))
        settle(game)
        kinds = [e.type for e in game.state.events]
        assert kinds.index(EventType.GIFT_GIVEN) < kinds.index(EventType.TOKEN_CREATED)

    def test_the_watcher_draws(self, builder):
        game = position(builder)
        hand = len(game.state.players[0].hand)
        game.apply(cast_line(game, GIFT, promised=True))
        settle(game)
        # The Gust has left the hand and the Gerbils' card has arrived.
        assert len(game.state.players[0].hand) == hand - 1 + 1


class TestAnUnpromisedGiftIsNoGift:
    def test_an_unpromised_instant_fires_nothing(self, builder):
        game = position(builder)
        game.apply(cast_line(game, GIFT, promised=False))
        settle(game)
        assert gifts(game) == []
        assert fired(game, WATCHER) == 0

    def test_a_countered_gift_spell_gave_nothing(self, builder):
        """Both Bears gone in response: the Gust resolves to nothing (608.2b)."""
        game = position(builder)
        game.apply(cast_line(game, GIFT, promised=True))
        for bear in [oid for oid, o in game.state.objects.items() if o.def_id == VICTIM]:
            move_object(game.state, bear, Zone.GRAVEYARD)
        settle(game)
        assert any(e.type == EventType.SPELL_FIZZLED for e in game.state.events)
        assert gifts(game) == []
        assert fired(game, WATCHER) == 0

    def test_the_promise_alone_is_not_the_gift(self, builder):
        """On the stack, promised and cast, nothing has been given yet."""
        game = position(builder)
        game.apply(cast_line(game, GIFT, promised=True))
        assert game.state.stack
        assert gifts(game) == []


class TestAPermanentGivesItsGiftAsItEnters:
    def test_the_gift_trigger_gives_one_gift(self, builder):
        game = position(builder, card=ENTERS)
        game.apply(cast_line(game, ENTERS, promised=True))
        settle(game)
        (event,) = gifts(game)
        assert event.player == 0
        assert event.data["gift_to"] == 1
        assert event.source == only_oid(game, ENTERS)
        assert fired(game, WATCHER) == 1

    def test_it_is_given_by_the_trigger_not_by_the_spell(self, builder):
        """The permanent spell resolving is not the gift; its enters trigger is."""
        game = position(builder, card=ENTERS)
        game.apply(cast_line(game, ENTERS, promised=True))
        kinds = [e.type for e in game.state.events]
        while game.state.stack and EventType.SPELL_RESOLVED not in kinds:
            game.apply(_default_answer(game, game.pending()))
            kinds = [e.type for e in game.state.events]
        assert gifts(game) == []
        settle(game)
        assert len(gifts(game)) == 1

    def test_an_unpromised_permanent_gives_nothing(self, builder):
        game = position(builder, card=ENTERS)
        game.apply(cast_line(game, ENTERS, promised=False))
        settle(game)
        assert gifts(game) == []
        assert fired(game, WATCHER) == 0

    def test_the_card_knows_which_ability_gives_it(self, registry):
        assert registry.get(ENTERS).gift_ability == 0
        assert registry.get(GIFT).gift_ability is None
        assert registry.get("octomancer").gift_ability == 0
        assert registry.get("scrapshooter").gift_ability == 0


class TestTheGiverIsTheActor:
    def test_an_opponents_gift_does_not_trigger_you(self, builder):
        game = position(builder, caster=1, mine=(WATCHER, RIVAL))
        game.apply(cast_line(game, GIFT, promised=True))
        settle(game)
        (event,) = gifts(game)
        assert event.player == 1
        assert event.data["gift_to"] == 0, "the recipient is not the giver"
        assert fired(game, WATCHER) == 0

    def test_an_opponent_clause_hears_it(self, builder):
        game = position(builder, caster=1, mine=(WATCHER, RIVAL))
        life = game.state.players[0].life
        game.apply(cast_line(game, GIFT, promised=True))
        settle(game)
        assert fired(game, RIVAL) == 1
        assert game.state.players[0].life == life + 1

    def test_your_own_gift_is_not_an_opponents(self, builder):
        game = position(builder, mine=(RIVAL,))
        game.apply(cast_line(game, GIFT, promised=True))
        settle(game)
        assert len(gifts(game)) == 1
        assert fired(game, RIVAL) == 0


class TestTheRecipientIsBound:
    def test_gift_to_names_the_player_who_got_it(self, builder):
        game = position(builder, mine=(TOLL,))
        mine, theirs = game.state.players[0].life, game.state.players[1].life
        game.apply(cast_line(game, GIFT, promised=True))
        settle(game)
        assert game.state.players[1].life == theirs - 1
        assert game.state.players[0].life == mine, "the giver is not the recipient"


class TestTheLoader:
    def test_two_abilities_giving_one_gift_are_refused(self):
        model = _creature()
        model["abilities"].append(dict(model["abilities"][0]))
        with pytest.raises(DslError, match="only one ability may give it"):
            compile_card(CardModel.model_validate(model))

    def test_the_printed_shape_loads(self):
        assert compile_card(CardModel.model_validate(_creature())).gift_ability == 0


def _creature() -> dict:
    text = "When this creature enters, if the gift was promised, they draw a card."
    return {
        "id": "t_bare_gift_enters",
        "name": "Test Bare Gift Enters",
        "oracle_text": f"Gift a card\n{text}",
        "mana_cost": "{1}{G}",
        "types": ["Creature"],
        "power": 2,
        "toughness": 2,
        "gift": "a card",
        "abilities": [
            {
                "kind": "triggered",
                "text": text,
                "trigger": {"event": "self_enters", "condition": {"gift_promised": True}},
                "effects": [{"op": "draw", "player": "gift_recipient", "amount": {"const": 1}}],
            }
        ],
    }
