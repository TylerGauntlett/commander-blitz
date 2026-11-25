"""`blitz_cost_reduction` -- a discount on the cost being paid, not on the spell.

    Blitz costs you pay cost {1} less for each time you've cast your commander
    from the command zone this game.

Witness: Henzie "Toolbox" Torre's second line. `spell_cost_reduction` cannot
say it: its filter reads what a spell *is*, and the same creature cast for its
mana cost is not discounted while cast for its blitz cost it is. So the static
is asked only on a line paying a blitz cost (`casting.pays_blitz`) -- a granted
one (`Action.blitzed`) or a printed one (the evoke slot under `evoke_label:
"blitz"`) -- and both `casting._cast_variant` and `Game._cast` net it from the
same flags, so the line offered is the line charged.

Generic only and clamped (601.2f), like `plot_cost_reduction`: a reduction
larger than the generic part leaves the coloured pips, never less. The amount
is the `commander_casts_this_game` tally, so it is zero until the commander has
been cast from the command zone.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.schema import AbilityModel, CardModel
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import settle

DISCOUNTER = "t_blitz_discounter"  # Henzie's second line
GRANTER = "t_blitz_granter"        # Henzie's first line
BRUTE = "t_blitz_brute"            # {3}{R} creature
GUARDIAN = "caldaia_guardian"      # {3}{G}, prints Blitz {2}{G}
COMMANDER = "t_commander_two"      # {1}{W}, only its tally matters


def board(builder, *, hand, casts=0, discounter=True, discounter_seat=0, lands=8):
    b = (
        builder(players=2)
        .hand(0, [*hand, "forest"])
        .battlefield(0, ["mountain"] * (lands // 2) + ["forest"] * (lands - lands // 2))
        .battlefield(0, [GRANTER])
        .commander(0, [COMMANDER])
        .hand(1, ["forest"])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
    )
    if discounter:
        b = b.battlefield(discounter_seat, [DISCOUNTER])
    game = b.build()
    if casts:
        player = game.state.players[0]
        player.commander_tax[player.commanders[0]] = casts
        game.state.bump_chars()
    return game


def casts_of(game, card_id):
    oid = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id)
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def tapped_after(game, action):
    game.apply(action)
    settle(game)
    return sum(
        1 for o in game.state.battlefield_objects(0) if o.tapped and game.state.card_of(o).is_land
    )


class TestItDiscountsTheGrantedBlitz:
    def test_two_casts_take_two_off(self, builder):
        game = board(builder, hand=[BRUTE], casts=2)
        assert tapped_after(game, next(a for a in casts_of(game, BRUTE) if a.blitzed)) == 2

    def test_no_casts_yet_is_no_discount(self, builder):
        game = board(builder, hand=[BRUTE])
        assert tapped_after(game, next(a for a in casts_of(game, BRUTE) if a.blitzed)) == 4

    def test_the_discount_never_reaches_a_coloured_pip(self, builder):
        # {3}{R} less five is {R}, never nothing.
        game = board(builder, hand=[BRUTE], casts=5)
        assert tapped_after(game, next(a for a in casts_of(game, BRUTE) if a.blitzed)) == 1


class TestItDiscountsAPrintedBlitz:
    def test_the_printed_blitz_cost_is_discounted(self, builder):
        # Blitz {2}{G} less one is {1}{G}.
        game = board(builder, hand=[GUARDIAN], casts=1)
        assert tapped_after(game, next(a for a in casts_of(game, GUARDIAN) if a.evoked)) == 2


class TestItDiscountsNothingElse:
    def test_the_printed_cast_of_the_same_creature_pays_full_price(self, builder):
        # The measurement `spell_cost_reduction` could not make: same spell,
        # different cost being paid.
        game = board(builder, hand=[BRUTE], casts=2)
        line = next(a for a in casts_of(game, BRUTE) if not a.blitzed)
        assert tapped_after(game, line) == 4

    def test_without_the_static_there_is_no_discount(self, builder):
        game = board(builder, hand=[BRUTE], casts=2, discounter=False)
        assert tapped_after(game, next(a for a in casts_of(game, BRUTE) if a.blitzed)) == 4

    def test_an_opponents_static_discounts_nothing(self, builder):
        game = board(builder, hand=[BRUTE], casts=2, discounter_seat=1)
        assert tapped_after(game, next(a for a in casts_of(game, BRUTE) if a.blitzed)) == 4


class TestTheLoaderRefusesTheSilentFailures:
    def _card(self, **static):
        base = dict(
            kind="static",
            text="x",
            effect="blitz_cost_reduction",
            affects_player="you",
            amount={"commander_casts_this_game": "you"},
        )
        base.update(static)
        return CardModel(
            id="t_bad", name="Bad", mana_cost="{3}", types=["Creature"],
            power=1, toughness=1, abilities=[AbilityModel(**base)],
        )

    def test_the_well_formed_static_loads(self):
        from commanderblitz.cards.loader import compile_card

        compile_card(self._card())

    def test_no_amount_is_refused(self):
        from commanderblitz.cards.loader import compile_card

        with pytest.raises(DslError, match="amount"):
            compile_card(self._card(amount=None))

    def test_a_zero_amount_is_refused(self):
        from commanderblitz.cards.loader import compile_card

        with pytest.raises(DslError, match="1 or more"):
            compile_card(self._card(amount={"const": 0}))

    def test_a_spell_filter_is_refused(self):
        from commanderblitz.cards.loader import compile_card

        # The cost being paid is the filter; a spell filter would read as one.
        with pytest.raises(DslError, match="affects_spells"):
            compile_card(self._card(affects_spells={"types": ["Creature"]}))

    def test_a_permanent_filter_is_refused(self):
        from commanderblitz.cards.loader import compile_card

        with pytest.raises(DslError, match="the cost being paid is the filter"):
            compile_card(self._card(affects={"types": ["Creature"]}))
