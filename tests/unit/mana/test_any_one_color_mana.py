"""Mana that is all one colour, in a size the board sets, spendable on two clauses.

"{T}: Add X mana of **any one color**, where X is Helga's power. Spend this mana
only to cast creature spells with mana value 4 or greater or creature spells with
{X} in their mana costs." -- Helga, Skittish Seer. Two capabilities in one line,
and every way of approximating either ships a card better than the printed one.

**The size and the colour together.** "Add N mana of any one color" is spelled as
a `choose_mode` of five fixed `add_mana`s (Gilded Lotus), which needs a literal N
at load time; Helga's N is her power, and she is a 1/1 that grows with every
+1/+1 counter her own first ability puts on her. The `amount` that *does* read
the board (Gyre Sage) scales a single `add_mana` and refuses to sit on a
`choose_mode` -- so written that way `mana_amount` comes back `None` and the card
taps for exactly one mana for ever, which loads clean and plays as a different
card. `add_mana` with `split` is the dangerous near miss and is the *other*
direction: "any combination" at X=3 makes {W}{U}{G}, which the printed Helga
cannot. `TestTheManaIsAllOneColour` is the witness for that one.

**The restriction.** `mana_restriction`'s whole vocabulary was type names, and
neither clause has a name. `"mana-value-4"` is not a type -- it is the
permanently-unspendable mana `mana._restriction_name`'s shape check exists to
catch, and `TestTheLoaderRefusesAnInventedName` pins that it still does. Dropping
both clauses leaves the bare `["creature"]` of Ancient Ziggurat, which funds
every creature spell ever printed: `t_ziggurat_seer` is that card, kept alive
beside the real one so `TestTheBareCreatureSpellingIsABetterCard` can show the
difference rather than assert it.

So a `RestrictionGroup` carries a **predicate** beside its names, and
`SpendPurpose` carries the two numbers to answer one with. The groups are an
any-of of two all-ofs, exactly as the printed "or" reads.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.costs import mana_amount, mana_options_of, mana_sources, spell_purpose
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.mana import SYMBOLS, compile_restriction
from automtg.engine.primitives import add_counters
from tests.conftest import only_oid

#: "{T}: Add X mana of any one color, where X is its power." Restricted to
#: creature spells of mana value 4 or greater, or with {X} in their cost.
SEER = "t_one_colour_seer"
#: The same ability with the bare `["creature"]` restriction -- Ancient
#: Ziggurat's spelling, and the closest thing the language had.
ZIGGURAT = "t_ziggurat_seer"

SMALL = "t_seer_small_beast"  # {3} creature -- under the bar
BIG = "t_seer_big_beast"  # {4} creature -- over it
XSPELL = "t_seer_x_beast"  # {X}{G} creature -- mana value 1, and an {X}
RELIC = "t_seer_relic"  # {4} artifact -- big enough, and not a creature


def a_seer(builder, power: int = 1, *, card: str = SEER, hand=()):
    """The seer on the battlefield at ``power``, grown with +1/+1 counters.

    Printed a 1/1, so ``power`` counters minus the one she starts with. The
    library keeps the auto-pass from decking anybody before a test looks.
    """
    game = (
        builder(players=2)
        .battlefield(0, [card])
        .hand(0, list(hand))
        .library(0, ["forest"] * 20)
        .library(1, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    oid = only_oid(game, card)
    for _ in range(power - 1):
        add_counters(game.state, oid, "+1/+1", 1)
    game.state.bump_chars()
    ability = next(a for a in game.state.registry.get(card).abilities if a.is_mana_ability)
    return game, oid, ability


def colours_of(option) -> list[str]:
    """Which symbols an option actually produces, by name."""
    return [SYMBOLS[i] for i, amount in enumerate(option) if amount]


class TestTheManaIsAllOneColour:
    """The half `split` gets wrong: "any one color", not "any combination"."""

    def test_five_options_one_per_colour(self, builder):
        game, oid, ability = a_seer(builder, 3)
        assert [colours_of(o) for o in mana_options_of(game.state, oid, ability)] == [
            ["W"],
            ["U"],
            ["B"],
            ["R"],
            ["G"],
        ]

    def test_no_offer_ever_mixes_two_colours(self, builder):
        """{W}{U}{G} off a power-3 source is the better card `split` would ship."""
        game, _oid, _ = a_seer(builder, 3, hand=[BIG])
        purpose = spell_purpose(game.state.registry.get(BIG))
        for source in mana_sources(game.state, 0, purpose=purpose):
            for option in source.options:
                assert len(colours_of(option)) == 1, f"{option} is a combination, not one colour"

    def test_the_whole_size_lands_in_that_one_colour(self, builder):
        game, _oid, _ = a_seer(builder, 3, hand=[BIG])
        offered = {
            tuple(option)
            for source in mana_sources(
                game.state, 0, purpose=spell_purpose(game.state.registry.get(BIG))
            )
            for option in source.options
        }
        assert offered == {
            (3, 0, 0, 0, 0, 0),
            (0, 3, 0, 0, 0, 0),
            (0, 0, 3, 0, 0, 0),
            (0, 0, 0, 3, 0, 0),
            (0, 0, 0, 0, 3, 0),
        }


class TestXTracksHerPower:
    """She is a 1/1 who grows, so the size is a question and not a constant."""

    def test_a_printed_one_one_makes_one_mana(self, builder):
        game, oid, ability = a_seer(builder, 1)
        assert mana_amount(game.state, oid, ability) == 1

    def test_counters_raise_it(self, builder):
        game, oid, ability = a_seer(builder, 4)
        assert mana_amount(game.state, oid, ability) == 4

    def test_it_is_read_off_the_board_not_the_printed_face(self, builder):
        """The `choose_mode` spelling would answer 1 here for ever."""
        game, oid, ability = a_seer(builder, 1)
        add_counters(game.state, oid, "+1/+1", 5)
        game.state.bump_chars()
        assert mana_amount(game.state, oid, ability) == 6

    def test_zero_power_taps_for_nothing(self, builder):
        game, oid, ability = a_seer(builder, 1)
        add_counters(game.state, oid, "-1/-1", 1)
        game.state.bump_chars()
        assert mana_amount(game.state, oid, ability) == 0
        assert mana_sources(game.state, 0, purpose=None) == []


class TestWhatTheManaMayPayFor:
    """The any-of of two all-ofs, at each of its four corners."""

    def permits(self, builder, card_id: str, *, seer: str = SEER) -> bool:
        game, _oid, _ability = a_seer(builder, 4, card=seer)
        purpose = spell_purpose(game.state.registry.get(card_id))
        return bool(mana_sources(game.state, 0, purpose=purpose))

    def test_a_four_mana_creature_spell_is_funded(self, builder):
        assert self.permits(builder, BIG)

    def test_a_three_mana_creature_spell_is_not(self, builder):
        """The bar is 4, and one under it is where a dropped predicate shows."""
        assert not self.permits(builder, SMALL)

    def test_an_x_creature_spell_is_funded(self, builder):
        """{X}{G} is mana value 1 (202.3b), so only the second group reaches it."""
        assert self.permits(builder, XSPELL)

    def test_a_four_mana_noncreature_spell_is_not(self, builder):
        """Big enough for the comparison, and never a creature."""
        assert not self.permits(builder, RELIC)


class TestTheBareCreatureSpellingIsABetterCard:
    """`["creature"]` is what the language had, and it is a different card."""

    def test_it_funds_the_three_drop_the_printed_card_refuses(self, builder):
        assert TestWhatTheManaMayPayFor().permits(builder, SMALL, seer=ZIGGURAT)

    def test_and_still_refuses_the_artifact(self, builder):
        """So the contrast is the predicate alone, not the type name."""
        assert not TestWhatTheManaMayPayFor().permits(builder, RELIC, seer=ZIGGURAT)


class TestCastingThroughIt:
    """End to end: what a power-4 seer's four mana actually buys, in a real turn.

    The position is anchored with a Plains and a {W} instant, because a
    precombat main phase where the active player has nothing to do auto-advances
    into combat -- and a test reading zero cast actions there would pass for the
    wrong reason. One white mana is also the only *unrestricted* mana on the
    board, which is a mana short of every spell tested here: anything castable
    is castable because the seer's mana was allowed to pay.
    """

    def position(self, builder, hand, *, power: int = 4):
        game = (
            builder(players=2)
            .battlefield(0, [SEER, "plains"])
            .hand(0, [*hand, "t_plain_instant"])
            .library(0, ["forest"] * 20)
            .library(1, ["island"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        oid = only_oid(game, SEER)
        for _ in range(power - 1):
            add_counters(game.state, oid, "+1/+1", 1)
        game.state.bump_chars()
        game._advance()
        return game

    def castable(self, game) -> set[str]:
        return {
            game.state.card_of(game.state.objects[a.source]).id
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
        }

    def test_the_four_drop_is_castable(self, builder):
        assert BIG in self.castable(self.position(builder, [BIG]))

    def test_the_three_drop_is_not(self, builder):
        """A three-mana creature beside four mana it may not buy."""
        assert SMALL not in self.castable(self.position(builder, [SMALL]))

    def test_the_x_creature_is(self, builder):
        assert XSPELL in self.castable(self.position(builder, [XSPELL]))

    def test_the_artifact_is_not(self, builder):
        assert RELIC not in self.castable(self.position(builder, [RELIC]))

    def test_the_bare_creature_spelling_would_have_bought_the_three_drop(self, builder):
        """The contrast, played out rather than asserted about a data structure."""
        game = (
            builder(players=2)
            .battlefield(0, [ZIGGURAT, "plains"])
            .hand(0, [SMALL, "t_plain_instant"])
            .library(0, ["forest"] * 20)
            .library(1, ["island"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        for _ in range(3):
            add_counters(game.state, only_oid(game, ZIGGURAT), "+1/+1", 1)
        game.state.bump_chars()
        game._advance()
        assert SMALL in self.castable(game)

    def test_the_spell_really_goes_on_the_stack(self, builder):
        game = self.position(builder, [BIG])
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.card_of(game.state.objects[a.source]).id == BIG
        )
        game.apply(action)
        assert BIG in {
            game.state.card_of(obj).id
            for obj in game.state.objects.values()
            if obj.zone is Zone.STACK
        }


class TestTheLoaderRefusesAnInventedName:
    """The failure the shape check exists for, in the place it now has a spelling.

    A restriction that names nothing ever printed does not fail -- it freezes,
    and the card reads at the table as a creature that taps for nothing.
    """

    def test_a_predicate_written_as_a_name_is_refused(self):
        with pytest.raises(DslError, match="unparsable mana restriction"):
            compile_restriction(["mana-value-4"], "r")

    def test_the_predicate_key_as_a_bare_name_names_its_spelling(self):
        with pytest.raises(DslError, match="predicate, not a type"):
            compile_restriction(["mana value"], "r")

    def test_an_unknown_key_inside_the_predicate_object_is_refused(self):
        with pytest.raises(DslError, match="unknown keys"):
            compile_restriction([[{"mana_value": {"op": ">=", "amount": 4}}]], "r")

    def test_a_comparison_where_the_x_question_belongs_is_refused(self):
        """A truthy mapping would read as `true` and widen the clause silently."""
        with pytest.raises(DslError, match="true or false"):
            compile_restriction([[{"x_in_mana_cost": {"op": ">=", "value": 1}}]], "r")

    def test_a_board_reading_value_is_refused(self):
        """Compiled once at load, so there is no context to evaluate one in."""
        with pytest.raises(DslError, match="literal number"):
            compile_restriction([[{"mana_value": {"op": ">=", "value": {"count": {}}}}]], "r")

    def test_the_authoring_pipelines_const_spelling_is_accepted(self):
        groups = compile_restriction([[{"mana_value": {"op": ">=", "value": {"const": 4}}}]], "r")
        assert groups.cast[0].mana_value == (">=", 4)


class TestTheLoaderRefusesAHalfWrittenAbility:
    """`amount` is the capability; without it the card is a quieter one."""

    def _card(self, effect):
        return {
            "id": "t_bad_seer",
            "name": "Test Bad Seer",
            "mana_cost": "{G}",
            "types": ["Creature"],
            "subtypes": ["Elf"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "activated",
                    "text": "{T}: Add X mana of any one color.",
                    "is_mana_ability": True,
                    "cost": {"tap": True},
                    "effects": [effect],
                }
            ],
        }

    def test_no_amount_is_refused(self):
        with pytest.raises(DslError, match="needs an 'amount'"):
            compile_card(CardModel.model_validate(self._card({"op": "add_mana", "any_one_color": True})))

    def test_it_cannot_be_written_beside_a_fixed_symbol(self):
        with pytest.raises(DslError, match="two answers to one question"):
            compile_card(
                CardModel.model_validate(
                    self._card(
                        {
                            "op": "add_mana",
                            "any_one_color": True,
                            "mana": "{G}",
                            "amount": {"power_of": {"self": True}},
                        }
                    )
                )
            )

    def test_it_cannot_be_written_beside_a_split(self):
        """"Any one color" and "any combination" are the two cards this tells apart."""
        with pytest.raises(DslError, match="two answers to one question"):
            compile_card(
                CardModel.model_validate(
                    self._card(
                        {
                            "op": "add_mana",
                            "any_one_color": True,
                            "split": ["U", "R"],
                            "amount": {"power_of": {"self": True}},
                        }
                    )
                )
            )


class TestItPrintsNoManaSymbol:
    """903.4: colour identity comes off the symbols, and this line has none."""

    def test_the_five_colour_superset_is_not_an_identity(self, registry):
        assert registry.get(SEER).color_identity == frozenset({"G", "U"})
