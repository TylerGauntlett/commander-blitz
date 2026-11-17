""""Assign its combat damage as though it weren't blocked" (510.1c-d).

Rule 510.1c has a blocked creature assign its combat damage to the creatures
blocking it, and a blocked creature whose blockers have all left assigns none.
Thorn Elemental, Lone Wolf, Siege Behemoth and Indomitable Might let the
creature's controller instead assign all of it to the player, planeswalker or
battle it is attacking. Without this a blocked Thorn Elemental only ever kills
blockers: the near miss, trample, sends only the excess past lethal, and
`combat_damage_by_toughness` changes how much is assigned, never where.

So `combat.deal_combat_damage` asks the attacker's controller one `MAY`
question for each blocked attacker that
`player_statics.assigns_damage_as_though_unblocked` says has the option. Pinned
below: yes sends it all to the player and spares the blocker; no is the ordinary
assignment; nobody is asked about an unblocked creature or one without the
static; the Aura's version reaches only the creature it enchants and leaves with
it; a planeswalker under attack takes the damage; the option survives the
blockers leaving combat; and the CPU says yes.

The witnesses are Thorn Elemental (`t_dau_thorn`, its line on a 3/3) and
Indomitable Might (`t_dau_might`, its line alone).
"""

from __future__ import annotations

import pytest

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import assigns_damage_as_though_unblocked
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import destroy
from tests.conftest import _default_answer, attack_with, find_action, only_oid
from tests.unit.combat.test_combat import block_with, done, to_attackers, to_blockers

THORN = "t_dau_thorn"  # 3/3, may assign as though unblocked
MIGHT = "t_dau_might"  # Aura: enchanted creature may
BEAR = "t_bear"  # 2/2
WALKER = "t_walker"  # loyalty 4

PROMPT = "as though it weren't blocked"


def position(builder, mine=(), theirs=()):
    b = builder(players=2)
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    return b.active(0).step(Step.UNTAP).build()


def block(game, attacker, blocker, *, target=None):
    """Attack with ``attacker`` (at player 1, or at ``target``) and block it."""
    to_attackers(game)
    if target is None:
        attack_with(game, attacker, 1)
    else:
        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=attacker, targets=(target,))
        )
    done(game)
    to_blockers(game)
    block_with(game, blocker, attacker)
    done(game)


def finish(game, answer: bool | None = None) -> list:
    """Run combat damage, answering the question with ``answer``; return the
    questions asked."""
    asked = []
    start = game.state.turn
    for _ in range(80):
        if game.over or game.state.turn != start or int(game.state.step) > int(Step.COMBAT_DAMAGE):
            return asked
        decision = game.pending()
        if decision is None:
            return asked
        if decision.kind is DecisionKind.MAY and PROMPT in decision.prompt:
            asked.append(decision)
            want = ActionKind.YES if answer else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("combat did not resolve")


def dealt(game, source: int, oid: int) -> int:
    """Damage ``source`` dealt to the permanent ``oid`` this game."""
    return sum(
        e.data.get("amount", 0)
        for e in game.state.events
        if e.type == "damage_dealt" and e.source == source and e.data.get("oid") == oid
    )


class TestTheChoice:
    def test_yes_sends_it_all_to_the_player(self, builder):
        game = position(builder, mine=(THORN,), theirs=(BEAR,))
        bear = only_oid(game, BEAR, 1)
        block(game, only_oid(game, THORN, 0), bear)
        assert len(finish(game, True)) == 1
        assert game.state.players[1].life == 37
        assert bear in game.state.battlefield

    def test_no_is_the_ordinary_assignment(self, builder):
        game = position(builder, mine=(THORN,), theirs=(BEAR,))
        bear = only_oid(game, BEAR, 1)
        block(game, only_oid(game, THORN, 0), bear)
        assert len(finish(game, False)) == 1
        assert game.state.players[1].life == 40
        assert bear not in game.state.battlefield

    def test_the_blocker_still_deals_its_damage(self, builder):
        """Only the attacker's assignment changes; the Bear hits back for 2."""
        game = position(builder, mine=(THORN,), theirs=(BEAR,))
        thorn = only_oid(game, THORN, 0)
        bear = only_oid(game, BEAR, 1)
        block(game, thorn, bear)
        finish(game, True)
        assert dealt(game, bear, thorn) == 2

    def test_the_attackers_controller_is_asked(self, builder):
        game = position(builder, mine=(THORN,), theirs=(BEAR,))
        block(game, only_oid(game, THORN, 0), only_oid(game, BEAR, 1))
        (decision,) = finish(game, True)
        assert decision.player == 0


class TestWhoIsAsked:
    def test_not_an_unblocked_creature(self, builder):
        game = position(builder, mine=(THORN,))
        to_attackers(game)
        attack_with(game, only_oid(game, THORN, 0), 1)
        done(game)
        assert finish(game, False) == []
        assert game.state.players[1].life == 37

    def test_not_a_creature_without_the_static(self, builder):
        game = position(builder, mine=(BEAR,), theirs=(BEAR,))
        block(game, only_oid(game, BEAR, 0), only_oid(game, BEAR, 1))
        assert finish(game, True) == []
        assert game.state.players[1].life == 40

    def test_not_a_blocking_thorn(self, builder):
        """The option is the attacker's; a blocker has nothing to be unblocked from."""
        game = position(builder, mine=(BEAR,), theirs=(THORN,))
        bear = only_oid(game, BEAR, 0)
        block(game, bear, only_oid(game, THORN, 1))
        assert finish(game, True) == []
        assert bear not in game.state.battlefield


class TestTheAura:
    def board(self, builder):
        """``(game, aura, [two Bears of player 0])``, the Aura on the first.

        Attached before the game starts: an Aura attached to nothing is binned
        by the first state-based check (704.5m).
        """
        b = builder(players=2).battlefield(0, [MIGHT, BEAR, BEAR]).battlefield(1, [BEAR])
        aura, *mine = b.state.battlefield[:3]
        attach(b.state, aura, mine[0])
        return b.active(0).step(Step.UNTAP).build(), aura, mine

    def test_the_enchanted_creature_has_the_option(self, builder):
        game, _aura, mine = self.board(builder)
        assert assigns_damage_as_though_unblocked(game.state, mine[0])
        assert not assigns_damage_as_though_unblocked(game.state, mine[1])

    def test_the_enchanted_creature_hits_the_player(self, builder):
        game, _aura, mine = self.board(builder)
        block(game, mine[0], only_oid(game, BEAR, 1))
        assert len(finish(game, True)) == 1
        assert game.state.players[1].life == 38

    def test_it_follows_the_aura(self, builder):
        game, aura, mine = self.board(builder)
        attach(game.state, aura, mine[1])
        assert not assigns_damage_as_though_unblocked(game.state, mine[0])
        assert assigns_damage_as_though_unblocked(game.state, mine[1])

    def test_it_ends_when_the_aura_leaves(self, builder):
        game, aura, mine = self.board(builder)
        destroy(game.state, aura)
        assert not assigns_damage_as_though_unblocked(game.state, mine[0])


class TestWhereTheDamageGoes:
    def test_a_planeswalker_under_attack_takes_it(self, builder):
        game = position(builder, mine=(THORN,), theirs=(BEAR, WALKER))
        walker = only_oid(game, WALKER, 1)
        block(game, only_oid(game, THORN, 0), only_oid(game, BEAR, 1), target=TargetRef.obj(walker))
        finish(game, True)
        assert game.state.objects[walker].counters["loyalty"] == 1
        assert game.state.players[1].life == 40

    def test_the_option_survives_the_blockers_leaving(self, builder):
        """510.1c's "assigns no combat damage" is for an ordinary blocked
        creature; this one may still assign as though it weren't blocked."""
        game = position(builder, mine=(THORN,), theirs=(BEAR,))
        bear = only_oid(game, BEAR, 1)
        block(game, only_oid(game, THORN, 0), bear)
        destroy(game.state, bear)
        assert len(finish(game, True)) == 1
        assert game.state.players[1].life == 37

    def test_declined_with_no_blockers_left_it_deals_nothing(self, builder):
        game = position(builder, mine=(THORN,), theirs=(BEAR,))
        bear = only_oid(game, BEAR, 1)
        block(game, only_oid(game, THORN, 0), bear)
        destroy(game.state, bear)
        finish(game, False)
        assert game.state.players[1].life == 40


class TestTheCpu:
    def test_the_heuristic_agent_takes_the_option(self, builder):
        game = position(builder, mine=(THORN,), theirs=(BEAR,))
        block(game, only_oid(game, THORN, 0), only_oid(game, BEAR, 1))
        for _ in range(40):
            decision = game.pending()
            if decision.kind is DecisionKind.MAY and PROMPT in decision.prompt:
                break
            game.apply(_default_answer(game, decision))
        else:
            raise AssertionError("never asked")
        choice = HeuristicAgent(0).act(game, 0, game.legal_actions())
        assert choice.kind is ActionKind.YES


def _card(ability: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "X.",
            "mana_cost": "{G}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [ability],
        }
    )


class TestTheLoader:
    def test_the_static_needs_affects(self):
        with pytest.raises(DslError, match="assign_damage_as_though_unblocked needs an 'affects'"):
            compile_card(
                _card({"kind": "static", "text": "X.", "effect": "assign_damage_as_though_unblocked"})
            )

    def test_self_only_loads(self):
        compile_card(
            _card(
                {
                    "kind": "static",
                    "text": "X.",
                    "effect": "assign_damage_as_though_unblocked",
                    "affects": {"self_only": True},
                }
            )
        )
