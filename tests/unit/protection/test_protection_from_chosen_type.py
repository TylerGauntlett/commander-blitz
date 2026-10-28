""""…have protection from the chosen card type." -- 702.16a

    "As Serra's Emissary enters, choose a card type. You and creatures you
    control have protection from the chosen card type."  -- Serra's Emissary

The `protection` static's `from_types` held only literal type names, checked
against `KNOWN_TYPES` at load time. The answer `choose_type` writes to
`chosen_card_type` was read only by a selector's `types`, so "protection from
the chosen card type" had nowhere to be read and the card could not be written.

It is the colour substitution again, one key over:
``{"chosen_card_type_of": "self"}`` in `from_types`, replaced by
`characteristics.resolve_chosen_card_type_list` inside `protection_from` -- at
the moment a rule asks, not at load time, because the choice does not exist
until the permanent is on the battlefield. Because the substitution happens in
`protection_from`, all four rules that read it (damage, enchant/equip, block,
target) see it without knowing it was chosen.

The boundaries: before a choice the static protects from **nothing** (not from
everything), a type other than the chosen one walks straight through, and a
granted copy of the static is refused, since its source would be the recipient,
which has chosen nothing.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import protected_from, protection_from
from commanderblitz.engine.combat import can_block
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_permanent
from commanderblitz.engine.structs import CombatState
from tests.conftest import only_oid

WARDEN = "t_pct_warden"  # creatures you control have protection from the chosen type
BEAR = "t_bear"  # green Creature 2/2
BOLT = "t_bolt"  # red Instant, 3 damage to any target

CHOSEN = {"chosen_card_type_of": "self"}


def board(builder, chosen: str | None):
    """Our Warden and Bear; their Bear and a Bolt in their hand."""
    game = (
        builder(players=2)
        .battlefield(0, [WARDEN, BEAR])
        .battlefield(1, [BEAR, "mountain"])
        .hand(1, [BOLT])
        .library(0, ["plains"] * 20)
        .library(1, ["mountain"] * 20)
        .active(1)
        .build()
    )
    warden = only_oid(game, WARDEN, 0)
    game.state.objects[warden].chosen_card_type = chosen
    game.state.bump_chars()
    return game, warden, only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)


def bolt_targets(game) -> set[int]:
    return {
        ref.id
        for action in game.legal_actions()
        if action.kind is ActionKind.CAST
        and game.state.objects[action.source].def_id == BOLT
        for ref in action.targets
        if ref.kind != "player"
    }


class TestTheChosenTypeIsTheQuality:
    def test_it_reads_the_choice(self, builder):
        game, _, ours, _ = board(builder, "Instant")
        assert "Instant" in protection_from(game.state, ours)

    def test_the_source_has_it_too(self, builder):
        """"Creatures you control" includes the Emissary itself."""
        game, warden, _, _ = board(builder, "Instant")
        assert "Instant" in protection_from(game.state, warden)

    def test_before_a_choice_it_protects_from_nothing(self, builder):
        """Not from everything: the window before the choice grants nobody
        anything."""
        game, _, ours, _ = board(builder, None)
        assert protection_from(game.state, ours) == frozenset()

    def test_a_later_choice_is_followed(self, builder):
        game, warden, ours, _ = board(builder, "Instant")
        game.state.objects[warden].chosen_card_type = "Sorcery"
        game.state.bump_chars()
        assert protection_from(game.state, ours) == frozenset({"Sorcery"})

    def test_it_does_not_reach_the_opponents_creatures(self, builder):
        game, _, _, theirs = board(builder, "Instant")
        assert protection_from(game.state, theirs) == frozenset()


class TestTheFourRulesSeeIt:
    def test_an_instant_cannot_target_a_protected_creature(self, builder):
        game, warden, ours, theirs = board(builder, "Instant")
        targets = bolt_targets(game)
        assert ours not in targets
        assert warden not in targets
        assert theirs in targets

    def test_the_control_another_choice_lets_the_instant_through(self, builder):
        """A type other than the chosen one walks straight through."""
        game, _, ours, _ = board(builder, "Creature")
        assert ours in bolt_targets(game)

    def test_damage_from_a_creature_is_prevented(self, builder):
        game, _, ours, theirs = board(builder, "Creature")
        assert protected_from(game.state, ours, theirs)
        assert damage_permanent(game.state, ours, 2, theirs) == 0

    def test_damage_from_another_type_is_dealt(self, builder):
        game, _, ours, theirs = board(builder, "Instant")
        assert damage_permanent(game.state, ours, 2, theirs) == 2

    def test_a_creature_of_the_chosen_type_cannot_block_it(self, builder):
        game, _, ours, theirs = board(builder, "Creature")
        game.state.combat = CombatState(attackers={ours: 1})
        game.state.bump_chars()
        assert not can_block(game.state, theirs, ours, 1)


def _warden_model(**static) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_pct_probe",
            "name": "Probe",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "static",
                    "effect": "protection",
                    "affects": {"controller": "you", "types": ["Creature"]},
                    **static,
                }
            ],
        }
    )


class TestTheLoader:
    def test_the_chosen_entry_loads(self):
        compile_card(_warden_model(from_types=[CHOSEN]))

    def test_it_loads_beside_a_literal(self):
        compile_card(_warden_model(from_types=["Planeswalker", CHOSEN]))

    def test_a_near_miss_is_refused(self):
        """Unrefused it would resolve to nothing and protect from nothing."""
        with pytest.raises(DslError, match="chosen_card_type_of"):
            compile_card(_warden_model(from_types=[{"chosen_card_type_of": "other"}]))

    def test_the_colour_leaf_is_not_a_type(self):
        with pytest.raises(DslError, match="chosen_card_type_of"):
            compile_card(_warden_model(from_types=[{"chosen_color_of": "self"}]))

    def test_a_granted_copy_is_refused(self):
        """A granted static's source is its recipient, which has chosen
        nothing -- so the author's "the chosen type" would read the wrong
        permanent and protect from nothing."""
        spec = {
            "id": "t_pct_granter",
            "name": "Granter",
            "mana_cost": "{2}{W}",
            "types": ["Enchantment"],
            "grantable_abilities": [
                {
                    "kind": "static",
                    "text": "This creature has protection from the chosen card type.",
                    "effect": "protection",
                    "affects": {"self_only": True},
                    "from_types": [CHOSEN],
                }
            ],
            "abilities": [
                {
                    "kind": "static",
                    "text": 'Creatures you control have "..."',
                    "effect": "grant_ability",
                    "affects": {"types": ["Creature"], "controller": "you"},
                    "ability": 0,
                }
            ],
        }
        with pytest.raises(DslError, match="chosen_card_type_of"):
            compile_card(CardModel.model_validate(spec))
