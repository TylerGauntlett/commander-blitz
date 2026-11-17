"""`block_restriction` measured against the source's power.

    Aura Gnarlid -- "Creatures with power less than this creature's power can't
    block it."  (Den Protector and Elusive Otter print the same line.)

Rule 509.1b: the defending player checks each blocker against the restrictions
as blockers are declared, so "this creature's power" is the attacker's power
*then* -- after its counters, its pumps and Aura Gnarlid's own "+1/+1 for each
Aura on the battlefield". A `blockers` filter's `power` clause compared against
a plain integer, and no integer is right for a creature whose size is the whole
point of the line: printed 2 would let a 2-power creature block a Gnarlid grown
to 5.

The value is `{"power_of": {"self": true}}`, the effect-side spelling of "this
creature's power". It is safe in `blockers` and nowhere else in the static
language: `blockers` is read outside the layer pipeline, against derived
characteristics (`combat.blockers_filter_refuses`), so reading the source's
derived power there cannot make one static depend on another's output. Every
layered static filter refuses it at load time.

"Less than" is strict: an equal-power creature blocks, and an engine written
with `<=` passes every test that only tried a smaller blocker.
"""

from __future__ import annotations

import pytest

from commanderblitz.ai.strategy.board import could_block
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.combat import can_block
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, remove_counters
from tests.conftest import attack_with, find_action, only_oid, pass_until

GNARLID = "t_rp_gnarlid"  # 2/2, the static
BEAR = "t_bear"           # 2/2
DORK = "t_dork"           # 1/1
OGRE = "t_menacer"        # 3/3
ANTHEM = "t_anthem"       # creatures you control get +1/+1

SOURCE_POWER = {"power_of": {"self": True}}


def board(builder, mine=(), theirs=(BEAR, DORK, OGRE), *, counters: int = 0, attack=True):
    """``(game, gnarlid_oid)``, the Gnarlid attacking and blockers pending.

    ``counters`` +1/+1 counters go on the Gnarlid before the attack, so the
    size the restriction reads is set before anything is declared.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + list(mine) + [GNARLID])
        .battlefield(1, list(theirs))
        .build()
    )
    oid = only_oid(game, GNARLID, 0)
    if counters:
        add_counters(game.state, oid, "+1/+1", counters)
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    if not attack:
        return game, oid
    attack_with(game, oid)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    return game, oid


class TestLessPowerCannotBlock:
    def test_a_smaller_creature_is_refused(self, builder):
        game, gnarlid = board(builder)
        assert not can_block(game.state, only_oid(game, DORK, 1), gnarlid, 1)

    def test_equal_power_blocks(self, builder):
        """The boundary, and the whole of "less than"."""
        game, gnarlid = board(builder)
        bear = only_oid(game, BEAR, 1)
        assert chars(game.state, bear).power == chars(game.state, gnarlid).power
        assert can_block(game.state, bear, gnarlid, 1)

    def test_a_bigger_creature_blocks(self, builder):
        """The pair. Without it, "can't be blocked" passes the class."""
        game, gnarlid = board(builder)
        assert can_block(game.state, only_oid(game, OGRE, 1), gnarlid, 1)

    def test_legality_does_not_offer_the_refused_block(self, builder):
        game, _ = board(builder)
        dork = only_oid(game, DORK, 1)
        offered = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_BLOCKER and a.source == dork
        ]
        assert not offered


class TestItReadsTheSourcesCurrentPower:
    def test_a_counter_on_the_source_raises_the_bar(self, builder):
        """A 3/3 Gnarlid refuses the 2/2 its printed size would let block."""
        game, gnarlid = board(builder, counters=1)
        assert chars(game.state, gnarlid).power == 3
        assert not can_block(game.state, only_oid(game, BEAR, 1), gnarlid, 1)
        assert can_block(game.state, only_oid(game, OGRE, 1), gnarlid, 1)

    def test_a_static_on_the_source_raises_it_too(self, builder):
        """The anthem is a layer, the counter is board state; both reach it."""
        game, gnarlid = board(builder, mine=[ANTHEM])
        assert chars(game.state, gnarlid).power == 3
        assert not can_block(game.state, only_oid(game, BEAR, 1), gnarlid, 1)

    def test_the_blockers_side_is_derived_as_well(self, builder):
        """An anthem in front of the dork makes it a 2/2, which may block."""
        game, gnarlid = board(builder, theirs=[DORK, ANTHEM])
        dork = only_oid(game, DORK, 1)
        assert chars(game.state, dork).power == 2
        assert can_block(game.state, dork, gnarlid, 1)

    def test_losing_the_counter_lowers_the_bar_again(self, builder):
        """Wearing off: asked as it is now, not as it was when it attacked."""
        game, gnarlid = board(builder, counters=1)
        bear = only_oid(game, BEAR, 1)
        assert not can_block(game.state, bear, gnarlid, 1)
        remove_counters(game.state, gnarlid, "+1/+1", 1)
        assert can_block(game.state, bear, gnarlid, 1)


class TestTheCpuAsksBeforeDeclaring:
    """`ai.strategy.board.could_block` answers while attackers are still being
    chosen; a CPU that did not ask would expect a chump block that cannot come."""

    def test_could_block_refuses_the_smaller_creature(self, builder):
        game, gnarlid = board(builder, attack=False)
        assert not could_block(game.state, only_oid(game, DORK, 1), gnarlid, 1)
        assert could_block(game.state, only_oid(game, BEAR, 1), gnarlid, 1)

    def test_could_block_reads_the_grown_source(self, builder):
        game, gnarlid = board(builder, counters=1, attack=False)
        assert not could_block(game.state, only_oid(game, BEAR, 1), gnarlid, 1)
        assert could_block(game.state, only_oid(game, OGRE, 1), gnarlid, 1)


def _creature(abilities: list[dict]) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_rp_probe",
            "name": "Relative Power Probe",
            "mana_cost": "{1}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": abilities,
        }
    )


def _restriction(blockers: dict) -> CardModel:
    return _creature(
        [
            {"kind": "static", "effect": "block_restriction",
             "affects": {"self_only": True}, "blockers": blockers}
        ]
    )


class TestLoadTimeRefusals:
    def test_the_witness_shape_loads(self):
        compile_card(_restriction({"power": {"op": "<", "value": SOURCE_POWER}}))

    def test_a_layered_static_may_not_read_the_source_power(self):
        """An anthem's `affects` is matched inside the pipeline; reading the
        source's derived power there would be one static reading another's."""
        with pytest.raises(DslError, match="plain integer"):
            compile_card(
                _creature(
                    [
                        {"kind": "static", "effect": "buff", "power": 1, "toughness": 1,
                         "affects": {"types": ["Creature"],
                                     "power": {"op": "<", "value": SOURCE_POWER}}}
                    ]
                )
            )

    def test_toughness_may_not_take_it(self):
        with pytest.raises(DslError, match="plain integer"):
            compile_card(_restriction({"toughness": {"op": "<", "value": SOURCE_POWER}}))

    def test_another_object_reference_is_refused(self):
        """Only "this creature's power"; a target has no meaning in a static."""
        with pytest.raises(DslError, match="plain integer"):
            compile_card(
                _restriction({"power": {"op": "<", "value": {"power_of": {"target": "t1"}}}})
            )
