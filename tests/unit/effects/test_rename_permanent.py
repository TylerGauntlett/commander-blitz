"""Changing a permanent's name.

    "…you may have The Irencrag **become a legendary Equipment artifact named
    Everflame, Heroes' Legacy**."                        -- The Irencrag

Nothing in the engine could change a name. The characteristics pipeline has no
name layer at all, and `_matches_printed` says so where it tests
`selector.name`: "a name is the most printed characteristic there is and nothing
in the pipeline can change one, so it is safe here for the same reason `types`
is."

Both near misses are the wrong shape. `change_text` rewrites *creature types*
and the loader refuses it anything else -- "change_text only implements
'creature_type'". `become_copy`'s `except_name` renames a permanent that is
**copying** something (706.2's override), which The Irencrag is not: it stays
itself and is called something else.

So the name goes on the **object** and is read by `GameState.card_of`, the
single funnel that decides a permanent's current face -- the same place the copy
override already lives. One place, and every reader gets it at once: the
characteristics layers, `selector.name`, the legend rule and the serializer.

Cleared by `reset_permanent_state`, so a renamed permanent that leaves the
battlefield answers to its printed name again (400.7).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy
from tests.conftest import only_oid, pass_until

CRAG = "t_rn_crag"  # renames itself as it enters
PLAIN = "t_rn_plain"  # printed name "Everflame"
OTHER = "t_rn_other"


def board(builder, cast_card: str | None = None, mine=()):
    """A position with ``mine`` already down, and ``cast_card`` cast from hand.

    The rename rides an enters trigger, and the builder puts permanents onto the
    battlefield without firing one -- so the card under test is *cast*, which is
    also the only way the trigger's own "when this enters" is true.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4)
        .battlefield(0, list(mine))
        .hand(0, [cast_card] if cast_card else [])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    if cast_card is not None:
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == cast_card
        )
        game.apply(action)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    return game


def name_of(game, card_id: str) -> str:
    oid = only_oid(game, card_id)
    return game.state.card_of(game.state.objects[oid]).name


class TestTheNameChanges:
    def test_the_permanent_answers_to_the_new_name(self, builder):
        game = board(builder, cast_card=CRAG)
        assert name_of(game, CRAG) == "Everflame"

    def test_it_is_still_the_same_card(self, builder):
        """A rename is not a copy: the permanent is the card it always was,
        called something else, and `def_id` still says so."""
        game = board(builder, cast_card=CRAG)
        oid = only_oid(game, CRAG)
        assert game.state.objects[oid].def_id == CRAG

    def test_another_permanent_is_untouched(self, builder):
        game = board(builder, cast_card=CRAG, mine=[OTHER])
        assert name_of(game, OTHER) == "Test Unrenamed Artifact"


class TestItReachesTheReaders:
    def test_a_name_selector_finds_it(self, builder):
        """`selector.name` reads the card `card_of` hands back, so a renamed
        permanent answers a question asked about the new name -- which is what
        makes the rename a fact about the game rather than a caption."""
        from commanderblitz.engine.characteristics import _matches_printed

        game = board(builder, cast_card=CRAG)
        oid = only_oid(game, CRAG)
        card = game.state.card_of(game.state.objects[oid])
        assert _matches_printed(card, {"name": "Everflame"})

    def test_and_no_longer_answers_to_the_printed_one(self, builder):
        from commanderblitz.engine.characteristics import _matches_printed

        game = board(builder, cast_card=CRAG)
        oid = only_oid(game, CRAG)
        card = game.state.card_of(game.state.objects[oid])
        assert not _matches_printed(card, {"name": "Test Irencrag"})

    def test_a_permanent_printed_with_that_name_matches_too(self, builder):
        """The control: the selector is not being fooled, it is being told."""
        from commanderblitz.engine.characteristics import _matches_printed

        game = board(builder, mine=[PLAIN])
        oid = only_oid(game, PLAIN)
        assert _matches_printed(game.state.card_of(game.state.objects[oid]), {"name": "Everflame"})


class TestItWearsOffOnLeaving:
    def test_a_renamed_permanent_that_dies_is_itself_again(self, builder):
        """400.7. The object that comes back is a new one, and
        `reset_permanent_state` is where every other such fact is cleared."""
        game = board(builder, cast_card=CRAG)
        oid = only_oid(game, CRAG)
        destroy(game.state, oid)
        assert game.state.objects[oid].renamed_to is None
        assert game.state.card_of(game.state.objects[oid]).name == "Test Irencrag"


class TestTheLoaderPlacesIt:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "It becomes named Everflame.",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_a_rename_loads(self):
        compile_card(
            self._card({"op": "rename", "name": "Everflame", "objects": {"self_only": True}})
        )

    def test_a_rename_to_nothing_is_refused(self):
        """It would load, run, and leave the permanent answering to its printed
        name -- the printed line silently not happening."""
        with pytest.raises(DslError, match="rename needs a 'name'"):
            compile_card(self._card({"op": "rename", "objects": {"self_only": True}}))

    def test_a_blank_name_is_refused(self):
        with pytest.raises(DslError, match="rename needs a 'name'"):
            compile_card(
                self._card({"op": "rename", "name": "   ", "objects": {"self_only": True}})
            )

    def test_a_bare_name_on_another_op_is_refused(self):
        """Every other op that means anything by a name spells it inside a
        selector or a token id, so a bare one elsewhere is read by nobody."""
        with pytest.raises(DslError, match="read only by the rename op"):
            compile_card(
                self._card({"op": "draw", "amount": {"const": 1}, "name": "Everflame"})
            )
