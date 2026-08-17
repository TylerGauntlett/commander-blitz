""""Pay life equal to the number of colors in your commanders' color identity."

    War Room — "{3}, {T}, Pay life equal to the number of colors in your
    commanders' color identity: Draw a card."

Two leaves, and neither existed.

**The value.** Nothing in `VALUE_KEYS` read a colour identity. `distinct` is the
only leaf that counts distinct values, and `DISTINCT_OF` is a closed two-entry
tuple resolved over `resolve_pool` — i.e. over objects in a *zone*, so it could
not see a commander in the command zone at all. The union across a player's
commanders, so partners sharing a colour count it once, which is what "your
commanders' color identity" means in the singular.

Read off the **printed** identity rather than derived colours: colour identity is
a deck-construction fact fixed by the card, and it is the same number whether the
commander is in the command zone, on the battlefield or in a graveyard.

**The cost.** `pay_life` was an `int`, coerced once by `Cost.from_spec`, and both
`can_pay` and `pay` read that constant. It is the right cost — it is the *amount*
that could not be spelled. `times` is the only other non-fixed part of a cost and
its own comment says it multiplies the mana half.

`costs.life_cost` is the single place the amount is computed, and both `can_pay`
and `pay` go through it, because a cost checked at one price and charged at
another either strands the payment or hands out a discount. The same care
`mana_produced` and `mana_options_of` already take.
"""

from __future__ import annotations

from automtg.engine.costs import can_pay, life_cost
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value
from tests.conftest import oids_of

WAR_ROOM = "t_war_room"
MONO = "grizzly_bears"  # mono-green
EDGAR = "edgar_markov"  # Mardu -- three colours


def identity_count(game, pid: int = 0) -> int:
    ctx = EffectContext(state=game.state, controller=pid, source_oid=None)
    return evaluate_value(ctx, {"commander_color_identity": "you"})


class TestTheValue:
    def test_no_commander_is_zero(self, builder):
        game = builder(players=2).build()
        assert identity_count(game) == 0

    def test_a_mono_coloured_commander_is_one(self, builder):
        game = builder(players=2).commander(0, [MONO]).build()
        assert identity_count(game) == 1

    def test_a_three_colour_commander_is_three(self, builder):
        game = builder(players=2).commander(0, [EDGAR]).build()
        assert identity_count(game) == 3

    def test_it_reads_the_named_player(self, builder):
        """"**your** commanders" -- the opponent's Mardu commander is not yours."""
        game = builder(players=2).commander(1, [EDGAR]).build()
        assert identity_count(game, 0) == 0

    def test_it_is_a_union_not_a_sum(self, builder):
        """Two commanders sharing a colour count it once between them."""
        game = builder(players=2).commander(0, [MONO, MONO]).build()
        assert identity_count(game) == 1


class TestTheCostIsPricedAndCharged:
    def board(self, builder, commander: str | None, life: int = 40):
        b = builder(players=2).battlefield(0, [WAR_ROOM, *(["forest"] * 3)])
        if commander:
            b = b.commander(0, [commander])
        return b.life(0, life).library(0, ["forest"] * 20).build()

    def cost_of(self, game) -> int:
        oid = oids_of(game, WAR_ROOM)[0]
        return life_cost(game.state, 0, game.state.card(oid).abilities[1].cost, oid)

    def test_the_price_follows_the_commander(self, builder):
        game = self.board(builder, EDGAR)
        assert self.cost_of(game) == 3

    def test_a_mono_commander_is_cheaper(self, builder):
        game = self.board(builder, MONO)
        assert self.cost_of(game) == 1

    def test_it_is_payable_at_enough_life(self, builder):
        game = self.board(builder, EDGAR, life=40)
        oid = oids_of(game, WAR_ROOM)[0]
        assert can_pay(game.state, 0, game.state.card(oid).abilities[1].cost, oid)

    def test_it_is_not_payable_below_the_price(self, builder):
        """118.4 lets you pay down to exactly 0 -- 2 life cannot pay 3."""
        game = self.board(builder, EDGAR, life=2)
        oid = oids_of(game, WAR_ROOM)[0]
        assert not can_pay(game.state, 0, game.state.card(oid).abilities[1].cost, oid)

    def test_exactly_the_price_is_payable(self, builder):
        game = self.board(builder, EDGAR, life=3)
        oid = oids_of(game, WAR_ROOM)[0]
        assert can_pay(game.state, 0, game.state.card(oid).abilities[1].cost, oid)


class TestTheManaAbilityIsUnaffected:
    def test_a_life_cost_is_not_tap_only(self, builder):
        """`is_tap_only` gates what the payment solver may tap for you.

        A value-expression life cost is still a life cost, so the second ability
        must not become a free mana source.
        """
        game = builder(players=2).battlefield(0, [WAR_ROOM]).build()
        card = game.state.card(oids_of(game, WAR_ROOM)[0])
        assert card.abilities[0].cost.is_tap_only()
        assert not card.abilities[1].cost.is_tap_only()
