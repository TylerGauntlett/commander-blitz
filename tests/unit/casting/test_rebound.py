"""Rebound — suspend's second half, reached from the other direction.

    "Rebound (If you cast this spell from your hand, exile it as it resolves. At
    the beginning of your next upkeep, you may cast this card from exile without
    paying its mana cost.)"

Two halves, and both were nearly there.

The **exile** is the third rider on the destination a resolving spell goes to,
beside flashback's exile and buyback's hand — and like both it only ever
replaces the *graveyard*, which is why `rebound` on a permanent card is refused
rather than accepted: a permanent enters the battlefield and never reaches the
rider at all, so the card would load, look implemented and never rebound once.

The **free cast** is suspend's, word for word: "cast this card from exile
without paying its mana cost". `cast_for_free` is shared rather than copied.

What is genuinely new is one clause, and it is the loop guard: **"if you cast
this spell from your hand"**. The free cast happens from *exile*, so without it
a rebounded spell rebounds again, every upkeep, for the rest of the game. It
takes two things to close, and the tests below pin both:

- `cast_from_hand`, recorded by `push_spell` — the only moment the zone is
  still knowable, since by resolution every spell is on the stack and looks
  alike;
- clearing the mark **before** the free cast rather than after, since that cast
  is itself a cast and would otherwise re-arm the card as it resolved.

*Divergences, shared with suspend and recorded in rules-coverage.md*: the free
cast is mandatory rather than "you **may** cast", and its targets are the first
legal tuple rather than a choice — both because the upkeep tick runs from the
turn structure, which cannot stop to ask. The assertions below are therefore
about *that the card was cast again for nothing*, not about where it pointed.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, pass_until

MOUNTAIN = "mountain"
BOLT = "t_rebounder"


def position(builder):
    return (
        builder(players=2)
        .battlefield(0, [MOUNTAIN] * 3)
        .hand(0, [BOLT])
        .library(0, [MOUNTAIN] * 20)
        .library(1, [MOUNTAIN] * 20)
        .build()
    )


def cast_it(game):
    """Cast the Bolt at the opponent.

    Chosen explicitly rather than taking the first cast action: `kind: "any"`
    enumerates every permanent and player, and the free cast later picks its own
    target, so a test that read life totals off "whatever was first" would be
    measuring the enumeration order.
    """
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == BOLT
        and any(t.kind == "player" and t.id == 1 for t in a.targets)
    )
    oid = action.source
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)
    return oid


def run_to_turn(game, turn: int, limit: int = 900):
    for _ in range(limit):
        if game.state.turn >= turn and game.state.step is Step.PRECOMBAT_MAIN:
            return
        decision = game.pending()
        if decision is None:
            return
        game.apply(_default_answer(game, decision))


class TestTheExileRider:
    def test_it_goes_to_exile_rather_than_the_graveyard(self, builder):
        game = position(builder)
        bolt = cast_it(game)

        assert game.state.objects[bolt].zone is Zone.EXILE

    def test_it_is_marked_for_its_controller(self, builder):
        game = position(builder)
        bolt = cast_it(game)

        assert game.state.objects[bolt].rebound_by == 0

    def test_the_spell_still_did_what_it_says(self, builder):
        game = position(builder)
        life = game.state.players[1].life
        cast_it(game)

        assert game.state.players[1].life == life - 2


def free_casts(game, oid: int) -> int:
    return sum(
        1
        for e in game.state.events
        if e.type == "spell_cast" and e.source == oid and e.data.get("free") == 1
    )


class TestTheFreeCast:
    def test_it_is_cast_again_at_your_next_upkeep(self, builder):
        game = position(builder)
        bolt = cast_it(game)

        run_to_turn(game, 3)

        assert free_casts(game, bolt) == 1

    def test_it_costs_nothing(self, builder):
        """Every land was spent on the first cast, so nothing could have paid."""
        game = (
            builder(players=2)
            .battlefield(0, [MOUNTAIN])
            .hand(0, [BOLT])
            .library(0, [MOUNTAIN] * 20)
            .library(1, [MOUNTAIN] * 20)
            .build()
        )
        bolt = cast_it(game)
        assert all(o.tapped for o in game.state.battlefield_objects(0))

        run_to_turn(game, 3)

        assert free_casts(game, bolt) == 1

    def test_it_goes_to_the_graveyard_the_second_time(self, builder):
        """The loop guard. Cast from exile, so the rider does not fire again."""
        game = position(builder)
        bolt = cast_it(game)

        run_to_turn(game, 3)

        assert game.state.objects[bolt].zone is Zone.GRAVEYARD
        assert game.state.objects[bolt].rebound_by is None

    def test_it_does_not_rebound_for_ever(self, builder):
        """The loop guard, over four of your upkeeps."""
        game = position(builder)
        bolt = cast_it(game)

        run_to_turn(game, 9)

        assert free_casts(game, bolt) == 1, "once, not once a turn"


class TestTheLoaderGuard:
    def _card(self, **extra) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_rebound_probe",
                "name": "Rebound Probe",
                "mana_cost": "{R}",
                "rebound": True,
                "spell_effects": [{"op": "draw", "player": "you"}],
                **extra,
            }
        )

    def test_an_instant_loads(self):
        compile_card(self._card(types=["Instant"]))

    def test_a_sorcery_loads(self):
        compile_card(self._card(types=["Sorcery"]))

    def test_a_permanent_is_refused(self):
        """It enters the battlefield, so the rider never fires -- silently."""
        with pytest.raises(DslError, match="only means anything on an instant or sorcery"):
            compile_card(self._card(types=["Creature"], power=1, toughness=1))
