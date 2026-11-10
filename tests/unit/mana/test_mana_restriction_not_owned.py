"""`not_owned` in a `mana_restriction` -- mana for spells the payer does not own.

    Thieving Varmint -- "{T}, Pay 1 life: Add two mana of any one color. Spend
    this mana only to cast spells you don't own."

The owner of a card is the player who started the game with it in their deck
(108.3), and casting it does not change that. So the restriction asks about the
*object* being cast, which the printed face `spell_purpose` reads cannot answer:
every cast lane hands it the caster and the object's owner, the same owner it
hands `cost_reduction` for `spell_cost_reduction`'s `not_owned`. A copy of a
card cast is owned by the player who cast it (707.10), so `cast_copy` hands down
the caster and the mana never pays for one. A purpose that names no owner fails
closed, the under-permitting direction every restriction takes.

The near miss is Klauth's `{"cast": "any"}`, which funds the caster's own spells
too -- a strictly better card than the printed one.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.costs import spell_purpose
from commanderblitz.engine.enums import DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import (
    ACTIVATE,
    CAST,
    OTHER_PAYMENT,
    SpendPurpose,
    _permits,
    compile_restriction,
)
from tests.conftest import pass_until
from tests.unit.costs.test_cost_reduction_not_owned import (
    CANE,
    DIVINATION,
    RELIC,
    casts,
    table,
    tapped_mountains,
)

VARMINT = "t_varmint_mana"  # {T}, Pay 1 life: two mana of one colour, not-owned only
FONT = "t_unowned_font"  # {T}: Add {C}{C}, not-owned only -- tap-only, so the solver taps it

RESTRICTION = {"cast": [[{"not_owned": True}]]}


def purpose(*, not_owned, kind=CAST):
    return SpendPurpose(kind, frozenset({"artifact"}), not_owned=not_owned)


def oid_of(game, def_id: str) -> int:
    state = game.state
    return next(o for o in state.battlefield if state.objects[o].def_id == def_id)


def tap_the_varmint(game) -> None:
    """Activate the Varmint for {W}{W}, the colour of nothing on this board."""
    varmint = oid_of(game, VARMINT)
    action = next(a for a in game.legal_actions() if a.source == varmint)
    game.apply(action)


class TestThePurposeAnswersIt:
    def test_an_opponents_card_is_not_owned(self, registry):
        assert spell_purpose(registry.get(RELIC), caster=0, owner=1).not_owned is True

    def test_your_own_card_is_owned(self, registry):
        assert spell_purpose(registry.get(RELIC), caster=0, owner=0).not_owned is False

    def test_a_printed_face_alone_does_not_say(self, registry):
        assert spell_purpose(registry.get(RELIC)).not_owned is None
        assert spell_purpose(registry.get(RELIC), caster=0).not_owned is None


class TestThePredicate:
    def test_a_spell_you_dont_own_is_permitted(self):
        assert compile_restriction(RESTRICTION, "test").cast[0].satisfied_by(
            purpose(not_owned=True)
        )

    def test_a_spell_you_own_is_not(self):
        assert not compile_restriction(RESTRICTION, "test").cast[0].satisfied_by(
            purpose(not_owned=False)
        )

    def test_an_unanswered_question_fails(self):
        assert not compile_restriction(RESTRICTION, "test").cast[0].satisfied_by(
            purpose(not_owned=None)
        )

    def test_it_pays_for_no_activation_and_no_other_payment(self):
        restriction = compile_restriction(RESTRICTION, "test")
        assert not _permits(restriction, purpose(not_owned=True, kind=ACTIVATE))
        assert not _permits(restriction, OTHER_PAYMENT)


class TestTheVarmintsPool:
    """The life cost keeps the ability out of the solver, so its two mana sit in
    the pool and are spent from there -- tagged with the ability's restriction
    by `costs.activate_mana_ability`, or they would pay for anything. A {4}
    artifact off two Mountains needs them both."""

    def test_a_stolen_relic_is_bought_with_it(self, builder):
        game = table(builder, board=[VARMINT], exile_theirs=[RELIC], lands=2)
        assert not casts(game, RELIC)
        tap_the_varmint(game)
        assert game.state.players[0].life == 39
        assert casts(game, RELIC)

    def test_your_own_exiled_relic_is_not(self, builder):
        game = table(builder, board=[VARMINT], exile_mine=[RELIC], lands=2)
        tap_the_varmint(game)
        assert not casts(game, RELIC)

    def test_the_cast_spends_the_pool(self, builder):
        game = table(builder, board=[VARMINT], exile_theirs=[RELIC], lands=2)
        tap_the_varmint(game)
        game.apply(casts(game, RELIC)[0])
        assert tapped_mountains(game) == 2
        stolen = spell_purpose(game.state.registry.get(RELIC), caster=0, owner=1)
        assert not any(game.state.players[0].mana_pool.spendable(stolen))


class TestTheSolverTapsTheFont:
    """The same restriction on a tap-only source, offered or withheld by
    `mana_sources` before the solver sees it."""

    def test_a_stolen_relic_is_castable(self, builder):
        assert casts(table(builder, board=[FONT], exile_theirs=[RELIC], lands=2), RELIC)

    def test_your_own_exiled_relic_is_not(self, builder):
        assert not casts(table(builder, board=[FONT], exile_mine=[RELIC], lands=2), RELIC)

    def test_the_cast_taps_the_font(self, builder):
        game = table(builder, board=[FONT], exile_theirs=[RELIC], lands=2)
        game.apply(casts(game, RELIC)[0])
        assert game.state.objects[oid_of(game, FONT)].tapped
        assert tapped_mountains(game) == 2


class TestACopyIsOwnedByItsCaster:
    """`cast_copy` of an opponent's card: the copy is the caster's (707.10), so
    the Font cannot pay its {4}, whoever owns the card copied."""

    def offered(self, builder, islands: int) -> bool:
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * islands + [FONT])
            .battlefield(1, ["plains"])
            .graveyard(1, [DIVINATION])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .hand(0, [CANE])
            .hand(1, ["t_plain_instant"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        game.apply(casts(game, CANE)[0])
        pass_until(
            game,
            lambda g: not any(i.def_id == CANE for i in g.state.stack)
            or ((d := g.pending()) is not None and d.kind is not DecisionKind.PRIORITY),
        )
        decision = game.pending()
        return decision is not None and decision.kind is DecisionKind.MAY

    def test_the_font_does_not_pay_for_the_copy(self, builder):
        """Two Islands and the Font's {C}{C} would be {4}, if the copy were stolen."""
        assert not self.offered(builder, 3)

    def test_four_islands_do(self, builder):
        assert self.offered(builder, 5)


class TestTheLoaderChecksIt:
    def test_true_compiles(self):
        assert compile_restriction(RESTRICTION, "test").cast[0].not_owned is True

    @pytest.mark.parametrize("value", [False, 1, "yes", {"op": "=", "value": 1}])
    def test_anything_but_true_is_refused(self, value):
        with pytest.raises(DslError, match="not_owned"):
            compile_restriction([[{"not_owned": value}]], "test")

    def test_the_activate_half_refuses_it(self):
        """No ability is a spell anyone owns; the group would pay for nothing."""
        with pytest.raises(DslError, match="cast"):
            compile_restriction(
                {"cast": [[{"not_owned": True}]], "activate": [[{"not_owned": True}]]}, "test"
            )

    def test_the_word_as_a_name_is_refused(self):
        with pytest.raises(DslError, match="predicate"):
            compile_restriction([["not_owned"]], "test")
