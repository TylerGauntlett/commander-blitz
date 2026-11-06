""""As this artifact enters, choose a color."

Heraldic Banner is the witness and it asks the question three times over: the
colour it names is read back by a static filter ("creatures you control **of the
chosen color** get +1/+0"), by a mana ability ("{T}: Add one mana **of the
chosen color**"), and — on Brave the Elements — by `grant_protection`
("protection from **the color of your choice**"). 105.2 says a colour is a
characteristic like any other; the engine had a chooser for creature types and
none for colours, so all three lines were literal-only.

This is the exact colour twin of `choose_type`, down to its two decisions, and
both are worth restating because both were tempting to get wrong:

**No new `DecisionKind`.** `ask_mode` already asks "pick one of these labels"
and hands back an index, which is precisely this question — so legality's
`_choice_actions`, `game.apply` and the authoring verifier's auto-answer table
all keep working unchanged. A `CHOOSE_COLOR` kind would have been the same
decision wearing a different name.

*Divergence, recorded in `docs/rules-coverage.md` on `choose_type`'s own entry
rather than as a second claim*: the printed line is "**as** this enters", a
replacement that cannot be responded to. `zones` applies enter-replacements
synchronously and cannot stop to ask, so this is a `self_enters` trigger and the
colour is chosen a moment after the permanent arrives rather than as it does.

Three things are pinned here because each one is a different card if it goes the
other way:

- Before a colour is chosen, the anthem pumps **nobody** and the mana ability
  offers **nothing**. Both defaults are "match nothing", never "match
  everything": a filter that fell back to everything would make the Banner a
  global anthem for as long as its own trigger sat on the stack, and a mana
  ability that offered all five would be a Chromatic Lantern for the same
  window.
- The mana ability is locked to the one colour named on entry. Spelled as the
  `choose_mode` of five `add_mana`s the DSL already had, it would be the *any
  colour* card — a free pick every activation, and decoupled from the anthem
  that is supposed to read the same choice.
- The choice lives on the *object*, not the card: two Banners choose
  independently, and one that leaves and returns is a new object that chooses
  again.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars, protection_from
from commanderblitz.engine.costs import activate_mana_ability, mana_options_of
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError

BANNER = "t_heraldic"  # {3} artifact: choose a colour, anthem, and a mana ability
BRAVE = "t_brave"  # {W} instant: protection from the colour of your choice
BEAR = "t_bear"  # {1}{G} Bear — green
FLIER = "t_flier"  # {2}{U} Bird — blue
GOBLIN = "t_goblin"  # {1}{R} Goblin — red
DEATHTOUCHER = "t_deathtoucher"  # {B} creature — the one-mana black spell


def only(game, def_id: str) -> int:
    return next(o for o in game.state.battlefield if game.state.objects[o].def_id == def_id)


def board(builder, chosen: str | None = None, extra=()):
    """A Banner already on the battlefield, with ``chosen`` written on it.

    Written directly rather than answered, because most of these claims are
    about what the choice *does* once made, and a position is a cheaper witness
    than a cast.
    """
    b = builder(players=2).battlefield(0, [BANNER, *extra])
    for oid in list(b.state.battlefield):
        if b.state.objects[oid].def_id == BANNER:
            b.state.objects[oid].chosen_color = chosen
    b.state.bump_chars()
    return b.build()


def cast_the_banner(builder):
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * 6)
        .hand(0, [BANNER])
        .library(0, ["forest"] * 10)
        .active(0)
        .max_turns(1)
        .build()
    )
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BANNER
        )
    )
    return game


def choose(game, color_label: str) -> None:
    """Answer a `choose_color` decision with a named colour."""
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_MODE
    index = [o.label for o in decision.options].index(color_label)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and a.choice == index
        )
    )


def mana_ability(game, oid: int):
    """The Banner's ``(ability, options)`` as the solver sees it right now."""
    ability = next(
        a for a in game.state.card(oid).abilities if a.is_mana_ability
    )
    return ability, mana_options_of(game.state, oid, ability)


def spending(builder, chosen: str | None):
    """A Banner and nothing else that makes mana, with a {B} spell in hand."""
    b = (
        builder(players=2)
        .battlefield(0, [BANNER])
        .hand(0, [DEATHTOUCHER])
        .library(0, ["forest"] * 10)
        .active(0)
        .max_turns(1)
    )
    for oid in list(b.state.battlefield):
        if b.state.objects[oid].def_id == BANNER:
            b.state.objects[oid].chosen_color = chosen
    b.state.bump_chars()
    return b.build()


def castable(game, def_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
        for a in game.legal_actions()
    )


class TestTheChoice:
    def test_it_is_asked_as_the_banner_arrives(self, builder):
        game = cast_the_banner(builder)
        decision = game.pending()
        assert decision is not None
        assert decision.prompt == "Choose a color"

    def test_it_offers_the_five_colours_in_printed_order(self, builder):
        """A fixed list, not a survey of the pool the way `choose_type` is.

        Every colour is always a legal answer, so there is nothing for the board
        to narrow — and WUBRG order is what keeps a replay picking the same
        colour from the same index.
        """
        game = cast_the_banner(builder)
        labels = [o.label for o in game.pending().options]
        assert labels == ["White", "Blue", "Black", "Red", "Green"]

    def test_it_is_recorded_on_the_permanent_as_a_letter(self, builder):
        """The letter, because that is what `card.colors` holds."""
        game = cast_the_banner(builder)
        choose(game, "Green")
        assert game.state.objects[only(game, BANNER)].chosen_color == "G"

    def test_it_reuses_choose_mode_rather_than_a_new_kind(self, builder):
        game = cast_the_banner(builder)
        assert game.pending().kind is DecisionKind.CHOOSE_MODE, (
            "no CHOOSE_COLOR kind; every seat answers this already"
        )


class TestTheAnthem:
    def test_it_pumps_the_chosen_colour(self, builder):
        game = board(builder, "G", extra=[BEAR])
        c = chars(game.state, only(game, BEAR))
        assert (c.power, c.toughness) == (3, 2), "+1/+0, not +1/+1"

    def test_it_leaves_other_colours_alone(self, builder):
        game = board(builder, "R", extra=[BEAR])
        c = chars(game.state, only(game, BEAR))
        assert (c.power, c.toughness) == (2, 2)

    def test_before_a_choice_it_pumps_nobody(self, builder):
        """An unresolved filter must match nothing, never everything."""
        game = board(builder, None, extra=[BEAR])
        assert game.state.objects[only(game, BANNER)].chosen_color is None
        c = chars(game.state, only(game, BEAR))
        assert (c.power, c.toughness) == (2, 2)

    def test_it_sorts_a_mixed_board(self, builder):
        """The boundary: one colour up, the other two untouched, one filter."""
        game = board(builder, "U", extra=[BEAR, FLIER, GOBLIN])
        sizes = {
            def_id: (chars(game.state, only(game, def_id)).power)
            for def_id in (BEAR, FLIER, GOBLIN)
        }
        assert sizes[FLIER] == 3, "the blue one"
        assert sizes[BEAR] == 2 and sizes[GOBLIN] == 1, "a 2/2 Bear and a 1/1 Goblin"


class TestTheManaAbility:
    def test_it_offers_exactly_the_chosen_colour(self, builder):
        game = board(builder, "G")
        _, options = mana_ability(game, only(game, BANNER))
        assert options == ((0, 0, 0, 0, 1, 0),), "one option: {G}"

    def test_it_is_not_the_any_colour_card(self, builder):
        """The whole reason this is not a `choose_mode` of five `add_mana`s.

        A modal spelling would offer all five on every activation, which is
        Commander's Sphere — strictly better than the printed Banner, and no
        longer reading the same choice the anthem reads.
        """
        game = board(builder, "R")
        oid = only(game, BANNER)
        ability, options = mana_ability(game, oid)
        assert len(ability.mana_options) == 5, "the load-time superset is all five"
        assert options == ((0, 0, 0, 1, 0, 0),), "and the board narrows it to one"

    def test_before_a_choice_it_offers_nothing(self, builder):
        """Not five, and not colourless — nothing, so the solver skips it."""
        game = board(builder, None)
        _, options = mana_ability(game, only(game, BANNER))
        assert options == ()

    def test_tapping_it_adds_the_chosen_colour(self, builder):
        game = board(builder, "B")
        oid = only(game, BANNER)
        ability, _ = mana_ability(game, oid)
        activate_mana_ability(game.state, oid, ability.index, 0)
        assert game.state.players[0].mana_pool.to_dict() == {"B": 1}
        assert game.state.objects[oid].tapped

    def test_the_solver_pays_a_spell_with_it(self, builder):
        """The offer and the payment must agree, or a cast strands mid-payment.

        A tap-only mana ability is never an `ActionKind.ACTIVATE` row -- the
        payment solver taps it -- so the honest witness is a spell that becomes
        castable, and only in the colour that was chosen.
        """
        assert castable(spending(builder, "B"), DEATHTOUCHER), "{B} off a black choice"
        assert not castable(spending(builder, "G"), DEATHTOUCHER), "green pays no {B}"

    def test_before_a_choice_it_pays_for_nothing(self, builder):
        """Not five colours, and not colourless -- nothing at all."""
        assert not castable(spending(builder, None), DEATHTOUCHER)

    def test_it_names_no_colour_identity(self, builder):
        """"One mana of the chosen color" prints no mana symbol.

        The five-colour superset lives in `mana_options` so the ability is
        recognisable as a mana source at load time; reading it as identity would
        make a colourless artifact five-colour and illegal in most decks.
        """
        game = board(builder, "G")
        assert game.state.card(only(game, BANNER)).color_identity == frozenset()


class TestItIsPerObject:
    def test_two_banners_choose_independently(self, builder):
        game = board(builder, None, extra=[BANNER, BEAR])
        banners = [
            o for o in game.state.battlefield if game.state.objects[o].def_id == BANNER
        ]
        assert len(banners) == 2
        game.state.objects[banners[0]].chosen_color = "G"
        game.state.objects[banners[1]].chosen_color = "R"
        game.state.bump_chars()
        bear = next(
            o for o in game.state.battlefield if game.state.objects[o].def_id == BEAR
        )
        assert chars(game.state, bear).power == 3, "one Banner matches, one does not"

    def test_the_choice_is_cleared_when_it_leaves(self, builder):
        from commanderblitz.engine.zones import destroy

        game = board(builder, "G", extra=[BEAR])
        banner = only(game, BANNER)
        destroy(game.state, banner)
        assert game.state.objects[banner].chosen_color is None, (
            "a permanent that comes back is a new object and chooses again"
        )

    def test_the_anthem_wears_off_with_the_banner(self, builder):
        from commanderblitz.engine.zones import destroy

        game = board(builder, "G", extra=[BEAR])
        bear = only(game, BEAR)
        assert chars(game.state, bear).power == 3
        destroy(game.state, only(game, BANNER))
        assert chars(game.state, bear).power == 2


class TestTheProtectionReader:
    """Brave the Elements — the same leaf, on a spell rather than a permanent.

    The colour is chosen during resolution and written to the *spell's* object,
    which the very next op in the same effect list reads back. Nothing about the
    substitution changes; only where the source happens to be.
    """

    def cast_brave(self, builder, color_label: str):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", BEAR])
            .hand(0, [BRAVE])
            .library(0, ["forest"] * 10)
            .active(0)
            .max_turns(1)
            .build()
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == BRAVE
            )
        )
        for _ in range(20):
            decision = game.pending()
            if decision is None:
                break
            if decision.kind is DecisionKind.CHOOSE_MODE:
                choose(game, color_label)
                continue
            if decision.kind is DecisionKind.PRIORITY and game.state.stack:
                game.apply(
                    next(a for a in game.legal_actions() if a.kind is ActionKind.PASS)
                )
                continue
            break
        return game

    def test_it_grants_protection_from_the_chosen_colour(self, builder):
        game = self.cast_brave(builder, "Black")
        assert protection_from(game.state, only(game, BEAR)) == {"B"}

    def test_another_colour_is_not_granted(self, builder):
        game = self.cast_brave(builder, "White")
        assert "B" not in protection_from(game.state, only(game, BEAR))


class TestTheLoaderRefusesANearMiss:
    """The leaf's spelling cannot be checked against the board, so it is checked
    here. A near miss that fell through would read as "no colour chosen" for
    ever: an anthem that pumps nobody and a land that taps for nothing, loading
    perfectly cleanly."""

    base = {
        "id": "t_bad_color",
        "name": "Bad",
        "mana_cost": "{3}",
        "types": ["Artifact"],
    }

    def mana_card(self, mana):
        return compile_card(
            CardModel.model_validate(
                {
                    **self.base,
                    "abilities": [
                        {
                            "kind": "activated",
                            "text": "{T}: Add one mana of the chosen color.",
                            "is_mana_ability": True,
                            "cost": {"tap": True},
                            "effects": [{"op": "add_mana", "mana": mana}],
                        }
                    ],
                }
            )
        )

    def test_a_misspelled_leaf_is_refused(self):
        with pytest.raises(DslError, match="chosen_color_of"):
            self.mana_card({"chosen_color_of": "that_permanent"})

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(DslError, match="chosen_color_of"):
            self.mana_card({"chosen_colour_of": "self"})

    def test_the_good_spelling_compiles(self):
        card = self.mana_card({"chosen_color_of": "self"})
        assert card.abilities[0].mana_chosen_color
        assert len(card.abilities[0].mana_options) == 5

    def test_it_cannot_be_summed_inside_a_mode(self):
        """"Add one mana of the chosen color" is a whole ability or a whole mode.

        A mode beside fixed symbols is the Thriving lands' shape and is pinned in
        `test_thriving_lands.py`; summed with a symbol inside one mode, the
        chosen colour has no load-time tuple to join.
        """
        with pytest.raises(DslError, match="only effect"):
            compile_card(
                CardModel.model_validate(
                    {
                        **self.base,
                        "abilities": [
                            {
                                "kind": "activated",
                                "text": "{T}: Add {G} or one of the chosen color.",
                                "is_mana_ability": True,
                                "cost": {"tap": True},
                                "effects": [
                                    {
                                        "op": "choose_mode",
                                        "modes": [
                                            {
                                                "effects": [
                                                    {"op": "add_mana", "mana": "{G}"}
                                                ]
                                            },
                                            {
                                                "effects": [
                                                    {"op": "add_mana", "mana": "{G}"},
                                                    {
                                                        "op": "add_mana",
                                                        "mana": {
                                                            "chosen_color_of": "self"
                                                        },
                                                    },
                                                ]
                                            },
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                )
            )

    def test_a_misspelled_protection_leaf_is_refused(self):
        with pytest.raises(DslError, match="chosen_color_of"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_bad_protection",
                        "name": "Bad",
                        "mana_cost": "{W}",
                        "types": ["Instant"],
                        "spell_effects": [
                            {
                                "op": "grant_protection",
                                "from_colors": [{"chosen_color_of": "it"}],
                                "objects": {"controller": "you", "types": ["Creature"]},
                            }
                        ],
                    }
                )
            )
