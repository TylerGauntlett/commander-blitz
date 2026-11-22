"""A token copy's exception can rename it: `copy_permanent`'s ``except_.name``.

    "At the beginning of combat on your turn, create a token that's a copy of
    target noncreature artifact you control, **except its name is Mishra's
    Warform** and it's a 4/4 Construct artifact creature in addition to its
    other types."                                    -- Mishra, Eminent One

707.9b: an exception to a copy effect becomes part of the copiable values, and
the name is one of them. So the token *is* Mishra's Warform from the moment it
exists -- the enters triggers that see it arrive, `selector.name`, the legend
rule (704.5j) and the serializer all read the new name, and a copy of the
token is a Mishra's Warform too.

The near miss is the `rename` op on the `as` binding after the copy. That is
an effect on a token that already entered under the copied artifact's name, so
anything its arrival runs sees the old name, and it is not a
copiable value, so a copy of the token comes back under the original's name.
`become_copy`'s ``except_name`` is the other near miss: it renames a permanent
copying something in place, and a token copy is not copying -- its ``def_id``
is the original's, and the exception lives in `copy_overrides`, read by
`GameState.card_of` through `live_copy_overrides`.

Witness: Mishra, Eminent One.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.effects import _validate_effect
from commanderblitz.engine import primitives, sba
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.serialize import card_view
from tests.conftest import only_oid, pt

RELIC = "t_glory_relic"  # Test Glory Relic, a vanilla noncreature artifact
LEGEND = "t_legend_artifact"  # Test Legendary Relic
OTHER = "t_rn_other"  # Test Unrenamed Artifact, for a later copy effect

WARFORM = "Mishra's Warform"
MISHRA = {
    "name": WARFORM,
    "power": 4,
    "toughness": 4,
    "add_types": ["Creature"],
    "add_subtypes": ["Construct"],
}


def board(builder, card: str = RELIC):
    """``(game, oid)``: the artifact a copy will be made of."""
    game = builder(players=2).battlefield(0, [card]).build()
    return game, only_oid(game, card)


def copy(game, oid: int, overrides: dict | None = MISHRA) -> int:
    """Resolve the token-copy sentence at ``oid`` and return the one token."""
    spec: dict = {"op": "copy_permanent", "objects": {"self_only": True}, "as": "made"}
    if overrides is not None:
        spec["except_"] = overrides
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    list(execute(ctx, [spec]))
    (token,) = ctx.bindings["made"]
    return token


def name_of(game, oid: int) -> str:
    return game.state.card_of(game.state.objects[oid]).name


class TestTheTokenIsRenamed:
    def test_it_answers_to_the_new_name(self, builder):
        game, relic = board(builder)
        token = copy(game, relic)
        assert name_of(game, token) == WARFORM
        assert card_view(game.state, token)["name"] == WARFORM, "the client shows it"

    def test_without_the_key_it_keeps_the_copied_name(self, builder):
        """The counterfactual: a plain copy copies the printed name."""
        game, relic = board(builder)
        token = copy(game, relic, {k: v for k, v in MISHRA.items() if k != "name"})
        assert name_of(game, token) == "Test Glory Relic"

    def test_the_original_keeps_its_name(self, builder):
        game, relic = board(builder)
        copy(game, relic)
        assert name_of(game, relic) == "Test Glory Relic"

    def test_the_rest_of_the_exception_still_applies(self, builder):
        """The whole of Mishra's line: a 4/4 Construct artifact creature."""
        game, relic = board(builder)
        token = copy(game, relic)
        token_chars = chars(game.state, token)
        assert pt(game, token) == (4, 4)
        assert {"Artifact", "Creature"} <= set(token_chars.types)
        assert "Construct" in token_chars.subtypes

    def test_a_name_selector_finds_the_token_only(self, builder):
        game, relic = board(builder)
        token = copy(game, relic)
        ctx = EffectContext(state=game.state, controller=0)
        assert resolve_pool(ctx, {"zone": "battlefield", "name": WARFORM}) == [token]
        assert resolve_pool(ctx, {"zone": "battlefield", "name": "Test Glory Relic"}) == [relic]


class TestItEntersUnderTheNewName:
    """The rename is a copiable value, on the token before it moves -- so
    everything its arrival runs (enters triggers, replacements) sees it."""

    def test_the_token_is_named_as_it_enters(self, builder, monkeypatch):
        game, relic = board(builder)
        seen: list[str] = []
        real = primitives.move_object

        def spy(state, oid, to, **kw):
            if to is Zone.BATTLEFIELD:
                seen.append(state.card_of(state.objects[oid]).name)
            return real(state, oid, to, **kw)

        monkeypatch.setattr(primitives, "move_object", spy)
        copy(game, relic)
        assert seen == [WARFORM]


class TestACopyOfTheTokenKeepsTheName:
    def test_a_token_copy_of_the_token_is_a_warform(self, builder):
        """707.9b: the exception is copiable, so a copy of the copy has it."""
        game, relic = board(builder)
        token = copy(game, relic)
        second = copy(game, token, None)
        assert name_of(game, second) == WARFORM
        assert pt(game, second) == (4, 4)

    def test_a_later_copy_effect_overwrites_it(self, builder):
        """613.2a: a copy effect applied to the token replaces every copiable
        value, the creating exception's name included."""
        game, relic = board(builder)
        token = copy(game, relic)
        obj = game.state.objects[token]
        obj.copying = OTHER
        game.state.bump_chars()
        assert name_of(game, token) == "Test Unrenamed Artifact"
        obj.copying = None
        game.state.bump_chars()
        assert name_of(game, token) == WARFORM, "the exception returns when the copy ends"


class TestTheLegendRuleReadsTheName:
    """704.5j groups legendary permanents by name -- the token's new one."""

    def test_a_renamed_copy_of_a_legend_survives_beside_it(self, builder):
        game, legend = board(builder, LEGEND)
        token = copy(game, legend, {"name": WARFORM})
        sba.run(game.state)
        assert legend in game.state.battlefield
        assert token in game.state.battlefield

    def test_an_unrenamed_copy_of_a_legend_is_binned(self, builder):
        """The counterfactual: one name under one controller, one survives."""
        game, legend = board(builder, LEGEND)
        token = copy(game, legend, None)
        sba.run(game.state)
        assert (legend in game.state.battlefield) != (token in game.state.battlefield)

    def test_two_renamed_copies_share_a_name(self, builder):
        game, legend = board(builder, LEGEND)
        first = copy(game, legend, {"name": WARFORM})
        second = copy(game, legend, {"name": WARFORM})
        sba.run(game.state)
        assert legend in game.state.battlefield
        assert first not in game.state.battlefield, "the newest Warform is kept"
        assert second in game.state.battlefield


class TestLoadTime:
    COPY = {"op": "copy_permanent", "objects": {"self_only": True}, "except_": MISHRA}

    def test_the_name_loads(self):
        _validate_effect(self.COPY, "test", {})

    @pytest.mark.parametrize("name", ["", "   ", 4, None, ["Mishra's Warform"]])
    def test_a_malformed_name_is_refused(self, name):
        bad = {**self.COPY, "except_": {**MISHRA, "name": name}}
        with pytest.raises(DslError, match=r"except_\.name"):
            _validate_effect(bad, "test", {})
