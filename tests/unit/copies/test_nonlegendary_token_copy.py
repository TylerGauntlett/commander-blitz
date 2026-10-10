"""A copy's exception can *strip* the Legendary supertype, not only grant it.

"Whenever another nontoken Dragon you control enters, create a token that's a
copy of it, except the token isn't legendary." -- Miirym, Sentinel Wyrm. Also
Helm of the Host, Kindred Charge and Moritte of the Frost: the clause is printed
whenever a card hands you a second copy of something that may well be legendary.

The rule is 707.9b beside 704.5j. 707.9b makes the exception part of the copy's
**copiable values** -- what the token *is*, not an effect on it -- and 704.5j
then puts all but one legendary permanent of a name into its controller's
graveyard. `_legend_rule` in `engine/sba.py` reads the *derived* supertypes, so
the exception is exactly what keeps the token off that list.

`except_` could already say "except it's legendary" (`add_supertypes`, Adagia).
Every supertype key was additive, so the opposite sentence was unsayable, and
the near-miss was not a weaker card but the *reverse* one: an unqualified copy
of a legendary Dragon carries the original's Legendary, the legend rule sees two
of one name under one controller, and Miirym's doubling ability visibly destroys
a creature every time it triggers. `remove_supertypes` is the set difference
beside `add_supertypes`' union.

The counterfactual under every claim here is the same copy with the key left
out, and `TestTheLegendRuleSparesIt` is the one that matters: a test that only
reads the supertype set passes on an implementation that still bins the token.

Witness: Azusa, Lost but Seeking -- Legendary Creature -- Human Monk, 1/2, whose
own static ability touches no characteristic, so what the copy keeps is legible.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.errors import DslError

AZUSA = "azusa_lost_but_seeking"
NOT_LEGENDARY = {"remove_supertypes": ["Legendary"]}


def board(builder, card: str = AZUSA):
    """``(game, oid)``: the legendary permanent a copy will be made of."""
    game = builder(players=2).battlefield(0, [card]).build()
    return game, game.state.battlefield[0]


def copy(game, oid: int, overrides: dict | None = None, amount: int = 1) -> list[int]:
    spec: dict = {"op": "copy_permanent", "objects": {"self_only": True}, "amount": amount}
    if overrides is not None:
        spec["except_"] = overrides
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    list(execute(ctx, [{**spec, "as": "made"}]))
    return list(ctx.bindings["made"])


class TestTheTokenIsNotLegendary:
    def test_the_supertype_is_gone(self, builder):
        game, azusa = board(builder)
        (token,) = copy(game, azusa, NOT_LEGENDARY)
        assert "Legendary" not in chars(game.state, token).supertypes

    def test_without_the_clause_the_copy_carries_it(self, builder):
        """The counterfactual: a plain copy copies the printed supertype."""
        game, azusa = board(builder)
        (token,) = copy(game, azusa)
        assert "Legendary" in chars(game.state, token).supertypes

    def test_the_original_stays_legendary(self, builder):
        """The exception is on the copy; the card it copied is untouched."""
        game, azusa = board(builder)
        copy(game, azusa, NOT_LEGENDARY)
        assert "Legendary" in chars(game.state, azusa).supertypes

    def test_a_legendary_selector_skips_it(self, builder):
        game, azusa = board(builder)
        copy(game, azusa, NOT_LEGENDARY)
        ctx = EffectContext(state=game.state, controller=0)
        found = resolve_pool(ctx, {"zone": "battlefield", "supertypes": ["Legendary"]})
        assert found == [azusa], "only the printed card answers to 'legendary'"


class TestTheLegendRuleSparesIt:
    """704.5j -- the whole reason the printed clause exists.

    The supertype set is not the claim. The claim is that both permanents are
    still on the battlefield after state-based actions, which is what a player
    sees and what an implementation that stripped the supertype from `chars`
    alone would still get wrong.
    """

    def test_the_token_and_its_original_both_survive(self, builder):
        game, azusa = board(builder)
        (token,) = copy(game, azusa, NOT_LEGENDARY)
        sba.run(game.state)
        assert token in game.state.battlefield, "the token is not legendary; nothing bins it"
        assert azusa in game.state.battlefield, "and it was never the original's rival"

    def test_the_token_survives_repeated_checks(self, builder):
        """Not a one-pass accident: state-based actions run constantly."""
        game, azusa = board(builder)
        (token,) = copy(game, azusa, NOT_LEGENDARY)
        for _ in range(3):
            sba.run(game.state)
        assert {token, azusa} <= set(game.state.battlefield)

    def test_many_such_tokens_all_survive(self, builder):
        """Miirym triggers again on the next Dragon. None of them is unique."""
        game, azusa = board(builder)
        tokens = copy(game, azusa, NOT_LEGENDARY, amount=3)
        sba.run(game.state)
        assert all(t in game.state.battlefield for t in tokens)
        assert azusa in game.state.battlefield

    def test_without_the_clause_the_legend_rule_bins_one(self, builder):
        """The card written without its exception, which is the opposite card.

        The engine keeps the most recent of a legendary name, so the ability
        meant to double a legendary Dragon destroys the Dragon instead.
        """
        game, azusa = board(builder)
        (token,) = copy(game, azusa)
        sba.run(game.state)
        survivors = {azusa, token} & set(game.state.battlefield)
        assert len(survivors) == 1, "two legendary Azusas under one controller"
        assert azusa not in game.state.battlefield, "and it is the original that died"

    def test_an_opponent_keeps_their_own_legendary_copy(self, builder):
        """704.5j is per player: stripping the supertype is not what saves this
        one, so the clause must not be read as a rule about the token's owner."""
        game = builder(players=2).battlefield(0, [AZUSA]).battlefield(1, [AZUSA]).build()
        mine, theirs = game.state.battlefield[0], game.state.battlefield[1]
        (token,) = copy(game, mine, NOT_LEGENDARY)
        sba.run(game.state)
        assert {mine, theirs, token} <= set(game.state.battlefield)


class TestTheRestOfTheCopyIsUntouched:
    """"Except the token isn't legendary" takes away one word and nothing else."""

    def test_it_keeps_the_name(self, builder):
        game, azusa = board(builder)
        (token,) = copy(game, azusa, NOT_LEGENDARY)
        state = game.state
        assert state.card_of(state.objects[token]).name == "Azusa, Lost but Seeking"

    def test_it_keeps_the_types_and_subtypes(self, builder):
        game, azusa = board(builder)
        (token,) = copy(game, azusa, NOT_LEGENDARY)
        c = chars(game.state, token)
        assert "Creature" in c.types
        assert {"Human", "Monk"} <= c.subtypes

    def test_it_keeps_the_printed_size(self, builder):
        game, azusa = board(builder)
        (token,) = copy(game, azusa, NOT_LEGENDARY)
        c = chars(game.state, token)
        assert (c.power, c.toughness) == (1, 2)

    def test_it_is_a_token(self, builder):
        game, azusa = board(builder)
        (token,) = copy(game, azusa, NOT_LEGENDARY)
        assert game.state.objects[token].is_token


class TestAddingAndRemovingTogether:
    """Moritte of the Frost -- "except it's snow and it isn't legendary"."""

    def test_the_added_supertype_lands_and_the_removed_one_goes(self, builder):
        game, azusa = board(builder)
        (token,) = copy(
            game, azusa, {"add_supertypes": ["Snow"], "remove_supertypes": ["Legendary"]}
        )
        supertypes = chars(game.state, token).supertypes
        assert "Snow" in supertypes
        assert "Legendary" not in supertypes

    def test_removing_a_supertype_the_card_never_had_is_a_no_op(self, builder):
        game, azusa = board(builder)
        (token,) = copy(game, azusa, {"remove_supertypes": ["Basic"]})
        assert chars(game.state, token).supertypes == {"Legendary"}


def _card(**overrides) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_nonlegendary_copy",
            "name": "Test Nonlegendary Copy",
            "oracle_text": (
                "Create a token that's a copy of target creature, "
                "except the token isn't legendary."
            ),
            "mana_cost": "{2}{U}",
            "types": ["Sorcery"],
            "targets": [
                {"id": "t1", "kind": "permanent", "count": 1, "selector": {"types": ["Creature"]}}
            ],
            "spell_effects": [
                {"op": "copy_permanent", "objects": {"target": "t1"}, "except_": overrides}
            ],
        }
    )


class TestTheLoaderChecksIt:
    def test_the_printed_shape_loads(self):
        compile_card(_card(**NOT_LEGENDARY), source="test")

    def test_an_unknown_supertype_is_refused(self):
        """"legendary" in lower case removes nothing and looks right."""
        with pytest.raises(DslError, match="unknown supertype"):
            compile_card(_card(remove_supertypes=["legendary"]), source="test")

    @pytest.mark.parametrize("empty", [[], "Legendary", None])
    def test_a_removal_of_nothing_is_refused(self, empty):
        with pytest.raises(DslError, match="non-empty list"):
            compile_card(_card(remove_supertypes=empty), source="test")

    def test_adding_and_removing_the_same_supertype_is_refused(self):
        """No printing says both, and the order would decide the card."""
        with pytest.raises(DslError, match="both added and removed"):
            compile_card(
                _card(add_supertypes=["Legendary"], remove_supertypes=["Legendary"]),
                source="test",
            )

    def test_adding_and_removing_different_supertypes_is_fine(self):
        compile_card(
            _card(add_supertypes=["Snow"], remove_supertypes=["Legendary"]), source="test"
        )

    def test_a_misspelled_key_is_still_refused(self):
        """The whole reason the key set is closed: a dropped exception is a
        copy that looks identical until the legend rule runs."""
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(_card(remove_supertype=["Legendary"]), source="test")
