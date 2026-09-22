"""Chromatic Orrery: every coloured pip you pay is payable with any mana.

    You may spend mana as though it were mana of any color.

Rule 609.4b and the Mycosynth Lattice rulings give the shape of it. It is a
payment permission, not a cost change: the spell's mana value, its colours and
its printed cost do not move, only which mana may be handed over for a coloured
symbol. Colourless mana counts -- mana spent as though it were of a colour is
spent as that colour -- while ``{C}`` in a *cost* does not, because colourless
is not a colour and a Mountain still cannot pay a Wastes' activation.

The engine already knew how to read a cost that way: `ManaCost.as_any_color`
was written for Elder Brain's "you may spend mana as though it were mana of any
color **to cast it**" -- the *granted* form of the same sentence, whose own
tests are `tests/unit/test_spend_mana_as_any_color.py` beside this file. That
one rides on `permission.playable_any_color`, a flag on one card some
`grant_playable` had made castable. Chromatic Orrery grants no playability, so
there was no card for that flag to attach to, and nothing in the engine loosened
the colour of a pip a *player* pays. The nearest thing was
`black_mana_as_phyrexian`, K'rrik's static, which is the only other player-wide
rule about how a cost is paid.

**The half that is easy to lose is the activated abilities.** "Any cost you
pay" covers the Orrery's own ``{5}, {T}`` line, an equip, a morph and
"unless its controller pays {B}"; a version that loosened only spell costs is a
different and much weaker card, so both halves are pinned below, along with the
two things the waiver must *not* do: fold ``{C}`` away, and swallow the life
half of a printed Phyrexian pip.

Without it Chromatic Orrery is a five-mana artifact that taps for colourless,
and every five-colour deck that leans on it to cast off-colour spells does not
function.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.mana import ManaCost

ORRERY = "t_orrery_static"
BOLT = "t_azure_bolt"  # {1}{U}
PAIR = "t_azure_pair"  # {U}{U}
FONT = "t_chroma_font"  # {W}{W}: gain 1 life
X_FONT = "t_x_chroma_font"  # {X}{G}: gain X life
WASTE_FONT = "t_waste_font"  # {C}: gain 1 life
PHYREXIAN_FONT = "t_green_phyrexian_font"  # {G/P}: gain 1 life


def board(builder, *, hand=(), lands=(), permanents=(), orrery=True, orrery_seat=0):
    b = (
        builder(players=2)
        .hand(0, list(hand))
        .battlefield(0, list(lands) + list(permanents))
        .life(0, 20)
        .library(0, ["forest"] * 10)
    )
    if orrery:
        b = b.battlefield(orrery_seat, [ORRERY])
    return b.build()


def oid_in_hand(game, card_id):
    return next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id)


def oid_on_battlefield(game, card_id):
    return next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == card_id)


def casts(game, card_id):
    oid = oid_in_hand(game, card_id)
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def activations(game, card_id):
    oid = oid_on_battlefield(game, card_id)
    return [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid]


def tapped(game) -> int:
    return sum(1 for o in game.state.battlefield_objects(0) if o.tapped)


class TestTheCostItself:
    """What `as_any_color` reads a cost as, and what it leaves alone."""

    def test_each_coloured_pip_becomes_one_generic(self):
        cost = ManaCost.parse("{1}{U}{U}").as_any_color()
        assert cost.generic == 3
        assert cost.colors == set()

    def test_the_cost_is_not_changed(self):
        # 609.4b: mana value and colour are read off the printed cost. This is
        # a rule about which mana pays a symbol, never a new cost.
        printed = ManaCost.parse("{1}{U}{U}")
        cost = printed.as_any_color()
        assert cost.mana_value() == printed.mana_value() == 3
        assert cost.text == printed.text

    def test_colorless_is_not_a_colour_and_stays(self):
        # A Mountain still cannot pay a {C}. This is the one symbol the waiver
        # does not reach, and the whole difference from `as_any_type`.
        cost = ManaCost.parse("{C}{U}").as_any_color()
        assert cost.generic == 1
        assert cost.colored == ManaCost.parse("{C}").colored

    def test_a_hybrid_pip_becomes_a_single_generic(self):
        # Its coloured half is now payable with any one mana, so the pip is one.
        assert ManaCost.parse("{2/W}").as_any_color().generic == 1

    def test_a_requirement_with_nothing_coloured_is_returned_unchanged(self):
        # Identity is the cheap test `costs.spendable_requirement` uses to skip
        # the battlefield walk for the great majority of costs.
        req = ManaCost.parse("{3}").with_x(0)
        assert req.as_any_color() is req

    def test_the_discount_is_applied_before_the_waiver(self):
        # The reason the requirement gets its own `as_any_color`. "Costs {2}
        # less" is clamped at the generic part, so a {1}{G} ability discounted
        # by two still owes the one mana the {G} is. Loosening first would fold
        # the pip into the generic part where the discount could eat it, and
        # the ability would come out free.
        req = ManaCost.parse("{1}{G}").with_x(0)
        assert req.with_generic(req.generic - 2).as_any_color().generic == 1


class TestTheCastLine:
    """A spell's coloured pips are payable off any land the player controls."""

    def test_an_off_colour_spell_is_castable(self, builder):
        game = board(builder, hand=[BOLT], lands=["mountain"] * 2)
        assert casts(game, BOLT)

    def test_without_the_orrery_it_is_not(self, builder):
        game = board(builder, hand=[BOLT], lands=["mountain"] * 2, orrery=False)
        assert casts(game, BOLT) == []

    def test_an_opponents_orrery_does_nothing_for_you(self, builder):
        # "You may spend": the static reaches its controller only.
        game = board(builder, hand=[BOLT], lands=["mountain"] * 2, orrery_seat=1)
        assert casts(game, BOLT) == []

    def test_every_pip_is_loosened_not_just_one(self, builder):
        game = board(builder, hand=[PAIR], lands=["mountain"] * 2)
        assert casts(game, PAIR)

    def test_the_amount_owed_does_not_move(self, builder):
        # A waiver about colour is not a discount: {U}{U} off one land is still
        # one mana short.
        game = board(builder, hand=[PAIR], lands=["mountain"])
        assert casts(game, PAIR) == []

    def test_paying_taps_the_off_colour_lands(self, builder):
        game = board(builder, hand=[BOLT], lands=["mountain"] * 2)
        game.apply(casts(game, BOLT)[0])
        # The Orrery is the third permanent and is not a mana source.
        assert tapped(game) == 2


class TestActivatedAbilityCosts:
    """ "Any cost you pay" -- the half a spells-only version would lose."""

    def test_an_off_colour_activation_is_offered(self, builder):
        game = board(builder, permanents=[FONT], lands=["mountain"] * 2)
        assert activations(game, FONT)

    def test_without_the_orrery_it_is_not(self, builder):
        game = board(builder, permanents=[FONT], lands=["mountain"] * 2, orrery=False)
        assert activations(game, FONT) == []

    def test_an_opponents_orrery_does_nothing_for_you(self, builder):
        game = board(builder, permanents=[FONT], lands=["mountain"] * 2, orrery_seat=1)
        assert activations(game, FONT) == []

    def test_the_amount_owed_does_not_move(self, builder):
        game = board(builder, permanents=[FONT], lands=["mountain"])
        assert activations(game, FONT) == []

    def test_paying_it_taps_the_off_colour_lands(self, builder):
        game = board(builder, permanents=[FONT], lands=["mountain"] * 2)
        game.apply(activations(game, FONT)[0])
        assert tapped(game) == 2

    def test_colourless_mana_pays_a_coloured_pip(self, builder):
        # The Mycosynth Lattice ruling: mana spent as though it were of a colour
        # is spent as that colour, and colourless mana may be spent that way.
        # This is also what makes the Orrery's own {T} line -- five {C} -- worth
        # anything to a five-colour deck.
        game = board(builder, permanents=[FONT], lands=["wastes"] * 2)
        assert activations(game, FONT)

    def test_a_colorless_pip_in_the_cost_is_not_loosened(self, builder):
        # {C} is not a colour: an Orrery does not let a Mountain pay it.
        game = board(builder, permanents=[WASTE_FONT], lands=["mountain"])
        assert activations(game, WASTE_FONT) == []

    def test_and_is_still_payable_with_colourless_mana(self, builder):
        game = board(builder, permanents=[WASTE_FONT], lands=["wastes"])
        assert activations(game, WASTE_FONT)

    def test_the_x_ceiling_counts_the_loosened_pip(self, builder):
        # {X}{G} off three Mountains: the {G} is payable with one of them, so
        # X can be 2. Without the waiver legality's X gate and `can_pay` would
        # disagree -- payable, and then withheld.
        game = board(builder, permanents=[X_FONT], lands=["mountain"] * 3)
        game.apply(activations(game, X_FONT)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X
        assert decision.context["max_x"] == 2

    def test_the_x_ability_is_not_offered_without_the_orrery(self, builder):
        game = board(builder, permanents=[X_FONT], lands=["mountain"] * 3, orrery=False)
        assert activations(game, X_FONT) == []


class TestWhatTheWaiverMustNotSwallow:
    """The two things folding pips into generic could quietly take away."""

    def test_a_printed_phyrexian_pip_keeps_its_life_half(self, builder):
        # 107.4f is a way of paying one symbol and the Orrery is a rule about
        # which mana pays it; neither cancels the other. Read in the wrong
        # place -- inside `costs.payable_mana` -- the fold would have hidden the
        # pip from `phyrexian_count` and this activation would need mana.
        game = board(builder, permanents=[PHYREXIAN_FONT])
        assert activations(game, PHYREXIAN_FONT)
        game.apply(activations(game, PHYREXIAN_FONT)[0])
        assert game.state.players[0].life == 18

    def test_and_is_payable_with_any_mana_too(self, builder):
        game = board(builder, permanents=[PHYREXIAN_FONT], lands=["mountain"])
        assert activations(game, PHYREXIAN_FONT)
