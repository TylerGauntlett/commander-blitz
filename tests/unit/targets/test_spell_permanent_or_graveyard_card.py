""""The owner of target **spell, nonland permanent, or card in a graveyard**
puts it on their choice of the top or bottom of their library."

Endless Detour. One instance of the word "target" whose pool spans three zones:
`spell_or_permanent` (Sink into Stupor) with a graveyard half. Two specs -- a
`spell_or_permanent` and a `card_in_graveyard` -- would be a card that targets
twice, castable only with a legal choice of each and fizzling if either became
illegal (608.2b); the printed card is castable at any one of the three alone.

"Nonland" narrows only the permanent: a land card in a graveyard is legal, so it
is `permanent_selector`, and the graveyard half walks **every** graveyard.

608.2b re-checks a chosen object against the half for the zone it is in as the
spell resolves, so one that has left for a zone no half names is no target.

The effect half: `put_on_top` reads `objects` through `ctx.target_oids`, which
never reaches a stack ref, so the spell half is tucked off the stack by the op
itself -- the owner choosing top or bottom, as for a permanent.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

DETOUR = "t_detour"
BEAR = "t_bear"
BAIT = "t_plain_instant"


def position(builder, *, their_board=(), their_yard=(), their_hand=(), my_yard=()):
    game = (
        builder(players=2)
        .battlefield(0, ["forest", "plains", "island"])
        .graveyard(0, list(my_yard))
        .battlefield(1, [*their_board, "plains", "plains"])
        .graveyard(1, list(their_yard))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [DETOUR])
        .hand(1, list(their_hand))
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def detour_casts(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == DETOUR and a.targets
    ]


def detour_targets(game):
    return [a.targets[0] for a in detour_casts(game)]


def cast_at(game, ref_id, ref_kind="object"):
    game.apply(
        next(
            a
            for a in detour_casts(game)
            if a.targets[0].id == ref_id and a.targets[0].kind == ref_kind
        )
    )


def resolve(game, *, top: bool):
    """Pass until the stack empties, answering the owner's top-or-bottom."""
    for _ in range(200):
        decision = game.pending()
        if decision.kind is DecisionKind.MAY:
            assert decision.player == 1, "the **owner** chooses"
            wanted = ActionKind.YES if top else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is wanted))
        elif not game.state.stack:
            return
        else:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    raise AssertionError("the stack never emptied")


def assert_tucked(game, oid, *, top):
    """On the bottom of seat 1's library, or on top -- where the turn the engine
    passes into has seat 1 draw it as the first card."""
    if not top:
        assert game.state.players[1].library[-1] == oid
        return
    draws = [e.source for e in game.state.events if e.type == "draw" and e.player == 1]
    assert draws and draws[0] == oid, "drawn as the top card"


def cast_bait_then_wait(game):
    """Seat 1 casts the bait; stop when seat 0 can answer it."""
    pass_until(
        game,
        lambda g: any(
            a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == BAIT
            for a in g.legal_actions()
        ),
    )
    bait = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BAIT
    )
    game.apply(bait)
    pass_until(game, lambda g: bool(detour_casts(g)))
    return bait.source


def only(game, def_id, zone):
    found = [o.oid for o in game.state.objects.values() if o.def_id == def_id and o.zone is zone]
    assert len(found) == 1, found
    return found[0]


class TestEachHalfAlone:
    def test_a_permanent(self, builder):
        game = position(builder, their_board=[BEAR])
        refs = detour_targets(game)
        assert refs and all(r.kind == "object" for r in refs)

    def test_a_card_in_a_graveyard(self, builder):
        game = position(builder, their_yard=[BEAR])
        bear = only(game, BEAR, Zone.GRAVEYARD)
        assert bear in {r.id for r in detour_targets(game)}

    def test_a_spell(self, builder):
        game = position(builder, their_hand=[BAIT])
        cast_bait_then_wait(game)
        assert {r.kind for r in detour_targets(game)} >= {"stack"}


class TestTheHalvesTogether:
    def test_the_pool_spans_all_three_zones(self, builder):
        game = position(builder, their_board=[BEAR], their_yard=[BEAR], their_hand=[BAIT])
        cast_bait_then_wait(game)
        refs = detour_targets(game)
        zones = {
            "stack" if r.kind == "stack" else game.state.objects[r.id].zone for r in refs
        }
        assert zones == {"stack", Zone.BATTLEFIELD, Zone.GRAVEYARD}


class TestNonlandNarrowsOnlyThePermanent:
    def test_a_land_on_the_battlefield_is_not_offered(self, builder):
        game = position(builder, their_board=[BEAR])
        lands = {o.oid for o in game.state.battlefield_objects(1) if o.def_id == "plains"}
        assert lands and not lands & {r.id for r in detour_targets(game)}

    def test_a_land_card_in_a_graveyard_is(self, builder):
        game = position(builder, their_yard=["plains"])
        yard = only(game, "plains", Zone.GRAVEYARD)
        assert yard in {r.id for r in detour_targets(game)}

    def test_every_graveyard_is_walked(self, builder):
        game = position(builder, their_yard=[BEAR], my_yard=["island"])
        offered = {r.id for r in detour_targets(game)}
        assert only(game, BEAR, Zone.GRAVEYARD) in offered
        assert only(game, "island", Zone.GRAVEYARD) in offered


class TestItTucksEachOne:
    @pytest.mark.parametrize("top", [True, False])
    def test_a_permanent_goes_where_its_owner_says(self, builder, top):
        game = position(builder, their_board=[BEAR])
        bear = only(game, BEAR, Zone.BATTLEFIELD)
        cast_at(game, bear)
        resolve(game, top=top)
        assert_tucked(game, bear, top=top)

    @pytest.mark.parametrize("top", [True, False])
    def test_a_graveyard_card_goes_where_its_owner_says(self, builder, top):
        game = position(builder, their_yard=[BEAR])
        bear = only(game, BEAR, Zone.GRAVEYARD)
        cast_at(game, bear)
        resolve(game, top=top)
        assert_tucked(game, bear, top=top)

    @pytest.mark.parametrize("top", [True, False])
    def test_a_spell_leaves_the_stack_for_its_owners_library(self, builder, top):
        game = position(builder, their_hand=[BAIT])
        bait = cast_bait_then_wait(game)
        sid = game.state.objects[bait].stack_id
        cast_at(game, sid, "stack")
        resolve(game, top=top)
        assert_tucked(game, bait, top=top)
        assert game.state.players[1].life == 40, "tucked, never resolved"


class TestTheRecheck:
    def test_a_permanent_bounced_in_response_is_no_target(self, builder):
        game = position(builder, their_board=[BEAR])
        bear = only(game, BEAR, Zone.BATTLEFIELD)
        cast_at(game, bear)
        move_object(game.state, bear, Zone.HAND)
        resolve(game, top=True)
        assert game.state.objects[bear].zone is Zone.HAND


def _load(target, effects):
    compile_card(CardModel.model_validate({
        "id": "t_probe",
        "name": "Probe",
        "oracle_text": "x",
        "mana_cost": "{U}",
        "types": ["Instant"],
        "targets": [target],
        "spell_effects": effects,
    }), source="test")


TUCK = [{"op": "put_on_top", "objects": {"target": "t1"}}]


class TestLoadTimeRefusals:
    def test_a_zone_is_refused(self):
        target = {
            "id": "t1",
            "kind": "spell_permanent_or_graveyard_card",
            "selector": {"zone": "graveyard"},
        }
        with pytest.raises(DslError, match="takes no 'zone'"):
            _load(target, TUCK)

    def test_an_op_that_cannot_reach_the_spell_is_refused(self):
        target = {"id": "t1", "kind": "spell_permanent_or_graveyard_card"}
        with pytest.raises(DslError, match="never reach the spell half"):
            _load(target, [{"op": "exile", "objects": {"target": "t1"}}])

    def test_the_tuck_loads(self):
        target = {
            "id": "t1",
            "kind": "spell_permanent_or_graveyard_card",
            "permanent_selector": {"not_types": ["Land"]},
        }
        _load(target, TUCK)
