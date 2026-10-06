"""A spell whose casting window is narrower than instant speed.

    "Cast this spell only before the combat damage step."      -- Berserk

`casting._timing_ok` is the one gate on casting speed and it could only **widen**:
it returns True the moment it sees an instant, and everything after it --
`flash`, `cast_as_though_flash`, an ability's `sorcery_speed_only` -- is another
way of saying yes. `CardModel` had no field that could say no, and the three
sibling lines in the queue ("only during combat", "only during your turn") had
nowhere to live either.

So `cast_before_step` is asked **first**, before any of the widening branches.
Written after them it would load, read exactly like the printed card, and never
once refuse a cast -- the silent failure this engine is built to catch.

**510.4 is why the card says one step and the engine checks another.** With first
strike on the board a combat phase has two combat damage steps, and both of them
are combat damage steps, so "only before the combat damage step" closes at the
earlier one. The card file says what the card prints and `_WINDOW_CLOSES` reads
the rule.

A misspelled step is a load error rather than a fall back to "no restriction",
which would be a strictly better Berserk -- castable after blockers, with the
damage already dealt.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step
from automtg.engine.errors import DslError

BERSERK = "t_cbs_berserk"  # "only before the combat damage step"
FREE = "t_cbs_free"  # the same instant, unrestricted


def at(builder, step: Step, spell: str = BERSERK):
    """A priority window in ``step``, with ``spell`` in hand and mana for it.

    Built in the precombat main and then *moved*, rather than built in the
    target step. `GameBuilder` hands the turn to the engine, and a turn with no
    attackers walks straight through combat into the next upkeep -- so a
    position built at `COMBAT_DAMAGE` is not in one by the time anything can be
    asked. Setting the step on a live priority window keeps the question going
    through `legality` and `_timing_ok` exactly as a real cast does, while
    naming the moment the test is about.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4)
        .battlefield(1, ["t_bear"])
        .library(0, ["forest"] * 10)
        .hand(0, [spell])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    game.state.step = step
    return game


def castable(game, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


BEFORE = [Step.UPKEEP, Step.PRECOMBAT_MAIN, Step.BEGIN_COMBAT, Step.DECLARE_BLOCKERS]
AFTER = [Step.COMBAT_DAMAGE, Step.END_OF_COMBAT, Step.POSTCOMBAT_MAIN, Step.END_STEP]


class TestTheWindowIsOpenBefore:
    @pytest.mark.parametrize("step", BEFORE, ids=lambda s: s.name.lower())
    def test_it_can_be_cast(self, builder, step):
        assert castable(at(builder, step), BERSERK)


class TestTheWindowIsShutFrom:
    @pytest.mark.parametrize("step", AFTER, ids=lambda s: s.name.lower())
    def test_it_cannot_be_cast(self, builder, step):
        assert not castable(at(builder, step), BERSERK)

    @pytest.mark.parametrize("step", AFTER, ids=lambda s: s.name.lower())
    def test_but_an_unrestricted_instant_still_can(self, builder, step):
        """The control at every step, so "cannot be cast" is never really "this
        position offers no casts at all"."""
        assert castable(at(builder, step, FREE), FREE)


class TestFirstStrikeClosesItEarly:
    def test_the_first_strike_damage_step_is_a_combat_damage_step(self, builder):
        """510.4. Both damage steps are combat damage steps, so a card that says
        "before the combat damage step" may not be cast in either.

        Checked against `_window_closes_at` rather than only through a board,
        because reaching a first-strike damage step needs a first striker and
        this claim is about the rule, not about that board.
        """
        from automtg.engine.casting import _window_closes_at

        assert _window_closes_at(Step.COMBAT_DAMAGE) is Step.FIRST_STRIKE_DAMAGE

    def test_any_other_step_closes_where_it_says(self, builder):
        from automtg.engine.casting import _window_closes_at

        assert _window_closes_at(Step.END_STEP) is Step.END_STEP

    def test_it_cannot_be_cast_in_the_first_strike_step(self, builder):
        assert not castable(at(builder, Step.FIRST_STRIKE_DAMAGE), BERSERK)


class TestTheLoaderResolvesTheStep:
    def _card(self, step):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Cast this spell only before the combat damage step.",
                "mana_cost": "{G}",
                "types": ["Instant"],
                "cast_before_step": step,
                "spell_effects": [{"op": "draw", "amount": {"const": 1}}],
            }
        )

    def test_a_real_step_resolves(self):
        assert compile_card(self._card("combat_damage")).cast_before_step is Step.COMBAT_DAMAGE

    def test_a_typo_is_refused(self):
        """Unrefused it would read as "no restriction" -- a strictly better
        Berserk, castable after blockers with the damage already dealt."""
        with pytest.raises(DslError, match="cast_before_step"):
            compile_card(self._card("combat_damge"))

    def test_absent_means_no_restriction(self):
        card = CardModel.model_validate(
            {
                "id": "y",
                "name": "Y",
                "oracle_text": "Draw a card.",
                "mana_cost": "{G}",
                "types": ["Instant"],
                "spell_effects": [{"op": "draw", "amount": {"const": 1}}],
            }
        )
        assert compile_card(card).cast_before_step is None
