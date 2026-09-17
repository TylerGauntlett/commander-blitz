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
text, so every card named here has a class.
"""

from __future__ import annotations

from automtg.engine.characteristics import abilities_of, chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.events import EventType
from tests.conftest import (
    _default_answer,
    action_for_card,
    count_on_battlefield,
    oids_of,
    only_oid,
    pass_until,
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


def settle(game) -> None:
    """Pass until the stack is empty and nobody is mid-resolution."""
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


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
    settle(game)
    return action.source


def activations(game, oid: int, index: int | None = None) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and a.source == oid
        and (index is None or a.ability_index == index)
    ]


def activate(game, oid: int, index: int, **match) -> None:
    action = next(
        a
        for a in activations(game, oid, index)
        if all(getattr(a, k) == v for k, v in match.items())
    )
    game.apply(action)
    settle(game)


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
        settle(game)

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
        settle(game)

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
        settle(game)
        assert before - library(game, 0) == 1

    def test_one_at_you_and_one_at_your_planeswalker_draw(self, builder):
        """"You **and/or** planeswalkers you control"."""
        game, (a, b) = opponent_swings(builder, "mangara_the_diplomat", mine=["t_walker"])
        walker = only_oid(game, "t_walker", 0)
        before = library(game, 0)
        declare_attack(game, {a: ("player", 0), b: ("object", walker)})
        settle(game)
        assert before - library(game, 0) == 1

    def test_one_attacker_does_not_draw(self, builder):
        game, (a, _b) = opponent_swings(builder, "mangara_the_diplomat")
        before = library(game, 0)
        declare_attack(game, {a: ("player", 0)})
        settle(game)
        assert library(game, 0) == before

    def test_a_split_attack_across_the_table_does_not_draw(self, builder):
        """Two attackers, but only one at you: "two or more **of those** … attacking
        you"."""
        game, (a, b) = opponent_swings(builder, "mangara_the_diplomat", players=3)
        before = library(game, 0)
        declare_attack(game, {a: ("player", 0), b: ("player", 2)})
        settle(game)
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
        settle(game)

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
        settle(game)
        assert before - library(game, 0) == 1

    def test_one_at_you_and_one_at_your_planeswalker_does_not(self, builder):
        """"Attacks **you**" -- Mangara's "and/or planeswalkers you control" is the
        near miss, and this board is exactly where the two cards differ."""
        game, (a, b) = opponent_swings(builder, "trouble_in_pairs", mine=["t_walker"])
        walker = only_oid(game, "t_walker", 0)
        before = library(game, 0)
        declare_attack(game, {a: ("player", 0), b: ("object", walker)})
        settle(game)
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
        settle(game)

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
        settle(game)

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
        settle(game)
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
        lines = [
            a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND and a.second_face
        ]
        assert lines
        card = lines[0].source
        game.apply(lines[0])
        while (p := game.pending()) is not None and p.kind is not DecisionKind.PRIORITY:
            game.apply(_default_answer(game, p))  # decline the 3 life
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
        settle(game)

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
        settle(game)
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
        settle(game)

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
        settle(game)
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
        settle(game)
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
        settle(game)

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
        settle(game)
        assert len(tokens(game, "human_soldier_1_1_w", 0)) == 1

    def test_both_opponents_count_all_four(self, builder):
        game = self.position(builder, 5)
        action = next(a for a in self.lines(game) if len(a.targets) == 2)
        game.apply(action)
        settle(game)
        assert len(tokens(game, "human_soldier_1_1_w", 0)) == 4


# ----------------------------------------------------------------------
# the rest of the deck, where the gate could not reach the printed text
# ----------------------------------------------------------------------


def castable(game, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


def resolve_answering(game, answer) -> None:
    """Settle the stack, handing every non-priority decision to ``answer``."""
    for _ in range(200):
        p = game.pending()
        if p is None or (p.kind is DecisionKind.PRIORITY and not game.state.stack):
            return
        if p.kind is DecisionKind.PRIORITY:
            game.apply(_default_answer(game, p))
        else:
            game.apply(answer(game, p))
    raise AssertionError("the stack never settled")


def say_yes(game, p):
    if p.kind is DecisionKind.MAY:
        return next(a for a in game.legal_actions() if a.kind is ActionKind.YES)
    return _default_answer(game, p)


class TestAbandonedAirTemple:
    """"This land enters tapped unless you control a basic land." / "{3}{W}, {T}: Put
    a +1/+1 counter on each creature you control." """

    def test_the_counters_go_on_each_creature_you_control_only(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["abandoned_air_temple", BEAR, "grizzly_bears"] + ["plains"] * 4)
            .battlefield(1, [BEAR])
            .build()
        )
        activate(game, only_oid(game, "abandoned_air_temple", 0), 1)
        assert game.state.objects[only_oid(game, BEAR, 0)].counters.get("+1/+1") == 1
        assert game.state.objects[only_oid(game, "grizzly_bears", 0)].counters.get("+1/+1") == 1
        assert not game.state.objects[only_oid(game, BEAR, 1)].counters.get("+1/+1")

    def played(self, builder, board) -> bool:
        game = builder(players=2).battlefield(0, board).hand(0, ["abandoned_air_temple"]).build()
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "abandoned_air_temple"))
        return game.state.objects[only_oid(game, "abandoned_air_temple", 0)].tapped

    def test_it_enters_untapped_beside_a_basic_land(self, builder):
        assert not self.played(builder, ["plains"])

    def test_it_enters_tapped_without_one(self, builder):
        """A nonbasic land is not a basic land."""
        assert self.played(builder, ["floodfarm_verge"])


class TestAlandraSkyDreamer:
    """"Whenever you draw your second card each turn, create a 2/2 blue Drake creature
    token with flying." / "Whenever you draw your fifth card each turn, Alandra and
    Drakes you control each get +X/+X until end of turn, where X is the number of
    cards in your hand." """

    def position(self, builder, hand):
        return (
            builder(players=2)
            .battlefield(0, ["alandra_sky_dreamer", BEAR] + ["plains"] * 3 + ["island"] * 3)
            .hand(0, hand)
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_the_second_card_makes_one_drake(self, builder):
        game = self.position(builder, [DRAW_TWO])
        cast(game, DRAW_TWO)
        [drake] = tokens(game, "drake_2_2_u_flying", 0)
        assert "flying" in {str(k) for k in chars(game.state, drake.oid).keywords}

    def test_the_fifth_card_pumps_alandra_and_drakes_by_hand_size(self, builder):
        game = self.position(builder, ["secret_rendezvous", DRAW_TWO])
        alandra, bear = only_oid(game, "alandra_sky_dreamer", 0), only_oid(game, BEAR, 0)
        cast(game, "secret_rendezvous")
        assert len(tokens(game, "drake_2_2_u_flying", 0)) == 1, "only the second card, once"
        cast(game, DRAW_TWO)

        assert len(game.state.players[0].hand) == 5
        [drake] = tokens(game, "drake_2_2_u_flying", 0)
        assert (chars(game.state, alandra).power, chars(game.state, alandra).toughness) == (7, 9)
        assert chars(game.state, drake.oid).power == 7
        assert chars(game.state, bear).power == 2, "a Bear is not a Drake"


class TestArchaeomancersMap:
    """"Whenever a land an opponent controls enters, if that player controls more lands
    than you, you may put a land card from your hand onto the battlefield." """

    def position(self, builder, their_lands: int):
        return (
            builder(players=2)
            .battlefield(0, ["archaeomancer_s_map", "plains", "plains"])
            .hand(0, ["island", ANCHOR])
            .battlefield(1, ["plains"] * their_lands)
            .hand(1, ["plains", ANCHOR])
            .active(1)
            .build()
        )

    def play_their_land(self, game) -> None:
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 1)
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "plains"))
        resolve_answering(game, say_yes)

    def test_falling_behind_puts_a_land_from_hand_onto_the_battlefield(self, builder):
        game = self.position(builder, their_lands=2)
        self.play_their_land(game)
        assert count_on_battlefield(game, "island", 0) == 1

    def test_drawing_level_does_not(self, builder):
        """Two lands to their three would; one to two ties, and "more" is not a tie."""
        game = self.position(builder, their_lands=1)
        self.play_their_land(game)
        assert count_on_battlefield(game, "island", 0) == 0


class TestAshnodsAltar:
    """"Sacrifice a creature: Add {C}{C}." """

    def test_sacrificing_a_creature_adds_two_colorless(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["ashnod_s_altar", BEAR, "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        altar, bear = only_oid(game, "ashnod_s_altar", 0), only_oid(game, BEAR, 0)
        game.apply(activations(game, altar)[0])
        while (p := game.pending()) is not None and p.kind is not DecisionKind.PRIORITY:
            game.apply(_default_answer(game, p))

        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert game.state.players[0].mana_pool.total() == 2

    def test_no_creature_no_mana(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["ashnod_s_altar", "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        assert not activations(game, only_oid(game, "ashnod_s_altar", 0))


class TestAustereCommand:
    """"Choose two — • Destroy all artifacts. • Destroy all enchantments. • Destroy all
    creatures with mana value 3 or less. • Destroy all creatures with mana value 4 or
    greater."

    The gate takes the first two modes. The creature split is the other half.
    """

    def test_the_big_creature_mode_spares_the_small(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 6)
            .hand(0, ["austere_command"])
            .battlefield(1, [BEAR, "elesh_norn_grand_cenobite", "sol_ring", "cathars_crusade"])
            .build()
        )
        norn = only_oid(game, "elesh_norn_grand_cenobite", 1)
        ring, crusade = only_oid(game, "sol_ring", 1), only_oid(game, "cathars_crusade", 1)
        game.apply(action_for_card(game, ActionKind.CAST, "austere_command"))
        for mode in (1, 3):
            game.apply(
                next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == mode)
            )
        settle(game)

        assert norn not in game.state.battlefield, "mana value 7"
        assert crusade not in game.state.battlefield
        assert ring in game.state.battlefield, "artifacts were not chosen"
        # The Bear survives Norn's -2/-2 only because Norn died with it.
        assert count_on_battlefield(game, BEAR, 1) == 1, "mana value 2"

    def test_the_small_creature_mode_spares_the_big(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 6)
            .hand(0, ["austere_command"])
            .battlefield(1, [BEAR, "moonshaker_cavalry"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "austere_command"))
        for mode in (0, 2):
            game.apply(
                next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == mode)
            )
        settle(game)
        assert count_on_battlefield(game, BEAR, 1) == 0
        assert count_on_battlefield(game, "moonshaker_cavalry", 1) == 1


class TestCatharsCrusade:
    """"Whenever a creature you control enters, put a +1/+1 counter on each creature you
    control." """

    def test_a_creature_entering_grows_the_team_itself_included(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["cathars_crusade", "grizzly_bears", "forest", "forest"])
            .hand(0, [BEAR])
            .battlefield(1, ["t_five_five"])
            .build()
        )
        cast(game, BEAR)
        assert game.state.objects[only_oid(game, "grizzly_bears", 0)].counters.get("+1/+1") == 1
        assert game.state.objects[only_oid(game, BEAR, 0)].counters.get("+1/+1") == 1
        assert not game.state.objects[only_oid(game, "t_five_five", 1)].counters.get("+1/+1")

    def test_an_opponent_s_creature_entering_does_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["cathars_crusade", "grizzly_bears", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["forest", "forest"])
            .hand(1, [BEAR])
            .active(1)
            .build()
        )
        cast(game, BEAR, pid=1)
        assert not game.state.objects[only_oid(game, "grizzly_bears", 0)].counters.get("+1/+1")


class TestChivalricAlliance:
    """"Whenever you attack with two or more creatures, draw a card." / "{2}, Discard a
    card: Create a 2/2 white and blue Knight creature token with vigilance." """

    def attack(self, builder, bears: int) -> int:
        game = (
            builder(players=2)
            .battlefield(0, ["chivalric_alliance", "plains"] + [BEAR] * bears)
            .hand(0, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )
        pass_until(game, lambda g: g.state.step is Step.PRECOMBAT_MAIN)
        before = library(game, 0)
        declare_attack(game, {oid: ("player", 1) for oid in oids_of(game, BEAR, 0)})
        settle(game)
        return before - library(game, 0)

    def test_two_attackers_draw(self, builder):
        assert self.attack(builder, 2) == 1

    def test_one_attacker_does_not(self, builder):
        assert self.attack(builder, 1) == 0

    def test_discarding_makes_a_vigilant_knight(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["chivalric_alliance", "plains", "plains"])
            .hand(0, [BEAR])
            .build()
        )
        activate(game, only_oid(game, "chivalric_alliance", 0), 1)
        [knight] = tokens(game, "knight_2_2_wu_vigilance", 0)
        assert "vigilance" in {str(k) for k in chars(game.state, knight.oid).keywords}
        assert game.state.players[0].hand == [], "the Bear paid for it"

    def test_an_empty_hand_can_t_pay(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["chivalric_alliance", "plains", "plains"])
            .build(advance=False)
        )
        assert not activations(game, only_oid(game, "chivalric_alliance", 0), 1)


class TestDetectiveOfTheMonth:
    """"Ascend" / "As long as you have the city's blessing, Detectives you control can't
    be blocked." / "Whenever you draw your second card each turn, create a 2/2 white and
    blue Detective creature token." """

    def test_the_second_card_makes_a_detective(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["detective_of_the_month", "island", "island", "island"])
            .hand(0, [DRAW_TWO])
            .build()
        )
        cast(game, DRAW_TWO)
        assert len(tokens(game, "detective_2_2_wu", 0)) == 1

    def blockable(self, builder, permanents: int) -> bool:
        game = (
            builder(players=2)
            .battlefield(0, ["detective_of_the_month", "detective_2_2_wu", "plains"])
            .battlefield(0, ["plains"] * (permanents - 3))
            .hand(0, [ANCHOR])
            .battlefield(1, [BEAR, "plains"])
            .hand(1, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )
        detective = only_oid(game, "detective_2_2_wu", 0)
        declare_attack(game, {detective: ("player", 1)})
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.DECLARE_BLOCKERS,
        )
        return any(
            a.kind is ActionKind.ADD_BLOCKER and detective in [t.id for t in a.targets]
            for a in game.legal_actions()
        )

    def test_with_ten_permanents_detectives_can_t_be_blocked(self, builder):
        assert not self.blockable(builder, 10)

    def test_with_nine_they_can(self, builder):
        assert self.blockable(builder, 9)


class TestEleshNornGrandCenobite:
    """"Other creatures you control get +2/+2." / "Creatures your opponents control get
    -2/-2." """

    def test_mine_grow_theirs_shrink_and_a_two_two_dies(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["elesh_norn_grand_cenobite", BEAR])
            .battlefield(1, [BEAR, "t_five_five"])
            .hand(0, [ANCHOR])
            .battlefield(0, ["plains"])
            .build()
        )
        norn = only_oid(game, "elesh_norn_grand_cenobite", 0)
        assert (chars(game.state, norn).power, chars(game.state, norn).toughness) == (4, 7), "other"
        mine = only_oid(game, BEAR, 0)
        assert (chars(game.state, mine).power, chars(game.state, mine).toughness) == (4, 4)
        five = only_oid(game, "t_five_five", 1)
        assert (chars(game.state, five).power, chars(game.state, five).toughness) == (3, 3)
        assert count_on_battlefield(game, BEAR, 1) == 0, "0 toughness, put into the graveyard"


class TestEmrakulsMessenger:
    """"Whenever you draw your second card each turn, create a 0/1 colorless Eldrazi
    Spawn creature token with "Sacrifice this token: Add {C}."" """

    def test_the_second_card_makes_a_spawn_and_the_third_does_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["emrakul_s_messenger"] + ["island"] * 3 + ["plains"] * 3)
            .hand(0, ["secret_rendezvous"])
            .build()
        )
        cast(game, "secret_rendezvous")
        assert len(tokens(game, "eldrazi_spawn_0_1_c", 0)) == 1


class TestFlawlessManeuver:
    """"If you control a commander, you may cast this spell without paying its mana
    cost." """

    def position(self, builder, commander: bool):
        game = (
            builder(players=2)
            .battlefield(0, ["bard_king_of_dale"])
            .hand(0, ["flawless_maneuver"])
            .build(advance=False)
        )
        bard = only_oid(game, "bard_king_of_dale", 0)
        if commander:
            game.state.objects[bard].is_commander = True
            game.state.players[0].commanders.append(bard)
        game.state.bump_chars()
        game._advance()
        return game

    def test_with_the_commander_out_it_is_free(self, builder):
        assert castable(self.position(builder, commander=True), "flawless_maneuver")

    def test_the_same_creature_not_a_commander_does_not_pay_for_it(self, builder):
        assert not castable(self.position(builder, commander=False), "flawless_maneuver")


class TestFloodfarmVerge:
    """"{T}: Add {W}." / "{T}: Add {U}. Activate only if you control a Plains or an
    Island." """

    def position(self, builder, other: str | None):
        b = builder(players=2).battlefield(0, ["floodfarm_verge"]).hand(0, ["brainstorm", ANCHOR])
        if other:
            b = b.battlefield(0, [other], tapped=True)
        game = b.build()
        assert game.state.active_player == 0 and game.state.turn == 1, "stopped on my turn"
        return game

    def test_beside_a_plains_it_makes_blue(self, builder):
        """A tapped Plains pays nothing, but it is still a Plains you control."""
        assert castable(self.position(builder, "plains"), "brainstorm")

    def test_alone_it_makes_only_white(self, builder):
        game = self.position(builder, None)
        assert castable(game, ANCHOR)
        assert not castable(game, "brainstorm")


class TestGildedLotus:
    """"{T}: Add three mana of any one color." """

    def position(self, builder, spell: str):
        game = builder(players=2).battlefield(0, ["gilded_lotus"]).hand(0, [spell, ANCHOR]).build()
        assert game.state.active_player == 0 and game.state.turn == 1, "stopped on my turn"
        return game

    def test_it_pays_a_three_mana_blue_spell_alone(self, builder):
        assert castable(self.position(builder, DRAW_TWO), DRAW_TWO)

    def test_not_two_colours_at_once(self, builder):
        """"Any **one** color": {W}{U} is out of reach."""
        game = self.position(builder, "t_nth_draw_you")
        assert castable(game, ANCHOR), "white alone it makes"
        assert not castable(game, "t_nth_draw_you")


class TestHermesOverseerOfElpis:
    """"Whenever you cast a noncreature spell, create a 1/1 blue Bird creature token
    with flying and vigilance." / "Whenever you attack with one or more Birds, scry 2." """

    def test_a_noncreature_spell_makes_a_bird(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["hermes_overseer_of_elpis", "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        cast(game, ANCHOR)
        [bird] = tokens(game, "bird_1_1_u_flying_vigilance", 0)
        assert {"flying", "vigilance"} <= {str(k) for k in chars(game.state, bird.oid).keywords}

    def test_a_creature_spell_does_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["hermes_overseer_of_elpis", "forest", "forest"])
            .hand(0, [BEAR])
            .build()
        )
        cast(game, BEAR)
        assert tokens(game, "bird_1_1_u_flying_vigilance") == []

    def scries(self, builder, attacker: str) -> bool:
        game = (
            builder(players=2)
            .battlefield(0, ["hermes_overseer_of_elpis", attacker, "plains"])
            .hand(0, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )
        declare_attack(game, {only_oid(game, attacker, 0): ("player", 1)})
        pass_until(
            game,
            lambda g: not g.state.stack
            or (g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_OBJECTS),
        )
        p = game.pending()
        return p.kind is DecisionKind.CHOOSE_OBJECTS and len(p.options) == 2

    def test_attacking_with_a_bird_scries_two(self, builder):
        assert self.scries(builder, "bird_1_1_u_flying_vigilance")

    def test_attacking_with_a_non_bird_does_not(self, builder):
        assert not self.scries(builder, BEAR)


class TestLoranOfTheThirdPath:
    """"{T}: You and target opponent each draw a card." """

    def test_both_players_draw(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, ["loran_of_the_third_path"])
            .build()
        )
        loran = only_oid(game, "loran_of_the_third_path", 0)
        before = [library(game, p) for p in range(3)]
        lines = activations(game, loran)
        assert sorted(a.targets[0].id for a in lines) == [1, 2], "an opponent, not me"
        at_two = next(a for a in lines if a.targets[0].id == 2)
        game.apply(at_two)
        settle(game)
        assert [before[p] - library(game, p) for p in range(3)] == [1, 0, 1], "only the target"
        assert game.state.objects[loran].tapped


class TestLuminarchAscension:
    """"At the beginning of each opponent's end step, if you didn't lose life this turn,
    you may put a quest counter on this enchantment." / "{1}{W}: Create a 4/4 white
    Angel creature token with flying. Activate only if this enchantment has four or
    more quest counters on it." """

    def quest(self, builder, *, active: int, lose: bool = False) -> int:
        game = (
            builder(players=2)
            .battlefield(0, ["luminarch_ascension", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .active(active)
            .build()
        )
        if lose:
            from automtg.engine.primitives import lose_life

            lose_life(game.state, 0, 1)
        to_step(game, Step.END_STEP, active)
        resolve_answering(game, say_yes)
        return game.state.objects[only_oid(game, "luminarch_ascension", 0)].counters.get("quest", 0)

    def test_an_opponent_s_end_step_adds_a_quest_counter(self, builder):
        assert self.quest(builder, active=1) == 1

    def test_not_if_you_lost_life_this_turn(self, builder):
        assert self.quest(builder, active=1, lose=True) == 0

    def test_not_at_your_own_end_step(self, builder):
        assert self.quest(builder, active=0) == 0

    def angel_offered(self, builder, quest: int) -> bool:
        game = (
            builder(players=2)
            .battlefield(0, ["luminarch_ascension"], counters={"quest": quest})
            .battlefield(0, ["plains", "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        return bool(activations(game, only_oid(game, "luminarch_ascension", 0)))

    def test_four_counters_make_angels(self, builder):
        assert self.angel_offered(builder, 4)

    def test_three_do_not(self, builder):
        assert not self.angel_offered(builder, 3)


class TestMakindiStampede:
    """"Creatures you control get +2/+2 until end of turn." // Makindi Mesas: "This land
    enters tapped." """

    def test_the_pump_is_until_end_of_turn(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR] + ["plains"] * 5)
            .hand(0, ["makindi_stampede_makindi_mesas", ANCHOR])
            .battlefield(1, [BEAR, "plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        cast(game, "makindi_stampede_makindi_mesas")
        assert chars(game.state, mine).power == 4
        assert chars(game.state, theirs).power == 2, "creatures **you** control"
        pass_until(game, lambda g: g.state.active_player == 1)
        assert chars(game.state, mine).power == 2

    def test_the_back_face_is_a_tapped_land_drop(self, builder):
        game = builder(players=2).hand(0, ["makindi_stampede_makindi_mesas"]).build()
        line = next(
            a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND and a.second_face
        )
        game.apply(line)
        obj = game.state.objects[line.source]
        assert game.state.card_of(obj).id == "makindi_mesas"
        assert obj.tapped


class TestMinasTirith:
    """"Minas Tirith enters tapped unless you control a legendary creature." / "{1}{W},
    {T}: Draw a card. Activate only if you attacked with two or more creatures this
    turn." """

    def played_tapped(self, builder, board) -> bool:
        game = builder(players=2).battlefield(0, board).hand(0, ["minas_tirith"]).build()
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "minas_tirith"))
        return game.state.objects[only_oid(game, "minas_tirith", 0)].tapped

    def test_untapped_beside_a_legendary_creature(self, builder):
        assert not self.played_tapped(builder, ["bard_king_of_dale"])

    def test_tapped_beside_a_nonlegendary_one(self, builder):
        assert self.played_tapped(builder, [BEAR])

    def draw_offered_after_attacking_with(self, builder, bears: int) -> bool:
        game = (
            builder(players=2)
            .battlefield(0, ["minas_tirith", "plains", "plains"] + [BEAR] * bears)
            .hand(0, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )
        declare_attack(game, {oid: ("player", 1) for oid in oids_of(game, BEAR, 0)})
        pass_until(
            game,
            lambda g: g.state.step is Step.POSTCOMBAT_MAIN
            and g.pending() is not None
            and g.pending().player == 0,
        )
        return bool(activations(game, only_oid(game, "minas_tirith", 0), 1))

    def test_after_attacking_with_two_the_draw_is_offered(self, builder):
        assert self.draw_offered_after_attacking_with(builder, 2)

    def test_after_attacking_with_one_it_is_not(self, builder):
        assert not self.draw_offered_after_attacking_with(builder, 1)


class TestMischievousMystic:
    """"Whenever you draw your second card each turn, create a 1/1 blue Faerie creature
    token with flying." """

    def test_draw_two_makes_one_faerie(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["mischievous_mystic"] + ["island"] * 3 + ["plains"] * 3)
            .hand(0, ["secret_rendezvous"])
            .build()
        )
        cast(game, "secret_rendezvous")
        assert len(tokens(game, "faerie_1_1_u_flying", 0)) == 1, "the second card, not the third"


class TestMonasteryMentor:
    """"Prowess" / "Whenever you cast a noncreature spell, create a 1/1 white Monk
    creature token with prowess." """

    def test_each_spell_makes_a_monk_and_the_monks_have_prowess(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["monastery_mentor", "plains", "plains"])
            .hand(0, [ANCHOR, ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        mentor = only_oid(game, "monastery_mentor", 0)
        cast(game, ANCHOR)
        [monk] = tokens(game, "monk_1_1_w_prowess", 0)
        assert chars(game.state, mentor).power == 3, "prowess"
        assert chars(game.state, monk.oid).power == 1, "made after the spell was cast"

        cast(game, ANCHOR)
        assert len(tokens(game, "monk_1_1_w_prowess", 0)) == 2
        assert chars(game.state, monk.oid).power == 2, "the first Monk's own prowess"

    def test_a_creature_spell_or_an_opponent_s_spell_makes_none(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["monastery_mentor", "forest", "forest"])
            .hand(0, [BEAR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        cast(game, BEAR)
        cast(game, ANCHOR, pid=1)
        assert tokens(game, "monk_1_1_w_prowess") == []
        assert chars(game.state, only_oid(game, "monastery_mentor", 0)).power == 2


class TestMoonshakerCavalry:
    """"When this creature enters, creatures you control gain flying and get +X/+X
    until end of turn, where X is the number of creatures you control." """

    def test_x_counts_the_team_including_itself(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, BEAR] + ["plains"] * 8)
            .hand(0, ["moonshaker_cavalry"])
            .battlefield(1, [BEAR, "plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        cast(game, "moonshaker_cavalry")
        bear = oids_of(game, BEAR, 0)[0]
        cavalry = only_oid(game, "moonshaker_cavalry", 0)
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (5, 5)
        assert chars(game.state, cavalry).power == 9
        assert chars(game.state, only_oid(game, BEAR, 1)).power == 2, "not theirs"


class TestNadirKraken:
    """"Whenever you draw a card, you may pay {1}. If you do, put a +1/+1 counter on
    this creature and create a 1/1 blue Tentacle creature token." """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["nadir_kraken"] + ["island"] * 5)
            .hand(0, [DRAW_TWO])
            .build()
        )

    def test_paying_for_each_card_grows_it_twice(self, builder):
        game = self.position(builder)
        kraken = only_oid(game, "nadir_kraken", 0)
        game.apply(action_for_card(game, ActionKind.CAST, DRAW_TWO))
        resolve_answering(game, say_yes)
        assert game.state.objects[kraken].counters.get("+1/+1") == 2
        assert len(tokens(game, "tentacle_1_1_u", 0)) == 2

    def test_declining_does_nothing(self, builder):
        game = self.position(builder)
        cast(game, DRAW_TWO)
        assert not game.state.objects[only_oid(game, "nadir_kraken", 0)].counters.get("+1/+1")
        assert tokens(game, "tentacle_1_1_u") == []


class TestNimbusMaze:
    """"{T}: Add {W}. Activate only if you control an Island." / "{T}: Add {U}. Activate
    only if you control a Plains." """

    def position(self, builder, other: str | None):
        # Ornithopter costs {0}: something castable keeps the turn from auto-passing
        # away on the board that makes no coloured mana at all.
        b = (
            builder(players=2)
            .battlefield(0, ["nimbus_maze"])
            .hand(0, ["brainstorm", ANCHOR, "ornithopter"])
        )
        if other:
            b = b.battlefield(0, [other], tapped=True)
        game = b.build()
        assert game.state.active_player == 0 and game.state.turn == 1, "stopped on my turn"
        return game

    def test_alone_it_makes_neither_colour(self, builder):
        game = self.position(builder, None)
        assert not castable(game, "brainstorm")
        assert not castable(game, ANCHOR)

    def test_an_island_unlocks_white_not_blue(self, builder):
        game = self.position(builder, "island")
        assert castable(game, ANCHOR)
        assert not castable(game, "brainstorm")

    def test_a_plains_unlocks_blue_not_white(self, builder):
        game = self.position(builder, "plains")
        assert castable(game, "brainstorm")
        assert not castable(game, ANCHOR)


class TestSecretRendezvous:
    """"You and target opponent each draw three cards." """

    def test_only_the_targeted_opponent_draws(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, ["plains"] * 3)
            .hand(0, ["secret_rendezvous"])
            .build()
        )
        before = [library(game, p) for p in range(3)]
        cast(game, "secret_rendezvous", targets=next(
            a.targets
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and [t.id for t in a.targets] == [2]
        ))
        assert [before[p] - library(game, p) for p in range(3)] == [3, 0, 3]


class TestSicarianInfiltrator:
    """"Squad {2} (… you may pay {2} any number of times. When this creature enters,
    create that many tokens that are copies of it.)" / "When this creature enters, draw
    a card." """

    def test_squad_twice_makes_two_copies_and_each_draws(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 7)
            .hand(0, ["sicarian_infiltrator"])
            .build()
        )
        before = library(game, 0)
        cast(game, "sicarian_infiltrator", additional_times=2)
        assert count_on_battlefield(game, "sicarian_infiltrator", 0) == 3
        assert len(tokens(game, "sicarian_infiltrator", 0)) == 2
        assert before - library(game, 0) == 3, "the copies have the enters trigger too"

    def test_unpaid_it_is_one_creature(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 7)
            .hand(0, ["sicarian_infiltrator"])
            .build()
        )
        cast(game, "sicarian_infiltrator", additional_times=0)
        assert count_on_battlefield(game, "sicarian_infiltrator", 0) == 1


class TestTataruTaru:
    """"When Tataru Taru enters, you draw a card and target opponent may draw a card." /
    "Whenever an opponent draws a card, if it isn't that player's turn, create a tapped
    Treasure token. This ability triggers only once each turn." """

    def test_an_opponent_drawing_on_my_turn_makes_one_treasure(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["tataru_taru", "plains", "plains", "plains"])
            .hand(0, ["secret_rendezvous"])
            .build()
        )
        cast(game, "secret_rendezvous")
        treasures = tokens(game, "treasure_token", 0)
        assert len(treasures) == 1, "three cards, once each turn"
        assert treasures[0].tapped

    def test_an_opponent_drawing_on_their_own_turn_makes_none(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["tataru_taru", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["island"] * 3)
            .hand(1, [DRAW_TWO])
            .active(1)
            .build()
        )
        cast(game, DRAW_TWO, pid=1)
        assert tokens(game, "treasure_token") == []

    def test_the_opponent_may_draw_when_it_enters(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", "plains"])
            .hand(0, ["tataru_taru"])
            .build()
        )
        before = library(game, 1)
        game.apply(action_for_card(game, ActionKind.CAST, "tataru_taru"))
        asked = []

        def answer(g, p):
            asked.append(p.player)
            return say_yes(g, p)

        resolve_answering(game, answer)
        assert before - library(game, 1) == 1
        assert 1 in asked, "the opponent is the one who may"


class TestThopterFabricator:
    """"Whenever you draw your second card each turn, create a 1/1 colorless Thopter
    artifact creature token with flying." / "Crew 2" """

    def test_the_second_card_makes_a_thopter(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["thopter_fabricator", "island", "island", "island"])
            .hand(0, [DRAW_TWO])
            .build()
        )
        cast(game, DRAW_TWO)
        [thopter] = tokens(game, "thopter_1_1_c_flying", 0)
        assert "Artifact" in {str(t) for t in chars(game.state, thopter.oid).types}

    def test_a_bear_crews_it_into_a_creature(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["thopter_fabricator", BEAR, "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        fabricator = only_oid(game, "thopter_fabricator", 0)
        assert "Creature" not in {str(t) for t in chars(game.state, fabricator).types}
        game.apply(activations(game, fabricator, 1)[0])
        resolve_answering(game, _default_answer)
        assert "Creature" in {str(t) for t in chars(game.state, fabricator).types}
        assert game.state.objects[only_oid(game, BEAR, 0)].tapped

    def test_a_one_one_cannot(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["thopter_fabricator", "t_dork", "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        assert not activations(game, only_oid(game, "thopter_fabricator", 0), 1)


class TestWillOfTheMardu:
    """"Choose one. If you control a commander as you cast this spell, you may choose
    both instead." """

    def modes_allowed(self, builder, commander: bool) -> int:
        game = (
            builder(players=2)
            .battlefield(0, ["bard_king_of_dale"] + ["plains"] * 3)
            .hand(0, ["will_of_the_mardu"])
            .battlefield(1, [BEAR])
            .build(advance=False)
        )
        if commander:
            bard = only_oid(game, "bard_king_of_dale", 0)
            game.state.objects[bard].is_commander = True
            game.state.players[0].commanders.append(bard)
        game.state.bump_chars()
        game._advance()
        game.apply(action_for_card(game, ActionKind.CAST, "will_of_the_mardu"))
        p = game.pending()
        assert p.kind is DecisionKind.CHOOSE_MODE
        return p.max_count

    def test_with_a_commander_both(self, builder):
        assert self.modes_allowed(builder, commander=True) == 2

    def test_without_one_only_one(self, builder):
        assert self.modes_allowed(builder, commander=False) == 1


class TestWitchEnchanter:
    """"When this creature enters, destroy target artifact or enchantment an opponent
    controls." // Witch-Blessed Meadow: "As this land enters, you may pay 3 life. If you
    don't, it enters tapped." """

    def test_my_own_artifact_is_not_a_target(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["sol_ring"] + ["plains"] * 4)
            .hand(0, ["witch_enchanter_witch_blessed_meadow"])
            .battlefield(1, ["cathars_crusade"])
            .build()
        )
        cast(game, "witch_enchanter_witch_blessed_meadow")
        assert count_on_battlefield(game, "sol_ring", 0) == 1
        assert count_on_battlefield(game, "cathars_crusade", 1) == 0

    def test_paying_three_life_the_meadow_enters_untapped(self, builder):
        game = builder(players=2).hand(0, ["witch_enchanter_witch_blessed_meadow"]).build()
        line = next(
            a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND and a.second_face
        )
        game.apply(line)
        resolve_answering(game, say_yes)
        obj = game.state.objects[line.source]
        assert game.state.card_of(obj).id == "witch_blessed_meadow"
        assert not obj.tapped
        assert game.state.players[0].life == 37


class TestCaretakersTalent:
    """"Whenever one or more tokens you control enter, draw a card. This ability
    triggers only once each turn." / "{W}: Level 2" / "When this Class becomes level 2,
    create a token that's a copy of target token you control." / "{3}{W}: Level 3" /
    "Creature tokens you control get +2/+2."

    The gate cast it at level 1 into a sandbox where no token entered afterwards, and
    never bought a level.
    """

    LEVEL_2, LEVEL_3 = 1, 3
    ILLUSION = "illusion_1_1_u"

    def position(self, builder, *, level: int = 1, active: int = 0):
        game = (
            builder(players=2)
            .battlefield(0, ["caretaker_s_talent"], level=level)
            .battlefield(0, [self.ILLUSION, BEAR] + ["plains"] * 4)
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .active(active)
            .build(advance=False)
        )
        # Placed rather than created, so the builder does not know it is a token.
        game.state.objects[only_oid(game, self.ILLUSION, 0)].is_token = True
        game.state.bump_chars()
        game._advance()
        return game, only_oid(game, "caretaker_s_talent", 0)

    def test_two_token_creations_in_a_turn_draw_once(self, builder):
        """Hermes makes a Bird on each of two spells: two batches, one card."""
        game = (
            builder(players=2)
            .battlefield(0, ["caretaker_s_talent", "hermes_overseer_of_elpis", "plains", "plains"])
            .hand(0, [ANCHOR, ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        before = library(game, 0)
        cast(game, ANCHOR)
        assert before - library(game, 0) == 1
        cast(game, ANCHOR)
        assert len(tokens(game, "bird_1_1_u_flying_vigilance", 0)) == 2
        assert before - library(game, 0) == 1, "only once each turn"

    def test_a_nontoken_creature_entering_draws_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["caretaker_s_talent", "forest", "forest"])
            .hand(0, [BEAR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        before = library(game, 0)
        cast(game, BEAR)
        assert library(game, 0) == before

    def test_level_two_is_offered_at_level_one_only(self, builder):
        game, talent = self.position(builder)
        assert activations(game, talent, self.LEVEL_2)
        game, talent = self.position(builder, level=2)
        assert not activations(game, talent, self.LEVEL_2)

    def test_level_two_is_not_offered_at_instant_speed(self, builder):
        game, talent = self.position(builder, active=1)
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 0)
        assert game.state.active_player == 1
        assert not activations(game, talent, self.LEVEL_2)

    def test_level_three_is_not_offered_at_level_one(self, builder):
        """A ladder: level 3 is bought from level 2, not skipped to."""
        game, talent = self.position(builder)
        assert not activations(game, talent, self.LEVEL_3)

    def test_becoming_level_two_copies_a_token_and_level_three_does_not_again(self, builder):
        game, talent = self.position(builder)
        activate(game, talent, self.LEVEL_2)
        assert game.state.objects[talent].class_level == 2
        assert len(tokens(game, self.ILLUSION, 0)) == 2, "the Illusion and its copy"
        assert count_on_battlefield(game, BEAR, 0) == 1, "a token, not the Bear"

        pass_until(game, lambda g: g.state.active_player == 1)
        pass_until(
            game,
            lambda g: g.state.active_player == 0
            and g.state.step is Step.PRECOMBAT_MAIN
            and g.pending() is not None
            and g.pending().player == 0,
        )
        activate(game, talent, self.LEVEL_3)
        assert game.state.objects[talent].class_level == 3
        assert len(tokens(game, self.ILLUSION, 0)) == 2, "level 2's trigger does not fire again"

    def test_at_level_three_creature_tokens_get_two(self, builder):
        game, _ = self.position(builder, level=3)
        illusion, bear = only_oid(game, self.ILLUSION, 0), only_oid(game, BEAR, 0)
        assert (chars(game.state, illusion).power, chars(game.state, illusion).toughness) == (3, 3)
        assert chars(game.state, bear).power == 2, "a nontoken creature is not buffed"

    def test_below_level_three_they_do_not(self, builder):
        game, _ = self.position(builder, level=2)
        assert chars(game.state, only_oid(game, self.ILLUSION, 0)).power == 1
