""""…then draws **that many** cards" -- counting what a tuck actually moved.

Teferi's Puzzle Box: "At the beginning of each player's draw step, that player
puts the cards in their hand on the bottom of their library in any order, then
draws that many cards."

"That many" is a number about the tuck, and every existing way to ask for it is
wrong by the time the draw runs:

- `cards_in_hand` read at the draw is **0** -- the hand has just gone under, so
  the Box would empty a hand and hand nothing back;
- read before the tuck, there is nowhere to keep it: `snapshot` captures one
  object's characteristics, not a count;
- a `for_each` that tucks a card and draws a card per iteration is a different
  card -- each draw can pull up a card that was just tucked once the library is
  short, and a draw trigger fires between tucks.

So `put_on_top` joins the recording ops: `as` binds the cards that **arrived in
a library**, and `{"count": {"binding": …}}` reads the number. That is the
pattern `discard`'s `as` set for Joshua's "then draw that many cards".

The position is the starting player's first draw step with the Box out, which
103.8a makes a draw step with no draw in it -- so the hand the Box sees is
exactly the hand the test built, and every number below is that hand's size.
"""

from __future__ import annotations

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Step, Zone
from tests.conftest import _default_answer

BOX = "t_puzzle_box"


def position(builder, hand: list[str]):
    game = (
        builder(players=2)
        .battlefield(0, [BOX, "island"])
        .library(0, ["forest"] * 10)
        .library(1, ["plains"] * 10)
        .hand(0, hand)
        .step(Step.UPKEEP)
        .build(advance=False)
    )
    return game


def through_the_box(game) -> None:
    """Advance into the draw step and resolve the Box's trigger."""
    game._advance()
    fired = False
    for _ in range(300):
        decision = game.pending()
        if decision is None:
            return
        if game.state.stack:
            fired = True
        if fired and not game.state.stack and decision.kind is DecisionKind.PRIORITY:
            return
        if game.state.step is Step.PRECOMBAT_MAIN:
            return
        game.apply(_default_answer(game, decision))


def ids(game, oids) -> list[str]:
    return [game.state.objects[oid].def_id for oid in oids]


class TestThatMany:
    def test_the_hand_comes_back_the_same_size(self, builder):
        """Three under, three drawn."""
        game = position(builder, ["swamp", "mountain", "swamp"])
        through_the_box(game)
        me = game.state.players[0]

        assert len(me.hand) == 3
        assert len(me.library) == 10
        # Everything drawn came off the top; everything tucked is underneath.
        assert ids(game, me.hand) == ["forest"] * 3
        assert sorted(ids(game, me.library[-3:])) == ["mountain", "swamp", "swamp"]

    def test_it_is_not_the_empty_hand_after(self, builder):
        """The near miss reads 0 here and draws nothing."""
        game = position(builder, ["swamp"])
        through_the_box(game)

        assert ids(game, game.state.players[0].hand) == ["forest"]

    def test_the_library_keeps_its_size(self, builder):
        game = position(builder, ["swamp", "mountain"])
        through_the_box(game)

        # 10, two tucked, two drawn back.
        assert len(game.state.players[0].library) == 10

    def test_an_empty_hand_draws_nothing(self, builder):
        game = position(builder, [])
        through_the_box(game)

        assert game.state.players[0].hand == []
        assert len(game.state.players[0].library) == 10


class TestTheBinding:
    def run(self, builder, effects, hand):
        game = (
            builder(players=2)
            .library(0, ["forest"] * 5)
            .hand(0, hand)
            .build()
        )
        ctx = EffectContext(state=game.state, controller=0)
        gen = execute(ctx, effects)
        for _ in gen:  # pragma: no cover - `count: "all"` and no any_order asks nothing
            raise AssertionError("nothing here should ask")
        return game, ctx

    def test_it_names_the_cards_that_arrived(self, builder):
        tuck = {
            "op": "put_on_top",
            "bottom": True,
            "objects": {"zone": "hand", "player": "you", "count": "all"},
            "as": "tucked",
        }
        game, ctx = self.run(builder, [tuck], ["swamp", "mountain"])

        assert sorted(ids(game, ctx.bindings["tucked"])) == ["mountain", "swamp"]
        assert all(game.state.objects[o].zone is Zone.LIBRARY for o in ctx.bindings["tucked"])

    def test_nothing_moved_is_an_empty_binding_not_a_stale_one(self, builder):
        tuck = {
            "op": "put_on_top",
            "bottom": True,
            "objects": {"zone": "hand", "player": "you", "count": "all"},
            "as": "tucked",
        }
        _game, ctx = self.run(builder, [tuck, tuck], ["swamp"])

        assert ctx.bindings["tucked"] == []


class TestTheLoader:
    def test_as_on_put_on_top_is_accepted(self):
        compile_card(
            CardModel.model_validate(
                {
                    "id": "t_as_tuck",
                    "name": "As Tuck",
                    "oracle_text": "Put your hand on the bottom of your library, then draw that many cards.",
                    "mana_cost": "{U}",
                    "types": ["Sorcery"],
                    "spell_effects": [
                        {
                            "op": "put_on_top",
                            "bottom": True,
                            "objects": {"zone": "hand", "player": "you", "count": "all"},
                            "as": "tucked",
                        },
                        {"op": "draw", "amount": {"count": {"binding": "tucked"}}},
                    ],
                }
            )
        )
