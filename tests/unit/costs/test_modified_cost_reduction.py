""""Costs {1} less for each **modified** creature you control."

    "This spell costs {1} less to cast for each modified creature you control.
    (Equipment, Auras you control, and counters are modifications.)"
                                                -- Walking Skyscraper
    "{4}, {T}: Draw a card. This ability costs {1} less to activate for each
    modified creature you control."             -- Towashi Guide-Bot

700.9: a permanent is modified when it has a counter on it, is equipped, or is
enchanted by an Aura its controller controls. A reduction filter could already
say two of the limbs (`has_counters`, `enchanted_by`) but not the Equipment,
and an `any_of` of the two it had would also price a creature carrying both a
counter and an Aura once per limb if it were written as two reductions.

`cost_reduction._object_matches` reads the key through
`characteristics.is_modified_printed`, the static filter's reader, so a
creature is counted once however many limbs it has. What would be wrong
without each limb:

- **Equipment**: a creature carrying a Sword would not discount Towashi.
- **"Auras you control"**: an opponent's Pacifism on your creature would.
- **Only a permanent**: a creature card in a graveyard with a counter history
  is not modified, and a reduction that named the zone would count it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.statics import _validate_cost_reduction
from commanderblitz.engine.cost_reduction import reduction_amount
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.primitives import add_counters, attach
from tests.conftest import only_oid

BEAR = "t_eb_bear"
CUB = "t_eb_cub"
AURA = "t_eb_aura"  # Enchant creature, nothing else
GEAR = "t_plain_gear"  # an Equipment with nothing printed
SWAMP = "swamp"

#: "…for each modified creature you control", spelled as the loader accepts it.
MODIFIED_CREATURES = {"controller": "you", "types": ["Creature"], "modified": True}


def position(builder, *, mine=(), theirs=(), on_bear=()):
    """Player 0's Bear and Cub; ``on_bear`` lists ``(card_id, seat)``
    attachments put on the Bear before the game advances. Returns
    ``(game, bear, cub)``."""
    b = builder(players=2).battlefield(0, [BEAR, CUB, *mine]).battlefield(1, list(theirs))
    for pid in range(2):
        b.library(pid, [SWAMP] * 20)
    game = b.active(0).step(Step.UNTAP).build(advance=False)
    bear, cub = only_oid(game, BEAR, 0), only_oid(game, CUB, 0)
    for card_id, seat in on_bear:
        assert attach(game.state, only_oid(game, card_id, seat), bear)
    game._advance()
    return game, bear, cub


def discount(game, filt=MODIFIED_CREATURES) -> int:
    return reduction_amount(game.state, 0, {"count": filt})


class TestEachLimbCounts:
    def test_a_bare_board_takes_nothing_off(self, builder):
        game, _, _ = position(builder)
        assert discount(game) == 0

    def test_a_counter(self, builder):
        game, bear, _ = position(builder)
        add_counters(game.state, bear, PLUS_ONE, 1)
        assert discount(game) == 1

    def test_your_equipment(self, builder):
        """The limb an `any_of` of the old keys could not reach."""
        game, _, _ = position(builder, mine=[GEAR], on_bear=[(GEAR, 0)])
        assert discount(game) == 1

    def test_an_opponents_equipment(self, builder):
        """Equipped is equipped, whoever's Equipment it is."""
        game, _, _ = position(builder, theirs=[GEAR], on_bear=[(GEAR, 1)])
        assert discount(game) == 1

    def test_your_aura(self, builder):
        game, _, _ = position(builder, mine=[AURA], on_bear=[(AURA, 0)])
        assert discount(game) == 1

    def test_an_opponents_aura_is_not_a_modification(self, builder):
        game, _, _ = position(builder, theirs=[AURA], on_bear=[(AURA, 1)])
        assert discount(game) == 0


class TestItCountsCreaturesNotModifications:
    def test_a_creature_with_every_limb_counts_once(self, builder):
        game, bear, _ = position(
            builder, mine=[GEAR, AURA], on_bear=[(GEAR, 0), (AURA, 0)]
        )
        add_counters(game.state, bear, PLUS_ONE, 2)
        assert discount(game) == 1

    def test_two_modified_creatures_take_two_off(self, builder):
        game, bear, cub = position(builder)
        add_counters(game.state, bear, PLUS_ONE, 1)
        add_counters(game.state, cub, PLUS_ONE, 1)
        assert discount(game) == 2

    def test_an_opponents_modified_creature_does_not_count(self, builder):
        """Priced for player 1, player 0's countered Bear is someone else's."""
        game, bear, _ = position(builder)
        add_counters(game.state, bear, PLUS_ONE, 1)
        assert reduction_amount(game.state, 1, {"count": MODIFIED_CREATURES}) == 0


class TestTheLoader:
    def test_the_key_is_accepted(self):
        _validate_cost_reduction({"count": MODIFIED_CREATURES}, "t")

    def test_inside_any_of(self):
        _validate_cost_reduction(
            {"count": {"controller": "you", "any_of": [{"modified": True}, {"tapped": True}]}},
            "t",
        )

    @pytest.mark.parametrize("value", [False, {"counter": "+1/+1"}])
    def test_true_only(self, value):
        with pytest.raises(DslError, match="modified: true only"):
            _validate_cost_reduction(
                {"count": dict(MODIFIED_CREATURES, modified=value)}, "t"
            )
