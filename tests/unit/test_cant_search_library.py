"""A search that cannot happen: "Spells and abilities your opponents control can't
cause their controller to search their library."

Ashiok, Dream Render is the witness. The static stops one precise thing -- a
player searching **their own** library because a spell or ability **they
control** told them to -- and every word of that is load-bearing:

- **Their own spells.** An opponent's Demonic Tutor finds nothing. My Path to
  Exile on their creature still lets them search: Path is mine, and it is my
  spell causing *them* to search, which the sentence does not name.
- **Their library.** Finale of Devastation searches "your library and/or
  graveyard"; the graveyard half is not a library and is still searched.
- **The rest still happens.** The search is refused, not the spell: a "then
  shuffle" is still performed (the printed ruling), so a stacked top is still
  lost -- the reason the lock is not a strictly better card for the opponent.

Without it the only nearby statics are `cant_cast_spells` and
`cant_activate_abilities`, which stop the tutor being *cast* -- a far harsher
lock that also stops everything else the spell does.

The `cant_search_library` static, read by `ops_cards._search` through
`player_statics.search_forbidden`.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects import execute, ops_cards
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.player_statics import search_forbidden
from automtg.engine.zones import move_object

ASHIOK = "t_ashiok_lock"  # Spells and abilities your opponents control can't cause ...
BEAR = "t_bear"

TUTOR = {"op": "search_library", "player": "you", "count": 1, "destination": "hand"}


def position(builder, mine=(ASHIOK,), theirs=()):
    """Player 0 holds Ashiok; each library is ten bears; graveyards hold one bear."""
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, [BEAR] * 10)
        .library(1, [BEAR] * 10)
        .graveyard(1, [BEAR])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def run(game, effects, controller: int) -> list:
    """Resolve ``effects`` for ``controller``, taking the first option each time."""
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
    return asked


def count_shuffles(monkeypatch) -> list[int]:
    """Record the seat of every library shuffle a search performs."""
    shuffled: list[int] = []
    real = ops_cards.shuffle_library

    def spy(state, pid):
        shuffled.append(pid)
        return real(state, pid)

    monkeypatch.setattr(ops_cards, "shuffle_library", spy)
    return shuffled


class TestTheOpponentsOwnSearch:
    def test_their_tutor_finds_nothing(self, builder):
        game = position(builder)
        asked = run(game, [TUTOR], controller=1)
        assert asked == []
        assert game.state.players[1].hand == []
        assert len(game.state.players[1].library) == 10

    def test_they_still_shuffle(self, builder, monkeypatch):
        game = position(builder)
        shuffles = count_shuffles(monkeypatch)
        run(game, [TUTOR], controller=1)
        assert shuffles == [1]

    def test_the_rest_of_the_spell_still_happens(self, builder):
        game = position(builder)
        run(game, [TUTOR, {"op": "draw", "player": "you", "amount": 1}], controller=1)
        assert len(game.state.players[1].hand) == 1

    def test_the_graveyard_half_of_an_and_or_search_is_still_searched(self, builder):
        game = position(builder)
        spec = {**TUTOR, "op": "search_zones", "zones": ["library", "graveyard"]}
        asked = run(game, [spec], controller=1)
        assert asked, "the graveyard is not a library"
        assert len(asked[0].options) == 1, "only the graveyard bear is offered"
        assert game.state.players[1].graveyard == []
        assert len(game.state.players[1].library) == 10


class TestWhatItDoesNotName:
    def test_its_controller_searches_freely(self, builder):
        game = position(builder)
        assert run(game, [TUTOR], controller=0)
        assert len(game.state.players[0].hand) == 1

    def test_my_spell_making_them_search_is_not_stopped(self, builder):
        """Path to Exile: my spell, their search -- not "their controller"."""
        game = position(builder)
        spec = {**TUTOR, "player": "each_opponent"}
        assert run(game, [spec], controller=0)
        assert len(game.state.players[1].hand) == 1

    def test_their_spell_searching_my_library_is_not_named(self, builder):
        """"…their controller to search **their** library" -- only their own."""
        assert not search_forbidden(position(builder).state, 0, 1)

    def test_nothing_without_the_static(self, builder):
        game = position(builder, mine=())
        assert run(game, [TUTOR], controller=1)
        assert len(game.state.players[1].hand) == 1


class TestItFollowsItsSource:
    def test_it_lifts_when_ashiok_leaves(self, builder):
        game = position(builder)
        ashiok = next(o for o in game.state.battlefield if game.state.objects[o].def_id == ASHIOK)
        move_object(game.state, ashiok, Zone.GRAVEYARD)
        assert not search_forbidden(game.state, 1, 1)
        assert run(game, [TUTOR], controller=1)


class TestTheLoaderRefusesWhatIsNotACard:
    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))

    def test_affects_player_is_required(self):
        card = _card()
        card["abilities"][0].pop("affects_player")
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(card))

    @pytest.mark.parametrize(
        "extra", [{"affects": {"types": ["Creature"]}}, {"amount": {"const": 1}}]
    )
    def test_a_filter_or_an_amount_is_refused(self, extra):
        card = _card()
        card["abilities"][0].update(extra)
        with pytest.raises(DslError, match="cant_search_library takes"):
            compile_card(CardModel.model_validate(card))


def _card() -> dict:
    text = (
        "Spells and abilities your opponents control can't cause their "
        "controller to search their library."
    )
    return {
        "id": "t_bad_ashiok",
        "name": "Test Bad Ashiok",
        "oracle_text": text,
        "mana_cost": "{1}{U}{B}",
        "types": ["Enchantment"],
        "abilities": [
            {
                "kind": "static",
                "text": text,
                "effect": "cant_search_library",
                "affects_player": "opponent",
            }
        ],
    }
