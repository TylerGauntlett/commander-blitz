"""Cut a Deal: "…then you draw a card for each opponent **who drew a card this way**."

The rider is not decoration. Told to draw, a player does not always draw:

- **121.4** -- a player with an empty library who is told to draw has only
  *attempted* to draw. No card was drawn; the consequence is the state-based
  loss of 704.5b, not a card in hand.
- **121.6 / 614.11** -- a draw can be replaced. Dredge returns a card from the
  graveyard *instead*, and no card was drawn.

So `draw` grew an `as` recording **the seats that actually drew at least one
card**, read back with the `{"binding": …}` player spec -- the set-of-seats
shape `may`'s `as` already writes for Snort. Without it the only spelling of
the card's second half is a `for_each_player` over `"each_opponent"`, which
pays out for exactly the opponents the rider exists to exclude, and looks
completely ordinary on any board where every library has cards in it.

The loader half: a seat binding is a list of player ids, and `resolve_pool`
reads any bound list as oids. `{"count": {"binding": "drew"}}` would count
*objects* numbered like seats, so it is refused at load time.

Witness: Cut a Deal.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS, RECORDING_OPS, execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError

SWAMP = "swamp"
TROLL = "t_dredger"  # dredge 3

DRAW_EACH_OPPONENT = {
    "op": "draw",
    "player": "each_opponent",
    "amount": {"const": 1},
    "as": "drew",
}
PAY_OUT = {
    "op": "for_each_player",
    "players": {"binding": "drew"},
    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
}
CUT_A_DEAL = [DRAW_EACH_OPPONENT, PAY_OUT]


def table(builder, *, players: int = 2, libraries: dict[int, int] | None = None):
    """A table where seat N has ``libraries[N]`` cards (default 10). Returns (game, ctx)."""
    libraries = libraries or {}
    b = builder(players=players)
    for pid in range(players):
        b = b.library(pid, [SWAMP] * libraries.get(pid, 10))
    game = b.build(advance=False)
    return game, EffectContext(state=game.state, controller=0)


def run(gen, *, dredge: bool = False):
    """Drive an effect generator. The only question these boards ask is dredge."""
    send = None
    while True:
        try:
            gen.send(send)
        except StopIteration as stop:
            return stop.value
        send = [0] if dredge else []


def hand(game, pid: int) -> int:
    return len(game.state.players[pid].hand)


class TestWhatIsRecorded:
    def test_draw_is_a_recording_op(self):
        assert "draw" in RECORDING_OPS

    def test_the_seats_that_drew(self, builder):
        _game, ctx = table(builder, players=3)
        run(OPS["draw"](ctx, DRAW_EACH_OPPONENT))
        assert ctx.bindings["drew"] == [1, 2]

    def test_an_empty_library_draws_nothing_and_is_not_recorded(self, builder):
        """121.4: an attempt to draw from an empty library is not drawing a card."""
        game, ctx = table(builder, players=3, libraries={2: 0})
        run(OPS["draw"](ctx, DRAW_EACH_OPPONENT))
        assert ctx.bindings["drew"] == [1]
        assert game.state.players[2].attempted_draw_from_empty, "…and still decks them"

    def test_a_dredged_draw_is_not_a_draw(self, builder):
        """121.6: the replaced draw drew nothing, so the dredger is not recorded."""
        game = (
            builder(players=2)
            .library(0, [SWAMP] * 10)
            .library(1, [SWAMP] * 10)
            .graveyard(1, [TROLL])
            .build(advance=False)
        )
        troll = game.state.players[1].graveyard[0]
        ctx = EffectContext(state=game.state, controller=0)
        run(OPS["draw"](ctx, DRAW_EACH_OPPONENT), dredge=True)
        assert game.state.objects[troll].zone is Zone.HAND, "the dredge happened"
        assert ctx.bindings["drew"] == []

    def test_declining_the_dredge_draws_and_is_recorded(self, builder):
        game = (
            builder(players=2)
            .library(0, [SWAMP] * 10)
            .library(1, [SWAMP] * 10)
            .graveyard(1, [TROLL])
            .build(advance=False)
        )
        ctx = EffectContext(state=game.state, controller=0)
        run(OPS["draw"](ctx, DRAW_EACH_OPPONENT), dredge=False)
        assert ctx.bindings["drew"] == [1]

    def test_drawing_fewer_than_asked_still_drew(self, builder):
        """"Who drew **a** card": one of two is at least one."""
        _game, ctx = table(builder, libraries={1: 1})
        spec = {**DRAW_EACH_OPPONENT, "amount": {"const": 2}}
        run(OPS["draw"](ctx, spec))
        assert ctx.bindings["drew"] == [1]


class TestTheBindingIsWrittenAndAccumulates:
    def test_nobody_drawing_still_writes_an_empty_set(self, builder):
        """A read after it answers for this draw, not for whatever came before."""
        _game, ctx = table(builder, libraries={1: 0})
        run(OPS["draw"](ctx, DRAW_EACH_OPPONENT))
        assert ctx.bindings["drew"] == []

    def test_a_loop_of_single_draws_names_every_seat_that_drew(self, builder):
        _game, ctx = table(builder, players=4, libraries={2: 0})
        loop = {
            "op": "for_each_player",
            "players": "each_opponent",
            "effects": [
                {"op": "draw", "player": {"binding": "each_player"}, "as": "drew"}
            ],
        }
        run(execute(ctx, [loop]))
        assert sorted(ctx.bindings["drew"]) == [1, 3]


class TestCutADeal:
    def test_two_players(self, builder):
        game, ctx = table(builder)
        run(execute(ctx, CUT_A_DEAL))
        assert hand(game, 1) == 1
        assert hand(game, 0) == 1

    def test_an_opponent_with_an_empty_library_pays_nothing_out(self, builder):
        game, ctx = table(builder, libraries={1: 0})
        run(execute(ctx, CUT_A_DEAL))
        assert hand(game, 1) == 0
        assert hand(game, 0) == 0, "the near miss over each_opponent would draw one here"

    def test_three_opponents_three_cards(self, builder):
        game, ctx = table(builder, players=4)
        run(execute(ctx, CUT_A_DEAL))
        assert [hand(game, pid) for pid in (1, 2, 3)] == [1, 1, 1]
        assert hand(game, 0) == 3

    def test_three_opponents_one_decked(self, builder):
        game, ctx = table(builder, players=4, libraries={2: 0})
        run(execute(ctx, CUT_A_DEAL))
        assert [hand(game, pid) for pid in (1, 2, 3)] == [1, 0, 1]
        assert hand(game, 0) == 2


def spell(*effects):
    return CardModel.model_validate(
        {
            "id": "t_cut_a_deal_probe",
            "name": "Cut a Deal Probe",
            "mana_cost": "{2}{W}",
            "types": ["Sorcery"],
            "spell_effects": list(effects),
        }
    )


class TestTheLoaderGuards:
    def test_the_printed_spelling_loads(self):
        compile_card(spell(*CUT_A_DEAL))

    def test_counting_the_seats_as_objects_is_refused(self):
        """A seat list read by `resolve_pool` is oids that happen to equal seats."""
        miscount = {
            "op": "draw",
            "player": "you",
            "amount": {"count": {"binding": "drew"}},
        }
        with pytest.raises(DslError, match="holds players"):
            compile_card(spell(DRAW_EACH_OPPONENT, miscount))

    def test_an_as_on_draw_is_no_longer_refused_as_unwritten(self):
        compile_card(spell(DRAW_EACH_OPPONENT))
