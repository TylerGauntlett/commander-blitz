"""Tiered: "Choose one additional cost", where the tier buys a different effect.

Fire Magic and Ice Magic (Final Fantasy). Three prices on one card, exactly one
paid as it is cast, and — unlike every other choose-a-price card — **which one
was paid decides what the spell does**. Ice Magic's tiers bounce, or put on top
or bottom, or shuffle away: three genuinely different effects, not one effect
with a scaling number.

The cost machinery was already here. `additional_cost_options` has shipped since
Bitter Triumph's "discard a card **or** pay 3 life", and it does the hard part —
one price chosen at cast time, paid as part of casting, offered as a separate
cast line per option. It was missing from the packet's curated
`CARD_LEVEL_COST_KEYS`, which is why two workers read their reference correctly
and reported a mechanic that already worked as absent.

What genuinely did not exist is reading the choice **back**. Bitter Triumph
never needed it: both of its prices lead to the same "destroy target creature",
so the card resolves identically either way. A tiered card cannot resolve at all
without knowing which tier was bought, so the index is now carried on the stack
item, stamped onto the object before `spell_effects` run — the same moment and
for the same reason as `overloaded` and `kicked` — and read by
`{"cost_option": n}`.

The stamping moment is the trap: a flag written *after* `spell_effects` would
read `None` and every tier would resolve as none of them, which is a card that
costs mana and does nothing.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import only_oid, pass_until

BURN = "t_tiered_burn"  # {R}; +{0}/+{2}/+{5} for 1/2/3 damage to each creature
BEAR = "t_bear"  # 2/2
BIG = "t_big_wall"  # 0/9 -- survives every tier, so damage is readable as marks


def position(builder, lands: int):
    """``lands`` untapped Mountains: {R} plus whatever tier they can afford."""
    game = (
        builder(players=2)
        .battlefield(0, ["mountain"] * lands)
        .battlefield(1, [BIG, "plains"])
        .library(0, ["forest"] * 10)
        .hand(0, [BURN])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def casts(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BURN
    ]


def cast_tier(game, tier: int) -> int:
    """Cast at ``tier`` and report the damage marked on the opposing wall."""
    wall = only_oid(game, BIG, 1)
    action = next(a for a in casts(game) if a.additional_choice == tier)
    game.apply(action)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return game.state.objects[wall].damage


class TestEachTierIsItsOwnCastLine:
    def test_one_mana_offers_only_the_cheapest(self, builder):
        """{R} plus {0}. The {2} and {5} tiers are unaffordable."""
        game = position(builder, lands=1)
        assert {a.additional_choice for a in casts(game)} == {0}

    def test_three_mana_offers_two_tiers(self, builder):
        game = position(builder, lands=3)
        assert {a.additional_choice for a in casts(game)} == {0, 1}

    def test_six_mana_offers_all_three(self, builder):
        game = position(builder, lands=6)
        assert {a.additional_choice for a in casts(game)} == {0, 1, 2}


class TestTheTierDecidesTheEffect:
    def test_the_cheapest_tier_deals_one(self, builder):
        assert cast_tier(position(builder, lands=6), 0) == 1

    def test_the_middle_tier_deals_two(self, builder):
        assert cast_tier(position(builder, lands=6), 1) == 2

    def test_the_priciest_tier_deals_three(self, builder):
        assert cast_tier(position(builder, lands=6), 2) == 3


class TestTheChoiceSurvivesToResolution:
    def test_a_tier_deals_something(self, builder):
        """The failure this exists to prevent is a card that resolves as no tier.

        If the index were stamped after `spell_effects` ran, every branch would
        read None, nothing would fire, and the spell would cost mana and do
        nothing at all.
        """
        assert cast_tier(position(builder, lands=6), 1) > 0


class TestItAffectsEveryCreature:
    def test_the_casters_own_creatures_are_hit_too(self, builder):
        """"each creature" -- the tier changes the number, not the targets."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR] + ["mountain"] * 6)
            .battlefield(1, [BIG, "plains"])
            .library(0, ["forest"] * 10)
            .hand(0, [BURN])
            .hand(1, ["t_plain_instant"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        bear = only_oid(game, BEAR)

        action = next(a for a in casts(game) if a.additional_choice == 0)
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.objects[bear].damage == 1
