""""You may cast this spell as though it had flash by <paying a cost>."

Tegwyll's Scouring is the witness: "…by tapping three untapped creatures you
control with flying in addition to paying its other costs." Rout, Ghitu Fire,
Harbinger of the Tides and Mystical Tether print the mana form, "…if you pay
{2} more to cast it". Both are `flash_cost`, the card's own flash permission
with a price on it.

The rules argument. 307.1 lets a sorcery be cast only by the active player in a
main phase with an empty stack, and flash (702.8a) lifts that for a spell that
has it. "As though it had flash" is that permission without the keyword, and
here the permission is bought: the price is an additional cost (601.2f), paid
with the others (601.2g-h), and owed only by a cast the permission is what
makes legal. At sorcery timing the card is cast as printed, and nothing extra
is paid. A cast another permission already allows (Vedalken Orrery) is not
using this one, so it does not pay for it either.

Without this the card has two wrong readings. `as_though_flash: true` makes the
sweeper an instant for free, a strictly better card than the printed one.
Dropping the sentence makes it a sorcery, strictly worse. And charging the cost
on every cast, as a plain `additional_cost` would, makes the sorcery-speed cast
cost three tapped fliers it does not owe.

The cards are `t_fc_scouring` and `t_fc_rout`, in
tests/data/flash_cost.cards.json.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import legality
from commanderblitz.engine.casting import flash_cost_owed
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, settle

SCOURING = "t_fc_scouring"  # {R}: flash by tapping three untapped fliers you control
ROUT = "t_fc_rout"  # {R}: flash for {2} more
FLIER = "t_sky_flier"  # 1/1 flier
BEAR = "t_ground_bear"  # 2/2, no flying
ORRERY = "t_orrery"  # you may cast spells as though they had flash
BOLT = "t_bolt"  # {R} instant, something to hold the stack open
MOUNTAIN = "mountain"


def position(
    builder,
    *,
    step: Step = Step.PRECOMBAT_MAIN,
    creatures: tuple[str, ...] = (FLIER, FLIER, FLIER),
    mountains: int = 3,
    hand: tuple[str, ...] = (SCOURING, ROUT),
    extra: tuple[str, ...] = (),
    active: int = 0,
):
    """Player 0 at ``step`` on ``active``'s turn, holding ``hand``.

    An upkeep or a combat step is instant timing on the caster's own turn, so
    the only thing that moves between tests is whether 307.1 is met.
    """
    game = (
        builder(players=2)
        .battlefield(0, [MOUNTAIN] * mountains + list(creatures) + list(extra))
        .battlefield(1, [MOUNTAIN] * 3)
        .hand(0, list(hand))
        .hand(1, [BOLT])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(step)
        .active(active)
        .build(advance=False)
    )
    for player in game.state.players:
        player.full_control = True
    game._advance()
    return game


def casts(game, card_id: str) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


def cast(game, card_id: str):
    (action,) = casts(game, card_id)
    game.apply(action)
    return action


def tapped_fliers(game) -> int:
    return sum(game.state.objects[o].tapped for o in oids_of(game, FLIER, 0))


def untapped_mountains(game) -> int:
    return sum(not game.state.objects[o].tapped for o in oids_of(game, MOUNTAIN, 0))


class TestAtSorceryTiming:
    """The card is cast as printed, and the extra cost is not paid."""

    def test_one_line_and_it_owes_nothing(self, builder):
        game = position(builder)
        (line,) = casts(game, SCOURING)
        assert not line.flash_cost
        assert not flash_cost_owed(game.state, 0, game.state.card(line.source))

    def test_no_flier_is_needed(self, builder):
        game = position(builder, creatures=())
        assert casts(game, SCOURING)

    def test_casting_it_taps_no_flier(self, builder):
        game = position(builder)
        cast(game, SCOURING)
        settle(game)
        assert tapped_fliers(game) == 0
        assert game.state.players[0].life == 41

    def test_the_mana_form_costs_the_printed_price(self, builder):
        game = position(builder, mountains=1)
        (line,) = casts(game, ROUT)
        assert not line.flash_cost


class TestAtInstantTiming:
    """Outside 307.1 the cast is legal only by paying the cost."""

    @pytest.mark.parametrize("step", [Step.UPKEEP, Step.BEGIN_COMBAT, Step.END_STEP])
    def test_it_is_castable_by_paying(self, builder, step):
        game = position(builder, step=step)
        (line,) = casts(game, SCOURING)
        assert line.flash_cost

    def test_the_fliers_end_tapped(self, builder):
        game = position(builder, step=Step.UPKEEP)
        cast(game, SCOURING)
        settle(game)
        assert tapped_fliers(game) == 3
        assert game.state.players[0].life == 41

    def test_on_an_opponents_turn(self, builder):
        """In the opponent's main phase, asked of player 0's priority actions."""
        game = position(builder, active=1)
        (line,) = [
            a
            for a in legality._priority_actions(game.state, 0)
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == SCOURING
        ]
        assert line.flash_cost

    def test_with_something_on_the_stack_in_its_own_main_phase(self, builder):
        """Its own main phase is not enough: 307.1 also wants an empty stack."""
        game = position(builder, hand=(SCOURING, BOLT))
        bolt = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BOLT
        )
        game.apply(bolt)
        assert game.state.stack
        (line,) = casts(game, SCOURING)
        assert line.flash_cost


class TestTheCostMustBePayable:
    def test_two_fliers_are_not_enough(self, builder):
        game = position(builder, step=Step.UPKEEP, creatures=(FLIER, FLIER))
        assert casts(game, ROUT), "the control: player 0 holds priority here"
        assert casts(game, SCOURING) == []

    def test_a_creature_without_flying_does_not_count(self, builder):
        game = position(builder, step=Step.UPKEEP, creatures=(FLIER, FLIER, BEAR))
        assert casts(game, SCOURING) == []

    def test_a_tapped_flier_does_not_count(self, builder):
        game = position(builder, step=Step.UPKEEP)
        game.state.objects[oids_of(game, FLIER, 0)[0]].tapped = True
        assert casts(game, SCOURING) == []


class TestTheDiagnosticAgrees:
    """`legality.unplayable_reason` names the gate the action list closed."""

    def _hand_oid(self, game, card_id):
        return next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id)

    def test_too_few_fliers_is_timing(self, builder):
        game = position(builder, step=Step.UPKEEP, creatures=(FLIER, FLIER))
        oid = self._hand_oid(game, SCOURING)
        assert legality.unplayable_reason(game.state, 0, oid) == "timing"

    def test_the_two_more_is_mana(self, builder):
        # The instant keeps a priority stop open with nothing else castable.
        game = position(builder, step=Step.UPKEEP, mountains=2, hand=(ROUT, BOLT))
        oid = self._hand_oid(game, ROUT)
        assert legality.unplayable_reason(game.state, 0, oid) == "mana"

    def test_a_payable_line_has_no_reason(self, builder):
        game = position(builder, step=Step.UPKEEP)
        oid = self._hand_oid(game, SCOURING)
        assert legality.unplayable_reason(game.state, 0, oid) is None


class TestTheManaForm:
    """Rout's "{2} more", folded into the price where every additional cost is."""

    def test_two_mountains_are_not_enough_at_instant_speed(self, builder):
        game = position(builder, step=Step.UPKEEP, mountains=2, hand=(ROUT, BOLT))
        assert casts(game, BOLT), "the control: player 0 holds priority here"
        assert casts(game, ROUT) == []

    def test_three_mountains_pay_it(self, builder):
        game = position(builder, step=Step.UPKEEP, mountains=3, hand=(ROUT,))
        (line,) = casts(game, ROUT)
        assert line.flash_cost
        game.apply(line)
        settle(game)
        assert untapped_mountains(game) == 0
        assert game.state.players[0].life == 41

    def test_at_sorcery_timing_it_costs_one(self, builder):
        game = position(builder, mountains=3, hand=(ROUT,))
        cast(game, ROUT)
        settle(game)
        assert untapped_mountains(game) == 2


class TestAnotherPermissionIsNotThisOne:
    """Under Vedalken Orrery the cast is legal without the card's permission,
    so the card's price is not owed (601.2f charges the way it is cast)."""

    def test_the_orrery_line_owes_nothing(self, builder):
        game = position(builder, step=Step.UPKEEP, creatures=(), extra=(ORRERY,))
        (line,) = casts(game, SCOURING)
        assert not line.flash_cost


class TestTheLoader:
    def _card(self, **extra):
        base = {
            "id": "x",
            "name": "X",
            "oracle_text": "",
            "mana_cost": "{R}",
            "types": ["Sorcery"],
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def test_the_cost_compiles(self):
        card = compile_card(self._card(flash_cost={"mana": "{2}"}))
        assert str(card.flash_cost.mana) == "{2}"
        assert not card.as_though_flash

    def test_it_is_refused_beside_the_free_permission(self):
        with pytest.raises(DslError, match="as_though_flash"):
            compile_card(self._card(flash_cost={"mana": "{2}"}, as_though_flash=True))

    def test_it_is_refused_on_an_instant(self):
        with pytest.raises(DslError, match="never be owed"):
            compile_card(self._card(types=["Instant"], flash_cost={"mana": "{2}"}))

    def test_it_is_refused_on_a_card_with_flash(self):
        with pytest.raises(DslError, match="never be owed"):
            compile_card(
                self._card(
                    types=["Creature"], power=1, toughness=1, keywords=["flash"],
                    flash_cost={"mana": "{2}"},
                )
            )

    def test_a_free_price_is_refused(self):
        with pytest.raises(DslError, match="charges nothing"):
            compile_card(self._card(flash_cost={}))

    def test_an_x_is_refused(self):
        with pytest.raises(DslError, match="no X"):
            compile_card(self._card(flash_cost={"mana": "{X}"}))

    @pytest.mark.parametrize("key", ["tap", "untap"])
    def test_a_spell_has_no_tap_symbol_to_pay(self, key):
        with pytest.raises(DslError, match="mean nothing"):
            compile_card(self._card(flash_cost={key: True, "mana": "{1}"}))


class TestTheResidualGateReadsTheLine:
    """The authoring residual gate claims the printed "as though it had flash"
    line for `flash_cost` on a permanent, whose line no `spell_effects` covers
    (Harbinger of the Tides, Mystical Tether) -- and only at the printed price.
    """

    LINE = "You may cast this spell as though it had flash if you pay {2} more to cast it."

    def _creature(self, price: str):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "x",
                    "name": "X",
                    "oracle_text": self.LINE,
                    "mana_cost": "{U}",
                    "types": ["Creature"],
                    "power": 1,
                    "toughness": 1,
                    "flash_cost": {"mana": price},
                }
            )
        )

    def test_the_printed_price_claims_the_line(self):
        from commanderblitz.cards.authoring.verify import residual_text

        assert residual_text(self._creature("{2}"), self.LINE) == ""

    def test_a_cheaper_price_does_not(self):
        from commanderblitz.cards.authoring.verify import residual_text

        assert residual_text(self._creature("{1}"), self.LINE) != ""
