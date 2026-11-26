"""A search of somebody else's library, by the player resolving it.

    "For each player, search that player's library for a nonland card and
    exile it, then that player shuffles."
                                  -- Jace, Architect of Thought's -8

701.19: the player told to search is the one who looks and picks. Every
other `search_library` makes a library's owner search it ("each player
searches their library", Tempt with Discovery), so the same words inside
`for_each_player` would hand each opponent the choice of which of their cards
Jace takes: a strictly worse ultimate than the printed one, and a normal-
looking one on screen. `searcher: "you"` makes the resolving player search
every library `player` names. The owner still shuffles their own (701.19c),
the cards still go to their owner's zones, and Ashiok, Dream Render, which
stops a player searching **their own** library, does not stop a search of
somebody else's.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute, ops_cards
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError

ASHIOK = "t_ashiok_lock"  # Spells and abilities your opponents control can't cause ...
BEAR = "t_bear"

#: Jace's -8, its search half, as the card writes it.
SEARCH = {
    "op": "search_library",
    "player": "each_player",
    "searcher": "you",
    "selector": {"not_types": ["Land"]},
    "count": 1,
    "destination": "exile",
    "as": "found",
}


def position(builder, mine=(), theirs=()):
    """Each library is five Forests and a Bear."""
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 5 + [BEAR])
        .library(1, ["forest"] * 5 + [BEAR])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def run(game, effects, controller: int = 0):
    """Resolve ``effects``, taking the first option each time; returns the
    decisions asked and the context."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, effects)
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            decision = gen.send([0] if decision.options else [])
    except StopIteration:
        pass
    return asked, ctx


def bears_in_exile(game) -> dict[int, int]:
    return {
        pid: sum(
            1
            for oid in game.state.players[pid].zone_list(Zone.EXILE)
            if game.state.objects[oid].def_id == BEAR
        )
        for pid in (0, 1)
    }


class TestTheResolvingPlayerSearches:
    def test_every_question_is_the_controllers(self, builder):
        game = position(builder)
        asked, _ = run(game, [SEARCH], controller=0)
        assert len(asked) == 2
        assert {d.player for d in asked} == {0}

    def test_a_card_from_each_library_goes_to_its_owners_exile(self, builder):
        game = position(builder)
        _, ctx = run(game, [SEARCH], controller=0)
        assert bears_in_exile(game) == {0: 1, 1: 1}
        assert len(ctx.bindings["found"]) == 2

    def test_each_owner_shuffles_their_own_library(self, builder, monkeypatch):
        shuffled: list[int] = []
        real = ops_cards.shuffle_library

        def spy(state, pid):
            shuffled.append(pid)
            return real(state, pid)

        monkeypatch.setattr(ops_cards, "shuffle_library", spy)
        game = position(builder)
        run(game, [SEARCH], controller=0)
        assert sorted(shuffled) == [0, 1]

    def test_without_it_each_owner_searches(self, builder):
        game = position(builder)
        plain = {k: v for k, v in SEARCH.items() if k != "searcher"}
        asked, _ = run(game, [plain], controller=0)
        assert sorted(d.player for d in asked) == [0, 1]


class TestAshiok:
    def test_it_bars_only_the_searchers_own_library(self, builder):
        """Ashiok is the opponent's: player 0 may not search player 0's own
        library because of player 0's ability, and may still search player 1's."""
        game = position(builder, theirs=(ASHIOK,))
        run(game, [SEARCH], controller=0)
        assert bears_in_exile(game) == {0: 0, 1: 1}


def _card(**effect) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_bad_search", "name": "Bad Search",
                "oracle_text": "Search each library.",
                "mana_cost": "{U}", "types": ["Sorcery"],
                "spell_effects": [{"op": "search_library", "player": "each_player",
                                   "count": 1, **effect}],
            }
        )
    )


class TestTheLoader:
    def test_the_printed_shape_compiles(self):
        _card(searcher="you", destination="exile")

    def test_another_searcher_is_refused(self):
        with pytest.raises(DslError, match="searcher"):
            _card(searcher="each_opponent", destination="exile")

    def test_onto_the_battlefield_is_refused(self):
        with pytest.raises(DslError, match="whose control"):
            _card(searcher="you", destination="battlefield")

    def test_on_another_op_it_is_refused(self):
        with pytest.raises(DslError, match="searcher"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_bad_zones", "name": "Bad Zones",
                        "oracle_text": "Search.", "mana_cost": "{U}", "types": ["Sorcery"],
                        "spell_effects": [{"op": "search_zones", "searcher": "you",
                                           "zones": ["library", "graveyard"]}],
                    }
                )
            )
