"""A target whose selector the kicked cast replaces.

    "Kicker {1}{B}. Exile target artifact or enchantment. **If this spell was
    kicked, exile target nonland permanent instead.**" -- Tear Asunder.

Legal because of the rules order: 601.2b announces kicker and 601.2c declares
the targets one step later, so the kicked cast already knows it is kicked when
it chooses what to point at. One target either way; only what it may be
changes.

What would be wrong without `selector_if_kicked` is a different card in either
direction. One spec with the wide selector lets the unkicked cast exile a
creature. Two specs with `count_if_kicked` sized 1/0 and 0/1 split the stored
ref by position, so the kicked ref is re-checked (608.2b) against the
artifact-or-enchantment selector and the kicked spell exiles nothing.
`targeting.kicked_targets` swaps the selector in for the kicked line's
declaration *and* its resolution, so the re-check reads the selector the target
was declared under.

The witness is Tear Asunder (`t_tear_asunder` in
`tests/data/kicked_selector.cards.json`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.actions import TargetRef
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import unplayable_reason
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, oids_of

TEAR = "t_tear_asunder"
BEAR = "grizzly_bears"
RING = "sol_ring"


def position(builder, theirs=(BEAR, RING), lands=("swamp", "swamp", "forest", "forest")):
    """Tear Asunder in hand on the caster's main phase, with a priority stop.

    The Bolt is never cast: `full_control` only holds a window open while
    something other than Pass is legal, and it always has a target.
    """
    game = (
        builder(players=2)
        .hand(0, [TEAR, "lightning_bolt"])
        .battlefield(0, [*lands, "mountain"])
        .library(0, ["swamp"] * 10)
        .battlefield(1, ["island", *theirs])
        .library(1, ["island"] * 10)
        .turn(1)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game.state.players[0].full_control = True
    game._advance()
    return game


def lines(game):
    """Every cast of Tear Asunder right now, split into unkicked and kicked."""
    casts = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == TEAR
    ]
    return [a for a in casts if not a.kicked], [a for a in casts if a.kicked]


def resolve(game, action):
    game.apply(action)
    for _ in range(30):
        if not game.state.stack:
            break
        game.apply(_default_answer(game, game.pending()))
    return game


def theirs(game, card):
    return oids_of(game, card, 1)[0]


def in_hand(game):
    return next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == TEAR)


class TestTheUnkickedCast:
    def test_it_targets_only_an_artifact_or_enchantment(self, builder):
        game = position(builder)
        plain, _kicked = lines(game)
        assert {a.targets for a in plain} == {(TargetRef.obj(theirs(game, RING)),)}

    def test_it_exiles_the_artifact(self, builder):
        game = position(builder)
        ring = theirs(game, RING)
        plain, _kicked = lines(game)
        resolve(game, plain[0])
        assert game.state.objects[ring].zone is Zone.EXILE
        assert game.state.objects[theirs(game, BEAR)].zone is Zone.BATTLEFIELD

    def test_no_artifact_means_no_unkicked_line(self, builder):
        """601.2c: the narrow target has no legal choice, so only the kicked
        cast is offered -- and the diagnostic agrees the card is playable."""
        game = position(builder, theirs=(BEAR,))
        plain, kicked = lines(game)
        assert plain == []
        assert kicked
        tear = in_hand(game)
        assert unplayable_reason(game.state, 0, tear) is None

    def test_without_the_kicker_mana_a_creature_is_no_target(self, builder):
        game = position(builder, theirs=(BEAR,), lands=("forest", "forest"))
        plain, kicked = lines(game)
        assert plain == [] and kicked == []
        tear = in_hand(game)
        assert unplayable_reason(game.state, 0, tear) == "targets"


class TestTheKickedCast:
    def test_it_targets_any_nonland_permanent(self, builder):
        game = position(builder)
        _plain, kicked = lines(game)
        assert {a.targets for a in kicked} == {
            (TargetRef.obj(theirs(game, BEAR)),),
            (TargetRef.obj(theirs(game, RING)),),
        }

    def test_never_a_land(self, builder):
        game = position(builder)
        island = theirs(game, "island")
        _plain, kicked = lines(game)
        assert all(TargetRef.obj(island) not in a.targets for a in kicked)

    def test_it_exiles_the_creature(self, builder):
        """608.2b re-checks the creature against the kicked selector, the one
        it was declared under, so the spell resolves rather than fizzling."""
        game = position(builder)
        bear = theirs(game, BEAR)
        _plain, kicked = lines(game)
        resolve(game, next(a for a in kicked if a.targets == (TargetRef.obj(bear),)))
        assert game.state.objects[bear].zone is Zone.EXILE
        assert game.state.objects[theirs(game, RING)].zone is Zone.BATTLEFIELD

    def test_a_target_that_leaves_fizzles_the_spell(self, builder):
        """608.2b: its only target gone, the spell is countered on resolution
        and goes to the graveyard, exiling nothing."""
        game = position(builder)
        bear = theirs(game, BEAR)
        ring = theirs(game, RING)
        tear = in_hand(game)
        _plain, kicked = lines(game)
        game.apply(next(a for a in kicked if a.targets == (TargetRef.obj(bear),)))
        move_object(game.state, bear, Zone.HAND)
        resolve(game, _default_answer(game, game.pending()))
        assert game.state.objects[bear].zone is Zone.HAND
        assert game.state.objects[ring].zone is Zone.BATTLEFIELD
        assert game.state.objects[tear].zone is Zone.GRAVEYARD


class TestTheLoader:
    def model(self, **extra) -> CardModel:
        base = {
            "id": "t_kicked_gate",
            "name": "Kicked Gate",
            "mana_cost": "{1}{G}",
            "types": ["Instant"],
            "kicker": "{1}{B}",
            "targets": [
                {
                    "id": "t1",
                    "kind": "permanent",
                    "selector": {"zone": "battlefield", "types": ["Artifact"]},
                    "selector_if_kicked": {"zone": "battlefield", "not_types": ["Land"]},
                }
            ],
            "spell_effects": [{"op": "exile", "objects": {"target": "t1"}}],
        }
        base.update(extra)
        return CardModel(**base)

    def target(self, **extra):
        spec = {
            "id": "t1",
            "kind": "permanent",
            "selector": {"zone": "battlefield", "types": ["Artifact"]},
            "selector_if_kicked": {"zone": "battlefield", "not_types": ["Land"]},
        }
        spec.update(extra)
        return spec

    def test_it_compiles_and_reads_the_kicker(self):
        """The selector is the kicked half, so the card is not half a kicker
        though no effect says `kicked`."""
        card = compile_card(self.model())
        assert card.targets[0].selector_if_kicked == {
            "zone": "battlefield",
            "not_types": ["Land"],
        }

    def test_refused_on_a_card_with_no_kicker(self):
        with pytest.raises(DslError, match="no 'kicker'"):
            compile_card(self.model(kicker=None))

    def test_refused_when_the_selector_is_malformed(self):
        """Checked as a selector of the spec's own kind, as `selector` is."""
        target = self.target(selector_if_kicked={"zone": "graveyard", "types": ["Creature"]})
        with pytest.raises(DslError, match="'permanent' target is on the battlefield"):
            compile_card(self.model(targets=[target]))

    def test_refused_with_an_unknown_selector_key(self):
        target = self.target(selector_if_kicked={"nonsense": True})
        with pytest.raises(DslError):
            compile_card(self.model(targets=[target]))

    def test_refused_when_it_repeats_the_selector(self):
        target = self.target(selector_if_kicked={"zone": "battlefield", "types": ["Artifact"]})
        with pytest.raises(DslError, match="over again"):
            compile_card(self.model(targets=[target]))

    def test_refused_when_it_reads_x(self):
        target = self.target(
            selector_if_kicked={"zone": "battlefield", "mana_value": {"op": "==", "value": "x"}}
        )
        with pytest.raises(DslError, match="sibling target or"):
            compile_card(self.model(targets=[target]))

    def test_refused_on_an_abilitys_targets(self):
        model = self.model(
            types=["Creature"],
            power=1,
            toughness=1,
            targets=[],
            spell_effects=[],
            abilities=[
                {
                    "kind": "triggered",
                    "trigger": {"event": "self_enters", "condition": {"kicked": True}},
                    "targets": [self.target()],
                    "effects": [{"op": "exile", "objects": {"target": "t1"}}],
                }
            ],
        )
        with pytest.raises(DslError, match="'selector_if_kicked' is about a cast"):
            compile_card(model)
