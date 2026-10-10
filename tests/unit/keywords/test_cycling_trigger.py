""""When you cycle this card…" — a trigger on paying a cost.

Krosan Tusker is the shipped witness: "When you cycle this card, you may search
your library for a basic land card, reveal that card, put it into your hand,
then shuffle. **(Do this before you draw.)**"

Plain cycling already shipped — `Cost.discard_self` plus an activated ability
offerable from hand — so the cost half was expressible and only the event was
not. None of the 18 existing trigger events could carry it, and the near misses
are all *wrong* rather than merely absent:

- `draw` fires on every draw, including the draw step and every other draw
  spell, so a Tusker in the graveyard would fetch a land each time its
  controller drew anything. It also fires **after** the draw, which the
  parenthetical explicitly forbids.
- `discard` (the event exists) fires on hand-size discards and on every
  discard cost, so a Tusker pitched to a Wheel would fetch.
- `spell_cast` does not fire, because cycling is not casting; `dies`,
  `leaves_battlefield` and `creature_dies` all need the card to have been a
  permanent, and a cycled card goes hand → graveyard without ever being one.

So `EventType.CYCLED` is its own event, and cycling is **declared**
(`is_cycling`) rather than inferred from `discard_self`: "Discard this card:"
is a shape other cards print without being cycling, and a trigger firing on
those would be a different card. The loader refuses `is_cycling` without a cost
that discards the card.

Two orderings carry the card, and both are load-bearing:

1. The event fires **after** the cycling ability is on the stack, so the
   trigger drains on top of it and resolves first. That is the whole of "(Do
   this before you draw.)" — and it comes out of the stack's ordinary
   last-on-first-off behaviour rather than any special case.
2. The card is **already in the graveyard** when it fires, because paying the
   cost discarded it. So the trigger declares `active_zones: ["graveyard"]` and
   is collected by the walk `_candidate_abilities` already does over that zone.

`fire` rather than `emit` is the third thing worth saying: `state.emit` only
writes the log, and an event nothing listens for is exactly the silent no-op
this run exists to remove.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError

TUSKER = "krosan_tusker"


def hand_with_tusker(builder, *, library=("island", "mountain", "forest")):
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * 4)
        .hand(0, [TUSKER])
        .library(0, list(library))
        .active(0)
        .max_turns(1)
        .build()
    )


def cycle_it(game):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and game.state.objects[a.source].def_id == TUSKER
    )
    game.apply(action)


def run_out(game, *, search: bool = True) -> None:
    """Answer the trigger's `may`, pick a land, and let everything resolve."""
    for _ in range(40):
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if search else ActionKind.NO
            game.apply(next(a for a in actions if a.kind is want))
            continue
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choose = next((a for a in actions if a.kind is ActionKind.CHOOSE), None)
            if choose is not None:
                game.apply(choose)
                continue
            done = next(
                (a for a in actions if a.kind is ActionKind.FINISH_DECLARATION), None
            )
            if done is not None:
                game.apply(done)
                continue
        if decision.kind is DecisionKind.PRIORITY and game.state.stack:
            game.apply(next(a for a in actions if a.kind is ActionKind.PASS))
            continue
        return


def event_types(game, since: int) -> list[str]:
    return [e.type for e in game.state.events[since:]]


def hand_names(game) -> list[str]:
    return sorted(
        game.state.card_of(game.state.objects[o]).name
        for o in game.state.players[0].hand
    )


class TestItFires:
    def test_cycling_emits_the_event(self, builder):
        game = hand_with_tusker(builder)
        mark = len(game.state.events)
        cycle_it(game)
        assert "cycled" in event_types(game, mark)

    def test_the_trigger_resolves(self, builder):
        game = hand_with_tusker(builder, library=("island", "plains", "mountain"))
        cycle_it(game)
        run_out(game)
        assert "Plains" in hand_names(game) or "Island" in hand_names(game)
        assert len(game.state.players[0].hand) == 2, (
            "one card searched to hand, one card drawn"
        )

    def test_declining_the_search_still_draws(self, builder):
        game = hand_with_tusker(builder)
        cycle_it(game)
        run_out(game, search=False)
        assert len(game.state.players[0].hand) == 1, "'you may' is optional"


class TestTheOrdering:
    def test_the_search_happens_before_the_draw(self, builder):
        """"(Do this before you draw.)" -- the parenthetical is the test."""
        game = hand_with_tusker(builder, library=("island", "plains", "mountain"))
        mark = len(game.state.events)
        cycle_it(game)
        run_out(game)

        kinds = event_types(game, mark)
        # The trigger's resolution and the cycling draw are both in here; the
        # trigger's must come first.
        first_ability = kinds.index("ability_resolved")
        first_draw = kinds.index("draw")
        assert first_ability < first_draw, (
            "the fetch resolves before the cycling draw; firing the event "
            "before the ability went on the stack would reverse this"
        )


class TestItIsOnlyCycling:
    def test_an_ordinary_draw_does_not_fire_it(self, builder):
        game = hand_with_tusker(builder)
        mark = len(game.state.events)
        # Advance without cycling: the draw step draws a card.
        for _ in range(30):
            decision = game.pending()
            if decision is None:
                break
            passing = next(
                (a for a in game.legal_actions() if a.kind is ActionKind.PASS), None
            )
            if passing is None:
                break
            game.apply(passing)
        assert "cycled" not in event_types(game, mark), (
            "a `draw`-based stand-in would have fired here, which is why one "
            "was refused"
        )


def probe(**ability) -> dict:
    base = {
        "kind": "activated",
        "text": "Cycling {2}",
        "active_zones": ["hand"],
        "cost": {"mana": "{2}", "discard_self": True},
        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
    }
    base.update(ability)
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Cycling {2}",
        "mana_cost": "{3}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [base],
    }


class TestTheLoader:
    def test_cycling_loads(self):
        compile_card(CardModel.model_validate(probe(is_cycling=True)))

    def test_it_must_actually_discard_the_card(self):
        """`is_cycling` on an ability that keeps the card is not cycling.

        Without the discard the event would fire for an ability that cycled
        nothing, and Krosan Tusker would fetch a land every time.
        """
        payload = probe(
            is_cycling=True,
            active_zones=["battlefield"],
            cost={"mana": "{2}", "tap": True},
        )
        with pytest.raises(DslError, match="needs a cost that discards this card"):
            compile_card(CardModel.model_validate(payload))

    def test_a_self_discard_is_not_cycling_by_itself(self):
        """The flag is declared, not inferred -- and stays off by default."""
        card = compile_card(CardModel.model_validate(probe()))
        assert card.abilities[0].is_cycling is False
