"""A free cast of a target card out of a graveyard, exiled instead of graveyarded.

    Torrential Gearhulk -- "When this creature enters, you may cast target
    instant card from your graveyard without paying its mana cost. If that
    spell would be put into your graveyard, exile it instead."

    Impulsivity -- the same sentence over "a graveyard", any player's.

`cast_from_hand` with ``objects: {"target": …}`` already made the free cast out
of a graveyard (601.2, 608.2g). The second sentence is a replacement on the
**spell** (614.1a), the one `cast_card`'s and `play_exiled`'s ``exiles`` puts on
the stack item (`StackItem.exiles_instead`), so it holds however the spell
leaves the stack for a graveyard -- resolving or being countered. Without it the
instant goes back to the graveyard to be flashed back again by the next
Gearhulk, a strictly better card. `cast_card` is the near miss and charges the
mana cost; `play_exiled` is free but reads its pool out of exile.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import action_for_card, only_oid, pass_until, settle

GEARHULK = "t_fcei_gearhulk"
IMPULSE = "t_fcei_impulse"
INSIGHT = "t_fcei_insight"  # Instant -- draw two cards.


def position(builder, *, creature=GEARHULK, mine=(INSIGHT,), theirs=(), hand1=()):
    """Seat 0 with ``creature`` in hand, an Island and a Mountain, and ``mine`` in
    the graveyard; seat 1 with two Islands, ``theirs`` in the graveyard and
    ``hand1``. Seat 0's precombat main, with priority. Returns ``(game, oid)`` of seat
    0's first graveyard card, or seat 1's when seat 0 has none."""
    game = (
        builder(players=2)
        .battlefield(0, ["island", "mountain"])
        .battlefield(1, ["island", "island"])
        .hand(0, [creature])
        .hand(1, list(hand1))
        .graveyard(0, list(mine))
        .graveyard(1, list(theirs))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .active(0)
        .step(Step.UNTAP)
        .build()
    )
    pass_until(
        game,
        lambda g: g.state.step is Step.PRECOMBAT_MAIN
        and g.pending() is not None
        and g.pending().player == 0,
    )
    pile = game.state.players[0].graveyard or game.state.players[1].graveyard
    return game, pile[0]


def enter_and_offer(game, creature=GEARHULK) -> None:
    """Cast ``creature`` and pass until its trigger's free-cast choice is asked."""
    game.apply(action_for_card(game, ActionKind.CAST, creature))
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().kind is DecisionKind.CHOOSE_OBJECTS
        and g.pending().context.get("purpose") == "cast_from_hand",
    )


def take(game, oid: int) -> None:
    decision = game.pending()
    index = next(i for i, o in enumerate(decision.options) if o.value == oid)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )


def zone_of(game, oid) -> Zone:
    return game.state.objects[oid].zone


class TestTheSpellIsExiled:
    def test_resolved_it_is_exiled_not_returned(self, builder):
        game, insight = position(builder)
        hand = len(game.state.players[0].hand)
        enter_and_offer(game)
        take(game, insight)
        settle(game)

        # The Gearhulk left the hand; the Insight resolved and drew two.
        assert len(game.state.players[0].hand) == hand - 1 + 2
        assert zone_of(game, insight) is Zone.EXILE
        assert insight not in game.state.players[0].graveyard

    def test_countered_it_is_exiled(self, builder):
        game, insight = position(builder, hand1=("t_counterspell",))
        enter_and_offer(game)
        take(game, insight)
        pass_until(game, lambda g: g.pending().player == 1)
        assert game.state.stack[-1].exiles_instead
        game.apply(action_for_card(game, ActionKind.CAST, "t_counterspell"))
        settle(game)

        assert any(e.type == "spell_countered" for e in game.state.events)
        assert zone_of(game, insight) is Zone.EXILE

    def test_it_is_free(self, builder):
        """The Island paid for the creature; the {2}{U} Insight was cast with
        one Mountain left, so it cost nothing."""
        game, insight = position(builder)
        enter_and_offer(game)
        take(game, insight)
        assert any(
            e.type == "spell_cast" and e.data.get("card") == INSIGHT and e.data.get("free")
            for e in game.state.events
        )


class TestTheBoundary:
    def test_declined_the_card_stays_in_the_graveyard(self, builder):
        game, insight = position(builder)
        enter_and_offer(game)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        settle(game)
        assert zone_of(game, insight) is Zone.GRAVEYARD

    def test_without_exiles_it_returns_to_the_graveyard(self, builder):
        """The rider is the key's, not the op's: the same cast without it is
        an ordinary free spell."""
        game, insight = position(builder)
        ctx = EffectContext(
            state=game.state,
            controller=0,
            source_oid=None,
            targets={"t1": (TargetRef.obj(insight),)},
            bindings={},
        )
        gen = execute(ctx, [{"op": "cast_from_hand", "objects": {"target": "t1"}}])
        decision = next(gen)
        with pytest.raises(StopIteration):
            gen.send([next(i for i, o in enumerate(decision.options) if o.value == insight)])
        assert not game.state.stack[-1].exiles_instead
        settle(game)
        assert zone_of(game, insight) is Zone.GRAVEYARD

    def test_an_opponents_card_goes_to_its_owners_exile(self, builder):
        """Impulsivity: "a graveyard". The caster controls the spell; its owner
        keeps the card (108.3), so the replacement exiles it to the owner."""
        game, theirs = position(builder, creature=IMPULSE, mine=(), theirs=(INSIGHT,))
        enter_and_offer(game, IMPULSE)
        take(game, theirs)
        assert any(
            e.type == "spell_cast" and e.data.get("card") == INSIGHT and e.player == 0
            for e in game.state.events
        )
        settle(game)
        assert zone_of(game, theirs) is Zone.EXILE
        assert game.state.objects[theirs].owner == 1
        assert theirs not in game.state.players[1].graveyard
        assert only_oid(game, IMPULSE, 0)


class TestTheLoader:
    def _probe(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_fcei_probe",
                "name": "Exiles Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_the_printed_form_loads(self):
        compile_card(self._probe({"op": "cast_from_hand", "exiles": True}))

    @pytest.mark.parametrize("value", ["false", 1, None])
    def test_a_non_boolean_is_refused(self, value):
        with pytest.raises(DslError, match="exiles"):
            compile_card(self._probe({"op": "cast_from_hand", "exiles": value}))
