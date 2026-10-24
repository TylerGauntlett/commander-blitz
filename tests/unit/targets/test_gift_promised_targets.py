"""A target only one side of the gift promise declares.

    "Gift a card. Target opponent sacrifices a creature with the greatest power
    among creatures they control. **If the gift was promised, return target
    creature card from your graveyard to your hand.**" -- Consumed by Greed.

    "Gift a tapped Fish. Return target creature an opponent controls to its
    owner's hand. **If the gift was promised, instead return target nonland
    permanent an opponent controls to its owner's hand.**" -- Into the Flood Maw.

Legal because of the rules order, which is kicker's argument again: 601.2b
announces the promise (702.164a makes it a choice made as the spell is cast) and
601.2c declares the targets one step later. So a cast already knows which side
of the promise it is on when it chooses what to point at, and the printed card
may make the target depend on it.

What would be wrong without the gate is a different card in either direction.
Declared on every cast and branched on with `{"gift_promised": true}` at
resolution, Consumed by Greed would need a creature card in your graveyard to be
cast at all, and would announce a target the unpromised spell never chooses --
which is what opponents respond to and what decides whether it fizzles. Made
`optional`, a promised cast could skip the target the promise is meant to buy.
601.2c read for a required target: a promised cast must choose it, so with no
legal choice the promised line is not offered -- exactly as a kicked line with no
legal kicked target is not, `count_if_kicked`'s behaviour -- while the
unpromised line stays castable.

The witnesses are Consumed by Greed and Into the Flood Maw (`t_greed` and
`t_flood_maw` in `tests/data/gift_targets.cards.json`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.actions import TargetRef
from commanderblitz.engine.effects.ops_stack import put_copy_on_stack
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import unplayable_reason
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, hand_ids

GREED = "t_greed"
MAW = "t_flood_maw"
BEAR = "grizzly_bears"
GIANT = "hill_giant"
RING = "sol_ring"


def position(builder, card, *, graveyard=(), theirs=(BEAR,), players=2, lands=("swamp",) * 4):
    """``card`` in hand on the caster's own main phase, with a priority stop.

    The Bolt is never cast: `full_control` only holds a window open while
    something other than Pass is legal, and it always has a target.
    """
    game = (
        builder(players=players)
        .hand(0, [card, "lightning_bolt"])
        .battlefield(0, [*lands, "mountain"])
        .graveyard(0, list(graveyard))
        .library(0, ["swamp"] * 10)
        .turn(1)
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid in range(1, players):
        game = game.battlefield(pid, ["island", *theirs]).library(pid, ["island"] * 10)
    game = game.build(advance=False)
    game.state.players[0].full_control = True
    game._advance()
    return game


def lines(game, card):
    """Every cast of ``card`` right now, split by the promise."""
    casts = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card
    ]
    return [a for a in casts if a.gift_to is None], [a for a in casts if a.gift_to is not None]


def cast(game, action):
    game.apply(action)
    for _ in range(30):
        if not game.state.stack:
            break
        game.apply(_default_answer(game, game.pending()))
    return game


def oid_in(game, def_id, zone, pid=None):
    return next(
        oid
        for oid, obj in game.state.objects.items()
        if obj.def_id == def_id and obj.zone is zone and (pid is None or obj.owner == pid)
    )


def object_refs(action):
    return [ref for ref in action.targets if ref.kind != "player"]


class TestTheUnpromisedCastDeclaresNoGiftTarget:
    def test_castable_with_an_empty_graveyard(self, builder):
        """The gift-only target asks nothing of a cast that made no promise."""
        game = position(builder, GREED)
        plain, _promised = lines(game, GREED)
        assert plain
        assert all(a.targets == (TargetRef.player(1),) for a in plain)

    def test_it_announces_nothing_even_when_one_is_there(self, builder):
        """A creature card in the graveyard is not a target of the unpromised
        spell -- not chosen, not shown, not something to respond to."""
        game = position(builder, GREED, graveyard=[BEAR])
        plain, _promised = lines(game, GREED)
        assert plain and all(not object_refs(a) for a in plain)

    def test_it_resolves_as_the_small_half(self, builder):
        game = position(builder, GREED, graveyard=[BEAR])
        plain, _promised = lines(game, GREED)
        theirs = oid_in(game, BEAR, Zone.BATTLEFIELD, pid=1)
        cast(game, plain[0])
        assert game.state.objects[theirs].zone is Zone.GRAVEYARD
        assert BEAR not in hand_ids(game, 0)


class TestThePromisedCastMustChooseIt:
    def test_the_promised_line_targets_a_creature_card_in_your_graveyard(self, builder):
        game = position(builder, GREED, graveyard=[BEAR, "swamp"])
        mine = oid_in(game, BEAR, Zone.GRAVEYARD, pid=0)
        _plain, promised = lines(game, GREED)
        assert promised
        assert all(a.targets == (TargetRef.player(1), TargetRef.obj(mine)) for a in promised)

    def test_and_returns_it(self, builder):
        game = position(builder, GREED, graveyard=[BEAR])
        mine = oid_in(game, BEAR, Zone.GRAVEYARD, pid=0)
        theirs = oid_in(game, BEAR, Zone.BATTLEFIELD, pid=1)
        opponent_hand = len(game.state.players[1].hand)
        _plain, promised = lines(game, GREED)
        cast(game, promised[0])
        assert game.state.objects[mine].zone is Zone.HAND
        assert game.state.objects[theirs].zone is Zone.GRAVEYARD
        assert len(game.state.players[1].hand) == opponent_hand + 1, "the gift"

    def test_no_legal_gift_target_means_no_promised_line(self, builder):
        """601.2c: a required target with no legal choice cannot be declared,
        so the promise that would require it cannot be made -- the kicked line
        with no kicked target is not offered either. The unpromised cast is
        untouched."""
        game = position(builder, GREED, graveyard=["swamp"])
        plain, promised = lines(game, GREED)
        assert plain
        assert promised == []

    def test_every_promisee_gets_the_same_targets(self, builder):
        """Whom the promise names changes nothing about what the spell may
        point at -- only that a promise was made."""
        game = position(builder, GREED, graveyard=[BEAR], players=3)
        _plain, promised = lines(game, GREED)
        assert {a.gift_to for a in promised} == {1, 2}
        assert all(len(object_refs(a)) == 1 for a in promised)

    def test_the_target_leaving_does_not_counter_the_rest(self, builder):
        """608.2b: one illegal target of two is not all of them -- the opponent
        still sacrifices."""
        game = position(builder, GREED, graveyard=[BEAR])
        mine = oid_in(game, BEAR, Zone.GRAVEYARD, pid=0)
        theirs = oid_in(game, BEAR, Zone.BATTLEFIELD, pid=1)
        _plain, promised = lines(game, GREED)
        game.apply(promised[0])
        move_object(game.state, mine, Zone.EXILE)
        cast(game, _default_answer(game, game.pending()))
        assert game.state.objects[theirs].zone is Zone.GRAVEYARD
        assert game.state.objects[mine].zone is Zone.EXILE


class TestOneTargetWordTwoSelectors:
    """Into the Flood Maw: the promise widens the one target it declares."""

    def test_unpromised_points_only_at_a_creature(self, builder):
        game = position(builder, MAW, theirs=(BEAR, RING), lands=("island",) * 2)
        bear = oid_in(game, BEAR, Zone.BATTLEFIELD, pid=1)
        plain, _promised = lines(game, MAW)
        assert {a.targets for a in plain} == {(TargetRef.obj(bear),)}

    def test_promised_points_at_any_nonland_permanent(self, builder):
        game = position(builder, MAW, theirs=(BEAR, RING), lands=("island",) * 2)
        bear = oid_in(game, BEAR, Zone.BATTLEFIELD, pid=1)
        ring = oid_in(game, RING, Zone.BATTLEFIELD, pid=1)
        _plain, promised = lines(game, MAW)
        assert {a.targets for a in promised} == {(TargetRef.obj(bear),), (TargetRef.obj(ring),)}

    def test_castable_promised_only_when_no_creature_is_there(self, builder):
        """The early "nothing to target" exit must not take the promised lines
        with it: the promise declares a target the plain cast has no use for."""
        game = position(builder, MAW, theirs=(RING,), lands=("island",) * 2)
        plain, promised = lines(game, MAW)
        assert plain == []
        assert promised
        assert unplayable_reason(game.state, 0, oid_in(game, MAW, Zone.HAND)) is None

    def test_the_promised_cast_bounces_the_artifact(self, builder):
        game = position(builder, MAW, theirs=(RING,), lands=("island",) * 2)
        ring = oid_in(game, RING, Zone.BATTLEFIELD, pid=1)
        _plain, promised = lines(game, MAW)
        cast(game, promised[0])
        assert game.state.objects[ring].zone is Zone.HAND

    def test_the_unpromised_cast_bounces_the_creature(self, builder):
        game = position(builder, MAW, theirs=(BEAR, RING), lands=("island",) * 2)
        bear = oid_in(game, BEAR, Zone.BATTLEFIELD, pid=1)
        plain, _promised = lines(game, MAW)
        cast(game, plain[0])
        assert game.state.objects[bear].zone is Zone.HAND

    def test_a_promised_creature_target_is_bounced_once(self, builder):
        """Resolution splits the refs by the promised list: the creature is
        the promised spec's, and the unpromised spec has no bucket at all."""
        game = position(builder, MAW, theirs=(BEAR, GIANT), lands=("island",) * 2)
        bear = oid_in(game, BEAR, Zone.BATTLEFIELD, pid=1)
        giant = oid_in(game, GIANT, Zone.BATTLEFIELD, pid=1)
        _plain, promised = lines(game, MAW)
        cast(game, next(a for a in promised if a.targets == (TargetRef.obj(bear),)))
        assert game.state.objects[bear].zone is Zone.HAND
        assert game.state.objects[giant].zone is Zone.BATTLEFIELD


class TestACopyKeepsThePromise:
    def test_the_copy_resolves_with_the_promised_specs(self, builder):
        """707.10: the promise is a cast-time decision and the copy has it too,
        so its stored ref is split by the list it was declared under."""
        game = position(builder, MAW, theirs=(RING,), lands=("island",) * 2)
        ring = oid_in(game, RING, Zone.BATTLEFIELD, pid=1)
        _plain, promised = lines(game, MAW)
        game.apply(promised[0])
        original = game.state.stack[-1]
        put_copy_on_stack(game.state, 0, original)
        assert game.state.stack[-1].gift_to == original.gift_to == 1
        # The copy alone: split by the unpromised list it would fizzle, since
        # Sol Ring is no creature, and the original would do the bouncing.
        for _ in range(10):
            if len(game.state.stack) < 2:
                break
            game.apply(_default_answer(game, game.pending()))
        assert game.state.stack and game.state.stack[-1].sid == original.sid
        assert game.state.objects[ring].zone is Zone.HAND


class TestTheLoader:
    def model(self, **extra) -> CardModel:
        base = {
            "id": "t_gift_gate",
            "name": "Gift Gate",
            "mana_cost": "{1}{B}",
            "types": ["Instant"],
            "gift": "a card",
            "targets": [
                {
                    "id": "t1",
                    "kind": "card_in_graveyard",
                    "gift_promised": True,
                    "selector": {"zone": "graveyard", "controller": "you"},
                }
            ],
            "spell_effects": [
                {"op": "draw", "player": "gift_recipient", "amount": {"const": 1}},
                {"op": "return_to_hand", "objects": {"target": "t1"}},
            ],
        }
        base.update(extra)
        return CardModel(**base)

    def test_the_card_carries_both_lists(self, registry):
        card = registry.get(MAW)
        assert [s.id for s in card.targets] == ["t1"]
        assert [s.id for s in card.gift_targets] == ["t2"]
        assert [s.id for s in registry.get(GREED).gift_targets] == ["t1", "t2"]

    def test_an_ungated_card_has_no_promised_list(self, registry):
        assert registry.get("t_gift").gift_targets is None

    def test_a_gift_gated_target_reads_the_gift(self):
        """The promise deciding what the spell points at is a read of it, so a
        card whose only other gift clause is "they draw" is not half a gift."""
        model = self.model(
            spell_effects=[{"op": "return_to_hand", "objects": {"target": "t1"}}]
        )
        assert compile_card(model).gift_targets is not None

    def test_refused_on_a_card_with_no_gift(self):
        model = self.model(
            gift=None,
            spell_effects=[{"op": "return_to_hand", "objects": {"target": "t1"}}],
        )
        with pytest.raises(DslError, match="no 'gift'"):
            compile_card(model)

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
                    "trigger": {"event": "self_enters"},
                    "targets": [
                        {
                            "id": "t1",
                            "kind": "card_in_graveyard",
                            "gift_promised": True,
                            "selector": {"zone": "graveyard", "controller": "you"},
                        }
                    ],
                    "effects": [
                        {"op": "draw", "player": "gift_recipient", "amount": {"const": 1}},
                        {"op": "return_to_hand", "objects": {"target": "t1"}},
                    ],
                }
            ],
        )
        with pytest.raises(DslError, match="'gift_promised' is about a cast"):
            compile_card(model)

    def test_refused_beside_count_if_kicked(self):
        model = self.model(
            kicker="{1}",
            targets=[
                {
                    "id": "t1",
                    "kind": "card_in_graveyard",
                    "gift_promised": True,
                    "count_if_kicked": 2,
                    "selector": {"zone": "graveyard", "controller": "you"},
                }
            ],
        )
        with pytest.raises(DslError, match="count_if_kicked"):
            compile_card(model)

    def test_refused_on_a_mode_owned_target(self):
        model = self.model(
            targets=[
                {
                    "id": "t1",
                    "kind": "card_in_graveyard",
                    "gift_promised": True,
                    "mode": 0,
                    "selector": {"zone": "graveyard", "controller": "you"},
                }
            ],
            spell_effects=[
                {
                    "op": "choose_mode",
                    "count": 1,
                    "modes": [
                        [{"op": "return_to_hand", "objects": {"target": "t1"}}],
                        [{"op": "draw", "player": "gift_recipient", "amount": {"const": 1}}],
                    ],
                }
            ],
        )
        with pytest.raises(DslError, match="mode-owned"):
            compile_card(model)

    def test_the_ordering_rule_holds_per_side(self):
        """"Any number of" must be last in the list a cast actually declares;
        a promised spec after it breaks the promised list even though the
        unpromised one is fine."""
        model = self.model(
            targets=[
                {
                    "id": "t0",
                    "kind": "permanent",
                    "count": "any",
                    "selector": {"zone": "battlefield", "controller": "you"},
                },
                {
                    "id": "t1",
                    "kind": "card_in_graveyard",
                    "gift_promised": True,
                    "selector": {"zone": "graveyard", "controller": "you"},
                },
            ],
            spell_effects=[
                {"op": "draw", "player": "gift_recipient", "amount": {"const": 1}},
                {"op": "return_to_hand", "objects": {"target": "t0"}},
                {"op": "return_to_hand", "objects": {"target": "t1"}},
            ],
        )
        with pytest.raises(DslError, match="must come last"):
            compile_card(model)
