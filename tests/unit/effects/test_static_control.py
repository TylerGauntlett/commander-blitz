"""A static control effect: "You control enchanted creature."

Control Magic's line, Become the Pilot's, and Fealty to the Realm's "The monarch
controls enchanted creature." Rule 613.1b puts control-changing effects in layer
2, and a static ability's effect applies for exactly as long as the static does
(611.3a), in timestamp order with the other effects of its layer (613.7, an
Aura's timestamp being when it became attached, 613.7e). So the creature changes
hands when the Aura arrives, goes back when the Aura leaves or moves, and -- for
Fealty -- follows the crown around the table (721) and goes nowhere while nobody
holds it.

The `gain_control` op is the near miss and it is wrong three ways: it is
one-shot, so the creature stays stolen when the Aura is destroyed or moved; it
reads the monarch once, so the creature does not follow the crown; and an enters
trigger would miss an Aura attached later. The `control` static is enforced by
`primitives.reconcile_static_control` in every state-based-action pass (ADR
0030), and every move goes through `change_control`, so 302.6 (summoning
sickness) and 506.4 (removal from combat) apply both ways.

613.7 also decides what happens when a second control effect lands on top: the
later one wins. A permanent steal made after the Aura outlives the Aura, and an
until-end-of-turn steal on top of it hands the creature back to the Aura's seat
at cleanup, after which the static holds it again.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import (
    attach,
    become_monarch,
    change_control,
    clear_until_eot,
    lose_all_abilities_timed,
    reconcile_static_control,
)
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import destroy
from tests.conftest import event_types, find_action, only_oid, pass_until

MAGIC = "t_scm_magic"  # Enchant creature / You control enchanted creature.
FEALTY = "t_scm_fealty"  # Enchant creature / The monarch controls enchanted creature.
BEAR = "t_scm_bear"


def enchanted(builder, aura: str = MAGIC, *, players: int = 3, bears: int = 1):
    """Player 0's ``aura`` attached to player 1's Bear, before any SBA pass.

    Returns ``(game, aura_oid, bear_oid)``. Nothing has changed hands yet:
    the static is enforced by the next state-based-action pass.
    """
    game = (
        builder(players=players)
        .battlefield(0, [aura])
        .battlefield(1, [BEAR] * bears)
        .build(advance=False)
    )
    aura_oid = only_oid(game, aura, 0)
    bear = next(oid for oid in game.state.battlefield if game.state.objects[oid].def_id == BEAR)
    assert attach(game.state, aura_oid, bear)
    return game, aura_oid, bear


def controller(game, oid: int) -> int:
    return game.state.objects[oid].controller


def holds(game, oid: int) -> list:
    return [t for t in game.state.objects[oid].until_eot if t.while_static]


class TestTheAuraTakesIt:
    def test_the_creature_changes_hands_at_the_next_check(self, builder):
        game, _, bear = enchanted(builder)
        assert controller(game, bear) == 1
        sba.run(game.state)
        assert controller(game, bear) == 0
        assert game.state.objects[bear].owner == 1

    def test_it_is_summoning_sick_for_its_new_controller(self, builder):
        """302.6: it has not been player 0's since their turn began."""
        game, _, bear = enchanted(builder)
        assert not game.state.objects[bear].summoning_sick(game.state.turn)
        sba.run(game.state)
        assert game.state.objects[bear].summoning_sick(game.state.turn)

    def test_the_change_is_announced_by_the_aura(self, builder):
        game, aura, _ = enchanted(builder)
        before = len(game.state.events)
        sba.run(game.state)
        new = list(game.state.events)[before:]
        assert EventType.CONTROL_CHANGED in event_types(new)
        event = next(e for e in new if e.type == EventType.CONTROL_CHANGED)
        assert (event.data["from"], event.data["to"], event.data["by"]) == (1, 0, aura)

    def test_casting_the_aura_takes_it(self, builder):
        game = builder(players=2).hand(0, [MAGIC]).battlefield(1, [BEAR]).build()
        bear = only_oid(game, BEAR, 1)
        aura = game.state.players[0].hand[0]
        game.apply(
            find_action(game, ActionKind.CAST, source=aura, targets=(TargetRef.obj(bear),))
        )
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.objects[aura].attached_to == bear
        assert controller(game, bear) == 0

    def test_only_the_enchanted_creature_is_taken(self, builder):
        game, _, bear = enchanted(builder, bears=2)
        other = next(
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].def_id == BEAR and oid != bear
        )
        sba.run(game.state)
        assert controller(game, other) == 1


class TestItIsIdempotent:
    def test_a_second_pass_changes_nothing(self, builder):
        game, _, bear = enchanted(builder)
        assert reconcile_static_control(game.state) is True
        before = len(game.state.events)
        entries = [t.to_dict() for t in holds(game, bear)]
        assert reconcile_static_control(game.state) is False
        assert len(game.state.events) == before
        assert [t.to_dict() for t in holds(game, bear)] == entries

    def test_one_entry_per_aura_and_creature(self, builder):
        game, aura, bear = enchanted(builder)
        for _ in range(3):
            sba.run(game.state)
        [entry] = holds(game, bear)
        assert entry.kind == "control" and entry.source == aura
        assert (entry.previous_controller, entry.new_controller) == (1, 0)

    def test_cleanup_does_not_end_it(self, builder):
        game, _, bear = enchanted(builder)
        sba.run(game.state)
        clear_until_eot(game.state)
        assert controller(game, bear) == 0
        assert holds(game, bear)


class TestTheAuraLetsGo:
    def test_destroying_the_aura_hands_it_back(self, builder):
        game, aura, bear = enchanted(builder)
        sba.run(game.state)
        destroy(game.state, aura)
        sba.run(game.state)
        assert controller(game, bear) == 1
        assert not holds(game, bear)

    def test_the_handback_sickens_it_again(self, builder):
        """302.6 coming home: somebody else had it since its owner's turn began."""
        game, aura, bear = enchanted(builder)
        sba.run(game.state)
        game.state.turn += 1
        destroy(game.state, aura)
        sba.run(game.state)
        assert game.state.objects[bear].summoning_sick(game.state.turn)

    def test_moving_the_aura_hands_the_first_back_and_takes_the_second(self, builder):
        game, aura, bear = enchanted(builder, bears=2)
        other = next(
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].def_id == BEAR and oid != bear
        )
        sba.run(game.state)
        assert attach(game.state, aura, other)
        sba.run(game.state)
        assert controller(game, bear) == 1
        assert controller(game, other) == 0

    def test_an_unattached_aura_lets_go(self, builder):
        """Unattached and not yet binned -- the static applies to nothing."""
        game, aura, bear = enchanted(builder)
        sba.run(game.state)
        game.state.objects[aura].attached_to = None
        assert reconcile_static_control(game.state) is True
        assert controller(game, bear) == 1

    def test_losing_the_ability_lets_go_until_it_comes_back(self, builder):
        game, aura, bear = enchanted(builder)
        sba.run(game.state)
        lose_all_abilities_timed(game.state, aura, cutoff=game.state.alloc_timestamp())
        sba.run(game.state)
        assert controller(game, bear) == 1
        clear_until_eot(game.state)
        sba.run(game.state)
        assert controller(game, bear) == 0, "the static is back, and so is the hold"

    def test_the_auras_controller_changing_takes_the_creature_along(self, builder):
        """"You" is whoever controls the Aura now."""
        game, aura, bear = enchanted(builder)
        sba.run(game.state)
        change_control(game.state, aura, 2)
        sba.run(game.state)
        assert controller(game, bear) == 2
        destroy(game.state, aura)
        sba.run(game.state)
        assert controller(game, bear) == 1, "home is still the seat it was taken from"


class TestTheMonarch:
    def test_the_monarch_takes_it(self, builder):
        game, _, bear = enchanted(builder, FEALTY)
        become_monarch(game.state, 2)
        sba.run(game.state)
        assert controller(game, bear) == 2

    def test_control_follows_the_crown(self, builder):
        game, _, bear = enchanted(builder, FEALTY)
        become_monarch(game.state, 0)
        sba.run(game.state)
        assert controller(game, bear) == 0
        become_monarch(game.state, 2)
        sba.run(game.state)
        assert controller(game, bear) == 2
        assert game.state.objects[bear].summoning_sick(game.state.turn)
        [entry] = holds(game, bear)
        assert entry.previous_controller == 1, "home is the seat it was first taken from"

    def test_with_no_monarch_nobody_takes_it(self, builder):
        game, _, bear = enchanted(builder, FEALTY)
        assert game.state.monarch is None
        sba.run(game.state)
        assert controller(game, bear) == 1

    def test_the_crown_arriving_later_takes_it(self, builder):
        game, _, bear = enchanted(builder, FEALTY)
        sba.run(game.state)
        become_monarch(game.state, 0)
        sba.run(game.state)
        assert controller(game, bear) == 0

    def test_the_monarch_already_controlling_it_changes_nothing(self, builder):
        game, _, bear = enchanted(builder, FEALTY)
        become_monarch(game.state, 1)
        before = len(game.state.events)
        sba.run(game.state)
        assert controller(game, bear) == 1
        assert EventType.CONTROL_CHANGED not in event_types(list(game.state.events)[before:])

    def test_leaving_the_aura_after_the_crown_moved_goes_home(self, builder):
        game, aura, bear = enchanted(builder, FEALTY)
        become_monarch(game.state, 0)
        sba.run(game.state)
        become_monarch(game.state, 2)
        sba.run(game.state)
        destroy(game.state, aura)
        sba.run(game.state)
        assert controller(game, bear) == 1


class TestALaterEffectWins:
    def test_a_later_permanent_steal_outlives_the_aura(self, builder):
        """613.7: Mind Control after Control Magic holds the creature, and the
        Aura leaving does not hand it to anybody."""
        game, aura, bear = enchanted(builder)
        sba.run(game.state)
        change_control(game.state, bear, 2)
        sba.run(game.state)
        assert controller(game, bear) == 2, "the static does not take it back"
        destroy(game.state, aura)
        sba.run(game.state)
        assert controller(game, bear) == 2

    def test_an_until_end_of_turn_steal_then_the_static_resumes(self, builder):
        game, _, bear = enchanted(builder)
        sba.run(game.state)
        change_control(game.state, bear, 2, duration="until_end_of_turn")
        sba.run(game.state)
        assert controller(game, bear) == 2
        clear_until_eot(game.state)
        sba.run(game.state)
        assert controller(game, bear) == 0

    def test_the_crown_moving_under_a_steal_is_obeyed_when_it_ends(self, builder):
        game, _, bear = enchanted(builder, FEALTY, players=4)
        become_monarch(game.state, 0)
        sba.run(game.state)
        change_control(game.state, bear, 2, duration="until_end_of_turn")
        become_monarch(game.state, 3)
        sba.run(game.state)
        assert controller(game, bear) == 2, "the later steal still holds it"
        clear_until_eot(game.state)
        sba.run(game.state)
        assert controller(game, bear) == 3

    def test_an_aura_that_leaves_under_a_steal_sends_it_home_at_cleanup(self, builder):
        """The Act of Treason's handback skips the seat the Aura no longer holds it for."""
        game, aura, bear = enchanted(builder)
        sba.run(game.state)
        change_control(game.state, bear, 2, duration="until_end_of_turn")
        destroy(game.state, aura)
        sba.run(game.state)
        assert controller(game, bear) == 2
        clear_until_eot(game.state)
        sba.run(game.state)
        assert controller(game, bear) == 1

    def test_a_second_aura_wins_and_the_first_resumes_when_it_leaves(self, builder):
        """Two Control Magics: the later attachment is the later timestamp."""
        game = (
            builder(players=3)
            .battlefield(0, [MAGIC])
            .battlefield(1, [BEAR])
            .battlefield(2, [MAGIC])
            .build(advance=False)
        )
        first, second = only_oid(game, MAGIC, 0), only_oid(game, MAGIC, 2)
        bear = only_oid(game, BEAR, 1)
        assert attach(game.state, first, bear)
        reconcile_static_control(game.state)
        assert attach(game.state, second, bear)
        sba.run(game.state)
        assert controller(game, bear) == 2
        destroy(game.state, second)
        sba.run(game.state)
        assert controller(game, bear) == 0
        destroy(game.state, first)
        sba.run(game.state)
        assert controller(game, bear) == 1

    def test_the_first_aura_leaving_under_the_second_sends_it_home_later(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, [MAGIC])
            .battlefield(1, [BEAR])
            .battlefield(2, [MAGIC])
            .build(advance=False)
        )
        first, second = only_oid(game, MAGIC, 0), only_oid(game, MAGIC, 2)
        bear = only_oid(game, BEAR, 1)
        assert attach(game.state, first, bear)
        reconcile_static_control(game.state)
        assert attach(game.state, second, bear)
        sba.run(game.state)
        destroy(game.state, first)
        sba.run(game.state)
        assert controller(game, bear) == 2
        destroy(game.state, second)
        sba.run(game.state)
        assert controller(game, bear) == 1, "not to the seat whose Aura is gone"


class TestCombat:
    def test_taking_an_attacker_removes_it_from_combat(self, builder):
        """506.4: the Aura arriving mid-combat ends the Bear's attack."""
        game = (
            builder(players=2)
            .battlefield(0, [MAGIC, BEAR])
            .battlefield(1, [BEAR])
            .active(1)
            .build(advance=False)
        )
        bear = only_oid(game, BEAR, 1)
        # Parked on player 0's own Bear, where it changes nothing, so the SBA
        # that bins an unattached Aura leaves it alone until it moves.
        assert attach(game.state, only_oid(game, MAGIC, 0), only_oid(game, BEAR, 0))
        game._advance()
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=bear, targets=(TargetRef.player(0),))
        )
        assert game.state.combat.attacking(bear)
        assert attach(game.state, only_oid(game, MAGIC, 0), bear)
        sba.run(game.state)
        assert controller(game, bear) == 0
        assert not game.state.combat.attacking(bear)


class TestTheLoader:
    def _card(self, **static) -> CardModel:
        ability = {"kind": "static", "text": "You control enchanted creature.", "effect": "control"}
        ability |= static
        return CardModel.model_validate(
            {
                "id": "t_scm_probe",
                "name": "Test Control Probe",
                "mana_cost": "{2}{U}{U}",
                "types": ["Enchantment"],
                "subtypes": ["Aura"],
                "oracle_text": "Enchant creature\nYou control enchanted creature.",
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

    @pytest.mark.parametrize("seat", ["you", "monarch"])
    def test_both_seats_load(self, seat):
        compile_card(self._card(affects={"attached": True}, controller=seat))

    def test_a_missing_controller_is_refused(self):
        with pytest.raises(DslError, match="control needs a 'controller'"):
            compile_card(self._card(affects={"attached": True}))

    def test_an_unknown_controller_is_refused(self):
        with pytest.raises(DslError, match="control needs a 'controller'"):
            compile_card(self._card(affects={"attached": True}, controller="opponent"))

    @pytest.mark.parametrize(
        "affects",
        [None, {"types": ["Creature"], "controller": "opponent"}, {"attached": True, "types": ["Creature"]}],
        ids=["missing", "controller_filter", "extra_key"],
    )
    def test_anything_but_the_enchanted_permanent_is_refused(self, affects):
        """A filter reading control would stop matching what it took: an SBA loop."""
        static = {"controller": "you"}
        if affects is not None:
            static["affects"] = affects
        with pytest.raises(DslError, match="control takes 'affects'"):
            compile_card(self._card(**static))

    def test_a_condition_is_refused(self):
        with pytest.raises(DslError, match="control takes no 'condition'"):
            compile_card(
                self._card(
                    affects={"attached": True}, controller="you", condition={"is_your_turn": True}
                )
            )

    def test_controller_on_another_static_is_refused(self):
        with pytest.raises(DslError, match="'controller' only means anything on a control"):
            compile_card(
                self._card(
                    effect="goaded", affects={"attached": True}, controller="you"
                )
            )

    def test_it_cannot_be_granted(self):
        from commanderblitz.cards.loader.vocabulary import GRANTABLE_STATIC_EFFECTS

        assert "control" not in GRANTABLE_STATIC_EFFECTS
