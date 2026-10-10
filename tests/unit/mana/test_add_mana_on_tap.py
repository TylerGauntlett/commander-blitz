"""A triggered mana ability: "whenever you tap a Swamp for mana, add an additional {B}".

    Crypt Ghast -- and Nirkana Revenant, Nissa's static, Vernal Bloom,
    Gauntlet of Might and Leyline of Abundance print the same sentence.

Rule 605.1b makes this a *mana ability* even though it is triggered: it triggers
off a mana ability and adds mana. 605.4a makes it resolve immediately, right
after the mana ability that triggered it, without using the stack. So it cannot
be a `triggered` ability in this engine -- tapping for mana happens inside cost
payment, where nothing may be queued or asked -- and the nearest static,
`double_land_mana` (Vorinclex), has no filter on what was tapped and doubles
what the land made rather than adding a fixed {B}.

`add_mana_on_tap` is read at the three places tapped mana is counted:
`costs._sources_of` (the planner: what can I cast?), `costs.activate_mana_ability`
(the payment: what lands in the pool?) and legality's chip label. The first two
disagreeing is the failure that matters: a spell offered on Ghast mana and paid
for without it strands the cast half-paid.

106.12 is why the ability must actually tap: "tap a permanent for mana" means
a mana ability with {T} in its cost. The tapped permanent is matched on its
*current* subtypes, so a land another effect made a Swamp counts (Urborg, Tomb
of Yawgmoth -- the pairing the card is played for).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability, pay_mana
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaCost
from tests.conftest import oids_of

GHAST = "t_crypt_ghast"
TURN_GHAST = "t_turn_ghast"
BLOOM = "t_vernal_bloom"
SWAMP_MAKER = "t_swamp_maker"
FOUR_DROP = "t_black_four_drop"  # {B}{B}{B}{B}

B = SYMBOL_INDEX["B"]
G = SYMBOL_INDEX["G"]


def position(builder, mine=(), theirs=(), *, active: int = 0, hand=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .active(active)
        .build(advance=False)
    )


def tap(game, card_id: str, pid: int) -> list[int]:
    """Tap the first ``card_id`` ``pid`` controls for mana; return their pool."""
    oid = oids_of(game, card_id, pid)[0]
    activate_mana_ability(game.state, oid, 0, pid)
    return list(game.state.players[pid].mana_pool.amounts)


class TestTheExtraMana:
    def test_a_swamp_makes_two_black(self, builder):
        game = position(builder, [GHAST, "swamp"])
        pool = tap(game, "swamp", 0)
        assert pool[B] == 2
        assert sum(pool) == 2

    def test_another_land_makes_only_its_own(self, builder):
        game = position(builder, [GHAST, "forest"])
        pool = tap(game, "forest", 0)
        assert pool[G] == 1
        assert sum(pool) == 1

    def test_without_the_ghast_a_swamp_makes_one(self, builder):
        game = position(builder, ["swamp"])
        assert sum(tap(game, "swamp", 0)) == 1

    def test_two_ghasts_trigger_separately(self, builder):
        game = position(builder, [GHAST, GHAST, "swamp"])
        assert tap(game, "swamp", 0)[B] == 3

    def test_the_extra_pip_is_the_ghasts(self, builder):
        """The triggered ability's source made that mana, not the Swamp."""
        game = position(builder, [GHAST, "swamp"])
        ghast = oids_of(game, GHAST, 0)[0]
        swamp = oids_of(game, "swamp", 0)[0]
        tap(game, "swamp", 0)
        made_by = [pip.source for pip in game.state.players[0].mana_pool.tags[B]]
        assert sorted(made_by) == sorted([ghast, swamp])


class TestWhoseTapsCount:
    def test_an_opponents_swamp_gets_nothing_from_my_ghast(self, builder):
        """ "Whenever *you* tap" -- `affects_player: you`."""
        game = position(builder, [GHAST], ["swamp"])
        assert sum(tap(game, "swamp", 1)) == 1

    def test_any_reaches_every_player_and_pays_the_tapper(self, builder):
        """Vernal Bloom: "its controller adds" -- the mana is the tapper's."""
        game = position(builder, [BLOOM], ["forest"])
        assert tap(game, "forest", 1)[G] == 2
        assert sum(game.state.players[0].mana_pool.amounts) == 0


class TestCurrentCharacteristics:
    def test_a_land_made_a_swamp_counts(self, builder):
        """Urborg's half: a Forest that is also a Swamp adds the extra {B}."""
        game = position(builder, [GHAST, SWAMP_MAKER, "forest"])
        pool = tap(game, "forest", 0)
        assert (pool[G], pool[B]) == (1, 1)


class TestPlannerAndPaymentAgree:
    def test_the_solver_pays_four_black_from_two_swamps(self, builder):
        game = position(builder, [GHAST, "swamp", "swamp"])
        assert pay_mana(game.state, 0, ManaCost.parse("{B}{B}{B}{B}").with_x(0))

    def test_without_the_ghast_it_cannot(self, builder):
        game = position(builder, ["swamp", "swamp"])
        assert not pay_mana(game.state, 0, ManaCost.parse("{B}{B}{B}{B}").with_x(0))

    @staticmethod
    def offered(builder, lands) -> bool:
        game = (
            builder(players=2)
            .battlefield(0, list(lands))
            .hand(0, [FOUR_DROP])
            .active(0)
            .build()
        )
        return any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == FOUR_DROP
            for a in game.legal_actions()
        )

    def test_legality_offers_the_spell_the_extra_mana_affords(self, builder):
        assert self.offered(builder, [GHAST, "swamp", "swamp"])

    def test_and_does_not_offer_it_without(self, builder):
        assert not self.offered(builder, ["swamp", "swamp"])


class TestItWearsOff:
    def test_gone_with_its_source(self, builder):
        game = position(builder, [GHAST, "swamp"])
        game.state.battlefield.remove(oids_of(game, GHAST, 0)[0])
        game.state.bump_chars()
        assert sum(tap(game, "swamp", 0)) == 1

    def test_the_condition_is_asked(self, builder):
        on = position(builder, [TURN_GHAST, "swamp"], active=0)
        assert tap(on, "swamp", 0)[B] == 2
        off = position(builder, [TURN_GHAST, "swamp"], active=1)
        assert tap(off, "swamp", 0)[B] == 1


def _card(**static) -> dict:
    ability = {
        "kind": "static",
        "text": "Whenever you tap a Swamp for mana, add an additional {B}.",
        "effect": "add_mana_on_tap",
        "affects_player": "you",
        "tapped_permanent": {"subtypes": ["Swamp"]},
        "add_mana": "{B}",
    }
    ability.update(static)
    ability = {k: v for k, v in ability.items() if v is not None}
    return {
        "id": "t_bad_ghast",
        "name": "Bad Ghast",
        "oracle_text": ability["text"],
        "mana_cost": "{3}{B}",
        "types": ["Enchantment"],
        "abilities": [ability],
    }


class TestTheLoader:
    def test_the_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))

    @pytest.mark.parametrize(
        "change",
        [
            {"tapped_permanent": None},
            {"add_mana": None},
            {"add_mana": ""},
            {"tapped_permanent": {}},
            {"tapped_permanent": {"controller": "you"}},
            {"tapped_permanent": {"types": ["Lnad"]}},
            {"add_mana": "{Q}"},
            {"affects": {"types": ["Land"]}},
            {"affects_player": None},
        ],
        ids=[
            "no-tapped",
            "no-mana",
            "empty-mana",
            "empty-filter",
            "non-characteristic-key",
            "unknown-type",
            "bad-symbol",
            "affects",
            "no-affects-player",
        ],
    )
    def test_refused(self, change):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(_card(**change)))

    def test_the_keys_are_refused_on_another_static(self):
        card = _card(effect="double_land_mana")
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(card))
