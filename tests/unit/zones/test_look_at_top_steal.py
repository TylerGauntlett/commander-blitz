"""`look_at_top` on an opponent's library, the pick entering under *your* control.

    Lonis, Cryptozoologist -- "{T}, Sacrifice X Clues: Target opponent reveals
    the top X cards of their library. You may put a nonland permanent card with
    mana value X or less from among them onto the battlefield **under your
    control**. That player puts the rest on the bottom of their library in a
    random order."

Two seats are named and the sentence splits between them, as it does for
`reveal_until` on Jhoira:

- **The library and the rest are the opponent's.** The window is the top of
  their library, and "the rest" goes to the bottom of *that* library.
- **The permanent is yours.** Rule 110.2: a permanent's controller is by
  default whoever put it onto the battlefield, but an effect that says "under
  your control" decides it. The pick already belongs to the effect's controller
  (109.5, the chooser); without ``controller: "you"`` the arrival does not, and
  the card enters under the seat whose library was looked at -- Lonis would
  sacrifice its Clues to hand the opponent a free permanent.

The claims: with the key the card enters under seat 0 and stays owned by seat
1, in the pool branch and in a ``destinations`` step; without it the card
enters under the looked-at seat; the rest goes to the bottom of the opponent's
library and yours is untouched; and the loader admits only ``"you"``, only
beside a battlefield arrival, never with ``cast_free``.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import (
    activations,
    battlefield_ids,
    library_ids,
    oids_of,
    only_oid,
    pass_until,
    settle,
)

FOREST = "forest"
BEAR = "t_bear"  # a creature, mana value 2
SOL_RING = "sol_ring"  # an artifact, mana value 1

LONIS = {
    "op": "look_at_top",
    "player": {"target": "t1"},
    "amount": {"const": 3},
    "destination": "battlefield",
    "controller": "you",
    "objects": {
        "count": 1,
        "optional": True,
        "not_types": ["Land", "Instant", "Sorcery"],
        "mana_value": {"op": "<=", "value": {"const": 3}},
    },
    "rest_to_bottom": True,
}


def board(builder, library: list[str]):
    """Seat 1's library is stacked; seat 0 controls the source and targets seat 1."""
    game = (
        builder(players=2, seed=0)
        .battlefield(0, [FOREST])
        .library(0, ["island"] * 5)
        .library(1, library)
        .build(advance=False)
    )
    src = next(o.oid for o in game.state.battlefield_objects(0))
    return game, src


def run(game, effects: list[dict], source: int, pick=lambda decision: [0]) -> list:
    """Resolve for seat 0, answering each decision with ``pick``; returns them."""
    ctx = EffectContext(
        state=game.state,
        controller=0,
        source_oid=source,
        targets={"t1": (TargetRef.player(1),)},
    )
    gen = execute(ctx, effects)
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            decision = gen.send(pick(decision))
    except StopIteration:
        pass
    return asked


def the(game, card_id: str):
    return next(o for o in game.state.objects.values() if o.def_id == card_id)


class TestThePickIsYours:
    def test_it_enters_under_your_control_from_their_library(self, builder):
        game, src = board(builder, [FOREST, SOL_RING, FOREST, BEAR])

        asked = run(game, [LONIS], src)

        assert [d.player for d in asked] == [0], "the caster picks"
        assert SOL_RING in battlefield_ids(game, 0)
        assert SOL_RING not in battlefield_ids(game, 1)
        ring = the(game, SOL_RING)
        assert ring.controller == 0
        assert ring.owner == 1, "control changes, ownership does not"

    def test_without_the_key_it_enters_under_the_looked_at_seat(self, builder):
        """The contrast: every own-library look, and the bug Lonis would be."""
        game, src = board(builder, [FOREST, SOL_RING, FOREST])
        plain = dict(LONIS)
        plain.pop("controller")

        run(game, [plain], src)

        assert SOL_RING in battlefield_ids(game, 1)
        assert SOL_RING not in battlefield_ids(game, 0)

    def test_a_destinations_step_to_the_battlefield_reads_it_too(self, builder):
        game, src = board(builder, [SOL_RING, FOREST, FOREST])
        stepped = {
            key: value for key, value in LONIS.items() if key not in ("destination", "objects")
        }
        stepped["destinations"] = [
            {"to": "battlefield", "count": 1, "selector": {"types": ["Artifact"]}}
        ]

        run(game, [stepped], src)

        assert the(game, SOL_RING).controller == 0

    def test_declining_puts_nothing_down(self, builder):
        game, src = board(builder, [SOL_RING, BEAR, FOREST])

        run(game, [LONIS], src, pick=lambda decision: [])

        assert battlefield_ids(game, 0) == [FOREST]
        assert battlefield_ids(game, 1) == []
        assert sorted(library_ids(game, 1)) == sorted([SOL_RING, BEAR, FOREST])


class TestTheRestIsTheirs:
    def test_the_rest_goes_to_the_bottom_of_their_library(self, builder):
        game, src = board(builder, [FOREST, SOL_RING, BEAR, "island"])
        yours = list(game.state.players[0].library)

        run(game, [LONIS], src)

        assert library_ids(game, 1)[0] == "island", "the card under the window stays on top"
        assert sorted(library_ids(game, 1)[1:]) == sorted([FOREST, BEAR])
        assert game.state.players[0].library == yours, "your library is not touched"


class TestTheLoader:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_look_at_top_steal_probe",
                "name": "Look At Top Steal Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "targets": [{"id": "t1", "kind": "player", "selector": {"controller": "opponent"}}],
                "spell_effects": [effect],
            }
        )

    def test_loniss_shape_loads(self):
        compile_card(self._card(LONIS))

    def test_controller_needs_the_battlefield(self):
        with pytest.raises(DslError, match="'controller' is \"you\""):
            compile_card(self._card({**LONIS, "destination": "hand"}))

    def test_controller_is_only_you(self):
        with pytest.raises(DslError, match="'controller' is \"you\""):
            compile_card(self._card({**LONIS, "controller": "opponent"}))

    def test_controller_is_refused_with_cast_free(self):
        free = {k: v for k, v in LONIS.items() if k != "destination"}
        with pytest.raises(DslError, match="'controller' is \"you\""):
            compile_card(self._card({**free, "cast_free": True}))

    def test_a_step_to_the_battlefield_admits_it(self):
        stepped = {k: v for k, v in LONIS.items() if k not in ("destination", "objects")}
        compile_card(
            self._card({**stepped, "destinations": [{"to": "battlefield", "count": 1}]})
        )

    def test_steps_that_never_reach_the_battlefield_refuse_it(self):
        stepped = {k: v for k, v in LONIS.items() if k not in ("destination", "objects")}
        with pytest.raises(DslError, match="'controller' is \"you\""):
            compile_card(self._card({**stepped, "destinations": [{"to": "hand", "count": 1}]}))


class TestThePrintedCard:
    def test_lonis_steals_a_card_off_the_top_of_their_library(self, builder):
        game = (
            builder(players=2, seed=0)
            .battlefield(0, ["lonis_cryptozoologist", "clue_token", "clue_token"])
            .library(0, ["island"] * 10)
            .library(1, [FOREST, SOL_RING, BEAR, "island"])
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        lonis = only_oid(game, "lonis_cryptozoologist", 0)

        game.apply(activations(game, lonis)[0])
        assert game.pending().kind is DecisionKind.CHOOSE_X
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 2)
        )
        ring = the(game, SOL_RING).oid
        pass_until(game, lambda g: g.pending().kind is DecisionKind.CHOOSE_OBJECTS)
        offered = [o.ref.id for o in game.pending().options if o.ref is not None]
        assert offered == [ring], "the Forest is a land; only the top two were revealed"
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 0)
        )
        settle(game)

        assert oids_of(game, "clue_token", 0) == [], "both Clues were the cost"
        assert the(game, SOL_RING).controller == 0
        assert the(game, SOL_RING).owner == 1
        assert SOL_RING in battlefield_ids(game, 0)
