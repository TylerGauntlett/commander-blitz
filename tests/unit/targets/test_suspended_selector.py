"""The `suspended` selector key -- "a suspended card you own".

    Whenever Amy Pond deals combat damage to a player, choose a suspended card
    you own and remove that many time counters from it.
                                                            -- Amy Pond

    …put a time counter on it for each suspended card you own…
                                                            -- Rose Tyler

702.62b: "a card is suspended if it's in exile, has suspend, and has a time
counter on it." Three conditions, and the selector language could say only two
of them: `{"zone": "exile", "has_counters": "time"}` is the near miss, and it
also takes a card exiled with time counters that nothing suspended -- which the
upkeep never ticks and which is never cast -- so Rose Tyler would grow off a
card that is not waiting for anything. "Has suspend" is the `suspended_by` mark
the suspend action and `suspend.make_suspended` write, and `GameObject.suspended`
is the one reading of all three, shared with `suspend.suspended_cards`.

The boundaries pinned here: the mark without a time counter is not suspended
(the last one came off), time counters without the mark are not, and a card on
the battlefield never is, whatever it carries. The key names its own zone, so a
pool, a value `count` and a `card_in_exile` target all reach exile without
writing one, and a target re-check (608.2b) asks the same question in the same
zone as the offer did.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.carddef import TargetSpec
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import matches, resolve_pool
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import TIME_COUNTER
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.suspend import make_suspended, suspended_cards
from commanderblitz.engine.targeting import candidates, still_legal
from commanderblitz.engine.zones import exile

BEAR = "grizzly_bears"

SUSPENDED = {"suspended": True}
TARGET = TargetSpec(id="t1", kind="card_in_exile", selector=SUSPENDED)


def position(builder, *, how: str):
    """Seat 0's Grizzly Bears, put where ``how`` says; returns ``(game, oid)``.

    ``suspended`` -- suspended with two time counters (702.62b);
    ``emptied`` -- suspended, then its last time counter removed;
    ``exiled`` -- exiled with two time counters by nothing that suspends;
    ``battlefield`` -- on the battlefield with two time counters and the mark.
    """
    b = builder(players=2)
    b = b.battlefield(0, [BEAR], counters={TIME_COUNTER: 2}) if how == "battlefield" else b.hand(0, [BEAR])
    game = b.build(advance=False)
    state = game.state
    if how == "battlefield":
        oid = next(o.oid for o in state.battlefield_objects(0) if o.def_id == BEAR)
        state.objects[oid].suspended_by = 0
        return game, oid
    oid = state.players[0].hand[0]
    if how == "exiled":
        exile(state, oid, cause="test")
        state.objects[oid].add_counter(TIME_COUNTER, 2)
    else:
        assert make_suspended(state, oid, 2)
        if how == "emptied":
            state.objects[oid].remove_counter(TIME_COUNTER, 2)
    return game, oid


def ctx_for(game, pid: int = 0) -> EffectContext:
    return EffectContext(state=game.state, controller=pid)


class TestASuspendedCardMatches:
    def test_the_pool_finds_it_without_naming_a_zone(self, builder):
        game, oid = position(builder, how="suspended")
        assert resolve_pool(ctx_for(game), SUSPENDED) == [oid]
        assert resolve_pool(ctx_for(game), {"suspended": True, "zone": "exile"}) == [oid]

    def test_it_agrees_with_the_tick(self, builder):
        game, oid = position(builder, how="suspended")
        assert suspended_cards(game.state, 0) == [oid]
        assert game.state.objects[oid].suspended

    def test_a_value_count_counts_it(self, builder):
        """Rose Tyler's "for each suspended card you own"."""
        game, _ = position(builder, how="suspended")
        count = {"count": {"suspended": True, "owner": "you"}}
        assert evaluate_value(ctx_for(game), count) == 1

    def test_whose_is_ownership(self, builder):
        game, oid = position(builder, how="suspended")
        theirs = ctx_for(game, pid=1)
        assert resolve_pool(theirs, {"suspended": True, "owner": "you"}) == []
        assert resolve_pool(theirs, {"suspended": True, "owner": "any"}) == [oid]

    def test_a_card_in_exile_target_offers_it_and_keeps_it(self, builder):
        game, oid = position(builder, how="suspended")
        state = game.state
        assert candidates(state, 0, TARGET, None) == [TargetRef.obj(oid)]
        assert still_legal(state, 0, TARGET, TargetRef.obj(oid), None)

    def test_any_of_composes_over_exile(self, builder):
        """`any_of` narrows one zone, so it composes with the key in exile."""
        game, oid = position(builder, how="suspended")
        either = {"zone": "exile", "any_of": [SUSPENDED, {"types": ["Land"]}]}
        assert resolve_pool(ctx_for(game), either) == [oid]


class TestTimeCountersWithoutSuspendDoNot:
    def test_an_exiled_card_with_time_counters_is_not_suspended(self, builder):
        game, oid = position(builder, how="exiled")
        assert not game.state.objects[oid].suspended
        assert resolve_pool(ctx_for(game), SUSPENDED) == []
        assert candidates(game.state, 0, TARGET, None) == []

    def test_the_near_miss_takes_it(self, builder):
        """The approximation this key exists to replace."""
        game, oid = position(builder, how="exiled")
        near_miss = {"zone": "exile", "has_counters": TIME_COUNTER}
        assert resolve_pool(ctx_for(game), near_miss) == [oid]


class TestTheLastCounterEndsIt:
    def test_the_mark_with_no_time_counter_is_not_suspended(self, builder):
        game, oid = position(builder, how="emptied")
        assert game.state.objects[oid].suspended_by is not None
        assert resolve_pool(ctx_for(game), SUSPENDED) == []
        assert evaluate_value(ctx_for(game), {"count": {"suspended": True}}) == 0

    def test_a_target_whose_last_counter_came_off_is_no_longer_legal(self, builder):
        """608.2b: offered while suspended, refused once it is not."""
        game, oid = position(builder, how="suspended")
        state = game.state
        ref = TargetRef.obj(oid)
        assert still_legal(state, 0, TARGET, ref, None)
        state.objects[oid].remove_counter(TIME_COUNTER, 2)
        assert not still_legal(state, 0, TARGET, ref, None)


class TestTheBattlefieldNeverIs:
    def test_a_permanent_with_time_counters_and_the_mark_does_not_match(self, builder):
        game, oid = position(builder, how="battlefield")
        assert not game.state.objects[oid].suspended
        assert resolve_pool(ctx_for(game), SUSPENDED) == []
        assert not matches(ctx_for(game), oid, SUSPENDED)
        assert not matches(ctx_for(game), oid, SUSPENDED, default_zone=None)


def _probe(*, selector: dict, kind: str = "card_in_exile") -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_suspended_probe",
            "name": "Test Suspended Probe",
            "oracle_text": "Exile target suspended card.",
            "mana_cost": "{1}",
            "types": ["Sorcery"],
            "targets": [{"id": "t1", "kind": kind, "count": 1, "selector": selector}],
            "spell_effects": [{"op": "exile", "objects": {"target": "t1"}}],
        }
    )


def _count_probe(selector: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_suspended_count_probe",
            "name": "Test Suspended Count Probe",
            "oracle_text": "Draw a card for each suspended card you own.",
            "mana_cost": "{1}",
            "types": ["Sorcery"],
            "spell_effects": [{"op": "draw", "amount": {"count": selector}}],
        }
    )


class TestTheLoader:
    def test_the_key_loads_on_a_target_and_in_a_count(self):
        compile_card(_probe(selector=SUSPENDED), source="test")
        compile_card(_probe(selector={"suspended": True, "zone": "exile"}), source="test")
        compile_card(_count_probe({"suspended": True, "owner": "you"}), source="test")

    def test_false_is_refused(self):
        with pytest.raises(DslError, match="'suspended' must be true"):
            compile_card(_count_probe({"suspended": False}), source="test")

    @pytest.mark.parametrize("zone", ["battlefield", "graveyard", "hand"])
    def test_a_zone_other_than_exile_is_refused(self, zone):
        with pytest.raises(DslError, match="'suspended' asks about a card in exile"):
            compile_card(_count_probe({"suspended": True, "zone": zone}), source="test")

    def test_a_permanent_target_is_refused(self):
        with pytest.raises(DslError, match="belongs on a 'card_in_exile' target"):
            compile_card(_probe(selector=SUSPENDED, kind="permanent"), source="test")
