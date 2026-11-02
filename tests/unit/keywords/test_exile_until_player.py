"""`exile_until`'s ``player`` — the walk down someone else's library.

Strago and Relm: "Target opponent exiles cards from the top of their library
until they exile an instant, sorcery, or creature card. You may cast that card
without paying its mana cost."

Two players are named in that sentence and they do different things. The
opponent's library is the one walked, so a walk down the controller's own
library would exile the wrong cards and cast the controller's own spell -- a
different card. The *controller* is the one who may cast the hit (the "you" of
"you may cast"), so asking the opponent would hand them a free spell on our
activation. And rule 400.3 still holds throughout: every card the walk moves,
and the spell cast from among them, remains its **owner's** card. The free
cast puts it on the stack under the controller's control (601.2), while the
exiled cards sit in their owner's exile, never the caster's.

The key defaults to the controller, so Breaching Dragonstorm and every other
"exile cards from the top of **your** library" card is untouched.
"""

from __future__ import annotations

import inspect

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.structs import TargetRef
from tests.conftest import library_ids

FOREST = "forest"
BEAR = "t_bear"           # a creature card, the Strago stop
SOURCE = "t_cascader"     # only somewhere for the effect to come from


def strago(**extra) -> dict:
    """Strago and Relm's walk, with the player as a parameter."""
    return {
        "op": "exile_until",
        "objects": {"any_types": ["Instant", "Sorcery", "Creature"]},
        "cast_free": True,
        "as": "hit",
        "player": {"target": "t1"},
        **extra,
    }


def board(builder, *, mine: list[str], theirs: list[str]):
    game = (
        builder(players=2)
        .battlefield(0, [SOURCE])
        .library(0, mine)
        .library(1, theirs)
        .build(advance=False)
    )
    src = next(o.oid for o in game.state.battlefield_objects(0))
    return game, src


def run(game, spec: dict, source: int, *, cast: bool = True):
    """Run one op with seat 1 as target t1; returns the context and who was asked."""
    ctx = EffectContext(
        state=game.state,
        controller=0,
        source_oid=source,
        targets={"t1": (TargetRef("player", 1),)},
    )
    gen = OPS[spec["op"]](ctx, spec)
    asked: list[int] = []
    if inspect.isgenerator(gen):
        send = None
        while True:
            try:
                decision = gen.send(send)
            except StopIteration:
                break
            asked.append(decision.player)
            send = [0] if cast else [1]
    return ctx, asked


def exile_ids(game, pid: int) -> list[str]:
    return sorted(game.state.objects[o].def_id for o in game.state.players[pid].exile)


class TestWhoseLibrary:
    def test_the_default_is_the_controllers_library(self, builder):
        game, src = board(builder, mine=[FOREST, BEAR], theirs=[FOREST, BEAR])
        spec = strago()
        del spec["player"]

        run(game, spec, src, cast=False)

        assert exile_ids(game, 0) == sorted([FOREST, BEAR])
        assert library_ids(game, 1) == [FOREST, BEAR], "the opponent's library is untouched"

    def test_the_named_players_library_is_walked(self, builder):
        game, src = board(builder, mine=[FOREST, BEAR], theirs=[FOREST, FOREST, BEAR, FOREST])

        run(game, strago(), src, cast=False)

        assert library_ids(game, 0) == [FOREST, BEAR], "the controller's library is untouched"
        assert library_ids(game, 1) == [FOREST], "the walk stopped at the Bear"
        assert exile_ids(game, 1) == sorted([FOREST, FOREST, BEAR])

    def test_an_empty_library_finds_nothing_and_asks_nothing(self, builder):
        game, src = board(builder, mine=[BEAR], theirs=[])

        ctx, asked = run(game, strago(), src)

        assert ctx.bindings["hit"] == []
        assert asked == []
        assert game.state.stack == []
        assert library_ids(game, 0) == [BEAR]

    def test_a_library_with_no_match_is_exiled_whole(self, builder):
        game, src = board(builder, mine=[], theirs=[FOREST, FOREST])

        ctx, asked = run(game, strago(), src)

        assert ctx.bindings["hit"] == []
        assert asked == []
        assert exile_ids(game, 1) == [FOREST, FOREST]


class TestWhoCasts:
    def test_the_controller_is_offered_the_cast(self, builder):
        game, src = board(builder, mine=[], theirs=[FOREST, BEAR])

        _, asked = run(game, strago(), src, cast=True)

        assert asked == [0], "you may cast that card -- not the opponent"
        (item,) = game.state.stack
        assert item.def_id == BEAR
        assert item.controller == 0

    def test_the_cast_card_stays_its_owners(self, builder):
        game, src = board(builder, mine=[], theirs=[FOREST, BEAR])

        ctx, _ = run(game, strago(), src, cast=True)

        (oid,) = ctx.bindings["hit"]
        assert game.state.objects[oid].owner == 1

    def test_a_declined_hit_stays_in_its_owners_exile(self, builder):
        game, src = board(builder, mine=[], theirs=[FOREST, BEAR])

        ctx, asked = run(game, strago(), src, cast=False)

        assert asked == [0]
        assert game.state.stack == []
        (oid,) = ctx.bindings["hit"]
        assert oid in game.state.players[1].exile
        assert exile_ids(game, 0) == []

    def test_else_destination_is_the_owners_hand(self, builder):
        """400.3: a card goes to its owner's hand, whoever's effect sent it."""
        game, src = board(builder, mine=[], theirs=[BEAR])

        run(game, strago(else_destination="hand"), src, cast=False)

        assert [game.state.objects[o].def_id for o in game.state.players[1].hand] == [BEAR]
        assert game.state.players[0].hand == []


class TestEachPlayer:
    def test_every_seat_walks_its_own_library_and_the_binding_accumulates(self, builder):
        game, src = board(builder, mine=[FOREST, BEAR], theirs=[BEAR, FOREST])
        spec = {"op": "exile_until", "objects": {"not_types": ["Land"]}, "as": "hit",
                "player": "each_player"}

        ctx, _ = run(game, spec, src)

        owners = sorted(game.state.objects[o].owner for o in ctx.bindings["hit"])
        assert owners == [0, 1]
        assert library_ids(game, 0) == []
        assert library_ids(game, 1) == [FOREST]


class TestTheLoader:
    def test_strago_and_relms_walk_loads_with_a_target_opponent(self):
        compile_card(
            CardModel.model_validate(
                {
                    "id": "t_exile_until_player_probe",
                    "name": "Exile Until Player Probe",
                    "mana_cost": "{2}",
                    "types": ["Sorcery"],
                    "targets": [
                        {"id": "t1", "kind": "player", "count": 1,
                         "selector": {"controller": "opponent"}}
                    ],
                    "spell_effects": [strago()],
                }
            )
        )
