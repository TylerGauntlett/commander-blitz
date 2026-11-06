"""`modified` in a static's `affects` -- "other modified creatures you control".

    "Other modified creatures you control have vigilance and trample. (Equipment,
    Auras you control, and counters are modifications.)"
                                                -- Red XIII, Proud Warrior

A permanent is modified when it has a counter on it, is equipped, or is
enchanted by an Aura its viewer controls -- the reminder text's three limbs. The
effect-side selector always had the word (`selectors._is_modified`); a static's
filter did not, and an `any_of` over `has_counters` and `enchanted_by` drops the
equipped limb, because no static key asks a host whether an Equipment is on it.

ADR 0001 lets a static's filter read pipeline inputs only, so
`characteristics.is_modified_printed` reads counters (board state), the Aura
walk `enchanted_by` makes (attachment, controller, printed face, bestow stamp),
and an Equipment told by its **printed** face, as `sba` bins it -- not by its
derived subtypes, which are layer 4's output.

What would be wrong without each limb:

- **Equipment**: a creature carrying a Sword would not trample.
- **"Auras you control"**: an opponent's Pacifism would make your creature
  modified, and so vigilant.
- **Counters of any kind**: a stun or shield counter modifies as +1/+1 does.

Witness: Red XIII, Proud Warrior. `t_mod_lord` is its middle line alone.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.primitives import add_counters, attach, remove_counters
from commanderblitz.engine.zones import destroy
from tests.conftest import keywords, only_oid, static_probe

LORD = "t_mod_lord"  # Red XIII's middle line alone
BEAR = "t_eb_bear"
CUB = "t_eb_cub"
AURA = "t_eb_aura"  # Enchant creature, nothing else
GEAR = "t_plain_gear"  # an Equipment with nothing printed
SWAMP = "swamp"

GRANTED = {"vigilance", "trample"}


def position(builder, *, mine=(), theirs=(), on_bear=()):
    """Player 0's lord beside a Bear and a Cub; ``on_bear`` lists
    ``(card_id, seat)`` attachments put on the Bear before the game advances,
    so the state-based action that bins an unattached Aura never sees one.
    Returns ``(game, bear, cub)``."""
    b = builder(players=2).battlefield(0, [LORD, BEAR, CUB, *mine]).battlefield(1, list(theirs))
    for pid in range(2):
        b.library(pid, [SWAMP] * 20)
    game = b.active(0).step(Step.UNTAP).build(advance=False)
    bear, cub = only_oid(game, BEAR, 0), only_oid(game, CUB, 0)
    for card_id, seat in on_bear:
        assert attach(game.state, only_oid(game, card_id, seat), bear)
    game._advance()
    return game, bear, cub


def granted(game, oid: int) -> bool:
    got = keywords(game, oid) & GRANTED
    assert got in (set(), GRANTED), "both keywords or neither"
    return got == GRANTED


class TestEachLimbModifies:
    def test_a_bare_creature_is_not_modified(self, builder):
        game, bear, cub = position(builder)
        assert not granted(game, bear)
        assert not granted(game, cub)

    def test_your_equipment(self, builder):
        game, bear, cub = position(builder, mine=[GEAR], on_bear=[(GEAR, 0)])
        assert granted(game, bear)
        assert not granted(game, cub)

    def test_an_opponents_equipment(self, builder):
        """Equipped is equipped, whoever's Equipment it is."""
        game, bear, _ = position(builder, theirs=[GEAR], on_bear=[(GEAR, 1)])
        assert granted(game, bear)

    def test_your_aura(self, builder):
        game, bear, cub = position(builder, mine=[AURA], on_bear=[(AURA, 0)])
        assert granted(game, bear)
        assert not granted(game, cub)

    def test_an_opponents_aura_does_not_modify(self, builder):
        """The one asymmetric limb: "Auras **you** control"."""
        game, bear, _ = position(builder, theirs=[AURA], on_bear=[(AURA, 1)])
        assert not granted(game, bear)

    @pytest.mark.parametrize("kind", [PLUS_ONE, "stun", "shield"])
    def test_a_counter_of_any_kind(self, builder, kind):
        game, bear, cub = position(builder)
        add_counters(game.state, bear, kind, 1)
        assert granted(game, bear)
        assert not granted(game, cub)


class TestTheFilterAroundIt:
    def test_other_excludes_the_lord_itself(self, builder):
        game, _, _ = position(builder)
        lord = only_oid(game, LORD, 0)
        add_counters(game.state, lord, PLUS_ONE, 1)
        assert not granted(game, lord)

    def test_an_opponents_modified_creature_is_not_yours(self, builder):
        game, _, _ = position(builder, theirs=[BEAR])
        theirs = only_oid(game, BEAR, 1)
        add_counters(game.state, theirs, PLUS_ONE, 1)
        assert not granted(game, theirs)


class TestTheWearingOff:
    def test_the_equipment_destroyed(self, builder):
        game, bear, _ = position(builder, mine=[GEAR], on_bear=[(GEAR, 0)])
        destroy(game.state, only_oid(game, GEAR, 0), cause="test")
        assert not granted(game, bear)

    def test_the_equipment_moved(self, builder):
        game, bear, cub = position(builder, mine=[GEAR], on_bear=[(GEAR, 0)])
        attach(game.state, only_oid(game, GEAR, 0), cub)
        assert not granted(game, bear)
        assert granted(game, cub)

    def test_the_last_counter_removed(self, builder):
        game, bear, _ = position(builder)
        add_counters(game.state, bear, PLUS_ONE, 1)
        remove_counters(game.state, bear, PLUS_ONE, 1)
        assert not granted(game, bear)

    def test_the_lord_leaving(self, builder):
        game, bear, _ = position(builder, mine=[GEAR], on_bear=[(GEAR, 0)])
        destroy(game.state, only_oid(game, LORD, 0), cause="test")
        assert not granted(game, bear)


def compile_static(affects):
    static = {"effect": "grant_keyword", "keywords": ["trample"], "affects": affects}
    return compile_card(CardModel.model_validate(static_probe(static)))


class TestTheLoader:
    def test_true_loads(self):
        compile_static({"types": ["Creature"], "modified": True})

    def test_inside_an_any_of_branch_loads(self):
        compile_static(
            {"types": ["Creature"], "any_of": [{"modified": True}, {"tapped": True}]}
        )

    @pytest.mark.parametrize("value", [False, "true", {"controller": "you"}, 1])
    def test_anything_but_true_is_refused(self, value):
        """`false` would read as no clause, and a dict as `true`."""
        with pytest.raises(DslError, match="modified"):
            compile_static({"types": ["Creature"], "modified": value})

    def test_refused_in_a_branch_too(self):
        with pytest.raises(DslError, match="modified"):
            compile_static(
                {"types": ["Creature"], "any_of": [{"modified": "yes"}, {"tapped": True}]}
            )

    def test_not_a_cost_reduction_or_blocker_key(self):
        """`affects` alone admits it: `STATIC_FILTER_KEYS` also validates
        cost-reduction and effect filters whose matchers would walk past the
        word and match everything."""
        static = {
            "effect": "block_restriction",
            "affects": {"self_only": True},
            "blockers": {"types": ["Creature"], "modified": True},
        }
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(static_probe(static)))
