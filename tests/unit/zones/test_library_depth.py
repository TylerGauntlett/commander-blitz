"""A library position, not a library end: "fourth from the top" (Lost to Legend).

Rule 701.20a and the whole tuck family: "put it into its owner's library" comes
with an ordinal, and the ordinal *is* the card. Lost to Legend prints "into its
owner's library **fourth from the top**", Hinder prints "second from the top",
Condemn prints "second from the top" for the creature it removes from combat.

What was wrong without this, and it was wrong loudly in both directions. The
zone layer had exactly two library positions -- `move_object`'s `to_top: bool`,
which is `list.insert(0)` or `list.append` -- so a depth had to be rounded to
one of them, and both roundings change the card:

* on **top**, the owner draws the permanent back on their very next draw step,
  which is the opposite of what paying for the depth buys;
* on the **bottom** of a 99-card Commander deck, the permanent is never seen
  again, which is exile with extra steps.

So `move_object` grew `to_index`, a position counted from the top, and
`put_on_top` grew `from_top`, the printed ordinal counted from 1. Three things
about it are only ever visible when they are wrong, and each has a claim below:

* the **off-by-one** -- "fourth from the top" is index 3, and a card tucked
  third is drawn a turn early;
* the **clamp** -- a library shorter than the depth takes the card as deep as it
  goes, and a raw `list.insert` of a *negative* index would silently bury it
  near the bottom instead;
* the **owner** -- "its owner's library", which is only distinguishable on a
  stolen permanent, where the controller's library would hand the victim's card
  to the thief for good.

The witness is `lost_to_legend`, authored against this and re-verified through
all six gates on every run. Everything `move_object` did before is unchanged:
`to_index` defaults to `None`, and the thirty-odd existing callers -- draw,
mill, discard, dies, fizzle, mulligan -- pass nothing and still append.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

BEAR = "t_bear"
#: Five distinguishable cards, so a position can be read off the list by name
#: rather than by counting.
STACK = ["forest", "island", "swamp", "mountain", "plains"]


def a_tuckable(builder, library: list[str] | None = None):
    """One opponent creature on the battlefield and a known library under it.

    ``advance=False`` because the claim is about the position: letting the
    engine auto-pass runs a draw step, and a library whose top card has already
    been drawn cannot be counted down from.
    """
    game = (
        builder(players=2)
        .battlefield(1, [BEAR])
        .library(1, STACK if library is None else library)
        .build(advance=False)
    )
    return game, only_oid(game, BEAR, 1)


def run(game, controller: int = 0, **effect) -> None:
    """Drive one op to completion outside the stack, as `test_proliferate` does."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [effect])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def tuck(game, *, from_top=None, controller: int = 0) -> None:
    """`put_on_top` over the one creature on the board, at an optional depth."""
    spec = {
        "op": "put_on_top",
        "objects": {"zone": "battlefield", "types": ["Creature"], "controller": "any"},
    }
    if from_top is not None:
        spec["from_top"] = from_top
    run(game, controller=controller, **spec)


def names(game, pid: int) -> list[str]:
    return [game.state.objects[oid].def_id for oid in game.state.players[pid].library]


class TestTheOrdinalIsThePrintedOne:
    def test_fourth_from_the_top_is_fourth(self, builder):
        """Lost to Legend, exactly. Three cards are drawn before this one."""
        game, bear = a_tuckable(builder)
        tuck(game, from_top={"const": 4})

        assert names(game, 1) == ["forest", "island", "swamp", BEAR, "mountain", "plains"]
        assert game.state.players[1].library.index(bear) == 3

    def test_second_from_the_top_is_second(self, builder):
        """Hinder and Condemn. The other ordinal actually printed on cards."""
        game, _ = a_tuckable(builder)
        tuck(game, from_top={"const": 2})

        assert names(game, 1) == ["forest", BEAR, "island", "swamp", "mountain", "plains"]

    def test_a_depth_of_one_is_the_top(self, builder):
        """The ordinal counts from 1, so 1 must be the top card and not the second."""
        game, bear = a_tuckable(builder)
        tuck(game, from_top={"const": 1})

        assert game.state.players[1].library[0] == bear

    def test_no_depth_is_still_the_top(self, builder):
        """Today's behaviour, unchanged: every tuck already in the pool omits it."""
        game, bear = a_tuckable(builder)
        tuck(game)

        assert game.state.players[1].library[0] == bear
        assert names(game, 1) == [BEAR, *STACK]

    def test_the_depth_may_be_computed(self, builder):
        """`from_top` is a value expression like every other numeric field, so a
        card can read one off the board rather than printing a literal."""
        game, bear = a_tuckable(builder)
        tuck(game, from_top={"count": {"zone": "library", "controller": "opponent"}})

        # Five cards in the opponent's library, so fifth from the top.
        assert game.state.players[1].library.index(bear) == 4

    def test_the_card_is_in_the_library_zone_and_off_the_battlefield(self, builder):
        """The move is a real zone change, not a list edit: `hideaway` learned
        this the hard way -- a card spliced into a library while its `zone` still
        said something else is invisible to everything but the list."""
        game, bear = a_tuckable(builder)
        tuck(game, from_top={"const": 4})

        assert game.state.objects[bear].zone is Zone.LIBRARY
        assert bear not in game.state.battlefield


class TestTheClamp:
    def test_a_library_shorter_than_the_depth_takes_it_at_the_bottom(self, builder):
        """"As deep as it goes" -- and the card is still *in* the library."""
        game, _ = a_tuckable(builder, ["forest", "island"])
        tuck(game, from_top={"const": 4})

        assert names(game, 1) == ["forest", "island", BEAR]

    def test_an_empty_library_takes_it_as_the_only_card(self, builder):
        """The boundary that would crash or wrap: index 4 into a list of none."""
        game, bear = a_tuckable(builder, [])
        tuck(game, from_top={"const": 4})

        assert game.state.players[1].library == [bear]

    def test_a_depth_of_exactly_the_library_size_is_the_bottom(self, builder):
        """Off-by-one at the far end: five cards, fifth from the top is *not*
        past the end -- it is the fifth, with one card left under it."""
        game, _ = a_tuckable(builder)
        tuck(game, from_top={"const": 5})

        assert names(game, 1) == ["forest", "island", "swamp", "mountain", BEAR, "plains"]

    def test_a_computed_depth_of_zero_is_the_top_not_the_bottom(self, builder):
        """The direction that is silent rather than loud. `list.insert(-1)` puts
        a card *second from the bottom*, so an ordinal that computes to zero on
        an empty board must be floored at the top rather than passed through."""
        game, bear = a_tuckable(builder)
        tuck(game, from_top={"count": {"zone": "battlefield", "types": ["Land"]}})

        assert game.state.players[1].library[0] == bear

    def test_a_raw_negative_index_still_lands_on_top(self, builder):
        """`move_object` is public and does its own clamping, so the guarantee
        does not depend on `put_on_top` having floored the ordinal first."""
        game, bear = a_tuckable(builder)
        move_object(game.state, bear, Zone.LIBRARY, to_player=1, to_index=-3)

        assert game.state.players[1].library[0] == bear


class TestWhoseLibrary:
    def test_a_stolen_permanent_goes_to_its_owners_library(self, builder):
        """"Into **its owner's** library." The only board where owner and
        controller differ is the only board where this is observable -- and
        sending it to the thief's library would give them the card permanently,
        which no tuck spell has ever done."""
        game, bear = a_tuckable(builder)
        game.state.objects[bear].controller = 0
        library_before = len(game.state.players[0].library)

        tuck(game, from_top={"const": 4}, controller=0)

        assert game.state.objects[bear].zone is Zone.LIBRARY
        assert bear in game.state.players[1].library, "the owner's library"
        assert len(game.state.players[0].library) == library_before
        assert game.state.players[1].library.index(bear) == 3, "at the printed depth"


class TestNothingElseMoved:
    """`to_index` is optional and library-only; every other caller is untouched."""

    def test_a_graveyard_ignores_an_index(self, builder):
        """Every non-library zone is an unordered pile, and an index that
        reordered a graveyard would change what `return_from_graveyard` finds
        first for no reason a rule asks for."""
        game = (
            builder(players=2)
            .battlefield(1, [BEAR])
            .graveyard(1, ["forest", "island"])
            .build(advance=False)
        )
        bear = only_oid(game, BEAR, 1)
        move_object(game.state, bear, Zone.GRAVEYARD, to_player=1, to_index=0)

        assert game.state.players[1].graveyard[-1] == bear, "appended, like every death"

    def test_the_default_move_still_appends(self, builder):
        """Draw, mill, discard and every death pass no position at all. This is
        the behaviour those thirty-odd callers depend on."""
        game, bear = a_tuckable(builder)
        move_object(game.state, bear, Zone.LIBRARY, to_player=1)

        assert game.state.players[1].library[-1] == bear

    def test_to_top_still_means_the_top(self, builder):
        """The boolean is still there and still wins over nothing."""
        game, bear = a_tuckable(builder)
        move_object(game.state, bear, Zone.LIBRARY, to_player=1, to_top=True)

        assert game.state.players[1].library[0] == bear


class TestTheLoaderRefusesADepthNothingReads:
    """Both ways of writing it wrong load clean and play as a different card."""

    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_tucker",
                "name": "Test Tucker",
                "mana_cost": "{1}{U}",
                "types": ["Instant"],
                "oracle_text": "Put target creature into its owner's library fourth from the top.",
                "targets": [
                    {"id": "t1", "kind": "permanent", "selector": {"types": ["Creature"]}}
                ],
                "spell_effects": [effect],
            }
        )

    def test_the_printed_shape_compiles(self):
        compile_card(
            self._card(
                {"op": "put_on_top", "objects": {"target": "t1"}, "from_top": {"const": 4}}
            )
        )

    def test_a_depth_on_an_op_that_cannot_read_it_is_refused(self):
        """`draw` takes `amount`, ignores everything else, and would load a card
        that reads "fourth from the top" and does nothing of the kind."""
        with pytest.raises(DslError, match="only put_on_top reads it"):
            compile_card(self._card({"op": "draw", "amount": 1, "from_top": {"const": 4}}))

    def test_a_zero_ordinal_is_refused(self):
        """The op floors it, but a card that needed correcting was authored
        wrong: there is no zeroth card in a library."""
        with pytest.raises(DslError, match="counts from 1"):
            compile_card(
                self._card(
                    {"op": "put_on_top", "objects": {"target": "t1"}, "from_top": {"const": 0}}
                )
            )

    def test_a_negative_ordinal_is_refused(self):
        with pytest.raises(DslError, match="counts from 1"):
            compile_card(
                self._card({"op": "put_on_top", "objects": {"target": "t1"}, "from_top": -2})
            )

    def test_a_nonsense_value_expression_is_still_refused(self):
        """`from_top` goes through `validate_value` like any numeric field."""
        with pytest.raises(DslError):
            compile_card(
                self._card(
                    {"op": "put_on_top", "objects": {"target": "t1"}, "from_top": {"nope": 1}}
                )
            )
