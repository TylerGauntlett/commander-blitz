"""Fuse — one spell made of two faces, which `card_of` cannot answer.

    "Test Wear {1}{R} — Instant. Destroy target creature.
     // Test Tear {W} — Instant. Destroy target enchantment.
     Fuse (You may cast one or both halves of this card from your hand.)"
     (702.102a)

`second_face` shipped adventure, aftermath and the halves of a split card, and
all three are one face *or* the other: `card_of` answers with exactly one, which
is why fuse was left open when they landed.

Fuse is the case where the answer is **both**, and the shape it needs already
existed — it is **splice**. A spliced card's effects run after its host's,
through the same `EffectContext`, and that shared context is what makes them one
spell rather than two. Fuse is that with the second effect list coming from the
card's own other half instead of from a different card in hand.

So nothing here reaches into `card_of` at all. A fused cast builds one card from
the two — name joined, costs added, target lists concatenated — and hands it to
the machinery that prices, targets and resolves any other spell:

| what | where it comes from |
|---|---|
| the price | `front.mana_cost.plus(back.mana_cost)` |
| the targets | both halves' lists, concatenated |
| the effects | both halves', through one context |
| the name in the log | "Test Wear // Test Tear" |

The one thing the halves may not do is **share a target id**, and the loader
refuses it: they resolve in one context, so one would silently answer for the
other and the spell would point somewhere nobody chose. That is the same
argument that stops a spliced card declaring targets at all — here the halves
may declare them, because they are the same card and their ids are visible
together at load time.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.loader.linking import link_faces
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from tests.conftest import only_oid, pass_until

MOUNTAIN = "mountain"
PLAINS = "plains"
WEAR = "t_fuse_left"    # {1}{R} destroy target creature, fuse
TEAR = "t_fuse_right"   # {W} destroy target enchantment
BEAR = "t_bear"
SHRINE = "t_anthem"     # a plain Enchantment to point the right half at


def position(builder, lands: int = 6, *, enchantment: bool = True):
    """Both colours on the board: {1}{R} for one half, {W} for the other."""
    board = [BEAR] + ([SHRINE] if enchantment else [])
    mana = [MOUNTAIN, PLAINS] * (lands // 2) + [MOUNTAIN] * (lands % 2)
    return (
        builder(players=2)
        .battlefield(0, mana)
        .battlefield(1, board)
        .hand(0, [WEAR])
        .library(0, [MOUNTAIN] * 20)
        .library(1, [MOUNTAIN] * 20)
        .build()
    )


def cast_lines(game) -> list[str]:
    return sorted({a.base_label or "" for a in game.legal_actions() if a.kind is ActionKind.CAST})


def cast_fused(game):
    action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.fused)
    game.apply(action)
    pass_until(game, lambda g: g.pending() is None or not g.state.stack)
    return action


class TestTheThreeLines:
    def test_all_three_are_offered(self, builder):
        game = position(builder)
        assert cast_lines(game) == [
            "Cast Test Tear",
            "Cast Test Wear",
            "Cast Test Wear // Test Tear (fused)",
        ]

    def test_the_fused_line_costs_both_halves(self, builder):
        """{1}{R} + {W} is three mana, and a Mountain and a Plains are two."""
        game = position(builder, lands=2)
        assert "Cast Test Wear // Test Tear (fused)" not in cast_lines(game)
        assert "Cast Test Wear" in cast_lines(game)

    def test_it_is_not_offered_without_a_target_for_each_half(self, builder):
        """Both halves' targets are chosen together, so both must exist."""
        game = position(builder, enchantment=False)
        assert cast_lines(game) == ["Cast Test Wear"]

    def test_the_fused_line_carries_both_targets(self, builder):
        game = position(builder)
        action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.fused)

        assert len(action.targets) == 2


class TestResolving:
    def test_both_halves_happen(self, builder):
        game = position(builder)
        bear, shrine = only_oid(game, BEAR, 1), only_oid(game, SHRINE, 1)

        cast_fused(game)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert game.state.objects[shrine].zone is Zone.GRAVEYARD

    def test_one_half_alone_does_only_its_own(self, builder):
        game = position(builder)
        bear, shrine = only_oid(game, BEAR, 1), only_oid(game, SHRINE, 1)

        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and "Test Wear" in (a.base_label or "") and not a.fused
        )
        game.apply(action)
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert game.state.objects[shrine].zone is Zone.BATTLEFIELD

    def test_it_is_one_card_in_one_graveyard(self, builder):
        """One spell, so one card -- not two halves going two places."""
        game = position(builder)
        cast_fused(game)

        mine = [game.state.objects[o].def_id for o in game.state.players[0].graveyard]
        assert mine.count(WEAR) == 1
        assert TEAR not in mine

    def test_the_log_names_both(self, builder):
        game = position(builder)
        cast_fused(game)

        cast = next(e for e in game.state.events if e.type == "spell_cast")
        assert cast.data["card"] == WEAR, "the card that was cast is the printed one"


class TestTheLoaderGuards:
    def _pool(self, front: dict, face: dict | None = None):
        cards = {}
        for model in (front, face):
            if model is None:
                continue
            card = compile_card(CardModel.model_validate(model))
            cards[card.id] = card
        link_faces(cards)
        return cards

    def _front(self, **extra) -> dict:
        base = {
            "id": "t_fuse_probe",
            "name": "Fuse Probe",
            "mana_cost": "{1}{R}",
            "types": ["Instant"],
            "fuse": True,
            "second_face": "t_fuse_probe_half",
            "spell_effects": [{"op": "draw", "player": "you"}],
        }
        base.update(extra)
        return base

    def _half(self, **extra) -> dict:
        base = {
            "id": "t_fuse_probe_half",
            "name": "Fuse Probe Half",
            "mana_cost": "{W}",
            "types": ["Instant"],
            "spell_effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
        }
        base.update(extra)
        return base

    def test_a_well_formed_fused_card_loads(self):
        self._pool(self._front(), self._half())

    def test_fuse_with_no_second_face_is_refused(self):
        with pytest.raises(DslError, match="'fuse' needs a 'second_face'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_fuse_probe",
                        "name": "Fuse Probe",
                        "mana_cost": "{1}{R}",
                        "types": ["Instant"],
                        "fuse": True,
                    }
                )
            )

    def test_fusing_a_graveyard_only_half_is_refused(self):
        """Aftermath's half may not be cast from hand, and fuse casts from hand."""
        with pytest.raises(DslError, match="'fuse' is cast from hand"):
            compile_card(
                CardModel.model_validate(self._front(second_face_zone="graveyard"))
            )

    def test_fuse_and_adventure_together_are_refused(self):
        with pytest.raises(DslError, match="both 'adventure' and 'fuse'"):
            compile_card(CardModel.model_validate(self._front(adventure=True)))

    def test_two_halves_naming_the_same_target_are_refused(self):
        """One context, so one would silently answer for the other."""
        target = {
            "id": "t1",
            "kind": "permanent",
            "count": 1,
            "selector": {"zone": "battlefield", "types": ["Creature"]},
        }
        with pytest.raises(DslError, match="both name target"):
            self._pool(
                self._front(
                    targets=[target],
                    spell_effects=[{"op": "destroy", "objects": {"target": "t1"}}],
                ),
                self._half(
                    targets=[target],
                    spell_effects=[{"op": "destroy", "objects": {"target": "t1"}}],
                ),
            )
