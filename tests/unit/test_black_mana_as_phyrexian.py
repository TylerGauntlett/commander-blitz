"""K'rrik, Son of Yawgmoth: every {B} in a cost is a {B/P}.

    For each {B} in a cost, you may pay 2 life rather than pay that mana.

The rulings make this exactly a Phyrexian pip (107.4f) laid over every black
symbol the player pays, and they say where the edges are: "any cost you pay,
including the mana costs of spells, activation costs, and even costs for special
actions"; hybrid symbols that *may* be paid with {B} -- ``{B/R}``, ``{2/B}`` --
count once you choose to pay them with black; generic mana never does; and the
cost itself is not changed, only how it may be paid.

So the engine reuses the Phyrexian machinery rather than growing a second one:
`ManaCost.black_as_phyrexian` turns each black pip into one with a life half,
the cast line counts the pips it buys as lines exactly as it does for Gitaxian
Probe, and every other cost -- an activation, a special action -- asks the
payer how many to buy through `costs.pay`, bounded by what `costs.can_pay`
found payable.

Without it K'rrik is a lifelinking vanilla creature that grows, and the deck he
leads (every black spell cast off a life total) does not function. The
narrowing it removes along the way is the one `docs/rules-coverage.md` recorded:
a Phyrexian pip in an *activated ability's* cost was payable with mana only,
because the choice existed only as a cast line.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.mana import ManaCost

KRRIK = "t_krrik"
BARGAIN = "t_night_bargain"  # {1}{B}{B}
HYBRID = "t_black_hybrid"  # {B/R}
FONT = "t_blood_font"  # {B}{B}: gain 1 life
X_FONT = "t_x_font"  # {X}{B}: gain X life
PHYREXIAN_FONT = "t_phyrexian_font"  # {G/P}: gain 1 life
BEAR = "t_bear"  # {1}{G}


def board(builder, *, hand=(), lands=(), permanents=(), krrik=True, life=20, krrik_seat=0):
    b = (
        builder(players=2)
        .hand(0, list(hand))
        .battlefield(0, list(lands) + list(permanents))
        .life(0, life)
        .library(0, ["forest"] * 10)
    )
    if krrik:
        b = b.battlefield(krrik_seat, [KRRIK])
    return b.build()


def oid_in_hand(game, card_id):
    return next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id)


def oid_on_battlefield(game, card_id):
    return next(
        o.oid for o in game.state.battlefield_objects(0) if o.def_id == card_id
    )


def life_lines(game, card_id) -> list[int]:
    oid = oid_in_hand(game, card_id)
    return sorted(
        {
            a.phyrexian
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.source == oid
        }
    )


def activations(game, card_id):
    oid = oid_on_battlefield(game, card_id)
    return [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid]


def tapped(game) -> int:
    return sum(1 for o in game.state.battlefield_objects(0) if o.tapped)


class TestTheCostItself:
    """What `black_as_phyrexian` reads a cost as, and what it leaves alone."""

    def test_a_plain_black_pip_gains_a_life_half(self):
        cost = ManaCost.parse("{1}{B}{B}").black_as_phyrexian()
        assert cost.phyrexian_count == 2
        assert cost.generic == 1

    def test_the_cost_is_not_changed(self):
        # "doesn't modify or reduce costs you pay" -- mana value, colour and
        # the printed text all read the same.
        printed = ManaCost.parse("{1}{B}{B}")
        cost = printed.black_as_phyrexian()
        assert cost.mana_value() == printed.mana_value() == 3
        assert cost.colors == printed.colors
        assert cost.symbols_of("B") == 2
        assert cost.text == printed.text

    def test_hybrid_symbols_that_may_be_paid_with_black_count(self):
        assert ManaCost.parse("{B/R}").black_as_phyrexian().phyrexian_count == 1
        assert ManaCost.parse("{2/B}").black_as_phyrexian().phyrexian_count == 1

    def test_a_phyrexian_black_pip_is_already_one(self):
        cost = ManaCost.parse("{B/P}")
        assert cost.black_as_phyrexian() is cost

    def test_generic_and_other_colours_are_untouched(self):
        # "You can't pay 2 life to pay for generic mana."
        for text in ("{3}", "{1}{G}", "{W/U}", "{R/P}"):
            cost = ManaCost.parse(text)
            assert cost.black_as_phyrexian() is cost

    def test_the_plain_pip_is_bought_before_the_hybrid_one(self):
        # Anything that pays a {B} also pays a {B/R}; the reverse is not true.
        remaining, owed = ManaCost.parse("{B/R}{B}").black_as_phyrexian().paying_phyrexian(1)
        assert owed == 2
        assert len(remaining.hybrid) == 1
        assert len(remaining.hybrid[0].symbols) == 2


class TestTheCastLine:
    """A spell's black pips are offered as life lines, as Phyrexian ones are."""

    def test_every_count_is_offered_with_black_mana_and_the_life(self, builder):
        game = board(builder, hand=[BARGAIN], lands=["swamp"] * 3)
        assert life_lines(game, BARGAIN) == [0, 1, 2]

    def test_with_no_black_source_both_pips_go_the_life_way(self, builder):
        game = board(builder, hand=[BARGAIN], lands=["mountain"])
        assert life_lines(game, BARGAIN) == [2]

    def test_without_krrik_it_is_not_castable_off_mountains(self, builder):
        game = board(builder, hand=[BARGAIN], lands=["mountain"] * 3, krrik=False)
        assert life_lines(game, BARGAIN) == []

    def test_an_opponents_krrik_does_nothing_for_you(self, builder):
        # "you may pay": the static reaches its controller only.
        game = board(builder, hand=[BARGAIN], lands=["mountain"] * 3, krrik_seat=1)
        assert life_lines(game, BARGAIN) == []

    def test_a_hybrid_black_pip_is_payable_with_life(self, builder):
        game = board(builder, hand=[HYBRID])
        assert life_lines(game, HYBRID) == [1]

    def test_a_spell_with_no_black_in_it_offers_no_life_line(self, builder):
        game = board(builder, hand=[BEAR], lands=["forest"] * 2)
        assert life_lines(game, BEAR) == [0]

    def test_the_generic_part_is_still_owed(self, builder):
        # {1}{B}{B} with both pips bought is still {1}, and nothing pays it.
        game = board(builder, hand=[BARGAIN])
        assert life_lines(game, BARGAIN) == []


class TestTheLifeBoundary:
    """118.4: down to exactly 0 and no further, two life a pip."""

    def test_four_life_buys_both_pips(self, builder):
        game = board(builder, hand=[BARGAIN], lands=["mountain"], life=4)
        assert life_lines(game, BARGAIN) == [2]

    def test_three_life_buys_one(self, builder):
        game = board(builder, hand=[BARGAIN], lands=["mountain"], life=3)
        assert life_lines(game, BARGAIN) == []
        game = board(builder, hand=[BARGAIN], lands=["swamp", "mountain"], life=3)
        assert life_lines(game, BARGAIN) == [1]


class TestPayingTheCast:
    def cast(self, game, card_id, bought):
        oid = oid_in_hand(game, card_id)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and a.source == oid and a.phyrexian == bought
            )
        )

    def test_the_life_line_charges_life_and_only_the_generic_mana(self, builder):
        game = board(builder, hand=[BARGAIN], lands=["mountain"])
        self.cast(game, BARGAIN, 2)
        assert game.state.players[0].life == 16
        assert tapped(game) == 1

    def test_the_mana_line_charges_no_life(self, builder):
        game = board(builder, hand=[BARGAIN], lands=["swamp"] * 3)
        self.cast(game, BARGAIN, 0)
        assert game.state.players[0].life == 20
        assert tapped(game) == 3


class TestActivationCosts:
    """"…including activation costs": asked while paying, since there is no line."""

    def test_offered_with_no_mana_at_all(self, builder):
        game = board(builder, permanents=[FONT])
        assert activations(game, FONT)

    def test_not_offered_without_krrik(self, builder):
        game = board(builder, permanents=[FONT], krrik=False)
        assert activations(game, FONT) == []

    def test_not_offered_without_the_life(self, builder):
        game = board(builder, permanents=[FONT], life=3)
        assert activations(game, FONT) == []

    def test_a_forced_answer_is_not_asked(self, builder):
        # No black mana: both pips must be bought, so there is nothing to choose.
        game = board(builder, permanents=[FONT])
        game.apply(activations(game, FONT)[0])
        pending = game.pending()
        assert pending is None or pending.kind is not DecisionKind.CHOOSE_MODE
        assert game.state.players[0].life == 16

    def test_a_real_choice_is_asked_and_honoured(self, builder):
        game = board(builder, permanents=[FONT], lands=["swamp"])
        game.apply(activations(game, FONT)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_MODE
        labels = [o.label for o in decision.options]
        # One swamp: at least one pip has to be bought, at most both.
        assert labels == ["Pay 2 life for 1 mana symbol", "Pay 4 life for 2 mana symbols"]
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 0)
        )
        assert game.state.players[0].life == 18
        assert tapped(game) == 1

    def test_paying_all_mana_is_one_of_the_choices(self, builder):
        game = board(builder, permanents=[FONT], lands=["swamp"] * 2)
        game.apply(activations(game, FONT)[0])
        decision = game.pending()
        assert decision.options[0].label == "Pay with mana"
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 0)
        )
        assert game.state.players[0].life == 20
        assert tapped(game) == 2

    def test_the_x_ceiling_counts_the_pip_bought_with_life(self, builder):
        # {X}{B} off three Mountains: the {B} goes for 2 life, so X can be 3.
        game = board(builder, permanents=[X_FONT], lands=["mountain"] * 3)
        game.apply(activations(game, X_FONT)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X
        assert decision.context["max_x"] == 3


class TestPrintedPhyrexianActivations:
    """The recorded narrowing, gone: a {G/P} activation is payable with life."""

    def test_offered_off_no_mana(self, builder):
        game = board(builder, permanents=[PHYREXIAN_FONT], krrik=False)
        assert activations(game, PHYREXIAN_FONT)

    def test_charged_in_life(self, builder):
        game = board(builder, permanents=[PHYREXIAN_FONT], krrik=False)
        game.apply(activations(game, PHYREXIAN_FONT)[0])
        assert game.state.players[0].life == 18

    def test_not_at_one_life(self, builder):
        game = board(builder, permanents=[PHYREXIAN_FONT], krrik=False, life=1)
        assert activations(game, PHYREXIAN_FONT) == []
