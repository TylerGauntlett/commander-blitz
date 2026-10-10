"""Tokens "created with this creature" -- the link from a token to its creator.

Faerie Artisans: "Whenever a nontoken creature an opponent controls enters,
create a token that's a copy of that creature except it's an artifact in
addition to its other types. Then exile all other tokens created with this
creature."

`create_token` and `copy_permanent` recorded nothing about who made a token: the
new object had an owner, a controller and `is_token`, and the TOKEN_CREATED
event's `source` is the token itself. The only reachable approximation was
`{"is_token": true, "controller": "you"}` minus the fresh copy, which is a
different card -- it exiles every Treasure, Clue and Soldier its controller has,
and it exiles a second Artisans' copy too. `t_loose_artisans` is that card, kept
beside the real one so the pair pins that the link does the work.

The rules argument is the 607.2a linked-ability shape one step removed: the
sentence names objects by what *this object's* ability did earlier. And "this
creature" is an object, not a card -- rule 400.7 makes a permanent that leaves
the battlefield and returns a new object with no memory of its previous
existence, so the tokens an earlier incarnation made are no longer "created with
this creature" and survive the next trigger. An oid survives every zone change
here, so the record lives on the creator (`GameObject.created_tokens`) and is
cleared by `reset_permanent_state` at exactly the moment the object ends; a
pointer on the token could not tell the two incarnations apart.

"Other" is the binding the creating op wrote (`as`) read back through
`exclude_binding`, so the copy made by this same resolution is spared.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.state import new_object
from commanderblitz.engine.triggers import matches_card_filter
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of, pass_until

ARTISANS = "t_faerie_artisans"
LOOSE = "t_loose_artisans"  # `is_token` where the link should be
BEAR = "t_bear"
TREASURE = "treasure_token"


def position(builder, *mine: str):
    """``(game, oid)``: player 0's permanents, and the first of them."""
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game, game.state.battlefield[0]


def enter(game, pid: int, card: str = BEAR) -> int:
    """Put a creature onto the battlefield under ``pid`` and let every trigger
    it causes resolve.

    Waits on the TOKEN_CREATED count rather than on an empty stack: the
    trigger is only *queued* by the move, so the stack is still empty the
    first time an emptiness predicate is checked.
    """
    state = game.state
    obj = new_object(state, card, owner=pid, zone=Zone.HAND)
    state.players[pid].hand.append(obj.oid)
    before = _made(game)
    move_object(state, obj.oid, Zone.BATTLEFIELD)
    pass_until(game, lambda g: _made(g) > before and not g.state.stack)
    return obj.oid


def _made(game) -> int:
    return sum(1 for e in game.state.events if e.type == "token_created")


def make_tokens(game, source: int, spec: dict) -> list[int]:
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    list(execute(ctx, [{**spec, "as": "made"}]))
    return list(ctx.bindings["made"])


def tokens(game) -> list[int]:
    return [oid for oid in game.state.battlefield if game.state.objects[oid].is_token]


class TestTheLinkIsRecorded:
    def test_create_token_records_on_its_source(self, builder):
        game, bear = position(builder, BEAR)
        made = make_tokens(game, bear, {"op": "create_token", "token": TREASURE, "amount": 2})
        assert game.state.objects[bear].created_tokens == set(made)

    def test_copy_permanent_records_on_its_source(self, builder):
        game, bear = position(builder, BEAR)
        made = make_tokens(game, bear, {"op": "copy_permanent", "objects": {"self_only": True}})
        assert game.state.objects[bear].created_tokens == set(made)

    def test_the_selector_reads_it(self, builder):
        game, bear = position(builder, BEAR, "island")
        mine = make_tokens(game, bear, {"op": "create_token", "token": TREASURE})
        make_tokens(game, game.state.battlefield[1], {"op": "create_token", "token": TREASURE})
        ctx = EffectContext(state=game.state, controller=0, source_oid=bear)
        assert resolve_pool(ctx, {"created_with": "self"}) == mine

    def test_no_source_links_nothing(self, builder):
        game, bear = position(builder, BEAR)
        ctx = EffectContext(state=game.state, controller=0)
        list(execute(ctx, [{"op": "create_token", "token": TREASURE}]))
        assert game.state.objects[bear].created_tokens == set()
        probe = EffectContext(state=game.state, controller=0, source_oid=bear)
        assert resolve_pool(probe, {"created_with": "self"}) == []


class TestFaerieArtisans:
    def test_the_first_copy_is_made_and_is_an_artifact(self, builder):
        from commanderblitz.engine.characteristics import chars

        game, _ = position(builder, ARTISANS)
        enter(game, 1)
        (copy,) = tokens(game)
        assert {"Artifact", "Creature"} <= chars(game.state, copy).types

    def test_the_second_trigger_exiles_the_first_copy(self, builder):
        game, _ = position(builder, ARTISANS)
        enter(game, 1)
        (first,) = tokens(game)
        enter(game, 1)
        assert first not in game.state.battlefield
        assert len(tokens(game)) == 1

    def test_the_just_made_copy_survives(self, builder):
        """ "All *other* tokens" -- the copy this resolution made is spared by
        `exclude_binding`, or the ability would exile its own output."""
        game, artisans = position(builder, ARTISANS)
        enter(game, 1)
        enter(game, 1)
        (survivor,) = tokens(game)
        assert survivor in game.state.objects[artisans].created_tokens

    def test_another_permanents_tokens_are_not_exiled(self, builder):
        game, _ = position(builder, ARTISANS, "island")
        (treasure,) = make_tokens(
            game, game.state.battlefield[1], {"op": "create_token", "token": TREASURE}
        )
        enter(game, 1)
        enter(game, 1)
        assert treasure in game.state.battlefield

    def test_without_the_link_the_treasure_is_exiled(self, builder):
        """The other half of the pair: if this ever passes for the real card,
        the test above proves nothing."""
        game, _ = position(builder, LOOSE, "island")
        (treasure,) = make_tokens(
            game, game.state.battlefield[1], {"op": "create_token", "token": TREASURE}
        )
        enter(game, 1)
        assert treasure not in game.state.battlefield

    def test_two_artisans_each_keep_their_own_copy(self, builder):
        """Both trigger on the same creature. Each exiles only what *it* made,
        so after two arrivals there is one copy per Artisans -- the loose card
        would leave whichever resolved last with the only token."""
        game, _ = position(builder, ARTISANS, ARTISANS)
        first, second = oids_of(game, ARTISANS, 0)
        enter(game, 1)
        enter(game, 1)
        pass_until(game, lambda g: len(tokens(g)) == 2 and not g.state.stack)
        alive = set(tokens(game))
        assert len(alive) == 2
        for artisans in (first, second):
            assert len(alive & game.state.objects[artisans].created_tokens) == 1


class TestANewObjectIsNotTheCreator:
    """400.7: a creator that left and came back made nothing yet."""

    def test_leaving_clears_the_record(self, builder):
        game, bear = position(builder, BEAR)
        make_tokens(game, bear, {"op": "create_token", "token": TREASURE})
        move_object(game.state, bear, Zone.EXILE)
        assert game.state.objects[bear].created_tokens == set()

    def test_tokens_from_a_previous_incarnation_are_not_exiled(self, builder):
        game, artisans = position(builder, ARTISANS)
        enter(game, 1)
        (old,) = tokens(game)
        move_object(game.state, artisans, Zone.EXILE)
        move_object(game.state, artisans, Zone.BATTLEFIELD)
        enter(game, 1)
        assert old in game.state.battlefield, "the old incarnation's copy was exiled"
        assert len(tokens(game)) == 2

    def test_the_new_incarnation_still_links_its_own(self, builder):
        game, artisans = position(builder, ARTISANS)
        enter(game, 1)
        (old,) = tokens(game)
        move_object(game.state, artisans, Zone.EXILE)
        move_object(game.state, artisans, Zone.BATTLEFIELD)
        enter(game, 1)
        (new,) = set(tokens(game)) - {old}
        enter(game, 1)
        assert new not in game.state.battlefield
        assert old in game.state.battlefield


class TestATriggerFilterHonoursIt:
    def test_only_the_creators_tokens_match(self, builder):
        game, bear = position(builder, BEAR, "island")
        (mine,) = make_tokens(game, bear, {"op": "create_token", "token": TREASURE})
        (theirs,) = make_tokens(
            game, game.state.battlefield[1], {"op": "create_token", "token": TREASURE}
        )
        source = game.state.objects[bear]
        filt = {"created_with": "self"}
        assert matches_card_filter(game.state, mine, filt, source)
        assert not matches_card_filter(game.state, theirs, filt, source)


def _card(created_with) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_created_with_loader",
            "name": "Test Created With Loader",
            "oracle_text": "Exile all tokens created with this artifact.",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "activated",
                    "cost": {"mana": "{1}"},
                    "effects": [
                        {"op": "exile", "objects": {"created_with": created_with}},
                    ],
                }
            ],
        }
    )


class TestTheLoaderChecksIt:
    def test_self_loads(self):
        compile_card(_card("self"), source="test")

    @pytest.mark.parametrize("bad", ["you", "opponent", 3, True])
    def test_anything_else_is_refused(self, bad):
        with pytest.raises(DslError, match="created_with"):
            compile_card(_card(bad), source="test")

    def test_the_witness_compiles(self, registry):
        assert registry.get(ARTISANS) is not None
