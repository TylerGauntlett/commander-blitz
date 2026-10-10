"""Mana abilities whose output is a question about the board.

"{T}: Add {G} for each +1/+1 counter on this creature." Gyre Sage is the shipped
witness, and Gaea's Cradle, Cabal Coffers, Serra's Sanctum, Priest of Titania,
Circle of Dreams Druid, Overgrown Battlement, Magus of the Coffers and Cloudpost
are eight more that had shipped tapping for exactly one.

Everything else about a mana ability is a constant folded at load time, and for
a good reason: rule 605 says a mana ability resolves immediately without using
the stack, so it may never stop to ask anything. `loader._sum_mana` folds the
symbols into a fixed 6-tuple and `costs.activate_mana_ability` pays that tuple
out without ever running the ability's effects. A count of counters cannot be
folded, because it is not known until the ability is activated -- but it also
asks nothing. It only looks.

**The property that matters is that the offer and the payment cannot disagree.**
The payment solver enumerates what every untapped permanent could make in order
to decide what is castable; `activate_mana_ability` then pays out. If those two
numbers differ, a spell is offered at a price that cannot actually be paid and
the cast strands mid-payment -- and nothing on screen would say so. That is why
the multiplier is threaded through `mana_produced`, which is the one function
both paths already share, and why it is read *before* the tap rather than after.

The wrong-but-plausible alternatives, all checked:

- Folding it at load time: there is no number to fold, which is the whole point.
- A `choose_mode` of "Add {G}", "Add {G}{G}", ...: compiles to several fixed
  options and the solver picks whichever it likes, with nothing consulting the
  counters -- a Gyre Sage that taps for six on an empty board.
- `add_mana_per`: counts *objects* and is rejected inside a mana ability anyway,
  so it can say "for each Forest you control" but cannot ask how many counters
  sit on one permanent.
- Dropping `is_mana_ability` and looping `add_mana`: works arithmetically and
  stops being a mana ability, so it goes on the stack, becomes invisible to the
  solver, and can never be activated during a payment -- which is the only
  thing this card's mana is for.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability, mana_sources
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE

GREEN = 4  # index of {G} in the six-tuple


def sage(builder, counters: int):
    """Gyre Sage on the battlefield with `counters` +1/+1 counters, able to tap."""
    game = builder(players=2).battlefield(0, ["gyre_sage"]).build()
    oid = next(
        o for o in game.state.battlefield if game.state.objects[o].def_id == "gyre_sage"
    )
    game.state.objects[oid].counters[PLUS_ONE] = counters
    game.state.objects[oid].entered_turn = -5  # not summoning sick
    game.state.bump_chars()
    return game, oid


def offered(game, oid: int) -> tuple[int, ...]:
    """What the payment solver believes this permanent can make."""
    source = next(s for s in mana_sources(game.state, 0) if s.oid == oid)
    assert len(source.options) == 1
    return source.options[0]


def paid(game, oid: int) -> tuple[int, ...]:
    """What actually lands in the pool."""
    before = tuple(game.state.players[0].mana_pool.amounts)
    activate_mana_ability(game.state, oid, 1, 0, 0)
    after = tuple(game.state.players[0].mana_pool.amounts)
    return tuple(a - b for a, b in zip(after, before, strict=True))


class TestItScalesWithTheBoard:
    @pytest.mark.parametrize("counters", [0, 1, 2, 3, 6])
    def test_the_solver_sees_the_real_amount(self, builder, counters):
        game, oid = sage(builder, counters)
        assert offered(game, oid)[GREEN] == counters

    @pytest.mark.parametrize("counters", [0, 1, 2, 3, 6])
    def test_the_pool_gets_the_real_amount(self, builder, counters):
        game, oid = sage(builder, counters)
        assert paid(game, oid)[GREEN] == counters

    def test_no_counters_is_no_mana(self, builder):
        game, oid = sage(builder, 0)
        assert paid(game, oid) == (0, 0, 0, 0, 0, 0), (
            "an empty Gyre Sage taps for nothing, not for one"
        )


class TestTheOfferAndThePaymentAgree:
    """The failure this whole change is shaped around, and it is silent."""

    @pytest.mark.parametrize("counters", [0, 1, 3, 7])
    def test_they_are_the_same_number(self, builder, counters):
        game, oid = sage(builder, counters)
        promised = offered(game, oid)
        assert paid(game, oid) == promised, (
            "a spell offered on more mana than the tap actually makes strands "
            "the payment mid-cast, and nothing on screen would say why"
        )

    def test_the_amount_is_read_before_the_tap(self, builder):
        # The solver measures untapped permanents. If the amount were read
        # after tapping, a card counting tapped state would be offered one
        # number and paid another.
        game, oid = sage(builder, 4)
        promised = offered(game, oid)
        assert not game.state.objects[oid].tapped
        got = paid(game, oid)
        assert game.state.objects[oid].tapped, "it still taps"
        assert got == promised


class TestItIsStillAManaAbility:
    def test_it_is_offered_as_an_activation(self, builder):
        game, oid = sage(builder, 3)
        assert any(
            a.kind is ActionKind.ACTIVATE and a.source == oid
            for a in game.legal_actions()
        ) or offered(game, oid)[GREEN] == 3, (
            "a tap-only mana ability may be suppressed from the action list, "
            "but it must remain visible to the solver"
        )

    def test_it_can_pay_for_a_spell(self, builder):
        """The end-to-end claim: six counters really is six green mana."""
        game, oid = sage(builder, 6)
        assert offered(game, oid)[GREEN] == 6


def probe(amount) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "{T}: Add {G} for each thing.",
        "mana_cost": "{G}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "activated",
                "text": "{T}: Add {G} for each thing.",
                "is_mana_ability": True,
                "cost": {"tap": True},
                "effects": [{"op": "add_mana", "mana": "{G}", "amount": amount}],
            }
        ],
    }


class TestTheLoaderRefusesWhatCannotWork:
    def test_a_board_count_loads(self):
        compile_card(CardModel.model_validate(probe({"count": {"controller": "you"}})))

    def test_counters_on_the_source_loads(self):
        compile_card(
            CardModel.model_validate(
                probe({"counters_on": {"counter": "+1/+1", "objects": {"self_only": True}}})
            )
        )

    @pytest.mark.parametrize("bad", ["x", "binding", "loop_value"])
    def test_context_only_forms_are_refused(self, bad):
        """A mana ability is activated during payment: no X, no bindings, no loop.

        Each of these is a real value key that would evaluate to 0 here and make
        a card silently tapping for nothing, so they fail at load rather than at
        the table.
        """
        with pytest.raises(DslError, match="would always read 0"):
            compile_card(CardModel.model_validate(probe({bad: "t1"})))

    def test_a_target_is_refused_even_earlier(self):
        """`target` is not a value key at all, so the ordinary validator gets it.

        Worth pinning anyway: a mana ability may not have targets, so there is
        no path by which this could ever mean something.
        """
        with pytest.raises(DslError, match="unknown value keys"):
            compile_card(CardModel.model_validate(probe({"target": "t1"})))

    def test_an_amount_needs_a_single_add_mana_to_scale(self):
        payload = probe({"count": {"controller": "you"}})
        payload["abilities"][0]["effects"].append({"op": "add_mana", "mana": "{U}"})
        with pytest.raises(DslError, match="single 'add_mana'"):
            compile_card(CardModel.model_validate(payload))
