"""Counter replacements that tell a cost from an effect.

    "If **an effect** would put one or more counters on a permanent you
    control, it puts twice that many of those counters on that permanent
    instead."                                            -- Doubling Season

`replace_counters` with ``counter_multiplier: 2`` was the documented shape for
this line, and it was wrong in the one place this Atraxa deck looks hardest:
`primitives.add_counters` is the funnel `costs.py` also calls to pay a positive
loyalty cost, so every +1 loyalty ability became +2. A cost is not an effect
(118.1, 602.2b), and Doubling Season's ruling says it outright: a planeswalker's
+1 ability puts one loyalty counter on it. ``effects_only`` is that word, and
`add_counters(..., as_cost=True)` is the placement it skips.

The other half is the planeswalker's **starting** loyalty, which the same
ruling doubles. 122.6 counts counters a permanent is given *as it enters* as
"put on" it, and they were written straight onto the object by
`zones._enter_battlefield` with no replacement consulted -- so High Score, the
shipped witness, let a creature that "enters with two +1/+1 counters" arrive
with two rather than three. `zones._entering_counters` now asks the same
statics, once, of everything the permanent enters with (see
`tests/unit/test_counters_as_it_enters.py`).

Without ``effects_only`` the static still reaches costs, which is what "if one
or more counters **would be put**" says (Hardened Scales, High Score): the
default is unchanged.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from tests.conftest import action_for_card, only_oid, pass_until

SEASON = "t_ceo_season"  # "if an effect would put", every kind, doubled
UNCHECKED = "t_rc_season"  # the same line without `effects_only`
SCALES = "t_rc_scales"  # High Score's "+1/+1 would be put … plus one"
WALKER = "t_ceo_walker"  # loyalty 3; +1: gain 2; +0: put a loyalty counter on it
HYDRA = "t_ceo_hydra"  # a 0/0 that enters with two +1/+1 counters
BRUTE = "t_riot_brute"  # 2/2 riot


def position(builder, board=(), hand=()):
    """Eight Forests, a main phase, and whatever else player 0 has."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 8 + list(board))
        .hand(0, list(hand))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def loyalty(game, card_id: str = WALKER) -> int:
    return game.state.objects[only_oid(game, card_id, 0)].counter("loyalty")


def activate(game, index: int) -> None:
    """Activate the walker's ``index``-th ability; the cost is paid at once."""
    oid = only_oid(game, WALKER, 0)
    actions = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == oid
    ]
    game.apply(actions[index])


def resolve_all(game) -> None:
    for _ in range(40):
        pending = game.pending()
        if pending is not None and pending.kind is DecisionKind.CHOOSE_MODE:
            # riot: take the counter half
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
            continue
        break
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def cast(game, card_id: str) -> int:
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    resolve_all(game)
    return only_oid(game, card_id, 0)


class TestACostIsNotAnEffect:
    def test_a_plus_one_puts_one_counter_on(self, builder):
        game = position(builder, board=[SEASON, WALKER])
        before = loyalty(game)
        activate(game, 0)
        assert loyalty(game) == before + 1

    def test_the_effect_of_the_same_walker_is_doubled(self, builder):
        """The control: on the same permanent, a counter put on by the
        ability's *effect* is doubled. +0, then one loyalty counter twice."""
        game = position(builder, board=[SEASON, WALKER])
        before = loyalty(game)
        activate(game, 1)
        resolve_all(game)
        assert loyalty(game) == before + 2

    def test_without_effects_only_the_cost_is_replaced(self, builder):
        """The default reaches costs -- "would be put" names no effect. This is
        the reading Hardened Scales and "if you would put" want, and why the
        key is opt-in."""
        game = position(builder, board=[UNCHECKED, WALKER])
        before = loyalty(game)
        activate(game, 0)
        assert loyalty(game) == before + 2

    def test_a_minus_cost_is_untouched(self, builder):
        """Removing counters was never a placement."""
        game = position(builder, board=[SEASON, "t_patient_walker"])
        oid = only_oid(game, "t_patient_walker", 0)
        before = game.state.objects[oid].counter("loyalty")
        game.apply(
            [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid][1]
        )
        assert game.state.objects[oid].counter("loyalty") == before - 3


class TestEnteringWithCountersIsAPlacement:
    """122.6: counters given as a permanent enters are "put on" it."""

    def test_a_planeswalker_enters_with_twice_its_loyalty(self, builder):
        game = position(builder, board=[SEASON], hand=[WALKER])
        cast(game, WALKER)
        assert loyalty(game) == 6

    def test_without_a_replacement_it_enters_with_its_printed_loyalty(self, builder):
        game = position(builder, hand=[WALKER])
        cast(game, WALKER)
        assert loyalty(game) == 3

    def test_high_score_adds_one_to_an_arriving_creature(self, builder):
        """The shipped card this was wrong for: "enters with two +1/+1
        counters" under a Hardened Scales is three."""
        game = position(builder, board=[SCALES], hand=[HYDRA])
        oid = cast(game, HYDRA)
        assert game.state.objects[oid].counter("+1/+1") == 3

    def test_riot_counter_is_replaced(self, builder):
        game = position(builder, board=[SEASON], hand=[BRUTE])
        oid = cast(game, BRUTE)
        assert game.state.objects[oid].counter("+1/+1") == 2

    def test_an_opponents_arrival_is_untouched(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [SEASON])
            .battlefield(1, ["forest"] * 8)
            .hand(1, [WALKER])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(1)
            .build(advance=False)
        )
        game._advance()
        game.apply(action_for_card(game, ActionKind.CAST, WALKER))
        pass_until(game, lambda g: not g.state.stack)
        oid = only_oid(game, WALKER, 1)
        assert game.state.objects[oid].counter("loyalty") == 3


class TestTheLoader:
    def _card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "If an effect would put one or more counters…",
                "mana_cost": "{G}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "If an effect would put one or more counters…",
                        **extra,
                    }
                ],
            }
        )

    def test_it_loads_on_replace_counters(self):
        compiled = compile_card(
            self._card(
                effect="replace_counters",
                counter_multiplier=2,
                effects_only=True,
                affects={"controller": "you"},
            )
        )
        assert compiled.abilities[0].static["effects_only"] is True

    def test_it_is_refused_on_another_static(self):
        with pytest.raises(DslError, match="effects_only"):
            compile_card(
                self._card(
                    effect="replace_draw", draw_multiplier=2, effects_only=True
                )
            )

