"""Naming what an earlier effect in the same resolution did — "this way".

    Grey Host Reinforcements — "…exile target player's graveyard. Put a number
    of +1/+1 counters on this creature equal to the number of creature cards
    exiled **this way**."
    Flamerush Rider — "…create a token that's a copy of another target attacking
    creature… Exile **the token** at end of combat."

Rule 608.2 resolves a one-shot effect's instructions in order, and the later
instruction on both of these cards is *about the objects the earlier one
touched*. Nothing in the selector language can name them afterwards:

- the exiled cards land in the shared exile zone among everything that has ever
  been exiled there, and counting the graveyard *before* exiling it is only
  numerically equal because this particular card empties the whole zone;
- `is_token` matches every token you control, so `{"is_token": true,
  "attacking": true}` would also catch tokens some other attack trigger made
  this turn — a second Flamerush Rider exiles the wrong permanent.

So the op writes down what it consumed or produced (``as``) and a later selector
reads it back by ``binding``, which is the idiom `sacrifice` and `reveal` have
carried since amplify and devour shipped (`test_recorded_choices.py`). `exile`
was the one member of that family that never got it, and the two token-making
ops threw away the oids `create_token` returns.

The other half is a **silent** one. `matches` defaults an absent ``zone`` clause
to the battlefield, which is right for a selector that searches a zone and wrong
for one that names a pool the engine already holds: an object recorded by ``as``
has, by construction, just changed zones. So
`{"binding": "exiled", "types": ["Creature"]}` — the exact selector Grey Host
Reinforcements needs — matched nothing at all, counted 0, and put no counters on
a card that reads as though it should. A `target` selector keeps the battlefield
default, because a target really is re-checked on resolution (608.2b).
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, _validate_effect
from automtg.engine.effects import execute_one
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import resolve_pool
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.objects import PLUS_ONE
from automtg.engine.structs import TargetRef
from tests.conftest import action_for_card, find_action, oids_of, only_oid, pass_until

BEAR = "t_bear"
FOREST = "forest"
MOUNTAIN = "mountain"
PLAINS = "plains"
WARRIOR = "t_warrior_token"
GRAVEPICKER = "t_gravepicker"
SMITH = "t_token_smith"


def counters(game, oid: int) -> int:
    return game.state.objects[oid].counters.get(PLUS_ONE, 0)


def run(game, spec, source=None, *, take: int | None = None) -> EffectContext:
    """Run one effect dict to completion, answering any decision it asks.

    Through `execute_one` rather than `OPS[op]` directly, because the ops under
    test here are a mix: `exile` is a generator that may ask what to exile, and
    the two token-making ops are plain functions.
    """
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    gen = execute_one(ctx, spec)
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return ctx
        send = list(range(len(decision.options) if take is None else take))


class TestExileRecordsWhatItExiled:
    """`exile`'s `as`, byte-for-byte the record `sacrifice` already kept."""

    def test_it_records_the_cards_it_exiled(self, builder):
        game = builder(players=2).graveyard(0, [BEAR, BEAR, FOREST]).build(advance=False)
        spec = {
            "op": "exile",
            "as": "exiled",
            "objects": {"zone": "graveyard", "controller": "you", "count": "all"},
        }

        ctx = run(game, spec)

        assert len(ctx.bindings["exiled"]) == 3

    def test_the_record_outlives_the_zone_change(self, builder):
        """The whole point: the cards are in exile by the time it is read."""
        game = builder(players=2).graveyard(0, [BEAR, BEAR]).build(advance=False)
        spec = {
            "op": "exile",
            "as": "exiled",
            "objects": {"zone": "graveyard", "controller": "you", "count": "all"},
        }

        ctx = run(game, spec)

        assert not game.state.players[0].graveyard
        assert all(game.state.objects[o].zone is Zone.EXILE for o in ctx.bindings["exiled"])
        assert len(resolve_pool(ctx, {"binding": "exiled"})) == 2

    def test_an_exile_without_as_records_nothing(self, builder):
        """Every `exile` shipped before this one, unchanged."""
        game = builder(players=2).graveyard(0, [BEAR]).build(advance=False)
        spec = {"op": "exile", "objects": {"zone": "graveyard", "controller": "you"}}

        ctx = run(game, spec)

        assert ctx.bindings == {}

    def test_exiling_nothing_records_an_empty_set(self, builder):
        """"…equal to the number of cards exiled this way" is 0, not unwritten."""
        game = builder(players=2).build(advance=False)
        spec = {
            "op": "exile",
            "as": "exiled",
            "objects": {"zone": "graveyard", "controller": "you", "count": "all"},
        }

        ctx = run(game, spec)

        assert ctx.bindings["exiled"] == []


class TestARecordedSetCanBeFiltered:
    """"…the number of **creature** cards exiled this way" — the subset, not the size."""

    def test_a_types_clause_narrows_the_record(self, builder):
        game = builder(players=2).graveyard(0, [BEAR, BEAR, FOREST]).build(advance=False)
        spec = {
            "op": "exile",
            "as": "exiled",
            "objects": {"zone": "graveyard", "controller": "you", "count": "all"},
        }
        ctx = run(game, spec)

        assert len(resolve_pool(ctx, {"binding": "exiled", "types": ["Creature"]})) == 2
        assert len(resolve_pool(ctx, {"binding": "exiled", "types": ["Land"]})) == 1

    def test_the_bare_binding_still_counts_everything(self, builder):
        """Devour and amplify read this spelling. It must not start filtering."""
        game = builder(players=2).graveyard(0, [BEAR, FOREST]).build(advance=False)
        ctx = run(
            game,
            {
                "op": "exile",
                "as": "exiled",
                "objects": {"zone": "graveyard", "controller": "you", "count": "all"},
            },
        )

        assert len(resolve_pool(ctx, {"binding": "exiled"})) == 2

    def test_a_zone_clause_the_card_writes_is_still_obeyed(self, builder):
        """Only the *default* is dropped, so "…still in exile" remains sayable."""
        game = builder(players=2).graveyard(0, [BEAR, BEAR]).build(advance=False)
        ctx = run(
            game,
            {
                "op": "exile",
                "as": "exiled",
                "objects": {"zone": "graveyard", "controller": "you", "count": "all"},
            },
        )

        assert len(resolve_pool(ctx, {"binding": "exiled", "zone": "exile"})) == 2
        assert resolve_pool(ctx, {"binding": "exiled", "zone": "graveyard"}) == []

    def test_a_target_selector_keeps_the_battlefield_default(self, builder):
        """608.2b: a target is re-checked on resolution, so this default is a check.

        "Destroy target creature" whose creature is already in a graveyard must
        reach nothing -- a binding is a record of the past, a target is not.
        """
        game = builder(players=2).graveyard(0, [BEAR]).build(advance=False)
        dead = game.state.players[0].graveyard[0]
        ctx = EffectContext(state=game.state, controller=0)
        ctx.targets["t1"] = (TargetRef.obj(dead),)

        assert resolve_pool(ctx, {"target": "t1"}) == [dead], "the bare form is a pool"
        assert resolve_pool(ctx, {"target": "t1", "types": ["Creature"]}) == []


class TestTokenMakingOpsRecordWhatTheyMade:
    def test_create_token_records_the_new_tokens(self, builder):
        game = builder(players=2).build(advance=False)
        spec = {"op": "create_token", "token": WARRIOR, "amount": 2, "as": "made"}

        ctx = run(game, spec)

        made = ctx.bindings["made"]
        assert len(made) == 2
        assert all(game.state.objects[o].is_token for o in made)
        assert all(game.state.objects[o].zone is Zone.BATTLEFIELD for o in made)

    def test_the_record_names_only_this_effects_tokens(self, builder):
        """`is_token` cannot say it: the board already holds an identical token."""
        game = builder(players=2).battlefield(0, [WARRIOR]).build(advance=False)
        already = only_oid(game, WARRIOR)

        ctx = run(game, {"op": "create_token", "token": WARRIOR, "as": "made"})

        assert already not in ctx.bindings["made"]
        assert len(resolve_pool(ctx, {"binding": "made"})) == 1
        assert (
            len(resolve_pool(ctx, {"zone": "battlefield", "name": "Warrior Token"})) == 2
        ), "no characteristic tells the two apart -- only the record does"

    def test_copy_permanent_records_the_copy_not_the_original(self, builder):
        game = builder(players=2).battlefield(0, [BEAR]).build(advance=False)
        bear = only_oid(game, BEAR)

        ctx = run(game, {"op": "copy_permanent", "objects": {"self_only": True},
                         "as": "copies"}, source=bear)

        copies = ctx.bindings["copies"]
        assert len(copies) == 1 and copies[0] != bear
        assert game.state.objects[copies[0]].def_id == BEAR
        assert game.state.objects[copies[0]].is_token

    def test_copying_nothing_leaves_the_binding_unwritten(self, builder):
        """Nothing was created, so a later `{"binding": …}` must reach nothing."""
        game = builder(players=2).build(advance=False)

        ctx = run(game, {"op": "copy_permanent", "objects": {"types": ["Creature"]},
                         "as": "copies"})

        assert resolve_pool(ctx, {"binding": "copies"}) == []

    def test_a_token_op_without_as_records_nothing(self, builder):
        game = builder(players=2).build(advance=False)

        ctx = run(game, {"op": "create_token", "token": WARRIOR})

        assert ctx.bindings == {}


class TestTheRecordReachesALaterEffect:
    """A binding is only worth writing if the next op in the list can act on it."""

    def test_a_later_op_exiles_exactly_the_token_just_made(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [MOUNTAIN] * 3)
            .battlefield(0, [WARRIOR])
            .hand(0, [SMITH])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        bystander = only_oid(game, WARRIOR)

        game.apply(action_for_card(game, ActionKind.CAST, SMITH))
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        assert oids_of(game, WARRIOR) == [bystander], "the identical token is untouched"
        assert only_oid(game, SMITH)


class TestGreyHostReinforcementsOnACard:
    """The printed card, cast in a real position, counters and all."""

    def cast_it(self, builder, graveyard):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 4)
            .graveyard(0, graveyard)
            .hand(0, [GRAVEPICKER])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, GRAVEPICKER))
        # The ETB trigger targets a player, and both seats are legal, so the
        # controller is asked as it goes on the stack (603.3d). Option 0 is seat
        # 0 -- `enumerate_target_tuples` walks `state.alive()` -- whose graveyard
        # is the one this position stocked.
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None
            and d.kind is DecisionKind.CHOOSE_OBJECTS,
        )
        game.apply(find_action(game, ActionKind.CHOOSE))
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)
        return game

    def test_it_counts_the_creature_cards_it_exiled(self, builder):
        game = self.cast_it(builder, [BEAR, BEAR, FOREST])

        assert not game.state.players[0].graveyard, "the whole graveyard went"
        assert counters(game, only_oid(game, GRAVEPICKER)) == 2, "two creature cards"

    def test_an_empty_graveyard_is_no_counters(self, builder):
        game = self.cast_it(builder, [])

        assert counters(game, only_oid(game, GRAVEPICKER)) == 0

    def test_a_graveyard_of_lands_is_no_counters(self, builder):
        """The boundary the `types` clause exists for: exiled, but not creatures."""
        game = self.cast_it(builder, [FOREST, FOREST])

        assert counters(game, only_oid(game, GRAVEPICKER)) == 0
        assert not game.state.players[0].graveyard


class TestTheLoaderGuard:
    def test_an_as_on_exile_loads(self):
        _validate_effect(
            {"op": "exile", "as": "exiled", "objects": {"zone": "graveyard"}}, "test", {}
        )

    def test_an_as_on_create_token_loads(self):
        _validate_effect({"op": "create_token", "token": WARRIOR, "as": "made"}, "test", {})

    def test_an_as_on_copy_permanent_loads(self):
        _validate_effect(
            {"op": "copy_permanent", "objects": {"target": "t1"}, "as": "made"},
            "test",
            {"t1"},
        )

    def test_an_as_on_an_op_that_records_nothing_is_refused(self):
        """It would read back as 0 and the card's second sentence would do nothing."""
        with pytest.raises(DslError, match="records no binding"):
            _validate_effect(
                {"op": "destroy", "as": "killed", "objects": {"types": ["Creature"]}},
                "test",
                {},
            )

    def test_a_non_string_as_is_still_refused(self):
        with pytest.raises(DslError, match="'as' must be a non-empty binding name"):
            _validate_effect({"op": "exile", "as": 3, "objects": {}}, "test", {})
