""""Whenever an opponent discards a card, you may gain 3 life." -- Sangromancer.

The last card in `precon_deficits.json`, and the only one of the eight that was
a real gap rather than a card file that had fallen behind the engine. Discarding
was fully modelled — rule 701.8, `primitives.discard_cards`, and an `EventType.
DISCARD` fired once per card since the beginning — but `TRIGGER_EVENTS` had no
name for it, so no card could listen. The event was emitted into a log that only
the UI read.

Three things make the shape worth pinning rather than assuming:

**`controller` names the player who discarded.** It defaults to `"you"`, which
is the trap the Sengir Vampire run wrote down: an unqualified trigger loads,
looks implemented, and watches the wrong seat forever. Sangromancer wants
`"opponent"`, and the two must not be the same trigger with a different label.

The actor is read off the *event*, not off the discarded object, which is why
`discard` appears in `_actor`'s explicit list as well as in
`OBJECT_SUBJECT_TRIGGERS`. By the time the trigger is collected the card is in a
graveyard, and its controller has been through `reset_permanent_state`;
`discard_cards` puts the discarding player on the event, so that is the copy to
trust.

**One trigger per card, not per discard.** "Discards a card" is singular, and
`discard_cards` fires per oid — so an effect that takes two cards is two
triggers and six life, not one and three.

**Every discard is a discard.** Cycling pays its cost by discarding the card
(rule 702.29a), and the cleanup step's discard to hand size (rule 514.1) is the
commonest discard in any real game. Both run through `discard_cards`, so both
fire this — and a Sangromancer that missed the cleanup discard would be a card
that almost never triggered at a table.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Step
from commanderblitz.engine.player import MAX_HAND_SIZE
from commanderblitz.engine.primitives import discard_cards
from tests.conftest import pass_until

SANGROMANCER = "sangromancer"
WATCHER = "t_discard_watcher"  # "Whenever an opponent discards a card, gain 3"
OWN_WATCHER = "t_own_discard_watcher"  # the same trigger, `controller: "you"`
CREATURE_WATCHER = "t_creature_discard_watcher"  # …discards a *creature* card

START = 40  # the sandbox's starting life


def board(builder, watcher: str, *, opponent_hand=("t_bear",), your_hand=()):
    """`watcher` on player 0's battlefield, with hands to throw away."""
    return (
        builder(players=2)
        .battlefield(0, [watcher])
        .hand(1, list(opponent_hand))
        .hand(0, list(your_hand))
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def hand_oids(game, pid: int) -> list[int]:
    return list(game.state.players[pid].hand)


def settle(game) -> None:
    """Let every queued trigger reach the stack and resolve."""
    game._advance()
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


class TestItFiresOnTheRightSeat:
    def test_an_opponents_discard_gains_you_life(self, builder):
        game = board(builder, WATCHER)
        discard_cards(game.state, 1, hand_oids(game, 1))
        settle(game)
        assert life(game) == START + 3

    def test_your_own_discard_does_not(self, builder):
        """`controller: "opponent"` is a real filter, not decoration."""
        game = board(builder, WATCHER, your_hand=("t_bear",))
        discard_cards(game.state, 0, hand_oids(game, 0))
        settle(game)
        assert life(game) == START

    def test_the_you_form_is_the_mirror_image(self, builder):
        """Both directions, because a trigger that fires on everything passes
        the test above by accident."""
        game = board(builder, OWN_WATCHER, your_hand=("t_bear",))
        discard_cards(game.state, 0, hand_oids(game, 0))
        settle(game)
        assert life(game) == START + 3

    def test_the_you_form_ignores_an_opponent(self, builder):
        game = board(builder, OWN_WATCHER)
        discard_cards(game.state, 1, hand_oids(game, 1))
        settle(game)
        assert life(game) == START


class TestOneTriggerPerCard:
    def test_two_cards_discarded_is_two_triggers(self, builder):
        game = board(builder, WATCHER, opponent_hand=("t_bear", "t_bear"))
        discard_cards(game.state, 1, hand_oids(game, 1))
        settle(game)
        assert life(game) == START + 6, "'discards a card' is per card"

    def test_an_empty_hand_fires_nothing(self, builder):
        game = board(builder, WATCHER, opponent_hand=())
        discard_cards(game.state, 1, [])
        settle(game)
        assert life(game) == START


class TestEveryDiscardCounts:
    def test_the_cleanup_discard_to_hand_size(self, builder):
        """Rule 514.1, and the commonest discard there is.

        Player 1 is the active player, so it is their cleanup that trims their
        hand — a discard by the opponent of the watcher's controller.
        """
        game = (
            builder(players=2)
            .battlefield(0, [WATCHER])
            .hand(1, ["t_bear"] * (MAX_HAND_SIZE + 2))
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        pass_until(game, lambda g: g.state.turn == 2)
        assert len(game.state.players[1].hand) <= MAX_HAND_SIZE, "the trim happened"
        assert life(game) == START + 6, "two cards over the limit, two triggers"

    def test_cycling_is_a_discard(self, builder):
        """Rule 702.29a: the cycling cost *is* a discard, so it fires this."""
        game = (
            builder(players=2)
            .battlefield(0, [WATCHER])
            .hand(1, ["t_cycler"])
            .battlefield(1, ["forest", "forest"])
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        cycle = next(
            (a for a in game.legal_actions() if "cycling" in (a.label or "").lower()),
            None,
        )
        assert cycle is not None, (
            f"no cycling action offered; legal: "
            f"{[a.label or a.kind.value for a in game.legal_actions()]}"
        )
        game.apply(cycle)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert life(game) == START + 3


class TestTheFilterReadsTheDiscardedCard:
    """`discard` is in `OBJECT_SUBJECT_TRIGGERS`, so a filter has a subject.

    The card is in the graveyard by the time the trigger is collected, and
    `matches_card_filter` reads the printed face — which is exactly the case it
    was written for.
    """

    def test_a_creature_card_matches(self, builder):
        game = board(builder, CREATURE_WATCHER, opponent_hand=("t_bear",))
        discard_cards(game.state, 1, hand_oids(game, 1))
        settle(game)
        assert life(game) == START + 3

    def test_a_land_does_not(self, builder):
        game = board(builder, CREATURE_WATCHER, opponent_hand=("forest",))
        discard_cards(game.state, 1, hand_oids(game, 1))
        settle(game)
        assert life(game) == START

    def test_only_the_matching_card_of_two(self, builder):
        game = board(builder, CREATURE_WATCHER, opponent_hand=("forest", "t_bear"))
        discard_cards(game.state, 1, hand_oids(game, 1))
        settle(game)
        assert life(game) == START + 3


class TestTheShippedCard:
    def test_sangromancer_gains_three_when_an_opponent_discards(self, builder):
        game = board(builder, SANGROMANCER)
        discard_cards(game.state, 1, hand_oids(game, 1))
        settle(game)
        assert life(game) == START + 3

    def test_its_other_trigger_still_works(self, builder):
        """The card has two "you may gain 3 life" clauses on different events.

        Worth one assertion: adding the second ability to the card file is the
        kind of edit that can shadow the first if the trigger list is rebuilt
        rather than appended to.
        """
        from commanderblitz.engine.zones import destroy

        game = (
            builder(players=2)
            .battlefield(0, [SANGROMANCER])
            .battlefield(1, ["t_bear"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        victim = next(
            o for o in game.state.battlefield if game.state.objects[o].def_id == "t_bear"
        )
        destroy(game.state, victim)
        settle(game)
        assert life(game) == START + 3
