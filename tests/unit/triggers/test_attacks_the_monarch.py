"""`defending: "monarch"` -- "whenever equipped creature attacks **the monarch**".

    "Whenever equipped creature attacks the monarch, destroy target tapped
    nonland permanent that player controls."      -- The Spear of Bashenga

The monarch is a player (721), and attacking a planeswalker or battle that
player controls attacks the permanent, not the player (506.2). The near miss is
an `attacks` trigger with `condition: {"is_monarch": {"binding": "defender"}}`
and `recheck: false` (M'Baku, Jabari Chieftain's spelling), and it fails on
that second point: the `attacks` event names a planeswalker's or battle's
*controller* as `defender`, so the Spear would destroy a permanent whenever the
equipped creature swung at the monarch's planeswalker -- a different card.

So the clause sits beside dethrone's `most_life` in `_defender_matches`: the
attack was at a player (no `attacked_permanent`) and that player is
`GameState.monarch`, asked as the creature attacks. The sentence has no "if"
(603.4), so the crown moving before the ability resolves does not undo it.
"That player" is the event's `defender`, read by the target selector as
`controller: {"binding": "defender"}`.

The rules points, each with a test:

- attacking the monarch triggers, and the target is the monarch's tapped
  nonland permanent, not another player's;
- attacking a player who is not the monarch, or attacking while nobody is,
  does not;
- attacking the monarch's planeswalker does not;
- only the equipped creature's attack counts;
- the crown changing hands before resolution keeps the trigger;
- the loader refuses `monarch` on an event that cannot tell a player attack
  from a planeswalker attack.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach, become_monarch
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, oids_of, only_oid, pass_until, settle

SPEAR = "t_spear"  # the Spear's attack trigger, nothing else
BEAR = "t_bear"  # 2/2, no abilities
WALKER = "t_walker"  # loyalty 4
BOLT = "t_bolt"  # {R} instant, so priority stops while the trigger is on the stack


def position(builder, *, monarch=1, mine=(BEAR, BEAR), theirs=None, untapped=None):
    """Player 0 with an equipped bear (and an unequipped one), three seats.

    ``theirs`` are tapped permanents per seat, ``untapped`` untapped ones.
    Returns ``(game, equipped, unequipped)``.
    """
    b = (
        builder(players=3)
        .battlefield(0, ["mountain", SPEAR, *mine])
        .hand(0, [BOLT])
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid, cards in (theirs or {}).items():
        b.battlefield(pid, cards, tapped=True)
    for pid, cards in (untapped or {}).items():
        b.battlefield(pid, cards)
    game = b.build()
    bears = oids_of(game, BEAR, 0)
    attach(game.state, only_oid(game, SPEAR, 0), bears[0])
    if monarch is not None:
        become_monarch(game.state, monarch)
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    return game, bears[0], bears[1] if len(bears) > 1 else None


def declare(game, attacks: dict[int, TargetRef]) -> None:
    for oid, ref in attacks.items():
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(ref,)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def at(pid: int) -> TargetRef:
    return TargetRef.player(pid)


def alive(game, oid: int) -> bool:
    return oid in game.state.battlefield


class TestAttackingTheMonarch:
    def test_destroys_a_tapped_nonland_permanent_the_monarch_controls(self, builder):
        game, spear_bear, _ = position(builder, theirs={1: [BEAR, "mountain"], 2: [BEAR]})
        theirs, land = only_oid(game, BEAR, 1), only_oid(game, "mountain", 1)
        bystander = only_oid(game, BEAR, 2)
        declare(game, {spear_bear: at(1)})
        assert game.state.stack, "the trigger is waiting to resolve"
        settle(game)
        assert not alive(game, theirs)
        assert alive(game, land), "nonland"
        assert alive(game, bystander), "'that player controls'"

    def test_an_untapped_permanent_is_not_a_legal_target(self, builder):
        game, spear_bear, _ = position(builder, untapped={1: [BEAR]})
        theirs = only_oid(game, BEAR, 1)
        declare(game, {spear_bear: at(1)})
        settle(game)
        assert alive(game, theirs)

    def test_the_crown_moving_before_resolution_keeps_the_trigger(self, builder):
        """No intervening-if: asked as the creature attacks, never again."""
        game, spear_bear, _ = position(builder, theirs={1: [BEAR]})
        theirs = only_oid(game, BEAR, 1)
        declare(game, {spear_bear: at(1)})
        assert game.state.stack
        become_monarch(game.state, 2)
        settle(game)
        assert not alive(game, theirs)


class TestNotTheMonarch:
    def test_attacking_another_player_does_not_trigger(self, builder):
        game, spear_bear, _ = position(builder, theirs={1: [BEAR], 2: [BEAR]})
        declare(game, {spear_bear: at(2)})
        assert not game.state.stack
        settle(game)
        assert alive(game, only_oid(game, BEAR, 2))

    def test_with_no_monarch_nothing_triggers(self, builder):
        game, spear_bear, _ = position(builder, monarch=None, theirs={1: [BEAR]})
        declare(game, {spear_bear: at(1)})
        assert not game.state.stack
        settle(game)
        assert alive(game, only_oid(game, BEAR, 1))

    def test_attacking_the_monarchs_planeswalker_does_not_trigger(self, builder):
        """506.2: an attack on a planeswalker attacks the walker, not its controller."""
        game, spear_bear, _ = position(builder, theirs={1: [BEAR]}, untapped={1: [WALKER]})
        declare(game, {spear_bear: TargetRef.obj(only_oid(game, WALKER, 1))})
        assert not game.state.stack
        settle(game)
        assert alive(game, only_oid(game, BEAR, 1))

    def test_only_the_equipped_creature_counts(self, builder):
        game, _, plain_bear = position(builder, theirs={1: [BEAR]})
        declare(game, {plain_bear: at(1)})
        assert not game.state.stack
        settle(game)
        assert alive(game, only_oid(game, BEAR, 1))


def _trigger(**trigger) -> dict:
    return {
        "id": "t_monarch_probe",
        "name": "Monarch Probe",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "triggered",
                "trigger": trigger,
                "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            }
        ],
    }


class TestTheLoaderGuard:
    def test_monarch_loads_on_attacks(self):
        compile_card(CardModel.model_validate(_trigger(event="attacks", source="self", defending="monarch")))

    @pytest.mark.parametrize("event", ["creatures_attack_player", "deals_damage_to_player"])
    def test_monarch_is_refused_where_the_event_cannot_tell_a_player_from_a_walker(self, event):
        with pytest.raises(DslError, match="monarch"):
            compile_card(CardModel.model_validate(_trigger(event=event, defending="monarch")))
