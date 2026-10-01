"""The Atraxa, Praetors' Voice superfriends deck: its walkers A to J, doing what they print.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card **once**, in one
fixed sandbox, and reads the board. For a planeswalker that is almost nothing:

- **It never activates an ability.** A walker *is* its loyalty abilities, so
  the recorded expectation for each of the fifteen cards below is "it entered
  with its printed loyalty". Every +N, 0 and -N here is activated for the first
  time in this file, and each test asserts both the effect and the loyalty it
  cost.
- **A duration that outlives the turn cannot be seen.** Dovin Baan's and
  Gideon of the Trials' "until your next turn" have to survive the opponent's
  whole turn and end at their controller's next one; Gideon Jura's +2 bites
  only during the opponent's turn. None of that exists in a sandbox that stops
  after one resolution.
- **An emblem is a later turn's card.** Each one is asserted doing its job
  after it was made -- and, where it has a condition, stopping when the
  condition stops (Gideon of the Trials with no Gideon left).
- **Linked abilities** (607) need two activations: Ashiok, Nightmare Weaver's
  -X can only find what *its own* +2 exiled.

Each class is one card and pins the near miss too: the reading that would be
wrong if the card had been written the other way.

**Why every position holds an `ANCHOR`.** With no play available to anybody the
engine's auto-pass runs whole turns inside a single `apply`, and an "until your
next turn" or an end-of-turn pump would be gone before it could be read. A
castable instant in each seat's hand is a reason for priority to stop.
"""

from __future__ import annotations

from automtg.engine import combat as combat_mod
from automtg.engine import legality, sba
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.player_statics import search_forbidden
from automtg.engine.sba import player_cant_lose, player_cant_win
from automtg.engine.zones import move_object
from tests.conftest import (
    _default_answer,
    find_action,
    only_oid,
    pass_until,
)

PLAINS = "plains"
ANCHOR = "t_plain_instant"  # {W}, gain 1 life -- a reason for priority to stop
BEAR = "t_bear"  # {1}{G} 2/2 vanilla, mana value 2
GIANT = "hill_giant"  # {3}{R} 3/3 vanilla, mana value 4
ANGEL = "serra_angel"  # {3}{W}{W} 4/4 flier, power exactly 4
BIG = "t_big"  # {5}{G} 6/6 vanilla
OFFICER = "recruitment_officer"  # {W} 2/1 with a {3}{W} activated ability
WALKER = "t_walker"  # a loyalty-4 walker with no static, the "other planeswalker"
PUMP = "t_pump_spell"  # {G} instant, "Target creature gets +3/+3" -- a targeting spell
DRAW_TWO = "divination"  # {2}{U} sorcery -- a noncreature spell
RAMP = "rampant_growth"  # {1}{G} sorcery that searches its caster's library
SOLDIER = "soldier_1_1_w"
ILLUSION = "illusion_2_2_u_sac_when_targeted"


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def settle(game) -> None:
    """Pass until the stack is empty and nothing is waiting to go on it."""
    pass_until(
        game,
        lambda g: (
            not g.state.stack
            and not g.state.pending_triggers
            and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY)
        ),
    )


def board(
    builder,
    walker: str | None,
    *,
    mine=(),
    theirs=(),
    loyalty: int | None = None,
    hand0=(),
    hand1=(),
    lib0=None,
    lib1=None,
    grave0=(),
    grave1=(),
    lands0: int = 1,
    lands1: int = 1,
    tapped0=(),
    tapped1=(),
    active: int = 0,
    step: Step = Step.PRECOMBAT_MAIN,
    max_turns: int = 6,
):
    """Player 0 holds ``walker``; both seats hold an anchor and a land to cast it."""
    b = builder(players=2)
    if walker is not None:
        b = b.battlefield(0, [walker], counters={"loyalty": loyalty} if loyalty else None)
    b = (
        b.battlefield(0, [*mine, *[PLAINS] * lands0])
        .battlefield(1, [*theirs, *[PLAINS] * lands1])
        .battlefield(0, list(tapped0), tapped=True)
        .battlefield(1, list(tapped1), tapped=True)
        .hand(0, [ANCHOR, *hand0])
        .hand(1, [ANCHOR, *hand1])
        .graveyard(0, list(grave0))
        .graveyard(1, list(grave1))
        .library(0, list(lib0) if lib0 is not None else [PLAINS] * 20)
        .library(1, list(lib1) if lib1 is not None else [PLAINS] * 20)
        .active(active)
        .step(step)
        .max_turns(max_turns)
    )
    game = b.build()
    oid = only_oid(game, walker, 0) if walker is not None else None
    return game, oid


def activations(game, oid: int, index: int | None = None) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and a.source == oid
        and (index is None or a.ability_index == index)
    ]


def activate(game, oid: int, index: int, *, targets=None, x: int | None = None, finish=True):
    """Activate ability ``index`` of ``oid``, at ``targets`` (ids) if given."""
    lines = activations(game, oid, index)
    assert lines, f"ability {index} was not offered"
    if targets is not None:
        lines = [a for a in lines if sorted(t.id for t in a.targets) == sorted(targets)]
        assert lines, f"ability {index} was not offered at {targets}"
    if x is not None and any(a.x for a in lines):
        lines = [a for a in lines if a.x == x]
    game.apply(lines[0])
    if x is not None and game.pending() is not None and game.pending().kind is DecisionKind.CHOOSE_X:
        game.apply(find_action(game, ActionKind.CHOOSE, choice=x))
    if finish:
        settle(game)


def answer(game, *, yes: bool = False, pick: bool = False, limit: int = 200) -> None:
    """Let the stack empty, optionally saying yes and choosing rather than declining."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if yes and decision.kind is DecisionKind.MAY:
            game.apply(find_action(game, ActionKind.YES))
            continue
        if pick and decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choice = next((a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None)
            if choice is not None:
                game.apply(choice)
                continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def cast(
    game, card_id: str, pid: int = 0, *, target: int | None = None, pick: bool = False, **match
) -> int:
    """Cast ``card_id`` from ``pid``'s hand and let everything resolve."""
    pass_until(
        game,
        lambda g: (
            g.pending() is not None
            and g.pending().player == pid
            and any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == card_id
                for a in g.legal_actions()
            )
        ),
    )
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
        and (target is None or [t.id for t in a.targets] == [target])
        and all(getattr(a, k) == v for k, v in match.items())
    )
    game.apply(action)
    if pick:
        answer(game, pick=True)
    else:
        settle(game)
    return action.source


def loyalty(game, oid: int) -> int:
    return game.state.objects[oid].counter("loyalty")


def pt(game, oid: int) -> tuple[int, int]:
    c = chars(game.state, oid)
    return c.power, c.toughness


def keywords(game, oid: int) -> set[str]:
    return {str(k) for k in chars(game.state, oid).keywords}


def tokens(game, def_id: str, pid: int | None = 0) -> list:
    return [o for o in game.state.battlefield_objects(pid) if o.def_id == def_id and o.is_token]


def zone_ids(game, pid: int, zone: str) -> list[str]:
    return [game.state.objects[o].def_id for o in getattr(game.state.players[pid], zone)]


def to_step(game, step: Step, active: int) -> None:
    pass_until(game, lambda g: g.state.step is step and g.state.active_player == active)


def declare_attackers(game, attacks: dict[int, tuple[str, int]]) -> None:
    """Declare each attacker at ``("player", pid)`` or ``("object", walker)``, and close."""
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
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def declare_blockers(game, blocks: dict[int, int]) -> None:
    """Block ``attacker`` with ``blocker`` for each ``blocker: attacker``, and close."""
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().kind is DecisionKind.DECLARE_BLOCKERS,
    )
    for blocker, attacker in blocks.items():
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_BLOCKER
                and a.source == blocker
                and any(t.id == attacker for t in a.targets)
            )
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def emblems(game, pid: int) -> int:
    return len(game.state.players[pid].command)


# ----------------------------------------------------------------------
# Ajani
# ----------------------------------------------------------------------


class TestAjaniSteadfast:
    """+1: up to one target creature gets +1/+1 and first strike, vigilance and
    lifelink until end of turn. -2: a +1/+1 counter on each creature you control
    and a loyalty counter on each **other** planeswalker you control. -7: an
    emblem preventing all but 1 of the damage to you or a planeswalker you control.
    """

    def test_plus_one_pumps_and_grants_three_keywords(self, builder):
        game, ajani = board(builder, "ajani_steadfast", mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        activate(game, ajani, 0, targets=[bear])

        assert pt(game, bear) == (3, 3)
        assert {"first_strike", "vigilance", "lifelink"} <= keywords(game, bear)
        assert loyalty(game, ajani) == 5

    def test_the_pump_ends_with_the_turn(self, builder):
        """ "Until end of turn" -- by the opponent's turn the Bear is a 2/2 again."""
        game, ajani = board(builder, "ajani_steadfast", mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        activate(game, ajani, 0, targets=[bear])
        to_step(game, Step.UPKEEP, 1)

        assert pt(game, bear) == (2, 2)
        assert not {"first_strike", "vigilance", "lifelink"} & keywords(game, bear)

    def test_plus_one_needs_no_target(self, builder):
        """ "**Up to one**" -- an empty board still gains loyalty."""
        game, ajani = board(builder, "ajani_steadfast")
        activate(game, ajani, 0, targets=[])

        assert loyalty(game, ajani) == 5

    def test_minus_two_counters_your_creatures_and_your_other_walkers(self, builder):
        game, ajani = board(builder, "ajani_steadfast", mine=[BEAR, WALKER], theirs=[BEAR, WALKER])
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        my_walker, their_walker = only_oid(game, WALKER, 0), only_oid(game, WALKER, 1)
        activate(game, ajani, 1)

        assert game.state.objects[mine].counters.get("+1/+1") == 1
        assert loyalty(game, my_walker) == 5
        assert loyalty(game, ajani) == 2, "'each **other** planeswalker' -- not himself"
        assert game.state.objects[theirs].counters.get("+1/+1") is None
        assert loyalty(game, their_walker) == 4, "'you control'"

    def test_minus_seven_emblem_caps_damage_to_you_and_your_walkers_at_one(self, builder):
        """A 6/6 at your face and a 6/6 at your walker each deal exactly 1."""
        game, ajani = board(
            builder, "ajani_steadfast", loyalty=7, mine=[WALKER], theirs=[BIG, BIG], max_turns=4
        )
        my_walker = only_oid(game, WALKER, 0)
        big_a, big_b = [o.oid for o in game.state.battlefield_objects(1) if o.def_id == BIG]
        activate(game, ajani, 2)
        assert emblems(game, 0) == 1
        assert game.state.objects[ajani].zone is Zone.GRAVEYARD, "7 - 7 is 0"

        declare_attackers(game, {big_a: ("player", 0), big_b: ("object", my_walker)})
        to_step(game, Step.END_STEP, 1)

        assert game.state.players[0].life == 39
        assert loyalty(game, my_walker) == 3

    def test_the_emblem_does_not_protect_the_opponent(self, builder):
        """ "...deal damage to **you**" -- my Bear's 2 at their face is 2."""
        game, ajani = board(builder, "ajani_steadfast", loyalty=7, mine=[BEAR], max_turns=4)
        bear = only_oid(game, BEAR, 0)
        activate(game, ajani, 2)
        declare_attackers(game, {bear: ("player", 1)})
        to_step(game, Step.END_STEP, 0)

        assert game.state.players[1].life == 38


class TestAjaniUnyielding:
    """+2: reveal the top three; every nonland permanent card to hand, the rest to
    the bottom. -2: exile target creature, **its controller** gains life equal to
    its power. -9: five +1/+1 counters on each creature you control and five
    loyalty on each other planeswalker you control.
    """

    def test_plus_two_takes_every_nonland_permanent_of_the_top_three(self, builder):
        game, ajani = board(
            builder,
            "ajani_unyielding",
            lib0=[BEAR, PLAINS, "sol_ring", "island", *[PLAINS] * 6],
        )
        activate(game, ajani, 0)

        assert sorted(zone_ids(game, 0, "hand")) == sorted([ANCHOR, BEAR, "sol_ring"])
        assert loyalty(game, ajani) == 6
        library = zone_ids(game, 0, "library")
        assert library[0] == "island", "the fourth card was never revealed"
        assert library[-1] == PLAINS and len(library) == 8, "the land went to the bottom"

    def test_an_instant_or_sorcery_is_not_a_permanent_card(self, builder):
        """ "nonland **permanent** cards" -- a Divination goes to the bottom."""
        game, ajani = board(
            builder, "ajani_unyielding", lib0=[DRAW_TWO, BEAR, PLAINS, *[PLAINS] * 6]
        )
        activate(game, ajani, 0)

        assert DRAW_TWO not in zone_ids(game, 0, "hand")
        assert BEAR in zone_ids(game, 0, "hand")
        assert DRAW_TWO in zone_ids(game, 0, "library")[-2:]

    def test_minus_two_exiles_and_its_controller_gains_the_life(self, builder):
        game, ajani = board(builder, "ajani_unyielding", theirs=[GIANT])
        giant = only_oid(game, GIANT, 1)
        activate(game, ajani, 1, targets=[giant])

        assert game.state.objects[giant].zone is Zone.EXILE
        assert game.state.players[1].life == 43, "the Giant's controller gains 3"
        assert game.state.players[0].life == 40, "not Ajani's controller"
        assert loyalty(game, ajani) == 2

    def test_minus_nine_five_counters_on_your_team_and_your_other_walkers(self, builder):
        game, ajani = board(
            builder, "ajani_unyielding", loyalty=9, mine=[BEAR, WALKER], theirs=[BEAR]
        )
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        my_walker = only_oid(game, WALKER, 0)
        activate(game, ajani, 2)

        assert game.state.objects[mine].counters.get("+1/+1") == 5
        assert loyalty(game, my_walker) == 9
        assert game.state.objects[theirs].counters.get("+1/+1") is None
        assert game.state.objects[ajani].zone is Zone.GRAVEYARD, "no counters for himself"


class TestAjaniSleeperAgent:
    """Compleated; +1: reveal the top card, a creature or planeswalker to hand,
    otherwise you may bottom it. -3: distribute three +1/+1 counters among up to
    three creatures, vigilance until end of turn. -6: an emblem -- whenever you
    cast a creature or planeswalker spell, target opponent gets two poison.
    """

    def in_hand(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["forest"] * 3 + [PLAINS] * 3)
            .battlefield(1, [PLAINS])
            .hand(0, ["ajani_sleeper_agent"])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_cast_with_mana_it_enters_with_four(self, builder):
        game = self.in_hand(builder)
        oid = cast(game, "ajani_sleeper_agent", phyrexian=0)

        assert loyalty(game, oid) == 4
        assert game.state.players[0].life == 40

    def test_cast_with_life_it_enters_with_two(self, builder):
        """Compleated: 2 life for the {G/W/P} costs two loyalty."""
        game = self.in_hand(builder)
        oid = cast(game, "ajani_sleeper_agent", phyrexian=1)

        assert loyalty(game, oid) == 2
        assert game.state.players[0].life == 38

    def test_plus_one_puts_a_creature_into_hand(self, builder):
        game, ajani = board(builder, "ajani_sleeper_agent", lib0=[BEAR, *[PLAINS] * 5])
        activate(game, ajani, 0)

        assert BEAR in zone_ids(game, 0, "hand")
        assert loyalty(game, ajani) == 5

    def test_plus_one_puts_a_planeswalker_into_hand(self, builder):
        game, ajani = board(builder, "ajani_sleeper_agent", lib0=[WALKER, *[PLAINS] * 5])
        activate(game, ajani, 0)

        assert WALKER in zone_ids(game, 0, "hand")

    def test_a_land_may_go_to_the_bottom(self, builder):
        game, ajani = board(builder, "ajani_sleeper_agent", lib0=["island", *[PLAINS] * 5])
        activate(game, ajani, 0, finish=False)
        answer(game, yes=True)

        assert zone_ids(game, 0, "hand") == [ANCHOR], "a land is not taken"
        assert zone_ids(game, 0, "library")[-1] == "island"

    def test_or_stay_on_top(self, builder):
        """ "you **may**" -- declined, the land is still the top card."""
        game, ajani = board(builder, "ajani_sleeper_agent", lib0=["island", *[PLAINS] * 5])
        activate(game, ajani, 0)

        assert zone_ids(game, 0, "library")[0] == "island"

    def test_minus_three_distributes_three_counters_and_vigilance(self, builder):
        game, ajani = board(builder, "ajani_sleeper_agent", mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        activate(game, ajani, 1, targets=[bear])

        assert game.state.objects[bear].counters.get("+1/+1") == 3
        assert "vigilance" in keywords(game, bear)
        assert loyalty(game, ajani) == 1

    def test_the_counters_stay_and_the_vigilance_ends(self, builder):
        game, ajani = board(builder, "ajani_sleeper_agent", mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        activate(game, ajani, 1, targets=[bear])
        to_step(game, Step.UPKEEP, 1)

        assert game.state.objects[bear].counters.get("+1/+1") == 3
        assert "vigilance" not in keywords(game, bear)

    def test_three_targets_one_counter_each(self, builder):
        game, ajani = board(builder, "ajani_sleeper_agent", mine=[BEAR, GIANT], theirs=[ANGEL])
        ids = [only_oid(game, BEAR, 0), only_oid(game, GIANT, 0), only_oid(game, ANGEL, 1)]
        activate(game, ajani, 1, targets=ids)

        assert [game.state.objects[o].counters.get("+1/+1") for o in ids] == [1, 1, 1]

    def test_the_emblem_poisons_on_a_creature_spell_and_not_on_a_sorcery(self, builder):
        game, ajani = board(
            builder,
            "ajani_sleeper_agent",
            loyalty=6,
            mine=["forest", "forest", "island", "island"],
            hand0=[BEAR, DRAW_TWO],
        )
        activate(game, ajani, 2)
        assert emblems(game, 0) == 1

        cast(game, DRAW_TWO)
        assert game.state.players[1].poison == 0

        cast(game, BEAR)
        assert game.state.players[1].poison == 2
        assert game.state.players[0].poison == 0


class TestAjaniTheGreathearted:
    """Creatures you control have vigilance. +1: gain 3 life. -2: a +1/+1 counter
    on each creature you control and a loyalty counter on each other walker."""

    def test_your_creatures_have_vigilance_and_theirs_do_not(self, builder):
        game, _ajani = board(builder, "ajani_the_greathearted", mine=[BEAR], theirs=[BEAR])

        assert "vigilance" in keywords(game, only_oid(game, BEAR, 0))
        assert "vigilance" not in keywords(game, only_oid(game, BEAR, 1))

    def test_plus_one_gains_three(self, builder):
        game, ajani = board(builder, "ajani_the_greathearted")
        activate(game, ajani, 1)

        assert game.state.players[0].life == 43
        assert game.state.players[1].life == 40
        assert loyalty(game, ajani) == 6

    def test_minus_two_counters_your_creatures_and_other_walkers(self, builder):
        game, ajani = board(
            builder, "ajani_the_greathearted", mine=[BEAR, WALKER], theirs=[BEAR, WALKER]
        )
        activate(game, ajani, 2)

        assert game.state.objects[only_oid(game, BEAR, 0)].counters.get("+1/+1") == 1
        assert loyalty(game, only_oid(game, WALKER, 0)) == 5
        assert loyalty(game, ajani) == 3, "not himself"
        assert game.state.objects[only_oid(game, BEAR, 1)].counters.get("+1/+1") is None
        assert loyalty(game, only_oid(game, WALKER, 1)) == 4


# ----------------------------------------------------------------------
# Aminatou, Ashiok, Dovin, Elspeth
# ----------------------------------------------------------------------


class TestAminatouTheFateshifter:
    """+1: draw, then put a card from your hand on top. -1: exile **another**
    target permanent **you own** and return it. -6: each player gains control of
    the nonland permanents other than Aminatou of the next player."""

    def test_plus_one_draws_then_puts_a_card_back_on_top(self, builder):
        game, ami = board(
            builder, "aminatou_the_fateshifter", hand0=[BEAR], lib0=[GIANT, *[PLAINS] * 5]
        )
        bear = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == BEAR)
        activate(game, ami, 0, finish=False)
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_OBJECTS,
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and [t.id for t in a.targets] == [bear]
            )
        )
        settle(game)

        assert sorted(zone_ids(game, 0, "hand")) == sorted([ANCHOR, GIANT])
        assert zone_ids(game, 0, "library")[0] == BEAR
        assert len(game.state.players[0].library) == 6, "one drawn, one put back"
        assert loyalty(game, ami) == 4

    def test_minus_one_blinks_a_permanent_you_own(self, builder):
        """It comes back a new object: untapped, and without its counter."""
        game, ami = board(builder, "aminatou_the_fateshifter", tapped0=[BEAR])
        bear = only_oid(game, BEAR, 0)
        game.state.objects[bear].counters["+1/+1"] = 1
        activate(game, ami, 1, targets=[bear])
        back = only_oid(game, BEAR, 0)

        assert not game.state.objects[back].tapped
        assert game.state.objects[back].counters.get("+1/+1") is None
        assert loyalty(game, ami) == 2

    def test_minus_one_cannot_target_herself_or_an_opponents_permanent(self, builder):
        """ "**another** target permanent **you own**"."""
        game, ami = board(builder, "aminatou_the_fateshifter", mine=[BEAR], theirs=[BEAR])
        offered = {t.id for a in activations(game, ami, 1) for t in a.targets}

        assert only_oid(game, BEAR, 0) in offered
        assert ami not in offered
        assert only_oid(game, BEAR, 1) not in offered

    def test_minus_six_swaps_the_nonland_permanents_but_not_herself(self, builder):
        game, ami = board(
            builder, "aminatou_the_fateshifter", loyalty=6, mine=[BEAR], theirs=[GIANT]
        )
        bear, giant = only_oid(game, BEAR, 0), only_oid(game, GIANT, 1)
        activate(game, ami, 2)

        assert game.state.objects[giant].controller == 0
        assert game.state.objects[bear].controller == 1
        lands = [o for o in game.state.battlefield_objects() if o.def_id == PLAINS]
        assert all(o.controller == o.owner for o in lands), "lands stay put"
        assert game.state.objects[ami].zone is Zone.GRAVEYARD, "she spent all six"


class TestAshiokDreamRender:
    """Spells and abilities your opponents control can't cause their controller to
    search their library. -1: target player mills four, then exile **each
    opponent's** graveyard."""

    def test_an_opponents_search_finds_nothing(self, builder):
        game, _ashiok = board(
            builder,
            "ashiok_dream_render",
            lands1=0,
            theirs=["forest", "forest"],
            hand1=[RAMP],
            lib1=["forest"] * 10,
            active=1,
        )
        assert search_forbidden(game.state, 1, 1)
        cast(game, RAMP, pid=1, pick=True)

        assert len(game.state.players[1].library) == 10, "no land left the library"
        assert sum(1 for o in game.state.battlefield_objects(1) if o.def_id == "forest") == 2

    def test_you_can_still_search(self, builder):
        """ "your **opponents**" -- my own Rampant Growth fetches."""
        game, _ashiok = board(
            builder,
            "ashiok_dream_render",
            mine=["forest", "forest"],
            hand0=[RAMP],
            lib0=["forest"] * 10,
        )
        assert not search_forbidden(game.state, 0, 0)
        cast(game, RAMP, pick=True)

        assert len(game.state.players[0].library) == 9

    def test_minus_one_mills_an_opponent_and_exiles_their_graveyard(self, builder):
        game, ashiok = board(builder, "ashiok_dream_render", grave1=[BEAR])
        activate(game, ashiok, 1, targets=[1])

        assert len(game.state.players[1].library) == 16
        assert game.state.players[1].graveyard == []
        assert len(game.state.players[1].exile) == 5, "the four milled and the Bear"
        assert loyalty(game, ashiok) == 4

    def test_milling_yourself_keeps_your_graveyard(self, builder):
        """ "exile each **opponent's** graveyard" -- yours stays, theirs still goes."""
        game, ashiok = board(builder, "ashiok_dream_render", grave1=[BEAR])
        activate(game, ashiok, 1, targets=[0])

        assert len(game.state.players[0].graveyard) == 4
        assert game.state.players[1].graveyard == []


class TestAshiokNightmareWeaver:
    """+2: exile the top three of target opponent's library. -X: put a creature
    card with mana value X **exiled with Ashiok** onto the battlefield under your
    control, a Nightmare too. -10: exile all cards from opponents' hands and
    graveyards."""

    def test_plus_two_exiles_the_top_three_of_an_opponents_library(self, builder):
        game, ashiok = board(
            builder, "ashiok_nightmare_weaver", lib1=[BEAR, GIANT, PLAINS, ANGEL, *[PLAINS] * 6]
        )
        activate(game, ashiok, 0, targets=[1])

        assert sorted(zone_ids(game, 1, "exile")) == sorted([BEAR, GIANT, PLAINS])
        assert zone_ids(game, 1, "library")[0] == ANGEL
        assert len(game.state.players[0].library) == 20, "not mine"
        assert loyalty(game, ashiok) == 5

    def nightmare(self, builder):
        """+2 this turn, then on my next turn the -X with three cards to find."""
        game, ashiok = board(
            builder,
            "ashiok_nightmare_weaver",
            lib1=[BEAR, GIANT, PLAINS, *[PLAINS] * 10],
            max_turns=6,
        )
        activate(game, ashiok, 0, targets=[1])
        to_step(game, Step.UPKEEP, 1)
        to_step(game, Step.PRECOMBAT_MAIN, 0)
        settle(game)
        assert game.state.active_player == 0 and loyalty(game, ashiok) == 5
        return game, ashiok

    def test_minus_x_puts_the_creature_of_mana_value_x_onto_the_battlefield(self, builder):
        game, ashiok = self.nightmare(builder)
        activate(game, ashiok, 1, x=2, finish=False)
        answer(game, pick=True)

        bear = only_oid(game, BEAR, 0)
        assert game.state.objects[bear].controller == 0
        assert "Nightmare" in chars(game.state, bear).subtypes
        assert GIANT in zone_ids(game, 1, "exile"), "mana value 4 is not X = 2"
        assert loyalty(game, ashiok) == 3

    def test_x_has_to_match_exactly(self, builder):
        """X = 3 finds nothing: the Bear is 2 and the Giant is 4."""
        game, ashiok = self.nightmare(builder)
        activate(game, ashiok, 1, x=3, finish=False)
        answer(game, pick=True)

        assert [o for o in game.state.battlefield_objects(0) if o.def_id in (BEAR, GIANT)] == []
        assert loyalty(game, ashiok) == 2

    def test_a_creature_exiled_by_something_else_is_out_of_reach(self, builder):
        """ "exiled **with Ashiok**" (607) -- a Bear exiled any other way stays put."""
        game, ashiok = board(builder, "ashiok_nightmare_weaver", loyalty=5, theirs=[BEAR])
        bear = only_oid(game, BEAR, 1)
        move_object(game.state, bear, Zone.EXILE)
        game.state.bump_chars()
        activate(game, ashiok, 1, x=2, finish=False)
        answer(game, pick=True)

        assert [o for o in game.state.battlefield_objects() if o.def_id == BEAR] == []
        assert loyalty(game, ashiok) == 3

    def test_minus_ten_exiles_opponents_hands_and_graveyards_only(self, builder):
        game, ashiok = board(
            builder,
            "ashiok_nightmare_weaver",
            loyalty=10,
            hand0=[BEAR],
            hand1=[BEAR],
            grave0=[GIANT],
            grave1=[GIANT],
        )
        activate(game, ashiok, 2)

        assert game.state.players[1].hand == []
        assert game.state.players[1].graveyard == []
        assert sorted(zone_ids(game, 0, "hand")) == sorted([ANCHOR, BEAR])
        assert zone_ids(game, 0, "graveyard")[:1] == [GIANT]


class TestDovinBaan:
    """+1: until your next turn, up to one target creature gets -3/-0 and its
    activated abilities can't be activated. -1: gain 2, draw a card. -7: an emblem
    -- your opponents can't untap more than two permanents during their untap."""

    def officer_can_activate(self, game, officer) -> bool:
        return any(
            a.kind is ActionKind.ACTIVATE and a.source == officer
            for a in legality._priority_actions(game.state, 1)
        )

    def locked(self, builder):
        game, dovin = board(builder, "dovin_baan", theirs=[OFFICER], lands1=5, max_turns=6)
        officer = only_oid(game, OFFICER, 1)
        assert self.officer_can_activate(game, officer), "the premise"
        activate(game, dovin, 0, targets=[officer])
        return game, dovin, officer

    def test_plus_one_shrinks_and_locks_the_creature(self, builder):
        game, dovin, officer = self.locked(builder)

        assert pt(game, officer) == (-1, 1)
        assert not self.officer_can_activate(game, officer)
        assert loyalty(game, dovin) == 4

    def test_it_lasts_through_the_opponents_turn(self, builder):
        """ "Until your next turn" -- not end of turn."""
        game, _dovin, officer = self.locked(builder)
        to_step(game, Step.PRECOMBAT_MAIN, 1)

        assert pt(game, officer) == (-1, 1)
        assert not self.officer_can_activate(game, officer)

    def test_and_ends_at_your_next_turn(self, builder):
        game, _dovin, officer = self.locked(builder)
        to_step(game, Step.UPKEEP, 0)

        assert pt(game, officer) == (2, 1)
        assert self.officer_can_activate(game, officer)

    def test_minus_one_gains_two_and_draws(self, builder):
        game, dovin = board(builder, "dovin_baan")
        activate(game, dovin, 1)

        assert game.state.players[0].life == 42
        assert len(game.state.players[0].library) == 19
        assert loyalty(game, dovin) == 2

    def test_the_emblem_holds_an_opponent_to_two_untaps(self, builder):
        game, dovin = board(
            builder, "dovin_baan", loyalty=7, lands1=0, tapped1=[PLAINS] * 5, max_turns=6
        )
        activate(game, dovin, 2)
        assert emblems(game, 0) == 1
        to_step(game, Step.UPKEEP, 1)

        assert sum(not o.tapped for o in game.state.battlefield_objects(1)) == 2

    def test_but_not_you(self, builder):
        """ "Your **opponents**" -- my own five tapped lands all untap."""
        game, dovin = board(
            builder, "dovin_baan", loyalty=7, lands0=0, tapped0=[PLAINS] * 5, max_turns=6
        )
        activate(game, dovin, 2)
        to_step(game, Step.UPKEEP, 0)

        assert sum(o.tapped for o in game.state.battlefield_objects(0)) == 0


class TestElspethSunsChampion:
    """+1: three 1/1 white Soldiers. -3: destroy all creatures with power 4 or
    greater. -7: an emblem -- creatures you control get +2/+2 and have flying."""

    def test_plus_one_makes_three_soldiers(self, builder):
        game, elspeth = board(builder, "elspeth_sun_s_champion")
        activate(game, elspeth, 0)

        assert len(tokens(game, SOLDIER)) == 3
        assert loyalty(game, elspeth) == 5

    def test_minus_three_destroys_power_four_or_more_on_both_sides(self, builder):
        game, elspeth = board(
            builder, "elspeth_sun_s_champion", mine=[ANGEL, GIANT], theirs=[BIG, GIANT]
        )
        activate(game, elspeth, 1)

        names = [o.def_id for o in game.state.battlefield_objects()]
        assert ANGEL not in names, "power exactly 4 is 'or greater'"
        assert BIG not in names
        assert names.count(GIANT) == 2, "power 3 survives on both sides"
        assert loyalty(game, elspeth) == 1

    def test_the_emblem_buffs_and_gives_flying_to_your_creatures_only(self, builder):
        game, elspeth = board(
            builder, "elspeth_sun_s_champion", loyalty=7, mine=[BEAR], theirs=[BEAR], max_turns=4
        )
        activate(game, elspeth, 2)
        to_step(game, Step.UPKEEP, 1)
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)

        assert pt(game, mine) == (4, 4)
        assert "flying" in keywords(game, mine)
        assert pt(game, theirs) == (2, 2)
        assert "flying" not in keywords(game, theirs)


# ----------------------------------------------------------------------
# Gideon
# ----------------------------------------------------------------------


class TestGideonJura:
    """+2: during target opponent's next turn, creatures that player controls
    attack Gideon Jura if able. -2: destroy target **tapped** creature. 0: until
    end of turn a 6/6 Human Soldier creature that's still a planeswalker; prevent
    all damage that would be dealt to him this turn."""

    def taunted(self, builder):
        game, gideon = board(builder, "gideon_jura", theirs=[BEAR], max_turns=6)
        activate(game, gideon, 0, targets=[1])
        return game, gideon, only_oid(game, BEAR, 1)

    def test_plus_two_forces_their_creatures_at_gideon_next_turn(self, builder):
        game, gideon, bear = self.taunted(builder)
        assert loyalty(game, gideon) == 8
        pass_until(
            game,
            lambda g: g.pending() is not None
            and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
            and g.state.active_player == 1,
        )
        offered = [
            t
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER and a.source == bear
            for t in a.targets
        ]

        assert [(t.kind, t.id) for t in offered] == [("object", gideon)], "only Gideon"
        assert not any(a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions()), (
            "the Bear must attack"
        )

    def test_it_does_not_bind_them_on_your_own_turn(self, builder):
        game, _gideon, bear = self.taunted(builder)

        assert combat_mod.required_attack_walkers(game.state, bear) == set()

    def test_it_is_over_after_their_next_turn(self, builder):
        """ "During target opponent's **next** turn" -- one turn, not every turn."""
        game, gideon, _bear = self.taunted(builder)
        pass_until(game, lambda g: g.state.turn >= 3)

        assert game.state.objects[gideon].must_be_attacked_by == {}

    def test_minus_two_destroys_a_tapped_creature_and_cannot_reach_an_untapped_one(
        self, builder
    ):
        game, gideon = board(builder, "gideon_jura", theirs=[GIANT], tapped1=[BEAR])
        bear, giant = only_oid(game, BEAR, 1), only_oid(game, GIANT, 1)
        offered = {t.id for a in activations(game, gideon, 1) for t in a.targets}
        assert giant not in offered, "'target **tapped** creature'"
        activate(game, gideon, 1, targets=[bear])

        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert loyalty(game, gideon) == 4

    def test_zero_makes_a_6_6_that_takes_no_damage(self, builder):
        game, gideon = board(builder, "gideon_jura", theirs=[GIANT], max_turns=4)
        giant = only_oid(game, GIANT, 1)
        activate(game, gideon, 2)
        c = chars(game.state, gideon)
        assert (c.power, c.toughness) == (6, 6)
        assert {"Creature", "Planeswalker"} <= set(c.types)
        assert {"Human", "Soldier"} <= set(c.subtypes)
        assert loyalty(game, gideon) == 6

        declare_attackers(game, {gideon: ("player", 1)})
        declare_blockers(game, {giant: gideon})
        to_step(game, Step.END_STEP, 0)

        assert loyalty(game, gideon) == 6, "the Giant's 3 is prevented"
        assert game.state.objects[giant].zone is Zone.GRAVEYARD

    def test_he_is_not_a_creature_after_the_turn(self, builder):
        game, gideon = board(builder, "gideon_jura", max_turns=4)
        activate(game, gideon, 2)
        to_step(game, Step.UPKEEP, 1)

        assert "Creature" not in chars(game.state, gideon).types


class TestGideonOfTheTrials:
    """+1: until your next turn, prevent all damage target permanent would deal.
    0: until end of turn a 4/4 indestructible Human Soldier, damage to him
    prevented. 0: an emblem -- as long as you control a Gideon planeswalker, you
    can't lose the game and your opponents can't win the game."""

    def test_plus_one_stops_the_creatures_damage_through_their_turn(self, builder):
        game, gideon = board(builder, "gideon_of_the_trials", theirs=[BEAR], max_turns=6)
        bear = only_oid(game, BEAR, 1)
        activate(game, gideon, 0, targets=[bear])
        assert loyalty(game, gideon) == 4

        to_step(game, Step.UPKEEP, 1)
        declare_attackers(game, {bear: ("player", 0)})
        to_step(game, Step.END_STEP, 1)

        assert game.state.players[0].life == 40

    def test_and_ends_at_your_next_turn(self, builder):
        """ "Until **your next turn**" -- on their following turn the Bear hits."""
        game, gideon = board(builder, "gideon_of_the_trials", theirs=[BEAR], max_turns=8)
        bear = only_oid(game, BEAR, 1)
        activate(game, gideon, 0, targets=[bear])
        to_step(game, Step.UPKEEP, 1)
        to_step(game, Step.UPKEEP, 0)
        to_step(game, Step.UPKEEP, 1)
        declare_attackers(game, {bear: ("player", 0)})
        to_step(game, Step.END_STEP, 1)

        assert game.state.players[0].life == 38

    def test_zero_makes_an_indestructible_4_4_that_takes_no_damage(self, builder):
        game, gideon = board(builder, "gideon_of_the_trials", theirs=[BIG], max_turns=4)
        big = only_oid(game, BIG, 1)
        activate(game, gideon, 1)
        assert pt(game, gideon) == (4, 4)
        assert "indestructible" in keywords(game, gideon)
        assert "Planeswalker" in chars(game.state, gideon).types
        assert loyalty(game, gideon) == 3

        declare_attackers(game, {gideon: ("player", 1)})
        declare_blockers(game, {big: gideon})
        to_step(game, Step.END_STEP, 0)

        assert game.state.objects[gideon].zone is Zone.BATTLEFIELD
        assert loyalty(game, gideon) == 3, "the 6/6's damage is prevented"

    def emblem(self, builder, mine=()):
        game, gideon = board(builder, "gideon_of_the_trials", mine=list(mine))
        activate(game, gideon, 2)
        assert emblems(game, 0) == 1
        assert loyalty(game, gideon) == 3, "a 0 ability"
        return game, gideon

    def test_the_emblem_keeps_you_in_the_game_at_zero_life(self, builder):
        game, _gideon = self.emblem(builder)
        game.state.players[0].life = 0
        sba._player_losses(game.state)

        assert player_cant_lose(game.state, 0)
        assert player_cant_win(game.state, 1)
        assert not game.state.players[0].has_lost

    def test_it_stops_when_no_gideon_remains(self, builder):
        game, gideon = self.emblem(builder)
        game.state.players[0].life = 0
        move_object(game.state, gideon, Zone.GRAVEYARD)
        game.state.bump_chars()
        sba._player_losses(game.state)

        assert not player_cant_lose(game.state, 0)
        assert game.state.players[0].has_lost

    def test_any_gideon_will_do(self, builder):
        """ "a Gideon planeswalker" -- not this one. Gideon Jura holds it up."""
        game, gideon = self.emblem(builder, mine=["gideon_jura"])
        move_object(game.state, gideon, Zone.GRAVEYARD)
        game.state.bump_chars()
        game.state.players[0].life = 0
        sba._player_losses(game.state)

        assert player_cant_lose(game.state, 0)
        assert not game.state.players[0].has_lost


class TestGideonChampionOfJustice:
    """+1: a loyalty counter for each creature **target opponent** controls. 0:
    until end of turn a Human Soldier creature with P/T equal to his loyalty and
    indestructible, damage to him prevented. -15: exile all other permanents."""

    def test_plus_one_counts_the_targets_creatures(self, builder):
        game, gideon = board(
            builder, "gideon_champion_of_justice", mine=[BEAR], theirs=[BEAR, BEAR, GIANT]
        )
        activate(game, gideon, 0, targets=[1])

        assert loyalty(game, gideon) == 8, "4 + 1 + three of theirs, not my Bear"

    def test_zero_makes_him_as_big_as_his_loyalty(self, builder):
        game, gideon = board(builder, "gideon_champion_of_justice", loyalty=7)
        activate(game, gideon, 1)
        c = chars(game.state, gideon)

        assert (c.power, c.toughness) == (7, 7)
        assert "indestructible" in keywords(game, gideon)
        assert {"Creature", "Planeswalker"} <= set(c.types)
        assert {"Human", "Soldier"} <= set(c.subtypes)
        assert loyalty(game, gideon) == 7

    def test_minus_fifteen_exiles_everything_else(self, builder):
        game, gideon = board(
            builder, "gideon_champion_of_justice", loyalty=16, mine=[BEAR], theirs=[GIANT]
        )
        activate(game, gideon, 2)

        assert [o.oid for o in game.state.battlefield_objects()] == [gideon]
        assert loyalty(game, gideon) == 1
        assert BEAR in zone_ids(game, 0, "exile") and PLAINS in zone_ids(game, 0, "exile")
        assert GIANT in zone_ids(game, 1, "exile")


# ----------------------------------------------------------------------
# Jace
# ----------------------------------------------------------------------


class TestJaceCunningCastaway:
    """+1: whenever one or more creatures you control deal combat damage to a
    player **this turn**, draw then discard. -2: a 2/2 blue Illusion that is
    sacrificed when it becomes the target of a spell. -5: two token copies of
    Jace, except they're not legendary."""

    def test_plus_one_loots_once_for_a_whole_attack(self, builder):
        """Two Bears connect; "one or more" is one loot, not two."""
        game, jace = board(builder, "jace_cunning_castaway", mine=[BEAR, BEAR], max_turns=4)
        bears = [o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR]
        activate(game, jace, 0)
        assert loyalty(game, jace) == 5 - 1

        declare_attackers(game, {b: ("player", 1) for b in bears})
        to_step(game, Step.END_STEP, 0)

        assert game.state.players[1].life == 36
        assert len(game.state.players[0].library) == 19
        assert len(game.state.players[0].graveyard) == 1
        assert len(game.state.players[0].hand) == 1

    def test_the_loot_lasts_only_this_turn(self, builder):
        game, jace = board(builder, "jace_cunning_castaway", mine=[BEAR], max_turns=6)
        bear = only_oid(game, BEAR, 0)
        activate(game, jace, 0)
        to_step(game, Step.PRECOMBAT_MAIN, 1)
        to_step(game, Step.PRECOMBAT_MAIN, 0)
        library = len(game.state.players[0].library)

        declare_attackers(game, {bear: ("player", 1)})
        to_step(game, Step.END_STEP, 0)

        assert game.state.players[1].life == 38
        assert len(game.state.players[0].library) == library

    def test_minus_two_makes_an_illusion_that_dies_to_a_targeting_spell(self, builder):
        game, jace = board(builder, "jace_cunning_castaway", mine=["forest"], hand0=[PUMP])
        activate(game, jace, 1)
        (illusion,) = tokens(game, ILLUSION)
        assert pt(game, illusion.oid) == (2, 2)
        assert {str(c) for c in chars(game.state, illusion.oid).colors} == {"U"}
        assert loyalty(game, jace) == 1

        cast(game, PUMP, target=illusion.oid)

        assert tokens(game, ILLUSION) == []

    def test_minus_five_makes_two_nonlegendary_copies(self, builder):
        """Both survive the legend rule beside the original, each a Jace with his
        printed loyalty -- copies of the card, not of the counters on it."""
        game, jace = board(builder, "jace_cunning_castaway", loyalty=6)
        activate(game, jace, 2)
        copies = tokens(game, "jace_cunning_castaway")

        assert len(copies) == 2
        assert all("Legendary" not in chars(game.state, o.oid).supertypes for o in copies)
        assert all(loyalty(game, o.oid) == 3 for o in copies)
        assert game.state.objects[jace].zone is Zone.BATTLEFIELD, "the legend rule spared him"
        assert loyalty(game, jace) == 1

    def test_minus_five_from_exactly_five_still_makes_the_copies(self, builder):
        """The usual way the ability is used: Jace goes to 0 and dies as the cost
        is paid, and the copies still arrive from his last known information
        (608.2h; the card's own ruling)."""
        game, jace = board(builder, "jace_cunning_castaway", loyalty=5)
        activate(game, jace, 2)

        assert game.state.objects[jace].zone is Zone.GRAVEYARD, "5 - 5 is 0"
        assert len(tokens(game, "jace_cunning_castaway")) == 2


class TestJaceMemoryAdept:
    """+1: draw a card, target player mills a card. 0: target player mills ten.
    -7: any number of target players each draw twenty cards."""

    def test_plus_one_draws_and_mills_the_target(self, builder):
        game, jace = board(builder, "jace_memory_adept")
        activate(game, jace, 0, targets=[1])

        assert len(game.state.players[0].library) == 19
        assert len(game.state.players[0].hand) == 2
        assert len(game.state.players[1].graveyard) == 1
        assert game.state.players[0].graveyard == []
        assert loyalty(game, jace) == 5

    def test_zero_mills_ten(self, builder):
        game, jace = board(builder, "jace_memory_adept")
        activate(game, jace, 1, targets=[1])

        assert len(game.state.players[1].graveyard) == 10
        assert len(game.state.players[1].library) == 10
        assert loyalty(game, jace) == 4

    def test_minus_seven_only_the_targets_draw_twenty(self, builder):
        game, jace = board(builder, "jace_memory_adept", loyalty=7, lib1=[PLAINS] * 30)
        activate(game, jace, 2, targets=[1])

        assert len(game.state.players[1].library) == 10
        assert len(game.state.players[0].library) == 20, "I was not a target"

    def test_minus_seven_can_target_both(self, builder):
        game, jace = board(
            builder, "jace_memory_adept", loyalty=7, lib0=[PLAINS] * 30, lib1=[PLAINS] * 30
        )
        activate(game, jace, 2, targets=[0, 1])

        assert len(game.state.players[0].library) == 10
        assert len(game.state.players[1].library) == 10


class TestJaceUnravelerOfSecrets:
    """+1: scry 1, then draw. -2: return target creature to its owner's hand.
    -8: an emblem -- whenever an opponent casts their first spell each turn,
    counter that spell."""

    def test_plus_one_scry_then_draw(self, builder):
        """Kept on top, the scried card is the one drawn."""
        game, jace = board(builder, "jace_unraveler_of_secrets", lib0=[GIANT, BEAR, *[PLAINS] * 5])
        activate(game, jace, 0)

        assert GIANT in zone_ids(game, 0, "hand")
        assert loyalty(game, jace) == 6

    def test_the_scry_comes_first(self, builder):
        """Bottomed, the second card is drawn instead -- "scry 1, **then** draw"."""
        game, jace = board(builder, "jace_unraveler_of_secrets", lib0=[GIANT, BEAR, *[PLAINS] * 5])
        activate(game, jace, 0, finish=False)
        answer(game, pick=True)

        assert BEAR in zone_ids(game, 0, "hand")
        assert zone_ids(game, 0, "library")[-1] == GIANT

    def test_minus_two_returns_a_creature_to_its_owners_hand(self, builder):
        game, jace = board(builder, "jace_unraveler_of_secrets", theirs=[GIANT])
        giant = only_oid(game, GIANT, 1)
        activate(game, jace, 1, targets=[giant])

        assert giant in game.state.players[1].hand
        assert loyalty(game, jace) == 3

    def test_the_emblem_counters_only_an_opponents_first_spell(self, builder):
        game, jace = board(
            builder,
            "jace_unraveler_of_secrets",
            loyalty=8,
            hand1=[ANCHOR],
            lands1=2,
            max_turns=4,
        )
        activate(game, jace, 2)
        assert emblems(game, 0) == 1

        to_step(game, Step.PRECOMBAT_MAIN, 1)
        cast(game, ANCHOR, pid=1)
        assert game.state.players[1].life == 40, "the first is countered"
        cast(game, ANCHOR, pid=1)
        assert game.state.players[1].life == 41, "the second resolves"

    def test_the_emblem_leaves_your_own_spells_alone(self, builder):
        game, jace = board(builder, "jace_unraveler_of_secrets", loyalty=8)
        activate(game, jace, 2)
        cast(game, ANCHOR)

        assert game.state.players[0].life == 41
