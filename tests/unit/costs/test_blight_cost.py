"""Blight N as a cost -- -1/-1 counters on a creature the *payer* chooses.

"To blight N, a player puts N -1/-1 counters on a creature they control."
(Lorwyn Eclipsed.) Three printed homes, one cost key:

- an optional additional cost to cast -- Burning Curiosity's "you may blight 1",
  read back by ``additional_paid`` ("if this spell's additional cost was paid");
- a ward cost -- Auntie Ool, Cursewretch's "Ward--Blight 2", which the
  *targeting opponent* pays, onto a creature of their own;
- an activated ability's cost.

`put_counters` is the near miss and the wrong card on all three. It puts the
counters on the cost's own source and asks nothing, so as Auntie Ool's ward cost
it would shrink Auntie Ool herself, and on a spell it has no permanent to put
anything on. Blight's creature is chosen by whoever pays, at payment time
(601.2h), among the creatures *they* control -- which is why the pool is built
around the paying seat and never around the source's controller.

Three rules the tests hold:

- **Payable only with a creature to blight.** No creature, no payment: the cast
  line, the activation and the ward "yes" are all withheld rather than offered
  and then charged nothing.
- **A creature that can't have -1/-1 counters is not a candidate**, for
  `put_counters`' reason (Melira's ruling): a cost is paid only by doing all of
  it, so a board of nothing but such creatures cannot pay.
- **It is a placement** (122.6). Through `add_counters`, so it raises
  `counter_placed` put by the payer -- which is what Auntie Ool's own second
  ability watches.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import activations, only_oid, pass_until, settle

CURIOSITY = "t_blight_curiosity"  # Burning Curiosity: "you may blight 1", exile 2 or 3
OOL = "t_blight_ool"  # Auntie Ool: Ward--Blight 2, and the -1/-1 counter trigger
ENGINE = "t_blight_engine"  # a 3/3 with "Blight 1: Draw a card."
ROCK = "t_blight_rock"  # the same ability on a noncreature artifact
BEAR = "t_bear"  # a vanilla 2/2
OX = "t_chc_bear"  # another vanilla 2/2, so two candidates
WARD = "t_chc_ward"  # "Creatures you control can't have -1/-1 counters put on them."
BOLT = "t_bolt"  # {R} instant, 3 damage to a creature


def main_phase(builder, mine=(), theirs=(), hand=()):
    game = (
        builder(players=2)
        .battlefield(0, ["mountain"] * 3 + list(mine))
        .battlefield(1, ["mountain"] * 2 + list(theirs))
        .hand(0, list(hand))
        .hand(1, [BOLT])
        .library(0, ["mountain"] * 20)
        .library(1, ["mountain"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def minus(game, oid: int) -> int:
    return game.state.objects[oid].counter("-1/-1")


def choose(game, oid: int) -> None:
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS, decision
    assert decision.context.get("purpose") == "blight_cost"
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE
            and (a.choice == oid or any(ref.id == oid for ref in a.targets))
        )
    )


def cast_lines(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


class TestAnActivatedAbilityCost:
    def test_the_source_may_blight_itself(self, builder):
        """"A creature you control" -- the only one is the source, and it counts."""
        game = main_phase(builder, mine=(ENGINE,))
        engine = only_oid(game, ENGINE, 0)
        game.apply(activations(game, engine)[0])
        assert minus(game, engine) == 1

    def test_no_creature_means_no_activation(self, builder):
        game = main_phase(builder, mine=(ROCK,))
        assert not activations(game, only_oid(game, ROCK, 0))

    def test_an_opponents_creature_does_not_pay(self, builder):
        """"A creature **they** control": P1's Bear is no fodder for P0."""
        game = main_phase(builder, mine=(ROCK,), theirs=(BEAR,))
        assert not activations(game, only_oid(game, ROCK, 0))

    def test_the_payer_chooses_and_one_creature_takes_them_all(self, builder):
        game = main_phase(builder, mine=(ROCK, BEAR, OX))
        bear, ox = only_oid(game, BEAR, 0), only_oid(game, OX, 0)
        game.apply(activations(game, only_oid(game, ROCK, 0))[0])
        choose(game, ox)
        assert (minus(game, bear), minus(game, ox)) == (0, 1)

    def test_the_counter_is_on_while_the_ability_waits(self, builder):
        """A cost, so it is paid as the ability goes on the stack (602.2b) --
        the Bolt in P1's hand keeps the engine from auto-passing it away."""
        game = main_phase(builder, mine=(ROCK, BEAR))
        bear = only_oid(game, BEAR, 0)
        hand = len(game.state.players[0].hand)
        game.apply(activations(game, only_oid(game, ROCK, 0))[0])
        assert game.state.stack and minus(game, bear) == 1
        settle(game)
        assert len(game.state.players[0].hand) == hand + 1

    def test_it_raises_counter_placed_put_by_the_payer(self, builder):
        game = main_phase(builder, mine=(ROCK, BEAR))
        bear = only_oid(game, BEAR, 0)
        mark = len(game.state.events)
        game.apply(activations(game, only_oid(game, ROCK, 0))[0])
        placed = [e for e in game.state.events[mark:] if e.type == EventType.COUNTER_PLACED]
        assert [(e.data["oid"], e.data["counter"], e.data["put_by"]) for e in placed] == [
            (bear, "-1/-1", 0)
        ]

    def test_a_creature_that_cannot_have_the_counters_is_not_a_candidate(self, builder):
        """Melira's ruling: the placement would not happen, so it cannot pay."""
        game = main_phase(builder, mine=(ROCK, BEAR, WARD))
        assert not activations(game, only_oid(game, ROCK, 0))


class TestAnOptionalAdditionalCost:
    """Burning Curiosity: "you may blight 1 … if this spell's additional cost
    was paid, exile the top three cards instead"."""

    def test_both_lines_with_a_creature(self, builder):
        game = main_phase(builder, mine=(BEAR,), hand=(CURIOSITY,))
        assert sorted({a.additional_times for a in cast_lines(game, CURIOSITY)}) == [0, 1]

    def test_only_the_unpaid_line_without_one(self, builder):
        game = main_phase(builder, hand=(CURIOSITY,))
        assert sorted({a.additional_times for a in cast_lines(game, CURIOSITY)}) == [0]

    def test_paying_blights_and_exiles_three(self, builder):
        game = main_phase(builder, mine=(BEAR,), hand=(CURIOSITY,))
        bear = only_oid(game, BEAR, 0)
        game.apply(next(a for a in cast_lines(game, CURIOSITY) if a.additional_times == 1))
        assert minus(game, bear) == 1, "paid on casting, not on resolution"
        settle(game)
        assert len(game.state.players[0].exile) == 3

    def test_declining_exiles_two_and_blights_nothing(self, builder):
        game = main_phase(builder, mine=(BEAR,), hand=(CURIOSITY,))
        bear = only_oid(game, BEAR, 0)
        game.apply(next(a for a in cast_lines(game, CURIOSITY) if a.additional_times == 0))
        settle(game)
        assert (minus(game, bear), len(game.state.players[0].exile)) == (0, 2)


def bolt_ool(game) -> None:
    """P1 points the Bolt at Auntie Ool and the ward trigger goes on the stack."""
    ool = only_oid(game, OOL, 0)

    def offer(g):
        return next(
            (
                a
                for a in g.legal_actions()
                if a.kind is ActionKind.CAST
                and g.state.objects[a.source].def_id == BOLT
                and any(ref.id == ool for ref in a.targets)
            ),
            None,
        )

    pass_until(game, lambda g: offer(g) is not None)
    game.apply(offer(game))


def ward_prompt(game):
    pass_until(
        game,
        lambda g: ((d := g.pending()) is not None and d.kind is DecisionKind.MAY)
        or (not g.state.stack and not g.state.pending_triggers),
    )
    decision = game.pending()
    return decision if decision is not None and decision.kind is DecisionKind.MAY else None


class TestAWardCost:
    """Auntie Ool: "Ward--Blight 2", paid by the player who targeted her."""

    def test_the_targeting_opponent_blights_their_own_creature(self, builder):
        game = main_phase(builder, mine=(OOL, OX), theirs=(BEAR,))
        ool, ox = only_oid(game, OOL, 0), only_oid(game, OX, 0)
        bear = only_oid(game, BEAR, 1)
        bolt_ool(game)
        decision = ward_prompt(game)
        assert decision is not None and decision.player == 1
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
        # Two -1/-1 counters on P1's 2/2, none on Ool or on P0's creature.
        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert (minus(game, ool), minus(game, ox)) == (0, 0)

    def test_paying_lets_the_spell_resolve(self, builder):
        game = main_phase(builder, mine=(OOL,), theirs=(BEAR,))
        ool = only_oid(game, OOL, 0)
        bolt_ool(game)
        assert ward_prompt(game) is not None
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
        settle(game)
        assert game.state.objects[ool].damage == 3

    def test_a_payer_with_no_creature_is_not_asked_and_the_spell_is_countered(self, builder):
        game = main_phase(builder, mine=(OOL,))
        ool = only_oid(game, OOL, 0)
        bolt_ool(game)
        assert ward_prompt(game) is None
        assert game.state.objects[ool].damage == 0

    def test_ools_trigger_reads_the_blight(self, builder):
        """The ward payment is a placement, so Ool's own second ability sees it:
        the counters went on a creature Ool's controller doesn't control, so
        that creature's controller -- the payer -- loses 1 life."""
        game = main_phase(builder, mine=(OOL,), theirs=(BEAR,))
        life = game.state.players[1].life
        bolt_ool(game)
        assert ward_prompt(game) is not None
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
        settle(game)
        assert game.state.players[1].life == life - 1


class TestOolsTriggerOnHerControllersSide:
    def test_a_blight_of_your_own_draws(self, builder):
        game = main_phase(builder, mine=(OOL, ROCK, BEAR))
        hand = len(game.state.players[0].hand)
        game.apply(activations(game, only_oid(game, ROCK, 0))[0])
        choose(game, only_oid(game, BEAR, 0))
        settle(game)
        # One from the Rock's ability, one from Ool's trigger.
        assert len(game.state.players[0].hand) == hand + 2


class TestTheLoader:
    def _card(self, cost):
        return CardModel.model_validate(
            {
                "id": "t_blight_probe",
                "name": "Blight Probe",
                "mana_cost": "{1}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "activated",
                        "cost": cost,
                        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                    }
                ],
            }
        )

    def test_a_negative_blight_is_refused(self):
        with pytest.raises(DslError, match="blight"):
            compile_card(self._card({"blight": -1}))

    def test_blight_disqualifies_a_mana_ability_from_the_solver(self):
        card = compile_card(self._card({"blight": 1, "tap": True}))
        assert not card.abilities[0].cost.is_tap_only()

    def test_it_describes_itself(self):
        card = compile_card(self._card({"blight": 2}))
        assert card.abilities[0].cost.describe() == "Blight 2"
