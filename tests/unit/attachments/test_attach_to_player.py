"""Moving an Aura that is already on the battlefield onto a **player**.

    Archnemesis — "Enchant opponent / Whenever you attack enchanted player,
    that player loses 2 life. You draw a card and gain 2 life. / Whenever a
    player attacks you, you may attach this Aura to that player."

Rule 701.3 is the rule: an effect may attach an Aura to a player (303.4) as
long as the enchant ability allows that player. 303.4a/b make "Enchant
opponent" a restriction relative to the Aura's controller, so the controller is
never a legal host; 701.3b says that an effect trying to attach an Aura to a
host it can't enchant does nothing and the Aura **does not move**, and that
attaching it to the player it is already on does nothing either. Without the
clause check "that player" would be trusted, and an Aura could land on its own
controller and drain them every time they attacked.

`attach` with ``player`` is the spelling. The enchant clause is read off the
Aura's own first target, the same spec `stack._attach_aura` reads on the cast
path, so the cast and the move cannot disagree about who is a legal host.
Attaching is not targeting: hexproof does not stop it (protection does, in
`primitives.attach_to_player`).

The trigger half is ``defending: "enchanted_player"``: the seat the Aura is on,
attacked as a player (506.2) -- an attack at that player's planeswalker alone
is not attacking them.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import attach_to_player
from tests.conftest import _default_answer, oids_of, only_oid

ARCH = "t_archnemesis"
ROBE = "t_robe_mover"  # "Enchant player": every seat is a legal host
BEAR = "t_bear"
WALKER = "t_walker"
HEXPROOF = "t_ph_reformer"  # "You have hexproof."
SWAMP = "swamp"

FACE = "face"
PW = "walker"


def position(builder, *, active: int, aura=ARCH, on: int = 1, boards=None):
    """Three seats; player 0 controls ``aura``, attached to player ``on``.

    Three, because "that player" and "enchanted player" each have a wrong seat
    to name that a two-player game cannot show.
    """
    b = builder(players=3)
    b.battlefield(0, [aura])
    for pid, cards in (boards or {}).items():
        b.battlefield(pid, list(cards))
    for pid in range(3):
        b.library(pid, [SWAMP] * 20)
    game = b.active(active).step(Step.UNTAP).max_turns(2).build(advance=False)
    attach_to_player(game.state, only_oid(game, aura, 0), on)
    game._advance()
    return game


def attack(game, plan: list[tuple[int, str]], *, may: ActionKind = ActionKind.NO) -> list:
    """The active player sends one bear per ``(seat, FACE | PW)``; triggers resolve.

    Returns the MAY decisions seen, answered with ``may``.
    """
    attacker = game.state.active_player
    for _ in range(80):
        decision = game.pending()
        if decision is not None and decision.kind is DecisionKind.DECLARE_ATTACKERS:
            break
        game.apply(_default_answer(game, decision))
    else:
        raise AssertionError("never reached declare attackers")
    bears = list(oids_of(game, BEAR, attacker))
    for seat, at in plan:
        oid = bears.pop(0)
        want = ("player", seat) if at == FACE else ("object", only_oid(game, WALKER, seat))
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and any((t.kind, t.id) == want for t in a.targets)
            )
        )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    asked = []
    for _ in range(80):
        decision = game.pending()
        # Stop before blockers and combat damage, so a life total read
        # afterwards says what the triggers did and nothing else.
        if decision is None or game.state.step is not Step.DECLARE_ATTACKERS:
            break
        if (
            not game.state.stack
            and not game.state.pending_triggers
            and decision.kind is DecisionKind.PRIORITY
        ):
            break
        if decision.kind is DecisionKind.MAY:
            asked.append(decision)
            game.apply(next(a for a in game.legal_actions() if a.kind is may))
            continue
        game.apply(_default_answer(game, decision))
    return asked


def host(game, card=ARCH) -> int | None:
    return game.state.objects[only_oid(game, card, 0)].attached_to_player


def attached_events(game) -> int:
    return sum(1 for e in game.state.events if e.type == EventType.ATTACHED)


class TestAPlayerAttacksYou:
    def test_yes_moves_the_aura_onto_the_attacker(self, builder):
        game = position(builder, active=2, boards={2: [BEAR]})
        asked = attack(game, [(0, FACE)], may=ActionKind.YES)
        assert len(asked) == 1
        assert host(game) == 2
        assert game.state.objects[only_oid(game, ARCH, 0)].attached_to is None

    def test_no_leaves_it_where_it_was(self, builder):
        game = position(builder, active=2, boards={2: [BEAR]})
        attack(game, [(0, FACE)], may=ActionKind.NO)
        assert host(game) == 1

    def test_the_player_it_is_already_on_changes_nothing(self, builder):
        """701.3b: the effect does nothing, so no ATTACHED event for a trigger to read."""
        game = position(builder, active=1, boards={1: [BEAR]})
        before = attached_events(game)
        assert len(attack(game, [(0, FACE)], may=ActionKind.YES)) == 1
        assert host(game) == 1
        assert attached_events(game) == before

    def test_an_attack_on_your_planeswalker_alone_is_not_attacking_you(self, builder):
        game = position(builder, active=2, boards={0: [WALKER], 2: [BEAR]})
        asked = attack(game, [(0, PW)], may=ActionKind.YES)
        assert asked == []
        assert host(game) == 1

    def test_an_attack_on_somebody_else_does_not_trigger(self, builder):
        game = position(builder, active=2, boards={2: [BEAR]}, on=2)
        asked = attack(game, [(1, FACE)], may=ActionKind.YES)
        assert asked == []
        assert host(game) == 2

    def test_hexproof_does_not_stop_an_attach(self, builder):
        """Attaching is not targeting (701.3, 702.11)."""
        game = position(builder, active=2, boards={2: [BEAR, HEXPROOF]})
        attack(game, [(0, FACE)], may=ActionKind.YES)
        assert host(game) == 2


class TestTheEnchantClauseIsChecked:
    def run(self, game, card, who):
        ctx = EffectContext(state=game.state, controller=0, source_oid=only_oid(game, card, 0))
        list(execute(ctx, [{"op": "attach", "player": who}]))

    def test_enchant_opponent_never_lands_on_its_controller(self, builder):
        """303.4b and 701.3b: an illegal host, so the Aura stays where it is."""
        game = position(builder, active=2)
        before = attached_events(game)
        self.run(game, ARCH, "you")
        assert host(game) == 1
        assert attached_events(game) == before

    def test_enchant_opponent_moves_to_another_opponent(self, builder):
        game = position(builder, active=2)
        self.run(game, ARCH, "active_player")
        assert host(game) == 2

    def test_enchant_player_may_land_on_its_controller(self, builder):
        """The counterfactual: the same move on an "Enchant player" Aura."""
        game = position(builder, active=2, aura=ROBE)
        self.run(game, ROBE, "you")
        assert host(game, ROBE) == 0

    def test_a_seat_that_has_lost_is_not_a_host(self, builder):
        game = position(builder, active=2)
        game.state.players[2].has_lost = True
        self.run(game, ARCH, "active_player")
        assert host(game) == 1


class TestYouAttackEnchantedPlayer:
    def life(self, game, pid):
        return game.state.players[pid].life

    def test_the_whole_sentence(self, builder):
        game = position(builder, active=0, boards={0: [BEAR]})
        hand = len(game.state.players[0].hand)
        p0, p1 = self.life(game, 0), self.life(game, 1)
        attack(game, [(1, FACE)])
        assert self.life(game, 1) == p1 - 2
        assert self.life(game, 0) == p0 + 2
        assert len(game.state.players[0].hand) == hand + 1

    def test_attacking_another_opponent_does_nothing(self, builder):
        game = position(builder, active=0, boards={0: [BEAR]})
        p0, p2 = self.life(game, 0), self.life(game, 2)
        attack(game, [(2, FACE)])
        assert (self.life(game, 0), self.life(game, 2)) == (p0, p2)

    def test_attacking_only_their_planeswalker_is_not_attacking_them(self, builder):
        game = position(builder, active=0, boards={0: [BEAR], 1: [WALKER]})
        p0, p1 = self.life(game, 0), self.life(game, 1)
        attack(game, [(1, PW)])
        assert (self.life(game, 0), self.life(game, 1)) == (p0, p1)

    def test_once_per_combat_however_many_attack(self, builder):
        game = position(builder, active=0, boards={0: [BEAR, BEAR], 1: [WALKER]})
        p1 = self.life(game, 1)
        attack(game, [(1, FACE), (1, PW)])
        assert self.life(game, 1) == p1 - 2


def _card(**over):
    body = {
        "id": "x",
        "name": "X",
        "mana_cost": "{1}",
        "types": ["Enchantment"],
        "subtypes": ["Aura"],
        "targets": [
            {"id": "t1", "kind": "player", "selector": {"controller": "opponent"}, "count": 1}
        ],
        "abilities": [
            {
                "kind": "triggered",
                "text": "",
                "trigger": {"event": "creatures_attack_player", "controller": "any",
                            "defending": "you"},
                "effects": [{"op": "attach", "player": {"binding": "event_player"}}],
            }
        ],
    }
    body.update(over)
    return compile_card(CardModel.model_validate(body))


class TestTheLoaderRefusesTheNearMisses:
    def test_the_aura_form_loads(self):
        assert _card() is not None

    def test_not_an_aura_is_refused(self):
        with pytest.raises(DslError, match="Aura"):
            _card(subtypes=[])

    def test_an_aura_that_enchants_a_permanent_is_refused(self):
        with pytest.raises(DslError, match="kind 'player'"):
            _card(targets=[{"id": "t1", "kind": "permanent", "count": 1,
                            "selector": {"zone": "battlefield", "types": ["Creature"]}}])

    @pytest.mark.parametrize("who", ["opponent", "each_opponent", "each_player"])
    def test_a_spec_naming_several_seats_is_refused(self, who):
        ability = {
            "kind": "triggered",
            "text": "",
            "trigger": {"event": "self_enters", "source": "self"},
            "effects": [{"op": "attach", "player": who}],
        }
        with pytest.raises(DslError, match="one player"):
            _card(abilities=[ability])

    @pytest.mark.parametrize("key", ["objects", "attachment"])
    def test_a_second_host_or_mover_is_refused(self, key):
        ability = {
            "kind": "triggered",
            "text": "",
            "trigger": {"event": "self_enters", "source": "self"},
            "effects": [{"op": "attach", "player": "active_player", key: {"zone": "battlefield"}}],
        }
        with pytest.raises(DslError, match=f"no '{key}'"):
            _card(abilities=[ability])

    def test_defending_enchanted_player_off_an_aura_is_refused(self):
        ability = {
            "kind": "triggered",
            "text": "",
            "trigger": {"event": "creatures_attack_player", "controller": "you",
                        "defending": "enchanted_player"},
            "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
        }
        with pytest.raises(DslError, match="enchanted_player"):
            _card(subtypes=[], targets=[], abilities=[ability])
