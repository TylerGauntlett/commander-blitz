"""Espers to Magicite — "choose up to one target creature **card exiled this way**".

    Exile each opponent's graveyard. When you do, choose up to one target
    creature card exiled this way. Create a token that's a copy of that card…

A target in **exile**, which the target language had no word for. The five kinds
were `permanent`, `player`, `spell`, `card_in_graveyard` and `any`, and the
missing one is not cosmetic: the kind is what the rest of the engine reads a
target *by*, and a card in exile is not a permanent (110.1).

Written `kind: "permanent"` with an exile selector the card would have *worked*
— `candidates` falls through to the selector for any kind it does not name — and
would have gone on calling the thing it targets something it is not. That is the
quiet state this loader refuses everywhere else, so the three zone/kind pairs now
have to agree: a `permanent` target is on the battlefield, a `card_in_graveyard`
is in a graveyard, a `card_in_exile` is in exile. No card in the pool wrote a
mismatched one, so the refusals cost nothing and close the door.

**608.2b is re-asked with the selector, not just the zone.** `card_in_graveyard`
above checks only that the card is still in a graveyard, and can: it names a card
by its printed face, which does not change while it lies there. An exile spec
names one by *where it came from* — "exiled **this way**" — which is a binding,
and a binding is exactly the sort of clause the re-check exists for.

`t_wide_magicite` is the counterfactual: the same target line without the
binding, which reaches every creature card anybody has ever exiled.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import exile as exile_object

MAGICITE = "t_magicite"
WIDE = "t_wide_magicite"
BEAR = "t_bear"
DORK = "t_dork"


def board(builder, card: str = MAGICITE, *, stranded: str | None = None):
    """Their graveyard holds a creature; `stranded` was exiled long before.

    The stranded card is what separates the two readings: it is a creature card
    in exile that this spell did not put there.
    """
    game = (
        builder(players=2)
        .hand(0, [card, "forest"])
        .battlefield(0, ["swamp"] * 4)
        .graveyard(1, [BEAR, "forest"])
        .graveyard(0, [stranded] if stranded else [])
        .library(0, ["forest"] * 10)
        .build()
    )
    if stranded:
        exile_object(game.state, game.state.players[0].graveyard[0], cause="test")
    return game


def cast(game, card: str):
    """Cast it and take the target the reflexive half offers.

    The target is "up to one", so declining is always on the menu and is the
    last option -- these tests are about which cards are *on* that menu.
    """
    state = game.state
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and state.card(a.source).id == card
    )
    game.apply(action)
    for _ in range(20):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.PRIORITY:
            break
        actions = game.legal_actions()
        if not actions:
            break
        game.apply(actions[0])
    return game


def mine(game, pid: int = 0):
    state = game.state
    return sorted(state.card_of(o).id for o in state.battlefield_objects(pid))


class TestItTargetsACardInExile:
    def test_the_exiled_creature_comes_back_under_your_control(self, builder):
        game = cast(board(builder), MAGICITE)
        assert BEAR in mine(game)

    def test_the_land_it_exiled_is_not_a_legal_choice(self, builder):
        """"…target **creature** card" -- the selector still narrows."""
        game = cast(board(builder), MAGICITE)
        assert "forest" not in mine(game)

    def test_the_card_leaves_exile(self, builder):
        game = cast(board(builder), MAGICITE)
        left = [game.state.card(o).id for o in game.state.players[1].exile]
        assert left == ["forest"]


class TestExiledThisWay:
    def test_a_card_exiled_earlier_is_not_reachable(self, builder):
        """The binding is the whole clause. A creature card that was already
        sitting in exile is not one this spell put there."""
        game = cast(board(builder, stranded=DORK), MAGICITE)
        assert DORK not in mine(game)
        assert BEAR in mine(game)

    def test_without_the_binding_it_is(self, builder):
        """The counterfactual: the same line reading "target creature card in
        exile", which is a strictly wider card."""
        game = cast(board(builder, WIDE, stranded=DORK), WIDE)
        assert DORK in mine(game) or BEAR in mine(game)
        assert len(mine(game)) == 5  # four Swamps and whichever card it took

    def test_the_wide_version_offers_the_stranded_card(self, builder):
        """Named directly, since which of the two it then takes is a choice."""
        from commanderblitz.engine.targeting import candidates

        game = board(builder, WIDE, stranded=DORK)
        state = game.state
        spec = state.registry.get(WIDE).abilities[0].targets[0]
        offered = [state.card(ref.id).id for ref in candidates(state, 0, spec, None)]
        assert offered == [DORK]

    def test_the_narrow_version_offers_nothing_before_it_exiles(self, builder):
        """The same board, the same moment, the binding empty: the printed card
        can only ever reach what its own first sentence put in exile."""
        from commanderblitz.engine.targeting import candidates

        game = board(builder, MAGICITE, stranded=DORK)
        state = game.state
        spec = state.registry.get(MAGICITE).abilities[0].targets[0]
        assert candidates(state, 0, spec, None) == []


class TestTheKindAndTheZoneMustAgree:
    def _spec(self, kind: str, zone: str | None):
        selector: dict = {"types": ["Creature"]}
        if zone is not None:
            selector["zone"] = zone
        return CardModel.model_validate(
            {
                "id": "t_bad_target",
                "name": "Test Bad Target",
                "oracle_text": "Destroy target creature.",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "targets": [
                    {"id": "t1", "kind": kind, "count": 1, "selector": selector}
                ],
                "spell_effects": [{"op": "destroy", "objects": {"target": "t1"}}],
            }
        )

    def test_a_permanent_target_in_exile_is_refused(self):
        """It would have worked, and gone on calling a card a permanent."""
        with pytest.raises(DslError, match="is on the battlefield"):
            compile_card(self._spec("permanent", "exile"), source="test")

    def test_a_permanent_target_in_a_graveyard_is_refused(self):
        with pytest.raises(DslError, match="is on the battlefield"):
            compile_card(self._spec("permanent", "graveyard"), source="test")

    def test_a_card_in_exile_target_in_a_graveyard_is_refused(self):
        with pytest.raises(DslError, match="'card_in_exile' target is in exile"):
            compile_card(self._spec("card_in_exile", "graveyard"), source="test")

    def test_a_card_in_graveyard_target_in_exile_is_refused(self):
        with pytest.raises(DslError, match="is in a graveyard"):
            compile_card(self._spec("card_in_graveyard", "exile"), source="test")

    def test_the_zone_may_be_left_out(self):
        """The kind already said it, so every shipped card omits it."""
        compile_card(self._spec("card_in_exile", None), source="test")
        compile_card(self._spec("permanent", None), source="test")
        compile_card(self._spec("permanent", "battlefield"), source="test")


class TestItIsRecheckedOnResolution:
    def test_a_card_that_left_exile_is_no_longer_legal(self, builder, registry):
        """608.2b. The zone half of the re-check."""
        from commanderblitz.engine.structs import TargetRef
        from commanderblitz.engine.targeting import still_legal

        game = board(builder)
        state = game.state
        oid = state.players[1].graveyard[0]
        exile_object(state, oid, cause="test")
        spec = registry.get(WIDE).abilities[0].targets[0]
        ref = TargetRef.obj(oid)
        assert still_legal(state, 0, spec, ref, None)
        state.objects[oid].zone = Zone.GRAVEYARD
        assert not still_legal(state, 0, spec, ref, None)

    def test_a_card_the_binding_no_longer_names_is_not_legal(self, builder, registry):
        """The selector half, which `card_in_graveyard` does not ask and this
        kind must: "exiled **this way**" is a binding."""
        from commanderblitz.engine.structs import TargetRef
        from commanderblitz.engine.targeting import still_legal

        game = board(builder)
        state = game.state
        oid = state.players[1].graveyard[0]
        exile_object(state, oid, cause="test")
        spec = registry.get(MAGICITE).abilities[0].targets[0]
        ref = TargetRef.obj(oid)
        assert still_legal(state, 0, spec, ref, None, bindings={"banished": [oid]})
        assert not still_legal(state, 0, spec, ref, None, bindings={"banished": []})
