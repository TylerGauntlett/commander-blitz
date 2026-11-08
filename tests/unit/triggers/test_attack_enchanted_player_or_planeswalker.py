"""Attacking an enchanted player **or a planeswalker they control**.

    Tenuous Truce -- "Enchant opponent / At the beginning of enchanted
    opponent's end step, you and that player each draw a card. / When you
    attack enchanted opponent or a planeswalker they control or when they
    attack you or a planeswalker you control, sacrifice this Aura."

Rule 506.2 gives an attacking creature three things to attack: a player, a
planeswalker, or a battle. "Enchanted opponent or a planeswalker they control"
names two of them, both behind the one seat the Aura is attached to (303.4).
``defending: "enchanted_player"`` (Archnemesis) is the narrower sentence -- the
player attacked as a player -- so without
``"enchanted_player_or_planeswalker"`` the truce survives an attack on the
enchanted opponent's planeswalker, and with ``defending: "opponent"`` it breaks
when you attack somebody else entirely.

The second half, "when **they** attack you or a planeswalker you control", needs
no new word: ``defending: "you"`` already folds your planeswalkers into you on
``creatures_attack_player``, and "they" is ``is_active_player:
"enchanted_player"``, because only the active player declares attackers (508.1),
asked with ``recheck: false`` since the sentence has no "if".
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach_to_player
from tests.conftest import _default_answer, count_on_battlefield, oids_of, only_oid

TRUCE = "t_tenuous_truce"
LOOKOUT = "t_truce_lookout"  # the per-creature `attacks` form, +1 life each
BEAR = "t_bear"
WALKER = "t_walker"
BATTLE = "t_battle_wall"
SWAMP = "swamp"

FACE = "face"


def position(builder, *, active: int, aura: str = TRUCE, boards=None):
    """Three seats; player 0 controls ``aura``, attached to player 1.

    Three, because "enchanted opponent" and "they" each have a wrong seat a
    two-player game cannot show: player 2.
    """
    b = builder(players=3)
    b.battlefield(0, [aura])
    for pid, cards in (boards or {}).items():
        b.battlefield(pid, list(cards))
    for pid in range(3):
        b.library(pid, [SWAMP] * 20)
    game = b.active(active).step(Step.UNTAP).max_turns(2).build(advance=False)
    attach_to_player(game.state, only_oid(game, aura, 0), 1)
    game._advance()
    return game


def attack(game, plan: list[tuple[int, str]]) -> None:
    """The active player sends one bear per ``(seat, FACE | card id)``; triggers resolve."""
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
        want = ("player", seat) if at == FACE else ("object", only_oid(game, at, seat))
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
    for _ in range(80):
        decision = game.pending()
        if decision is None or game.state.step is not Step.DECLARE_ATTACKERS:
            break
        if (
            not game.state.stack
            and not game.state.pending_triggers
            and decision.kind is DecisionKind.PRIORITY
        ):
            break
        game.apply(_default_answer(game, decision))


def broken(game) -> bool:
    """The truce left the battlefield -- sacrificed, so into its owner's graveyard."""
    return count_on_battlefield(game, TRUCE, 0) == 0 and any(
        game.state.objects[oid].def_id == TRUCE for oid in game.state.players[0].graveyard
    )


class TestYouAttackEnchantedOpponent:
    def test_attacking_the_enchanted_player_breaks_it(self, builder):
        game = position(builder, active=0, boards={0: [BEAR]})
        attack(game, [(1, FACE)])
        assert broken(game)

    def test_attacking_their_planeswalker_alone_breaks_it(self, builder):
        """The half `defending: "enchanted_player"` refuses."""
        game = position(builder, active=0, boards={0: [BEAR], 1: [WALKER]})
        attack(game, [(1, WALKER)])
        assert broken(game)

    def test_attacking_their_battle_alone_does_not(self, builder):
        """A battle is the third thing 506.2 names, and the sentence leaves it out."""
        game = position(builder, active=0, boards={0: [BEAR], 1: [BATTLE]})
        attack(game, [(1, BATTLE)])
        assert not broken(game)

    def test_attacking_a_different_opponent_does_not(self, builder):
        game = position(builder, active=0, boards={0: [BEAR], 2: [WALKER]})
        attack(game, [(2, FACE)])
        assert not broken(game)

    def test_a_different_opponents_planeswalker_does_not(self, builder):
        game = position(builder, active=0, boards={0: [BEAR], 2: [WALKER]})
        attack(game, [(2, WALKER)])
        assert not broken(game)


class TestTheyAttackYou:
    def test_the_enchanted_player_attacking_you_breaks_it(self, builder):
        game = position(builder, active=1, boards={1: [BEAR]})
        attack(game, [(0, FACE)])
        assert broken(game)

    def test_the_enchanted_player_attacking_your_planeswalker_breaks_it(self, builder):
        game = position(builder, active=1, boards={0: [WALKER], 1: [BEAR]})
        attack(game, [(0, WALKER)])
        assert broken(game)

    def test_the_enchanted_player_attacking_someone_else_does_not(self, builder):
        game = position(builder, active=1, boards={1: [BEAR], 2: [WALKER]})
        attack(game, [(2, FACE)])
        assert not broken(game)

    def test_a_third_player_attacking_you_does_not(self, builder):
        game = position(builder, active=2, boards={0: [WALKER], 2: [BEAR, BEAR]})
        attack(game, [(0, FACE), (0, WALKER)])
        assert not broken(game)


class TestThePerCreatureForm:
    """On `attacks` the value is asked of each creature, so each one counts."""

    def test_the_player_and_their_planeswalker_each_count(self, builder):
        game = position(
            builder, active=2, aura=LOOKOUT, boards={1: [WALKER, BATTLE], 2: [BEAR] * 4}
        )
        life = game.state.players[0].life
        attack(game, [(1, FACE), (1, WALKER), (1, BATTLE), (0, FACE)])
        assert game.state.players[0].life == life + 2


def _aura(trigger: dict, **over):
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
                "trigger": trigger,
                "effects": [{"op": "sacrifice", "objects": {"self_only": True}}],
            }
        ],
    }
    body.update(over)
    return compile_card(CardModel.model_validate(body))



ATTACK = {"event": "creatures_attack_player", "defending": "enchanted_player_or_planeswalker"}


class TestTheLoaderRefusesTheNearMisses:
    @pytest.mark.parametrize("event", ["creatures_attack_player", "attacks"])
    def test_the_attack_events_load(self, event):
        assert _aura({**ATTACK, "event": event}) is not None

    def test_a_damage_event_is_refused(self):
        """A damage event's defender was dealt damage; nothing was attacked."""
        with pytest.raises(DslError, match="whom an attack is aimed at"):
            _aura({**ATTACK, "event": "deals_damage_to_player"})

    def test_off_an_aura_it_is_refused(self):
        """It reads `attached_to_player`, which only an Aura ever has."""
        with pytest.raises(DslError, match="enchanted_player"):
            _aura(ATTACK, subtypes=[], targets=[])
