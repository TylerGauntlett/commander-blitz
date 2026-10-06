"""Statics that make *other* spells cheaper.

"Creature spells with flying you cast cost {1} less to cast." Warden of Evos
Isle and Watcher of the Spheres are the shipped witnesses, and both print
exactly that line.

The near miss is the card-level `cost_reduction` field, and it points the other
way: it discounts the card that **carries** it, choosing by counting permanents
on the board. That is Ghalta — "this spell costs {X} less". Writing it on Warden
would make Warden cheaper, which is a different card. What was missing is a
discount on a *different* card, selected by that card's own printed face.

So the filter is a new one. `affects` names permanents on the battlefield and
carries board state (`tapped`, `attacking`, `attached`); a spell being priced is
still in hand and has none of that. `affects_spells` reads the printed face plus
who is casting, which is exactly `characteristics._matches_printed`.

**Where it is applied is the design.** `cost_reduction.cost_reduction` is the one
function both `legality` (deciding what is castable, and what the client shows)
and `game.cast` (actually charging) already call, so adding the term there means
a spell offered at the reduced price is paid at the reduced price by
construction. A `spell_cast` trigger could not stand in: it fires after the
spell is cast and paid for, so at best it refunds mana into the pool, which is
not the same as being able to afford the spell in the first place.

Three ways to get it wrong, all invisible on a board:

- Discounting everything. An empty filter matches every card, so a compile bug
  that dropped `affects_spells` would make the whole game free. It did, once,
  during this run — hence `test_it_does_not_discount_everything` and the
  `continue` in `spell_cost_reduction` rather than a `{}` default.
- Discounting coloured pips. "Costs {1} less" never touches coloured mana.
- Discounting the wrong player's spells.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.cost_reduction import cost_reduction
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError

WARDEN = "warden_of_evos_isle"  # creature spells with flying cost {1} less
WATCHER = "watcher_of_the_spheres"  # the same line
FLIER = "t_flier"  # {2}{U} creature with flying
BEAR = "t_bear"  # {1}{G} creature, no flying
FLYING_ARTIFACT = "t_flying_artifact"  # {2} artifact with flying


def table(builder, board=(), *, lands=6, hand=(FLIER,)):
    return (
        builder(players=2)
        .battlefield(0, list(board) + ["island"] * lands)
        .hand(0, list(hand))
        .active(0)
        .max_turns(1)
        .build()
    )


def reduction(builder, board, spell: str, *, pid: int = 0) -> int:
    game = table(builder, board, hand=(spell,))
    return cost_reduction(game.state, pid, game.state.registry.get(spell))


def can_cast(game, def_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
        for a in game.legal_actions()
    )


class TestWhatItDiscounts:
    def test_a_creature_spell_with_flying(self, builder):
        assert reduction(builder, [WARDEN], FLIER) == 1

    def test_it_does_not_discount_everything(self, builder):
        """The failure mode that actually happened: an empty filter."""
        assert reduction(builder, [WARDEN], BEAR) == 0, (
            "a creature without flying is not 'a creature spell with flying'"
        )

    def test_flying_alone_is_not_enough(self, builder):
        assert reduction(builder, [WARDEN], FLYING_ARTIFACT) == 0, (
            "an artifact with flying is not a *creature* spell"
        )

    def test_nothing_on_an_empty_board(self, builder):
        assert reduction(builder, [], FLIER) == 0

    def test_two_of_them_stack(self, builder):
        assert reduction(builder, [WARDEN, WATCHER], FLIER) == 2


class TestWhoseSpells:
    def test_only_the_controller_s(self, builder):
        """"…you cast." The opponent's Warden does not help you."""
        assert reduction(builder, [WARDEN], FLIER, pid=1) == 0


class TestOfferedAndPaidAgree:
    """The property the placement in `cost_reduction.cost_reduction` buys."""

    def test_it_makes_an_unaffordable_spell_castable(self, builder):
        # {2}{U} is three mana; two Islands cannot pay it.
        assert not can_cast(table(builder, [], lands=2), FLIER)
        assert can_cast(table(builder, [WARDEN], lands=2), FLIER), (
            "with the discount it is {1}{U}, which two Islands can pay"
        )

    def test_and_the_cast_actually_completes(self, builder):
        game = table(builder, [WARDEN], lands=2)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == FLIER
        )
        game.apply(action)

        assert any(
            game.state.objects[o].def_id == FLIER for o in game.state.battlefield
        ), "offered at the reduced price and paid at it, or the cast strands"
        assert game.state.players[0].mana_pool.to_dict() == {}, "no mana left over"

    def test_it_does_not_touch_coloured_pips(self, builder):
        # One Island: {1}{U} reduced by another {1} is still {U}, never {0}.
        game = table(builder, [WARDEN, WATCHER], lands=1)
        assert can_cast(game, FLIER), "{2}{U} minus {2} is {U}, and one Island pays it"

    def test_and_never_below_zero(self, builder):
        game = table(builder, [WARDEN, WATCHER], lands=0)
        assert not can_cast(game, FLIER), (
            "the generic part floors at zero; the {U} still has to be paid"
        )


def probe(**static) -> dict:
    base = {
        "kind": "static",
        "text": "Creature spells with flying you cast cost {1} less to cast.",
        "effect": "spell_cost_reduction",
        "affects_spells": {"controller": "you", "types": ["Creature"]},
        "amount": {"const": 1},
    }
    base.update(static)
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Creature spells with flying you cast cost {1} less to cast.",
        "mana_cost": "{U}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [base],
    }


class TestTheLoader:
    def test_the_shipped_shape_loads(self):
        compile_card(CardModel.model_validate(probe()))

    def test_a_filter_is_required(self):
        payload = probe()
        del payload["abilities"][0]["affects_spells"]
        with pytest.raises(DslError, match="needs 'affects_spells'"):
            compile_card(CardModel.model_validate(payload))

    def test_an_amount_is_required(self):
        payload = probe()
        del payload["abilities"][0]["amount"]
        with pytest.raises(DslError, match="needs an 'amount'"):
            compile_card(CardModel.model_validate(payload))

    def test_affects_is_the_wrong_key(self):
        """`affects` picks out permanents; this picks out a card in hand."""
        with pytest.raises(DslError, match="not 'affects'"):
            compile_card(
                CardModel.model_validate(probe(affects={"types": ["Creature"]}))
            )

    def test_board_state_keys_are_refused(self):
        """A card in hand is not tapped, so `tapped` there means nothing."""
        with pytest.raises(DslError, match="no board state"):
            compile_card(
                CardModel.model_validate(
                    probe(affects_spells={"types": ["Creature"], "tapped": False})
                )
            )

    def test_affects_spells_is_refused_on_other_effects(self):
        with pytest.raises(DslError, match="only means anything on a"):
            compile_card(
                CardModel.model_validate(
                    probe(
                        effect="buff",
                        affects={"self_only": True},
                        power={"const": 1},
                        toughness={"const": 1},
                    )
                )
            )
