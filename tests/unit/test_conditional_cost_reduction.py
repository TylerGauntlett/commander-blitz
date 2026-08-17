"""A cost reduction that can be switched off, and one that belongs to a variant.

    Crown of Gondor — "Equip {4}. This ability costs {3} less to activate if
    you're the monarch."

    Visions of Glory — "Flashback {8}{W}{W}. This spell costs {X} less to cast
    **this way**, where X is …"

Rule 601.2f and 118.7: a cost reduction alters the total cost, generic-only, and
never below zero. Two things the engine could not say before, and both fail
*silently* rather than loudly:

**Conditional.** `Cost.mana_reduction` took only `{"count": {filter}}` — a
per-object multiplier. A flat "{3} less if X" written that way would need a
filter matching exactly three permanents while the crown is yours and none
otherwise, which no filter over a board can express. The two card-level
reductions never reach an activated ability at all, and splitting the line into
two equip abilities leaves nothing able to switch the cheap one off. So Crown of
Gondor's equip was either always {4} or always {1} — a card that plays like a
different card, at a price nothing on screen would question.

**Variant-scoped.** `legality._cast_variant` picks a price per cast variant and
then applies `cost_reduction` to whatever it picked, because Ghalta costs less
however it is cast. A "costs {X} less to cast **this way**" rider written as a
card-level reduction therefore discounts the printed hand cast too — which is
the more dangerous of the two omissions, because the card still loads, still
plays, and is simply cheaper than it says from a zone the reader was not looking
at.

**One mechanism, three readers.** `costs.reduction_amount` is the whole
reduction language — `amount` / `count` / `total_power`, gated on an optional
`condition` — and the card-level `cost_reduction`, an activated ability's
`Cost.mana_reduction` and a graveyard cast's `Cost.mana_reduction` all go through
it. Two languages for "costs {N} less" would drift on what "for each" and "if"
mean; the variant scoping is then not a mechanism at all but *where the node is
read from*, which is the point the tests below pin.

**The offer and the charge are one number.** `can_pay` and `pay` both call
`ability_mana`; `_cast_variant` and `game._cast` both call `variant_reduction`.
A price that changes between being offered and being paid strands the payment —
the failure `life_cost` and `mana_produced` already exist to prevent.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.costs import ability_mana, can_pay, variant_reduction
from automtg.engine.enums import ActionKind, Step
from automtg.engine.primitives import become_monarch
from tests.conftest import only_oid, pass_until

CROWN = "t_monarch_equip"          # Equip {4}, {3} less if you're the monarch
SCALER = "t_flashback_discount"    # {4}{W}; flashback {8}{W}, {1} less per creature
CONDITIONAL = "t_conditional_flashback"  # {4}{W}; flashback {6}{W}, {4} less if monarch
BEAR = "t_bear"
PLAINS = "plains"


# --------------------------------------------------------------------------- #
# positions
# --------------------------------------------------------------------------- #


def equipment(builder, *, lands: int = 6, creatures: int = 1, monarch: int | None = None):
    """The Equipment and a creature to hang it on, plus lands to pay with.

    ``monarch`` is granted *before* the build. It has to be: `build()` runs the
    engine's auto-pass, which rolls a board with nothing to do straight past the
    main phase -- and whether there is anything to do is exactly what the crown
    decides here.
    """
    position = (
        builder(players=2)
        .battlefield(0, [CROWN, *([BEAR] * creatures), *([PLAINS] * lands)])
        .battlefield(1, [BEAR])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .turn(3)
        .step(Step.PRECOMBAT_MAIN)
    )
    if monarch is not None:
        become_monarch(position.state, monarch)
    game = position.build()
    return game, only_oid(game, CROWN)


def equip_cost(game, oid: int):
    """The equip ability's mana half, priced against the board as it stands."""
    cost = game.state.card(oid).abilities[1].cost
    return ability_mana(game.state, 0, cost, 0, oid).total


def equip_line(game, oid: int):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid
        ),
        None,
    )


def graveyard_spell(
    builder,
    card_id: str,
    *,
    lands: int = 9,
    creatures: int = 0,
    monarch: int | None = None,
):
    """``card_id`` in the graveyard, castable for its flashback cost."""
    position = (
        builder(players=2)
        .battlefield(0, [*([BEAR] * creatures), *([PLAINS] * lands)])
        .graveyard(0, [card_id])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .turn(3)
        .step(Step.PRECOMBAT_MAIN)
    )
    if monarch is not None:
        become_monarch(position.state, monarch)
    game = position.build()
    return game, game.state.players[0].graveyard[0]


def hand_spell(builder, card_id: str, *, lands: int = 5, creatures: int = 0):
    game = (
        builder(players=2)
        .battlefield(0, [*([BEAR] * creatures), *([PLAINS] * lands)])
        .hand(0, [card_id])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .turn(3)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    return game, game.state.players[0].hand[0]


def cast_line(game, oid: int):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.source == oid
        ),
        None,
    )


def lands_left(game, pid: int = 0) -> int:
    """Untapped lands — how much was actually charged, read off the board."""
    return sum(
        1
        for oid in game.state.battlefield
        if game.state.objects[oid].controller == pid
        and not game.state.objects[oid].tapped
        and game.state.card(oid).is_land
    )


# --------------------------------------------------------------------------- #
# the condition is what switches the reduction on
# --------------------------------------------------------------------------- #


class TestTheConditionGatesTheReduction:
    def test_the_printed_price_stands_with_no_monarch(self, builder):
        """721.2: a game nobody granted the crown in has *no* monarch."""
        game, oid = equipment(builder)
        assert game.state.monarch is None
        assert equip_cost(game, oid) == 4

    def test_the_crown_takes_three_off(self, builder):
        game, oid = equipment(builder)
        become_monarch(game.state, 0)
        assert equip_cost(game, oid) == 1

    def test_an_opponents_crown_takes_nothing_off(self, builder):
        """"…if **you're** the monarch." The condition names a player, and the
        reduction is not "if there is a monarch"."""
        game, oid = equipment(builder)
        become_monarch(game.state, 1)
        assert equip_cost(game, oid) == 4

    def test_it_wears_off_when_the_crown_moves(self, builder):
        """Read off the board every time, never stored -- the same property that
        makes Ghalta a two-drop and then a twelve-drop again."""
        game, oid = equipment(builder)
        become_monarch(game.state, 0)
        assert equip_cost(game, oid) == 1
        become_monarch(game.state, 1)
        assert equip_cost(game, oid) == 4


class TestTheClampAndTheColouredPips:
    def test_a_reduction_larger_than_the_cost_floors_at_zero(self, builder):
        """"Costs {3} less" off a {2} ability is free, not a refund."""
        model = CardModel.model_validate(
            {
                "id": "x_overshoot",
                "name": "Overshoot",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "{2}: Draw a card.",
                        "cost": {
                            "mana": "{2}",
                            "mana_reduction": {
                                "amount": 5,
                                "condition": {"is_monarch": "you"},
                            },
                        },
                        "effects": [
                            {"op": "draw", "player": "you", "amount": {"const": 1}}
                        ],
                    }
                ],
            }
        )
        card = compile_card(model)
        game = builder(players=2).battlefield(0, [PLAINS]).build()
        become_monarch(game.state, 0)
        assert ability_mana(game.state, 0, card.abilities[0].cost).total == 0

    def test_it_never_reaches_the_coloured_pips(self, builder):
        """118.7 / 601.2f: a reduction takes generic mana off and stops there."""
        model = CardModel.model_validate(
            {
                "id": "x_coloured",
                "name": "Coloured",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "{1}{W}{W}: Draw a card.",
                        "cost": {
                            "mana": "{1}{W}{W}",
                            "mana_reduction": {
                                "amount": 4,
                                "condition": {"is_monarch": "you"},
                            },
                        },
                        "effects": [
                            {"op": "draw", "player": "you", "amount": {"const": 1}}
                        ],
                    }
                ],
            }
        )
        card = compile_card(model)
        game = builder(players=2).battlefield(0, [PLAINS]).build()
        become_monarch(game.state, 0)
        req = ability_mana(game.state, 0, card.abilities[0].cost)
        assert req.generic == 0
        assert req.total == 2, "the two white pips survive any reduction"


class TestLegalityAndPaymentAgree:
    def test_the_ability_is_out_of_reach_at_the_printed_price(self, builder):
        game, oid = equipment(builder, lands=3)
        cost = game.state.card(oid).abilities[1].cost
        assert not can_pay(game.state, 0, cost, oid)
        assert equip_line(game, oid) is None

    def test_the_crown_brings_it_into_reach(self, builder):
        """Three lands cannot pay {4}; with the crown the price is {1}."""
        game, oid = equipment(builder, lands=3, monarch=0)
        cost = game.state.card(oid).abilities[1].cost
        assert can_pay(game.state, 0, cost, oid)
        assert equip_line(game, oid) is not None

    def test_the_charge_is_the_price_that_was_offered(self, builder):
        """One helper, two callers -- so activating cannot strand the payment."""
        game, oid = equipment(builder, lands=3, monarch=0)
        before = lands_left(game)

        game.apply(equip_line(game, oid))
        pass_until(game, lambda g: not g.state.stack)

        assert before - lands_left(game) == 1, "charged {1}, not the printed {4}"
        bear = only_oid(game, BEAR, pid=0)
        assert game.state.objects[oid].attached_to == bear
        assert chars(game.state, bear).power == 3, "and the Equipment did equip"


# --------------------------------------------------------------------------- #
# "…to cast this way": the reduction belongs to the variant, not the card
# --------------------------------------------------------------------------- #


class TestTheReductionIsScopedToTheCastVariant:
    def test_the_flashback_price_is_discounted(self, builder):
        """{8}{W} less one per creature: two Bears make it {6}{W}.

        Seven lands, deliberately -- one short of the printed {8}{W}, so the line
        being offered at all is the discount reaching `_cast_variant`.
        """
        game, oid = graveyard_spell(builder, SCALER, lands=7, creatures=2)
        assert variant_reduction(game.state, 0, game.state.card(oid).flashback, oid) == 2
        assert cast_line(game, oid) is not None

    def test_it_is_not_offered_when_the_discount_is_not_enough(self, builder):
        game, oid = graveyard_spell(builder, SCALER, lands=7, creatures=1)
        assert cast_line(game, oid) is None, "{8}{W} less one is still eight mana"

    def test_the_printed_hand_cast_is_not_discounted(self, builder):
        """The whole point. {4}{W} from hand stays {4}{W} however many creatures
        are out, because the rider is on the flashback cost node and the hand
        cast never reads that node."""
        game, oid = hand_spell(builder, SCALER, lands=4, creatures=4)
        assert cast_line(game, oid) is None, "four lands cannot pay {4}{W}"

        game, oid = hand_spell(builder, SCALER, lands=5, creatures=4)
        before = lands_left(game)
        game.apply(cast_line(game, oid))
        pass_until(game, lambda g: not g.state.stack)
        assert before - lands_left(game) == 5, "charged the printed {4}{W}"

    def test_the_flashback_cast_is_charged_the_discounted_price(self, builder):
        """`_cast_variant` offered it; `game._cast` must charge the same number.

        Exactly six lands: enough for the discounted {6}{W}-minus-three and not a
        pip more, so a `game._cast` that ignored the rider would strand the
        payment rather than quietly overcharge.
        """
        game, oid = graveyard_spell(builder, SCALER, lands=6, creatures=3)
        before = lands_left(game)

        game.apply(cast_line(game, oid))
        pass_until(game, lambda g: not g.state.stack)

        assert before - lands_left(game) == 6, "{8}{W} less three creatures"

    def test_a_card_level_reduction_would_have_hit_both(self, builder):
        """The failure this scoping exists to prevent, stated as an assertion:
        `cost_reduction` is variant-blind, so the same spec written there
        discounts the hand cast that the printed line never mentions."""
        game, oid = hand_spell(builder, SCALER, lands=5, creatures=4)
        from automtg.engine.costs import cost_reduction

        card = game.state.card(oid)
        assert cost_reduction(game.state, 0, card) == 0, "nothing card-level here"
        assert variant_reduction(game.state, 0, card.flashback, oid) == 4, (
            "…while the flashback node reads four, which is exactly the number "
            "that must not reach the hand cast"
        )


class TestTheTwoFacesCompose:
    def test_a_conditional_variant_reduction_is_off_without_the_crown(self, builder):
        game, oid = graveyard_spell(builder, CONDITIONAL, lands=6)
        assert variant_reduction(game.state, 0, game.state.card(oid).flashback, oid) == 0
        assert cast_line(game, oid) is None, "six lands cannot pay {6}{W}"

    def test_the_crown_switches_it_on(self, builder):
        game, oid = graveyard_spell(builder, CONDITIONAL, lands=6, monarch=0)
        assert variant_reduction(game.state, 0, game.state.card(oid).flashback, oid) == 4
        before = lands_left(game)

        game.apply(cast_line(game, oid))
        pass_until(game, lambda g: not g.state.stack)

        assert before - lands_left(game) == 3, "{6}{W} less {4}, floored by the pip"


# --------------------------------------------------------------------------- #
# what the loader refuses, and why each one would otherwise be silent
# --------------------------------------------------------------------------- #


def compile_spec(spec: dict):
    return compile_card(CardModel.model_validate(spec))


def ability_card(reduction: dict, *, mana: str = "{4}") -> dict:
    return {
        "id": "x_probe",
        "name": "Probe",
        "types": ["Artifact"],
        "abilities": [
            {
                "kind": "activated",
                "text": "Draw a card.",
                "cost": {"mana": mana, "mana_reduction": reduction},
                "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            }
        ],
    }


class TestTheLoaderRefusesTheSilentShapes:
    def test_a_flat_amount_needs_a_condition(self):
        """An ungated "{3} less" is a smaller printed cost written the long way,
        and it would load clean."""
        with pytest.raises(DslError, match="needs a 'condition'"):
            compile_spec(ability_card({"amount": 3}))

    def test_two_kinds_of_arithmetic_are_refused(self):
        """Whichever the code read first would win, and no printed line says
        both."""
        with pytest.raises(DslError, match="exactly one"):
            compile_spec(
                ability_card({"amount": 3, "count": {"types": ["Creature"]}})
            )

    def test_a_zero_amount_is_refused(self):
        with pytest.raises(DslError, match="positive integer"):
            compile_spec(
                ability_card({"amount": 0, "condition": {"is_monarch": "you"}})
            )

    def test_a_reduction_with_no_mana_to_reduce_is_refused(self):
        """Clamped at zero, so it would load and do nothing at all."""
        with pytest.raises(DslError, match="needs a 'mana' cost"):
            compile_spec(
                {
                    "id": "x_nomana",
                    "name": "No Mana",
                    "types": ["Artifact"],
                    "abilities": [
                        {
                            "kind": "activated",
                            "text": "{T}: Draw a card.",
                            "cost": {
                                "tap": True,
                                "mana_reduction": {
                                    "amount": 2,
                                    "condition": {"is_monarch": "you"},
                                },
                            },
                            "effects": [
                                {"op": "draw", "player": "you", "amount": {"const": 1}}
                            ],
                        }
                    ],
                }
            )

    @pytest.mark.parametrize(
        "cond",
        [
            {"kicked": True},
            {"evoked": True},
            {"overloaded": True},
            {"cast_from_graveyard": True},
            {"all": [{"is_monarch": "you"}, {"kicked": True}]},
            {"not": {"kicked": True}},
        ],
    )
    def test_conditions_that_cannot_be_answered_at_pricing_time(self, cond):
        """A reduction is priced before the spell is on the stack, so every
        cast-variant flag reads False -- a discount clause that can never fire,
        on a card that reads as though it has one."""
        with pytest.raises(DslError, match="cannot be answered"):
            compile_spec(ability_card({"amount": 2, "condition": cond}))

    def test_a_condition_that_can_be_answered_loads(self):
        card = compile_spec(
            ability_card({"amount": 2, "condition": {"is_your_turn": True}})
        )
        assert card.abilities[0].cost.mana_reduction["amount"] == 2

    def test_a_filter_may_only_count_the_zones_that_are_walked(self):
        """`costs._reduction_matches` walks the battlefield and the command zone,
        and nothing else, so any other zone would load and match nothing.

        (The command zone arrived with `greatest_mana_value` --
        `tests/unit/test_commander_mana_value.py` is where that half is pinned.
        The graveyard is still refused, which is what this test was always
        about.)
        """
        with pytest.raises(DslError, match="counts \\['battlefield', 'command'\\] only"):
            compile_spec(
                ability_card({"count": {"types": ["Creature"], "zone": "graveyard"}})
            )

    def test_an_unreadable_node_is_refused_rather_than_ignored(self):
        """An additional cost's mana is folded into the spell's price, so nothing
        prices that node on its own -- a reduction there would cost the player
        the full amount, silently."""
        with pytest.raises(DslError, match="not read here"):
            compile_spec(
                {
                    "id": "x_additional",
                    "name": "Additional",
                    "mana_cost": "{1}",
                    "types": ["Sorcery"],
                    "additional_cost": {
                        "mana": "{2}",
                        "mana_reduction": {
                            "amount": 1,
                            "condition": {"is_monarch": "you"},
                        },
                    },
                    "spell_effects": [
                        {"op": "draw", "player": "you", "amount": {"const": 1}}
                    ],
                }
            )
