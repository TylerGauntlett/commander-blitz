""""…attacking you **or a planeswalker you control**" -- the
`or_planeswalkers` selector key beside `attacking_player`.

    Soul Snare — "{W}, Sacrifice this enchantment: Exile target creature
    that's attacking you or a planeswalker you control."

    Roar of Resistance — "…creatures attacking your opponents and/or
    planeswalkers they control get +2/+0 until end of turn."

Rule 506.2 gives an attacking creature three kinds of thing to attack: a player,
a planeswalker, or a battle. `attacking_player` reads the first alone, which is
right for Trouble in Pairs and one creature too few for these cards: a creature
sent at your planeswalker is exactly what Soul Snare is printed to exile.
`attacking: true` is the other near miss and is wrong in a pod, where it also
takes a creature attacking somebody else.

`or_planeswalkers: true` widens the player to the player's planeswalkers and
stops there: a creature attacking a battle is still attacking nothing these
cards name. The walker is asked about as it is now -- still a planeswalker,
still on the battlefield, still under that player's control.

What is pinned below, and each is a way this could be silently wrong:

1. One at you and one at your planeswalker is **2** -- Soul Snare's card.
2. At a pod, attacks at another opponent or at *their* walker are not at you.
3. `opponent` takes every opponent's face and walker -- Roar's card -- and
   never the controller's own.
4. A battle is not a planeswalker, with or without the flag.
5. A walker that has left is no longer "a planeswalker you control".
6. The binding form and the trigger-filter half honour the flag too.
7. The loader refuses the flag alone and a non-boolean.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.triggers import matches_card_filter
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, oids_of, only_oid, settle

BEAR = "t_bear"
WALKER = "t_walker"
BATTLE = "t_battle_wall"

#: Where a bear is sent: a player's face, their planeswalker, or their battle.
FACE = "face"
PW = WALKER
SIEGE = BATTLE


def position(builder, *, bears: int, p1=(), p2=()):
    """Player 0 attacks; players 1 and 2 defend -- three seats, because "you"
    has a way to be wrong that two cannot show."""
    b = builder(players=3)
    b.battlefield(0, [BEAR] * bears)
    if p1:
        b.battlefield(1, list(p1))
    if p2:
        b.battlefield(2, list(p2))
    for pid in range(3):
        b.library(pid, ["swamp"] * 20)
    return b.active(0).step(Step.UNTAP).max_turns(2).build()


def declare(game, plan: list[tuple[int, str]]) -> list[int]:
    """Send player 0's bears, one per ``(seat, FACE | PW | SIEGE)``, and stop
    with the attack still live. Returns the bears in plan order."""
    for _ in range(80):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            break
        game.apply(_default_answer(game, decision))
    bears = list(oids_of(game, BEAR, 0))
    sent = []
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
        sent.append(oid)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    settle(game)
    assert game.state.combat is not None, "the attack has to still be live"
    return sent


def pool(game, controller: int, who, *, widen: bool = True) -> set[int]:
    ctx = EffectContext(state=game.state, controller=controller)
    selector = {"attacking_player": who}
    if widen:
        selector["or_planeswalkers"] = True
    return set(resolve_pool(ctx, selector))


class TestYouOrAPlaneswalkerYouControl:
    def test_face_and_walker_both_count(self, builder):
        """Soul Snare's card: both bears may be exiled, where `attacking_player`
        alone offers only the one at your face."""
        game = position(builder, bears=2, p1=(WALKER,))
        at_face, at_walker = declare(game, [(1, FACE), (1, PW)])

        assert pool(game, 1, "you") == {at_face, at_walker}
        assert pool(game, 1, "you", widen=False) == {at_face}

    def test_another_opponents_face_and_walker_are_not_yours(self, builder):
        game = position(builder, bears=3, p1=(WALKER,), p2=(WALKER,))
        mine, theirs, their_walker = declare(game, [(1, PW), (2, FACE), (2, PW)])

        assert pool(game, 1, "you") == {mine}
        assert pool(game, 2, "you") == {theirs, their_walker}


class TestOpponentsAndPlaneswalkersTheyControl:
    def test_every_opponent_face_and_walker(self, builder):
        """Roar of Resistance from the attacker's seat: all three bears are
        attacking an opponent or an opponent's walker."""
        game = position(builder, bears=3, p1=(WALKER,))
        sent = declare(game, [(1, FACE), (1, PW), (2, FACE)])

        assert pool(game, 0, "opponent") == set(sent)

    def test_never_the_controllers_own(self, builder):
        """From player 1's seat, the bears at player 1 and player 1's walker are
        attacking *you*, not an opponent."""
        game = position(builder, bears=3, p1=(WALKER,))
        _, _, at_two = declare(game, [(1, FACE), (1, PW), (2, FACE)])

        assert pool(game, 1, "opponent") == {at_two}


class TestNotABattle:
    @pytest.mark.parametrize("widen", [True, False])
    def test_a_creature_attacking_a_battle_attacks_nobody(self, builder, widen):
        game = position(builder, bears=2, p1=(BATTLE,))
        at_face, _ = declare(game, [(1, FACE), (1, SIEGE)])

        assert pool(game, 1, "you", widen=widen) == {at_face}
        assert pool(game, 0, "any", widen=widen) == {at_face}


class TestTheWalkerAsItIsNow:
    def test_a_walker_that_left_is_not_a_planeswalker_you_control(self, builder):
        game = position(builder, bears=2, p1=(WALKER,))
        at_face, at_walker = declare(game, [(1, FACE), (1, PW)])
        assert at_walker in pool(game, 1, "you")

        move_object(game.state, only_oid(game, WALKER, 1), Zone.GRAVEYARD)

        assert pool(game, 1, "you") == {at_face}


class TestEveryFormReadsIt:
    def test_the_binding_form(self, builder):
        """"…attacking **that player** or a planeswalker they control", with the
        seat in a binding."""
        game = position(builder, bears=2, p1=(WALKER,))
        sent = declare(game, [(1, FACE), (1, PW)])
        ctx = EffectContext(state=game.state, controller=0)
        ctx.bindings["defender"] = 1
        selector = {"attacking_player": {"binding": "defender"}}

        assert len(resolve_pool(ctx, selector)) == 1
        assert set(resolve_pool(ctx, selector | {"or_planeswalkers": True})) == set(sent)

    def test_the_trigger_filter_half(self, builder):
        game = position(builder, bears=2, p1=(WALKER,))
        at_face, at_walker = declare(game, [(1, FACE), (1, PW)])
        source = game.state.objects[only_oid(game, WALKER, 1)]
        filt = {"attacking_player": "you", "or_planeswalkers": True}

        assert matches_card_filter(game.state, at_face, filt, source)
        assert matches_card_filter(game.state, at_walker, filt, source)
        assert not matches_card_filter(
            game.state, at_walker, {"attacking_player": "you"}, source
        )


class TestTheLoader:
    def compile(self, target: dict):
        model = CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "mana_cost": "{W}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "activated",
                        "cost": {"mana": "{W}"},
                        "targets": [
                            {
                                "id": "t1",
                                "kind": "permanent",
                                "selector": {"types": ["Creature"], **target},
                            }
                        ],
                        "effects": [{"op": "exile", "target": "t1"}],
                    }
                ],
            }
        )
        return compile_card(model)

    def test_soul_snares_selector_loads(self):
        self.compile({"attacking_player": "you", "or_planeswalkers": True})

    def test_the_flag_alone_is_refused(self):
        """"Attacking a planeswalker" with no player is not the printed filter,
        and beside `attacking: true` the flag would change nothing."""
        with pytest.raises(DslError, match="or_planeswalkers"):
            self.compile({"attacking": True, "or_planeswalkers": True})

    def test_a_non_boolean_is_refused(self):
        with pytest.raises(DslError, match="or_planeswalkers"):
            self.compile({"attacking_player": "you", "or_planeswalkers": "you"})
