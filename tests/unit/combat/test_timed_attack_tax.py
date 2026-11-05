"""The `attack_tax` op: Propaganda's toll with a clock, owned by no permanent.

"Until your next turn, creatures can't attack you unless their controller pays
{2} for each of those creatures." -- Summon: Yojimbo, chapters II and III.

The `attack_tax` static cannot say it: it is read off the battlefield for as
long as its source sits there and has no clock, so a Saga sacrificed after
chapter IV would end chapter III's tax a turn early. `cant_attack_player` has
the clock but no price -- a wall where the card prints a toll (508.1g: an
unpayable cost is a prohibition, a payable one is not). What is pinned:

1. The attack on the controller is priced, labelled, charged, and withheld when
   unpayable; a different seat and the controller's planeswalkers are untaxed.
2. It survives its source leaving, sums with a static tax and with another row.
3. It ends in the controller's untap step (or at cleanup for `this_turn`), and
   with the controller's elimination.
4. The loader refuses a tax with no price, an {X} price or an unknown duration.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import advance_to_step, only_oid, pass_until

BEAR = "grizzly_bears"
WALKER = "t_walker"
FORT = "t_propaganda"

YOJIMBO = {"op": "attack_tax", "cost": {"mana": "{2}"}, "duration": "until_your_next_turn"}


def install(game, spec=YOJIMBO, controller: int = 0, source: int | None = None) -> None:
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    gen = execute(ctx, [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def position(builder, *, lands: int = 2, players: int = 2, forts: int = 0, walker=False):
    """Player 1 attacks on its own turn; player 0 has taxed attacks on it."""
    b = builder(players=players).battlefield(1, [BEAR]).battlefield(1, ["forest"] * lands)
    if forts:
        b = b.battlefield(0, [FORT] * forts)
    if walker:
        b = b.battlefield(0, [WALKER])
    game = stocked(b, players).active(1).build()
    install(game)
    advance_to_step(game, Step.DECLARE_ATTACKERS)
    return game


def stocked(b, players: int = 2):
    """Libraries for every seat, so passing through a draw step loses nobody."""
    for pid in range(players):
        b.library(pid, ["forest"] * 30)
    return b


def on_controllers_main(builder, spec):
    """Player 0 installs ``spec`` in its own main phase; player 1 holds a Bear."""
    b = stocked(builder(players=2).battlefield(1, [BEAR]))
    game = b.active(0).step(Step.PRECOMBAT_MAIN).build(advance=False)
    install(game, spec)
    game._advance()
    return game


def attack_actions(game):
    return [a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER]


def untapped_forests(game, pid: int = 1) -> int:
    return sum(
        1
        for obj in game.state.battlefield_objects(pid)
        if obj.def_id == "forest" and not obj.tapped
    )


class TestTheAttackIsPriced:
    def test_offered_and_labelled_when_payable(self, builder):
        game = position(builder, lands=2)
        assert any("pay {2}" in (a.label or "") for a in attack_actions(game))

    def test_withheld_when_unpayable(self, builder):
        game = position(builder, lands=1)
        assert attack_actions(game) == []

    def test_declaring_charges_the_mana(self, builder):
        game = position(builder, lands=2)
        game.apply(attack_actions(game)[0])
        assert untapped_forests(game) == 0
        assert only_oid(game, BEAR, 1) in game.state.combat.attackers

    def test_without_the_row_the_attack_is_free(self, builder):
        game = builder(players=2).battlefield(1, [BEAR]).active(1).build()
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        assert attack_actions(game)
        assert not any("pay" in (a.label or "") for a in attack_actions(game))


class TestOnlyTheControllersSeat:
    def test_another_player_is_untaxed(self, builder):
        game = position(builder, lands=0, players=3)
        by_defender = {a.targets[0].id: (a.label or "") for a in attack_actions(game)}
        assert 0 not in by_defender, "no Forests: the taxed seat is closed"
        assert "pay" not in by_defender[2]

    def test_a_planeswalker_of_the_controller_is_untaxed(self, builder):
        """"Can't attack **you**" -- attacking a walker is not attacking its
        controller (506.2)."""
        game = position(builder, lands=0, walker=True)
        bear = only_oid(game, BEAR, 1)
        assert combat_mod.attack_tax_cost(game.state, bear, 0) is not None
        assert combat_mod.attack_tax_cost(game.state, bear, 0, planeswalker=True) is None


class TestItStandsAndStacks:
    def test_it_survives_its_source_leaving(self, builder):
        """No permanent owns it: the Saga sacrificed after IV takes nothing."""
        game = builder(players=2).battlefield(0, [FORT]).battlefield(1, [BEAR]).build()
        fort = only_oid(game, FORT, 0)
        install(game, source=fort)
        game.state.battlefield.remove(fort)
        game.state.objects.pop(fort)
        bear = only_oid(game, BEAR, 1)
        assert str(combat_mod.attack_tax_cost(game.state, bear, 0).mana) == "{2}"

    def test_it_sums_with_a_static_tax(self, builder):
        game = position(builder, lands=3, forts=1)
        assert attack_actions(game) == [], "{2} + {2} is {4}; three Forests cannot pay"

    def test_two_rows_are_two_taxes(self, builder):
        game = builder(players=2).battlefield(1, [BEAR]).build()
        install(game)
        install(game)
        bear = only_oid(game, BEAR, 1)
        assert str(combat_mod.attack_tax_cost(game.state, bear, 0).mana) == "{4}"


class TestTheClock:
    def test_it_ends_in_the_controllers_untap_step(self, builder):
        game = position(builder, lands=2)
        assert game.state.attack_taxes
        pass_until(game, lambda g: g.state.active_player == 0 and g.state.step > Step.UNTAP)
        assert game.state.attack_taxes == []

    def test_it_lasts_through_the_turns_in_between(self, builder):
        """Installed on the controller's turn, it is still there when the next
        player declares attackers -- the opponent's turn is the whole point."""
        game = on_controllers_main(builder, {**YOJIMBO})
        pass_until(
            game, lambda g: g.state.active_player == 1 and g.state.step is Step.DECLARE_ATTACKERS
        )
        assert game.state.active_player == 1
        assert len(game.state.attack_taxes) == 1
        assert not attack_actions(game), "no Forests: the {2} cannot be paid"

    def test_this_turn_ends_at_cleanup(self, builder):
        game = on_controllers_main(builder, {**YOJIMBO, "duration": "this_turn"})
        pass_until(
            game, lambda g: g.state.active_player == 1 and g.state.step is Step.DECLARE_ATTACKERS
        )
        assert game.state.active_player == 1
        assert game.state.attack_taxes == []
        assert attack_actions(game), "the tax ended with its turn"

    def test_it_ends_when_the_controller_leaves(self, builder):
        game = builder(players=3).build()
        install(game)
        sba.declare_loss(game.state, [0])
        assert game.state.attack_taxes == []


class TestTheLoader:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_bad_timed_tax",
                "name": "Bad Timed Tax",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "types": ["Sorcery"],
                "colors": ["W"],
                "color_identity": ["W"],
                "spell_effects": [{"op": "attack_tax", **effect}],
            }
        )

    def test_the_shipped_shape_loads(self):
        compile_card(self._card({"cost": {"mana": "{2}"}, "duration": "until_your_next_turn"}))

    @pytest.mark.parametrize(
        ("effect", "match"),
        [
            ({"duration": "until_your_next_turn"}, "needs 'cost' and 'duration'"),
            ({"cost": {"mana": "{2}"}}, "needs 'cost' and 'duration'"),
            ({"cost": {"mana": "{X}"}, "duration": "this_turn"}, "fixed, non-empty"),
            ({"cost": {"mana": ""}, "duration": "this_turn"}, "fixed, non-empty"),
            ({"cost": {"mana": "{2}", "pay_life": 2}, "duration": "this_turn"}, "attack_tax 'cost'"),
            ({"cost": {"mana": "{2}"}, "duration": "this_combat"}, "unknown attack_tax duration"),
        ],
    )
    def test_refusals(self, effect, match):
        with pytest.raises(DslError, match=match):
            compile_card(self._card(effect))
