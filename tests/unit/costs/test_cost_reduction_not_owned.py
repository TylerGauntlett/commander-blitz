"""`not_owned` on a `spell_cost_reduction` -- a spell its caster does not own.

    Gonti, Canny Acquisitor -- "Spells you cast but don't own cost {1} less to
    cast."

The owner of a card is the player who started the game with it in their deck
(108.3); casting it does not change that, and 601.2f applies the reduction to
the total cost of the spell being cast. So the sentence is about the *object*,
not its printed face: a stolen card cast from exile, from an opponent's
graveyard or from their library is discounted, and the caster's own card never
is, from whatever zone. Every pricer -- the action list, `Game._cast`, a
resolving `cast_card` -- hands `cost_reduction` the object's owner beside its
zone. A copy of a card cast is owned by its caster (707.10), so `cast_copy`
hands down the caster.

The near miss is `from_zone: "exile"`, which is wrong both ways: it discounts
your own foretold or impulse-drawn card and misses an opponent's card cast from
their graveyard. A pricer that names no owner fails closed.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.cost_reduction import cost_reduction
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

THIEF = "t_nod_thief"  # spells you cast but don't own cost {1} less
CANE = "t_nod_cane"  # exile an opponent's graveyard sorcery, cast a copy for {4}
RELIC = "t_czr_relic"  # {4} artifact
FLARE = "t_czr_flare"  # {3}{R} sorcery, flashback {3}{R}
DIVINATION = "t_draw_spell"  # {2}{U} sorcery: draw two


def table(builder, *, board=(), lands=3, exile_theirs=(), exile_mine=()):
    """Player 0's main phase with ``lands`` Mountains and ``board`` in play.

    ``exile_theirs`` are player 1's cards and ``exile_mine`` player 0's, each
    moved to exile and made playable by player 0 while exiled -- what Gonti's
    second line and an impulse draw leave behind. A Forest in hand keeps the
    priority window open when nothing else is affordable."""
    game = (
        builder(players=2)
        .battlefield(0, ["mountain"] * lands + list(board))
        .hand(0, ["forest"])
        .graveyard(0, list(exile_mine))
        .graveyard(1, list(exile_theirs))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(0)
        .max_turns(1)
        .build()
    )
    state = game.state
    for pid in (0, 1):
        for oid in list(state.players[pid].graveyard):
            move_object(state, oid, Zone.EXILE)
            obj = state.objects[oid]
            obj.playable_by = 0
            obj.playable_turn = state.turn
            obj.playable_duration = "while_exiled"
    return game


def reduction(builder, *, owner, pid=0, board=(THIEF,), zone=Zone.EXILE) -> int:
    game = table(builder, board=board)
    card = game.state.registry.get(RELIC)
    return cost_reduction(game.state, pid, card, zone=zone, owner=owner)


def casts(game, def_id: str) -> list:
    state = game.state
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and state.objects[a.source].def_id == def_id
    ]


def tapped_mountains(game) -> int:
    state = game.state
    return sum(
        state.objects[oid].tapped
        for oid in state.battlefield
        if state.objects[oid].def_id == "mountain"
    )


class TestTheOwnerIsNotTheCaster:
    """The arithmetic, straight from `cost_reduction`."""

    def test_an_opponents_card_is_discounted(self, builder):
        assert reduction(builder, owner=1) == 1

    def test_your_own_card_is_not(self, builder):
        assert reduction(builder, owner=0) == 0

    @pytest.mark.parametrize("zone", [Zone.HAND, Zone.GRAVEYARD, Zone.LIBRARY, Zone.EXILE])
    def test_the_zone_does_not_matter(self, builder, zone):
        assert reduction(builder, owner=1, zone=zone) == 1
        assert reduction(builder, owner=0, zone=zone) == 0

    def test_a_pricer_that_names_no_owner_gets_no_discount(self, builder):
        """Fail closed: a forgotten owner is a missing discount, not a free one."""
        assert reduction(builder, owner=None) == 0

    def test_it_is_only_your_spells(self, builder):
        """"Spells **you** cast": the opponent casting player 0's card pays full."""
        assert reduction(builder, owner=0, pid=1) == 0

    def test_without_the_permanent_nothing_is_discounted(self, builder):
        assert reduction(builder, owner=1, board=()) == 0


class TestAStolenCardIsOfferedAndChargedDiscounted:
    """`_cast_variant` and `Game._cast` read the same owner off the object.

    A {4} artifact off three Mountains is one short; {1} less closes the gap."""

    def test_the_stolen_relic_needs_the_discount(self, builder):
        assert not casts(table(builder, exile_theirs=[RELIC]), RELIC)
        assert casts(table(builder, board=[THIEF], exile_theirs=[RELIC]), RELIC)

    def test_your_own_exiled_relic_is_not_discounted(self, builder):
        """The near miss `from_zone: "exile"` would offer this one."""
        assert not casts(table(builder, board=[THIEF], exile_mine=[RELIC]), RELIC)

    def test_the_cast_charges_the_discounted_price(self, builder):
        game = table(builder, board=[THIEF], exile_theirs=[RELIC], lands=4)
        game.apply(casts(game, RELIC)[0])
        assert tapped_mountains(game) == 3

    def test_two_reductions_stack(self, builder):
        game = table(builder, board=[THIEF, THIEF], exile_theirs=[RELIC], lands=2)
        assert casts(game, RELIC)


class TestAStolenSorcery:
    """A coloured spell: the {1} comes off the generic part only."""

    def test_it_is_castable_off_three_lands_only_with_the_discount(self, builder):
        assert not casts(table(builder, exile_theirs=[FLARE], lands=3), FLARE)
        assert casts(table(builder, board=[THIEF], exile_theirs=[FLARE], lands=3), FLARE)


class TestACopyIsOwnedByItsCaster:
    """`cast_copy` of an opponent's card: the copy is the caster's (707.10)."""

    def position(self, builder, islands):
        return (
            builder(players=2)
            .battlefield(0, ["island"] * islands + [THIEF])
            .battlefield(1, ["plains"])
            .graveyard(1, [DIVINATION])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .hand(0, [CANE])
            .hand(1, ["t_plain_instant"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def offered(self, builder, islands) -> bool:
        game = self.position(builder, islands)
        game._advance()
        game.apply(casts(game, CANE)[0])
        pass_until(
            game,
            lambda g: not any(i.def_id == CANE for i in g.state.stack)
            or ((d := g.pending()) is not None and d.kind is not DecisionKind.PRIORITY),
        )
        decision = game.pending()
        return decision is not None and decision.kind is DecisionKind.MAY

    def test_the_copy_pays_full_price(self, builder):
        """Three Islands left after the Lesson: {4} is not reached by {1} less."""
        assert not self.offered(builder, 4)

    def test_four_islands_left_pay_it(self, builder):
        assert self.offered(builder, 5)


class TestTheLoader:
    def _card(self, filt) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_nod_probe",
                "name": "Unowned Discount Probe",
                "mana_cost": "{1}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "static",
                        "effect": "spell_cost_reduction",
                        "affects_spells": filt,
                        "amount": 1,
                    }
                ],
            }
        )

    def test_it_accepts_true(self):
        compile_card(self._card({"controller": "you", "not_owned": True}), source="test")

    @pytest.mark.parametrize("value", [False, "yes", 1, None])
    def test_it_refuses_anything_else(self, value):
        with pytest.raises(DslError, match="not_owned"):
            compile_card(self._card({"not_owned": value}), source="test")
