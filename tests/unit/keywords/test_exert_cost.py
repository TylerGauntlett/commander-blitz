"""Exert as a **cost** (702.121a).

    "{R}, {T}, **Exert this land**: Add {R}{R}."      -- Arena of Glory

`tests/unit/keywords/test_exert.py` already cashes the keyword's usual shape: an
`attacks` trigger, a `may`, and `skip_untap` for the price. That shape cannot
be reused here, twice over.

* Exert is a **cost** on this card, paid as the ability is activated (601.2h),
  not an effect that resolves. And the ability is a **mana ability** -- it never
  resolves at all: `costs.pay` and `mana_options_of` add its symbols during
  somebody's payment, with nothing on the stack for an op to run from.
* The loader forbids the effect spelling outright. `_split_mana_rider` allows a
  mana ability only `add_mana` plus a rider from `MANA_RIDER_OPS`, and
  `skip_untap` is not in it. Writing the line as an ordinary activated ability
  to smuggle the op in would be a different card: it would use the stack and be
  uncastable during another spell's payment, which is the whole point of a land.

So `Cost.exert` is a cost key, paid beside `{T}` and the `{R}`. It writes the
two halves 702.121a names -- `skip_next_untap` and the turn-scoped word
`exerted` -- and it asks nothing of its source but that it be on the
battlefield: Arena of Glory is a **land**, never attacking and never a creature,
which is where every earlier exert lived.

The assertions that matter are about **time**. `skip_next_untap` is a one-shot
consumed by the untap step it skips, so a test that looks too late reads it as
absent and concludes the price was never paid; and a test that looks only once
cannot tell "skips one untap step" from "never untaps again", which is a
strictly better land than the printed one.
"""

from __future__ import annotations

import pydantic
import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.carddef import Cost
from commanderblitz.engine.costs import activate_mana_ability
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid, pass_until

ARENA = "t_glory_arena"  # ability 0 is the plain {R}; ability 1 exerts
SPRINTER = "t_glory_sprinter"  # a vanilla 2/2 for {2}
PLAIN_MANA = 0
EXERT_MANA = 1


def position(builder):
    """The Arena, one Mountain and something worth making mana for.

    The Mountain pays the ability's `{R}`; the creature in hand is what stops
    the sandbox's auto-pass rolling straight past a main phase in which nobody
    has anything to spend mana on.
    """
    game = (
        builder(players=2)
        .hand(0, [SPRINTER])
        .battlefield(0, [ARENA, "mountain"])
        .build()
    )
    return game, only_oid(game, ARENA, 0)


def exert(game, oid: int) -> None:
    """Activate the exerting ability the way a player would -- through `pay`.

    The plain ability below is **not** reachable this way and must not be: it is
    `Cost.is_tap_only`, so legality hands it to the payment solver rather than
    offering it, which is exactly the line exert has to stay off.
    """
    for action in game.legal_actions():
        if (
            action.kind is ActionKind.ACTIVATE
            and action.source == oid
            and action.ability_index == EXERT_MANA
        ):
            game.apply(action)
            return
    raise AssertionError(
        f"the exerting ability of #{oid} was not offered; "
        f"legal: {[a.label for a in game.legal_actions()]}"
    )


def tap_plainly(game, oid: int) -> None:
    """Arena's first line, fired the way the payment solver fires it."""
    activate_mana_ability(game.state, oid, PLAIN_MANA, 0)


class TestItIsOfferedAtAll:
    def test_a_land_can_pay_it(self, builder):
        """No creature test and no attacking test: the only printed exert cost
        is on a land, and 702.121 is about permanents."""
        game, arena = position(builder)
        exert(game, arena)
        assert game.state.players[0].mana_pool.to_dict() == {"R": 2}

    def test_it_is_not_offered_once_the_source_is_tapped(self, builder):
        """The `{T}` half still has to be payable -- exert does not replace it."""
        game, arena = position(builder)
        tap_plainly(game, arena)
        assert not any(
            a.kind is ActionKind.ACTIVATE and a.source == arena
            for a in game.legal_actions()
        )


class TestPayingItWritesBothHalves:
    def test_it_taps_and_exerts(self, builder):
        game, arena = position(builder)
        exert(game, arena)
        obj = game.state.objects[arena]
        assert obj.tapped, "the {T} half"
        assert obj.skip_next_untap, "the exert half"

    def test_it_records_the_word_for_the_turn(self, builder):
        """`TurnLedger.object_flags` is what "hasn't been exerted this turn"
        reads, and the two stores are separate on purpose: one is spent by an
        untap step, the other by the turn boundary."""
        game, arena = position(builder)
        exert(game, arena)
        assert "exerted" in game.state.turn_ledger.object_flags.get(arena, set())

    def test_the_plain_ability_exerts_nothing(self, builder):
        """Same permanent, other ability. Arena's first line is an ordinary
        tap-for-mana and must stay one."""
        game, arena = position(builder)
        tap_plainly(game, arena)
        obj = game.state.objects[arena]
        assert obj.tapped and not obj.skip_next_untap
        assert "exerted" not in game.state.turn_ledger.object_flags.get(arena, set())


class TestThePriceIsReal:
    def test_it_stays_tapped_through_the_next_untap_step(self, builder):
        game, arena = position(builder)
        exert(game, arena)
        pass_until(game, lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert game.state.objects[arena].tapped, (
            "its controller's next untap step came and went"
        )

    def test_it_untaps_the_step_after_that(self, builder):
        """Exactly **one** untap step, not every one after it. A land that never
        untapped again would pass the assertion above and be a different card."""
        game, arena = position(builder)
        exert(game, arena)
        pass_until(game, lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert not game.state.objects[arena].skip_next_untap, "the one-shot is spent"
        pass_until(game, lambda g: g.state.turn >= 5 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert not game.state.objects[arena].tapped

    def test_the_plain_ability_untaps_normally(self, builder):
        game, arena = position(builder)
        tap_plainly(game, arena)
        pass_until(game, lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert not game.state.objects[arena].tapped


class TestTheCostKey:
    def test_it_is_not_a_tap_only_cost(self, builder):
        """`Cost.is_tap_only` is what lets the payment solver fire a mana
        ability on its own. A solver that paid an exert silently would keep a
        land down for a turn nobody agreed to, so the claim is asserted here
        rather than left to Arena's `{R}` to imply."""
        assert Cost(tap=True).is_tap_only()
        assert not Cost(tap=True, exert=True).is_tap_only()

    def test_it_reaches_the_compiled_ability(self, registry):
        card = registry.get(ARENA)
        assert not card.abilities[PLAIN_MANA].cost.exert
        assert card.abilities[EXERT_MANA].cost.exert

    def test_an_unknown_cost_key_is_still_refused(self):
        """The guard that makes the new key worth having: `CostModel` forbids
        extras, so `exert` had to be declared rather than merely accepted."""
        with pytest.raises(pydantic.ValidationError):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "x",
                        "name": "X",
                        "oracle_text": "{T}, Exhort this land: Add {R}.",
                        "types": ["Land"],
                        "abilities": [
                            {
                                "kind": "activated",
                                "text": "{T}, Exhort this land: Add {R}.",
                                "is_mana_ability": True,
                                "cost": {"tap": True, "exhort": True},
                                "effects": [{"op": "add_mana", "mana": "{R}"}],
                            }
                        ],
                    }
                )
            )


class TestTheEffectSpellingIsStillRefused:
    def test_skip_untap_is_not_a_mana_rider(self):
        """Why this is a cost key and not the op. A mana ability never resolves,
        and the loader says so before the engine ever gets the chance."""
        with pytest.raises(DslError, match="add_mana"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "x",
                        "name": "X",
                        "oracle_text": "{T}: Add {R}.",
                        "types": ["Land"],
                        "abilities": [
                            {
                                "kind": "activated",
                                "text": "{T}: Add {R}.",
                                "is_mana_ability": True,
                                "cost": {"tap": True},
                                "effects": [
                                    {"op": "add_mana", "mana": "{R}"},
                                    {"op": "skip_untap", "objects": {"self_only": True}},
                                ],
                            }
                        ],
                    }
                )
            )
