"""The Edgar Markov precon, its riskiest cards doing what they print.

Every card here cleared the six authoring gates, and almost every one reached
the pool with the weakest expectation there is -- "it is on the battlefield" --
because gate 5 casts the card once and stops. In a Mardu vampire-aristocrats
deck that is nearly the whole deck's rules text going unobserved:

- **Edgar's eminence** fires on *another* Vampire spell, and works from the
  command zone. The sandbox never casts a second spell, and never leaves the
  commander at home.
- **Edgar's attack trigger, Stromkirk Noble** need combat, which the gate
  declines.
- **The sacrifice outlets** (Vampire Aristocrat, Indulgent Aristocrat) are
  activated abilities, which the gate never activates.
- **The drain engines** (Blood Artist, Cruel Celebrant, Sanguine Bond, Epicure
  of Blood) need a death or a life gain *after* they are in play.
- **Phyrexian Arena** is an upkeep trigger, and the sandbox never reaches one.
- **Stromkirk Captain** is a lord, and the gate's board has no other Vampire to
  read the buff off.

So these are the observations. Each class quotes the card and pins the near
miss beside the hit: a non-Vampire spell makes no token, a non-Vampire gets no
counter, an opponent's creature dying drains nothing for Cruel Celebrant (but
does for Blood Artist), a gain of three is a loss of three for Sanguine Bond and
of one for the Epicure, an opponent's upkeep draws no card.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.zones import destroy
from tests.conftest import (
    _default_answer,
    advance_to_step,
    oids_of,
    only_oid,
    pass_until,
    pt,
)

EDGAR = "edgar_markov"
TOKEN = "vampire_1_1_b"
CHILD = "child_of_night"  # {1}{B} 2/1 Vampire, lifelink
BEAR = "t_bear"  # {1}{G} 2/2 Bear: a creature spell that is not a Vampire
ARISTOCRAT = "vampire_aristocrat"
INDULGENT = "indulgent_aristocrat"
BLOOD_ARTIST = "blood_artist"
FALKENRATH = "falkenrath_noble"
KALASTRIA = "kalastria_highborn"
CELEBRANT = "cruel_celebrant"
WALKER = "t_walker"  # a test planeswalker, for Cruel Celebrant's "or planeswalker"
BOND = "sanguine_bond"
EPICURE = "epicure_of_blood"
ARENA = "phyrexian_arena"
CAPTAIN = "stromkirk_captain"
NOBLE = "stromkirk_noble"
BOLT = "t_bolt"  # {R} instant, 3 damage to any target
GAIN_THREE = "t_splicer"  # {2}{W} instant, "You gain 3 life."
# A castable instant in each seat's hand: with no play available to anybody the
# engine's auto-pass runs whole turns inside one `apply` and overshoots the step
# under test. It is also the one-life gain the life-gain cards read.
ANCHOR = "t_plain_instant"  # {W}, "You gain 1 life."


def settle(game, *, yes: bool = False, limit: int = 300) -> None:
    """Let the stack empty, answering every `MAY` with ``yes``."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if yes else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def cast(game, card_id: str, *, target: int | None = None) -> None:
    """Cast ``card_id`` from hand (at ``target`` if it has one) and resolve it."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == card_id
            and (target is None or not a.targets or a.targets[0].id == target)
        )
    )
    while (p := game.pending()) is not None and p.kind is DecisionKind.CHOOSE_OBJECTS:
        game.apply(next(a for a in game.legal_actions() if a.targets and a.targets[0].id == target))
    settle(game)


def sacrifice(game, outlet: int, victim: int) -> None:
    """Activate ``outlet``'s sacrifice ability, sacrificing ``victim``."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == outlet
        )
    )
    assert game.pending().kind is DecisionKind.CHOOSE_OBJECTS
    game.apply(next(a for a in game.legal_actions() if a.targets and a.targets[0].id == victim))
    settle(game)


def sacrifice_paying(game, outlet: int, victim: int) -> None:
    """`sacrifice`, saying yes to every `MAY` -- Kalastria Highborn's "you may
    pay {B}"."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == outlet
        )
    )
    game.apply(next(a for a in game.legal_actions() if a.targets and a.targets[0].id == victim))
    settle(game, yes=True)


def life(game, pid: int) -> int:
    return game.state.players[pid].life


class TestEdgarEminence:
    """"Eminence -- Whenever you cast another Vampire spell, if Edgar is in the
    command zone or on the battlefield, create a 1/1 black Vampire creature
    token." """

    def position(self, builder, *, edgar_on_battlefield: bool = False):
        b = builder(players=2)
        if edgar_on_battlefield:
            b = b.battlefield(0, [EDGAR])
        else:
            b = b.commander(0, [EDGAR])
        return (
            b.battlefield(0, ["swamp", "swamp", "forest", "forest"])
            .hand(0, [CHILD, BEAR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_a_vampire_cast_from_the_command_zone_makes_a_token(self, builder):
        """The gate never leaves the commander at home: this is the eminence."""
        game = self.position(builder)
        cast(game, CHILD)
        assert len(oids_of(game, CHILD, 0)) == 1
        [token] = oids_of(game, TOKEN, 0)
        assert game.state.objects[token].is_token
        assert pt(game, token) == (1, 1)
        assert "Vampire" in chars(game.state, token).subtypes

    def test_it_works_from_the_battlefield_too(self, builder):
        game = self.position(builder, edgar_on_battlefield=True)
        cast(game, CHILD)
        assert len(oids_of(game, TOKEN, 0)) == 1

    def test_a_non_vampire_spell_makes_nothing(self, builder):
        game = self.position(builder)
        cast(game, BEAR)
        assert len(oids_of(game, BEAR, 0)) == 1
        assert oids_of(game, TOKEN, 0) == []


class TestEdgarAttacks:
    """"Whenever Edgar attacks, put a +1/+1 counter on each Vampire you
    control." """

    def test_each_vampire_gets_a_counter_and_nothing_else_does(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [EDGAR, CHILD, BEAR, "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains", CHILD])
            .hand(1, [ANCHOR])
            .build()
        )
        edgar = only_oid(game, EDGAR, 0)
        child = only_oid(game, CHILD, 0)
        bear = only_oid(game, BEAR, 0)
        theirs = only_oid(game, CHILD, 1)
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == edgar
                and a.targets[0].kind == "player"
            )
        )
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        settle(game)

        assert game.state.objects[edgar].counters == {"+1/+1": 1}
        assert game.state.objects[child].counters == {"+1/+1": 1}
        assert pt(game, child) == (3, 2)
        assert game.state.objects[bear].counters == {}, "a Bear is not a Vampire"
        assert game.state.objects[theirs].counters == {}, "nor is theirs one *you* control"


class TestVampireAristocrat:
    """"Sacrifice a creature: This creature gets +2/+2 until end of turn." """

    def test_it_sacrifices_and_grows_until_end_of_turn(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [ARISTOCRAT, BEAR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .library(0, ["swamp"] * 10)
            .library(1, ["swamp"] * 10)
            .max_turns(4)
            .build()
        )
        aristocrat = only_oid(game, ARISTOCRAT, 0)
        bear = only_oid(game, BEAR, 0)
        sacrifice(game, aristocrat, bear)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert pt(game, aristocrat) == (4, 4)
        assert game.state.objects[aristocrat].counters == {}, "a pump, not a counter"

        pass_until(game, lambda g: g.state.active_player == 1)
        assert pt(game, aristocrat) == (2, 2)


class TestIndulgentAristocrat:
    """"Lifelink. {2}, Sacrifice a creature: Put a +1/+1 counter on each Vampire
    you control." """

    def test_counters_on_each_vampire_not_on_a_bear(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [INDULGENT, CHILD, BEAR, "t_bear", "swamp", "swamp"])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        indulgent = only_oid(game, INDULGENT, 0)
        child = only_oid(game, CHILD, 0)
        fodder, survivor = oids_of(game, BEAR, 0)
        sacrifice(game, indulgent, fodder)

        assert game.state.objects[fodder].zone is Zone.GRAVEYARD
        assert game.state.objects[indulgent].counters == {"+1/+1": 1}
        assert game.state.objects[child].counters == {"+1/+1": 1}
        assert game.state.objects[survivor].counters == {}
        swamps = [
            o for o in game.state.battlefield_objects(0) if o.def_id == "swamp"
        ]
        assert all(s.tapped for s in swamps), "the {2} was paid"


class TestBloodArtist:
    """"Whenever this creature or another creature dies, target player loses 1
    life and you gain 1 life." """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [BLOOD_ARTIST, ARISTOCRAT, BEAR, "mountain"])
            .hand(0, [BOLT])
            .battlefield(1, ["plains", BEAR])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_your_creature_dying_drains_one(self, builder):
        game = self.position(builder)
        sacrifice(game, only_oid(game, ARISTOCRAT, 0), only_oid(game, BEAR, 0))
        assert (life(game, 0), life(game, 1)) == (41, 39)

    def test_an_opponents_creature_dying_drains_one_too(self, builder):
        """"Another creature", not "another creature you control"."""
        game = self.position(builder)
        theirs = only_oid(game, BEAR, 1)
        cast(game, BOLT, target=theirs)
        assert game.state.objects[theirs].zone is Zone.GRAVEYARD
        assert (life(game, 0), life(game, 1)) == (41, 39)

    def test_its_own_death_drains_one(self, builder):
        """"This creature or another": its own death is heard (603.10a)."""
        game = self.position(builder)
        sacrifice(game, only_oid(game, ARISTOCRAT, 0), only_oid(game, BLOOD_ARTIST, 0))
        assert (life(game, 0), life(game, 1)) == (41, 39)


class TestFalkenrathNoble:
    """"Flying. Whenever this creature or another creature dies, target player
    loses 1 life and you gain 1 life." -- the same trigger as Blood Artist's."""

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [FALKENRATH, ARISTOCRAT, BEAR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_another_creature_dying_drains_one(self, builder):
        game = self.position(builder)
        sacrifice(game, only_oid(game, ARISTOCRAT, 0), only_oid(game, BEAR, 0))
        assert (life(game, 0), life(game, 1)) == (41, 39)

    def test_its_own_death_drains_one(self, builder):
        """It used to carry `exclude_self`, which is "another creature" only."""
        game = self.position(builder)
        sacrifice(game, only_oid(game, ARISTOCRAT, 0), only_oid(game, FALKENRATH, 0))
        assert (life(game, 0), life(game, 1)) == (41, 39)


class TestKalastriaHighborn:
    """"Whenever this creature or another Vampire you control dies, you may pay
    {B}. If you do, target player loses 2 life and you gain 2 life." """

    def position(self, builder, *, players: int = 2):
        b = builder(players=players).battlefield(0, [KALASTRIA, ARISTOCRAT, CHILD, BEAR, "swamp"])
        for pid in range(1, players):
            b.battlefield(pid, ["plains"]).hand(pid, [ANCHOR])
        return b.build()

    def test_paying_drains_one_player_two(self, builder):
        """Three players: "target player" is one of them, not each opponent."""
        game = self.position(builder, players=3)
        sacrifice_paying(game, only_oid(game, ARISTOCRAT, 0), only_oid(game, CHILD, 0))
        assert life(game, 0) == 42
        assert sorted([life(game, 1), life(game, 2)]) == [38, 40]
        assert game.state.objects[only_oid(game, "swamp", 0)].tapped, "the {B} was paid"

    def test_its_own_death_counts(self, builder):
        game = self.position(builder)
        sacrifice_paying(game, only_oid(game, ARISTOCRAT, 0), only_oid(game, KALASTRIA, 0))
        assert (life(game, 0), life(game, 1)) == (42, 38)

    def test_declining_to_pay_does_nothing(self, builder):
        game = self.position(builder)
        sacrifice(game, only_oid(game, ARISTOCRAT, 0), only_oid(game, CHILD, 0))
        assert (life(game, 0), life(game, 1)) == (40, 40)
        assert not game.state.objects[only_oid(game, "swamp", 0)].tapped

    def test_a_non_vampire_dying_does_not_trigger_it(self, builder):
        game = self.position(builder)
        sacrifice_paying(game, only_oid(game, ARISTOCRAT, 0), only_oid(game, BEAR, 0))
        assert (life(game, 0), life(game, 1)) == (40, 40)


class TestCruelCelebrant:
    """"Whenever this creature or another creature or planeswalker you control
    dies, each opponent loses 1 life and you gain 1 life." """

    def position(self, builder):
        return (
            builder(players=3)
            .battlefield(0, [CELEBRANT, ARISTOCRAT, BEAR, "mountain"])
            .hand(0, [BOLT])
            .battlefield(1, ["plains", BEAR])
            .hand(1, [ANCHOR])
            .battlefield(2, ["plains"])
            .hand(2, [ANCHOR])
            .build()
        )

    def test_your_creature_dying_drains_each_opponent(self, builder):
        game = self.position(builder)
        sacrifice(game, only_oid(game, ARISTOCRAT, 0), only_oid(game, BEAR, 0))
        assert [life(game, p) for p in range(3)] == [41, 39, 39]

    def test_an_opponents_creature_dying_drains_nothing(self, builder):
        """The near miss Blood Artist does not have: "you control"."""
        game = self.position(builder)
        theirs = only_oid(game, BEAR, 1)
        cast(game, BOLT, target=theirs)
        assert game.state.objects[theirs].zone is Zone.GRAVEYARD
        assert [life(game, p) for p in range(3)] == [40, 40, 40]

    def test_its_own_death_drains_each_opponent(self, builder):
        game = self.position(builder)
        sacrifice(game, only_oid(game, ARISTOCRAT, 0), only_oid(game, CELEBRANT, 0))
        assert [life(game, p) for p in range(3)] == [41, 39, 39]

    def test_your_planeswalker_dying_drains_each_opponent(self, builder):
        """"…or planeswalker you control" -- the half the card used to drop."""
        game = (
            builder(players=3)
            .battlefield(0, [CELEBRANT, WALKER])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .battlefield(2, ["plains"])
            .hand(2, [ANCHOR])
            .build()
        )
        destroy(game.state, only_oid(game, WALKER, 0))
        settle(game)
        assert [life(game, p) for p in range(3)] == [41, 39, 39]


class TestSanguineBond:
    """"Whenever you gain life, target opponent loses that much life." """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [BOND, "plains", "plains", "plains", "plains"])
            .hand(0, [ANCHOR, GAIN_THREE])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_gaining_one_drains_one(self, builder):
        game = self.position(builder)
        cast(game, ANCHOR)
        assert (life(game, 0), life(game, 1)) == (41, 39)

    def test_gaining_three_drains_three(self, builder):
        """"That much life": the amount, not one per event."""
        game = self.position(builder)
        cast(game, GAIN_THREE)
        assert (life(game, 0), life(game, 1)) == (43, 37)


class TestEpicureOfBlood:
    """"Whenever you gain life, each opponent loses 1 life." """

    def test_one_per_gain_from_each_opponent_whatever_the_amount(self, builder):
        """The Bond's near miss: a gain of three is still a loss of one."""
        game = (
            builder(players=3)
            .battlefield(0, [EPICURE, "plains", "plains", "plains"])
            .hand(0, [GAIN_THREE])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .battlefield(2, ["plains"])
            .hand(2, [ANCHOR])
            .build()
        )
        cast(game, GAIN_THREE)
        assert [life(game, p) for p in range(3)] == [43, 39, 39]


class TestPhyrexianArena:
    """"At the beginning of your upkeep, you draw a card and you lose 1 life." """

    def upkeep(self, builder, *, whose: int):
        game = (
            builder(players=2)
            .battlefield(0, [ARENA, "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, ["swamp"] * 20)
            .library(1, ["swamp"] * 20)
            .active(1 - whose)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(4)
            .build()
        )
        pass_until(game, lambda g: g.state.step is Step.UPKEEP and g.state.active_player == whose)
        settle(game)
        return game

    def test_your_upkeep_draws_one_and_costs_one(self, builder):
        game = self.upkeep(builder, whose=0)
        assert game.state.step is Step.UPKEEP, "before the draw step's own card"
        assert len(game.state.players[0].library) == 19
        assert len(game.state.players[0].hand) == 2
        assert life(game, 0) == 39

    def test_an_opponents_upkeep_does_nothing(self, builder):
        game = self.upkeep(builder, whose=1)
        assert len(game.state.players[0].library) == 20
        assert life(game, 0) == 40
        assert len(game.state.players[1].library) == 20, "and it is not theirs either"


class TestStromkirkCaptain:
    """"First strike. Other Vampire creatures you control get +1/+1 and have
    first strike." """

    def test_other_vampires_you_control_only(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [CAPTAIN, CHILD, BEAR])
            .battlefield(1, [CHILD])
            .build(advance=False)
        )
        captain = only_oid(game, CAPTAIN, 0)
        child = only_oid(game, CHILD, 0)
        bear = only_oid(game, BEAR, 0)
        theirs = only_oid(game, CHILD, 1)

        def first_strike(oid: int) -> bool:
            return "first_strike" in {str(k) for k in chars(game.state, oid).keywords}

        assert pt(game, child) == (3, 2) and first_strike(child)
        assert pt(game, captain) == (2, 2), "other: it does not buff itself"
        assert first_strike(captain)
        assert pt(game, bear) == (2, 2) and not first_strike(bear)
        assert pt(game, theirs) == (2, 1) and not first_strike(theirs)


class TestStromkirkNoble:
    """"Whenever this creature deals combat damage to a player, put a +1/+1
    counter on it." """

    def attack(self, builder, *, blocker: str | None):
        game = (
            builder(players=2)
            .battlefield(0, [NOBLE, "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains", *([blocker] if blocker else [])])
            .hand(1, [ANCHOR])
            .build()
        )
        noble = only_oid(game, NOBLE, 0)
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER and a.source == noble
            )
        )
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        if blocker:
            pass_until(
                game,
                lambda g: g.pending() is not None
                and g.pending().kind is DecisionKind.DECLARE_BLOCKERS,
            )
            game.apply(
                next(a for a in game.legal_actions() if a.kind is ActionKind.ADD_BLOCKER)
            )
        pass_until(game, lambda g: g.state.step is Step.END_OF_COMBAT)
        settle(game)
        return game, noble

    def test_unblocked_it_hits_and_grows(self, builder):
        game, noble = self.attack(builder, blocker=None)
        assert life(game, 1) == 39
        assert game.state.objects[noble].counters == {"+1/+1": 1}
        assert pt(game, noble) == (2, 2)

    def test_blocked_it_deals_no_player_damage_and_stays_small(self, builder):
        """A 1/1 blocked by a 0/4 wall: combat damage, but not to a player."""
        game, noble = self.attack(builder, blocker="t_defensive_wall")
        assert life(game, 1) == 40
        assert game.state.objects[noble].counters == {}


class TestMavrenFein:
    """"Whenever one or more nontoken Vampires you control attack, create a 1/1
    white Vampire creature token with lifelink."

    Once per combat, not once per attacker, and Mavren need not be one of them.
    It was written as Mavren's own attack trigger making a *black* Vampire.
    """

    MAVREN = "mavren_fein_dusk_apostle"
    WHITE = "vampire_1_1_w_lifelink"

    def attack(self, builder, attackers: list[str]):
        game = (
            builder(players=2)
            .battlefield(0, [self.MAVREN, CHILD, EDGAR, BEAR, "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        for card_id in attackers:
            oid = only_oid(game, card_id, 0)
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.ADD_ATTACKER
                    and a.source == oid
                    and a.targets[0].kind == "player"
                )
            )
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        settle(game)
        return game

    def test_another_vampire_attacking_alone_makes_one_white_token(self, builder):
        game = self.attack(builder, [CHILD])
        assert len(oids_of(game, self.WHITE, 0)) == 1
        assert oids_of(game, "vampire_1_1_b_lifelink", 0) == []

    def test_three_vampires_attacking_still_make_one(self, builder):
        game = self.attack(builder, [self.MAVREN, CHILD, EDGAR])
        assert len(oids_of(game, self.WHITE, 0)) == 1

    def test_a_bear_attacking_alone_makes_none(self, builder):
        game = self.attack(builder, [BEAR])
        assert oids_of(game, self.WHITE, 0) == []
