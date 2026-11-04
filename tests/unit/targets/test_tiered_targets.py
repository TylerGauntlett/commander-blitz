"""A target only one tier of a Tiered spell declares.

    "Tiered (Choose one additional cost.)
    • Cross-Slash — {0} — Destroy target tapped creature.
    • Blade Beam — {1} — Destroy any number of target tapped creatures with
      different controllers.
    • Omnislash — {3}{W} — Destroy all tapped creatures." -- Cloud's Limit Break.

Rule 702.183 makes the tier an additional cost, chosen at 601.2b, and 601.2c
declares the targets one step later -- so a cast already knows its tier when it
chooses what to point at, and each tier may own its targets. That is gift's and
kicker's argument again, keyed by `additional_cost_options` index.

What would be wrong without it is a different card on every tier. One shared
card-level spec would make Omnislash declare a target -- uncastable with no
tapped creature, and countered when that one creature untaps -- and could not be
exactly one for Cross-Slash and any number, one per controller, for Blade Beam.

The witness is Cloud's Limit Break (`t_limit_break` in
`tests/data/tiered_targets.cards.json`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.ops_stack import put_copy_on_stack
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import unplayable_reason
from tests.conftest import _default_answer

CARD = "t_limit_break"
BEAR = "grizzly_bears"
GIANT = "hill_giant"


def position(builder, *, tapped_mine=(), tapped_theirs=(BEAR,), untapped_theirs=(), players=3):
    """The card in hand on the caster's main phase, with mana for every tier."""
    game = (
        builder(players=players)
        .hand(0, [CARD, "lightning_bolt"])
        .battlefield(0, ["plains"] * 6 + ["mountain"])
        .battlefield(0, list(tapped_mine), tapped=True)
        .library(0, ["plains"] * 10)
        .turn(1)
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid in range(1, players):
        game = (
            game.battlefield(pid, ["island", *untapped_theirs])
            .battlefield(pid, list(tapped_theirs), tapped=True)
            .library(pid, ["island"] * 10)
        )
    game = game.build(advance=False)
    game.state.players[0].full_control = True
    game._advance()
    return game


def casts(game, tier=None):
    out = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == CARD
    ]
    return out if tier is None else [a for a in out if a.additional_choice == tier]


def resolve(game, action):
    game.apply(action)
    for _ in range(30):
        if not game.state.stack:
            break
        game.apply(_default_answer(game, game.pending()))
    return game


def creatures(game, def_id):
    return [
        oid
        for oid, obj in game.state.objects.items()
        if obj.def_id == def_id and obj.zone is Zone.BATTLEFIELD
    ]


def owned_by(game, oids):
    return sorted(game.state.objects[oid].controller for oid in oids)


class TestEachTierDeclaresItsOwnTargets:
    def test_cross_slash_points_at_exactly_one_tapped_creature(self, builder):
        game = position(builder, tapped_theirs=(BEAR, GIANT), players=2)
        lines = casts(game, 0)
        assert lines and all(len(a.targets) == 1 for a in lines)
        assert {a.targets[0].id for a in lines} == set(creatures(game, BEAR) + creatures(game, GIANT))

    def test_cross_slash_ignores_untapped_creatures(self, builder):
        game = position(builder, tapped_theirs=(), untapped_theirs=(BEAR,), players=2)
        assert not casts(game, 0)

    def test_blade_beam_takes_any_number_with_different_controllers(self, builder):
        game = position(builder, tapped_mine=(GIANT,), tapped_theirs=(BEAR,), players=3)
        lines = casts(game, 1)
        sizes = {len(a.targets) for a in lines}
        assert sizes == {0, 1, 2, 3}
        for action in lines:
            controllers = owned_by(game, [r.id for r in action.targets])
            assert len(controllers) == len(set(controllers))

    def test_blade_beam_never_pairs_two_of_one_controller(self, builder):
        game = position(builder, tapped_theirs=(BEAR, GIANT), players=2)
        assert {len(a.targets) for a in casts(game, 1)} == {0, 1}

    def test_omnislash_declares_nothing(self, builder):
        game = position(builder, players=2)
        lines = casts(game, 2)
        assert lines and all(a.targets == () for a in lines)


class TestATierWithNoLegalTargetIsNotOffered:
    def test_no_tapped_creature_leaves_blade_beam_and_omnislash(self, builder):
        """601.2c for Cross-Slash's required target; the other tiers ask none."""
        game = position(builder, tapped_theirs=(), players=2)
        assert {a.additional_choice for a in casts(game)} == {1, 2}
        assert unplayable_reason(game.state, 0, casts(game, 2)[0].source) is None


class TestResolution:
    def test_cross_slash_destroys_its_target(self, builder):
        game = position(builder, tapped_theirs=(BEAR, GIANT), players=2)
        bear = creatures(game, BEAR)[0]
        action = next(a for a in casts(game, 0) if a.targets[0].id == bear)
        resolve(game, action)
        assert not creatures(game, BEAR)
        assert creatures(game, GIANT)

    def test_blade_beam_destroys_each_chosen_target(self, builder):
        game = position(builder, tapped_mine=(GIANT,), tapped_theirs=(BEAR,), players=3)
        action = max(casts(game, 1), key=lambda a: len(a.targets))
        resolve(game, action)
        assert not creatures(game, BEAR) and not creatures(game, GIANT)

    def test_omnislash_destroys_every_tapped_creature_and_no_other(self, builder):
        game = position(builder, tapped_mine=(GIANT,), untapped_theirs=(BEAR,), players=2)
        resolve(game, casts(game, 2)[0])
        assert not creatures(game, GIANT)
        assert len(creatures(game, BEAR)) == 1


class TestACopyKeepsTheTier:
    def test_the_copy_resolves_the_same_tier_against_its_targets(self, builder):
        """707.10: a copy copies the additional cost paid, and so the tier and
        the target list its refs were declared under."""
        game = position(builder, tapped_theirs=(BEAR, GIANT), players=2)
        bear = creatures(game, BEAR)[0]
        game.apply(next(a for a in casts(game, 0) if a.targets[0].id == bear))
        original = game.state.stack[-1]
        assert original.cost_option == 0
        copy = put_copy_on_stack(game.state, 0, original)
        assert copy.cost_option == 0 and copy.targets == original.targets


def _model(**changes):
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "data" / "tiered_targets.cards.json"
    card = json.loads(path.read_text())["cards"][0]
    card.update(changes)
    return CardModel.model_validate(card)


class TestTheLoader:
    def test_each_tier_gets_its_own_list(self, registry):
        card = registry.get(CARD)
        assert card.targets == ()
        assert {n: [s.id for s in specs] for n, specs in card.cost_option_targets.items()} == {
            0: ["t1"],
            1: ["t2"],
            2: [],
        }

    def test_a_card_without_a_tiered_target_has_no_tier_lists(self, registry):
        assert registry.get("fire_magic").cost_option_targets == {}

    def test_a_tier_the_card_lacks_is_refused(self):
        model = _model()
        model.targets[0].cost_option = 3
        with pytest.raises(DslError, match="cost option 3 does not exist"):
            compile_card(model)

    def test_a_card_with_no_cost_options_is_refused(self):
        model = _model(additional_cost_options=[])
        with pytest.raises(DslError, match="offers 0"):
            compile_card(model)
