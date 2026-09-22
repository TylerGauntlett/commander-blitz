"""Zurgo and Ojutai's whole printed line, standing on the two pieces under it.

    Flying, haste
    Zurgo and Ojutai has hexproof as long as it entered this turn.
    Whenever one or more Dragons you control deal combat damage to a player or
    battle, look at the top three cards of your library. Put one of them into
    your hand and the rest on the bottom of your library in any order. You may
    return one of those Dragons to its owner's hand.

The card is the reason the two commits before this one exist, and it is the one
place they have to work **together**: the trigger's `filter` picks the Dragons
out of the swing, `or_battle` lets the swing be at a battle, and the `damagers`
binding hands the narrowed list to the `return_to_hand` at the end of the same
ability. Each half is covered on its own by `test_battles.py` and
`test_batched_combat_damage.py`; nothing there casts one card that needs all of
it at once.

The card itself lives in `data/authoring/answers/zurgo_and_ojutai.json` and is
verified through the six authoring gates, but it is not in the registry until
the deck lane collects it -- and the behaviour gate cannot reach this anyway,
because it casts a card and stops before combat (see the worker brief's trap 1
and 5). So the shape is carried by a test-pool card with the same trigger and
the same effects, `t_zao_lord`, and the gates cover the card file.

The two divergences this pins, both inherited and both already written down:

* **"…in any order"** is `rest_to_bottom`, which routes the leftovers through
  `state.rng` rather than asking. The count is what is asserted here.
* **A battle is attacked by its controller's opponents**, not by its protector's
  (506.2b is not modelled), so "or battle" is exercised by swinging at a battle
  the *opponent* controls. See `engine/battles.py`.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Step, Zone
from tests.conftest import _default_answer, only_oid, pass_until

LORD = "t_zao_lord"  # Zurgo and Ojutai's shape
DRAKE = "t_zao_plain"  # a second Dragon, no text
OGRE = "t_zao_ogre"  # a non-Dragon, so the filter has something to leave out
BATTLE = "t_battle_wall"  # Siege, defense 3


def board(builder, *, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 5 + [LORD, *mine])
        .battlefield(1, list(theirs))
        .hand(0, [])
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def swing(game, attackers, *, at=None, take_the_option=False):
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    for oid in attackers:
        options = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
        ]
        game.apply(
            next(
                a
                for a in options
                if any(
                    (ref.kind == "object" and ref.id == at)
                    if at is not None
                    else ref.kind == "player"
                    for ref in a.targets
                )
            )
        )
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    _settle(game, take_the_option=take_the_option)


class TestHexproofWhileItIsNew:
    """The middle line, which an earlier lane on this branch already built --
    `entered_this_turn` in `STATIC_FILTER_KEYS`, held by
    `tests/unit/test_entered_this_turn_filter.py`. Asserted here on the whole
    card rather than on a one-line shape, because the three printed lines share
    a permanent and nothing else on this card was standing on that key."""

    def test_a_copy_that_entered_this_turn_has_hexproof(self, builder):
        game = board(builder)
        assert "hexproof" in chars(game.state, _arrive(game, LORD)).keywords

    def test_the_one_that_has_been_there_does_not(self, builder):
        """A Zurgo that has stood there since last turn is an ordinary
        creature. `GameObject.entered_turn` is the near miss and would say
        otherwise for a *stolen* permanent, because `change_control` stamps it
        for 302.6."""
        game = board(builder)
        assert "hexproof" not in chars(game.state, only_oid(game, LORD, 0)).keywords


class TestTheTriggerOnAPlayer:
    def test_it_looks_at_three_and_keeps_one(self, builder):
        """Three off the library, one into hand and two to the bottom: the
        library keeps its size and the hand gains exactly one."""
        game = board(builder)
        library = len(game.state.players[0].library)
        hand = len(game.state.players[0].hand)
        swing(game, [only_oid(game, LORD, 0)])

        assert len(game.state.players[0].hand) - hand == 1
        assert len(game.state.players[0].library) == library - 1

    def test_it_fires_once_for_two_dragons(self, builder):
        """"One or more", which is the reason the batch event exists."""
        game = board(builder, mine=[DRAKE])
        hand = len(game.state.players[0].hand)
        swing(game, [only_oid(game, LORD, 0), only_oid(game, DRAKE, 0)])
        assert len(game.state.players[0].hand) - hand == 1

    def test_a_swing_of_non_dragons_alone_fires_nothing(self, builder):
        game = board(builder, mine=[OGRE])
        hand = len(game.state.players[0].hand)
        swing(game, [only_oid(game, OGRE, 0)])
        assert len(game.state.players[0].hand) == hand


class TestOrBattle:
    def test_the_trigger_fires_off_a_battle(self, builder):
        """The half the card would be missing without `or_battle`, and it is
        the half that makes the sentence worth writing: a Dragon that got
        through to a battle drew nothing before."""
        game = board(builder, theirs=[BATTLE])
        hand = len(game.state.players[0].hand)
        swing(game, [only_oid(game, LORD, 0)], at=only_oid(game, BATTLE, 1))

        assert len(game.state.players[0].hand) - hand == 1
        assert game.state.players[1].life == 40, "the seat took none of it"

    def test_the_battle_took_the_damage(self, builder):
        game = board(builder, theirs=[BATTLE])
        battle = only_oid(game, BATTLE, 1)
        swing(game, [only_oid(game, LORD, 0)], at=battle)
        assert battle not in game.state.battlefield, "4 power against defense 3"


class TestThoseDragons:
    def test_the_bounce_names_a_dragon_that_connected(self, builder):
        """`{"binding": "damagers"}`, narrowed by the trigger's own filter. The
        Ogre swung too and is not one of "those Dragons"; the Dragon that
        stayed home is not one either."""
        game = board(builder, mine=[DRAKE, OGRE])
        lord = only_oid(game, LORD, 0)
        drake, ogre = only_oid(game, DRAKE, 0), only_oid(game, OGRE, 0)
        swing(game, [lord, ogre], take_the_option=True)

        returned = [
            oid
            for oid in (lord, drake, ogre)
            if game.state.objects[oid].zone is Zone.HAND
        ]
        assert returned == [lord], "only the Dragon that connected came back"


def _settle(game, *, take_the_option: bool = False) -> None:
    """Run to the first decision at or after this turn's postcombat main.

    Compared as a ``(turn, step)`` pair rather than waiting for a step by name:
    a swing that triggers nothing holds priority nowhere between the block
    declaration and the next player's turn, so `END_OF_COMBAT` is a state
    nobody is asked about and waiting for it walks the game on for forty turns.

    ``take_the_option`` answers **yes** to the card's "You may return one of
    those Dragons". `pass_until`'s default answer to a `MAY` is no, which is the
    right passivity everywhere else and silently skips the clause this file
    exists to check.
    """
    from automtg.engine.actions import DecisionKind

    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    for _ in range(400):
        if (game.state.turn, game.state.step) >= mark or game.over:
            return
        decision = game.pending()
        if decision is None:
            return
        if take_the_option and decision.kind is DecisionKind.MAY:
            game.apply(
                next(a for a in game.legal_actions() if a.kind is ActionKind.YES)
            )
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the combat never settled")


def _arrive(game, card_id: str, pid: int = 0) -> int:
    """Make a card *enter* the battlefield, firing the real event.

    Not `builder.battlefield(..., sick=True)`, which sets `entered_turn` and
    emits nothing: only an arrival writes the turn ledger `entered_this_turn`
    reads. Borrowed from `test_entered_this_turn_filter.py`, which is where
    that distinction is argued out.
    """
    from automtg.engine.state import new_object
    from automtg.engine.zones import move_object

    obj = new_object(game.state, card_id, owner=pid, zone=Zone.HAND)
    game.state.players[pid].hand.append(obj.oid)
    move_object(game.state, obj.oid, Zone.BATTLEFIELD)
    return obj.oid
