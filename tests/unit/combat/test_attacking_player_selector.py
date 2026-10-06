""""Whenever an opponent attacks **you** with two or more creatures" -- the
`attacking_player` selector key.

    Trouble in Pairs — "Whenever an opponent attacks you with two or more
    creatures, draws their second card each turn, or casts their second spell
    each turn, you draw a card."

Rule 506.2 gives an attacking creature three kinds of thing to attack: a player,
a planeswalker, or a battle. 508.1b has the active player choose one for each
creature. So a creature sent at your planeswalker is **not** attacking you, and
"attacks you with two or more creatures" does not count it.

The engine records the defending *player* in `combat.attackers` for both kinds,
and does so on purpose: `creatures_attack_player` with `defending: "you"` binds
`attackers` as every creature attacking you **and/or your planeswalkers**, which
is word for word Mangara, the Diplomat -- a shipped card whose meaning this must
not change. Counting that binding for Trouble in Pairs is one creature too many:
one creature at you and one at your planeswalker would draw a card the printed
card does not draw.

`attacking` is the near miss and is a bare boolean with no notion of whom.
`attacking_player` names whom -- `"you"`, `"opponent"` or `"any"` player,
relative to the ability's controller -- and excludes every creature whose attack
is recorded in `combat.attacking_permanent`, a field that until now nothing
outside combat damage read. A selector key rather than a trigger option, because
it composes: it narrows the `attackers` binding inside `count`, and the same
words work on any pool of attacking creatures.

What is pinned below, and each is a way this could be silently wrong:

1. One at you and one at your planeswalker counts **1** -- the whole card.
2. Two at you counts 2, and the trigger fires.
3. At a pod, creatures attacking a *different* opponent are not attacking you.
4. The Mangara reading is unchanged beside it: the same split counts 2 there.
5. Out of combat nothing is attacking anybody.
6. The trigger-filter half honours the key rather than loading and ignoring it.
7. The loader refuses `true`, the spelling `attacking` invites.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import resolve_pool
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.triggers import matches_card_filter
from tests.conftest import _default_answer, oids_of, only_oid, pass_until, settle

BEAR = "t_bear"
WALKER = "t_walker"
#: Trouble in Pairs' attack clause, paying 1 life rather than a card.
PAIRS = "t_pairs_watcher"
#: Mangara, the Diplomat's attack clause -- "you and/or planeswalkers you
#: control" -- written with the bare binding, as the shipped card is.
DIPLOMAT = "t_diplomat_watcher"

#: Where a bear is sent: at a player's face, or at that player's planeswalker.
FACE = "face"
PW = "walker"


def position(builder, *, bears: int, p1=(), p2=()):
    """Player 0 attacks; players 1 and 2 defend.

    Three players, because "attacks you" has a second way to be wrong that a
    two-player game cannot show: counting creatures aimed at somebody else.
    """
    b = builder(players=3)
    b.battlefield(0, [BEAR] * bears)
    if p1:
        b.battlefield(1, list(p1))
    if p2:
        b.battlefield(2, list(p2))
    for pid in range(3):
        b.library(pid, ["swamp"] * 20)
    return b.active(0).step(Step.UNTAP).max_turns(2).build()


def to_declare_attackers(game, limit: int = 80):
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def declare(game, plan: list[tuple[int, str]]) -> list[int]:
    """Send player 0's bears, one per ``(seat, FACE | PW)`` entry, in order.

    Stops after the triggers resolve and **before** combat ends, so the attack
    is still live for the selector to be asked about. Returns the bears in plan
    order.
    """
    to_declare_attackers(game)
    bears = list(oids_of(game, BEAR, 0))
    sent = []
    for seat, at in plan:
        oid = bears.pop(0)
        if at == FACE:
            want = ("player", seat)
        else:
            want = ("object", only_oid(game, WALKER, seat))
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER
            and a.source == oid
            and any((t.kind, t.id) == want for t in a.targets)
        )
        game.apply(action)
        sent.append(oid)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    settle(game)
    assert game.state.combat is not None, "the attack has to still be live"
    return sent


def count(game, controller: int, who: str) -> int:
    ctx = EffectContext(state=game.state, controller=controller)
    return len(resolve_pool(ctx, {"attacking_player": who}))


def life(game, pid: int) -> int:
    return game.state.players[pid].life


class TestAttacksYouExcludesYourPlaneswalkers:
    def test_one_at_you_and_one_at_your_planeswalker_counts_one(self, builder):
        """The card. Two creatures are attacking "you and/or your planeswalkers"
        and only one is attacking you, so Trouble in Pairs does not draw."""
        game = position(builder, bears=2, p1=(PAIRS, WALKER))
        before = life(game, 1)
        declare(game, [(1, FACE), (1, PW)])

        assert count(game, 1, "you") == 1
        assert life(game, 1) == before

    def test_two_at_you_counts_two_and_fires(self, builder):
        game = position(builder, bears=2, p1=(PAIRS, WALKER))
        before = life(game, 1)
        declare(game, [(1, FACE), (1, FACE)])

        assert count(game, 1, "you") == 2
        assert life(game, 1) == before + 1

    def test_both_at_your_planeswalker_count_zero(self, builder):
        game = position(builder, bears=2, p1=(PAIRS, WALKER))
        before = life(game, 1)
        declare(game, [(1, PW), (1, PW)])

        assert count(game, 1, "you") == 0
        assert life(game, 1) == before

    def test_the_diplomat_reading_still_counts_the_planeswalker(self, builder):
        """Mangara's "you and/or planeswalkers you control" is the bare binding,
        and the same split that leaves Trouble in Pairs silent pays it."""
        game = position(builder, bears=2, p1=(DIPLOMAT, WALKER))
        before = life(game, 1)
        declare(game, [(1, FACE), (1, PW)])

        assert life(game, 1) == before + 1


class TestAtAPod:
    def test_attacks_at_another_opponent_are_not_attacking_you(self, builder):
        """Player 1 is attacked by one creature and player 2 by two. From
        player 1's seat that is one creature attacking *you*."""
        game = position(builder, bears=3, p1=(PAIRS,))
        before = life(game, 1)
        declare(game, [(1, FACE), (2, FACE), (2, FACE)])

        assert count(game, 1, "you") == 1
        assert life(game, 1) == before

    def test_opponent_and_any_name_the_other_seats(self, builder):
        """From player 1's seat: one bear at player 2, one at player 2's
        planeswalker, one at player 1. `opponent` is the bear at player 2's
        face; `any` adds player 1's; neither ever counts the planeswalker."""
        game = position(builder, bears=3, p2=(WALKER,))
        declare(game, [(2, FACE), (2, PW), (1, FACE)])

        assert count(game, 1, "opponent") == 1
        assert count(game, 1, "any") == 2
        assert count(game, 2, "you") == 1

    def test_the_trigger_filter_half_reads_it_too(self, builder):
        """A trigger filter is validated against the same `SELECTOR_KEYS`; a key
        loaded there and ignored would be the silently-wider filter."""
        game = position(builder, bears=2, p1=(PAIRS, WALKER))
        at_face, at_walker = declare(game, [(1, FACE), (1, PW)])
        source = game.state.objects[only_oid(game, PAIRS, 1)]
        filt = {"attacking_player": "you"}

        assert matches_card_filter(game.state, at_face, filt, source)
        assert not matches_card_filter(game.state, at_walker, filt, source)


class TestOutOfCombat:
    def test_nothing_is_attacking_anybody_once_combat_ends(self, builder):
        game = position(builder, bears=2, p1=(WALKER,))
        declare(game, [(1, FACE), (1, FACE)])
        assert count(game, 1, "you") == 2

        pass_until(game, lambda g: g.state.combat is None)

        assert count(game, 1, "you") == 0
        assert count(game, 1, "any") == 0


class TestTheLoader:
    def compile(self, selector: dict):
        model = CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "mana_cost": "{W}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "triggered",
                        "trigger": {
                            "event": "creatures_attack_player",
                            "controller": "opponent",
                            "defending": "you",
                            "condition": {
                                "cmp": ">=",
                                "left": {"count": selector},
                                "right": {"const": 2},
                            },
                        },
                        "effects": [
                            {"op": "gain_life", "player": "you", "amount": {"const": 1}}
                        ],
                    }
                ],
            }
        )
        return compile_card(model)

    def test_a_player_word_loads(self):
        self.compile({"binding": "attackers", "attacking_player": "you"})

    @pytest.mark.parametrize("bad", [True, "defender", "each_opponent"])
    def test_anything_else_is_refused(self, bad):
        """`true` is how `attacking` is spelled, and read as a word it would name
        nobody -- every creature would fail it and the card would never draw."""
        with pytest.raises(DslError, match="attacking_player"):
            self.compile({"binding": "attackers", "attacking_player": bad})
