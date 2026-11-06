"""A token copy's exception can give it keywords: "…except it … has haste".

"Create a token that's a copy of target permanent you control, except it's a
5/5 artifact creature in addition to its other types **and has haste**." --
Saheeli, Radiant Creator. Also Twinflame ("except it has haste") and Will of the
Temur ("except it's a 4/4 Dragon creature **with flying** in addition to its
other types").

The rule is 707.9b: the exception becomes part of the token's **copiable
values**. The keyword is what the token is, not an effect on it, so it is there
before layer 6 (a "loses all abilities" effect takes it away), and a copy of the
token copies it -- the difference between this and the near miss the pool used
to write, a `grant_keyword` on the `as` binding, which a copy of the token would
not inherit.

`copy_permanent`'s ``except_`` takes ``add_keywords``; it lands on the token's
`copy_overrides`, which `characteristics._compute` reads beside the printed
keywords.

Witness: Grizzly Bears, a vanilla 2/2, so every keyword the token has came from
the exception.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.combat import can_attack
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from tests.conftest import keywords, pt

BEARS = "grizzly_bears"
HASTE = {"add_keywords": ["haste"]}
SAHEELI = {"power": 5, "toughness": 5, "add_types": ["Artifact", "Creature"], **HASTE}


def board(builder, card: str = BEARS):
    """``(game, oid)``: player 0's permanent a copy will be made of."""
    game = builder(players=2).battlefield(0, [card]).build()
    return game, game.state.battlefield[0]


def copy(game, oid: int, overrides: dict | None = None) -> int:
    spec: dict = {"op": "copy_permanent", "objects": {"self_only": True}, "as": "made"}
    if overrides is not None:
        spec["except_"] = overrides
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    list(execute(ctx, [spec]))
    (token,) = ctx.bindings["made"]
    return token


def is_active(game) -> bool:
    return game.state.active_player == 0


class TestTheTokenHasTheKeyword:
    def test_haste(self, builder):
        game, bears = board(builder)
        token = copy(game, bears, HASTE)
        assert "haste" in keywords(game, token)

    def test_without_the_clause_it_has_none(self, builder):
        """The counterfactual: a plain copy of a vanilla creature."""
        game, bears = board(builder)
        token = copy(game, bears)
        assert keywords(game, token) == set()

    def test_the_original_is_untouched(self, builder):
        game, bears = board(builder)
        copy(game, bears, HASTE)
        assert keywords(game, bears) == set()

    def test_the_token_can_attack_the_turn_it_is_made(self, builder):
        """What haste is for: the token entered this turn and attacks anyway."""
        game, bears = board(builder)
        assert is_active(game)
        hasty = copy(game, bears, HASTE)
        plain = copy(game, bears)
        assert can_attack(game.state, hasty)
        assert not can_attack(game.state, plain), "summoning sick without the exception"

    def test_saheelis_whole_exception(self, builder):
        """5/5, an artifact creature in addition to its other types, with haste."""
        game, bears = board(builder)
        token = copy(game, bears, SAHEELI)
        c = chars(game.state, token)
        assert pt(game, token) == (5, 5)
        assert {"Artifact", "Creature"} <= c.types
        assert "Bear" in c.subtypes
        assert "haste" in c.keywords

    def test_several_keywords(self, builder):
        game, bears = board(builder)
        token = copy(game, bears, {"add_keywords": ["flying", "haste"]})
        assert {"flying", "haste"} <= keywords(game, token)


class TestItIsACopiableValue:
    """707.9b: the exception is part of what the token is."""

    def test_a_copy_of_the_token_has_it_too(self, builder):
        game, bears = board(builder)
        token = copy(game, bears, HASTE)
        second = copy(game, token)
        assert "haste" in keywords(game, second)

    def test_a_copy_with_its_own_keyword_keeps_both(self, builder):
        """Will of the Temur copying a Twinflame token: haste and flying."""
        game, bears = board(builder)
        token = copy(game, bears, HASTE)
        second = copy(game, token, {"add_keywords": ["flying"]})
        assert {"flying", "haste"} <= keywords(game, second)

    def test_losing_all_abilities_takes_it(self, builder):
        """Layer 6 removes what layer 1 put there, as for a printed keyword."""
        game, bears = board(builder)
        token = copy(game, bears, HASTE)
        ctx = EffectContext(state=game.state, controller=0, source_oid=bears)
        list(execute(ctx, [{"op": "lose_all_abilities", "objects": {"oid": token}}]))
        assert "haste" not in keywords(game, token)


def _card(overrides) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_hasty_copy",
            "name": "Test Hasty Copy",
            "oracle_text": "Create a token that's a copy of target creature, except it has haste.",
            "mana_cost": "{2}{R}",
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
        compile_card(_card(SAHEELI), source="test")

    def test_an_unknown_keyword_is_refused(self):
        """"Haste" capitalised grants nothing and looks right."""
        with pytest.raises(DslError, match="unknown keyword"):
            compile_card(_card({"add_keywords": ["Haste"]}), source="test")

    @pytest.mark.parametrize("empty", [[], "haste", None])
    def test_a_grant_of_nothing_is_refused(self, empty):
        with pytest.raises(DslError, match="non-empty list"):
            compile_card(_card({"add_keywords": empty}), source="test")

    def test_a_numbered_keyword_is_refused(self):
        """Toxic N has nowhere to carry its N."""
        with pytest.raises(DslError, match="carries a number"):
            compile_card(_card({"add_keywords": ["toxic"]}), source="test")
