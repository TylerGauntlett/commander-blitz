""""When a spell or ability an opponent controls causes you to discard this card."

Orvar, the All-Form's third line. A trigger that fires **from the hand**, on the
card being discarded, and only when somebody else made it happen.

The `DISCARD` event carried `player`, `source` and `oid` — the player who
discarded and the card — and nothing about *who caused it*. That is not a detail:
the same event covers an opponent's Mind Rot, your own rummaging, a cost you paid
with this very card, and the cleanup-step discard, and the printed line fires on
exactly one of the four.

`controller` is the near miss and is the wrong question. On a discard trigger
`_actor` answers it with `event.player`, the player who *discarded*, so
`controller: "opponent"` reads "an opponent discarded a card". `not_cause`
compares `event.data["cause"]`, which a discard never set. `cause_controller`,
`cause_events` and `cause_filter` existed only on the `double_triggers` static —
read from a battlefield permanent, not from a triggered ability, and never for
DISCARD.

So `discard_cards` takes a `caused_by` and puts it on the event, and
`cause_controller` is the trigger clause that reads it. **`None` is the load-
bearing value**: an event nobody caused fails the clause in every direction,
which is the whole of what keeps this from being a card that also fires on its
controller's own discards.

`t_loose_orvar` is that card, kept live. It is the approximation the gap record
refused to write, and `TestTheUnclausedSpellingIsStronger` measures it firing on
all three discards the printed card ignores.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError

ORVAR = "t_forced_orvar"  # with the cause clause
LOOSE = "t_loose_orvar"  # without it -- the stronger card
MIND_ROT = "t_mind_rot"  # an opponent's forced discard
RUMMAGE = "t_rummage"  # your own discard
BEAR = "t_bear"
ISLAND = "island"
SWAMP = "swamp"


def position(builder, *, orvar: str = ORVAR, caster: int, spell: str):
    """``caster`` casts ``spell``; player 0 holds the Orvar card in hand.

    Player 0's hand is sized so that a two-card discard *must* include the Orvar
    card -- two cards when the opponent is casting, and three when player 0 is,
    since casting the Rummage spends one of them first. The auto-answer picks the
    first legal option, so a hand with a spare would let it discard around the
    card under test and every assertion below would pass vacuously.

    A Bear on the battlefield gives the trigger's target something to be.
    """
    return (
        builder(players=2)
        .battlefield(0, [ISLAND] * 4 + [BEAR])
        .battlefield(1, [SWAMP] * 4)
        .hand(0, [orvar, RUMMAGE, RUMMAGE] if caster == 0 else [orvar, BEAR])
        .hand(1, [spell] if caster == 1 else [])
        .library(0, ["plains"] * 10)
        .library(1, ["plains"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(caster)
        .build(advance=False)
    )


def cast(game, card_id: str, pid: int, limit: int = 200) -> None:
    from tests.conftest import _default_answer

    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            game._advance()
            decision = game.pending()
            if decision is None:
                return
        if decision.kind is DecisionKind.PRIORITY and decision.player == pid:
            action = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CAST
                    and game.state.objects[a.source].def_id == card_id
                ),
                None,
            )
            if action is not None:
                game.apply(action)
                for _ in range(limit):
                    if not game.state.stack and not game.state.pending_triggers:
                        return
                    d = game.pending()
                    if d is None:
                        return
                    game.apply(_default_answer(game, d))
                return
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"never cast {card_id} as player {pid}")


def discarded(game, card_id: str) -> bool:
    return any(game.state.objects[o].def_id == card_id for o in game.state.players[0].graveyard)


def tokens(game) -> int:
    return sum(1 for oid in game.state.battlefield if game.state.objects[oid].is_token)


class TestAnOpponentsSpellFiresIt:
    def test_mind_rot_makes_a_token(self, builder):
        game = position(builder, caster=1, spell=MIND_ROT)
        cast(game, MIND_ROT, 1)
        assert discarded(game, ORVAR), "the card really was discarded"
        assert tokens(game) == 1


class TestYourOwnDiscardDoesNot:
    """The distinction the event could not previously make."""

    def test_your_own_rummaging_does_not_fire_it(self, builder):
        game = position(builder, caster=0, spell=RUMMAGE)
        cast(game, RUMMAGE, 0)
        assert discarded(game, ORVAR), "the card really was discarded"
        assert tokens(game) == 0, "you caused this one"


class TestTheUnclausedSpellingIsStronger:
    """Kept as a live card: the approximation the gap record refused to write."""

    def test_it_fires_on_an_opponents_discard_too(self, builder):
        """The half it gets right, so the difference below is only the clause."""
        game = position(builder, orvar=LOOSE, caster=1, spell=MIND_ROT)
        cast(game, MIND_ROT, 1)
        assert tokens(game) == 1

    def test_but_also_on_your_own(self, builder):
        game = position(builder, orvar=LOOSE, caster=0, spell=RUMMAGE)
        cast(game, RUMMAGE, 0)
        assert discarded(game, LOOSE)
        assert tokens(game) == 1, "the control: no cause clause, so nothing distinguishes them"


class TestTheEventCarriesTheCause:
    """Read directly, so the clause and the payload cannot drift apart."""

    def test_an_opponents_spell_records_that_opponent(self, builder):
        from commanderblitz.engine.events import EventType

        game = position(builder, caster=1, spell=MIND_ROT)
        cast(game, MIND_ROT, 1)
        events = [e for e in game.state.events if e.type is EventType.DISCARD]
        assert events and all(e.data.get("cause_controller") == 1 for e in events)

    def test_your_own_spell_records_you(self, builder):
        from commanderblitz.engine.events import EventType

        game = position(builder, caster=0, spell=RUMMAGE)
        cast(game, RUMMAGE, 0)
        events = [e for e in game.state.events if e.type is EventType.DISCARD]
        assert events and all(e.data.get("cause_controller") == 0 for e in events)


class TestAnUncausedDiscardFailsTheClause:
    """A cleanup-step discard and a discard paid as a cost are nobody's doing.

    Asserted at the primitive, because both routes reach `discard_cards` without
    passing a cause and the point is precisely that `None` is not a player.
    """

    def test_discard_cards_records_no_cause_by_default(self, builder):
        from commanderblitz.engine.events import EventType
        from commanderblitz.engine.primitives import discard_cards

        game = position(builder, caster=0, spell=RUMMAGE)
        oid = game.state.players[0].hand[0]
        discard_cards(game.state, 0, [oid])
        events = [e for e in game.state.events if e.type is EventType.DISCARD]
        assert events and events[-1].data.get("cause_controller") is None

    def test_and_the_trigger_does_not_fire_on_it(self, builder):
        game = position(builder, caster=0, spell=RUMMAGE)
        from commanderblitz.engine.primitives import discard_cards

        oid = next(
            o for o in game.state.players[0].hand if game.state.objects[o].def_id == ORVAR
        )
        discard_cards(game.state, 0, [oid])
        game._advance()
        assert tokens(game) == 0


class TestTheLoader:
    def card(self, **trigger):
        spec = {"event": "discard", "controller": "you", "filter": {"self_only": True}}
        spec.update(trigger)
        return {
            "id": "t_probe_forced",
            "name": "Probe Forced",
            "mana_cost": "{U}",
            "types": ["Creature"],
            "subtypes": ["Shapeshifter"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "When a spell or ability an opponent controls causes you to discard this card, you gain 1 life.",
                    "active_zones": ["hand"],
                    "trigger": spec,
                    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }

    def test_the_ordinary_shape_compiles(self):
        card = compile_card(CardModel.model_validate(self.card(cause_controller="opponent")))
        assert card.abilities[0].trigger.cause_controller == "opponent"

    def test_it_is_refused_on_another_event(self):
        """No other event records what caused it, so the clause would never fire."""
        with pytest.raises(DslError, match="only means anything on 'discard'"):
            compile_card(
                CardModel.model_validate(self.card(event="draw", cause_controller="opponent"))
            )

    def test_an_unknown_value_is_refused(self):
        with pytest.raises(DslError, match="unknown cause_controller"):
            compile_card(CardModel.model_validate(self.card(cause_controller="nobody")))
