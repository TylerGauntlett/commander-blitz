"""Imprint's mana half — "one mana of any of **the exiled card's colors**".

    Chrome Mox — "Imprint — When this artifact enters, you may exile a
    nonartifact, nonland card from your hand.
     {T}: Add one mana of any of the exiled card's colors."

The exile link is `test_imprint.py`'s subject and shipped long ago. What was
missing is the *question the mana ability asks*: `add_mana` knew four ways of
naming which colours it offers and none of them reads the printed colours of a
**card**.

`reflecting` is the near miss and is the whole reason this is a fifth key rather
than a fourth spelling. It asks each matched object's own mana **abilities**
what they could produce (`costs.mana_options_of` iterates `abilities_of` and
skips anything that is not a mana ability), and the imprinted card is a
nonartifact, nonland card lying in exile — it has no abilities at all, let alone
mana ones. Written that way the Mox loads clean, reads its own imprint
correctly, and taps for nothing for ever. `t_chrome_reflect` is that card, kept
here so the claim is demonstrated rather than asserted.

The other near miss is a `choose_mode` over five `add_mana`s, and it is the one
worth naming: it is *strictly better than the printed card*, because it taps for
any colour with **nothing imprinted at all**. 105.1 also says colourless is not
a colour, so an imprinted Eldrazi offers nothing either. Both of those are the
boundary this file exists to pin — an unimprinted Mox producing NOTHING is the
claim, not the happy path.

`mana_options` still carries the five-colour superset at load time, for the same
reason `reflecting` needs one: an empty tuple there makes `solver_taps` and
`offerable_mana_ability` decide this is not a mana source at all, so the ability
would never be offered whatever was imprinted. The card prints no mana symbol,
so that superset must not reach colour identity either — a five-colour Chrome
Mox is illegal in every commander deck that is not itself five-colour (903.4).
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.costs import activate_mana_ability, mana_options_of, mana_sources
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from automtg.engine.mana import SYMBOL_INDEX
from tests.conftest import action_for_card, only_oid, pass_until

ISLAND = "island"
MOX = "t_chrome"  # the capability: `colors_of`
MIRROR = "t_chrome_reflect"  # the same card written as `reflecting`
BLUE = "t_blue_spell"  # {U}
GOLD = "t_gold_spell"  # {U}{R}
VOID = "t_void_spell"  # {2}, colourless


def position(builder, hand: list[str], mox: str = MOX):
    return (
        builder(players=2)
        .battlefield(0, [ISLAND] * 4)
        .hand(0, [mox, *hand])
        .library(0, [ISLAND] * 20)
        .library(1, [ISLAND] * 20)
        .build()
    )


def play_the_mox(game, *, imprint: bool = True, mox: str = MOX):
    """Cast it and answer the imprint trigger, yes or no."""
    game.apply(action_for_card(game, ActionKind.CAST, mox))
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None and d.kind.value == "may",
        limit=60,
    )
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is (ActionKind.YES if imprint else ActionKind.NO)
        )
    )
    pass_until(game, lambda g: g.pending() is None or not g.state.stack)


def colors_offered(game, oid: int) -> set[str]:
    """Every symbol the mana ability actually offers, after the imprint narrows it."""
    ability = game.state.card(oid).abilities[1]
    out: set[str] = set()
    for option in mana_options_of(game.state, oid, ability):
        for symbol, index in SYMBOL_INDEX.items():
            if option[index]:
                out.add(symbol)
    return out


def imprinted(builder, card: str, mox: str = MOX):
    """A Mox on the battlefield, having imprinted ``card``."""
    game = position(builder, [card], mox=mox)
    play_the_mox(game, mox=mox)
    return game, only_oid(game, mox)


def unimprinted(builder, mox: str = MOX):
    """The same Mox, with the imprint **declined** — the blue card stays in hand.

    Declined rather than played off an empty hand, because "you may exile" with
    nothing to exile never asks and the position would be built by accident.
    This way the exile was possible, offered, and refused.
    """
    game = position(builder, [BLUE], mox=mox)
    play_the_mox(game, imprint=False, mox=mox)
    return game, only_oid(game, mox)


class TestNothingImprintedIsNothingAdded:
    """The claim, and the refusal of the five-mode approximation.

    A `choose_mode` over five `add_mana`s reads as the same sentence and is a
    different, better card: it taps for any colour before anything is exiled.
    """

    def test_an_unimprinted_mox_offers_no_colour(self, builder):
        game, mox = unimprinted(builder)
        assert colors_offered(game, mox) == set()

    def test_the_solver_can_produce_nothing_from_it(self, builder):
        """The solver reads the same narrowing, so it must not plan around a
        colour: the source is listed and offers no option, which is the answer
        `_identity_options` gives a colourless commander."""
        game, mox = unimprinted(builder)
        source = next(s for s in mana_sources(game.state, 0) if s.oid == mox)
        assert source.producible() == set()

    def test_declining_the_imprint_leaves_the_card_in_hand(self, builder):
        """The position the tests above assert about is a real one: the Mox is
        on the battlefield and the blue card it *could* have exiled is still in
        hand, so it is the imprint that is missing, not the colour."""
        game, _ = unimprinted(builder)
        assert BLUE in [game.state.objects[o].def_id for o in game.state.players[0].hand]


class TestTheImprintedCardsColors:
    def test_a_mono_blue_card_offers_blue(self, builder):
        game, mox = imprinted(builder, BLUE)
        assert colors_offered(game, mox) == {"U"}

    def test_it_offers_that_colour_and_no_other(self, builder):
        game, mox = imprinted(builder, BLUE)
        assert len(colors_offered(game, mox)) == 1

    def test_a_gold_card_offers_both_of_its_colours(self, builder):
        """"…any **of** the exiled card's colors" — a two-colour card is two
        options, one mana either way, not two mana."""
        game, mox = imprinted(builder, GOLD)
        assert colors_offered(game, mox) == {"U", "R"}

    def test_a_gold_card_still_offers_only_one_mana(self, builder):
        game, mox = imprinted(builder, GOLD)
        ability = game.state.card(mox).abilities[1]
        options = mana_options_of(game.state, mox, ability)
        assert [sum(option) for option in options] == [1, 1]

    def test_a_colourless_card_offers_nothing(self, builder):
        """105.1: colourless is not a colour. The boundary a sixth `{C}` option
        would quietly cross, and the reason there is no `any_type` here."""
        game, mox = imprinted(builder, VOID)
        assert colors_offered(game, mox) == set()


class TestTheSolverAndThePaymentAgree:
    """`mana_options_of` has two callers — `_sources_of` while planning and
    `activate_mana_ability` while paying — and a spell offered on one colour
    then billed in another strands the payment mid-cast."""

    def test_an_imprinted_mox_is_a_source(self, builder):
        game, mox = imprinted(builder, BLUE)
        assert any(s.oid == mox for s in mana_sources(game.state, 0))

    def test_it_produces_the_imprinted_colour(self, builder):
        game, mox = imprinted(builder, BLUE)
        source = next(s for s in mana_sources(game.state, 0) if s.oid == mox)
        assert source.producible() == {SYMBOL_INDEX["U"]}

    def test_a_gold_imprint_produces_both(self, builder):
        game, mox = imprinted(builder, GOLD)
        source = next(s for s in mana_sources(game.state, 0) if s.oid == mox)
        assert source.producible() == {SYMBOL_INDEX["U"], SYMBOL_INDEX["R"]}


class TestTappingItAddsThatMana:
    """`activate_mana_ability` indexes the *narrowed* list, so the colour the
    solver planned on is the colour that lands in the pool."""

    def test_it_adds_the_imprinted_colour(self, builder):
        game, mox = imprinted(builder, BLUE)
        activate_mana_ability(game.state, mox, 1, 0)
        pool = game.state.players[0].mana_pool
        assert pool.amounts[SYMBOL_INDEX["U"]] == 1

    def test_it_adds_exactly_one_mana(self, builder):
        game, mox = imprinted(builder, BLUE)
        activate_mana_ability(game.state, mox, 1, 0)
        assert sum(game.state.players[0].mana_pool.amounts) == 1

    def test_an_unimprinted_mox_cannot_be_tapped_for_anything(self, builder):
        """There is no option 0 to index into, so the payment refuses rather
        than falling back on the five-colour superset — which is the shape of
        the strictly-better card this whole capability refuses."""
        game, mox = unimprinted(builder)
        with pytest.raises(DslError):
            activate_mana_ability(game.state, mox, 1, 0)


class TestReflectingIsADifferentCard:
    """The same selector under `reflecting` polls the exiled card's mana
    *abilities*. A nonartifact, nonland card has none, so the Mox taps for
    nothing — which is why this is a fifth key and not a fourth spelling."""

    def test_the_mirror_taps_for_nothing_even_imprinted(self, builder):
        game, mirror = imprinted(builder, BLUE, mox=MIRROR)
        assert colors_offered(game, mirror) == set()

    def test_and_the_real_card_taps_off_the_same_imprint(self, builder):
        game, mox = imprinted(builder, BLUE)
        assert colors_offered(game, mox) == {"U"}


def _artifact(effect: dict) -> dict:
    return {
        "id": "t_colors_of_probe",
        "name": "Probe",
        "mana_cost": "{0}",
        "types": ["Artifact"],
        "abilities": [
            {
                "kind": "activated",
                "text": "{T}: Add one mana of any of the exiled card's colors.",
                "is_mana_ability": True,
                "cost": {"tap": True},
                "effects": [effect],
            }
        ],
    }


EXILED = {"zone": "exile", "controller": "any", "exiled_with": "self"}


class TestTheLoaderPinsTheSuperset:
    """The static superset is what makes this a mana source before the imprint
    is consulted; the narrowing happens at activation."""

    def test_it_advertises_five_colours(self):
        card = compile_card(
            CardModel.model_validate(_artifact({"op": "add_mana", "colors_of": EXILED}))
        )
        ability = card.abilities[0]
        assert ability.mana_colors_of == EXILED
        assert len(ability.mana_options) == 5

    def test_the_superset_is_not_colour_identity(self):
        """903.4 is deck construction, and the card prints no mana symbol: a
        derived five-colour identity would make Chrome Mox illegal in every
        commander deck that is not itself five-colour."""
        card = compile_card(
            CardModel.model_validate(_artifact({"op": "add_mana", "colors_of": EXILED}))
        )
        assert card.color_identity == frozenset()


class TestTheLoaderRefusesTheAmbiguousSpellings:
    def test_an_add_mana_with_no_colours_at_all_is_still_refused(self):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(_artifact({"op": "add_mana"})))

    def test_colors_of_beside_a_fixed_mana_string_is_refused(self):
        """Two answers to one question, and only the `mana` string would be
        read — a Mox that taps for {R} whatever it imprinted."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    _artifact({"op": "add_mana", "mana": "{R}", "colors_of": EXILED})
                )
            )

    def test_colors_of_beside_reflecting_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    _artifact({"op": "add_mana", "reflecting": EXILED, "colors_of": EXILED})
                )
            )

    def test_an_amount_is_refused_rather_than_dropped(self):
        """The narrowing hands back one-symbol options, so an amount here would
        load and leave a card printing "two mana" adding one."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    _artifact(
                        {"op": "add_mana", "colors_of": EXILED, "amount": {"const": 2}}
                    )
                )
            )

    def test_any_type_is_refused_beside_it(self):
        """106.1b's sixth type is not on offer: "any of the card's colors" is
        colours, and 105.1 says colourless is not one."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    _artifact({"op": "add_mana", "colors_of": EXILED, "any_type": True})
                )
            )

    def test_it_is_read_by_no_other_op(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_colors_of_probe",
                        "name": "Probe",
                        "mana_cost": "{0}",
                        "types": ["Artifact"],
                        "abilities": [
                            {
                                "kind": "activated",
                                "text": "{T}: Draw a card.",
                                "cost": {"tap": True},
                                "effects": [
                                    {
                                        "op": "draw",
                                        "amount": {"const": 1},
                                        "colors_of": EXILED,
                                    }
                                ],
                            }
                        ],
                    }
                )
            )
