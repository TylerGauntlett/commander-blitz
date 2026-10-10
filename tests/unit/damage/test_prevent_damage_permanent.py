""""Prevent all damage that would be dealt to him this turn" / "Until your next
turn, prevent all damage target permanent would deal" -- 615.1, a prevention
effect aimed at a **permanent**, with a clock, facing either way.

Gideon Jura is the witness for the first sentence ("0: Until end of turn, Gideon
Jura becomes a 6/6 … Prevent all damage that would be dealt to him this turn"),
Gideon of the Trials for the second ("+1: Until your next turn, prevent all
damage target permanent would deal"), and Kiora, the Crashing Wave prints both
at once ("…dealt to and dealt by target permanent an opponent controls").

The engine had two preventions and neither could say any of it. The
`prevent_damage` **op** is keyed to a seat -- a Fog -- and refuses `objects`.
The `prevent_damage` **static** is continuous while its source stands on the
battlefield, so printed on Gideon it would shield him on every turn rather than
the one he animated in; it cannot be installed by a resolving ability; and it
only ever stops damage dealt *to* what it matches. Nothing could stop damage a
permanent *deals*.

So `prevent_damage_permanent` installs a `structs.PermanentShield` on the
object, and the two damage primitives read it. What is pinned below, each a way
this could be silently wrong rather than broken:

1. The **direction**. ``to`` stops damage dealt to the permanent and nothing it
   deals; ``by`` stops damage it deals -- to permanents *and* players, combat and
   noncombat -- and nothing dealt to it; ``to_and_by`` is both.
2. Prevented damage was never dealt: no lifelink, no mark, no loyalty lost.
3. The clocks. ``this_turn`` ends at cleanup; ``until_your_next_turn`` survives
   the opponent's whole turn and ends in the installing player's untap step,
   and is dropped when that player leaves the game.
4. 400.7: a permanent that leaves and comes back is a new object and is no
   longer shielded.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_permanent, damage_player
from commanderblitz.engine.temp_effects import permanent_shielded, shield_permanent
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, only_oid, pass_until

BEAR = "t_bear"
SHIELD_TO = "t_shield_to"  # {W} instant: prevent all damage to target creature this turn
SHIELD_BY = "t_shield_by"  # {W} instant: until your next turn, prevent all damage it would deal


def position(builder, *, players=2, hand=(), active=0):
    """A bear each; ``active`` in their untap step, Plains for player 0's ``hand``."""
    b = builder(players=players).battlefield(0, [BEAR]).battlefield(1, [BEAR])
    if hand:
        b.hand(0, list(hand)).battlefield(0, ["plains"] * 2)
    for pid in range(players):
        b.library(pid, ["forest"] * 20)
    game = b.active(active).step(Step.UNTAP).build()
    return game, only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)


def cast(game, card_id: str, target: int, limit: int = 60) -> None:
    """Cast ``card_id`` from player 0's hand at ``target`` and let it resolve."""
    pass_until(game, lambda g: any(a.kind is ActionKind.CAST for a in g.legal_actions()))
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
        and a.targets
        and a.targets[0].id == target
    )
    game.apply(action)
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"{card_id} never resolved")


class TestTheDirection:
    def test_to_stops_damage_dealt_to_it(self, builder):
        game, mine, theirs = position(builder)
        shield_permanent(game.state, mine, "to", "this_turn", player=0)
        assert damage_permanent(game.state, mine, 3, theirs) == 0
        assert game.state.objects[mine].damage == 0

    def test_to_does_not_stop_damage_it_deals(self, builder):
        """The shielded creature still hits: Gideon animated and attacking deals
        his six."""
        game, mine, theirs = position(builder)
        shield_permanent(game.state, mine, "to", "this_turn", player=0)
        life = game.state.players[1].life
        damage_player(game.state, 1, 2, mine)
        assert game.state.players[1].life == life - 2
        assert damage_permanent(game.state, theirs, 1, mine) == 1

    def test_by_stops_damage_it_deals_to_a_permanent(self, builder):
        game, mine, theirs = position(builder)
        shield_permanent(game.state, theirs, "by", "until_your_next_turn", player=0)
        assert damage_permanent(game.state, mine, 2, theirs) == 0
        assert game.state.objects[mine].damage == 0

    def test_by_stops_damage_it_deals_to_a_player(self, builder):
        game, _mine, theirs = position(builder)
        shield_permanent(game.state, theirs, "by", "until_your_next_turn", player=0)
        life = game.state.players[0].life
        assert damage_player(game.state, 0, 2, theirs) == 0
        assert game.state.players[0].life == life

    def test_by_does_not_stop_damage_dealt_to_it(self, builder):
        """Gideon of the Trials pacifies the creature; he does not fog it."""
        game, mine, theirs = position(builder)
        shield_permanent(game.state, theirs, "by", "until_your_next_turn", player=0)
        assert damage_permanent(game.state, theirs, 2, mine) == 2

    def test_to_and_by_is_both(self, builder):
        """Kiora, the Crashing Wave's one clause."""
        game, mine, theirs = position(builder)
        shield_permanent(game.state, theirs, "to_and_by", "until_your_next_turn", player=0)
        assert damage_permanent(game.state, theirs, 2, mine) == 0
        assert damage_permanent(game.state, mine, 2, theirs) == 0
        assert damage_player(game.state, 0, 2, theirs) == 0

    def test_only_the_named_permanent(self, builder):
        game, mine, theirs = position(builder)
        shield_permanent(game.state, mine, "to_and_by", "this_turn", player=0)
        assert not permanent_shielded(game.state, theirs, by=False)
        assert not permanent_shielded(game.state, theirs, by=True)
        assert damage_permanent(game.state, theirs, 1, None) == 1


class TestPreventedDamageWasNeverDealt:
    def test_a_prevention_event_fires_and_no_damage_event_does(self, builder):
        game, _mine, theirs = position(builder)
        shield_permanent(game.state, theirs, "by", "this_turn", player=0)
        mark = len(game.state.events)
        damage_player(game.state, 0, 3, theirs)
        kinds = [e.type for e in game.state.events[mark:]]
        assert "damage_prevented" in kinds
        assert "damage_dealt" not in kinds

    def test_combat_damage_from_a_pacified_attacker_is_prevented(self, builder):
        """The combat path reaches the same primitive: an attacker Gideon of the
        Trials pointed at hits for nothing."""
        game, _mine, theirs = position(builder, active=1)
        shield_permanent(game.state, theirs, "by", "until_your_next_turn", player=0)
        life = game.state.players[0].life
        for _ in range(200):
            decision = game.pending()
            if decision is None or game.state.turn > 1:
                break
            if decision.kind is DecisionKind.DECLARE_ATTACKERS:
                adds = [a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER]
                if adds and game.state.combat is not None and not game.state.combat.attackers:
                    game.apply(adds[0])
                    continue
            game.apply(_default_answer(game, decision))
        assert game.state.players[0].life == life
        prevented = [
            e
            for e in game.state.events
            if e.type == "damage_prevented" and e.data.get("reason") == "permanent_shield"
        ]
        assert prevented, "the attack happened and its damage was prevented"


class TestTheClocks:
    def test_this_turn_ends_at_cleanup(self, builder):
        game, mine, _ = position(builder)
        shield_permanent(game.state, mine, "to", "this_turn", player=0)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.objects[mine].damage_shields == []

    def test_until_your_next_turn_survives_the_opponents_turn(self, builder):
        game, _, theirs = position(builder)
        shield_permanent(game.state, theirs, "by", "until_your_next_turn", player=0)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.active_player == 1
        assert permanent_shielded(game.state, theirs, by=True)

    def test_until_your_next_turn_ends_at_the_installing_players_untap(self, builder):
        game, _, theirs = position(builder)
        shield_permanent(game.state, theirs, "by", "until_your_next_turn", player=0)
        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.active_player == 0
        assert not permanent_shielded(game.state, theirs, by=True)

    def test_the_two_clocks_do_not_clear_each_other(self, builder):
        game, mine, _ = position(builder)
        shield_permanent(game.state, mine, "to", "this_turn", player=0)
        shield_permanent(game.state, mine, "by", "until_your_next_turn", player=0)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert [s.dealt for s in game.state.objects[mine].damage_shields] == ["by"]

    def test_an_eliminated_players_shields_are_dropped(self, builder):
        game, _, theirs = position(builder, players=3)
        shield_permanent(game.state, theirs, "by", "until_your_next_turn", player=2)
        game.state.players[2].life = 0
        sba.run(game.state)
        assert not permanent_shielded(game.state, theirs, by=True)


class TestANewObjectIsUnshielded:
    def test_leaving_the_battlefield_ends_it(self, builder):
        """400.7: blink the shielded creature and what comes back is a new object."""
        game, mine, theirs = position(builder)
        shield_permanent(game.state, mine, "to", "this_turn", player=0)
        move_object(game.state, mine, Zone.EXILE)
        move_object(game.state, mine, Zone.BATTLEFIELD)
        assert damage_permanent(game.state, mine, 1, theirs) == 1

    def test_a_permanent_off_the_battlefield_is_refused(self, builder):
        game, mine, _ = position(builder)
        move_object(game.state, mine, Zone.GRAVEYARD)
        assert not shield_permanent(game.state, mine, "to", "this_turn", player=0)

    def test_until_your_next_turn_needs_a_clock(self, builder):
        game, mine, _ = position(builder)
        assert not shield_permanent(game.state, mine, "by", "until_your_next_turn")

    def test_the_same_shield_is_recorded_once(self, builder):
        game, mine, _ = position(builder)
        assert shield_permanent(game.state, mine, "to", "this_turn", player=0)
        assert not shield_permanent(game.state, mine, "to", "this_turn", player=0)


class TestTheOp:
    def test_the_spell_shields_its_target_this_turn(self, builder):
        game, mine, _theirs = position(builder, hand=(SHIELD_TO,))
        cast(game, SHIELD_TO, mine)
        assert permanent_shielded(game.state, mine, by=False)
        assert [s.duration for s in game.state.objects[mine].damage_shields] == ["this_turn"]

    def test_the_spell_pacifies_its_target_until_your_next_turn(self, builder):
        game, _mine, theirs = position(builder, hand=(SHIELD_BY,))
        cast(game, SHIELD_BY, theirs)
        (shield,) = game.state.objects[theirs].damage_shields
        assert (shield.dealt, shield.duration, shield.player) == (
            "by",
            "until_your_next_turn",
            0,
        )


def _card(effect: dict) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Probe.",
        "mana_cost": "{W}",
        "types": ["Instant"],
        "spell_effects": [effect],
    }


class TestTheLoaderRefusesAGuess:
    base = {
        "op": "prevent_damage_permanent",
        "objects": {"self_only": True},
        "dealt": "to",
        "duration": "this_turn",
    }

    def test_the_whole_sentence_loads(self):
        compile_card(CardModel.model_validate(_card(dict(self.base))))

    @pytest.mark.parametrize("missing", ["objects", "dealt", "duration"])
    def test_each_key_is_required(self, missing):
        effect = {k: v for k, v in self.base.items() if k != missing}
        with pytest.raises(DslError, match="prevent_damage_permanent"):
            compile_card(CardModel.model_validate(_card(effect)))

    def test_an_amount_is_refused(self):
        with pytest.raises(DslError, match="takes no 'amount'"):
            compile_card(CardModel.model_validate(_card({**self.base, "amount": 3})))

    def test_an_unknown_duration_is_refused(self):
        with pytest.raises(DslError, match="needs a 'duration'"):
            compile_card(
                CardModel.model_validate(_card({**self.base, "duration": "this_combat"}))
            )

    def test_the_player_op_now_points_here(self):
        with pytest.raises(DslError, match="prevent_damage_permanent"):
            compile_card(
                CardModel.model_validate(
                    _card(
                        {
                            "op": "prevent_damage",
                            "duration": "this_turn",
                            "objects": {"self_only": True},
                        }
                    )
                )
            )
