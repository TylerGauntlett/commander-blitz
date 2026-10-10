"""The Myrel deck's control shell, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card **once**, in one
fixed sandbox, and reads the board one step later. Three of its documented limits
bite this group, and the third is the whole reason the file is worth having:

- **It never activates an ability.** Cathar Commando's "{1}, Sacrifice this
  creature: Destroy target artifact or enchantment" is the card, and the harness
  stops before it.
- **A trigger that never fires cannot be asserted.** Nothing in that position
  attacks, so Firemane Commando's two lines and Kinbinding's combat token are
  measured as "zero" -- a statement that the card did not *misfire*.
- **It cannot show a prohibition biting**, because nothing in the sandbox tries
  the forbidden thing afterwards. "Players can't untap more than one land", "you
  can't lose the game", "your life total can't change" and "exile it instead" all
  look *identical to doing nothing* when read one step after the card resolves.

So every class below pairs the claim with its **near miss**: the forbidden action
is set up and shown to be unavailable (or ineffective), and the same position
without the card is shown to allow it. For a prohibition that pair is not extra
rigour, it is the only test there is.

### What is pinned elsewhere, and is deliberately not repeated here

Four of these cards arrived with the capability that made them possible, and each
capability has its own unit test about the *mechanism*. This file is about the
*card in a game position*:

- `tests/unit/players/test_cant_lose_the_game.py` -- Angel's Grace: the outcome lock and
  the damage life-floor, read off `sba` and the primitives directly.
- `tests/unit/replacement/test_replace_graveyard.py` -- Rest in Peace: the graveyard
  replacement from every zone, on a synthetic probe card.
- `tests/unit/turn/test_untap_limit.py` -- Winter Orb: `untap_caps` and `untap_all`,
  neither of which runs an untap step.
- `tests/unit/named_cards/test_approach_of_the_second_sun.py` -- Approach: `cast_from_hand`,
  the game-long cast ledger, the `> 1` boundary and the seventh-from-top tuck.

The one printed clause in this group that no assertion here can reach is Angel's
Grace's **split second**. The engine stops a response at the legality layer, and
a seat with no legal action is never asked: by the time any `pending()` exists the
spell has already resolved, so there is no game state in which to observe the
prohibition. `tests/unit/casting/test_split_second.py` measures it where it lives.
"""

from __future__ import annotations

from automtg.engine.characteristics import (
    chars,
    player_protected_from,
    protection_from,
)
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.primitives import life_locked, lose_life
from tests.conftest import (
    action_for_card,
    battlefield_ids,
    count_on_battlefield,
    declare_targets,
    find_action,
    keywords,
    only_oid,
    pass_until,
    settle_to_priority,
)

# A castable instant in the *opponent's* hand, and it is load bearing rather than
# scenery. With no play available to anybody the engine's auto-pass runs from a
# spell resolving straight through cleanup into the next turn -- which wipes every
# until-end-of-turn grant before it can be read. A test measuring Akroma's Will or
# Unbreakable Formation after that would pass whatever the card did.
ANCHOR = "t_plain_instant"  # {W} instant, "You gain 1 life" -- a reason to stop
# A 2/2 for the boards that just need a creature. `t_bear` is the usual choice and
# is the wrong one for the arrival tests below: it costs {1}{G}, an opponent whose
# board is Plains can never cast it, and a test of "creatures your opponents
# control enter tapped" that produces no arrival measures nothing.
BEAR = "grizzly_bears"
WARDEN = "soul_warden"  # a {W} 1/1 the opponent really can cast off Plains
# Swords to Plowshares gives life equal to **power**, so the witness is a printed
# 4/3: on any 2/2 "equal to its power", "equal to its toughness" and a hard-coded
# 2 all coincide, and three different wrong cards would pass.
BIG = "firemane_commando"
RING = "sol_ring"  # an artifact, for the half of Cathar Commando that is not a creature
# A nonbasic land that does *not* print "enters tapped" of its own accord. Secluded
# Steppe and Castle Ardenvale are both in this deck and both useless here: they
# arrive tapped whether or not Thalia is on the battlefield.
PASSAGE = "rogue_s_passage"


def can_cast(game, card_id: str, pid: int) -> bool:
    decision = game.pending()
    return (
        decision is not None
        and decision.player == pid
        and any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
            for a in game.legal_actions()
        )
    )


def cast(game, card_id: str, pid: int = 0) -> int:
    """Cast ``card_id`` from ``pid``'s hand and let it resolve. Returns its oid."""
    pass_until(game, lambda g: can_cast(g, card_id, pid))
    action = action_for_card(game, ActionKind.CAST, card_id)
    oid = action.source
    game.apply(action)
    settle_to_priority(game)
    return oid


def cast_targeting(game, card_id: str, *target_oids: int, pid: int = 0) -> None:
    """Cast a card-level-targeted spell at exactly these objects.

    Targets are enumerated onto the cast action rather than chosen behind it, so
    the choice is which action to apply -- and taking the first offered one would
    let the harness pick the target, which is how a removal test ends up
    measuring the wrong permanent.
    """
    pass_until(game, lambda g: can_cast(g, card_id, pid))
    wanted = tuple(target_oids)
    lines = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]
    action = next((a for a in lines if tuple(t.id for t in a.targets) == wanted), None)
    if action is not None:
        game.apply(action)
    else:
        # A set of two or more is declared as the cast happens rather than on
        # the line (`casting.deferred_target_spec`) -- for The Eagles Are
        # Coming!, only the kicked line asks for one.
        deferred = sorted(
            (a for a in lines if not a.targets), key=lambda a: not a.kicked
        )
        game.apply(deferred[0])
        declare_targets(game, *wanted)
    settle_to_priority(game)


def attack_with(game, *oids: int, defender: int = 1) -> None:
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
    )
    for oid in oids:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and a.targets[0].kind == "player"
                and a.targets[0].id == defender
            )
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def tapped_lands(game, pid: int = 0, card_id: str = "plains") -> list[bool]:
    return [o.tapped for o in game.state.battlefield_objects(pid) if o.def_id == card_id]


class TestWinterOrb:
    """ "As long as this artifact is untapped, players can't untap more than one
    land during their untap steps."

    The prohibition gate 5 is furthest from reaching: the sandbox never takes a
    second turn, so it never runs an untap step at all, and its expectation is
    "the Orb is on the battlefield". `tests/unit/turn/test_untap_limit.py` pins
    `untap_caps` and `untap_all`; what is untested until here is the cap biting in
    a real untap step -- the decision it puts to the untapping player, and the two
    lands that stay down afterwards.
    """

    def position(self, builder, *, orb: bool = True, orb_tapped: bool = False):
        """Three tapped Plains, and the turn about to roll round to me.

        Built at the end step so the run passes through the *opponent's* untap
        step before mine: that is where a cap written about the wrong seat, or
        about the wrong board, shows up.
        """
        b = builder(players=2)
        if orb:
            b = b.battlefield(0, ["winter_orb"], tapped=orb_tapped)
        return (
            b.battlefield(0, ["plains", "plains", "plains"], tapped=True)
            .battlefield(1, ["plains"])
            .hand(0, ["plains"])
            .hand(1, [ANCHOR])
            .step(Step.END_STEP)
            .build()
        )

    def untap_cap(self, game):
        pass_until(
            game,
            lambda g: (
                g.pending() is not None
                and g.pending().kind is DecisionKind.CHOOSE_OBJECTS
                and g.state.step is Step.UNTAP
            ),
        )
        return game.pending()

    def test_the_untap_step_asks_which_one_land_untaps(self, builder):
        """502.2 untaps and asks nobody anything; under the Orb it has to ask.

        Which land is the untapping player's choice, and an engine that picked
        would be deciding whether the Orb locks out the Island or the Sol Ring --
        a different card every game.
        """
        game = self.position(builder)
        decision = self.untap_cap(game)

        assert decision.player == 0, "my untap step, my choice"
        assert decision.prompt == "Untap up to 1"
        assert len(decision.options) == 3, "all three Plains are candidates"

    def test_only_the_chosen_land_untaps(self, builder):
        """The cap biting. Two of my three lands stay down, which is the whole
        card and is invisible one step after it resolves."""
        game = self.position(builder)
        self.untap_cap(game)
        choice = next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE)
        kept = choice.targets[0].id
        game.apply(choice)
        pass_until(game, lambda g: g.state.step is Step.PRECOMBAT_MAIN)

        still_tapped = [
            o.oid for o in game.state.battlefield_objects(0) if o.def_id == "plains" and o.tapped
        ]
        assert not game.state.objects[kept].tapped, "the one I chose"
        assert len(still_tapped) == 2, "and the other two are held down"

    def test_and_the_same_board_untaps_fully_without_it(self, builder):
        """The control, and the reason the test above is not just "an untap step
        untapped a land". Three untapped Plains cannot happen under a cap of one.
        """
        game = self.position(builder, orb=False)
        pass_until(
            game,
            lambda g: g.state.turn >= 3 and g.state.step is Step.PRECOMBAT_MAIN,
        )

        assert tapped_lands(game) == [False, False, False]

    def test_a_tapped_orb_caps_nothing(self, builder):
        """ "As long as this artifact is untapped" -- and this is how the card is
        beaten in play: tap the Orb on the opponent's end step and your own untap
        step is free."""
        game = self.position(builder, orb_tapped=True)
        pass_until(
            game,
            lambda g: g.state.turn >= 3 and g.state.step is Step.PRECOMBAT_MAIN,
        )

        assert tapped_lands(game) == [False, False, False]

    def test_it_caps_the_opponents_untap_step_too(self, builder):
        """ "**Players** can't untap" -- the drawback is the card. A one-sided
        reading would leave the Orb's controller free and is a different, and
        much better, artifact."""
        game = (
            builder(players=2)
            .battlefield(0, ["winter_orb", "plains"])
            .battlefield(1, ["plains", "plains", "plains"], tapped=True)
            .hand(1, ["plains"])
            .step(Step.END_STEP)
            .build()
        )
        decision = self.untap_cap(game)

        assert decision.player == 1


class TestArmageddon:
    """ "Destroy all lands."

    Gate 5 already pinned the opponent's board emptying. What it cannot say is
    that *my* lands went too: the sandbox casts the card from a board it also
    owns, and "destroy all lands" and "destroy all lands your opponents control"
    are the same reading of a one-sided count.
    """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["plains"] * 4 + [BEAR])
            .battlefield(1, ["plains", RING, BEAR])
            .hand(0, ["armageddon"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_it_takes_my_own_lands_as_well(self, builder):
        """The symmetry, which is the thing a mis-written sweeper gets wrong."""
        game = self.position(builder)
        cast(game, "armageddon")

        assert "plains" not in battlefield_ids(game, 0)
        assert "plains" not in battlefield_ids(game, 1)

    def test_it_leaves_everything_that_is_not_a_land(self, builder):
        """ "All **lands**". A creature and an artifact on the same board survive,
        which is what separates this from a Jokulhaups."""
        game = self.position(builder)
        cast(game, "armageddon")

        assert count_on_battlefield(game, BEAR, 0) == 1
        assert sorted(battlefield_ids(game, 1)) == sorted([RING, BEAR])


class TestAuthorityOfTheConsuls:
    """ "Creatures your opponents control enter tapped. Whenever a creature an
    opponent controls enters, you gain 1 life."

    Both halves are about somebody *else's* arrival, and gate 5's sandbox has no
    arrival after the card under test -- so its honest expectation was "life 40
    and 40", which is a statement that the enchantment did not misfire.
    """

    def position(self, builder, *, caster: int):
        """The creature is cast by ``caster`` on ``caster``'s own turn."""
        return (
            builder(players=2)
            .battlefield(0, ["authority_of_the_consuls", "plains"])
            .battlefield(1, ["plains", "plains"])
            .hand(caster, [WARDEN])
            .active(caster)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_an_opponents_creature_arrives_tapped_and_pays_me_a_life(self, builder):
        game = self.position(builder, caster=1)
        before = game.state.players[0].life

        warden = cast(game, WARDEN, pid=1)

        assert game.state.objects[warden].tapped is True
        assert game.state.players[0].life == before + 1

    def test_my_own_creature_arrives_untapped_and_pays_nothing(self, builder):
        """The near miss in both halves at once: a filter that defaulted to
        `controller: "you"` would tap my own Soldiers, and a symmetric trigger
        would pay me for my own board -- which in a deck that makes a token every
        combat is a different card entirely."""
        game = self.position(builder, caster=0)
        before = game.state.players[0].life

        warden = cast(game, WARDEN, pid=0)

        assert game.state.objects[warden].tapped is False
        assert game.state.players[0].life == before


class TestThaliaHereticCathar:
    """ "First strike. Creatures and nonbasic lands your opponents control enter
    tapped."

    Gate 5's expectation for Thalia is `{"zone": "battlefield"}` -- the weakest
    there is -- because her printed line is about an arrival that never happens in
    that sandbox. Nothing caught, therefore, that she shipped carrying
    `replacements: [{event: self_enters_tapped}]`, which is read off the
    **arriving** card's own face: she tapped *herself* on arrival and did nothing
    at all to her opponents, so she was simultaneously inert and worse than
    printed -- a 3/2 first-striker that could not block the turn she landed.

    The feature log of the day named her as one of ten shipped cards written
    this way and said they were "repaired in the commit after this one". That
    repair never landed. She is repaired here, as two `enters_tapped` statics --
    the shape Authority of the Consuls already uses -- one filtered to an
    opponent's creatures and one to an opponent's nonbasic lands. No engine work
    was needed; the filter language could always say it.

    All four halves of the sentence are asserted below, because three of them
    failed in the shipped card and each fails differently: the creature, the
    nonbasic land, the basic land that must be **left alone**, and Thalia's own
    untapped arrival.
    """

    def position(self, builder, hand: list[str]):
        return (
            builder(players=2)
            .battlefield(0, ["thalia_heretic_cathar", "plains"])
            .battlefield(1, ["plains", "plains"])
            .hand(1, hand)
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def play_land(self, game, card_id: str, pid: int = 1) -> int:
        pass_until(
            game,
            lambda g: (
                g.pending() is not None
                and g.pending().player == pid
                and any(
                    a.kind is ActionKind.PLAY_LAND and g.state.objects[a.source].def_id == card_id
                    for a in g.legal_actions()
                )
            ),
        )
        action = action_for_card(game, ActionKind.PLAY_LAND, card_id)
        oid = action.source
        game.apply(action)
        settle_to_priority(game)
        return oid

    def test_she_has_first_strike(self, builder):
        game = self.position(builder, [WARDEN])
        assert "first_strike" in keywords(game, only_oid(game, "thalia_heretic_cathar"))

    def test_an_opponents_creature_arrives_tapped(self, builder):
        game = self.position(builder, [WARDEN])
        warden = cast(game, WARDEN, pid=1)
        assert game.state.objects[warden].tapped is True

    def test_an_opponents_nonbasic_land_arrives_tapped(self, builder):
        game = self.position(builder, [PASSAGE])
        passage = self.play_land(game, PASSAGE)
        assert game.state.objects[passage].tapped is True

    def test_an_opponents_basic_land_is_untouched(self, builder):
        """ "**Nonbasic** lands" -- the boundary that makes her a tax and not a
        Kismet, and the half a `not_supertypes` filter exists for."""
        game = self.position(builder, ["plains"])
        plains = self.play_land(game, "plains")
        assert game.state.objects[plains].tapped is False

    def test_she_does_not_arrive_tapped_herself(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", "plains", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, ["thalia_heretic_cathar"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        thalia = cast(game, "thalia_heretic_cathar")
        assert game.state.objects[thalia].tapped is False

    def test_my_own_creature_is_untouched(self, builder):
        """ "Your **opponents**". A symmetric reading would tap the Soldier deck's
        own arrivals, which is the worst thing that could happen to this deck."""
        game = (
            builder(players=2)
            .battlefield(0, ["thalia_heretic_cathar", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [WARDEN])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        warden = cast(game, WARDEN, pid=0)
        assert game.state.objects[warden].tapped is False


class TestRestInPeace:
    """ "When this enchantment enters, exile all graveyards. If a card or token
    would be put into a graveyard from anywhere, exile it instead."

    Gate 5 pinned `graveyard_size {"0": 0}` -- the caster's own pile, emptied by
    the enters trigger. Everything below is the *static*, which nothing in that
    sandbox goes to a graveyard to test, and the symmetry, which is the drawback
    the card is built around.

    `tests/unit/replacement/test_replace_graveyard.py` walks every zone the replacement has to
    reach on a probe card. This is the printed card doing it in a game, and the
    thing that kills the creatures is another card from the same deck.
    """

    def position(self, builder, *, rip: bool):
        """Six lands: {1}{W} for Rest in Peace and {2}{W}{W} for the sweeper."""
        return (
            builder(players=2)
            .battlefield(0, ["plains"] * 6 + [BEAR])
            .battlefield(1, ["plains", BEAR])
            .graveyard(0, ["plains", "plains"])
            .graveyard(1, ["plains"])
            .hand(0, ["rest_in_peace", "day_of_judgment"] if rip else ["day_of_judgment"])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_it_exiles_both_graveyards_as_it_enters(self, builder):
        """ "All graveyards", unqualified. The opponent's pile is the half gate 5
        did not look at."""
        game = self.position(builder, rip=True)
        cast(game, "rest_in_peace")

        assert game.state.players[0].graveyard == []
        assert game.state.players[1].graveyard == []
        assert len(game.state.players[0].exile) == 2
        assert len(game.state.players[1].exile) == 1

    def test_creatures_that_die_afterwards_are_exiled_from_both_sides(self, builder):
        """The static, and the whole reason the card is played: after a Day of
        Judgment nobody has anything to reanimate. Symmetric, so my own Soldier
        goes too."""
        game = self.position(builder, rip=True)
        cast(game, "rest_in_peace")
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)

        cast(game, "day_of_judgment")

        assert game.state.objects[mine].zone is Zone.EXILE
        assert game.state.objects[theirs].zone is Zone.EXILE
        assert game.state.players[0].graveyard == []
        assert game.state.players[1].graveyard == []

    def test_the_sweeper_itself_is_exiled_rather_than_buried(self, builder):
        """ "From **anywhere**" reaches the stack: a resolved sorcery is a card on
        its way to a graveyard like any other, and `dies_to` -- the hook that
        already existed -- is gated on the battlefield and would miss it."""
        game = self.position(builder, rip=True)
        cast(game, "rest_in_peace")
        judgment = cast(game, "day_of_judgment")

        assert game.state.objects[judgment].zone is Zone.EXILE

    def test_without_it_the_same_sweeper_fills_both_graveyards(self, builder):
        """The control. Two exiles and an empty pile mean nothing unless the same
        board without the enchantment buries everything."""
        game = self.position(builder, rip=False)
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)

        cast(game, "day_of_judgment")

        assert game.state.objects[mine].zone is Zone.GRAVEYARD
        assert game.state.objects[theirs].zone is Zone.GRAVEYARD
        assert len(game.state.players[1].graveyard) == 2, "their Bear joins their Plains"


class TestAngelsGrace:
    """ "You can't lose the game this turn and your opponents can't win the game
    this turn. Until end of turn, damage that would reduce your life total to less
    than 1 reduces it to 1 instead."

    Gate 5's expectation is `life {"0": 40, "1": 40}`: nothing in that sandbox
    damages anybody, so the card and a blank instant read identically. It is also
    the card most easily written as the wrong thing -- `prevent_damage` installs a
    shield, the total never moves, and a player at 40 ends the turn at 40.

    **Angel's Grace is not a Fog.** The damage lands, the total stops at 1, and
    you keep playing at or below it. `tests/unit/players/test_cant_lose_the_game.py` pins
    that against the primitives; here it is real combat damage and a real turn
    boundary.
    """

    def position(self, builder, *, grace: bool):
        """Me at 2 life, an opponent with a 2/2, and their turn about to happen.

        Two life rather than twenty because the floor is only observable when the
        damage would actually take me past 1 -- at 40 life a 2/2 and a Fog and a
        life floor are three indistinguishable things.
        """
        return (
            builder(players=2)
            .battlefield(0, ["plains", "plains"])
            .battlefield(1, [BEAR, "plains"])
            .hand(0, ["angel_s_grace"] if grace else [])
            .life(0, 2)
            .active(1)
            .step(Step.UPKEEP)
            .build()
        )

    def test_lethal_combat_damage_leaves_me_at_one_and_in_the_game(self, builder):
        game = self.position(builder, grace=True)
        cast(game, "angel_s_grace", pid=0)

        attack_with(game, only_oid(game, BEAR, 1), defender=0)
        pass_until(game, lambda g: g.state.step >= Step.END_OF_COMBAT or g.over)

        assert game.state.players[0].life == 1, "2 damage, floored -- not prevented"
        assert game.state.players[0].has_lost is False
        assert game.over is False

    def test_and_the_same_attack_kills_me_without_it(self, builder):
        """The control. "Still at 1 and still alive" is only a claim about the
        card if the identical board without it ends the game."""
        game = self.position(builder, grace=False)

        attack_with(game, only_oid(game, BEAR, 1), defender=0)
        pass_until(game, lambda g: g.state.step >= Step.END_OF_COMBAT or g.over)

        assert game.state.players[0].life == 0
        assert game.state.players[0].has_lost is True
        assert game.winners == [1]

    def test_a_loss_that_is_not_damage_is_held_off_until_the_lock_clears(self, builder):
        """The other printed half, and the reason the floor alone is not the card.

        The floor reads **damage** -- the printed word -- so an ordinary life
        payment walks straight past it and really does put me below zero. What
        keeps me in the game is "you can't lose the game this turn", and the proof
        that it is a *this turn* lock rather than a rewritten life total is that
        the same board loses on the following turn with nothing else happening.

        A life payment rather than a deck card because this deck prints none: it
        is mono-white with no burn, no Phyrexian cost and no Bitterblossom, which
        is exactly why the distinction had to be measured rather than assumed.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["plains", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, ["angel_s_grace"])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast(game, "angel_s_grace")

        lose_life(game.state, 0, 45)
        assert game.state.players[0].life == -5, "the floor does not read a payment"

        pass_until(game, lambda g: g.state.step is Step.END_STEP or g.over)
        assert game.state.players[0].has_lost is False, "still in the game this turn"

        pass_until(game, lambda g: g.over or g.state.active_player == 1, limit=200)
        assert game.state.players[0].has_lost is True, "and the lock was only a turn"
        assert game.winners == [1]


class TestApproachOfTheSecondSun:
    """ "If this spell was cast from your hand and you've cast another spell named
    Approach of the Second Sun this game, you win the game."

    Gate 5 saw the *other* branch -- `life {"0": 47}` and the card seventh from
    the top -- because one cast is never two. `tests/unit/named_cards/
    test_approach_of_the_second_sun.py` pins the `> 1` boundary, the tuck depth and `cast_from_hand`.

    What is left, and what belongs in a deck file rather than a unit file, is the
    pair this deck can make out of its own two cards: an **opponent's** Approach
    resolving into Angel's Grace's "your opponents can't win the game this turn".
    A win refused has to be refused *whole* -- `declare_win` eliminates everybody
    else, so a check one layer down would dismantle half the table and then stop.
    """

    def position(self, builder, *, grace: bool):
        """Sixteen Plains for the opponent: {6}{W} twice, in one turn."""
        return (
            builder(players=2)
            .battlefield(0, ["plains"])
            .battlefield(1, ["plains"] * 16)
            .hand(0, ["angel_s_grace"] if grace else [])
            .hand(1, ["approach_of_the_second_sun"] * 2)
            .active(1)
            .step(Step.UPKEEP)
            .build()
        )

    def test_the_second_approach_wins_the_game(self, builder):
        """The premise. Without it the test below is a statement about a card that
        never worked."""
        game = self.position(builder, grace=False)

        cast(game, "approach_of_the_second_sun", pid=1)
        assert game.over is False, "one cast is not another"
        cast(game, "approach_of_the_second_sun", pid=1)

        assert game.over is True
        assert game.winners == [1]

    def test_angels_grace_refuses_it_and_nobody_is_eliminated(self, builder):
        game = self.position(builder, grace=True)
        cast(game, "angel_s_grace", pid=0)

        cast(game, "approach_of_the_second_sun", pid=1)
        cast(game, "approach_of_the_second_sun", pid=1)

        assert game.over is False
        assert game.winners == []
        assert game.state.players[0].has_lost is False


class TestTeferisProtection:
    """ "Until your next turn, your life total can't change and you gain protection
    from everything. All permanents you control phase out."

    Gate 5 pinned `battlefield_count 0` and the card in exile -- and that is
    exactly the observation a *wrong* card would produce. Sacrificing my board,
    exiling it or destroying it all read as zero permanents one step later. The
    printed card gives everything back at my next untap step, and that is the half
    worth pinning.
    """

    def position(self, builder, *, teferi: bool, active: int = 0):
        return (
            builder(players=2)
            .battlefield(0, ["plains", "plains", "plains", WARDEN])
            .battlefield(1, [BEAR, "plains"])
            .hand(0, ["teferi_s_protection"] if teferi else [])
            .hand(1, [ANCHOR])
            .active(active)
            .step(Step.PRECOMBAT_MAIN if active == 0 else Step.UPKEEP)
            .build()
        )

    def test_my_permanents_leave_the_battlefield_without_dying(self, builder):
        """Phased out, not destroyed: nothing is in a graveyard and nothing lost
        its counters, because 702.26c is not a zone change."""
        game = self.position(builder, teferi=True)
        mine = [o.oid for o in game.state.battlefield_objects(0)]
        cast(game, "teferi_s_protection")

        assert battlefield_ids(game, 0) == []
        assert game.state.players[0].graveyard == []
        assert all(game.state.objects[oid].phased_out for oid in mine)

    def test_and_they_all_come_back_at_my_next_untap_step(self, builder):
        """The half that separates the printed card from a one-sided Armageddon."""
        game = self.position(builder, teferi=True)
        before = sorted(battlefield_ids(game, 0))
        cast(game, "teferi_s_protection")
        assert battlefield_ids(game, 0) == []

        pass_until(
            game,
            lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN,
            limit=400,
        )

        assert sorted(battlefield_ids(game, 0)) == before

    def test_the_opponents_board_is_untouched(self, builder):
        """ "All permanents **you** control"."""
        game = self.position(builder, teferi=True)
        cast(game, "teferi_s_protection")

        assert sorted(battlefield_ids(game, 1)) == sorted([BEAR, "plains"])

    def test_an_attack_that_connects_changes_nothing(self, builder):
        """ "Your life total can't change." The creature is still declared -- this
        is not a Fog and not a Maze of Ith -- and the damage simply cannot move
        the total."""
        game = self.position(builder, teferi=True, active=1)
        cast(game, "teferi_s_protection", pid=0)
        assert life_locked(game.state, 0) is True

        attack_with(game, only_oid(game, BEAR, 1), defender=0)
        pass_until(game, lambda g: g.state.step >= Step.END_OF_COMBAT or g.over)

        assert game.state.players[0].life == 40

    def test_and_the_same_attack_takes_two_without_it(self, builder):
        """The control."""
        game = self.position(builder, teferi=False, active=1)

        attack_with(game, only_oid(game, BEAR, 1), defender=0)
        pass_until(game, lambda g: g.state.step >= Step.END_OF_COMBAT or g.over)

        assert game.state.players[0].life == 38

    def test_protection_from_everything_covers_any_source_and_then_ends(self, builder):
        """Both clauses are on the same clock -- "until your next turn" -- so the
        pair is the grant and its expiry, read from the same position."""
        game = self.position(builder, teferi=True)
        theirs = only_oid(game, BEAR, 1)
        assert player_protected_from(game.state, 0, theirs) is False

        cast(game, "teferi_s_protection")
        assert player_protected_from(game.state, 0, theirs) is True
        assert player_protected_from(game.state, 1, theirs) is False, "mine, not theirs"

        pass_until(
            game,
            lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN,
            limit=400,
        )
        assert player_protected_from(game.state, 0, theirs) is False
        assert life_locked(game.state, 0) is False


class TestAkromasWill:
    """ "Choose one. If you control a commander as you cast this spell, you may
    choose both instead."

    Gate 5 takes the first mode and stops: its expectation records flying,
    vigilance and double strike, and says nothing about the second mode, about
    "both", or about the grant wearing off. The sandbox has no commander, so the
    conditional half of the modal cost is unreachable there by construction.
    """

    def position(self, builder, *, commander: bool):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 4 + [BEAR])
            .battlefield(1, ["plains"])
            .hand(0, ["akroma_s_will"])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        if commander:
            # "If you control a commander **as you cast this spell**" -- a
            # property of the board, so it is placed on the board rather than
            # played from a command zone: casting a commander would also move the
            # turn on and cost the mana this spell needs.
            game.state.objects[bear].is_commander = True
            game.state.bump_chars()
        return game, bear

    def take_modes(self, game) -> int:
        """Answer every mode question, taking the first offer each time.

        The count is the assertion: "choose both" is not an option on one
        decision, it is being asked a second time.
        """
        pass_until(game, lambda g: can_cast(g, "akroma_s_will", 0))
        game.apply(action_for_card(game, ActionKind.CAST, "akroma_s_will"))
        asked = 0
        while (
            decision := game.pending()
        ) is not None and decision.kind is DecisionKind.CHOOSE_MODE:
            choice = next((a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None)
            if choice is None:
                break
            asked += 1
            game.apply(choice)
        settle_to_priority(game)
        return asked

    def test_without_a_commander_it_is_choose_one(self, builder):
        game, bear = self.position(builder, commander=False)

        assert self.take_modes(game) == 1
        assert keywords(game, bear) >= {"flying", "vigilance", "double_strike"}
        assert "indestructible" not in keywords(game, bear), "the second mode is not free"

    def test_with_a_commander_both_modes_apply(self, builder):
        """Six keywords and protection from five colours off one card -- the
        reason this is the deck's combat trick and its fog at once."""
        game, bear = self.position(builder, commander=True)

        assert self.take_modes(game) == 2
        assert keywords(game, bear) >= {
            "flying",
            "vigilance",
            "double_strike",
            "lifelink",
            "indestructible",
        }
        assert protection_from(game.state, bear) >= {"W", "U", "B", "R", "G"}

    def test_the_grant_is_gone_after_cleanup(self, builder):
        """ "Until end of turn" -- and a permanent grant on a mono-white board of
        Soldiers would be a materially different card."""
        game, bear = self.position(builder, commander=True)
        self.take_modes(game)
        assert keywords(game, bear)

        pass_until(
            game,
            lambda g: g.state.active_player == 1 and g.state.step is Step.PRECOMBAT_MAIN,
        )

        assert keywords(game, bear) == set()
        assert protection_from(game.state, bear) == frozenset()


class TestUnbreakableFormation:
    """ "Creatures you control gain indestructible until end of turn. Addendum --
    If you cast this spell during your main phase, put a +1/+1 counter on each of
    those creatures and they gain vigilance until end of turn."

    Gate 5 casts from a main phase and records both halves, which makes its
    expectation blind to the one thing Addendum means: the *other* timing. A card
    written without the condition passes that gate exactly.
    """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["plains"] * 3 + [BEAR])
            .battlefield(1, ["plains"])
            .hand(0, ["unbreakable_formation"])
            .hand(1, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )

    def test_cast_in_a_main_phase_it_does_both_halves(self, builder):
        game = self.position(builder)
        bear = only_oid(game, BEAR, 0)
        pass_until(game, lambda g: g.state.step is Step.PRECOMBAT_MAIN)
        cast(game, "unbreakable_formation")

        assert keywords(game, bear) >= {"indestructible", "vigilance"}
        assert game.state.objects[bear].counters.get("+1/+1") == 1
        assert chars(game.state, bear).power == 3

    def test_cast_outside_one_it_does_only_the_first(self, builder):
        """The Addendum boundary, and the near miss for the whole card: at the
        beginning of combat it is still a fog for my board, and no counter."""
        game = self.position(builder)
        bear = only_oid(game, BEAR, 0)
        pass_until(game, lambda g: g.state.step is Step.BEGIN_COMBAT)
        cast(game, "unbreakable_formation")

        assert "indestructible" in keywords(game, bear)
        assert "vigilance" not in keywords(game, bear)
        assert game.state.objects[bear].counters.get("+1/+1") is None

    def test_the_counter_outlives_the_turn_and_the_keywords_do_not(self, builder):
        """One sentence, two durations. A version that pumped instead of countering
        would read identically until cleanup."""
        game = self.position(builder)
        bear = only_oid(game, BEAR, 0)
        pass_until(game, lambda g: g.state.step is Step.PRECOMBAT_MAIN)
        cast(game, "unbreakable_formation")

        pass_until(
            game,
            lambda g: g.state.active_player == 1 and g.state.step is Step.PRECOMBAT_MAIN,
        )

        assert keywords(game, bear) == set()
        assert game.state.objects[bear].counters.get("+1/+1") == 1
        assert chars(game.state, bear).power == 3


class TestMooglesValor:
    """ "For each creature you control, create a 1/2 white Moogle creature token
    with lifelink. Then creatures you control gain indestructible until end of
    turn."

    Gate 5's sandbox happened to hold two creatures and its expectation says two
    tokens, so the *count* is pinned. What it cannot say is that the count is a
    count of my creatures -- and it never reaches the "until end of turn".
    """

    def position(self, builder, mine: list[str]):
        return (
            builder(players=2)
            .battlefield(0, ["plains"] * 5 + mine)
            .battlefield(1, [BEAR, BEAR, "plains"])
            .hand(0, ["moogles_valor"])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_one_token_for_each_creature_i_control(self, builder):
        """ "For each creature **you** control" -- the opponent's two Bears are on
        the board precisely so that a symmetric count would read four."""
        game = self.position(builder, [BEAR, WARDEN])
        cast(game, "moogles_valor")

        assert count_on_battlefield(game, "moogle_1_2_w_lifelink", 0) == 2
        assert count_on_battlefield(game, "moogle_1_2_w_lifelink", 1) == 0

    def test_a_lone_creature_makes_a_lone_moogle(self, builder):
        """The count is a count, not a constant."""
        game = self.position(builder, [WARDEN])
        cast(game, "moogles_valor")

        assert count_on_battlefield(game, "moogle_1_2_w_lifelink", 0) == 1

    def test_the_tokens_are_1_2_lifelinkers_and_are_covered_too(self, builder):
        """ "**Then**" -- the tokens exist before the grant runs, so they get it."""
        game = self.position(builder, [WARDEN])
        cast(game, "moogles_valor")
        token = only_oid(game, "moogle_1_2_w_lifelink", 0)

        assert (chars(game.state, token).power, chars(game.state, token).toughness) == (1, 2)
        assert keywords(game, token) >= {"lifelink", "indestructible"}

    def test_the_indestructible_ends_and_the_tokens_stay(self, builder):
        """The asymmetry that makes this a token spell rather than a trick: the
        grant is for the turn and the board is forever."""
        game = self.position(builder, [WARDEN])
        cast(game, "moogles_valor")
        warden = only_oid(game, WARDEN, 0)

        pass_until(
            game,
            lambda g: g.state.active_player == 1 and g.state.step is Step.PRECOMBAT_MAIN,
        )

        assert "indestructible" not in keywords(game, warden)
        assert count_on_battlefield(game, "moogle_1_2_w_lifelink", 0) == 1


class TestReprieve:
    """ "Return target spell to its owner's hand. Draw a card."

    Gate 5 does put a spell on the stack for this one, so its expectation records
    the hand sizes. What no expectation key can separate is a **counter** from a
    return: 701.5a makes countering a specific action, and a card that countered
    instead would leave the spell in its owner's graveyard and every count in that
    expectation unchanged. So every assertion here is about where the *other*
    spell ended up.
    """

    def position(self, builder):
        """The opponent casts a creature on their own turn, holding a second card
        so priority comes back to me rather than the turn rolling on."""
        return (
            builder(players=2)
            .battlefield(0, ["plains", "plains"])
            .battlefield(1, ["plains", "plains", "plains"])
            .hand(0, ["reprieve"])
            .hand(1, [WARDEN, ANCHOR])
            .library(0, ["plains"] * 10)
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def reprieve_their_spell(self, game) -> int:
        pass_until(game, lambda g: can_cast(g, WARDEN, 1))
        action = action_for_card(game, ActionKind.CAST, WARDEN)
        spell = action.source
        game.apply(action)
        pass_until(game, lambda g: can_cast(g, "reprieve", 0))
        game.apply(action_for_card(game, ActionKind.CAST, "reprieve"))
        settle_to_priority(game)
        return spell

    def test_the_spell_goes_to_its_owners_hand_and_not_a_graveyard(self, builder):
        game = self.position(builder)
        spell = self.reprieve_their_spell(game)

        assert game.state.objects[spell].zone is Zone.HAND
        assert spell in game.state.players[1].hand, "its **owner's** hand, not mine"
        assert game.state.players[1].graveyard == [], "a counter is the near miss"
        assert count_on_battlefield(game, WARDEN, 1) == 0, "and it never arrived"

    def test_the_second_sentence_pays_for_the_first(self, builder):
        """ "Draw a card" -- measured in the same turn, because passing to my own
        draw step would make any counter look like a cantrip."""
        game = self.position(builder)
        before = len(game.state.players[0].library)
        self.reprieve_their_spell(game)

        assert len(game.state.players[0].library) == before - 1
        assert game.state.active_player == 1, "still their turn: that draw was the card"

    def test_with_an_empty_stack_there_is_nothing_to_return(self, builder):
        """The boundary: "target **spell**", so the card is uncastable in an empty
        window -- which is also why gate 5 had to build it a spell to see."""
        game = self.position(builder)
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 0)

        assert not game.state.stack
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == "reprieve"
        ]


class TestKinbinding:
    """ "Creatures you control get +X/+X, where X is the number of creatures that
    entered the battlefield under your control this turn. At the beginning of
    combat on your turn, create a 1/1 green and white Kithkin creature token."

    Gate 5 reads the board one step after the enchantment resolves, when nothing
    has entered since and no combat has begun: X is zero and the trigger has never
    fired, so its expectation is "33 permanents". Both halves start here.
    """

    def position(self, builder, *, caster: int = 0):
        return (
            builder(players=2)
            .battlefield(0, ["kinbinding", "plains", "plains", BEAR])
            .battlefield(1, ["plains", "plains"])
            .hand(caster, [WARDEN])
            .hand(1 - caster, [ANCHOR])
            .active(caster)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_a_creature_that_was_already_there_counts_for_nothing(self, builder):
        """ "…that **entered** the battlefield … this turn". The near miss is a
        count of creatures I control, which on this board reads +1/+1 before
        anything happens."""
        game = self.position(builder)
        bear = only_oid(game, BEAR, 0)

        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (2, 2)

    def test_each_arrival_grows_the_whole_team(self, builder):
        game = self.position(builder)
        bear = only_oid(game, BEAR, 0)
        warden = cast(game, WARDEN)

        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (3, 3)
        assert chars(game.state, warden).power == 2, "the arrival counts itself"

    def test_an_arrival_under_the_opponent_does_not(self, builder):
        """ "under **your** control"."""
        game = self.position(builder, caster=1)
        bear = only_oid(game, BEAR, 0)
        cast(game, WARDEN, pid=1)

        assert chars(game.state, bear).power == 2

    def test_the_combat_trigger_makes_a_kithkin_and_feeds_the_buff(self, builder):
        """The token is itself a creature that entered this turn, so the two
        halves of the card compound -- which is the whole point of the pairing."""
        game = self.position(builder)
        bear = only_oid(game, BEAR, 0)
        pass_until(game, lambda g: g.state.step is Step.BEGIN_COMBAT)
        settle_to_priority(game)

        assert count_on_battlefield(game, "kithkin_1_1_gw", 0) == 1
        assert chars(game.state, bear).power == 3

    def test_no_kithkin_on_the_opponents_combat(self, builder):
        """ "on **your** turn" -- the boundary an `is_your_turn`-less trigger would
        cross twice a round."""
        game = self.position(builder, caster=1)
        pass_until(
            game,
            lambda g: g.state.active_player == 1 and g.state.step >= Step.END_OF_COMBAT,
        )

        assert count_on_battlefield(game, "kithkin_1_1_gw", 0) == 0


class TestSwordsToPlowshares:
    """ "Exile target creature. Its controller gains life equal to its power."

    A hand-written card with no gate-5 expectation of its own, and the amount is
    the part that is easy to get wrong in three different ways at once: a printed
    4/3 separates "its power" from "its toughness" and from a constant.
    """

    def position(self, builder, *, owner: int):
        return (
            builder(players=2)
            .battlefield(0, ["plains"])
            .battlefield(owner, [BIG])
            .hand(0, ["swords_to_plowshares"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_it_exiles_and_pays_me_four_for_my_own_creature(self, builder):
        game = self.position(builder, owner=0)
        victim = only_oid(game, BIG, 0)
        cast_targeting(game, "swords_to_plowshares", victim)

        assert game.state.objects[victim].zone is Zone.EXILE
        assert victim not in game.state.players[0].graveyard, "exiled, so nothing died"
        assert game.state.players[0].life == 44, "power 4, not toughness 3"

    def test_the_life_goes_to_the_creatures_controller(self, builder):
        """ "**Its** controller" -- the drawback that makes this the cheapest
        removal in the game rather than the best. A card that paid the caster
        would look identical in every test cast at one's own board."""
        game = self.position(builder, owner=1)
        victim = only_oid(game, BIG, 1)
        cast_targeting(game, "swords_to_plowshares", victim)

        assert game.state.objects[victim].zone is Zone.EXILE
        assert game.state.players[1].life == 44
        assert game.state.players[0].life == 40, "and I gain nothing"


class TestGenerousGift:
    """ "Destroy target permanent. Its controller creates a 3/3 green Elephant
    creature token."

    Gate 5 recorded one Elephant, and its sandbox casts at its own board -- so
    "its controller" and "you" are the same player there, and the one clause that
    makes this card a drawback is untested.
    """

    def position(self, builder, *, owner: int):
        b = builder(players=2).battlefield(0, ["plains"] * 3).battlefield(1, ["plains"])
        return (
            b.battlefield(owner, [PASSAGE])
            .hand(0, ["generous_gift"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_it_reaches_a_land_and_gives_the_elephant_to_its_controller(self, builder):
        """ "Target **permanent**" is the breadth -- this is the deck's answer to a
        Cabal Coffers as much as to a creature -- and the Elephant lands on the
        other side of the table."""
        game = self.position(builder, owner=1)
        victim = only_oid(game, PASSAGE, 1)
        cast_targeting(game, "generous_gift", victim)

        assert game.state.objects[victim].zone is Zone.GRAVEYARD
        assert count_on_battlefield(game, "elephant_3_3_g", 1) == 1
        assert count_on_battlefield(game, "elephant_3_3_g", 0) == 0

    def test_and_i_get_it_when_the_permanent_was_mine(self, builder):
        """The same clause from the other end: "its controller" really is read off
        the permanent, not fixed to either seat."""
        game = self.position(builder, owner=0)
        victim = only_oid(game, PASSAGE, 0)
        cast_targeting(game, "generous_gift", victim)

        assert count_on_battlefield(game, "elephant_3_3_g", 0) == 1
        assert count_on_battlefield(game, "elephant_3_3_g", 1) == 0


class TestDayOfJudgment:
    """ "Destroy all creatures."

    A hand-written card with no expectation of its own. The assertion that matters
    is the one a mis-written sweeper fails: my own Soldiers die too.
    """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["plains"] * 4 + [BEAR, WARDEN])
            .battlefield(1, [BEAR, "plains"])
            .hand(0, ["day_of_judgment"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_it_takes_my_own_creatures_as_well(self, builder):
        game = self.position(builder)
        cast(game, "day_of_judgment")

        assert count_on_battlefield(game, BEAR, 0) == 0
        assert count_on_battlefield(game, WARDEN, 0) == 0
        assert count_on_battlefield(game, BEAR, 1) == 0

    def test_it_leaves_the_lands_alone(self, builder):
        """ "All **creatures**" -- the difference between this and Armageddon,
        measured on one board so a swapped op would be caught."""
        game = self.position(builder)
        cast(game, "day_of_judgment")

        assert battlefield_ids(game, 0) == ["plains"] * 4
        assert battlefield_ids(game, 1) == ["plains"]


class TestCatharCommando:
    """ "Flash. {1}, Sacrifice this creature: Destroy target artifact or
    enchantment."

    Gate 5 never activates an ability and casts every card in its own main phase,
    so both printed lines are unreachable there: its expectation is that a 3/1 is
    on the battlefield.
    """

    def test_flash_lets_it_arrive_on_the_opponents_turn(self, builder):
        """The pair in one position: the Commando is castable and the Soldier
        beside it in the same hand, off the same lands, is not."""
        game = (
            builder(players=2)
            .battlefield(0, ["plains", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, ["cathar_commando", WARDEN])
            .hand(1, [ANCHOR])
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 0)
        castable = {
            game.state.objects[a.source].def_id
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
        }

        assert castable == {"cathar_commando"}

    def position(self, builder, theirs: list[str]):
        return (
            builder(players=2)
            .battlefield(0, ["cathar_commando", "plains", "plains"])
            .battlefield(1, theirs)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def activations(self, game, commando: int):
        return [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == commando
        ]

    def test_the_ability_destroys_an_artifact_and_eats_the_commando(self, builder):
        """The sacrifice is a cost, so it happens whether or not the destruction
        resolves -- and a card whose cost was not paid would be a strictly better
        Disenchant on a body."""
        game = self.position(builder, [RING, BEAR])
        commando = only_oid(game, "cathar_commando", 0)
        ring = only_oid(game, RING, 1)
        game.apply(next(a for a in self.activations(game, commando) if a.targets[0].id == ring))
        settle_to_priority(game)

        assert game.state.objects[ring].zone is Zone.GRAVEYARD
        assert game.state.objects[commando].zone is Zone.GRAVEYARD

    def test_an_enchantment_is_the_other_half_and_a_creature_is_neither(self, builder):
        """ "Artifact **or** enchantment": both are offered and the Bear standing
        beside them is not, which is the filter doing its job rather than the
        position being short of permanents."""
        game = self.position(builder, [RING, "authority_of_the_consuls", BEAR])
        commando = only_oid(game, "cathar_commando", 0)
        offered = {
            game.state.objects[a.targets[0].id].def_id for a in self.activations(game, commando)
        }

        assert offered == {RING, "authority_of_the_consuls"}

    def test_with_nothing_to_destroy_it_is_not_offered_at_all(self, builder):
        """The boundary: a targeted ability with no legal target is not
        activatable, so the Commando cannot be sacrificed for nothing."""
        game = self.position(builder, [BEAR])
        commando = only_oid(game, "cathar_commando", 0)

        assert self.activations(game, commando) == []


class TestFiremaneCommando:
    """ "Whenever you attack with two or more creatures, draw a card. Whenever
    another player attacks with two or more creatures, they draw a card if none of
    those creatures attacked you."

    Gate 5 declines combat, so both lines are measured as "no cards drawn". The
    second one cannot even be *described* at a two-player table: "none of those
    creatures attacked you" needs a third seat to attack instead.
    """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["firemane_commando", BEAR, "plains"])
            .battlefield(1, ["plains"])
            .library(0, ["plains"] * 10)
            .step(Step.UPKEEP)
            .build()
        )

    def test_two_attackers_draw_a_card(self, builder):
        game = self.position(builder)
        before = len(game.state.players[0].library)
        attack_with(game, only_oid(game, "firemane_commando", 0), only_oid(game, BEAR, 0))
        settle_to_priority(game)

        assert len(game.state.players[0].library) == before - 1

    def test_one_attacker_draws_nothing(self, builder):
        """ "**Two or more**" -- the boundary, and the thing an unconditional
        attack trigger gets wrong every turn."""
        game = self.position(builder)
        before = len(game.state.players[0].library)
        attack_with(game, only_oid(game, "firemane_commando", 0))
        settle_to_priority(game)

        assert len(game.state.players[0].library) == before

    def three_player(self, builder):
        return (
            builder(players=3)
            .battlefield(0, ["firemane_commando", "plains"])
            .battlefield(1, [BEAR, WARDEN, "plains"])
            .battlefield(2, ["plains"])
            .library(0, ["plains"] * 10)
            .library(1, ["plains"] * 10)
            .active(1)
            .step(Step.UPKEEP)
            .build()
        )

    def test_an_opponent_attacking_somebody_else_draws_for_it(self, builder):
        """The gift half of the card, and the reason it is a pillowfort: it pays
        the table to attack anybody but me."""
        game = self.three_player(builder)
        mine = len(game.state.players[0].library)
        theirs = len(game.state.players[1].library)
        attack_with(game, only_oid(game, BEAR, 1), only_oid(game, WARDEN, 1), defender=2)
        settle_to_priority(game)

        assert len(game.state.players[1].library) == theirs - 1, "they drew"
        assert len(game.state.players[0].library) == mine, "and I did not"

    def test_and_the_same_attack_aimed_at_me_pays_nobody(self, builder):
        """ "…if **none** of those creatures attacked you." The near miss is a
        trigger that rewards every multi-creature attack, which would make the
        card actively encourage attacking its controller."""
        game = self.three_player(builder)
        theirs = len(game.state.players[1].library)
        attack_with(game, only_oid(game, BEAR, 1), only_oid(game, WARDEN, 1), defender=0)
        settle_to_priority(game)

        assert len(game.state.players[1].library) == theirs


class TestTheEaglesAreComing:
    """ "Choose target creature you own. If this spell was kicked, instead choose
    any number of target creatures you own. Return each chosen creature to your
    hand. At the beginning of the next upkeep, create a 4/4 white Bird Soldier
    creature token with flying for each creature returned to your hand this way."

    Gate 5 reads the board one step after the spell resolves, and the tokens do
    not exist then -- they arrive at the *next upkeep*, a step the sandbox never
    reaches. Its expectation is therefore the bounce alone, and a card that
    returned a creature and made no birds at all would clear it.
    """

    def position(self, builder, *, lands: int):
        return (
            builder(players=2)
            .battlefield(0, ["plains"] * lands + [BEAR, WARDEN])
            .battlefield(1, ["plains"])
            .hand(0, ["the_eagles_are_coming"])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def birds(self, game) -> int:
        return count_on_battlefield(game, "bird_soldier_4_4_w_flying", 0)

    def test_unkicked_it_returns_one_and_the_bird_waits_for_the_upkeep(self, builder):
        game = self.position(builder, lands=2)
        bear = only_oid(game, BEAR, 0)
        cast_targeting(game, "the_eagles_are_coming", bear)

        assert game.state.objects[bear].zone is Zone.HAND
        assert self.birds(game) == 0, "the delay is the cost of the card"

        pass_until(
            game,
            lambda g: g.state.turn >= 2 and g.state.step >= Step.PRECOMBAT_MAIN,
            limit=300,
        )
        assert self.birds(game) == 1

    def test_kicked_it_returns_two_and_pays_two_birds(self, builder):
        """The kicker is a different *target count*, not a bigger effect, and the
        token count is read off what actually came back -- so the two halves have
        to agree or the card is silently wrong by one."""
        game = self.position(builder, lands=6)
        bear, warden = only_oid(game, BEAR, 0), only_oid(game, WARDEN, 0)
        cast_targeting(game, "the_eagles_are_coming", bear, warden)

        assert game.state.objects[bear].zone is Zone.HAND
        assert game.state.objects[warden].zone is Zone.HAND
        assert self.birds(game) == 0

        pass_until(
            game,
            lambda g: g.state.turn >= 2 and g.state.step >= Step.PRECOMBAT_MAIN,
            limit=300,
        )
        assert self.birds(game) == 2

    def test_unkicked_it_cannot_be_aimed_at_two_creatures(self, builder):
        """The boundary the kicker buys: off two lands the second target is not on
        offer at all."""
        game = self.position(builder, lands=2)
        pass_until(game, lambda g: can_cast(g, "the_eagles_are_coming", 0))
        counts = {
            len(a.targets)
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "the_eagles_are_coming"
        }

        assert counts == {1}
