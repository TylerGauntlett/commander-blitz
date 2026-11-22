"""A total shield with an additional effect -- prevent the damage, then do something.

    "If damage would be dealt to Khârn the Betrayer, prevent that damage and an
     opponent of your choice gains control of it."   -- Khârn the Betrayer

A `prevent_damage` total shield (``prevent_all``) carrying ``effects``. 615.5:
"Some prevention effects also include an additional effect … The prevention
takes place at the time the original event would have happened; the rest of
the effect takes place immediately afterward." So the damage is prevented
inside `primitives.damage_permanent`, exactly as Unbreathing Horde's and
Panther Habit's are, and the rider -- which here asks a question the primitive
cannot -- runs off the stack at the engine's next suspension point, the way the
`prevent_damage` ops' "prevented this way" riders already do. It is one more
named prevention hook, not a general replacement system (616).

**Why not the shield plus a `damage_prevented` trigger.** The control change
would go on the stack, where it could be responded to, and be a second ability
the card never printed. **Why not `gain_control` with ``player: "opponent"``.**
That resolves to every opponent, and at a pod the card says *an* opponent of
your choice: `choose_player` asks the static's controller *as the damage is
prevented* ("your" is whoever controls Khârn then), and `gain_control` reads
the answer.

Combat damage is one event (510.2), so two blockers are one control change.
Under "damage can't be prevented" the additional effect still happens (615.12)
and the damage lands. A shield that costs nothing applies first (616.1, the
order the controller picks).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import (
    damage_prevented_with_effects,
    prevents_all_damage,
)
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import SHIELD
from commanderblitz.engine.primitives import damage_permanent
from tests.conftest import only_oid

BETRAYER = "t_betrayer"
SIGIL = "t_sigil_betrayer"  # the same line, with "when you lose control … draw two"
OGRE = "t_pc_ogre"  # red 3/3, a damage source
BLANKET = "t_blanket_shield"  # prevent all damage to creatures you control
TORMENT = "t_no_prevention"  # damage can't be prevented


def position(builder, players=2, card=BETRAYER, mine=()):
    b = builder(players=players).battlefield(0, [card, *mine]).battlefield(1, [OGRE])
    for pid in range(players):
        b = b.library(pid, ["forest"] * 20)
    game = b.build(advance=False)
    return game, only_oid(game, card)


def settle(game, picks=()) -> list:
    """Run the engine until it is quiet, answering each CHOOSE_PLAYER with
    ``picks`` (seat ids, in order) and passing priority otherwise. Returns the
    questions asked."""
    queue, asked = list(picks), []
    game._advance()
    for _ in range(400):
        decision = game.pending()
        if decision is None:
            game._advance()
            if game.pending() is None:
                return asked
            continue
        if decision.kind is DecisionKind.CHOOSE_PLAYER:
            asked.append(decision)
            pick = queue.pop(0)
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if decision.options[a.choice].value == pick
                )
            )
            continue
        state = game.state
        if (
            decision.kind is DecisionKind.PRIORITY
            and not state.stack
            and not state.pending_triggers
            and not state.armed_delays
        ):
            return asked
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    raise AssertionError("the engine never settled")


def controller(game, oid: int) -> int:
    return game.state.objects[oid].controller


def events_since(game, mark: int, kind: str):
    return [e for e in game.state.events[mark:] if e.type == kind]


class TestPreventAndGiveAway:
    def test_the_damage_is_prevented_and_marks_nothing(self, builder):
        game, kharn = position(builder)
        mark = len(game.state.events)
        assert damage_permanent(game.state, kharn, 3, only_oid(game, OGRE)) == 0
        assert game.state.objects[kharn].damage == 0
        prevented = events_since(game, mark, "damage_prevented")
        assert [(e.data["amount"], e.data["reason"]) for e in prevented] == [
            (3, "prevent_with_effects")
        ]
        assert events_since(game, mark, "damage_dealt") == []

    def test_then_the_opponent_gains_control(self, builder):
        """Two players: one opponent, so nobody is asked."""
        game, kharn = position(builder)
        damage_permanent(game.state, kharn, 3, None)
        assert settle(game) == []
        assert controller(game, kharn) == 1

    def test_nothing_waits_on_the_stack(self, builder):
        """615.5: the rest of the effect is not a triggered ability."""
        game, kharn = position(builder)
        damage_permanent(game.state, kharn, 3, None)
        assert not game.state.stack
        assert not game.state.pending_triggers
        assert len(game.state.armed_delays) == 1

    def test_it_is_permanent(self, builder):
        game, kharn = position(builder)
        damage_permanent(game.state, kharn, 3, None)
        settle(game)
        game.state.turn += 1
        game.state.bump_chars()
        assert controller(game, kharn) == 1


class TestAnOpponentOfYourChoice:
    def test_at_a_pod_its_controller_chooses(self, builder):
        game, kharn = position(builder, players=4)
        damage_permanent(game.state, kharn, 3, None)
        asked = settle(game, picks=[2])
        assert [d.player for d in asked] == [0], "the controller chooses"
        assert [[o.value for o in d.options] for d in asked] == [[1, 2, 3]]
        assert controller(game, kharn) == 2

    def test_your_is_whoever_controls_it_then(self, builder):
        """Hit again under its new controller, it is *their* choice among
        *their* opponents -- its owner among them."""
        game, kharn = position(builder, players=4)
        damage_permanent(game.state, kharn, 3, None)
        settle(game, picks=[2])
        damage_permanent(game.state, kharn, 3, None)
        asked = settle(game, picks=[0])
        assert [d.player for d in asked] == [2]
        assert [[o.value for o in d.options] for d in asked] == [[0, 1, 3]]
        assert controller(game, kharn) == 0


class TestItIsOneEventPerEvent:
    def test_two_blows_in_one_combat_event_are_one_change(self, builder):
        game, kharn = position(builder)
        for _ in range(2):
            damage_permanent(game.state, kharn, 3, None, is_combat=True, batch=11)
        assert len(game.state.armed_delays) == 1
        damage_permanent(game.state, kharn, 3, None, is_combat=True, batch=12)
        assert len(game.state.armed_delays) == 2

    def test_each_separate_hit_is_another(self, builder):
        game, kharn = position(builder)
        for amount in (1, 2):
            damage_permanent(game.state, kharn, amount, None)
        assert len(game.state.armed_delays) == 2


class TestTheOrderIsTheControllers:
    def test_a_free_total_shield_applies_first(self, builder):
        game, kharn = position(builder, mine=(BLANKET,))
        mark = len(game.state.events)
        damage_permanent(game.state, kharn, 3, None)
        prevented = events_since(game, mark, "damage_prevented")
        assert [e.data["reason"] for e in prevented] == ["prevent_all"]
        assert not game.state.armed_delays

    def test_a_shield_counter_applies_first(self, builder):
        game, kharn = position(builder)
        game.state.objects[kharn].add_counter(SHIELD, 1)
        damage_permanent(game.state, kharn, 3, None)
        assert game.state.objects[kharn].counter(SHIELD) == 0
        assert not game.state.armed_delays

    def test_it_is_not_a_plain_total_shield(self, builder):
        """`prevents_all_damage` leaves it to its own hook, or the rider would
        never run."""
        game, kharn = position(builder)
        assert not prevents_all_damage(game.state, kharn)
        assert damage_prevented_with_effects(game.state, kharn) is not None

    def test_only_itself(self, builder):
        game, _kharn = position(builder)
        ogre = only_oid(game, OGRE)
        assert damage_prevented_with_effects(game.state, ogre) is None
        assert damage_permanent(game.state, ogre, 2, None) == 2


class TestDamageThatCantBePrevented:
    def test_the_damage_lands_and_the_control_change_still_happens(self, builder):
        """615.12: the prevention prevents nothing, but its additional effect
        still happens."""
        game, kharn = position(builder, mine=(TORMENT,))
        mark = len(game.state.events)
        assert damage_permanent(game.state, kharn, 3, None) == 3
        assert events_since(game, mark, "damage_prevented") == []
        assert events_since(game, mark, "damage_dealt") != []
        settle(game)
        assert controller(game, kharn) == 1


class TestWithTheSigil:
    def test_the_player_who_lost_it_draws_two(self, builder):
        """Khârn's two lines together: given away, its former controller draws."""
        game, kharn = position(builder, card=SIGIL)
        before = len(game.state.players[0].hand)
        damage_permanent(game.state, kharn, 3, None)
        settle(game)
        assert controller(game, kharn) == 1
        assert len(game.state.players[0].hand) == before + 2


def probe(**static) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "If damage would be dealt to Probe, prevent that damage and draw a card.",
        "mana_cost": "{R}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "static",
                "text": "If damage would be dealt to Probe, prevent that damage and draw a card.",
                "effect": "prevent_damage",
                "effects": [{"op": "draw", "amount": {"const": 1}}],
                **static,
            }
        ],
    }


class TestTheLoader:
    def test_the_shape_loads(self):
        compile_card(
            CardModel.model_validate(probe(prevent_all=True, affects={"self_only": True}))
        )

    @pytest.mark.parametrize(
        "static",
        [
            {"amount": 1, "affects": {"self_only": True}},
            {"prevent_all": True, "affects": {"self_only": True}, "counter": "+1/+1"},
        ],
    )
    def test_only_on_a_lone_total_shield(self, static):
        with pytest.raises(DslError, match="prevent_damage"):
            compile_card(CardModel.model_validate(probe(**static)))

    def test_a_bad_effect_is_refused(self):
        card = probe(prevent_all=True, affects={"self_only": True})
        card["abilities"][0]["effects"] = [{"op": "no_such_op"}]
        with pytest.raises(DslError, match="unknown effect op"):
            compile_card(CardModel.model_validate(card))

    def test_another_static_still_may_not_carry_effects(self):
        card = probe(affects={"self_only": True})
        card["abilities"][0]["effect"] = "attacks_if_able"
        with pytest.raises(DslError, match="cannot have 'effects'"):
            compile_card(CardModel.model_validate(card))
