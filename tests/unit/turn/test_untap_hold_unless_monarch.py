"""``skip_untap_step`` gated on the **held permanent's controller** being the monarch.

    Fall from Favor — "Enchanted creature doesn't untap during its controller's
    untap step unless that player is the monarch."

502.3 untaps the active player's permanents; a "doesn't untap" static removes
some of them from that set. Fall from Favor removes the enchanted creature
*unless* "that player" -- the creature's controller, the one whose untap step it
is -- holds the crown (721). The monarch is player state, a pipeline input on the
city's blessing's terms, so a static may ask about it; what no static condition
could do before was name **the affected permanent's** controller. Every player
spec in the static language is measured from the source, and the source is the
Aura, controlled by whoever cast it.

That is not a pedantic difference. Fall from Favor's own enters trigger makes the
*caster* the monarch, so `{"is_monarch": "you"}` -- the near miss -- reads "the
creature is free while the Aura's controller is the monarch": frozen exactly
while its controller has taken the crown back, and free while the caster keeps
it. The opposite card. `TestTheNearMiss` measures it on one board.

So the spec is `affected_controller`, answered per held permanent in
`player_statics.untap_held`. `_battlefield_statics` has no permanent in hand, so
`_static_active` defers a condition naming it rather than guessing; and since the
loader admits it only on `skip_untap_step`, nothing else can come to read the
deferral as "always on".

Witness: Fall from Favor (`fall_from_favor` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import _battlefield_statics
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import untap_held
from commanderblitz.engine.primitives import attach, become_monarch, untap_all
from tests.conftest import keywords, only_oid, static_probe

HOLD = "t_fall_from_favor_hold"  # the printed sentence: "unless that player is the monarch"
WRONG = "t_fall_from_favor_wrong_player"  # the near miss: "unless you are the monarch"
BEAR = "t_bear"
FLYER = "t_monarch_flyer"  # flying "as long as you're the monarch"


def position(builder, aura=HOLD):
    """``(game, bear)`` -- player 0's Aura on player 1's tapped Bear, no monarch yet."""
    game = (
        builder(players=2)
        .battlefield(0, [aura])
        .battlefield(1, [BEAR])
        .build(advance=False)
    )
    bear = only_oid(game, BEAR, 1)
    attach(game.state, only_oid(game, aura, 0), bear)
    game.state.objects[bear].tapped = True
    game.state.bump_chars()
    return game, bear


class TestTheHold:
    def test_held_while_nobody_is_the_monarch(self, builder):
        game, bear = position(builder)
        assert bear in untap_held(game.state, 1)

    def test_held_while_the_aura_s_controller_is_the_monarch(self, builder):
        """The position the card's own enters trigger makes."""
        game, bear = position(builder)
        become_monarch(game.state, 0)

        untap_all(game.state, 1)

        assert game.state.objects[bear].tapped

    def test_released_while_the_creature_s_controller_is_the_monarch(self, builder):
        """"Unless that player is the monarch" -- take the crown and it untaps."""
        game, bear = position(builder)
        become_monarch(game.state, 1)

        untap_all(game.state, 1)

        assert not game.state.objects[bear].tapped

    def test_held_again_once_the_crown_is_lost(self, builder):
        """Read at each untap step, not latched when the crown first moves."""
        game, bear = position(builder)
        become_monarch(game.state, 1)
        become_monarch(game.state, 0)

        assert bear in untap_held(game.state, 1)

    def test_released_when_the_aura_leaves(self, builder):
        game, _ = position(builder)
        game.state.battlefield.remove(only_oid(game, HOLD, 0))
        game.state.bump_chars()

        assert untap_held(game.state, 1) == set()


class TestTheNearMiss:
    """`{"is_monarch": "you"}` asks about the Aura's controller: the opposite card."""

    def test_you_frees_the_creature_when_the_caster_is_the_monarch(self, builder):
        game, bear = position(builder, aura=WRONG)
        become_monarch(game.state, 0)
        assert bear not in untap_held(game.state, 1)

    def test_you_holds_the_creature_when_its_controller_is_the_monarch(self, builder):
        game, bear = position(builder, aura=WRONG)
        become_monarch(game.state, 1)
        assert bear in untap_held(game.state, 1)


class TestTheDeferral:
    def test_the_static_wide_walk_reports_the_static_without_a_permanent(self, builder):
        """`_battlefield_statics` cannot answer `affected_controller`; it defers,
        and `untap_held` asks again per permanent."""
        game, _ = position(builder)
        become_monarch(game.state, 1)
        effects = [s.get("effect") for _, s in _battlefield_statics(game.state)]
        assert "skip_untap_step" in effects


class TestTheMonarchMovesTheCache:
    """A static's `is_monarch` is a pipeline input, so the cache follows the crown.

    Without the bump in `become_monarch` a layered static would keep answering
    for the old monarch until something unrelated invalidated `chars`.
    """

    def test_a_layered_static_follows_the_crown(self, builder):
        game = builder(players=2).battlefield(0, [FLYER]).build(advance=False)
        flyer = only_oid(game, FLYER, 0)
        assert "flying" not in keywords(game, flyer)

        become_monarch(game.state, 0)
        assert "flying" in keywords(game, flyer)

        become_monarch(game.state, 1)
        assert "flying" not in keywords(game, flyer)


def compile_static(static: dict):
    return compile_card(CardModel.model_validate(static_probe(static)))


class TestTheLoader:
    def test_accepts_the_printed_card(self):
        compile_static(
            {
                "effect": "skip_untap_step",
                "affects": {"attached": True},
                "condition": {"not": {"is_monarch": "affected_controller"}},
            }
        )

    @pytest.mark.parametrize("who", ["you", "opponent", "each_player"])
    def test_source_relative_specs_load_on_any_static(self, who):
        compile_static(
            {
                "effect": "buff",
                "affects": {"self_only": True},
                "power": {"const": 1},
                "toughness": {"const": 1},
                "condition": {"is_monarch": who},
            }
        )

    def test_refuses_the_affected_spec_where_nobody_asks_per_permanent(self):
        """An anthem asks its condition once per static: the spec would be
        deferred for ever and the buff would apply as if unprinted."""
        with pytest.raises(DslError, match="affected_controller"):
            compile_static(
                {
                    "effect": "buff",
                    "affects": {"self_only": True},
                    "power": {"const": 1},
                    "toughness": {"const": 1},
                    "condition": {"all": [{"is_monarch": "affected_controller"}]},
                }
            )

    @pytest.mark.parametrize("who", ["active_player", "monarch", True, 0])
    def test_refuses_an_unknown_player(self, who):
        with pytest.raises(DslError, match="is_monarch"):
            compile_static(
                {
                    "effect": "skip_untap_step",
                    "affects": {"attached": True},
                    "condition": {"is_monarch": who},
                }
            )
