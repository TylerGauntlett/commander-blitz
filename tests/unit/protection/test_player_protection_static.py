""""You have protection from the chosen card type." -- 702.16, as a static

    "As Serra's Emissary enters, choose a card type. You and creatures you
    control have protection from the chosen card type."  -- Serra's Emissary

A player could have protection only from a timed grant: Teferi's Protection
installs a `PlayerProtection` on `GameState.player_protections`, and
`characteristics.player_protection_from` read nothing else. No static could
name a seat. `player_hexproof` was the closest static, and it is the wrong
rule twice over: hexproof stops only opponents and prevents no damage.

So `player_protection` is a player-wide static -- `affects_player`, walked by
`player_statics._active_player_statics` -- whose qualities are spelled with
the `protection` static's keys, and it feeds the **same reader**:
`player_protection_from` unions the timed entries with the statics. Every rule
that already asked about a protected seat sees it with no change of its own:

* **damage** from a source of that quality is prevented (`damage_player`);
* the seat **can't be targeted** by such a source, by anyone -- its controller
  included, which is what separates protection from hexproof;
* it **can't be enchanted** by an Aura of that quality (`attach_to_player`).

A player cannot be blocked, so the fourth object-side rule has no seat
counterpart. Without the static feeding the shared reader, the creature half
of Serra's Emissary would work and the "you" half would be a second, partial
implementation -- or nothing.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import player_protected_from, player_protection_from
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach_to_player, damage_player
from commanderblitz.engine.structs import PlayerProtection
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

AEGIS = "t_pps_aegis"  # you have protection from the chosen card type
WARD = "t_pps_ward"  # you have protection from creatures
BEAR = "t_bear"  # green Creature 2/2
BOLT = "t_bolt"  # red Instant, 3 damage to any target
ROBE = "t_seat_robe"  # an Aura that enchants a player

CHOSEN = {"chosen_card_type_of": "self"}


def board(builder, chosen: str | None, *, mine=(AEGIS,), bolt_for: int = 1):
    """Player 0 with the Aegis; player 1 with a Bear; a Bolt in a hand."""
    game = (
        builder(players=2)
        .battlefield(0, [*mine, "mountain"])
        .battlefield(1, [BEAR, "mountain"])
        .hand(bolt_for, [BOLT])
        .library(0, ["mountain"] * 20)
        .library(1, ["mountain"] * 20)
        .active(bolt_for)
        .build()
    )
    if AEGIS in mine:
        game.state.objects[only_oid(game, AEGIS, 0)].chosen_card_type = chosen
        game.state.bump_chars()
    return game


def seat_targets(game) -> set[int]:
    return {
        ref.id
        for action in game.legal_actions()
        if action.kind is ActionKind.CAST
        and game.state.objects[action.source].def_id == BOLT
        for ref in action.targets
        if ref.kind == "player"
    }


class TestTheStaticFeedsTheSharedReader:
    def test_the_chosen_type_is_a_quality_of_the_seat(self, builder):
        game = board(builder, "Instant")
        assert player_protection_from(game.state, 0) == frozenset({"Instant"})

    def test_only_its_controller_has_it(self, builder):
        game = board(builder, "Instant")
        assert player_protection_from(game.state, 1) == frozenset()

    def test_before_a_choice_it_protects_from_nothing(self, builder):
        game = board(builder, None)
        assert player_protection_from(game.state, 0) == frozenset()

    def test_a_literal_quality_reads_the_same_way(self, builder):
        game = board(builder, None, mine=(WARD,))
        assert player_protection_from(game.state, 0) == frozenset({"Creature"})

    def test_it_joins_a_timed_grant(self, builder):
        """One reader, two sources: neither hides the other."""
        game = board(builder, "Instant")
        game.state.player_protections.append(PlayerProtection(player=0, quality="R"))
        game.state.bump_chars()
        assert player_protection_from(game.state, 0) == frozenset({"Instant", "R"})

    def test_it_ends_when_the_permanent_leaves(self, builder):
        game = board(builder, "Instant")
        move_object(game.state, only_oid(game, AEGIS, 0), Zone.GRAVEYARD)
        assert player_protection_from(game.state, 0) == frozenset()


class TestTargeting:
    def test_an_instant_cannot_target_the_protected_player(self, builder):
        game = board(builder, "Instant")
        assert 0 not in seat_targets(game)
        assert 1 in seat_targets(game)

    def test_nor_can_the_protected_players_own(self, builder):
        """Protection, not hexproof: it stops everyone."""
        game = board(builder, "Instant", bolt_for=0)
        assert 0 not in seat_targets(game)

    def test_the_control_another_choice_lets_it_through(self, builder):
        game = board(builder, "Sorcery")
        assert 0 in seat_targets(game)


class TestDamage:
    def test_damage_from_the_chosen_type_is_prevented(self, builder):
        game = board(builder, "Creature")
        bear = only_oid(game, BEAR, 1)
        life = game.state.players[0].life
        assert damage_player(game.state, 0, 2, bear) == 0
        assert game.state.players[0].life == life

    def test_it_is_announced_as_protection(self, builder):
        game = board(builder, "Creature")
        mark = len(game.state.events)
        damage_player(game.state, 0, 2, only_oid(game, BEAR, 1))
        prevented = [e for e in game.state.events[mark:] if e.type == "damage_prevented"]
        assert len(prevented) == 1

    def test_damage_from_another_type_is_dealt(self, builder):
        game = board(builder, "Instant")
        assert damage_player(game.state, 0, 2, only_oid(game, BEAR, 1)) == 2

    def test_a_spell_of_the_chosen_type_is_matched_off_the_battlefield(self, builder):
        """A spell's source is read by its printed types, so an instant on the
        stack -- or, here, in hand -- is an Instant."""
        game = board(builder, "Instant")
        bolt = game.state.players[1].hand[0]
        assert player_protected_from(game.state, 0, bolt)


def aura_position(builder, chosen: str):
    """The Aegis under player 0 and an unattached player Aura under player 1.

    Not advanced: state-based actions would bin an Aura attached to nothing
    before the test could attach it.
    """
    game = (
        builder(players=2)
        .battlefield(0, [AEGIS])
        .battlefield(1, [ROBE])
        .library(0, ["mountain"] * 20)
        .library(1, ["mountain"] * 20)
        .build(advance=False)
    )
    game.state.objects[only_oid(game, AEGIS, 0)].chosen_card_type = chosen
    game.state.bump_chars()
    return game, only_oid(game, ROBE, 1)


class TestEnchanting:
    def test_an_aura_of_the_chosen_type_cannot_enchant_the_player(self, builder):
        game, robe = aura_position(builder, "Enchantment")
        assert not attach_to_player(game.state, robe, 0)
        assert game.state.objects[robe].attached_to_player is None

    def test_the_control_another_choice_lets_it_attach(self, builder):
        game, robe = aura_position(builder, "Creature")
        assert attach_to_player(game.state, robe, 0)


def _model(**static) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_pps_probe",
            "name": "Probe",
            "types": ["Enchantment"],
            "abilities": [{"kind": "static", "effect": "player_protection", **static}],
        }
    )


class TestTheLoader:
    def test_it_loads(self):
        compile_card(_model(affects_player="you", from_types=[CHOSEN]))

    def test_it_needs_a_quality(self):
        with pytest.raises(DslError, match="player_protection needs"):
            compile_card(_model(affects_player="you"))

    def test_it_needs_affects_player(self):
        with pytest.raises(DslError, match="affects_player"):
            compile_card(_model(from_types=["Creature"]))

    def test_an_affects_filter_is_refused(self):
        """The creature half is a separate `protection` static; an `affects`
        here would load clean and be read by nothing."""
        with pytest.raises(DslError, match="separate 'protection' static"):
            compile_card(
                _model(
                    affects_player="you",
                    affects={"types": ["Creature"], "controller": "you"},
                    from_types=["Creature"],
                )
            )

    def test_an_unknown_type_is_refused(self):
        with pytest.raises(DslError, match="unknown type"):
            compile_card(_model(affects_player="you", from_types=["Wizard"]))

    def test_it_cannot_be_granted(self):
        """`_active_player_statics` walks printed faces."""
        from commanderblitz.cards.loader.vocabulary import GRANTABLE_STATIC_EFFECTS

        assert "player_protection" not in GRANTABLE_STATIC_EFFECTS
