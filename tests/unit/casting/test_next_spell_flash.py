"""A single-use flash permission for the next spell of the chosen type.

    Witness, Progenitor's Icon -- "As this artifact enters, choose a creature
    type. / {T}: The next spell of the chosen type you cast this turn can be
    cast as though it had flash."

`grant_flash_permission` wrote a permission that lasted its whole duration and
named card types only, so the Icon would have read as "Goblins have flash this
turn" -- every Goblin, not the next one. `next_spell` makes it single-use and
`subtypes` narrows it by creature type (205.3m), with the type the Icon chose
snapshotted as the ability resolves.

The claims, each pinned below:

- **The next Goblin, at instant speed.** And only the next: the second Goblin
  is back to sorcery speed.
- **Spent by the cast, not by the timing.** "The next spell of the chosen type
  you cast this turn" is the next one *cast* (the 2017 ruling): a Goblin cast
  in your main phase, where it never needed the permission, still uses it up.
- **Only a spell of the type spends it.** A Bear cast in between leaves it
  waiting; a changeling is every creature type and spends it.
- **Two activations, one spell.** Each is an effect about "the next spell of
  the chosen type", so they name the same spell, and that spell spends both.
- **This turn.** Cleanup ends an unused one.
- **The type is last-known information.** An Icon destroyed in response still
  grants its flash, for the type it chose; an Icon that chose nothing grants
  nothing.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.actions import PendingDecision
from commanderblitz.engine.casting import _timing_ok
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.temp_effects import (
    clear_flash_permissions,
    consume_next_spell_flash_permissions,
)
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, activations, settle

ICON = "t_nsf_icon"
GOBLIN = "t_nsf_goblin"
BEAR = "t_nsf_bear"
CHANGELING = "t_nsf_changeling"


def position(builder, hand, *, icons=1, step=Step.UPKEEP, chosen="Goblin", lands=()):
    """Player 0 in their own ``step`` with ``icons`` Icons that chose ``chosen``."""
    game = (
        builder(players=2)
        .battlefield(0, [ICON] * icons + ["mountain"] * 4 + list(lands))
        .hand(0, list(hand))
        .step(step)
        .build(advance=False)
    )
    icon_oids = [o for o in game.state.battlefield if game.state.objects[o].def_id == ICON]
    for oid in icon_oids:
        game.state.objects[oid].chosen_type = chosen
    # Frozen with player 0 holding priority, as `build(advance=False)` leaves
    # nobody holding it.
    game.state.pending_decision = PendingDecision(kind=DecisionKind.PRIORITY, player=0)
    return game, icon_oids


def activate(game, icon):
    game.apply(activations(game, icon)[0])
    settle(game)


def castable(game, card_id) -> bool:
    """May player 0 cast ``card_id`` at instant speed now?

    Asked of the timing check rather than of the legal actions, because the
    engine's auto-pass walks a player with nothing to do into their main
    phase, where every creature is castable and the question is moot.
    """
    return _timing_ok(game.state, 0, game.state.registry.get(card_id), sorcery_speed=False)


def cast(game, card_id):
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    settle(game)


class TestTheNextGoblin:
    def test_a_goblin_is_sorcery_speed_without_it(self, builder):
        game, _ = position(builder, [GOBLIN])
        assert not castable(game, GOBLIN)

    def test_the_next_goblin_may_be_cast_at_instant_speed(self, builder):
        game, (icon,) = position(builder, [GOBLIN])
        activate(game, icon)
        assert game.state.step is Step.UPKEEP
        cast(game, GOBLIN)  # a legal action, in the upkeep
        assert [game.state.objects[o].def_id for o in game.state.battlefield].count(GOBLIN) == 1

    def test_the_second_goblin_is_not(self, builder):
        game, (icon,) = position(builder, [GOBLIN, GOBLIN])
        activate(game, icon)
        cast(game, GOBLIN)
        assert not castable(game, GOBLIN), "single-use: the first Goblin spent it"
        assert game.state.flash_permissions == []


class TestSpentByTheCast:
    def test_a_goblin_cast_at_sorcery_speed_still_spends_it(self, builder):
        game, (icon,) = position(builder, [GOBLIN, GOBLIN], step=Step.PRECOMBAT_MAIN)
        activate(game, icon)
        cast(game, GOBLIN)
        assert game.state.flash_permissions == [], (
            "the next Goblin cast is the next Goblin cast, whether it needed flash or not"
        )

    def test_reading_the_permission_spends_nothing(self, builder):
        game, (icon,) = position(builder, [GOBLIN])
        activate(game, icon)
        goblin = game.state.registry.get(GOBLIN)
        for _ in range(3):
            assert _timing_ok(game.state, 0, goblin, sorcery_speed=False)
        assert len(game.state.flash_permissions) == 1


class TestOnlyASpellOfTheType:
    def test_a_bear_in_between_does_not_spend_it(self, builder):
        game, (icon,) = position(builder, [BEAR, GOBLIN], step=Step.PRECOMBAT_MAIN)
        activate(game, icon)
        cast(game, BEAR)
        assert len(game.state.flash_permissions) == 1

    def test_a_bear_is_not_given_flash(self, builder):
        game, (icon,) = position(builder, [BEAR])
        activate(game, icon)
        assert not castable(game, BEAR)

    def test_a_changeling_is_a_goblin(self, builder):
        game, (icon,) = position(builder, [CHANGELING, GOBLIN])
        activate(game, icon)
        assert castable(game, CHANGELING)
        cast(game, CHANGELING)
        assert not castable(game, GOBLIN), "the changeling was the next Goblin"

    def test_another_players_spell_does_not_spend_it(self, builder):
        game, (icon,) = position(builder, [GOBLIN])
        activate(game, icon)
        goblin = game.state.registry.get(GOBLIN)
        consume_next_spell_flash_permissions(game.state, 1, goblin)
        assert len(game.state.flash_permissions) == 1


class TestTwoActivations:
    def test_one_spell_spends_both(self, builder):
        game, icons = position(builder, [GOBLIN, GOBLIN], icons=2)
        for icon in icons:
            activate(game, icon)
        assert len(game.state.flash_permissions) == 2
        cast(game, GOBLIN)
        assert not castable(game, GOBLIN), "both effects named the same next Goblin"

    def test_icons_of_different_types_are_spent_separately(self, builder):
        game, (goblin_icon, bear_icon) = position(builder, [GOBLIN, BEAR], icons=2)
        game.state.objects[bear_icon].chosen_type = "Bear"
        activate(game, goblin_icon)
        activate(game, bear_icon)
        cast(game, GOBLIN)
        assert castable(game, BEAR)


class TestThisTurn:
    def test_cleanup_ends_an_unused_one(self, builder):
        game, (icon,) = position(builder, [GOBLIN])
        activate(game, icon)
        clear_flash_permissions(game.state, "this_turn")
        assert not castable(game, GOBLIN)


class TestTheChosenType:
    def test_an_icon_gone_in_response_still_grants_its_type(self, builder):
        # An instant and an Island, so player 0 holds priority over the
        # ability instead of the auto-pass resolving it at once.
        game, (icon,) = position(builder, [GOBLIN, "opt"], lands=["island"])
        game.apply(activations(game, icon)[0])
        assert game.state.stack
        move_object(game.state, icon, Zone.GRAVEYARD)
        assert game.state.objects[icon].chosen_type is None
        settle(game)
        assert castable(game, GOBLIN)

    def test_an_icon_that_chose_nothing_grants_nothing(self, builder):
        game, (icon,) = position(builder, [GOBLIN], chosen=None)
        activate(game, icon)
        assert game.state.flash_permissions == []
        assert not castable(game, GOBLIN)


class TestTheLoaderGuard:
    def _card(self, **extra):
        effect = {"op": "grant_flash_permission", "duration": "this_turn", **extra}
        return CardModel.model_validate(
            {
                "id": "t_nsf_probe",
                "name": "Probe",
                "oracle_text": "Probe.",
                "mana_cost": "{U}",
                "types": ["Instant"],
                "spell_effects": [effect],
            }
        )

    def test_the_icon_shape_loads(self):
        compile_card(self._card(subtypes=[{"chosen_type_of": "self"}], next_spell=True))

    def test_a_literal_creature_type_loads(self):
        compile_card(self._card(subtypes=["Goblin"], next_spell=True))

    def test_a_near_miss_chosen_entry_is_refused(self):
        with pytest.raises(DslError, match="chosen_type_of"):
            compile_card(self._card(subtypes=[{"chosen_type_of": "source"}]))

    def test_a_subtype_that_is_not_a_creature_type_is_refused(self):
        with pytest.raises(DslError, match="creature type"):
            compile_card(self._card(subtypes=["Equipment"]))

    def test_next_spell_is_a_flag(self):
        with pytest.raises(DslError, match="next_spell"):
            compile_card(self._card(next_spell="yes"))
