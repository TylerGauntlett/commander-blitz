"""A mana ability that also does something — the painland's drawback.

    "{T}: Add {R} or {W}. Battlefield Forge deals 1 damage to you."

`_sum_mana` refused any effect in a mana ability that was not `add_mana`, so the
whole painland and Talisman family was unsayable. The tempting fix is to drop
`is_mana_ability` and let the damage in as an ordinary activated ability, and
that is not an approximation but a different card: a non-mana ability uses the
stack and is not offerable inside cost payment, so the land could never be
tapped to help cast a spell — the only thing it is played for.

`pay_life` is not a substitute either. It is life *payment*, not damage from a
source: unaffected by prevention, redirection, lifelink and every
`dealt_damage` trigger, and it happens at activation rather than at resolution.
Six cards in one deck print "deals 1 damage to you", and none of them means
"pay 1 life".

**The rider lives on `Ability`, not in `effects`.** The two halves answer to
different code. `mana_options` is a constant tuple the payment solver reads
while *planning*, before anything is tapped; the rider is a real effect that
must not run until the ability resolves. Leaving them mixed would either have
the solver believe a painland produces damage, or have the damage never happen.

**One home, both paths.** The thing that would actually go wrong here is a rider
that only fires on manual activation: the auto-payment solver taps lands for you
without asking, so the land would be painless exactly when the engine used it.
`pay_mana` and `Game.apply` both funnel through `activate_mana_ability`, which
is why the rider is applied there and nowhere else — and why the test below taps
a painland by *casting a spell* rather than by activating anything.

The rider may not ask questions. There is no stack inside cost payment and no
priority window to answer in, so a yielding op would hang the solver mid-tap;
`loader.MANA_RIDER_OPS` is the whitelist that makes that a load-time error
instead.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.costs import activate_mana_ability
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from tests.conftest import oids_of

PAINLAND = "t_painland"
COLOURED = 1  # the "{T}: Add {R} or {W}" ability; index 0 is the painless {C}


def position(builder, *, lands: int = 1, hand: list[str] | None = None):
    game = (
        builder(players=2)
        .battlefield(0, [PAINLAND] * lands)
        .hand(0, hand or [])
        .library(0, ["island"] * 20)
        .build()
    )
    return game


def a_painland(game) -> int:
    return oids_of(game, PAINLAND)[0]


class TestTheRiderHappens:
    def test_tapping_for_coloured_mana_costs_a_life(self, builder):
        game = position(builder)
        oid = a_painland(game)
        before = game.state.players[0].life
        activate_mana_ability(game.state, oid, COLOURED, 0)
        assert game.state.players[0].life == before - 1

    def test_the_mana_still_arrives(self, builder):
        game = position(builder)
        oid = a_painland(game)
        activate_mana_ability(game.state, oid, COLOURED, 0)
        assert game.state.players[0].mana_pool.total() == 1

    def test_the_permanent_is_tapped(self, builder):
        game = position(builder)
        oid = a_painland(game)
        activate_mana_ability(game.state, oid, COLOURED, 0)
        assert game.state.objects[oid].tapped

    def test_the_painless_mode_costs_nothing(self, builder):
        """Index 0 is "{T}: Add {C}" — a separate ability with no rider."""
        game = position(builder)
        oid = a_painland(game)
        before = game.state.players[0].life
        activate_mana_ability(game.state, oid, 0, 0)
        assert game.state.players[0].life == before

    def test_it_is_damage_from_a_source_not_a_life_payment(self, builder):
        """`pay_life` would be silent here; damage names who dealt it.

        That difference is the whole reason this is not modelled as a cost:
        prevention, redirection, lifelink and every `dealt_damage` trigger read
        this event, and none of them would ever see a life payment.
        """
        game = position(builder)
        oid = a_painland(game)
        before = len(game.state.events)
        activate_mana_ability(game.state, oid, COLOURED, 0)
        dealt = [
            e
            for e in game.state.events[before:]
            if e.type == EventType.DAMAGE_DEALT
        ]
        assert [(e.source, e.data["amount"]) for e in dealt] == [(oid, 1)]


class TestTheSolverPaysItToo:
    """The path that would silently make the land painless."""

    def test_the_auto_payment_solver_applies_the_rider(self, builder):
        from automtg.engine.costs import pay_mana
        from automtg.engine.mana import ManaCost

        game = position(builder, lands=2)
        before = game.state.players[0].life
        assert pay_mana(game.state, 0, ManaCost.parse("{R}").with_x(0))
        assert game.state.players[0].life == before - 1


class TestTheRiderIsStillAManaAbility:
    def test_it_produces_the_options_the_solver_reads(self, registry):
        ability = registry.get(PAINLAND).abilities[COLOURED]
        assert ability.is_mana_ability
        # Two modes, one symbol each -- the damage is not in here.
        assert len(ability.mana_options) == 2
        assert all(sum(o) == 1 for o in ability.mana_options)

    def test_the_rider_is_held_apart_from_the_mana(self, registry):
        ability = registry.get(PAINLAND).abilities[COLOURED]
        assert [e["op"] for e in ability.mana_rider] == ["damage"]


class TestTheWhitelistRefusesWhatWouldHang:
    def _card(self, rider: dict) -> CardModel:
        return CardModel(
            id="t_bad_rider",
            name="Bad Rider",
            oracle_text="{T}: Add {G}.",
            types=["Land"],
            abilities=[
                {
                    "kind": "activated",
                    "text": "{T}: Add {G}.",
                    "is_mana_ability": True,
                    "cost": {"tap": True},
                    "effects": [{"op": "add_mana", "mana": "{G}"}, rider],
                }
            ],
        )

    def test_an_op_that_asks_is_refused_at_load(self):
        """`may` yields a decision, and there is nowhere to answer it."""
        with pytest.raises(DslError, match="rider"):
            compile_card(self._card({"op": "may", "player": "you", "effects": []}))

    def test_drawing_a_card_is_refused_at_load(self):
        with pytest.raises(DslError, match="rider"):
            compile_card(
                self._card({"op": "draw", "player": "you", "amount": {"const": 1}})
            )

    def test_a_whitelisted_rider_loads(self):
        card = compile_card(
            self._card({"op": "lose_life", "player": "you", "amount": {"const": 1}})
        )
        assert [e["op"] for e in card.abilities[0].mana_rider] == ["lose_life"]
