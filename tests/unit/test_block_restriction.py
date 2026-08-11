"""Card-supplied restrictions on how a creature may be blocked.

    Tromokratis — "Tromokratis can't be blocked unless all creatures defending
    player controls block it."

    Stromkirk Noble — "This creature can't be blocked by Humans."

Before this, `combat.blocks_valid` hardcoded menace as the only block
restriction in the game and `can_block` knew flying, reach and protection. There
was no seam for a card to add one, so four cards in the shipped pool print an
evasion ability they do not have — and an evasion ability that does not evade is
invisible until the game somebody was counting on it in.

The two forms are not one form with a parameter, and that is the whole design:

- **A filter on the blocker** — "can't be blocked by Humans" — is a *per-pair*
  question, decided one blocker at a time, and belongs in `can_block` beside
  flying and protection.
- **`require_all`** cannot be answered per pair at all. Whether this block is
  legal depends on what every *other* creature is doing, so it belongs in
  `blocks_valid`, which is exactly the shape menace already needed.

A static carrying neither is refused at load time: it would be an evasion
ability that evades nothing, and it would load cleanly.
"""

from __future__ import annotations

from automtg.engine.combat import blocks_valid, can_block
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until


def to_blockers(game):
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )


def to_attackers(game):
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )


def attack_with(game, oid: int, defender: int = 1):
    game.apply(
        find_action(
            game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(defender),)
        )
    )


def board(builder, attacker: str, blockers: list[str]):
    """``(game, attacker_oid)`` with the attack already declared."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 8 + [attacker])
        .battlefield(1, blockers)
        .build()
    )
    oid = only_oid(game, attacker)
    to_attackers(game)
    attack_with(game, oid)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    to_blockers(game)
    return game, oid


class TestAFilterOnTheBlocker:
    def test_a_matching_blocker_is_refused(self, builder):
        game, attacker = board(builder, "t_no_bears", ["t_bear"])
        bear = only_oid(game, "t_bear", 1)
        assert not can_block(game.state, bear, attacker, 1)

    def test_a_creature_outside_the_filter_still_blocks(self, builder):
        """The pair. Without it, "can't be blocked" passes the test above."""
        game, attacker = board(builder, "t_no_bears", ["t_dork"])
        dork = only_oid(game, "t_dork", 1)
        assert can_block(game.state, dork, attacker, 1)

    def test_legality_does_not_offer_the_refused_block(self, builder):
        game, _ = board(builder, "t_no_bears", ["t_bear"])
        bear = only_oid(game, "t_bear", 1)
        offered = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_BLOCKER and a.source == bear
        ]
        assert not offered

    def test_a_creature_without_the_static_is_blocked_normally(self, builder):
        game, attacker = board(builder, "t_trampler", ["t_bear"])
        bear = only_oid(game, "t_bear", 1)
        assert can_block(game.state, bear, attacker, 1)


class TestRequireAll:
    def test_one_blocker_out_of_two_is_an_illegal_declaration(self, builder):
        """The card's own reminder text: "if any creature that player controls
        doesn't block this creature, it can't be blocked"."""
        game, attacker = board(builder, "t_tromokratis", ["t_bear", "t_dork"])
        bear = only_oid(game, "t_bear", 1)
        game.apply(
            find_action(
                game,
                ActionKind.ADD_BLOCKER,
                source=bear,
                targets=(TargetRef.obj(attacker),),
            )
        )
        assert not blocks_valid(game.state, 1)

    def test_every_creature_blocking_is_legal(self, builder):
        game, attacker = board(builder, "t_tromokratis", ["t_bear", "t_dork"])
        for card_id in ("t_bear", "t_dork"):
            oid = only_oid(game, card_id, 1)
            game.apply(
                find_action(
                    game,
                    ActionKind.ADD_BLOCKER,
                    source=oid,
                    targets=(TargetRef.obj(attacker),),
                )
            )
        assert blocks_valid(game.state, 1)

    def test_declining_to_block_at_all_is_legal(self, builder):
        """"Can't be blocked unless" restricts blocking, it does not require it."""
        game, _ = board(builder, "t_tromokratis", ["t_bear", "t_dork"])
        assert blocks_valid(game.state, 1)

    def test_a_tapped_creature_still_counts(self, builder):
        """Deliberate, and it is what makes the card what it is. The printed line
        says "controls", not "could block", so a tapped creature that cannot
        block makes the whole block illegal."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 8 + ["t_tromokratis"])
            .battlefield(1, ["t_bear"])
            .battlefield(1, ["t_dork"], tapped=True)
            .build()
        )
        attacker = only_oid(game, "t_tromokratis")
        to_attackers(game)
        attack_with(game, attacker)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        to_blockers(game)
        bear = only_oid(game, "t_bear", 1)
        game.apply(
            find_action(
                game,
                ActionKind.ADD_BLOCKER,
                source=bear,
                targets=(TargetRef.obj(attacker),),
            )
        )
        assert not blocks_valid(game.state, 1), (
            "the tapped creature was ignored; this is 'could block', not 'controls'"
        )
