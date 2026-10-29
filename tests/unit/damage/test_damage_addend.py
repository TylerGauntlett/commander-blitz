"""Adding to damage: "it deals that much damage plus 1 instead".

    "If another source you control would deal damage to an opponent or a
     permanent an opponent controls, it deals that much damage plus 1
     instead."                              -- Thor, Asgard's Avenger

Rule 614.1a makes it a replacement effect, the same family as Twinflame
Tyrant's "double that damage", and it could not be written as one:
`replace_damage` carried only `damage_multiplier`, which the loader refuses
below 2, and "plus 1" is not a multiplier at any size. So the static grew a
second axis, `damage_addend`, exactly as `replace_life_gain` has `gain_addend`
beside `gain_multiplier`, and a static uses one or the other.

The near miss is a "whenever a source you control deals damage" trigger that
deals 1 more, and it is a different card: the extra point is a second event,
so it uses the stack, triggers every "whenever dealt damage" twice, gains a
lifelinker 1 separately and lets a creature die to the first hit before the
second arrives.

The claims, each of which an implementation could get wrong while a plain
"3 becomes 4" assertion still passed:

* **Per event, and only to what is dealt** (614.1a, 120.8): a 0-damage event
  and a hit protection prevents entirely are not dealt, so nothing is added.
* **"Another source you control"**, in any zone -- the burn spell on the stack
  is a source (109.5) -- and never Thor itself.
* **Outwards only**: the recipient filters are `replace_damage`'s union, so
  your own creature and your own face are untouched.
* **Against a doubler the order is the affected player's** (616.1). Under
  Furnace of Rath a 3 is 3*2+1 = 7 or (3+1)*2 = 8, and the opponent being
  hit picks 7. The damage primitives cannot ask -- combat damage reaches
  them -- so `replaced_damage` applies multipliers first, whichever
  permanent arrived first. When the damage is turned into +1/+1 counters
  (Panther Habit) the permanent's controller wants the larger number, so
  there the addend goes first. Recorded as a divergence in
  rules-coverage.md: an affected player who wanted the other order cannot
  have it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.player_statics import damage_addend, damage_multiplier
from commanderblitz.engine.primitives import attach, damage_permanent, damage_player
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until, two_seat_board

THOR = "t_da_thor"  # "another source you control", plus 1, outwards only
BEAR = "t_rd_bear"  # 2/2
OGRE = "t_rd_ogre"  # 3/9
LINKER = "t_rd_lifelinker"  # 2/2 lifelink
FURNACE = "t_rd_furnace"  # any damage doubled
SCORCH = "t_rd_scorch"  # {R} instant, 3 damage to target player
HABIT = "t_pc_habit"  # damage to equipped creature becomes +1/+1 counters
WARDED = "t_pc_warded"  # protection from red
RED_OGRE = "t_pc_ogre"  # red 3/3


def position(builder, mine=(THOR, BEAR), theirs=(OGRE,)):
    """Player 0's ``mine`` facing player 1's ``theirs``, frozen in main phase.

    Returns ``(game, oid)`` with ``oid`` player 0's first `BEAR` or, without
    one, its first card -- the dealer most tests want.
    """
    game = two_seat_board(builder, mine=list(mine), theirs=list(theirs), advance=False)
    dealer_id = BEAR if BEAR in mine else mine[0]
    dealer = next(
        oid
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == dealer_id
        and game.state.objects[oid].controller == 0
    )
    return game, dealer


def life_lost(game, pid: int, hit) -> int:
    before = game.state.players[pid].life
    hit()
    return before - game.state.players[pid].life


class TestTheAddendItself:
    """`damage_addend` reads the same statics `damage_multiplier` does."""

    def test_your_creature_hitting_an_opponent_adds_one(self, builder):
        game, bear = position(builder)
        assert damage_addend(game.state, bear, None, target_pid=1, is_combat=True) == 1

    def test_an_addend_is_not_a_multiplier(self, builder):
        """Thor's static reads as x1 on the other axis, never x0."""
        game, bear = position(builder)
        assert damage_multiplier(game.state, bear, None, target_pid=1, is_combat=True) == 1

    def test_a_multiplier_is_not_an_addend(self, builder):
        game, bear = position(builder, mine=(FURNACE, BEAR))
        assert damage_addend(game.state, bear, None, target_pid=1, is_combat=True) == 0

    def test_two_thors_add_two(self, builder):
        """614.5: two replacements, each applied once -- plus 1, then plus 1."""
        game, bear = position(builder, mine=(THOR, THOR, BEAR))
        assert life_lost(game, 1, lambda: damage_player(game.state, 1, 2, bear)) == 4


class TestOutwardsOnly:
    def test_damage_to_an_opponent(self, builder):
        game, bear = position(builder)
        assert life_lost(game, 1, lambda: damage_player(game.state, 1, 2, bear)) == 3

    def test_damage_to_an_opponents_permanent(self, builder):
        game, bear = position(builder)
        their_ogre = only_oid(game, OGRE, 1)
        assert damage_permanent(game.state, their_ogre, 2, bear, is_combat=True) == 3
        assert game.state.objects[their_ogre].damage == 3

    def test_damage_to_you_is_untouched(self, builder):
        game, bear = position(builder)
        assert life_lost(game, 0, lambda: damage_player(game.state, 0, 2, bear)) == 2

    def test_damage_to_your_own_permanent_is_untouched(self, builder):
        game, bear = position(builder, mine=(THOR, BEAR, OGRE), theirs=())
        my_ogre = only_oid(game, OGRE, 0)
        assert damage_permanent(game.state, my_ogre, 2, bear) == 2

    def test_an_opponents_source_is_untouched(self, builder):
        """"A source **you control**": their creature hitting their own face,
        or yours, is not Thor's business."""
        game, _ = position(builder, mine=(THOR,), theirs=(BEAR, OGRE))
        theirs = only_oid(game, BEAR, 1)
        assert life_lost(game, 0, lambda: damage_player(game.state, 0, 2, theirs)) == 2


class TestAnotherSource:
    def test_thor_himself_is_not_another_source(self, builder):
        """`exclude_self`: Thor's own blow is 4, not 5."""
        game, thor = position(builder, mine=(THOR,))
        assert life_lost(game, 1, lambda: damage_player(game.state, 1, 4, thor)) == 4

    def test_but_a_second_thor_is(self, builder):
        game, first = position(builder, mine=(THOR, THOR))
        assert life_lost(game, 1, lambda: damage_player(game.state, 1, 4, first)) == 5

    def test_your_burn_spell_is_a_source(self, builder):
        """109.5: the resolving instant deals the damage. A dealer filter read
        through `_matches` would refuse it for being off the battlefield, and
        Thor would add nothing to the spells he is mostly about."""
        game = (
            builder(players=2)
            .battlefield(0, [THOR, "mountain"])
            .hand(0, [SCORCH])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        life = game.state.players[1].life
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and a.source is not None
            and game.state.objects[a.source].def_id == SCORCH
            and TargetRef.player(1) in a.targets
        )
        game.apply(cast)
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.players[1].life == life - 4


class TestOnlyDamageThatIsDealt:
    def test_zero_damage_stays_zero(self, builder):
        """120.8: 0 damage is not dealt, so there is nothing to add 1 to."""
        game, bear = position(builder)
        assert life_lost(game, 1, lambda: damage_player(game.state, 1, 0, bear)) == 0

    def test_a_fully_prevented_hit_stays_prevented(self, builder):
        """Protection prevents all of it; the opponent applies the prevention
        first (616.1) and there is no damage left to replace."""
        game, _ = position(builder, mine=(THOR, RED_OGRE), theirs=(WARDED,))
        ogre = only_oid(game, RED_OGRE, 0)
        warded = only_oid(game, WARDED, 1)
        assert damage_permanent(game.state, warded, 3, ogre, is_combat=True) == 0
        assert game.state.objects[warded].damage == 0

    def test_it_lifts_when_thor_leaves(self, builder):
        game, bear = position(builder)
        move_object(game.state, only_oid(game, THOR), Zone.GRAVEYARD)
        game.state.bump_chars()
        assert life_lost(game, 1, lambda: damage_player(game.state, 1, 2, bear)) == 2


class TestOneEventCarryingTheReplacedAmount:
    def test_lifelink_gains_the_replaced_amount(self, builder):
        """702.15b: "that much life" is what was dealt -- 3, in one gain."""
        game, _ = position(builder, mine=(THOR, LINKER))
        linker = only_oid(game, LINKER, 0)
        life = game.state.players[0].life
        mark = len(game.state.events)
        damage_player(game.state, 1, 2, linker, is_combat=True)
        assert game.state.players[0].life == life + 3
        dealt = [e for e in game.state.events[mark:] if e.type == "damage_dealt"]
        assert [e.data["amount"] for e in dealt] == [3]


class TestTheOrderAgainstADoubler:
    """616.1: the affected player orders Thor against Furnace of Rath."""

    @pytest.mark.parametrize("mine", [(THOR, FURNACE, BEAR), (FURNACE, THOR, BEAR)])
    def test_the_opponent_takes_the_smaller_hit(self, builder, mine):
        """3*2+1 = 7, not (3+1)*2 = 8 -- whichever permanent arrived first."""
        game, bear = position(builder, mine=mine)
        assert life_lost(game, 1, lambda: damage_player(game.state, 1, 3, bear)) == 7

    def test_the_same_on_a_permanent(self, builder):
        game, bear = position(builder, mine=(THOR, FURNACE, BEAR))
        their_ogre = only_oid(game, OGRE, 1)
        assert damage_permanent(game.state, their_ogre, 3, bear) == 7

    def test_damage_into_counters_takes_the_larger_number(self, builder):
        """Panther Habit on their creature: its controller wants the most
        counters, so the addend goes first -- (3+1)*2 = 8."""
        game, _ = position(builder, mine=(THOR, FURNACE, OGRE), theirs=(HABIT, BEAR))
        ogre = only_oid(game, OGRE, 0)
        their_bear = only_oid(game, BEAR, 1)
        assert attach(game.state, only_oid(game, HABIT), their_bear)
        game.state.bump_chars()
        damage_permanent(game.state, their_bear, 3, ogre)
        assert game.state.objects[their_bear].counter(PLUS_ONE) == 8
        assert game.state.objects[their_bear].damage == 0


class TestTheLoaderGuard:
    TEXT = "If a source would deal damage, it deals that much damage plus 1 instead."

    def _card(self, **static):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": self.TEXT,
                "mana_cost": "{R}",
                "types": ["Enchantment"],
                "abilities": [
                    {"kind": "static", "text": self.TEXT, "effect": "replace_damage", **static}
                ],
            }
        )

    def test_the_addend_reaches_the_compiled_static(self):
        """Pinned on the compiled dict, because the whitelist copy loop is where
        a new key is dropped -- and a dropped addend loads as a static nobody
        reads."""
        card = compile_card(
            self._card(
                damage_addend=1,
                damage_source={"controller": "you", "exclude_self": True},
                affects_player="opponent",
                affects={"controller": "opponent"},
            )
        )
        static = card.abilities[0].static
        assert static["damage_addend"] == 1
        assert "damage_multiplier" not in static

    def test_both_axes_are_refused(self):
        with pytest.raises(DslError, match="not both"):
            compile_card(self._card(damage_addend=1, damage_multiplier=2))

    def test_neither_axis_is_refused(self):
        with pytest.raises(DslError, match="needs 'damage_multiplier'"):
            compile_card(self._card())

    def test_an_addend_of_zero_is_refused(self):
        with pytest.raises(DslError, match="must be 1 or more"):
            compile_card(self._card(damage_addend=0))

    def test_the_addend_means_nothing_elsewhere(self):
        model = CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Creatures you control have flying.",
                "mana_cost": "{U}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Creatures you control have flying.",
                        "effect": "grant_keyword",
                        "keywords": ["flying"],
                        "affects": {"types": ["Creature"]},
                        "damage_addend": 1,
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="only mean"):
            compile_card(model)
