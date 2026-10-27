"""The as-enters copy, with an exception and a duration.

    "You may have this creature enter as a copy of any creature on the
    battlefield, **except it has haste and dethrone**."     -- Dack's Duplicate

    "As this artifact enters, you may have it become a copy of any creature on
    the battlefield **until end of turn, except it has haste**."
                                                            -- Cursed Mirror

Both are the `self_enters_as_copy` replacement (614.1b), so the permanent is
never seen as itself; what they add is two things that replacement could not
say.

**The exception is a copiable value (707.9b), not a grant.** `except_`'s
``add_keywords`` is written onto the copy itself (`copying_keywords`, read by
`GameState.card_of`), so the Duplicate is a copy *with* haste. The near miss --
a printed static granting haste and dethrone -- is a different card: it would
keep working on the 0/0 the Duplicate is when it declines to copy, and it is a
layer-6 effect a `lose_all_abilities` would strip while leaving the copy.

**The duration ends the copy and its exception together.** Cursed Mirror is a
copy only until cleanup (`clear_until_eot`'s timed form); afterwards it is its
printed self again, a noncreature mana rock, and the haste goes with the copy.
Without the duration the Mirror would stay a hasty copy for ever, a strictly
better card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import abilities_of, chars
from commanderblitz.engine.combat import can_attack
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import find_action, keywords, only_oid, pass_until, plus_one_counters, settle
from tests.unit.copies.test_enters_as_copy import cast, name_of

DUPLICATE = "t_eacx_duplicate"  # 0/0, copy except haste and dethrone
MIRROR = "t_eacx_mirror"  # {T}: Add {R}; copy until end of turn, except haste
BEAR = "t_bear"  # 2/2 vanilla, the thing copied


def position(builder, spell: str):
    """The Bear is the opponent's: "any creature on the battlefield"."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4)
        .battlefield(1, [BEAR])
        .hand(0, [spell])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .life(0, 20)
        .life(1, 30)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def to_attackers(game) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )


class TestTheExceptionIsPartOfTheCopy:
    def test_the_copy_has_the_added_keywords(self, builder):
        game = position(builder, DUPLICATE)
        cast(game, DUPLICATE)
        oid = only_oid(game, DUPLICATE, 0)
        assert name_of(game, oid) == "Test Bear"
        assert {"haste", "dethrone"} <= keywords(game, oid)
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (2, 2)

    def test_the_copied_card_itself_is_untouched(self, builder):
        """The exception belongs to this copy, not to the Bear it copied."""
        game = position(builder, DUPLICATE)
        cast(game, DUPLICATE)
        bear = only_oid(game, BEAR, 1)
        assert not {"haste", "dethrone"} & keywords(game, bear)

    def test_haste_lets_it_attack_the_turn_it_arrives(self, builder):
        game = position(builder, DUPLICATE)
        cast(game, DUPLICATE)
        assert can_attack(game.state, only_oid(game, DUPLICATE, 0))

    def test_dethrone_triggers_off_the_exception(self, builder):
        game = position(builder, DUPLICATE)
        cast(game, DUPLICATE)
        oid = only_oid(game, DUPLICATE, 0)
        to_attackers(game)
        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),))
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        settle(game)
        assert plus_one_counters(game, oid) == 1

    def test_declining_the_copy_declines_the_exception(self, builder):
        """No copy, no exception: the keywords are not printed on the card."""
        game = position(builder, DUPLICATE)
        cast(game, DUPLICATE, say_yes=False)
        assert not any(
            game.state.objects[o].def_id == DUPLICATE for o in game.state.battlefield
        ), "a 0/0 that copied nothing is put into the graveyard (704.5f)"

    def test_the_exception_does_not_outlive_the_object(self, builder):
        """400.7: a permanent that leaves is a new object, copying nothing."""
        game = position(builder, DUPLICATE)
        cast(game, DUPLICATE)
        oid = only_oid(game, DUPLICATE, 0)
        move_object(game.state, oid, Zone.HAND)
        obj = game.state.objects[oid]
        assert obj.copying is None and obj.copying_keywords is None
        assert "haste" not in game.state.card_of(obj).keywords

    def test_a_permanent_copy_survives_cleanup(self, builder):
        game = position(builder, DUPLICATE)
        cast(game, DUPLICATE)
        oid = only_oid(game, DUPLICATE, 0)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn, limit=800)
        assert name_of(game, oid) == "Test Bear"
        assert "haste" in keywords(game, oid)


class TestUntilEndOfTurn:
    def test_this_turn_it_is_a_hasty_copy(self, builder):
        game = position(builder, MIRROR)
        cast(game, MIRROR)
        oid = only_oid(game, MIRROR, 0)
        assert name_of(game, oid) == "Test Bear"
        assert "Creature" in {str(t) for t in chars(game.state, oid).types}
        assert "haste" in keywords(game, oid)
        assert can_attack(game.state, oid)
        assert not any("Add {R}" in a.text for a in abilities_of(game.state, oid))

    def test_after_cleanup_it_is_its_printed_self(self, builder):
        game = position(builder, MIRROR)
        cast(game, MIRROR)
        oid = only_oid(game, MIRROR, 0)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn, limit=800)
        assert name_of(game, oid) == "Test Mirror"
        assert "Creature" not in {str(t) for t in chars(game.state, oid).types}
        assert "haste" not in keywords(game, oid)
        assert game.state.objects[oid].copying_keywords is None
        assert any("Add {R}" in a.text for a in abilities_of(game.state, oid))

    def test_declined_it_is_a_mana_rock(self, builder):
        game = position(builder, MIRROR)
        cast(game, MIRROR, say_yes=False)
        oid = only_oid(game, MIRROR, 0)
        assert name_of(game, oid) == "Test Mirror"
        assert "haste" not in keywords(game, oid)


class TestTheLoaderChecksIt:
    def _card(self, replacement):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "You may have this enter as a copy of any creature.",
                "mana_cost": "{1}",
                "types": ["Artifact"],
                "replacements": [replacement],
            }
        )

    def _copy(self, **extra):
        return {
            "event": "self_enters_as_copy",
            "copying": {"zone": "battlefield", "types": ["Creature"]},
            **extra,
        }

    def test_a_well_formed_clause_loads(self):
        compile_card(
            self._card(
                self._copy(duration="end_of_turn", except_={"add_keywords": ["haste"]})
            )
        )

    def test_an_unknown_keyword_is_refused(self):
        with pytest.raises(DslError, match="unknown keyword 'hasty'"):
            compile_card(self._card(self._copy(except_={"add_keywords": ["hasty"]})))

    def test_an_empty_exception_is_refused(self):
        with pytest.raises(DslError, match="non-empty list"):
            compile_card(self._card(self._copy(except_={"add_keywords": []})))

    def test_an_exception_it_cannot_apply_is_refused(self):
        """Silently dropped, "except its name is…" would be a different card."""
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(self._card(self._copy(except_={"name": "Gogo"})))

    @pytest.mark.parametrize(
        "extra",
        [{"except_": {"add_keywords": ["haste"]}}, {"duration": "end_of_turn"}],
    )
    def test_refused_on_another_event(self, extra):
        with pytest.raises(DslError, match="read only by 'self_enters_as_copy'"):
            compile_card(self._card({"event": "self_enters_tapped", **extra}))
