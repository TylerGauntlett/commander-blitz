"""The Ur-Dragon deck's mana engine, card by card, doing what it prints.

Every card here cleared the six authoring gates, and every card here is an
**ability** -- which is precisely what gate 5 cannot reach. The behaviour gate
casts a card once into a fixed sandbox and reads the board; it never activates
anything and never attacks with anything. So for all seven of these the
authored expectation says only "it resolved", and a land that taps for nothing
would have passed it.

The other reason this file exists is that a mana ability is the one place in the
engine where the **wrong** encoding is a *better* card. "Add X mana of any one
color" written as a combination, "for each color among permanents" written as a
choice of one, "spend this mana only to cast spells" written without the clause,
"any type" written as "any color" -- each of those loads clean, plays, and hands
the deck a card nobody printed. So each class below asserts the near miss beside
the printed line.

Where the engine already has a capability test under `tests/unit/` (there is one
for every mechanic here), this file is the *card*: the shipped id off
`data/cards/auto/`, on a board made of the other 99 cards in the deck, doing the
thing the deck plays it for. A capability that works on a test card and a card
that wires it up wrong is exactly the gap gate 5 leaves open.

Two things below are deliberately not asserted, and are called out where they
sit: Bloom Tender can never see a colourless-only board (she is green and always
sees herself), and Kinnan's doubling of a *two*-mana rock is a known divergence
from the printed "add one mana", pinned as such in `TestKinnanBonderProdigy`.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.costs import (
    activate_mana_ability,
    available_mana,
    mana_amount,
    mana_options_of,
    mana_sources,
    spell_purpose,
)
from automtg.engine.enums import ActionKind, DecisionKind, Keyword, Step, Zone
from automtg.engine.mana import SYMBOLS
from automtg.engine.primitives import add_counters
from automtg.engine.structs import TargetRef
from tests.conftest import action_for_card, find_action, only_oid, pass_until

# A castable instant in a seat's hand, and it is load bearing rather than
# scenery. A precombat main phase in which the active player can do nothing
# auto-advances into combat, and a test that read "no legal cast" there would
# pass for the wrong reason. `t_plain_instant` is {W}, so a Plains beside it is
# the only unrestricted mana on those boards -- which is a mana short of every
# spell those tests ask about.
ANCHOR = "t_plain_instant"
PLAINS = "plains"

# A vanilla 2/2. On the Klauth board it is the second attacker whose *power* is
# not 1, which is the only way to tell "total power" from "number of attackers";
# on the Arena board it is the reason there is a declare-attackers step at all.
BEAR = "t_bear"

# Deck cards used as the spells the mana does or does not buy.
THREE_DROP = "temur_battlecrier"  # {G}{U}{R} -- a creature, and one under Helga's bar
FOUR_DROP = "smaug_the_magnificent"  # {2}{R}{R} -- a creature at exactly the bar
BIG_NONCREATURE = "the_one_ring"  # {4} -- over the bar, and never a creature
HASTELESS = "terror_of_the_peaks"  # {3}{R}{R}, flying and *no* printed haste

# The one stand-in from outside the deck: Helga's second clause is "creature
# spells with {X} in their mana costs" and the list has no {X} creature in it.
# Goldvein Hydra is {X}{G}, shipped in `data/cards/auto/`, and is here because
# the clause is otherwise untestable against this deck's own 99 cards.
X_CREATURE = "goldvein_hydra"

#: The order Klauth's `split` names its colours in, which is the order the
#: trigger's prompt offers them.
SPLIT = ["W", "U", "B", "R", "G"]


def symbols_of(option) -> list[str]:
    """One mana option as the symbols it actually makes, e.g. ``["G", "G", "U"]``."""
    return sorted(SYMBOLS[i] for i, count in enumerate(option) for _ in range(count))


def mana_ability_of(game, oid: int, index: int = 0):
    """The ``index``-th mana ability of the card on the battlefield at ``oid``."""
    return [a for a in game.state.card(oid).abilities if a.is_mana_ability][index]


def offered_symbols(game, oid: int, index: int = 0) -> set[str]:
    """Every symbol this permanent's mana ability offers on this board, right now."""
    ability = mana_ability_of(game, oid, index)
    return {
        SYMBOLS[i]
        for option in mana_options_of(game.state, oid, ability)
        for i, count in enumerate(option)
        if count
    }


def castable(game) -> set[str]:
    """The def_ids this seat may cast right now."""
    return {
        game.state.objects[a.source].def_id
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and a.source is not None
    }


def activations_of(game, oid: int) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid]


def pool(game, pid: int = 0) -> dict[str, int]:
    return game.state.players[pid].mana_pool.to_dict()


class TestHelgaSkittishSeer:
    """"{T}: Add X mana of any one color, where X is Helga's power.

    Spend this mana only to cast creature spells with mana value 4 or greater or
    creature spells with {X} in their mana costs."

    A printed **1/3**, so the size is a question about the board and not a
    constant, and her own first ability is what moves it. Both halves of the
    line are invisible to gate 5: it never taps her, and nothing in its sandbox
    casts the four-drop that would grow her.
    """

    def seer(self, builder, power: int = 1, *, board=(), hand=()):
        game = (
            builder(players=2)
            .battlefield(0, ["helga_skittish_seer", *board])
            .hand(0, list(hand))
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        oid = only_oid(game, "helga_skittish_seer", 0)
        if power > 1:
            add_counters(game.state, oid, "+1/+1", power - 1)
        game.state.bump_chars()
        game._advance()
        return game, oid

    # -- X is her power ---------------------------------------------------

    def test_a_printed_one_three_taps_for_one(self, builder):
        game, helga = self.seer(builder)
        assert chars(game.state, helga).power == 1
        assert mana_amount(game.state, helga, mana_ability_of(game, helga)) == 1

    def test_counters_raise_it(self, builder):
        """Read off the board, not off the printed face -- which is the whole
        card: written as five fixed `add_mana` modes she taps for one for ever."""
        game, helga = self.seer(builder, 4)
        assert mana_amount(game.state, helga, mana_ability_of(game, helga)) == 4

    def test_her_own_trigger_is_what_grows_her(self, builder):
        """"Whenever you cast a creature spell with mana value 4 or greater, you
        draw a card, gain 1 life, and put a +1/+1 counter on Helga."

        The loop the deck plays her for, and the half gate 5 could never reach:
        its sandbox casts the card under test and nothing after it.
        """
        game, helga = self.seer(builder, board=["mountain"] * 4, hand=[FOUR_DROP])
        library = len(game.state.players[0].library)
        life = game.state.players[0].life

        game.apply(action_for_card(game, ActionKind.CAST, FOUR_DROP))
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.objects[helga].counters.get("+1/+1") == 1
        assert len(game.state.players[0].library) == library - 1, "you draw a card"
        assert game.state.players[0].life == life + 1, "gain 1 life"
        assert mana_amount(game.state, helga, mana_ability_of(game, helga)) == 2, "and X is now 2"

    # -- one colour, not a combination ------------------------------------

    def test_every_option_is_a_single_colour(self, builder):
        """"Any **one** color". `split` is the near miss and is the other
        direction: at X=3 it makes {W}{U}{G}, which the printed card cannot."""
        game, _helga = self.seer(builder, 3)
        for source in mana_sources(game.state, 0, purpose=spell_purpose(
            game.state.registry.get(FOUR_DROP)
        )):
            for option in source.options:
                assert len(set(symbols_of(option))) == 1, f"{option} is a combination"

    def test_the_whole_size_lands_in_that_one_colour(self, builder):
        game, _helga = self.seer(builder, 3)
        offered = {
            tuple(option)
            for source in mana_sources(
                game.state, 0, purpose=spell_purpose(game.state.registry.get(FOUR_DROP))
            )
            for option in source.options
        }
        assert offered == {
            (3, 0, 0, 0, 0, 0),
            (0, 3, 0, 0, 0, 0),
            (0, 0, 3, 0, 0, 0),
            (0, 0, 0, 3, 0, 0),
            (0, 0, 0, 0, 3, 0),
        }, "five colours, three mana each -- never a mixture"

    # -- what the mana may pay for ----------------------------------------

    def funds(self, builder, card_id: str) -> bool:
        game, _helga = self.seer(builder, 4)
        purpose = spell_purpose(game.state.registry.get(card_id))
        return bool(mana_sources(game.state, 0, purpose=purpose))

    def test_a_four_mana_creature_spell_is_funded(self, builder):
        assert self.funds(builder, FOUR_DROP)

    def test_a_three_mana_creature_spell_is_not(self, builder):
        """The bar is 4, and Temur Battlecrier at 3 is where a dropped predicate
        shows. Written as the bare `["creature"]` the language used to have --
        Ancient Ziggurat's spelling -- this passes and the card is better."""
        assert not self.funds(builder, THREE_DROP)

    def test_an_x_creature_spell_is_funded(self, builder):
        """{X}{G} is mana value 1 (202.3b), so only the second clause reaches
        it: a restriction written on mana value alone refuses this."""
        assert self.funds(builder, X_CREATURE)

    def test_a_four_mana_noncreature_spell_is_not(self, builder):
        """The One Ring is over the bar and is never a creature spell."""
        assert not self.funds(builder, BIG_NONCREATURE)

    # -- and played out ---------------------------------------------------

    def played(self, builder, card_id: str) -> set[str]:
        """Helga at power 5 beside one Plains, with ``card_id`` in hand.

        The Plains is the anchor and the only unrestricted mana on the board,
        so anything castable here is castable because Helga's five were allowed
        to pay for it.
        """
        game, _helga = self.seer(builder, 5, board=[PLAINS], hand=[card_id, ANCHOR])
        return castable(game)

    def test_the_four_drop_really_casts_off_her_mana(self, builder):
        """Offered *and* payable: five red pays {2}{R}{R} and one Plains does not."""
        assert FOUR_DROP in self.played(builder, FOUR_DROP)

    def test_the_one_ring_does_not(self, builder):
        """The contrast with the colour taken out of it: {4} is all generic, so
        five mana of any one colour covers the *price* and the clause is the
        only thing left refusing."""
        assert BIG_NONCREATURE not in self.played(builder, BIG_NONCREATURE)


class TestBloomTender:
    """"Vivid -- {T}: For each color among permanents you control, add one mana
    of that color."

    Not a choice. Every other board-reading mana ability in the engine offers a
    *list* of options and lets the payment pick one; this one has a single
    option that is a variable bundle. Offered as a list -- Mox Amber's "one mana
    of any color among permanents you control" -- a three-colour board would tap
    her for one mana three different ways instead of for three mana.
    """

    def tender(self, builder, extras=()):
        game = (
            builder(players=2)
            .battlefield(0, ["bloom_tender", *extras])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .build(advance=False)
        )
        return game, only_oid(game, "bloom_tender", 0)

    def options(self, game, oid: int):
        return mana_options_of(game.state, oid, mana_ability_of(game, oid))

    def test_three_colours_are_one_option_and_not_three(self, builder):
        """Terror of the Peaks is red, Smothering Tithe is white, and the Tender
        herself is green."""
        game, tender = self.tender(builder, ["terror_of_the_peaks", "smothering_tithe"])
        assert len(self.options(game, tender)) == 1, "nothing is asked (605.1a)"

    def test_that_option_is_one_mana_of_each_colour_at_once(self, builder):
        game, tender = self.tender(builder, ["terror_of_the_peaks", "smothering_tithe"])
        assert symbols_of(self.options(game, tender)[0]) == ["G", "R", "W"]

    def test_it_is_three_mana_and_not_one(self, builder):
        game, tender = self.tender(builder, ["terror_of_the_peaks", "smothering_tithe"])
        assert sum(self.options(game, tender)[0]) == 3

    def test_one_gold_permanent_contributes_all_of_its_colours(self, builder):
        """"For each **color** among permanents", not for each permanent: Helga
        is {G}{W}{U} and is three colours off one card -- two of them new."""
        game, tender = self.tender(builder, ["helga_skittish_seer"])
        assert symbols_of(self.options(game, tender)[0]) == ["G", "U", "W"]

    def test_a_mono_green_board_taps_for_exactly_one_green(self, builder):
        """Two Forests beside her and it is still `{G}`: a *land* is a
        colourless permanent, so the count is of colours and not of sources."""
        game, tender = self.tender(builder, ["forest", "forest"])
        assert symbols_of(self.options(game, tender)[0]) == ["G"]

    def test_colourless_permanents_contribute_nothing(self, builder):
        """Colourless is not a colour (105.1), and this is as close to the
        empty case as the printed card reaches.

        "A colourless-only board adds nothing" is **not assertable for Bloom
        Tender**: she is a green creature and is always a green permanent she
        controls, so the board can never be colourless while she is on it to tap.
        The reachable half of the claim is this one -- a Sol Ring and a Wastes
        beside her add no sixth symbol and no sixth mana. The unreachable half
        is pinned on a colourless body in `tests/unit/test_mana_of_each_color.py`.
        """
        game, tender = self.tender(builder, ["sol_ring", "wastes"])
        assert symbols_of(self.options(game, tender)[0]) == ["G"]
        assert sum(self.options(game, tender)[0]) == 1


class TestChromaticOrrery:
    """"You may spend mana as though it were mana of any color."

    A payment permission, not a cost change (609.4b): nothing about what is owed
    moves, only which mana may be handed over. The half that is easy to lose is
    the **activated abilities** -- "any cost you pay" is not "any spell you
    cast", and a waiver that reached only spells is a different and much weaker
    card. Kinnan's `{5}{G}{U}` is the deck's own witness for it.

    Gate 5 can see none of this: a static that changes the price of a *later*
    payment, in a sandbox that casts one card and stops.
    """

    def board(self, builder, *, orrery: bool, hand=()):
        """Eight Wastes and a Plains: nine mana, not one pip of it green or blue.

        The Plains and the `{W}` instant are the anchor. Without them the seat
        in the no-Orrery control has nothing it can do and the phase advances
        before anything can be read off it.
        """
        return (
            builder(players=2)
            .battlefield(
                0,
                (["chromatic_orrery"] if orrery else [])
                + ["kinnan_bonder_prodigy", PLAINS]
                + ["wastes"] * 8,
            )
            .hand(0, [ANCHOR, *hand])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_it_loosens_an_activated_abilitys_cost(self, builder):
        """The claim. Kinnan's `{5}{G}{U}` off a board with no green or blue."""
        game = self.board(builder, orrery=True)
        kinnan = only_oid(game, "kinnan_bonder_prodigy", 0)
        assert activations_of(game, kinnan), "the {G}{U} was paid with colourless mana"

    def test_and_without_it_the_same_board_cannot(self, builder):
        """The control. Without it the assertion above is just "nine mana pays
        for seven"."""
        game = self.board(builder, orrery=False)
        kinnan = only_oid(game, "kinnan_bonder_prodigy", 0)
        assert not activations_of(game, kinnan)

    def test_it_loosens_a_spells_cost_too(self, builder):
        """The easy half, kept so the test above is measuring the *scope* of the
        waiver rather than measuring whether it exists at all."""
        game = self.board(builder, orrery=True, hand=[THREE_DROP])
        assert THREE_DROP in castable(game), "{G}{U}{R} off Wastes"

    def test_and_without_it_the_spell_is_uncastable(self, builder):
        game = self.board(builder, orrery=False, hand=[THREE_DROP])
        assert THREE_DROP not in castable(game)

    def test_its_own_tap_ability_still_makes_colourless_mana(self, builder):
        """The waiver is about *spending*, not about producing: the Orrery taps
        for five `{C}` and not for five of anything. A version that made the
        mana colour-flexible at the source would double-count the permission and
        show up as a five-colour Lotus."""
        game = self.board(builder, orrery=True)
        orrery = only_oid(game, "chromatic_orrery", 0)
        assert offered_symbols(game, orrery) == {"C"}


class TestKinnanBonderProdigy:
    """"Whenever you tap a nonland permanent for mana, add one mana of any type
    that permanent produced."

    Rule 605.1b makes this a mana ability even though it reads as a trigger, so
    it is folded into the tap itself and never uses the stack. The printed word
    is **nonland**, and the same sentence with "land" in it is Vorinclex -- the
    exact complement, and the card the engine already had.
    """

    def board(self, builder, cards):
        game = (
            builder(players=2)
            .battlefield(0, list(cards))
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .build(advance=False)
        )
        return game

    def tap(self, game, card_id: str) -> dict[str, int]:
        oid = only_oid(game, card_id, 0)
        activate_mana_ability(game.state, oid, 0, 0)
        return pool(game)

    def test_a_mana_creature_makes_two(self, builder):
        """Birds of Paradise taps for one mana of any colour; under Kinnan that
        is two."""
        game = self.board(builder, ["kinnan_bonder_prodigy", "birds_of_paradise"])
        assert sum(self.tap(game, "birds_of_paradise").values()) == 2

    def test_without_kinnan_it_makes_one(self, builder):
        """The control, so the assertion above is about Kinnan and not about
        Birds of Paradise."""
        game = self.board(builder, ["birds_of_paradise"])
        assert sum(self.tap(game, "birds_of_paradise").values()) == 1

    def test_a_land_is_left_alone(self, builder):
        """"**Nonland** permanent." A Mountain under Kinnan is a Mountain, and
        the deck runs thirty-odd of them."""
        game = self.board(builder, ["kinnan_bonder_prodigy", "mountain"])
        assert self.tap(game, "mountain") == {"R": 1}

    def test_a_basic_land_is_left_alone_even_beside_a_doubled_rock(self, builder):
        """Both on one board, so the split is per *permanent* and not per turn."""
        game = self.board(
            builder, ["kinnan_bonder_prodigy", "birds_of_paradise", "forest"]
        )
        assert sum(self.tap(game, "birds_of_paradise").values()) == 2
        assert sum(self.tap(game, "forest").values()) == 3, "+1 green, undoubled"

    def test_the_offer_and_the_payment_agree(self, builder):
        """`available_mana` is the planner's number and the tap above is the
        payment's. A spell offered on doubled mana and then paid on single mana
        strands the cast half-way through, so the two readers are pinned
        together rather than separately."""
        doubled = self.board(builder, ["kinnan_bonder_prodigy", "birds_of_paradise"])
        alone = self.board(builder, ["birds_of_paradise"])
        assert available_mana(doubled.state, 0) == 2
        assert available_mana(alone.state, 0) == 1

    def test_a_two_mana_rock_is_given_one_more_and_not_doubled(self, builder):
        """"Add **one** mana", which is not the same as twice the mana.

        This test found a real bug and its fix is in the same commit. The
        doubling family -- Kinnan here, Vorinclex and Zendikar Resurgent beside
        him -- multiplied the whole option by two. For every source the family
        had ever been tested against, a mana dork or a basic land, one more and
        twice as many are the same number. A Sol Ring is where they part: the
        printed Kinnan makes `{C}{C}{C}` and the engine made `{C}{C}{C}{C}`.

        Silently, and in the strictly-better direction, which is the pair of
        properties this whole pipeline exists to refuse.
        """
        game = self.board(builder, ["kinnan_bonder_prodigy", "sol_ring"])
        assert self.tap(game, "sol_ring") == {"C": 3}

    def test_a_one_mana_source_is_unchanged_by_the_fix(self, builder):
        """The reading that was always right, kept right.

        One more and twice as many coincide here, which is exactly why the bug
        above survived so long -- every source in the pool that anybody had
        pointed a doubler at made one mana.
        """
        game = self.board(builder, ["kinnan_bonder_prodigy", "birds_of_paradise"])
        assert sum(self.tap(game, "birds_of_paradise").values()) == 2


class TestKlauthUnrivaledAncient:
    """"Whenever Klauth attacks, add X mana in any combination of colors, where X
    is the total power of attacking creatures. Spend this mana only to cast
    spells. Until end of turn, you don't lose this mana as steps and phases end."

    Gate 5 casts a card and reads the board; it never attacks, so every word of
    this is new here. Three separate ways to get it wrong, each a different card:
    X as the *count* of attackers, the combination fixed to one colour, and the
    spend clause dropped -- which turns a big-mana payoff into a combo enabler.
    """

    def position(self, builder, *, friends=(), lands=()):
        """Klauth, a Chromatic Orrery, and -- by default -- no lands at all.

        The Orrery is the deck's own activated ability with a payable cost, and
        it is what the restriction is measured against. No lands, because an
        untapped land would fund it whatever the pool said. Its own `{T}`: it
        cannot tap for mana *and* pay its `{5}, {T}`, so the pool is the only
        thing that could.
        """
        return (
            builder(players=2)
            .battlefield(0, ["klauth_unrivaled_ancient", "chromatic_orrery", *friends, *lands])
            .hand(0, [THREE_DROP])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def attack_with(self, game, *card_ids: str) -> None:
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        for card_id in card_ids:
            game.apply(
                find_action(
                    game,
                    ActionKind.ADD_ATTACKER,
                    source=only_oid(game, card_id, 0),
                    targets=(TargetRef.player(1),),
                )
            )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))

    def divide(self, game, colors: str) -> None:
        """Answer the trigger's colour choice one mana at a time, in order."""
        for color in colors:
            pass_until(
                game, lambda g: g.pending() and g.pending().kind is DecisionKind.CHOOSE_MODE
            )
            game.apply(find_action(game, ActionKind.CHOOSE, choice=SPLIT.index(color)))

    def test_x_is_his_own_power_when_he_attacks_alone(self, builder):
        game = self.position(builder)
        self.attack_with(game, "klauth_unrivaled_ancient")
        self.divide(game, "RRRR")
        assert sum(pool(game).values()) == 4, "a 4/4 alone"

    def test_a_second_attacker_adds_its_power_and_not_one(self, builder):
        """The whole difference between "total power" and "number of attacking
        creatures": a 2/2 joining is +2. On a board of 1/1s the two readings
        coincide, which is why the witness is a bear."""
        game = self.position(builder, friends=[BEAR])
        self.attack_with(game, "klauth_unrivaled_ancient", BEAR)
        self.divide(game, "RRRRRR")
        assert sum(pool(game).values()) == 6

    def test_a_creature_left_at_home_is_not_counted(self, builder):
        """"Attacking", not "you control"."""
        game = self.position(builder, friends=[BEAR])
        self.attack_with(game, "klauth_unrivaled_ancient")
        self.divide(game, "RRRR")
        assert sum(pool(game).values()) == 4

    def test_the_four_are_divided_across_colours(self, builder):
        """The claim the card is played for, and the one a `choose_mode` over
        five fixed rituals cannot make: a mixed pool off one trigger."""
        game = self.position(builder)
        self.attack_with(game, "klauth_unrivaled_ancient")
        self.divide(game, "WUBR")
        assert pool(game) == {"W": 1, "U": 1, "B": 1, "R": 1}

    def test_all_of_one_colour_is_still_a_legal_division(self, builder):
        """"Any combination" includes the degenerate one."""
        game = self.position(builder)
        self.attack_with(game, "klauth_unrivaled_ancient")
        self.divide(game, "GGGG")
        assert pool(game) == {"G": 4}

    def test_the_mana_cannot_pay_for_an_activated_ability(self, builder):
        """"Spend this mana only to **cast spells**." Four mana floating and the
        Orrery's `{5}, {T}` still unaffordable -- which is the printed card.

        `{5}` is five and the pool holds four, so this is measured at the
        boundary rather than on the size: see the control below, where the same
        five mana off lands does offer it.
        """
        game = self.position(builder, friends=[BEAR])
        self.attack_with(game, "klauth_unrivaled_ancient", BEAR)
        self.divide(game, "RRRRRR")
        orrery = only_oid(game, "chromatic_orrery", 0)
        assert sum(pool(game).values()) == 6, "more than the {5} it is refusing"
        assert not activations_of(game, orrery)

    def test_unrestricted_mana_of_the_same_size_does_pay_for_it(self, builder):
        """The control. Five Wastes make the identical offer affordable, so the
        assertion above is measuring the clause and not the arithmetic."""
        game = self.position(builder, lands=["wastes"] * 5)
        self.attack_with(game, "klauth_unrivaled_ancient")
        self.divide(game, "RRRR")
        orrery = only_oid(game, "chromatic_orrery", 0)
        assert activations_of(game, orrery)

    def test_it_survives_the_end_of_the_phase(self, builder):
        """500.4 empties the pool at every boundary. A ritual that evaporated at
        the end of the declare-attackers step would never reach the postcombat
        main phase the card is bought for."""
        game = self.position(builder, friends=[BEAR])
        self.attack_with(game, "klauth_unrivaled_ancient", BEAR)
        self.divide(game, "GUURRR")
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)

        assert sum(pool(game).values()) == 6
        assert THREE_DROP in castable(game), "{G}{U}{R} paid out of the ritual"

    def test_it_does_not_survive_the_turn(self, builder):
        """"Until end of turn." Floating into the untap step would hand seat 0
        six mana on somebody else's turn."""
        game = self.position(builder, friends=[BEAR])
        self.attack_with(game, "klauth_unrivaled_ancient", BEAR)
        self.divide(game, "RRRRRR")
        pass_until(game, lambda g: g.state.turn > 1)

        assert pool(game) == {}


class TestArenaOfGlory:
    """"{R}, {T}, Exert this land: Add {R}{R}. If that mana is spent on a
    creature spell, it gains haste until end of turn."

    Two halves, and gate 5 reaches neither: it never activates the ability, and
    the ability is the entire card past "taps for red".

    The haste half is the trap. Every reachable way of writing it puts haste on
    the **spell**, and `reset_permanent_state` wipes that as the spell becomes a
    permanent -- so the creature arrives with nothing, and a test that asserts on
    the spell, or on the permanent without ever attacking, passes anyway. The
    assertion that catches it is the one the card is bought for: the creature is
    on the battlefield, it has haste, and it attacks **this turn**.
    """

    RIDER = 1  # ability 0 is the plain `{T}: Add {R}`; ability 1 exerts

    def position(self, builder, *, card_id: str = HASTELESS, lands: int = 4):
        """The Arena, four Mountains and a bear.

        One Mountain pays the Arena's `{R}`, leaving three untapped beside the
        `{R}{R}` in the pool -- exactly Terror of the Peaks' `{3}{R}{R}`, so the
        payment has one shape and both of the Arena's pips are in it. The bear
        is why there is a declare-attackers step at all.
        """
        return (
            builder(players=2)
            .battlefield(0, ["arena_of_glory", *["mountain"] * lands, BEAR])
            .hand(0, [card_id])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .build()
        )

    def cast_with_arena(self, game, card_id: str, *, rider: bool) -> int:
        arena = only_oid(game, "arena_of_glory", 0)
        if rider:
            game.apply(
                find_action(game, ActionKind.ACTIVATE, source=arena, ability_index=self.RIDER)
            )
        else:
            # The plain line is `Cost.is_tap_only`, so legality never offers it
            # as a row -- it is the payment solver's, and fired the way the
            # solver fires it.
            activate_mana_ability(game.state, arena, 0, 0)
        action = action_for_card(game, ActionKind.CAST, card_id)
        oid = action.source
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)
        return oid

    def to_combat(self, game) -> None:
        """Walk to **this** turn's declare-attackers step and no further.

        Not a bare `pass_until` on the step: the creature's controller is the
        active player, so the next such step would be theirs again two turns
        later with the summoning sickness long gone, and both halves of the test
        would look alike.
        """
        turn = game.state.turn
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
        assert game.state.turn == turn, "walked past the turn the creature entered"

    def test_the_mana_is_two_red(self, builder):
        game = self.position(builder)
        arena = only_oid(game, "arena_of_glory", 0)
        game.apply(find_action(game, ActionKind.ACTIVATE, source=arena, ability_index=self.RIDER))
        assert pool(game) == {"R": 2}

    def test_the_creature_has_haste_after_it_resolves(self, builder):
        """On the **battlefield**, not on the stack. Terror of the Peaks prints
        flying and no haste, so there is nothing here to mistake for the rider."""
        game = self.position(builder)
        oid = self.cast_with_arena(game, HASTELESS, rider=True)

        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert Keyword.HASTE.value in chars(game.state, oid).keywords

    def test_it_can_attack_that_turn(self, builder):
        """The assertion every wrong implementation fails, and silently."""
        game = self.position(builder)
        oid = self.cast_with_arena(game, HASTELESS, rider=True)
        self.to_combat(game)

        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),))
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert oid in game.state.combat.attackers

    def test_the_lands_other_ability_grants_nothing(self, builder):
        """The control, and the reason the rider rides the *pip*: Arena has two
        mana abilities and only the exerting one prints the clause. Recorded
        against the permanent, its plain `{R}` would hand out haste for free."""
        game = self.position(builder)
        oid = self.cast_with_arena(game, HASTELESS, rider=False)

        assert Keyword.HASTE.value not in chars(game.state, oid).keywords
        self.to_combat(game)
        assert not any(
            a.kind is ActionKind.ADD_ATTACKER and a.source == oid for a in game.legal_actions()
        )

    # -- the price --------------------------------------------------------

    def exerting_position(self, builder):
        """The Arena, one Mountain, and a two-drop worth making the mana for.

        Legality only offers a mana ability the seat could spend, so the
        creature in hand is load bearing: with nothing to cast, the exerting
        ability is not offered at all and the test would measure that instead.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["arena_of_glory", "mountain"])
            .hand(0, ["t_glory_sprinter"])
            .library(0, ["island"] * 40)
            .library(1, ["island"] * 40)
            .build()
        )
        arena = only_oid(game, "arena_of_glory", 0)
        game.apply(find_action(game, ActionKind.ACTIVATE, source=arena, ability_index=self.RIDER))
        return game, arena

    def test_exerting_taps_it_and_marks_it(self, builder):
        game, arena = self.exerting_position(builder)
        obj = game.state.objects[arena]
        assert obj.tapped, "the {T} half"
        assert obj.skip_next_untap, "the exert half"

    def test_it_stays_tapped_through_one_untap_step(self, builder):
        game, arena = self.exerting_position(builder)
        pass_until(game, lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert game.state.objects[arena].tapped, "its controller's next untap step came and went"

    def test_and_untaps_at_the_one_after_that(self, builder):
        """Exactly **one** untap step. A land that never untapped again would
        pass the test above and be a strictly worse card than the printed one --
        which is the direction nobody notices."""
        game, arena = self.exerting_position(builder)
        pass_until(game, lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert not game.state.objects[arena].skip_next_untap, "the one-shot is spent"
        pass_until(game, lambda g: g.state.turn >= 5 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert not game.state.objects[arena].tapped


class TestReflectingPool:
    """"{T}: Add one mana of any type that a land you control could produce."

    One printed word away from Exotic Orchard -- which this deck also runs -- and
    the word is worth a whole capability. 106.1b names **six** types of mana, so
    "any type" is "any color" plus `{C}`. Written as the `reflecting` the engine
    already had, the Pool loads clean, plays, and is an Exotic Orchard pointed at
    your own side: it cannot tap off a colourless land at all.
    """

    def board(self, builder, mine=(), theirs=()):
        game = (
            builder(players=2)
            .battlefield(0, ["reflecting_pool", *mine])
            .battlefield(1, list(theirs))
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .build(advance=False)
        )
        return game, only_oid(game, "reflecting_pool", 0)

    def test_a_colourless_land_makes_it_tap_for_colourless(self, builder):
        """The claim, and the whole difference from "any color": written as
        plain `reflecting` this is the empty set and the Pool taps for nothing."""
        game, pool_oid = self.board(builder, ["wastes"])
        assert offered_symbols(game, pool_oid) == {"C"}

    def test_a_land_that_makes_two_colourless_also_offers_it(self, builder):
        """Ancient Tomb adds `{C}{C}`. The amount is not the question -- whether
        the *type* appears at all is."""
        game, pool_oid = self.board(builder, ["ancient_tomb"])
        assert offered_symbols(game, pool_oid) == {"C"}

    def test_a_forest_offers_green_and_not_colourless(self, builder):
        """It is still the board's question. A six-mode any-type land would tap
        for `{C}` here with no colourless source out, and would be a better card."""
        game, pool_oid = self.board(builder, ["forest"])
        assert offered_symbols(game, pool_oid) == {"G"}

    def test_colour_and_colourless_together(self, builder):
        game, pool_oid = self.board(builder, ["forest", "wastes"])
        assert offered_symbols(game, pool_oid) == {"C", "G"}

    def test_it_reads_your_lands_and_not_an_opponents(self, builder):
        """"…a land **you control**." Exotic Orchard is the other half of the
        pair and is in this same deck, so the contrast is played rather than
        claimed: one board, two lands, two different answers."""
        game = (
            builder(players=2)
            .battlefield(0, ["reflecting_pool", "exotic_orchard", "wastes"])
            .battlefield(1, ["island"])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .build(advance=False)
        )
        assert offered_symbols(game, only_oid(game, "reflecting_pool", 0)) == {"C"}
        assert offered_symbols(game, only_oid(game, "exotic_orchard", 0)) == {"U"}

    def test_a_lone_pool_offers_nothing(self, builder):
        """The Pool is itself a land you control, and a reflecting ability is
        skipped before the recursion -- so it does not ask itself."""
        game, pool_oid = self.board(builder)
        assert offered_symbols(game, pool_oid) == set()
