"""The Bard, King of Dale deck, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 casts a card once, in one fixed sandbox, and reads the
board, and two of its documented limits bite almost every card in this deck:

- **It never activates an ability.** The Theorist's loyalty abilities, Shorikai's
  Pilot, Station, Urza's Saga's granted abilities and every utility land's second
  line are the whole point of those cards, and the harness stops before any of
  them.
- **A trigger that never fires cannot be asserted.** This is a group-hug deck:
  nearly every card triggers on an *opponent* drawing, casting or attacking, or on
  a second draw in a turn, and nothing in the sandbox does any of those after the
  card under test. The honest expectation for Esper Sentinel is "it is on the
  battlefield".

So the authoring expectations are floors, and these are the observations. Each
class is one card and asserts the printed sentence the gate could not reach, plus
the near miss -- the sentence that would be true of the card mis-written.

No card in the deck list is skipped: no gate expectation proves a card's whole
text, so every card named here has a class. The second half of the list is in
`test_bard_king_of_dale_deck_rest.py`, which imports its helpers from here.
"""

from __future__ import annotations

from automtg.engine.characteristics import abilities_of, chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.events import EventType
from tests.conftest import (
    _default_answer,
    action_for_card,
    activations,
    count_on_battlefield,
    oids_of,
    only_oid,
    pass_until,
    settle_to_priority,
)

# A castable instant, and it is load bearing rather than scenery. With no play
# available to anybody the engine's auto-pass runs whole turns inside one
# `apply`, so every seat that must be seen stopping holds one of these.
ANCHOR = "t_plain_instant"  # {W}, gain 1 life
DRAW_TWO = "divination"  # {2}{U} sorcery, "Draw two cards."
BEAR = "t_bear"  # a vanilla 2/2


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def cast(game, card_id: str, pid: int = 0, **match) -> int:
    """Cast ``card_id`` from ``pid``'s hand and let it resolve. Returns its oid."""
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().player == pid
        and any(
            a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == card_id
            for a in g.legal_actions()
        ),
    )
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
        and all(getattr(a, k) == v for k, v in match.items())
    )
    game.apply(action)
    settle_to_priority(game)
    return action.source


def activate(game, oid: int, index: int, **match) -> None:
    action = next(
        a
        for a in activations(game, oid, index)
        if all(getattr(a, k) == v for k, v in match.items())
    )
    game.apply(action)
    settle_to_priority(game)


def library(game, pid: int) -> int:
    return len(game.state.players[pid].library)


def tokens(game, def_id: str, pid: int | None = None) -> list:
    return [
        o for o in game.state.battlefield_objects(pid) if o.def_id == def_id and o.is_token
    ]


def to_step(game, step: Step, active: int) -> None:
    pass_until(game, lambda g: g.state.step is step and g.state.active_player == active)


def declare_attack(game, attacks: dict[int, tuple[str, int]]) -> None:
    """Declare each attacker at ``("player", pid)`` or ``("object", walker)``, and close.

    Stops at the declaration first, answering everything before it passively.
    """
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
    )
    for oid, (kind, target) in attacks.items():
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and any(t.kind == kind and t.id == target for t in a.targets)
            )
        )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


# ----------------------------------------------------------------------
# the commander
# ----------------------------------------------------------------------


class TestBardKingOfDale:
    """"If you would draw a card except the first one you draw in each of your draw
    steps, draw two cards instead." / "If one or more tokens would be created under
    your control, twice that many of those tokens are created instead."

    The gate cast Bard and read an unchanged hand: both lines are replacements on
    later events, and neither event happens in the sandbox.
    """

    def test_a_main_phase_draw_two_draws_four(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["bard_king_of_dale", "island", "island", "island"])
            .hand(0, [DRAW_TWO])
            .build()
        )
        before = library(game, 0)
        cast(game, DRAW_TWO)
        assert before - library(game, 0) == 4

    def test_without_bard_the_same_spell_draws_two(self, builder):
        """The control."""
        game = builder(players=2).battlefield(0, ["island"] * 3).hand(0, [DRAW_TWO]).build()
        before = library(game, 0)
        cast(game, DRAW_TWO)
        assert before - library(game, 0) == 2

    def test_the_turn_s_own_draw_is_not_doubled(self, builder):
        """The near miss is a plain doubler, and it draws two every draw step."""
        game = (
            builder(players=2)
            .battlefield(0, ["bard_king_of_dale", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(1)
            .step(Step.END_STEP)
            .build()
        )
        to_step(game, Step.UPKEEP, 0)
        before = library(game, 0)
        to_step(game, Step.PRECOMBAT_MAIN, 0)
        assert before - library(game, 0) == 1

    def test_an_opponent_s_draw_is_not_doubled(self, builder):
        """"If **you** would draw"."""
        game = (
            builder(players=2)
            .battlefield(0, ["bard_king_of_dale"])
            .battlefield(1, ["island"] * 3)
            .hand(1, [DRAW_TWO])
            .active(1)
            .build()
        )
        before = library(game, 1)
        cast(game, DRAW_TWO, pid=1)
        assert before - library(game, 1) == 2

    def test_a_token_you_create_is_two(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["bard_king_of_dale", "the_theorist_jace_beleren"])
            .build()
        )
        activate(game, only_oid(game, "the_theorist_jace_beleren"), 1)
        assert len(tokens(game, "illusion_1_1_u", 0)) == 2

    def test_an_opponent_s_token_is_not_doubled(self, builder):
        """"Under **your** control"."""
        game = (
            builder(players=2)
            .battlefield(0, ["the_theorist_jace_beleren"])
            .battlefield(1, ["bard_king_of_dale"])
            .build()
        )
        activate(game, only_oid(game, "the_theorist_jace_beleren"), 1)
        assert len(tokens(game, "illusion_1_1_u", 0)) == 1


class TestTheTheoristJaceBeleren:
    """A planeswalker, and the gate saw only its starting loyalty."""

    def position(self, builder, *, loyalty: int = 3, players: int = 2, **extra):
        b = builder(players=players).battlefield(
            0, ["the_theorist_jace_beleren"], counters={"loyalty": loyalty}
        )
        for pid, cards in extra.items():
            b = b.battlefield(int(pid[1:]), cards)
        game = b.build()
        return game, only_oid(game, "the_theorist_jace_beleren")

    def test_plus_one_makes_a_blue_illusion_and_gains_loyalty(self, builder):
        """"+1: Create a 1/1 blue Illusion creature token." """
        game, jace = self.position(builder)
        activate(game, jace, 1)

        [illusion] = tokens(game, "illusion_1_1_u", 0)
        c = chars(game.state, illusion.oid)
        assert (c.power, c.toughness) == (1, 1)
        assert {str(x) for x in c.colors} == {"U"}
        assert game.state.objects[jace].counters["loyalty"] == 4

    def test_minus_two_bounces_one_permanent_from_each_opponent(self, builder):
        """"For each opponent, return up to one target artifact or creature that
        player controls to its owner's hand." Both opponents lose one."""
        game, jace = self.position(
            builder, players=3, p1=[BEAR], p2=["sol_ring"], p0=["grizzly_bears"]
        )
        bear, ring = only_oid(game, BEAR, 1), only_oid(game, "sol_ring", 2)
        mine = only_oid(game, "grizzly_bears", 0)

        lines = activations(game, jace, 2)
        assert lines, "the -2 is offered"
        widest = max(lines, key=lambda a: len(a.targets))
        assert sorted(t.id for t in widest.targets) == sorted([bear, ring])
        assert all(mine not in [t.id for t in a.targets] for a in lines), "an opponent's, not mine"
        game.apply(widest)
        settle_to_priority(game)

        assert game.state.objects[bear].zone is Zone.HAND
        assert game.state.objects[ring].zone is Zone.HAND
        assert game.state.objects[jace].counters["loyalty"] == 1

    def test_minus_two_takes_at_most_one_from_a_single_opponent(self, builder):
        """"Up to **one** … that player controls" -- not every creature they have."""
        game, jace = self.position(builder, p1=[BEAR, "grizzly_bears"])
        assert all(len(a.targets) <= 1 for a in activations(game, jace, 2))

    def test_minus_six_draws_three_then_counts_the_hand(self, builder):
        """"Draw three cards. **Then** put X +1/+1 counters … where X is the number
        of cards in your hand." An empty hand before the draw is three after it --
        a version that read X first would put none."""
        game, jace = self.position(builder, loyalty=6, p0=[BEAR])
        bear = only_oid(game, BEAR, 0)
        assert game.state.players[0].hand == []

        activate(game, jace, 3)

        assert len(game.state.players[0].hand) == 3
        assert game.state.objects[bear].counters.get("+1/+1") == 3

    def test_it_draws_at_the_beginning_of_an_opponent_s_draw_step(self, builder):
        """"At the beginning of each opponent's draw step, you draw a card." """
        game = (
            builder(players=2)
            .battlefield(0, ["the_theorist_jace_beleren", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )
        to_step(game, Step.UPKEEP, 1)
        before = library(game, 0)
        to_step(game, Step.PRECOMBAT_MAIN, 1)
        assert before - library(game, 0) == 1

    def test_not_at_the_beginning_of_your_own(self, builder):
        """"Each **opponent's** draw step": my own draws only the turn's card."""
        game = (
            builder(players=2)
            .battlefield(0, ["the_theorist_jace_beleren", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(1)
            .step(Step.END_STEP)
            .build()
        )
        to_step(game, Step.UPKEEP, 0)
        before = library(game, 0)
        to_step(game, Step.PRECOMBAT_MAIN, 0)
        assert before - library(game, 0) == 1


class TestEsperSentinel:
    """"Whenever an opponent casts their first noncreature spell each turn, draw a
    card unless that player pays {X}, where X is this creature's power." """

    def position(self, builder, hand, lands=("plains", "plains", "plains")):
        return (
            builder(players=2)
            .battlefield(0, ["esper_sentinel", "plains"])
            .battlefield(1, list(lands))
            .hand(0, [ANCHOR])
            .hand(1, list(hand))
            .active(1)
            .build()
        )

    def answer_may(self, game, yes: bool) -> None:
        pass_until(
            game, lambda g: g.pending() is not None and g.pending().kind is DecisionKind.MAY
        )
        assert game.pending().player == 1, "that player decides whether to pay"
        want = ActionKind.YES if yes else ActionKind.NO
        game.apply(next(a for a in game.legal_actions() if a.kind is want))
        settle_to_priority(game)

    def test_an_unpaid_tax_draws(self, builder):
        game = self.position(builder, [ANCHOR])
        before = library(game, 0)
        cast_only(game, ANCHOR, 1)
        self.answer_may(game, yes=False)
        assert before - library(game, 0) == 1

    def test_paying_x_stops_the_draw(self, builder):
        game = self.position(builder, [ANCHOR])
        before = library(game, 0)
        cast_only(game, ANCHOR, 1)
        self.answer_may(game, yes=True)
        assert library(game, 0) == before
        assert sum(1 for o in game.state.battlefield_objects(1) if o.tapped) == 2, "{W} + {1}"

    def test_the_second_noncreature_spell_is_free(self, builder):
        """"Their **first** noncreature spell each turn"."""
        game = self.position(builder, [ANCHOR, ANCHOR])
        cast_only(game, ANCHOR, 1)
        self.answer_may(game, yes=False)
        before = library(game, 0)
        cast(game, ANCHOR, pid=1)
        assert library(game, 0) == before

    def test_a_creature_spell_does_not_trigger_it(self, builder):
        game = self.position(builder, [BEAR], lands=("forest", "forest"))
        before = library(game, 0)
        cast(game, BEAR, pid=1)
        assert library(game, 0) == before

    def test_my_own_spell_does_not_trigger_it(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["esper_sentinel", "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        before = library(game, 0)
        cast(game, ANCHOR)
        assert library(game, 0) == before


def cast_only(game, card_id: str, pid: int = 0) -> None:
    """Cast ``card_id`` and stop with it on the stack, answering nothing further."""
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().player == pid
        and any(
            a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == card_id
            for a in g.legal_actions()
        ),
    )
    game.apply(action_for_card(game, ActionKind.CAST, card_id))


def opponent_swings(builder, watcher: str, *, players: int = 2, mine=(), bears: int = 2):
    """Player 1's turn, ``bears`` ready to attack; ``watcher`` on player 0's side.

    Every seat holds a castable instant so the game stops in each step instead of
    auto-passing through combat.
    """
    b = (
        builder(players=players)
        .battlefield(0, [watcher, "plains", *mine])
        .hand(0, [ANCHOR])
        .battlefield(1, [BEAR] * bears + ["plains"])
        .hand(1, [ANCHOR])
    )
    for pid in range(2, players):
        b = b.battlefield(pid, ["plains"]).hand(pid, [ANCHOR])
    game = b.active(1).step(Step.UPKEEP).build()
    return game, oids_of(game, BEAR, 1)


class TestMangaraTheDiplomat:
    """"Whenever an opponent attacks with creatures, if two or more of those creatures
    are attacking you and/or planeswalkers you control, draw a card." / "Whenever an
    opponent casts their second spell each turn, draw a card." """

    def test_two_attackers_at_you_draw(self, builder):
        game, (a, b) = opponent_swings(builder, "mangara_the_diplomat")
        before = library(game, 0)
        declare_attack(game, {a: ("player", 0), b: ("player", 0)})
        settle_to_priority(game)
        assert before - library(game, 0) == 1

    def test_one_at_you_and_one_at_your_planeswalker_draw(self, builder):
        """"You **and/or** planeswalkers you control"."""
        game, (a, b) = opponent_swings(builder, "mangara_the_diplomat", mine=["t_walker"])
        walker = only_oid(game, "t_walker", 0)
        before = library(game, 0)
        declare_attack(game, {a: ("player", 0), b: ("object", walker)})
        settle_to_priority(game)
        assert before - library(game, 0) == 1

    def test_one_attacker_does_not_draw(self, builder):
        game, (a, _b) = opponent_swings(builder, "mangara_the_diplomat")
        before = library(game, 0)
        declare_attack(game, {a: ("player", 0)})
        settle_to_priority(game)
        assert library(game, 0) == before

    def test_a_split_attack_across_the_table_does_not_draw(self, builder):
        """Two attackers, but only one at you: "two or more **of those** … attacking
        you"."""
        game, (a, b) = opponent_swings(builder, "mangara_the_diplomat", players=3)
        before = library(game, 0)
        declare_attack(game, {a: ("player", 0), b: ("player", 2)})
        settle_to_priority(game)
        assert library(game, 0) == before

    def test_the_opponent_s_second_spell_draws_and_the_first_does_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["mangara_the_diplomat", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains", "plains"])
            .hand(1, [ANCHOR, ANCHOR])
            .active(1)
            .build()
        )
        before = library(game, 0)
        cast(game, ANCHOR, pid=1)
        assert library(game, 0) == before, "the first spell"
        cast(game, ANCHOR, pid=1)
        assert before - library(game, 0) == 1, "the second spell"

    def test_my_own_second_spell_does_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["mangara_the_diplomat", "plains", "plains"])
            .hand(0, [ANCHOR, ANCHOR])
            .build()
        )
        before = library(game, 0)
        cast(game, ANCHOR)
        cast(game, ANCHOR)
        assert library(game, 0) == before


class TestTheCouncilOfFour:
    """"Whenever a player draws their second card during their turn, you draw a card."
    / "Whenever a player casts their second spell during their turn, you create a 2/2
    white Knight creature token." """

    def test_an_opponent_s_second_draw_on_their_turn_draws(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["the_council_of_four", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["island"] * 3)
            .hand(1, [DRAW_TWO])
            .active(1)
            .build()
        )
        before = library(game, 0)
        cast(game, DRAW_TWO, pid=1)
        assert before - library(game, 0) == 1

    def test_an_opponent_drawing_during_my_turn_does_not(self, builder):
        """"During **their** turn". Secret Rendezvous hands the opponent three cards
        on my turn: my own second card triggers it once, theirs does not."""
        game = (
            builder(players=2)
            .battlefield(0, ["the_council_of_four", "plains", "plains", "plains"])
            .hand(0, ["secret_rendezvous"])
            .build()
        )
        mine, theirs = library(game, 0), library(game, 1)
        cast(game, "secret_rendezvous")
        assert theirs - library(game, 1) == 3
        assert mine - library(game, 0) == 4, "three, and one for my own second card"

    def test_a_second_spell_on_your_own_turn_makes_a_knight(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["the_council_of_four", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains", "plains"])
            .hand(1, [ANCHOR, ANCHOR])
            .active(1)
            .build()
        )
        cast(game, ANCHOR, pid=1)
        assert tokens(game, "knight_2_2_w") == []
        cast(game, ANCHOR, pid=1)
        assert len(tokens(game, "knight_2_2_w", 0)) == 1, "you create it, whoever cast"

    def test_two_instants_on_somebody_else_s_turn_make_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["the_council_of_four", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains", "plains"])
            .hand(1, [ANCHOR, ANCHOR])
            .build()
        )
        cast(game, ANCHOR, pid=1)
        cast(game, ANCHOR, pid=1)
        assert tokens(game, "knight_2_2_w") == []


class TestTheQueenOfDale:
    """"Whenever an opponent casts their first noncreature spell each turn, you
    recruit. (Draw a card, then discard a card. If you discarded a nonland card,
    create a 1/1 white Human Soldier creature token.)" """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["the_queen_of_dale", "plains"])
            .hand(0, [ANCHOR, BEAR])
            .library(0, ["island"] * 10)
            .battlefield(1, ["plains", "plains"])
            .hand(1, [ANCHOR, ANCHOR])
            .active(1)
            .build()
        )

    def recruit(self, game, discard: str) -> None:
        cast_only(game, ANCHOR, 1)
        pass_until(
            game,
            lambda g: g.pending() is not None
            and g.pending().kind is DecisionKind.CHOOSE_OBJECTS
            and g.pending().player == 0,
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE
                and game.state.objects[a.targets[0].id].def_id == discard
            )
        )
        settle_to_priority(game)

    def test_discarding_a_nonland_card_makes_a_soldier(self, builder):
        game = self.position(builder)
        self.recruit(game, BEAR)
        assert len(tokens(game, "human_soldier_1_1_w", 0)) == 1
        assert len(game.state.players[0].hand) == 2, "drew one, discarded one"

    def test_discarding_a_land_makes_nothing(self, builder):
        """"If you discarded a **nonland** card"."""
        game = self.position(builder)
        self.recruit(game, "island")
        assert tokens(game, "human_soldier_1_1_w") == []

    def test_only_the_first_noncreature_spell_recruits(self, builder):
        game = self.position(builder)
        self.recruit(game, BEAR)
        before = library(game, 0)
        cast(game, ANCHOR, pid=1)
        assert library(game, 0) == before


class TestTroubleInPairs:
    """"If an opponent would begin an extra turn, that player skips that turn
    instead." / "Whenever an opponent attacks you with two or more creatures, draws
    their second card each turn, or casts their second spell each turn, you draw a
    card." """

    def test_an_opponent_skips_the_extra_turn_they_would_take(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["trouble_in_pairs", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["island", "plains"])
            .hand(1, ["t_time_warp", ANCHOR])
            .active(1)
            .build()
        )
        cast(game, "t_time_warp", pid=1)
        pass_until(game, lambda g: g.state.step is Step.UPKEEP)
        assert [e.player for e in game.state.events if e.type == EventType.TURN_SKIPPED] == [1]
        assert game.state.active_player == 0 and not game.state.extra_turn

    def test_my_own_extra_turn_is_not_skipped(self, builder):
        """"If an **opponent** would begin an extra turn"."""
        game = (
            builder(players=2)
            .battlefield(0, ["trouble_in_pairs", "island", "plains"])
            .hand(0, ["t_time_warp", ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        cast(game, "t_time_warp")
        pass_until(game, lambda g: g.state.step is Step.UPKEEP)
        assert game.state.active_player == 0 and game.state.extra_turn
        assert not any(e.type == EventType.TURN_SKIPPED for e in game.state.events)

    def test_two_attackers_at_you_draw(self, builder):
        game, (a, b) = opponent_swings(builder, "trouble_in_pairs")
        before = library(game, 0)
        declare_attack(game, {a: ("player", 0), b: ("player", 0)})
        settle_to_priority(game)
        assert before - library(game, 0) == 1

    def test_one_at_you_and_one_at_your_planeswalker_does_not(self, builder):
        """"Attacks **you**" -- Mangara's "and/or planeswalkers you control" is the
        near miss, and this board is exactly where the two cards differ."""
        game, (a, b) = opponent_swings(builder, "trouble_in_pairs", mine=["t_walker"])
        walker = only_oid(game, "t_walker", 0)
        before = library(game, 0)
        declare_attack(game, {a: ("player", 0), b: ("object", walker)})
        settle_to_priority(game)
        assert library(game, 0) == before

    def test_an_opponent_s_second_card_on_my_turn_draws(self, builder):
        """"Draws their second card **each turn**" -- not only on their own turn,
        which is where this differs from The Council of Four."""
        game = (
            builder(players=2)
            .battlefield(0, ["trouble_in_pairs", "plains", "plains", "plains"])
            .hand(0, ["secret_rendezvous"])
            .build()
        )
        before = library(game, 0)
        cast(game, "secret_rendezvous")
        assert before - library(game, 0) == 4, "three, and one for their second card"

    def test_an_opponent_s_second_spell_draws(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["trouble_in_pairs", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains", "plains"])
            .hand(1, [ANCHOR, ANCHOR])
            .active(1)
            .build()
        )
        before = library(game, 0)
        cast(game, ANCHOR, pid=1)
        assert library(game, 0) == before
        cast(game, ANCHOR, pid=1)
        assert before - library(game, 0) == 1


class TestPerchProtection:
    """"Gift an extra turn … Create four 2/2 blue Bird creature tokens with flying. If
    the gift was promised, all permanents you control phase out, and until your next
    turn, your life total can't change and you gain protection from everything."

    The gate cast it unpromised and saw it exiled. The gift is the other half.
    """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["plains"] * 6 + [BEAR])
            .hand(0, ["perch_protection", ANCHOR])
            .battlefield(1, ["plains", "mountain"])
            .hand(1, [ANCHOR, "t_bolt"])
            .build()
        )

    def test_unpromised_it_makes_four_birds_and_nothing_else(self, builder):
        game = self.position(builder)
        cast(game, "perch_protection", gift_to=None)

        assert len(tokens(game, "bird_2_2_u_flying", 0)) == 4
        assert game.state.extra_turns == []
        assert not any(o.phased_out for o in game.state.battlefield_objects(0))

    def test_promised_the_opponent_takes_the_next_turn(self, builder):
        game = self.position(builder)
        cast(game, "perch_protection", gift_to=1)
        pass_until(game, lambda g: g.state.active_player == 1)
        assert game.state.extra_turn, "an extra turn, not their ordinary one"

    def test_promised_everything_you_control_phases_out_birds_included(self, builder):
        game = self.position(builder)
        bear = only_oid(game, BEAR, 0)
        cast(game, "perch_protection", gift_to=1)

        assert game.state.objects[bear].phased_out
        birds = [
            o for o in game.state.objects.values() if o.def_id == "bird_2_2_u_flying"
        ]
        assert len(birds) == 4 and all(o.phased_out for o in birds)

    def test_promised_your_life_total_can_t_change(self, builder):
        from automtg.engine.primitives import gain_life, lose_life

        game = self.position(builder)
        cast(game, "perch_protection", gift_to=1)
        lose_life(game.state, 0, 5)
        gain_life(game.state, 0, 5)
        assert game.state.players[0].life == 40

    def test_promised_you_can_t_be_targeted(self, builder):
        """Protection from everything: the opponent's Bolt has no line at my face."""
        game = self.position(builder)
        cast(game, "perch_protection", gift_to=1)
        pass_until(
            game,
            lambda g: g.state.active_player == 1
            and g.pending() is not None
            and g.pending().player == 1
            and g.state.step is Step.PRECOMBAT_MAIN,
        )
        bolts = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == "t_bolt"
        ]
        assert bolts, "the Bolt still has the opponent's own face to aim at"
        assert not any(t.kind == "player" and t.id == 0 for a in bolts for t in a.targets)


class TestCutADeal:
    """"Each opponent draws a card, then you draw a card for each opponent who drew a
    card this way."

    The gate's two-player table cannot tell "each opponent who drew" from "each
    opponent": both are one.
    """

    def test_at_a_pod_two_opponents_draw_and_so_do_you(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, ["plains"] * 3)
            .hand(0, ["cut_a_deal"])
            .build()
        )
        before = [library(game, p) for p in range(3)]
        cast(game, "cut_a_deal")
        assert [before[p] - library(game, p) for p in range(3)] == [2, 1, 1]

    def test_an_opponent_who_could_not_draw_does_not_count(self, builder):
        """The opponent with an empty library drew nothing, so I draw one, not two."""
        game = (
            builder(players=3)
            .battlefield(0, ["plains"] * 3)
            .hand(0, ["cut_a_deal"])
            .library(2, [])
            .build()
        )
        before = library(game, 0)
        cast(game, "cut_a_deal")
        assert before - library(game, 0) == 1


class TestChampionOfWits:
    """"Eternalize {5}{U}{U} (… Exile this card from your graveyard: Create a token
    that's a copy of it, except it's a 4/4 black Zombie Snake Wizard with no mana
    cost. Eternalize only as a sorcery.)" """

    def position(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 7)
            .graveyard(0, ["champion_of_wits"])
            .library(0, ["island"] * 10)
            .build()
        )
        return game, game.state.players[0].graveyard[0]

    def eternalize(self, game, card: int) -> None:
        game.apply(activations(game, card)[0])
        # "you may draw cards equal to its power": take it, then discard two
        while (p := game.pending()) is not None and p.kind is not DecisionKind.PRIORITY:
            if p.kind is DecisionKind.MAY:
                game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
            else:
                game.apply(_default_answer(game, p))
        settle_to_priority(game)

    def test_it_is_offered_from_the_graveyard(self, builder):
        game, card = self.position(builder)
        assert activations(game, card)

    def test_the_token_is_a_4_4_black_zombie_with_no_mana_cost(self, builder):
        game, card = self.position(builder)
        self.eternalize(game, card)

        assert game.state.objects[card].zone is Zone.EXILE, "the card pays for it"
        [token] = tokens(game, "champion_of_wits", 0)
        c = chars(game.state, token.oid)
        assert (c.power, c.toughness) == (4, 4)
        assert {str(x) for x in c.colors} == {"B"}, "black instead of blue, not as well"
        assert {"Zombie", "Wizard"} <= set(c.subtypes)
        assert token.copy_overrides.get("no_mana_cost"), "mana value 0, not the printed 3"

    def test_the_token_s_enters_trigger_draws_four(self, builder):
        """Its power is 4 now, so "draw cards equal to its power" draws four."""
        game, card = self.position(builder)
        before = library(game, 0)
        self.eternalize(game, card)
        assert before - library(game, 0) == 4
        assert len(game.state.players[0].hand) == 2, "four drawn, two discarded"

    def test_not_at_instant_speed(self, builder):
        """"Eternalize only as a sorcery": not on an opponent's turn."""
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 7 + ["plains"])
            .hand(0, [ANCHOR])
            .graveyard(0, ["champion_of_wits"])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .active(1)
            .build()
        )
        card = game.state.players[0].graveyard[0]
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 0)
        assert not activations(game, card)


class TestFaerieArtisans:
    """"Whenever a nontoken creature an opponent controls enters, create a token that's
    a copy of that creature except it's an artifact in addition to its other types.
    Then exile all other tokens created with this creature." """

    def position(self, builder, mine=()):
        return (
            builder(players=2)
            .battlefield(0, ["faerie_artisans", "plains", *mine])
            .hand(0, [ANCHOR])
            .battlefield(1, ["forest"] * 4)
            .hand(1, [BEAR, "grizzly_bears"])
            .active(1)
            .build()
        )

    def test_it_copies_the_creature_as_an_artifact(self, builder):
        game = self.position(builder)
        cast(game, BEAR, pid=1)
        [copy] = tokens(game, BEAR, 0)
        assert {"Artifact", "Creature"} <= {str(t) for t in chars(game.state, copy.oid).types}

    def test_the_next_copy_exiles_the_last(self, builder):
        game = self.position(builder)
        cast(game, BEAR, pid=1)
        [first] = tokens(game, BEAR, 0)
        cast(game, "grizzly_bears", pid=1)

        assert first.oid not in game.state.battlefield, "exiled, and a token ceases to exist"
        assert len(tokens(game, "grizzly_bears", 0)) == 1

    def test_a_token_it_did_not_make_is_left_alone(self, builder):
        """"All other tokens **created with this creature**", not all other tokens."""
        from automtg.engine.primitives import create_token

        game = self.position(builder)
        create_token(game.state, "illusion_1_1_u", 0)
        cast(game, BEAR, pid=1)
        cast(game, "grizzly_bears", pid=1)
        assert len(tokens(game, "illusion_1_1_u", 0)) == 1

    def test_my_own_creature_is_not_copied(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["faerie_artisans", "forest", "forest"])
            .hand(0, [BEAR])
            .build()
        )
        cast(game, BEAR)
        assert tokens(game, BEAR) == []


class TestVoiceOfVictory:
    """"Mobilize 2 (Whenever this creature attacks, create two tapped and attacking 1/1
    red Warrior creature tokens. Sacrifice them at the beginning of the next end
    step.)" / "Your opponents can't cast spells during your turn." """

    def windows(self, builder, active: int) -> list[bool]:
        """Every priority player 1 is given on ``active``'s turn: can they cast?

        A player with nothing to do is passed for automatically, so a Voice that
        works shows up as player 1 never being asked at all on my turn.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["voice_of_victory", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .active(active)
            .build()
        )
        seen = []
        while game.state.active_player == active and game.state.turn == 1:
            p = game.pending()
            if p.player == 1:
                seen.append(any(a.kind is ActionKind.CAST for a in game.legal_actions()))
            game.apply(_default_answer(game, p))
        return seen

    def test_an_opponent_can_t_cast_on_my_turn(self, builder):
        assert not any(self.windows(builder, active=0))

    def test_but_can_on_their_own(self, builder):
        """"During **your** turn"."""
        assert any(self.windows(builder, active=1))

    def test_attacking_makes_two_tapped_attacking_warriors(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["voice_of_victory", "plains"])
            .hand(0, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )
        voice = only_oid(game, "voice_of_victory", 0)
        declare_attack(game, {voice: ("player", 1)})
        settle_to_priority(game)

        warriors = tokens(game, "warrior_1_1_r", 0)
        assert len(warriors) == 2
        assert all(w.tapped and game.state.combat.attacking(w.oid) for w in warriors)

    def test_the_warriors_are_sacrificed_at_the_end_step(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["voice_of_victory", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )
        voice = only_oid(game, "voice_of_victory", 0)
        declare_attack(game, {voice: ("player", 1)})
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)
        assert len(tokens(game, "warrior_1_1_r", 0)) == 2, "still here after combat"

        to_step(game, Step.END_STEP, 0)
        settle_to_priority(game)
        assert tokens(game, "warrior_1_1_r") == []
        assert game.state.objects[voice].zone is Zone.BATTLEFIELD, "only the tokens"


class TestSeaGateRestoration:
    """"Draw cards equal to the number of cards in your hand plus one. You have no
    maximum hand size for the rest of the game." // Sea Gate, Reborn: "As this land
    enters, you may pay 3 life. If you don't, it enters tapped." """

    def test_it_draws_hand_plus_one(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 7)
            .hand(0, ["sea_gate_restoration_sea_gate_reborn", BEAR, BEAR])
            .build()
        )
        before = library(game, 0)
        cast(game, "sea_gate_restoration_sea_gate_reborn")
        assert before - library(game, 0) == 3, "two left in hand, plus one"

    def test_no_discard_to_hand_size_at_cleanup_afterwards(self, builder):
        """"For the rest of the game" -- the spell is in the graveyard by cleanup."""
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 7)
            .hand(0, ["sea_gate_restoration_sea_gate_reborn"] + [BEAR] * 9)
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        cast(game, "sea_gate_restoration_sea_gate_reborn")
        held = len(game.state.players[0].hand)
        assert held == 19
        pass_until(game, lambda g: g.state.active_player == 1)
        assert len(game.state.players[0].hand) == held

    def test_the_back_face_is_a_land_drop(self, builder):
        game = (
            builder(players=2)
            .hand(0, ["sea_gate_restoration_sea_gate_reborn"])
            .build()
        )
        # Two drops for the back face, paying 3 life and not: the choice is
        # which land drop to make (`Action.enters_paid`). Take the declining one.
        lines = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND and a.second_face and a.enters_paid is False
        ]
        assert lines
        card = lines[0].source
        game.apply(lines[0])
        while (p := game.pending()) is not None and p.kind is not DecisionKind.PRIORITY:
            game.apply(_default_answer(game, p))
        obj = game.state.objects[card]
        assert obj.zone is Zone.BATTLEFIELD
        assert game.state.card_of(obj).id == "sea_gate_reborn"
        assert obj.tapped, "no life paid, so it enters tapped"
        assert game.state.players[0].life == 40


class TestShorikaiGenesisEngine:
    """"{1}, {T}: Draw two cards, then discard a card. Create a 1/1 colorless Pilot
    creature token with "This token crews Vehicles as though its power were 2
    greater."" / "Crew 8" """

    def test_the_ability_draws_two_discards_one_and_makes_a_pilot(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["shorikai_genesis_engine", "island"])
            .build()
        )
        shorikai = only_oid(game, "shorikai_genesis_engine", 0)
        before = library(game, 0)
        game.apply(activations(game, shorikai, 0)[0])
        while (p := game.pending()) is not None and p.kind is not DecisionKind.PRIORITY:
            game.apply(_default_answer(game, p))
        settle_to_priority(game)

        assert before - library(game, 0) == 2
        assert len(game.state.players[0].hand) == 1
        [pilot] = tokens(game, "pilot_1_1_c_crew2", 0)
        c = chars(game.state, pilot.oid)
        assert (c.power, c.toughness) == (1, 1), "a 1/1 everywhere but a crew cost"
        assert game.state.objects[shorikai].tapped

    def test_a_pilot_and_a_five_five_crew_it(self, builder):
        """1 + 2 + 5 = 8."""
        game = (
            builder(players=2)
            .battlefield(0, ["shorikai_genesis_engine", "pilot_1_1_c_crew2", "t_five_five"])
            .build()
        )
        shorikai = only_oid(game, "shorikai_genesis_engine", 0)
        assert activations(game, shorikai, 1)

    def test_a_plain_one_one_and_the_same_five_five_do_not(self, builder):
        """The near miss: the Pilot without its line is six power, not eight."""
        game = (
            builder(players=2)
            .battlefield(0, ["shorikai_genesis_engine", "t_dork", "t_five_five"])
            .build()
        )
        shorikai = only_oid(game, "shorikai_genesis_engine", 0)
        assert not activations(game, shorikai, 1)


class TestAdagiaWindsweptBastion:
    """"Station (Tap another creature you control: Put charge counters equal to its
    power on this Planet. Station only as a sorcery.)" / "12+ | {3}{W}, {T}: Create a
    token that's a copy of target artifact or enchantment you control, except it's
    legendary. Activate only as a sorcery." """

    def position(self, builder, charge: int = 0):
        game = (
            builder(players=2)
            .battlefield(
                0, ["adagia_windswept_bastion"], counters={"charge": charge} if charge else None
            )
            .battlefield(0, ["t_five_five", "sol_ring"] + ["plains"] * 4)
            .build()
        )
        return game, only_oid(game, "adagia_windswept_bastion", 0)

    def test_station_puts_charge_counters_equal_to_the_tapped_creature_s_power(self, builder):
        game, adagia = self.position(builder)
        five = only_oid(game, "t_five_five", 0)
        game.apply(activations(game, adagia, 1)[0])
        while (p := game.pending()) is not None and p.kind is not DecisionKind.PRIORITY:
            game.apply(
                next(
                    (a for a in game.legal_actions() if five in [t.id for t in a.targets]),
                    _default_answer(game, p),
                )
            )
        settle_to_priority(game)
        assert game.state.objects[adagia].counters.get("charge") == 5
        assert game.state.objects[five].tapped
        assert not game.state.objects[adagia].tapped, "it taps the creature, not itself"

    def test_at_eleven_the_copy_ability_does_not_exist(self, builder):
        game, adagia = self.position(builder, 11)
        assert 2 not in [a.index for a in abilities_of(game.state, adagia)]
        assert not activations(game, adagia, 2)

    def test_at_twelve_it_copies_an_artifact_as_a_legendary_token(self, builder):
        game, adagia = self.position(builder, 12)
        ring = only_oid(game, "sol_ring", 0)
        activate(game, adagia, 2, targets=next(
            a.targets for a in activations(game, adagia, 2) if a.targets[0].id == ring
        ))
        [copy] = tokens(game, "sol_ring", 0)
        assert "Legendary" in {str(s) for s in chars(game.state, copy.oid).supertypes}
        assert "Legendary" not in {str(s) for s in chars(game.state, ring).supertypes}

    def test_it_enters_tapped(self, builder):
        game = builder(players=2).hand(0, ["adagia_windswept_bastion"]).build()
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "adagia_windswept_bastion"))
        assert game.state.objects[only_oid(game, "adagia_windswept_bastion", 0)].tapped


class TestUthrosTitanicGodcore:
    """"12+ | {U}, {T}: Add {U} for each artifact you control." """

    def position(self, builder, charge: int):
        game = (
            builder(players=2)
            .battlefield(0, ["uthros_titanic_godcore"], counters={"charge": charge})
            .battlefield(0, ["sol_ring"] * 3 + ["island", "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        return game, only_oid(game, "uthros_titanic_godcore", 0)

    def test_at_eleven_the_mana_ability_does_not_exist(self, builder):
        """Existence, not permission: the payment solver never asks legality."""
        game, uthros = self.position(builder, 11)
        assert 2 not in [a.index for a in abilities_of(game.state, uthros)]

    def test_at_twelve_it_adds_a_blue_for_each_artifact(self, builder):
        game, uthros = self.position(builder, 12)
        game.apply(activations(game, uthros, 2)[0])
        # A mana ability resolves at once; read the pool before a step ends it.
        pool = game.state.players[0].mana_pool
        assert pool.total() == 3, "three Sol Rings -- the land that paid {U} is no artifact"
        assert game.state.objects[uthros].tapped


class TestAdelineResplendentCathar:
    """"Adeline's power is equal to the number of creatures you control." / "Whenever
    you attack, for each opponent, create a 1/1 white Human creature token that's
    tapped and attacking that player or a planeswalker they control." """

    def test_her_power_counts_your_creatures(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["adeline_resplendent_cathar", BEAR, BEAR])
            .battlefield(1, [BEAR])
            .build(advance=False)
        )
        adeline = only_oid(game, "adeline_resplendent_cathar", 0)
        assert chars(game.state, adeline).power == 3, "herself and two Bears, not theirs"
        assert chars(game.state, adeline).toughness == 4

    def test_attacking_with_anything_makes_a_human_per_opponent(self, builder):
        """"Whenever **you** attack" -- Adeline stays home and still triggers -- and
        each Human attacks its own opponent."""
        game = (
            builder(players=3)
            .battlefield(0, ["adeline_resplendent_cathar", BEAR, "plains"])
            .hand(0, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )
        adeline = only_oid(game, "adeline_resplendent_cathar", 0)
        declare_attack(game, {only_oid(game, BEAR, 0): ("player", 1)})
        settle_to_priority(game)

        humans = tokens(game, "human_1_1_w", 0)
        assert len(humans) == 2
        assert sorted(game.state.combat.attackers[h.oid] for h in humans) == [1, 2]
        assert all(h.tapped for h in humans)
        assert not game.state.combat.attacking(adeline)


class TestUrzasSaga:
    """"I — This Saga gains "{T}: Add {C}."" / "II — This Saga gains "{2}, {T}: Create
    a 0/0 colorless Construct artifact creature token with 'This token gets +1/+1 for
    each artifact you control.'"" / "III — Search your library for an artifact card
    with mana cost {0} or {1}, put it onto the battlefield, then shuffle." """

    def texts(self, game, saga: int) -> list[str]:
        return [a.text for a in abilities_of(game.state, saga)]

    def test_chapter_one_grants_the_mana_ability_for_good(self, builder):
        """Played from hand; still there on the next turn, so not until end of turn."""
        game = (
            builder(players=2)
            .hand(0, ["urza_s_saga", ANCHOR])
            .battlefield(0, ["plains"])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "urza_s_saga"))
        settle_to_priority(game)
        saga = only_oid(game, "urza_s_saga", 0)
        assert "{T}: Add {C}." in self.texts(game, saga)
        assert not any(t.startswith("{2}") for t in self.texts(game, saga)), "not chapter II yet"

        pass_until(game, lambda g: g.state.active_player == 1)
        assert "{T}: Add {C}." in self.texts(game, saga)

    def test_chapter_two_makes_constructs_that_count_artifacts(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["urza_s_saga"], counters={"lore": 1})
            .battlefield(0, ["sol_ring", "plains", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .active(1)
            .step(Step.END_STEP)
            .build()
        )
        saga = only_oid(game, "urza_s_saga", 0)
        to_step(game, Step.PRECOMBAT_MAIN, 0)
        settle_to_priority(game)
        assert game.state.objects[saga].counters.get("lore") == 2
        construct_line = next(
            a.index for a in abilities_of(game.state, saga) if a.text.startswith("{2}, {T}")
        )
        activate(game, saga, construct_line)

        [construct] = tokens(game, "construct_0_0_c_artifact_buff", 0)
        c = chars(game.state, construct.oid)
        assert (c.power, c.toughness) == (2, 2), "itself and the Sol Ring"

    def test_chapter_three_finds_only_a_zero_or_one_cost_artifact(self, builder):
        """An artifact land has no mana cost, which is not mana cost {0}."""
        game = (
            builder(players=2)
            .battlefield(0, ["urza_s_saga"], counters={"lore": 2})
            .battlefield(0, ["plains"])
            .hand(0, [ANCHOR])
            .library(0, ["island", "seat_of_the_synod", "t_mc_two", "sol_ring", "island"])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .active(1)
            .step(Step.END_STEP)
            .build()
        )
        saga = only_oid(game, "urza_s_saga", 0)
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_OBJECTS,
        )
        offered = {game.state.objects[o.value].def_id for o in game.pending().options}
        assert offered == {"sol_ring"}
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
        settle_to_priority(game)

        assert count_on_battlefield(game, "sol_ring", 0) == 1
        assert saga not in game.state.battlefield, "sacrificed after III"


class TestCallTheCoppercoats:
    """"Strive — This spell costs {1}{W} more to cast for each target beyond the
    first." / "Choose any number of target opponents. Create X 1/1 white Human Soldier
    creature tokens, where X is the number of creatures those opponents control." """

    def position(self, builder, lands: int):
        return (
            builder(players=3)
            .battlefield(0, ["plains"] * lands + [BEAR])
            .hand(0, ["call_the_coppercoats"])
            .battlefield(1, [BEAR] * 3)
            .battlefield(2, [BEAR])
            .build()
        )

    def lines(self, game):
        return [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "call_the_coppercoats"
        ]

    def test_two_targets_cost_five(self, builder):
        assert not [a for a in self.lines(self.position(builder, 4)) if len(a.targets) == 2]
        assert [a for a in self.lines(self.position(builder, 5)) if len(a.targets) == 2]

    def test_x_counts_only_the_targeted_opponent_s_creatures(self, builder):
        """Player 2 alone: one Bear, not the four across the table, nor mine."""
        game = self.position(builder, 5)
        action = next(
            a for a in self.lines(game) if [t.id for t in a.targets] == [2]
        )
        game.apply(action)
        settle_to_priority(game)
        assert len(tokens(game, "human_soldier_1_1_w", 0)) == 1

    def test_both_opponents_count_all_four(self, builder):
        game = self.position(builder, 5)
        action = next(a for a in self.lines(game) if len(a.targets) == 2)
        game.apply(action)
        settle_to_priority(game)
        assert len(tokens(game, "human_soldier_1_1_w", 0)) == 4
