"""Doing something else instead of drawing from an empty library.

    Out of the Tombs — "If you would draw a card while your library has no
    cards in it, instead return a creature card from your graveyard to the
    battlefield. If you can't, you lose the game."

`replace_empty_draw` without `effects` is Laboratory Maniac: the replacement is
winning. With `effects` the static carries the "instead" itself, and
`replacements._draw_one` runs it in place of the draw. The rules argument is the
same race the win had (104.3c): the draw is *replaced*, so `draw_cards` is never
called, the "will lose" flag is never set, and the state-based action that
would eliminate a player who drew from an empty library never fires. A trigger
on the draw could not do it -- an empty library fires no `DRAW` -- and a
creature returned *after* a failed draw would arrive beside a player already
flagged to lose.

"If you can't" is an ordinary `if` inside the effects, asking whether a
creature card is there to return. Without it the card would be strictly
better than printed: an empty graveyard would replace the draw with nothing,
and the player would never deck.

Two empty-library replacements on one draw are the drawing player's choice
(616.1): whichever applies first replaces the draw, and the other has nothing
left to replace. The test pool's `t_tomb_reclaimer` prints Out of the Tombs'
second sentence; `t_lab_maniac` is the win.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.replacements import draw as draw_with_replacements
from tests.conftest import only_oid

RECLAIMER = "t_tomb_reclaimer"
MANIAC = "t_lab_maniac"
BEAR = "t_bear"


def _board(builder, *, graveyard: list[str], library: int, extra: list[str] = ()):
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * 3 + [RECLAIMER, *extra])
        .graveyard(0, graveyard)
        .library(0, ["forest"] * library)
        .library(1, ["forest"] * 20)
        .build()
    )
    return game, only_oid(game, RECLAIMER)


def _bear(game, pid: int = 0) -> int:
    """The one bear, wherever it is (`only_oid` reads only the battlefield)."""
    found = [
        oid
        for oid, obj in game.state.objects.items()
        if obj.def_id == BEAR and obj.owner == pid
    ]
    assert len(found) == 1, found
    return found[0]


def _draw(game, pid: int, count: int = 1, *, answer=None):
    """Run a draw through the replacement seam.

    ``answer`` picks one of each decision's option values (by default the
    first), sent back as its index. Returns ``(drawn, decisions)``.
    """
    gen = draw_with_replacements(game.state, pid, count)
    send = None
    decisions = []
    while True:
        try:
            decision = gen.send(send)
        except StopIteration as stop:
            return stop.value, decisions
        decisions.append(decision)
        values = [o.value for o in decision.options]
        send = [values.index(answer(decision, values)) if answer else 0]


class TestTheReplacement:
    def test_a_creature_card_returns_instead(self, builder):
        game, _ = _board(builder, graveyard=[BEAR], library=0)
        bear = _bear(game)
        drawn, _ = _draw(game, 0)
        assert drawn == []
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].controller == 0
        assert not game.state.players[0].attempted_draw_from_empty, (
            "the replaced draw was still recorded as an attempt"
        )
        assert not game.over

    def test_the_player_chooses_which_creature_card(self, builder):
        game, _ = _board(builder, graveyard=[BEAR, BEAR], library=0)
        second = [
            oid for oid in game.state.players[0].graveyard
            if game.state.card_of(game.state.objects[oid]).id == BEAR
        ][1]
        _, decisions = _draw(game, 0, answer=lambda _d, values: second)
        assert len(decisions) == 1
        assert game.state.objects[second].zone is Zone.BATTLEFIELD
        others = [oid for oid in game.state.players[0].graveyard]
        assert len(others) == 1

    def test_a_noncreature_card_does_not_count(self, builder):
        """"A creature card": a land in the graveyard is not one, so you lose."""
        game, _ = _board(builder, graveyard=["forest"], library=0)
        _draw(game, 0)
        assert game.over
        assert game.winners == [1]

    def test_with_nothing_to_return_you_lose(self, builder):
        game, _ = _board(builder, graveyard=[], library=0)
        _draw(game, 0)
        assert game.state.players[0].has_lost
        assert game.winners == [1]

    def test_each_empty_draw_is_replaced_separately(self, builder):
        """121.2: drawing two is two draws, so two creature cards come back."""
        game, _ = _board(builder, graveyard=[BEAR, BEAR], library=0)
        _draw(game, 0, 2)
        assert game.state.players[0].graveyard == []
        assert not game.over

    def test_a_nonempty_library_draws_as_usual(self, builder):
        game, _ = _board(builder, graveyard=[BEAR], library=3)
        drawn, _ = _draw(game, 0)
        assert len(drawn) == 1
        assert game.state.objects[_bear(game)].zone is Zone.GRAVEYARD


class TestWhoItAppliesTo:
    def test_an_opponent_drawing_empty_is_unaffected(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 3 + [RECLAIMER])
            .graveyard(1, [BEAR])
            .library(0, ["forest"] * 20)
            .library(1, [])
            .build()
        )
        _draw(game, 1)
        assert game.state.players[1].attempted_draw_from_empty
        assert game.state.objects[_bear(game, 1)].zone is Zone.GRAVEYARD

    def test_the_replacement_ends_when_the_source_leaves(self, builder):
        from commanderblitz.engine.zones import move_object

        game, reclaimer = _board(builder, graveyard=[BEAR], library=0)
        move_object(game.state, reclaimer, Zone.GRAVEYARD)
        _draw(game, 0)
        assert game.state.players[0].attempted_draw_from_empty


class TestTwoReplacements:
    """616.1: the drawing player picks which of the two replaces the draw."""

    def test_choosing_the_win(self, builder):
        game, _ = _board(builder, graveyard=[BEAR], library=0, extra=[MANIAC])
        maniac = only_oid(game, MANIAC)
        _, decisions = _draw(game, 0, answer=lambda _d, values: maniac)
        assert decisions[0].context.get("purpose") == "choose_permanents"
        assert game.winners == [0]

    def test_choosing_the_return(self, builder):
        game, reclaimer = _board(builder, graveyard=[BEAR], library=0, extra=[MANIAC])
        _draw(game, 0, answer=lambda _d, values: reclaimer if reclaimer in values else values[0])
        assert not game.over
        assert game.state.objects[only_oid(game, BEAR)].zone is Zone.BATTLEFIELD


class TestLoadTimeGuards:
    def _model(self, **over):
        ability = {
            "kind": "static",
            "text": "If you would draw a card while your library has no cards in it, instead you lose the game.",
            "effect": "replace_empty_draw",
            "affects_player": "you",
            "effects": [{"op": "lose_game", "player": "you"}],
        }
        ability.update(over)
        return CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "oracle_text": ability["text"],
                "mana_cost": "{2}{B}",
                "types": ["Enchantment"],
                "abilities": [ability],
            }
        )

    def test_the_effects_are_carried(self):
        card = compile_card(self._model())
        assert card.abilities[0].static["effects"] == [{"op": "lose_game", "player": "you"}]

    def test_effects_on_an_opponents_draw_are_refused(self):
        """The effects run as the static's controller, so their "you" would
        be the wrong player on anybody else's draw."""
        with pytest.raises(DslError, match="'affects_player' is 'you'"):
            compile_card(self._model(affects_player="opponent"))

    def test_a_malformed_effect_is_refused_at_load(self):
        with pytest.raises(DslError):
            compile_card(self._model(effects=[{"op": "no_such_op"}]))
