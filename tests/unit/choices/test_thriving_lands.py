""""Choose a color other than red. {T}: Add {R} or one mana of the chosen color."

Thriving Bluff is the witness, for the whole Thriving cycle of the Dance of the
Elements precon. It asks two things the Heraldic Banner idiom did not:

- **The choice excludes the printed colour.** `choose_color`'s
  `except_colors` drops letters from the offer before it is asked. Without it
  the Bluff could name red and tap for {R} or {R}: a mono-coloured land, which
  is a different card from the printed one.
- **The mana ability is a fixed symbol *or* the chosen colour.** A
  `choose_mode` of `add_mana {R}` and `add_mana {"chosen_color_of": "self"}`.
  The near miss an author reaches for is a `choose_mode` of five literal
  colours, which taps for any colour on every activation and is strictly
  better than the printed card. 605.1a keeps a mana ability decision-free, so
  `costs.mana_options_of` answers the chosen half off the permanent without
  asking, the same way it answers Heraldic Banner.

The boundary is the window before the choice: the enters trigger is still on
the stack, and the land offers {R} alone -- never all five, and never nothing.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability, mana_options_of
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError

BLUFF = "t_thriving_bluff"  # land: choose a colour other than red; {R} or the chosen colour
DEATHTOUCHER = "t_deathtoucher"  # {B} creature -- the one-mana black spell
BOLT = "t_bolt"  # {R} instant -- the one-mana red spell

RED = (0, 0, 0, 1, 0, 0)
BLACK = (0, 0, 1, 0, 0, 0)
GREEN = (0, 0, 0, 0, 1, 0)


def only(game, def_id: str) -> int:
    return next(o for o in game.state.battlefield if game.state.objects[o].def_id == def_id)


def position(builder, chosen: str | None, hand=()):
    """``(game, oid)``: an untapped Bluff with ``chosen`` already written on it."""
    b = (
        builder(players=2)
        .battlefield(0, [BLUFF])
        .hand(0, list(hand))
        .library(0, ["forest"] * 10)
        .active(0)
        .max_turns(1)
    )
    for oid in list(b.state.battlefield):
        if b.state.objects[oid].def_id == BLUFF:
            b.state.objects[oid].chosen_color = chosen
    b.state.bump_chars()
    game = b.build()
    return game, only(game, BLUFF)


def played(builder):
    """``(game, oid)``: the Bluff just played from hand, its choice pending."""
    game = (
        builder(players=2)
        .hand(0, [BLUFF])
        .library(0, ["forest"] * 10)
        .active(0)
        .max_turns(1)
        .build()
    )
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND and game.state.objects[a.source].def_id == BLUFF
        )
    )
    return game, only(game, BLUFF)


def answer(game, label: str) -> None:
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_MODE
    index = [o.label for o in decision.options].index(label)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )


def options(game, oid: int):
    ability = next(a for a in game.state.card(oid).abilities if a.is_mana_ability)
    return ability, mana_options_of(game.state, oid, ability)


def castable(game, def_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
        for a in game.legal_actions()
    )


class TestTheChoiceExcludesThePrintedColour:
    def test_red_is_not_offered(self, builder):
        game, _ = played(builder)
        labels = [o.label for o in game.pending().options]
        assert labels == ["White", "Blue", "Black", "Green"], "WUBRG order, red removed"

    def test_an_index_maps_into_the_narrowed_list(self, builder):
        """Index 3 is Green here, not Red: the mapping is over what was offered."""
        game, oid = played(builder)
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 3)
        )
        assert game.state.objects[oid].chosen_color == "G"

    def test_the_land_enters_tapped(self, builder):
        game, oid = played(builder)
        assert game.state.objects[oid].tapped

    def test_the_chosen_colour_is_recorded(self, builder):
        game, oid = played(builder)
        answer(game, "Black")
        assert game.state.objects[oid].chosen_color == "B"


class TestTheManaAbilityIsRedOrTheChosenColour:
    def test_it_offers_red_and_the_chosen_colour(self, builder):
        game, oid = position(builder, "G")
        _, offered = options(game, oid)
        assert offered == (RED, GREEN), "{R} first, then the chosen colour"

    def test_it_is_not_the_any_colour_card(self, builder):
        game, oid = position(builder, "B")
        _, offered = options(game, oid)
        assert len(offered) == 2
        assert GREEN not in offered

    def test_before_a_choice_it_offers_red_alone(self, builder):
        """The boundary: not five, and not nothing -- the {R} is printed."""
        game, oid = position(builder, None)
        _, offered = options(game, oid)
        assert offered == (RED,)

    def test_tapping_for_each_option(self, builder):
        for index, pool in ((0, {"R": 1}), (1, {"B": 1})):
            game, oid = position(builder, "B")
            ability, _ = options(game, oid)
            activate_mana_ability(game.state, oid, ability.index, 0, option_index=index)
            assert game.state.players[0].mana_pool.to_dict() == pool

    def test_the_solver_pays_with_the_chosen_colour(self, builder):
        game, _ = position(builder, "B", hand=[DEATHTOUCHER])
        assert castable(game, DEATHTOUCHER), "{B} off a black choice"
        game, _ = position(builder, "G", hand=[DEATHTOUCHER])
        assert not castable(game, DEATHTOUCHER), "a green choice pays no {B}"

    def test_the_solver_pays_with_red_before_a_choice(self, builder):
        game, _ = position(builder, None, hand=[DEATHTOUCHER, BOLT])
        assert not castable(game, DEATHTOUCHER), "no choice, no black"
        assert castable(game, BOLT), "but the printed {R} is always there"

    def test_its_identity_is_the_printed_symbol(self, builder):
        """The {R} is printed; the chosen colour is not (903.4)."""
        game, oid = position(builder, "G")
        assert game.state.card(oid).color_identity == frozenset({"R"})


def _land(choose: dict, mana_effects: list) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_bad_thriving",
                "name": "Bad",
                "types": ["Land"],
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "As it enters, choose a color.",
                        "trigger": {"event": "self_enters", "source": "self"},
                        "effects": [{"op": "choose_color", **choose}],
                    },
                    {
                        "kind": "activated",
                        "text": "{T}: Add mana.",
                        "is_mana_ability": True,
                        "cost": {"tap": True},
                        "effects": mana_effects,
                    },
                ],
            }
        )
    )


def _modes(*modes: list) -> list:
    return [{"op": "choose_mode", "modes": [{"effects": m} for m in modes]}]


FIXED_R = [{"op": "add_mana", "mana": "{R}"}]
CHOSEN = [{"op": "add_mana", "mana": {"chosen_color_of": "self"}}]


class TestTheLoaderRefusesANearMiss:
    def test_the_good_shape_compiles(self):
        _land({"except_colors": ["R"]}, _modes(FIXED_R, CHOSEN))

    @pytest.mark.parametrize(
        "excluded",
        [[], ["Red"], ["C"], ["R", "R"], ["W", "U", "B", "R", "G"], "R"],
    )
    def test_a_bad_exclusion_is_refused(self, excluded):
        with pytest.raises(DslError, match="except_colors"):
            _land({"except_colors": excluded}, _modes(FIXED_R, CHOSEN))

    def test_two_chosen_modes_are_refused(self):
        with pytest.raises(DslError, match="exactly one"):
            _land({}, _modes(FIXED_R, CHOSEN, CHOSEN))

    def test_a_chosen_mode_alone_is_refused(self):
        with pytest.raises(DslError, match="on its own"):
            _land({}, _modes(CHOSEN))

    def test_the_chosen_colour_summed_with_a_symbol_is_refused(self):
        with pytest.raises(DslError, match="summed"):
            _land({}, _modes(FIXED_R, FIXED_R + CHOSEN))

    def test_an_amount_is_refused(self):
        with pytest.raises(DslError, match="amount"):
            _land(
                {},
                _modes(
                    FIXED_R,
                    [{"op": "add_mana", "mana": {"chosen_color_of": "self"}, "amount": {"const": 2}}],
                ),
            )
