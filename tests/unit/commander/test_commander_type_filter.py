""""…that shares a creature type with your commander."

    Path of Ancestry — "When that mana is spent to cast a creature spell that
    shares a creature type with your commander, scry 1."

`shares_a_type_with` already existed and cannot say this. It resolves its
argument through `_bound_oid`: it names an object bound earlier in the *same*
effect, by a target or by a trigger. Nothing binds the commander, the commander
is not what this trigger is about, and it is usually sitting in the command zone
rather than on the battlefield — so there is nothing to find and the clause is
always false.

`is_commander` is the other near-miss and asks a different question. It is a
predicate on the object being tested ("is this permanent a commander"), not a
reference to compare a *different* object against, and it is a battlefield test.

A literal `subtypes` list is the approximation to refuse. Which creature type
matters is a property of whatever deck the card is played in, not of Path of
Ancestry — writing `["Vampire"]` into the card is a different card in every
other deck, and one that still loads and still looks implemented.

So this key takes a **player**, and the set it compares against comes from
`characteristics.commander_subtypes`. That helper is shared by both halves of
the filter language — `selectors.matches` for effects and
`triggers.matches_card_filter` for trigger filters, which is the half Path of
Ancestry actually reaches — so the two cannot disagree about what a commander's
types are.

The union across a player's commanders, so a partner pair is satisfied by
either half. Read through `chars` on the battlefield and off the printed card
elsewhere: an animated general really does share its new type, and one in the
command zone has only what is printed.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.player_statics import commander_subtypes
from tests.conftest import pass_until

WATCHER = "t_kindred_watcher"  # gains 1 life on a matching creature spell
BEAR = "t_bear"  # a Bear, {1}{G}
BAT_COMMANDER = "t_bats"  # a Bat, and nothing a Bear shares
BEAR_COMMANDER = "t_bear"


def board(builder, commander: str, hand: list[str]):
    return (
        builder(players=2)
        .battlefield(0, [WATCHER] + ["forest"] * 5)
        .hand(0, list(hand))
        .library(0, ["forest"] * 20)
        .commander(0, [commander])
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def cast(game, card_id: str) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == card_id
        )
    )
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


class TestTheTypeComesFromTheCommander:
    def test_a_matching_spell_triggers_it(self, builder):
        game = board(builder, BEAR_COMMANDER, [BEAR])
        life = game.state.players[0].life
        cast(game, BEAR)
        assert game.state.players[0].life == life + 1

    def test_a_mismatching_spell_does_not(self, builder):
        """The same spell, the same card on the board, a different deck."""
        game = board(builder, BAT_COMMANDER, [BEAR])
        life = game.state.players[0].life
        cast(game, BEAR)
        assert game.state.players[0].life == life


class TestWhereTheCommanderIsRead:
    def test_the_command_zone_counts(self, builder):
        """Where a commander sits for most of the game. `is_commander` is a
        battlefield test and would see nothing here."""
        game = board(builder, BEAR_COMMANDER, [BEAR])
        assert commander_subtypes(game.state, 0) == frozenset({"Bear"})

    def test_no_commander_shares_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [WATCHER] + ["forest"] * 5)
            .hand(0, [BEAR])
            .library(0, ["forest"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        life = game.state.players[0].life
        cast(game, BEAR)
        assert game.state.players[0].life == life

    def test_it_is_the_union_across_partners(self, builder):
        """Either half satisfies "shares a creature type with your commander"."""
        game = (
            builder(players=2)
            .battlefield(0, [WATCHER] + ["forest"] * 5)
            .hand(0, [BEAR])
            .library(0, ["forest"] * 20)
            .commander(0, [BEAR_COMMANDER, BAT_COMMANDER])
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        assert commander_subtypes(game.state, 0) >= {"Bear", "Bat"}


class TestItIsNotTheOtherSeat:
    def test_an_opponents_commander_is_a_different_question(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [WATCHER] + ["forest"] * 5)
            .hand(0, [BEAR])
            .library(0, ["forest"] * 20)
            .commander(0, [BAT_COMMANDER])
            .commander(1, [BEAR_COMMANDER])
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        life = game.state.players[0].life
        cast(game, BEAR)
        assert game.state.players[0].life == life, "it asked seat 1's commander"
