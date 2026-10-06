""""Whenever an opponent searches their library, you gain 1 life and draw a card."

Archivist of Oghma is the witness. Rule 701.19 makes searching a library an act
of its own, and the card watches the act rather than whatever caused it -- so
the trigger needs an event fired *by the search*, which nothing in the engine
had. `cant_search_library` proved the engine already knew where searches
happen; it simply told nobody.

The near misses are wrong rather than merely absent:

- `ability_activated` fires on a cracked fetchland and also on every equip and
  every Signet, and never on a resolved Demonic Tutor.
- `spell_cast` fires on the tutor, but a spell that searches only conditionally
  is counted when it did not search, and a search done by a *trigger*
  (Tireless Tracker's landfall, a Saga's chapter) is missed outright.

So `LIBRARY_SEARCHED` is fired from `ops_cards._search`, the one routine that
both `search_library` and `search_zones` (every tutor, fetchland, landcycling
ability) go through. The claims this file pins:

- **One search, one event.** An empty search is still a search (701.19 does
  not ask what was found); two searches in one resolution are two events; one
  `search_zones` over library and graveyard is one; a `look_at_top` is not a
  search at all.
- **The searcher is the actor.** Path to Exile is my spell making *them*
  search, and the printed ruling is that Archivist triggers: `controller:
  "opponent"` compares the searching player, never the source's controller.
- **A refused search never happened.** Under `cant_search_library` the library
  drops out of the pool; that library was not searched, and nothing fires --
  even when the graveyard half of an "and/or" search goes ahead.
- **It follows its source.** No watcher on the battlefield, no trigger.
"""

from __future__ import annotations

from contextlib import suppress

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.events import EventType
from automtg.engine.zones import move_object
from tests.conftest import only_oid, pass_until

WATCHER = "t_search_watcher"  # Whenever an opponent searches their library, ...
ASHIOK = "t_ashiok_lock"  # ... can't cause their controller to search their library
BEAR = "t_bear"
FOREST = "forest"
WILDS = "evolving_wilds"

TUTOR = {"op": "search_library", "player": "you", "count": 1, "destination": "hand"}


def position(builder, *, mine=(WATCHER,), theirs=(), library=(BEAR,) * 10):
    """Player 0 holds the watcher; each library is ``library``; graveyards one bear."""
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, list(library))
        .library(1, list(library))
        .graveyard(1, [BEAR])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def run(game, effects, controller: int) -> None:
    """Resolve ``effects`` for ``controller``, taking the first option each time."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, effects)
    try:
        decision = next(gen)
        while True:
            decision = gen.send([0] if decision.options else [])
    except StopIteration:
        pass


def searches(game) -> list:
    return [e for e in game.state.events if e.type == EventType.LIBRARY_SEARCHED]


def queued(game) -> int:
    """How many watcher triggers are waiting to go on the stack."""
    return sum(
        1 for t in game.state.pending_triggers if game.state.objects[t.source_oid].def_id == WATCHER
    )


class TestOneSearchOneEvent:
    def test_a_tutor_fires_once_naming_the_searcher(self, builder):
        game = position(builder)
        run(game, [TUTOR], controller=1)
        (event,) = searches(game)
        assert event.player == 1
        assert event.data["owner"] == 1

    def test_a_search_that_finds_nothing_is_still_a_search(self, builder):
        game = position(builder)
        run(game, [{**TUTOR, "selector": {"types": ["Instant"]}}], controller=1)
        assert game.state.players[1].hand == []
        assert len(searches(game)) == 1
        assert queued(game) == 1

    def test_declining_up_to_one_is_still_a_search(self, builder):
        game = position(builder)
        ctx = EffectContext(state=game.state, controller=1)
        gen = execute(ctx, [TUTOR])
        decision = next(gen)
        assert decision.options
        with suppress(StopIteration):
            gen.send([])
        assert game.state.players[1].hand == []
        assert len(searches(game)) == 1

    def test_two_searches_in_one_resolution_are_two(self, builder):
        game = position(builder)
        run(game, [TUTOR, TUTOR], controller=1)
        assert len(searches(game)) == 2
        assert queued(game) == 2

    def test_an_and_or_search_of_two_zones_is_one(self, builder):
        game = position(builder)
        run(game, [{**TUTOR, "op": "search_zones", "zones": ["library", "graveyard"]}], 1)
        assert len(searches(game)) == 1

    def test_each_player_searching_is_one_event_per_player(self, builder):
        game = position(builder)
        run(game, [{**TUTOR, "player": "each_player"}], controller=0)
        assert sorted(e.player for e in searches(game)) == [0, 1]
        assert queued(game) == 1, "only the opponent's search is the watcher's"

    def test_looking_at_the_top_is_not_a_search(self, builder):
        game = position(builder)
        look = {
            "op": "look_at_top",
            "player": "you",
            "amount": {"const": 3},
            "objects": {"count": 1},
            "destination": "hand",
        }
        run(game, [look], controller=1)
        assert searches(game) == []


class TestTheSearcherIsTheActor:
    def test_my_own_search_does_not_trigger_my_watcher(self, builder):
        game = position(builder)
        run(game, [TUTOR], controller=0)
        assert len(searches(game)) == 1
        assert queued(game) == 0

    def test_my_spell_making_them_search_triggers(self, builder):
        """Path to Exile: my spell, their search -- an opponent searched."""
        game = position(builder)
        run(game, [{**TUTOR, "player": "each_opponent"}], controller=0)
        (event,) = searches(game)
        assert event.player == 1
        assert queued(game) == 1


class TestARefusedSearchNeverHappened:
    def test_a_barred_tutor_fires_nothing(self, builder):
        game = position(builder, mine=(WATCHER, ASHIOK))
        run(game, [TUTOR], controller=1)
        assert searches(game) == []
        assert queued(game) == 0

    def test_the_graveyard_half_goes_ahead_without_a_library_search(self, builder):
        game = position(builder, mine=(WATCHER, ASHIOK))
        run(game, [{**TUTOR, "op": "search_zones", "zones": ["library", "graveyard"]}], 1)
        assert game.state.players[1].graveyard == [], "the graveyard bear was found"
        assert searches(game) == []

    def test_a_search_the_lock_does_not_name_still_fires(self, builder):
        """Ashiok bars an opponent's *own* spells; my Path is not one of them."""
        game = position(builder, mine=(WATCHER, ASHIOK))
        run(game, [{**TUTOR, "player": "each_opponent"}], controller=0)
        assert len(searches(game)) == 1


class TestItFollowsItsSource:
    def test_no_watcher_no_trigger(self, builder):
        game = position(builder, mine=())
        run(game, [TUTOR], controller=1)
        assert len(searches(game)) == 1, "the event is the game's, not the card's"
        assert game.state.pending_triggers == []

    def test_it_stops_when_the_watcher_leaves(self, builder):
        game = position(builder)
        move_object(game.state, only_oid(game, WATCHER), Zone.GRAVEYARD)
        run(game, [TUTOR], controller=1)
        assert queued(game) == 0


class TestEndToEnd:
    def test_an_opponent_cracking_a_fetchland_pays_the_watcher(self, builder):
        """The whole card, through a real activation: 1 life and a card."""
        game = (
            builder(players=2)
            .battlefield(0, [WATCHER])
            .battlefield(1, [WILDS])
            .library(0, [BEAR] * 10)
            .library(1, [FOREST] * 10)
            .active(1)
            .max_turns(4)
            .build()
        )
        life = game.state.players[0].life
        wilds = only_oid(game, WILDS)
        crack = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == wilds
        )
        game.apply(crack)
        pass_until(game, lambda g: g.state.players[0].life > life)
        assert game.state.players[0].life == life + 1
        # Read off the log rather than the hand: with nothing left to decide the
        # engine rolls on into player 0's own turn, whose draw step would blur
        # the count. The trigger's draw is the one between the search and the
        # next turn beginning.
        kinds = [
            (e.type, e.player)
            for e in game.state.events
            if e.type in (EventType.LIBRARY_SEARCHED, EventType.DRAW, EventType.TURN_BEGAN)
        ]
        searched = kinds.index((EventType.LIBRARY_SEARCHED, 1))
        assert kinds[searched + 1] == (EventType.DRAW, 0)


class TestTheLoader:
    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))


def _card() -> dict:
    text = "Whenever an opponent searches their library, you gain 1 life and draw a card."
    return {
        "id": "t_bare_watcher",
        "name": "Test Bare Watcher",
        "oracle_text": text,
        "mana_cost": "{1}{W}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 2,
        "abilities": [
            {
                "kind": "triggered",
                "text": text,
                "trigger": {"event": "searches_library", "controller": "opponent"},
                "effects": [
                    {"op": "gain_life", "player": "you", "amount": {"const": 1}},
                    {"op": "draw", "player": "you", "amount": {"const": 1}},
                ],
            }
        ],
    }
