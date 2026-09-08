"""`any_types` in a static filter: "instant **and** sorcery spells you cast".

Archmage of Runes, Baral, Goblin Electromancer, Jace's Sanctum — a whole family
whose printed line names two card types that no single card can both have.

`types` is a **conjunction**: `_matches_printed` tests `set(types).issubset(
card.types)`, which is exactly right for "artifact creature" and useless here,
because no spell is an instant *and* a sorcery. So `{"types": ["Instant",
"Sorcery"]}` loads clean, validates clean, and matches nothing whatever — a
cost reducer that reduces no cost. `TestTheConjunctionIsWhyThisExists` pins that
by keeping the broken spelling alive as a card and asserting it does nothing.

The selector language has had `any_types` for the or-of-types question since
before this; the *static* filter vocabularies did not, which is the whole of the
gap. The tempting alternative — writing `{"not_types": ["Creature"]}` — is
silently wider than printed: it discounts artifacts, enchantments and
planeswalkers too.

The shipped witness is Archmage of Runes; `t_runes` is its shape.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step

REDUCER = "t_runes"  # any_types: the working spelling
BROKEN = "t_runes_conjunction"  # types: the conjunction that matches nothing
INSTANT = "t_stormbolt"  # {2}{R} -- three mana
SORCERY = "t_casualty"  # {1}{B} -- two mana
CREATURE = "t_bear"  # {1}{G} -- a spell the reducer must NOT touch
MOUNTAIN = ["mountain"]
SWAMP = ["swamp"]
FOREST = ["forest"]
ISLAND = ["island"]


def position(builder, board, hand, lands, opp_board=()):
    """``lands`` is an explicit list of basics, exactly enough to sharpen a claim.

    Basics rather than a dual, and `advance=False` rather than the default:
    `build()` auto-advances, and with nothing castable it runs the turn on into
    combat -- where a test asking "can I cast this?" reads no cast lines and
    concludes the reducer failed, whatever the reducer did.
    """
    game = (
        builder(players=2)
        .battlefield(0, board + lands)
        .battlefield(1, ["plains", *opp_board])
        .library(0, ["forest"] * 20)
        .hand(0, hand)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def can_cast(game, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


class TestItDiscountsEitherType:
    def test_an_instant_costs_one_less(self, builder):
        """{2}{R} for three becomes castable off two lands."""
        game = position(builder, [REDUCER], [INSTANT], MOUNTAIN * 2)
        assert can_cast(game, INSTANT)

    def test_a_sorcery_costs_one_less(self, builder):
        """The half a conjunction filter can never reach. {1}{B} off one land."""
        game = position(builder, [REDUCER], [SORCERY], SWAMP * 1)
        assert can_cast(game, SORCERY)

    def test_without_the_reducer_the_same_lands_are_not_enough(self, builder):
        """The control. Two lands do not cast a three-mana instant unaided."""
        game = position(builder, [], [INSTANT], MOUNTAIN * 2)
        assert not can_cast(game, INSTANT)

        game = position(builder, [], [SORCERY], SWAMP * 1)
        assert not can_cast(game, SORCERY)


class TestItLeavesOtherSpellsAlone:
    def test_a_creature_spell_is_not_discounted(self, builder):
        """"instant and sorcery" is a restriction, not decoration.

        The near-miss spelling for this line is `not_types: ["Creature"]`, which
        would pass this test and silently discount artifacts and enchantments
        too. `any_types` says only what the card says.
        """
        game = position(builder, [REDUCER], [CREATURE], FOREST * 1)
        assert not can_cast(game, CREATURE)

        game = position(builder, [REDUCER], [CREATURE], FOREST * 2)
        assert can_cast(game, CREATURE), "still castable at its printed price"


class TestTheConjunctionIsWhyThisExists:
    def test_the_types_spelling_discounts_nothing(self, builder):
        """`types` is issubset, and no spell is both an instant and a sorcery.

        Kept as a live card rather than a comment: this is the failure mode the
        key exists to remove, and it is invisible -- the card loads, compiles
        and sits on the battlefield looking implemented.
        """
        game = position(builder, [BROKEN], [INSTANT], MOUNTAIN * 2)
        assert not can_cast(game, INSTANT), "the conjunction matched nothing"

        game = position(builder, [BROKEN], [SORCERY], SWAMP * 1)
        assert not can_cast(game, SORCERY)

    def test_and_the_any_types_spelling_does(self, builder):
        """Same position, same spells, one key different."""
        game = position(builder, [REDUCER], [INSTANT], MOUNTAIN * 2)
        assert can_cast(game, INSTANT)


class TestItIsTheControllersDiscount:
    def test_an_opponents_reducer_does_not_discount_your_spell(self, builder):
        """`controller: "you"` is read against the static's source, not the caster."""
        game = position(builder, [], [INSTANT], MOUNTAIN * 2, opp_board=[REDUCER])
        assert not can_cast(game, INSTANT)


def test_the_reducer_itself_is_unaffected(builder):
    """A creature spell reducing instants must not discount creature spells."""
    game = position(builder, [REDUCER], [REDUCER], ISLAND * 4)
    assert not can_cast(game, REDUCER), "{3}{U}{U} is five, and four lands is four"

    game = position(builder, [REDUCER], [REDUCER], ISLAND * 5)
    assert can_cast(game, REDUCER)
