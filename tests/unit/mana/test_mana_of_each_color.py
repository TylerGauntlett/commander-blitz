"""Vivid — "For each color among permanents you control, add one mana of that color."

    Bloom Tender — "Vivid — {T}: For each color among permanents you control,
     add one mana of that color."

Every other board-dependent mana ability the engine has produces **one** mana
whose colour is a question about the game: `reflecting` (what an opponent's
lands could make), `colors_of` (what an imprinted card is painted),
`in_commander_identity`, `mana_chosen_color`, and `split` (a free combination of
two named colours). All five hand `costs.mana_options_of` a *list of options*
and let the payment pick one.

Bloom Tender is not a choice at all. A board showing three colours taps it for
**three mana, one of each**, simultaneously and without asking — so this is the
one mana ability whose single option is a variable multi-symbol bundle read off
the board. `_each_color_among_options` returns exactly one option for that
reason: `legality._mana_option_indices` offers one chip per option, and a list
here would put a question in front of the player that the printed card never
asks (605.1a).

`colors_of` over the *identical selector* is the near miss and is a different,
strictly worse card — it is Mox Amber's "one mana of any color among permanents
you control". `t_vivid_mirror` ships it beside the real one so the difference is
demonstrated rather than claimed: on a three-colour board the mirror offers
three ways to make one mana and the Tender makes three mana.

`reflecting` over the same selector is the other near miss and asks a different
*question*, not a different shape: it polls each permanent's own mana
**abilities**. `t_vivid_reflect` beside a Forest and an Island offers {G} or {U}
— the colours those lands *tap for* — while the Tender beside the same two lands
adds only {G}, because a basic land is a colourless permanent. Two cards, same
board, three different answers.

Colourless is not a colour (105.1), so a board of nothing but artifacts adds
nothing and the ability is not a mana source at all. `t_vivid_golem` is the
colourless body that makes that position reachable — the printed Tender is green
and always sees at least itself.

`mana_options` still carries the five-colour superset at load time, for the same
reason `reflecting` needs one: an empty tuple there makes `solver_taps` and
`offerable_mana_ability` both decide this is not a mana source. Unlike every
other member of the family that superset is never *filtered* — the narrowing
builds a fresh tuple — so it must not reach colour identity either: Bloom Tender
prints {G}{G} and is legal in a mono-green deck (903.4).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability, mana_options_of, mana_sources
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, SYMBOLS
from tests.conftest import only_oid

TENDER = "t_vivid_tender"  # the capability
MIRROR = "t_vivid_mirror"  # the same selector under `colors_of` -- Mox Amber
REFLECT = "t_vivid_reflect"  # the same selector under `reflecting`
GOLEM = "t_vivid_golem"  # the capability on a colourless body
WHITE = "t_vivid_white_rock"
BLUE = "t_vivid_blue_rock"
GOLD = "t_vivid_gold_rock"  # {B}{R}
VOID = "t_vivid_void_rock"


def position(builder, board: list[str]):
    return (
        builder(players=2)
        .battlefield(0, board)
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .build()
    )


def options(game, oid: int) -> tuple[tuple[int, ...], ...]:
    """Every symbol tuple the Vivid ability offers on this board, right now."""
    return mana_options_of(game.state, oid, game.state.card(oid).abilities[0])


def produced(option) -> list[str]:
    """One option as the symbols it actually makes, e.g. ``["G", "U", "W"]``."""
    return sorted(SYMBOLS[i] for i, count in enumerate(option) for _ in range(count))


def board(builder, extras: list[str], source: str = TENDER):
    game = position(builder, [source, *extras])
    return game, only_oid(game, source)


class TestOneManaOfEachColorAtOnce:
    """The claim. Not one mana of a chosen colour — one of *every* colour, in a
    single option, so nothing is asked and nothing is left behind."""

    def test_a_three_colour_board_offers_a_single_option(self, builder):
        game, tender = board(builder, [WHITE, BLUE])
        assert len(options(game, tender)) == 1

    def test_that_option_is_one_mana_of_each_colour_present(self, builder):
        """Green off the Tender itself, white and blue off the two permanents
        beside it."""
        game, tender = board(builder, [WHITE, BLUE])
        assert produced(options(game, tender)[0]) == ["G", "U", "W"]

    def test_it_is_three_mana_and_not_one(self, builder):
        game, tender = board(builder, [WHITE, BLUE])
        assert sum(options(game, tender)[0]) == 3

    def test_a_gold_permanent_contributes_both_of_its_colours(self, builder):
        """"For each **color** among permanents" counts colours, not permanents:
        one {B}{R} enchantment is two colours off one card."""
        game, tender = board(builder, [GOLD])
        assert produced(options(game, tender)[0]) == ["B", "G", "R"]

    def test_a_five_colour_board_taps_for_five(self, builder):
        game, tender = board(builder, [WHITE, BLUE, GOLD])
        assert produced(options(game, tender)[0]) == ["B", "G", "R", "U", "W"]

    def test_a_colour_shown_twice_is_still_one_mana(self, builder):
        """The boundary `add_mana_per` gets wrong: it would add one {W} *per*
        white permanent. Two white permanents are one colour and one {W}."""
        game, tender = board(builder, [WHITE, WHITE])
        assert produced(options(game, tender)[0]) == ["G", "W"]


class TestAMonoGreenBoardTapsForExactlyOneGreen:
    """The degenerate end of the same rule, and the one a shipped Bloom Tender
    spends most of a game in."""

    def test_alone_it_sees_only_itself(self, builder):
        game, tender = board(builder, [])
        assert produced(options(game, tender)[0]) == ["G"]

    def test_and_a_colourless_permanent_adds_nothing_to_it(self, builder):
        """105.1: colourless is not a colour, so an artifact is not a sixth
        option — there is no `any_type` on this key."""
        game, tender = board(builder, [VOID])
        assert produced(options(game, tender)[0]) == ["G"]

    def test_a_basic_land_adds_nothing_either(self, builder):
        """A Forest is a *colourless permanent* that taps for green. This key
        reads the permanent's colours, not what it produces — which is the
        printed sentence and is exactly where `reflecting` disagrees."""
        game, tender = board(builder, ["forest", "island"])
        assert produced(options(game, tender)[0]) == ["G"]


class TestAColourlessBoardAddsNothing:
    """The empty answer is a real answer, the same one an unimprinted Chrome Mox
    and a colourless commander give."""

    def test_it_offers_no_option_at_all(self, builder):
        game, golem = board(builder, [VOID], source=GOLEM)
        assert options(game, golem) == ()

    def test_the_solver_plans_nothing_off_it(self, builder):
        game, golem = board(builder, [VOID], source=GOLEM)
        source = next((s for s in mana_sources(game.state, 0) if s.oid == golem), None)
        assert source is None or source.producible() == set()

    def test_tapping_it_refuses_rather_than_falling_back_on_the_superset(self, builder):
        """There is no option 0, so the payment refuses. Indexing the load-time
        five-colour superset here would be a strictly better card that taps for
        anything off an empty board."""
        game, golem = board(builder, [VOID], source=GOLEM)
        with pytest.raises(DslError):
            activate_mana_ability(game.state, golem, 0, 0)

    def test_one_coloured_permanent_switches_it_back_on(self, builder):
        game, golem = board(builder, [VOID, BLUE], source=GOLEM)
        assert produced(options(game, golem)[0]) == ["U"]


class TestTheSolverAndThePaymentAgree:
    """`mana_options_of` has two callers — `_sources_of` while planning and
    `activate_mana_ability` while paying — and the bundle must be the same in
    both, or a spell offered on three mana is billed one."""

    def test_the_source_advertises_the_whole_bundle(self, builder):
        game, tender = board(builder, [WHITE, BLUE])
        source = next(s for s in mana_sources(game.state, 0) if s.oid == tender)
        assert source.producible() == {SYMBOL_INDEX["W"], SYMBOL_INDEX["U"], SYMBOL_INDEX["G"]}

    def test_tapping_it_adds_three_mana(self, builder):
        game, tender = board(builder, [WHITE, BLUE])
        activate_mana_ability(game.state, tender, 0, 0)
        assert sum(game.state.players[0].mana_pool.amounts) == 3

    def test_tapping_it_adds_one_of_each_colour(self, builder):
        game, tender = board(builder, [WHITE, BLUE])
        activate_mana_ability(game.state, tender, 0, 0)
        assert produced(game.state.players[0].mana_pool.amounts) == ["G", "U", "W"]

    def test_a_mono_green_board_adds_exactly_one(self, builder):
        game, tender = board(builder, [])
        activate_mana_ability(game.state, tender, 0, 0)
        assert produced(game.state.players[0].mana_pool.amounts) == ["G"]


class TestTheNearMissesAreDifferentCards:
    """Same selector, same board, three different answers — which is why this is
    a sixth key rather than a spelling of one of the five."""

    def test_colors_of_offers_a_choice_of_one_where_this_makes_three(self, builder):
        """Mox Amber's sentence. Three single-symbol options, and the payment
        takes one of them."""
        game, mirror = board(builder, [WHITE, BLUE], source=MIRROR)
        assert sorted(produced(o)[0] for o in options(game, mirror)) == ["G", "U", "W"]
        assert [sum(o) for o in options(game, mirror)] == [1, 1, 1]

    def test_and_the_real_card_offers_one_option_worth_three(self, builder):
        game, tender = board(builder, [WHITE, BLUE])
        assert [sum(o) for o in options(game, tender)] == [3]

    def test_reflecting_asks_what_the_board_taps_for_not_what_colour_it_is(self, builder):
        """A Forest and an Island are colourless permanents that produce {G} and
        {U}. `reflecting` sees two colours here; the Tender sees none of them."""
        game, reflect = board(builder, ["forest", "island"], source=REFLECT)
        assert sorted(produced(o)[0] for o in options(game, reflect)) == ["G", "U"]

    def test_and_it_still_offers_only_one_mana(self, builder):
        game, reflect = board(builder, ["forest", "island"], source=REFLECT)
        assert all(sum(o) == 1 for o in options(game, reflect))

    def test_where_the_tender_beside_the_same_lands_adds_only_its_own_green(self, builder):
        game, tender = board(builder, ["forest", "island"])
        assert produced(options(game, tender)[0]) == ["G"]


def _creature(effect: dict) -> dict:
    return {
        "id": "t_each_color_probe",
        "name": "Probe",
        "mana_cost": "{G}{G}",
        "types": ["Creature"],
        "subtypes": ["Druid"],
        "power": 1,
        "toughness": 1,
        "colors": ["G"],
        "abilities": [
            {
                "kind": "activated",
                "text": "Vivid — {T}: For each color among permanents you control, "
                "add one mana of that color.",
                "is_mana_ability": True,
                "cost": {"tap": True},
                "effects": [effect],
            }
        ],
    }


YOURS = {"zone": "battlefield", "controller": "you"}


class TestTheLoaderPinsTheSuperset:
    def test_it_records_the_selector(self):
        card = compile_card(
            CardModel.model_validate(_creature({"op": "add_mana", "each_color_among": YOURS}))
        )
        assert card.abilities[0].mana_each_color_among == YOURS

    def test_it_advertises_five_colours_until_activation(self):
        """Without a non-empty `mana_options` at load time, `solver_taps` and
        `offerable_mana_ability` both decide this is not a mana source and the
        ability is never offered whatever the board shows."""
        card = compile_card(
            CardModel.model_validate(_creature({"op": "add_mana", "each_color_among": YOURS}))
        )
        assert len(card.abilities[0].mana_options) == 5

    def test_the_superset_is_not_colour_identity(self):
        """903.4 is deck construction. Bloom Tender prints {G}{G} and no other
        symbol; a derived five-colour identity would bar it from the mono-green
        decks it is actually played in."""
        card = compile_card(
            CardModel.model_validate(_creature({"op": "add_mana", "each_color_among": YOURS}))
        )
        assert card.color_identity == frozenset({"G"})


class TestTheLoaderRefusesTheAmbiguousSpellings:
    def test_each_color_among_beside_a_fixed_mana_string_is_refused(self):
        """Two answers to one question, and only the `mana` string would be read
        — a Tender that taps for {G} whatever the board showed."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    _creature({"op": "add_mana", "mana": "{G}", "each_color_among": YOURS})
                )
            )

    def test_each_color_among_beside_colors_of_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    _creature(
                        {"op": "add_mana", "colors_of": YOURS, "each_color_among": YOURS}
                    )
                )
            )

    def test_each_color_among_beside_reflecting_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    _creature(
                        {"op": "add_mana", "reflecting": YOURS, "each_color_among": YOURS}
                    )
                )
            )

    def test_an_amount_is_refused_rather_than_silently_doubling_the_bundle(self):
        """`mana_produced` would multiply the whole bundle, so this is not a
        dropped key — it is a card nobody printed."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    {
                        **_creature(
                            {
                                "op": "add_mana",
                                "each_color_among": YOURS,
                                "amount": {"const": 2},
                            }
                        )
                    }
                )
            )

    def test_any_type_is_refused_because_colourless_is_not_a_colour(self):
        """106.1b's sixth type of mana widens `reflecting` and nothing else;
        "for each **color**" is colours, and an artifact contributes none."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    _creature(
                        {"op": "add_mana", "each_color_among": YOURS, "any_type": True}
                    )
                )
            )

    def test_the_key_is_refused_on_any_other_op(self):
        """It is read only by the mana fold, so on anything else it would load,
        be ignored, and leave the printed line doing nothing."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_each_color_probe2",
                        "name": "Probe Two",
                        "mana_cost": "{G}",
                        "types": ["Instant"],
                        "colors": ["G"],
                        "spell_effects": [
                            {"op": "draw", "amount": {"const": 1}, "each_color_among": YOURS}
                        ],
                    }
                )
            )

    def test_a_rider_cannot_join_the_bundle(self):
        """A second `add_mana` beside this one would have to be summed with a
        tuple that is not known until activation, so the fold refuses it rather
        than picking one of the two."""
        card = _creature({"op": "add_mana", "each_color_among": YOURS})
        card["abilities"][0]["effects"].append({"op": "add_mana", "mana": "{C}"})
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(card))
