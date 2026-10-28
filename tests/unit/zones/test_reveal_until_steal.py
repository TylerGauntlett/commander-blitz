"""`reveal_until` on an opponent's library, the hit entering under *your* control.

    Jhoira, Weatherlight Corsair — "Whenever Jhoira enters or attacks, target
    opponent reveals cards from the top of their library until they reveal a
    historic permanent card. You put that card onto the battlefield under your
    control and lose life equal to that permanent's mana value. That player puts
    the rest of the revealed cards on the bottom of their library in a random
    order."

Two seats are named and the sentence splits between them:

- **The library and the rest are the opponent's.** The walk is over their
  library, and "the rest" goes back to the bottom of *that* library -- the
  scanned seat, exactly as a reveal from your own library bottoms yours.
- **The permanent is yours.** Rule 110.2: a permanent's controller is by
  default whoever put it onto the battlefield, but an effect that says "under
  your control" decides it. Without ``controller: "you"`` the match enters
  under the seat whose library was scanned (which is right for every card that
  reveals from its own library), and Jhoira would hand the opponent a free
  permanent.

"That permanent's mana value" is the op's ``as`` binding read by
``{"mana_value_of": {"objects": {"binding": …}}}``; a scan that finds nothing
binds the empty list and the loss is zero.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import action_for_card, battlefield_ids, library_ids, settle

FOREST = "forest"
BEAR = "t_bear"
SOL_RING = "sol_ring"  # an artifact, mana value 1
BARKTOOTH = "barktooth_warbeard"  # a legendary creature, mana value 7
SAGA = "oath_of_eorl"  # a Saga, mana value 5

HISTORIC_PERMANENT = {
    "any_types": ["Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"],
    "any_of": [
        {"types": ["Artifact"]},
        {"supertypes": ["Legendary"]},
        {"subtypes": ["Saga"]},
    ],
}

JHOIRA = [
    {
        "op": "reveal_until",
        "player": {"target": "t1"},
        "objects": HISTORIC_PERMANENT,
        "destination": "battlefield",
        "controller": "you",
        "as": "stolen",
    },
    {"op": "lose_life", "amount": {"mana_value_of": {"objects": {"binding": "stolen"}}}},
]


def board(builder, library: list[str]):
    """Seat 1's library is stacked; seat 0 controls the source and targets seat 1."""
    game = (
        builder(players=2, seed=0)
        .battlefield(0, [FOREST])
        .library(1, library)
        .build(advance=False)
    )
    src = next(o.oid for o in game.state.battlefield_objects(0))
    return game, src


def run(game, effects: list[dict], source: int) -> EffectContext:
    ctx = EffectContext(
        state=game.state,
        controller=0,
        source_oid=source,
        targets={"t1": (TargetRef.player(1),)},
    )
    for _ in execute(ctx, effects):  # pragma: no cover - the loop body is the failure
        raise AssertionError("reveal_until asked a decision; it takes none")
    return ctx


class TestTheHitIsYours:
    def test_it_enters_under_your_control_from_their_library(self, builder):
        game, src = board(builder, [FOREST, BEAR, SOL_RING, FOREST])

        run(game, JHOIRA, src)

        assert SOL_RING in battlefield_ids(game, 0)
        assert SOL_RING not in battlefield_ids(game, 1)
        ring = next(o for o in game.state.battlefield_objects(0) if o.def_id == SOL_RING)
        assert ring.owner == 1, "control changes, ownership does not"

    def test_without_the_key_it_enters_under_the_scanned_seat(self, builder):
        """The contrast: every own-library reveal, and the bug Jhoira would be."""
        game, src = board(builder, [FOREST, SOL_RING])
        plain = dict(JHOIRA[0])
        plain.pop("controller")

        run(game, [plain], src)

        assert SOL_RING in battlefield_ids(game, 1)
        assert SOL_RING not in battlefield_ids(game, 0)

    def test_the_rest_goes_to_the_bottom_of_their_library(self, builder):
        game, src = board(builder, [FOREST, BEAR, SOL_RING, BARKTOOTH])
        yours = list(game.state.players[0].library)

        run(game, JHOIRA, src)

        assert library_ids(game, 1)[0] == BARKTOOTH, "the scan stopped at the ring"
        assert sorted(library_ids(game, 1)[1:]) == sorted([FOREST, BEAR])
        assert game.state.players[0].library == yours, "your library is not touched"


class TestYouLoseItsManaValue:
    @pytest.mark.parametrize(("card", "mv"), [(SOL_RING, 1), (BARKTOOTH, 7), (SAGA, 5)])
    def test_the_loss_reads_the_permanent_put_down(self, builder, card, mv):
        game, src = board(builder, [BEAR, card])
        before = (game.state.players[0].life, game.state.players[1].life)

        run(game, JHOIRA, src)

        assert card in battlefield_ids(game, 0)
        assert game.state.players[0].life == before[0] - mv
        assert game.state.players[1].life == before[1], "the opponent loses nothing"

    def test_a_nonhistoric_creature_is_walked_past(self, builder):
        game, src = board(builder, [BEAR, FOREST, BARKTOOTH])

        run(game, JHOIRA, src)

        assert BEAR not in battlefield_ids(game, 0)
        assert BARKTOOTH in battlefield_ids(game, 0)

    def test_no_historic_card_costs_nothing(self, builder):
        game, src = board(builder, [BEAR, FOREST])
        before = game.state.players[0].life

        ctx = run(game, JHOIRA, src)

        assert ctx.bindings["stolen"] == []
        assert game.state.players[0].life == before
        assert battlefield_ids(game, 0) == [FOREST]
        assert sorted(library_ids(game, 1)) == sorted([BEAR, FOREST])


class TestThePrintedCard:
    def test_jhoira_entering_steals_and_costs_its_mana_value(self, builder):
        game = (
            builder(players=2, seed=0)
            .battlefield(0, ["swamp"] * 6)
            .hand(0, ["jhoira_weatherlight_corsair"])
            .library(1, [FOREST, BEAR, BARKTOOTH, FOREST])
            .build()
        )
        before = game.state.players[0].life

        game.apply(action_for_card(game, ActionKind.CAST, "jhoira_weatherlight_corsair"))
        settle(game)

        assert BARKTOOTH in battlefield_ids(game, 0)
        assert BARKTOOTH not in battlefield_ids(game, 1)
        assert game.state.players[0].life == before - 7


class TestTheLoader:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_reveal_until_steal_probe",
                "name": "Reveal Until Steal Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "targets": [{"id": "t1", "kind": "player", "selector": {"controller": "opponent"}}],
                "spell_effects": [effect],
            }
        )

    def test_jhoiras_shape_loads(self):
        compile_card(self._card(JHOIRA[0]))

    def test_controller_needs_the_battlefield(self):
        to_hand = {**JHOIRA[0], "destination": "hand"}
        with pytest.raises(DslError, match="'controller' is \"you\""):
            compile_card(self._card(to_hand))

    def test_controller_is_only_you(self):
        with pytest.raises(DslError, match="'controller' is \"you\""):
            compile_card(self._card({**JHOIRA[0], "controller": "opponent"}))
