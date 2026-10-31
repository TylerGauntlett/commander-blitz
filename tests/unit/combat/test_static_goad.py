"""Goad as a static: "Enchanted creature … is goaded" for as long as the Aura is on it.

Rule 701.38a's goad is two "if able" rules -- the creature attacks each combat,
and attacks a player other than the goader. The `goad` op writes that onto the
creature as a mark with a clock (`GameObject.goaded_by`, cleared at the goader's
untap step, or never with ``"permanent"``). The Impetus Auras print it as a
continuous effect instead: it holds exactly while the Aura enchants the
creature, so it must end when the Aura leaves, move when the Aura moves, and
ignore the goader's untap step. A mark cannot do the first two, and
`attacks_if_able` plus `cant_attack_you` is not goad at all -- it forbids
attacking the goader outright, where goad only steers away "if able".

So the `goaded` static is read live by `player_statics.goaders`, which every
reader of goad asks: the compulsion (`combat.attack_required`), the target
restriction (`combat.attack_target_forbidden`), and the ``goaded`` selector and
trigger-filter keys. The goader is the static's controller -- including when
that player controls the creature too, which is the Impetus ruling: the creature
still attacks each combat if able.

The witnesses are Coercive, Ghoulish, Martial and Parasitic Impetus and
Redemption Arc, from the Silverquill Influence precon. `t_sg_impetus` is their
goad clause alone.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import goaders
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.temp_effects import goad_creature
from commanderblitz.engine.triggers import matches_card_filter
from commanderblitz.engine.zones import destroy
from tests.conftest import only_oid, pass_until
from tests.unit.combat.test_goad import can_finish, defenders_offered, to_declare_attackers

IMPETUS = "t_sg_impetus"  # Enchant creature / Enchanted creature is goaded.
BEAR = "t_sg_bear"
CUB = "t_sg_cub"


def enchanted(builder, *, players=3, active=1, on_mine=False):
    """Player 0's Impetus on a Bear, beside an unenchanted Cub, on ``active``'s turn.

    The creatures are player 1's (the printed case: an Aura on an opponent's
    creature), or player 0's own with ``on_mine``. Attached before the position
    advances, as `test_goad.position` builds it from the untap step, so the
    state-based action that bins an unattached Aura never sees one. Returns
    ``(game, bear)``.
    """
    owner = 0 if on_mine else 1
    b = builder(players=players).battlefield(0, [IMPETUS]).battlefield(owner, [BEAR, CUB])
    game = b.active(active).step(Step.UNTAP).build(advance=False)
    bear = only_oid(game, BEAR, owner)
    assert attach(game.state, only_oid(game, IMPETUS, 0), bear)
    game._advance()
    return game, bear


class TestTheCompulsion:
    def test_the_enchanted_creature_must_attack(self, builder):
        game, bear = enchanted(builder)
        assert goaders(game.state, bear) == {0}
        assert combat_mod.attack_required(game.state, bear)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]
        assert not can_finish(game), '"Done attacking" is withheld'

    def test_the_creature_beside_it_is_free(self, builder):
        game, _ = enchanted(builder)
        cub = only_oid(game, CUB, 1)
        assert goaders(game.state, cub) == set()
        assert not combat_mod.attack_required(game.state, cub)

    def test_it_is_never_written_onto_the_creature(self, builder):
        """A mark would outlive the Aura; the static is read live instead."""
        game, bear = enchanted(builder)
        assert game.state.objects[bear].goaded_by == set()


class TestTheTargetRestriction:
    def test_it_attacks_a_player_other_than_the_goader(self, builder):
        game, bear = enchanted(builder)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [2]

    def test_with_only_the_goader_left_it_attacks_the_goader(self, builder):
        """The near miss `cant_attack_you` would leave it nowhere to attack."""
        game, bear = enchanted(builder, players=2)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [0]
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]

    def test_a_second_goader_by_the_op_frees_it_to_attack_either(self, builder):
        """Goaded by everybody left, it may attack anybody: the static's goader
        and the op's goader are two obligations, as two ops' are."""
        game, bear = enchanted(builder)
        assert goad_creature(game.state, bear, 2)
        assert goaders(game.state, bear) == {0, 2}
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [0, 2]


class TestItLastsExactlyAsLongAsTheAura:
    def test_an_unattached_aura_goads_nobody(self, builder):
        """`attached` matches nothing while the Aura is on nothing."""
        game = builder(players=3).battlefield(0, [IMPETUS]).battlefield(1, [BEAR]).build(
            advance=False
        )
        assert goaders(game.state, only_oid(game, BEAR, 1)) == set()

    def test_destroying_the_aura_ends_the_goad(self, builder):
        game, bear = enchanted(builder)
        destroy(game.state, only_oid(game, IMPETUS, 0), cause="test")
        assert goaders(game.state, bear) == set()
        assert not combat_mod.attack_required(game.state, bear)

    def test_moving_the_aura_moves_the_goad(self, builder):
        game, bear = enchanted(builder)
        cub = only_oid(game, CUB, 1)
        attach(game.state, only_oid(game, IMPETUS, 0), cub)
        assert goaders(game.state, cub) == {0}
        assert goaders(game.state, bear) == set()

    def test_the_goaders_untap_step_does_not_end_it(self, builder):
        """The op's clock is the goader's untap step; the static has none.
        Player 2's turn, then player 0 untaps, then player 1's turn again."""
        game, bear = enchanted(builder, active=2)
        pass_until(game, lambda g: g.state.active_player == 1)
        assert goaders(game.state, bear) == {0}
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]


class TestOnYourOwnCreature:
    def test_your_own_enchanted_creature_attacks_each_combat(self, builder):
        """The Impetus ruling: it attacks each combat if able, and may attack any
        opponent -- "a player other than you" is all of them."""
        game, bear = enchanted(builder, active=0, on_mine=True)
        assert goaders(game.state, bear) == {0}
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]
        assert defenders_offered(game, bear) == [1, 2]


class TestTheGoadedFilter:
    def test_the_selector_sees_the_static(self, builder):
        game, bear = enchanted(builder)
        cub = only_oid(game, CUB, 1)
        ctx = EffectContext(game.state, controller=0, source_oid=only_oid(game, IMPETUS, 0))
        base = {"zone": "battlefield", "types": ["Creature"]}
        assert resolve_pool(ctx, {**base, "goaded": True}) == [bear]
        assert resolve_pool(ctx, {**base, "goaded": False}) == [cub]

    def test_the_trigger_filter_sees_the_static(self, builder):
        game, bear = enchanted(builder)
        source = game.state.objects[only_oid(game, IMPETUS, 0)]
        assert matches_card_filter(game.state, bear, {"goaded": True}, source)
        assert not matches_card_filter(game.state, only_oid(game, CUB, 1), {"goaded": True}, source)


class TestTheLoader:
    @pytest.mark.parametrize("affects", [{"attached": True}, None])
    def test_a_goad_with_no_filter_is_refused(self, affects):
        """A missing filter matches nothing: the Aura would print "is goaded"
        and goad nobody."""
        ability = {"kind": "static", "text": "Enchanted creature is goaded.", "effect": "goaded"}
        if affects is not None:
            ability["affects"] = affects
        card = CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Enchant creature\nEnchanted creature is goaded.",
                "mana_cost": "{R}",
                "types": ["Enchantment"],
                "subtypes": ["Aura"],
                "targets": [
                    {
                        "id": "enchanted",
                        "kind": "permanent",
                        "selector": {"zone": "battlefield", "types": ["Creature"]},
                    }
                ],
                "abilities": [ability],
            }
        )
        if affects is None:
            with pytest.raises(DslError, match="goaded needs an 'affects' filter"):
                compile_card(card)
        else:
            compile_card(card)
