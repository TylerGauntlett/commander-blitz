"""The How to Train Ur-Dragon deck's unreachable sentences, card by card.

Every card here cleared the six authoring gates, and that is exactly why this
file exists. Gate 5 -- the behaviour gate -- casts a card **once**, in one fixed
sandbox, and reads the board. Four of its documented limits bite this deck
harder than most, because this deck's payoffs are all written on combat and on
other people's spells:

- **Nothing in the sandbox ever attacks.** Old Gnawbone and Ancient Copper
  Dragon are saboteur triggers and nothing else; their honest gate-5
  expectation is "a 7/7 with flying is on the battlefield".
- **Nothing in the sandbox ever deals damage after the card under test.**
  Twinflame Tyrant and Neriv are damage *replacements*, so a position that deals
  no damage cannot tell them from a vanilla body.
- **The sandbox casts exactly one spell.** Dracogenesis is a standing permission
  over the *next* spell, and the next spell never comes.
- **The sandbox's seat owns no commander and the harness answers "no".**
  Hellkite Courser's whole printed line is behind a `may` and a command zone,
  and Steely Resolve's shroud is behind a type that was never chosen.

So the authoring expectations are floors, and these are the observations. Each
class is one card and asserts the printed sentence the gate could not reach --
including, in each case, the **near miss**: the reading that would be wrong if
the card were mis-written.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.primitives import change_control, damage_permanent, damage_player
from automtg.engine.state import new_object
from automtg.engine.zones import move_object
from tests.conftest import (
    _default_answer,
    count_on_battlefield,
    keywords,
    only_oid,
    pass_until,
)

TREASURE = "treasure_token"
#: A land in each hand, and it is load bearing rather than scenery. With no play
#: available to anybody the engine's auto-pass runs out of the main phase inside
#: one `_advance` and keeps going -- past the end step a delayed trigger is due
#: at, and past the cleanup that clears the turn ledger every `entered_this_turn`
#: reading below depends on. A land in hand is the cheapest thing that makes a
#: seat stop and hold still.
ANCHOR = "forest"


def board(builder, *, mine=(), theirs=(), hand=(), lands=0, commanders=(), seed=0):
    """A position whose permanents have all been there since before this turn.

    `GameBuilder.battlefield` stamps ``entered_turn`` one turn back and fires no
    enters trigger, so nothing placed here *arrived*. That is the "standing
    there, but did not enter" half of every Neriv assertion, and it is also what
    lets a test choose the moment a card's trigger runs.
    """
    b = (
        builder(players=2, seed=seed)
        .battlefield(0, ["mountain"] * lands)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, [*hand, ANCHOR])
        .hand(1, [ANCHOR])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
    )
    for pid, ids in commanders:
        b = b.commander(pid, list(ids))
    return b.build()


def settle(game, *, accept: bool = False, limit: int = 400) -> None:
    """Let the stack empty. ``accept`` says yes to the "you may" halves.

    `pass_until`'s default answer is the passive one, which declines every
    `MAY` -- right for a test that only wants the board to settle, and the wrong
    answer for a card whose whole printed sentence is behind the prompt.
    """
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if accept and decision.kind is DecisionKind.MAY:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
            continue
        # Priority with nothing waiting is the end. The emptiness of the stack is
        # *not* enough on its own: a trigger that asks its question before it
        # resolves leaves both the stack and the trigger queue empty while its
        # decision is still pending, and a loop that stopped there would answer
        # nothing and report that the card did nothing.
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def cast(game, card_id: str, *, accept: bool = False) -> int:
    """Cast ``card_id`` from player 0's hand and let it resolve. Returns its oid."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    oid = action.source
    game.apply(action)
    settle(game, accept=accept)
    return oid


def arrive(game, card_id: str, pid: int = 0) -> int:
    """Make a card *enter* the battlefield, firing the real event.

    The route does not matter and the event does: cast, reanimated, or put there
    by another card, all three funnel through `zones._enter_battlefield`, which
    is where the turn ledger's arrival is written. Deliberately not
    ``builder.battlefield(..., sick=True)``, which stamps ``entered_turn`` and
    emits nothing -- the difference between those two fields is the whole of
    `TestNerivHeartOfTheStorm`.
    """
    obj = new_object(game.state, card_id, owner=pid, zone=Zone.HAND)
    game.state.players[pid].hand.append(obj.oid)
    move_object(game.state, obj.oid, Zone.BATTLEFIELD)
    game.state.bump_chars()
    return obj.oid


def connect(game, oid: int, amount: int, defender: int = 1) -> None:
    """``oid`` deals ``amount`` combat damage to a player -- the saboteur event.

    `damage_player` rather than a real swing, for the reason
    `tests/unit/combat/test_combat_damage_to_planeswalker.py` gives: the event is what
    the card listens to, and driving it directly keeps the position down to the
    permanents the printed sentence is about, with no blockers, no second
    attacker and no first-strike sub-step to explain an off-by-one with.
    """
    damage_player(game.state, defender, amount, oid, is_combat=True)
    settle(game)


class TestOldGnawbone:
    """"Whenever a creature you control deals combat damage to a player,
    create that many Treasure tokens."

    Gate 5 never attacks, so its expectation is a 7/7 with flying. "That many"
    is the entire card and has two near misses waiting for it: **one** Treasure
    per trigger (the reading that drops the word "many"), and one Treasure per
    *creature* (the reading that counts the subjects rather than the damage).
    A 7-power Dragon separates all three at once.
    """

    def position(self, builder):
        game = board(builder, mine=["old_gnawbone", "birds_of_paradise"])
        return game, only_oid(game, "old_gnawbone"), only_oid(game, "birds_of_paradise")

    def test_the_count_is_the_damage_and_not_one(self, builder):
        game, gnawbone, _birds = self.position(builder)
        assert chars(game.state, gnawbone).power == 7

        connect(game, gnawbone, 7)

        assert count_on_battlefield(game, TREASURE, 0) == 7

    def test_a_bigger_hit_makes_more_treasure(self, builder):
        """The control for the test above: 7 is the power, so a card that made
        one Treasure per point of *power* would also pass it."""
        game, gnawbone, _birds = self.position(builder)
        connect(game, gnawbone, 11, defender=1)

        assert count_on_battlefield(game, TREASURE, 0) == 11

    def test_two_creatures_connecting_is_not_two_treasures(self, builder):
        """The other near miss: "that many" is damage, not attackers.

        Two creatures connect for 7 and 2. A card counting its subjects makes
        2 Treasures; this one makes 9.
        """
        game, gnawbone, birds = self.position(builder)
        connect(game, gnawbone, 7)
        connect(game, birds, 2)

        assert count_on_battlefield(game, TREASURE, 0) == 9

    def test_a_creature_you_control_and_not_only_this_one(self, builder):
        """The printed subject is "a creature you control", not "this creature".

        Birds of Paradise is a 0/1 that will never connect on its own, so this
        is measured with it alone on the board -- a card narrowed to "this
        creature" makes nothing here.
        """
        game, _gnawbone, birds = self.position(builder)
        connect(game, birds, 3)

        assert count_on_battlefield(game, TREASURE, 0) == 3

    def test_noncombat_damage_does_not_trigger_it(self, builder):
        """"combat damage". A Dragon pinging a face on an ability makes nothing."""
        game, gnawbone, _birds = self.position(builder)
        damage_player(game.state, 1, 7, gnawbone, is_combat=False)
        settle(game)

        assert count_on_battlefield(game, TREASURE, 0) == 0

    def test_an_opponents_creature_connecting_makes_you_nothing(self, builder):
        """"a creature **you control**" -- and the Treasures are yours, not theirs."""
        game = board(builder, mine=["old_gnawbone"], theirs=["goldspan_dragon"])
        theirs = only_oid(game, "goldspan_dragon", 1)
        damage_player(game.state, 0, 4, theirs, is_combat=True)
        settle(game)

        assert count_on_battlefield(game, TREASURE) == 0


class TestAncientCopperDragon:
    """"…roll a d20. You create a number of Treasure tokens equal to the result."

    The result is the **face**, and the near miss is not hypothetical: every
    other way this engine can read a roll answers the *number of dice*, which on
    one die is 1 however it landed. `values.validate_rolled` refuses
    ``{"total": false}`` in so many words for that reason, and
    ``{"rolled": {"binding": …, "total": true}}`` -- the capability this card
    was the witness for -- is the only spelling that says "the face".

    The engine's RNG is seeded through the builder and nothing else in this
    position touches it, so seed 0's first d20 is a fixed 13.
    """

    #: The first `Rng(0).randint(1, 20)`. Pinned rather than computed, so a
    #: change to the die's plumbing shows up here as a failure rather than as
    #: two expressions agreeing with each other about the wrong number.
    SEED = 0
    FACE = 13

    def position(self, builder):
        game = board(builder, mine=["ancient_copper_dragon"], seed=self.SEED)
        return game, only_oid(game, "ancient_copper_dragon")

    def test_it_makes_treasure_equal_to_the_face_rolled(self, builder):
        game, dragon = self.position(builder)
        connect(game, dragon, 6)

        rolled = [e for e in game.state.events if e.type == "dice_rolled"]
        assert len(rolled) == 1, "one trigger, one roll"
        assert rolled[0].data["sides"] == 20
        assert rolled[0].data["results"] == [self.FACE]
        assert count_on_battlefield(game, TREASURE, 0) == self.FACE

    def test_the_face_is_not_the_number_of_dice(self, builder):
        """The bug this card's capability was built to fix, stated as a number.

        One die was thrown. Every count-shaped reading of a roll -- the die
        count, the parity count, a matching-face count -- answers 1 or 0 here,
        and the card makes 13 Treasures.
        """
        game, dragon = self.position(builder)
        assert self.FACE > 1, "a seed whose face is 1 could not separate the two"
        connect(game, dragon, 6)

        assert count_on_battlefield(game, TREASURE, 0) != 1
        assert count_on_battlefield(game, TREASURE, 0) == self.FACE

    def test_the_face_is_not_the_damage_dealt(self, builder):
        """Old Gnawbone's reading, on the card that does not print it.

        The two Dragons sit in the same deck and the same colour, and "that
        many" versus "the result" is the only difference between their lines.
        This Dragon is a 6/5 and connects for 6; if the Treasures counted the
        damage there would be 6 of them.
        """
        game, dragon = self.position(builder)
        assert chars(game.state, dragon).power == 6
        connect(game, dragon, 6)

        assert count_on_battlefield(game, TREASURE, 0) == self.FACE != 6

    def test_a_second_seed_rolls_a_different_face(self, builder):
        """The roll is a roll: nothing here is a constant dressed up as one."""
        game = board(builder, mine=["ancient_copper_dragon"], seed=1)
        connect(game, only_oid(game, "ancient_copper_dragon"), 6)

        rolled = [e for e in game.state.events if e.type == "dice_rolled"]
        assert rolled[0].data["results"] == [5]
        assert count_on_battlefield(game, TREASURE, 0) == 5

    def test_noncombat_damage_rolls_nothing(self, builder):
        """"deals **combat** damage to a player"."""
        game, dragon = self.position(builder)
        damage_player(game.state, 1, 6, dragon, is_combat=False)
        settle(game)

        assert [e for e in game.state.events if e.type == "dice_rolled"] == []
        assert count_on_battlefield(game, TREASURE, 0) == 0


class TestTwinflameTyrant:
    """"If a source you control would deal damage to an opponent or a permanent
    an opponent controls, it deals double that damage instead."

    The asymmetry is the whole card. A symmetric doubler -- Furnace of Rath, the
    near miss one word away -- reads identically on every board where only the
    opponent is being hit, and loses you the game on every board where anything
    is pointed back at you. So each assertion below is paired with the one that
    would also pass under Furnace of Rath, and the pair is the test.

    Both halves of the recipient are checked separately, because
    `player_statics.damage_multiplier` reads `affects` and `affects_player` as a
    **union**: no single damage event is dealt to a player *and* a permanent, so
    a version that ANDed them would double nothing at all.
    """

    def position(self, builder):
        """Two permanents on their side, because one cannot state the last claim.

        "A source **you** control" is measured by a source they control hitting
        something, and at a two-player table the only damage that is theirs to
        deal into the static's recipient filter is theirs into their own board.
        Damage they point at *you* is doubled by nobody either way -- you are
        not an opponent of the Tyrant's controller -- so a position with one
        creature each cannot tell the clause from its absence.
        """
        game = board(
            builder,
            mine=["twinflame_tyrant", "birds_of_paradise"],
            theirs=["goldspan_dragon", "terror_of_the_peaks"],
        )
        return (
            game,
            only_oid(game, "twinflame_tyrant"),
            only_oid(game, "birds_of_paradise"),
            only_oid(game, "goldspan_dragon", 1),
        )

    def test_damage_to_an_opponent_doubles(self, builder):
        game, tyrant, _mine, _theirs = self.position(builder)
        assert damage_player(game.state, 1, 3, tyrant) == 6

    def test_damage_to_a_permanent_an_opponent_controls_doubles(self, builder):
        """The second half of the "or", and it needs its own assertion: the
        recipient is a union of two filters and only one of them can speak for
        any one event."""
        game, tyrant, _mine, theirs = self.position(builder)
        assert damage_permanent(game.state, theirs, 3, tyrant) == 6

    def test_damage_to_you_is_not_doubled(self, builder):
        """The near miss. Furnace of Rath passes both tests above and fails this
        one, and this is the difference between a payoff and a liability."""
        game, tyrant, _mine, _theirs = self.position(builder)
        assert damage_player(game.state, 0, 3, tyrant) == 3
        assert game.state.players[0].life == 40 - 3

    def test_damage_to_your_own_permanent_is_not_doubled(self, builder):
        """The permanent-side twin of the test above."""
        game, tyrant, mine, _theirs = self.position(builder)
        assert damage_permanent(game.state, mine, 1, tyrant) == 1

    def test_any_source_you_control_doubles_not_only_the_tyrant(self, builder):
        """"a **source** you control" -- the Tyrant is not the subject.

        A card written as "whenever this creature deals damage" would double
        only its own 3 power, which is close to nothing; the Tyrant is played
        for what it does to everything else on the board.
        """
        game, _tyrant, mine, _theirs = self.position(builder)
        assert damage_player(game.state, 1, 2, mine) == 4

    def test_an_opponents_source_is_not_doubled_into_their_own_board(self, builder):
        """"a source **you** control", and this is the only board that says it.

        Their Dragon damages their other creature. The recipient answers the
        static -- it is a permanent an opponent controls -- so the *only* thing
        holding the doubling off is whose source it is. Dropping
        ``damage_source`` from the card passes every other test in this class
        and fails this one.
        """
        game, _tyrant, _mine, theirs = self.position(builder)
        target = only_oid(game, "terror_of_the_peaks", 1)
        assert damage_permanent(game.state, target, 3, theirs) == 3

    def test_their_source_pointed_at_you_is_not_doubled_either(self, builder):
        """Neither half answers, and the number has to come out printed.

        Weaker than the test above -- you are not an opponent of the Tyrant's
        controller, so the recipient filter alone already refuses this -- and
        kept because it is the board a player actually fears.
        """
        game, _tyrant, _mine, theirs = self.position(builder)
        assert damage_player(game.state, 0, 3, theirs) == 3

    def test_without_the_tyrant_nothing_doubles(self, builder):
        """The control. Without it, every number above is just arithmetic."""
        game = board(builder, mine=["birds_of_paradise"], theirs=["goldspan_dragon"])
        mine = only_oid(game, "birds_of_paradise")
        assert damage_player(game.state, 1, 3, mine) == 3
        assert damage_permanent(game.state, only_oid(game, "goldspan_dragon", 1), 3, mine) == 3


class TestNerivHeartOfTheStorm:
    """"If a creature you control that entered this turn would deal damage, it
    deals twice that much instead."

    "Entered this turn" is a *fact about an arrival*, and the field that looks
    like it -- ``GameObject.entered_turn`` -- is not it. `change_control` stamps
    that field, because rule 302.6 makes a stolen permanent summoning sick
    without its having entered anything; rule 400.7 is explicit that a control
    change is not a zone change. So an implementation reading `entered_turn`
    doubles an Act of Treason'd attacker, which the printed card does not, and
    every other assertion in this class would still pass.

    The engine reads `TurnLedger.entered_this_turn`, an arrival snapshot written
    by `emit` and by nothing else; `test_stealing_a_creature_is_not_entering`
    below is the whole reason that ledger exists.
    """

    def test_a_creature_that_entered_this_turn_deals_double(self, builder):
        game = board(builder, mine=["neriv_heart_of_the_storm"])
        fresh = arrive(game, "birds_of_paradise")
        assert damage_player(game.state, 1, 2, fresh) == 4

    def test_a_creature_there_since_last_turn_does_not(self, builder):
        """The boundary, and the reason the card is a build-around rather than a
        blanket doubler."""
        game = board(builder, mine=["neriv_heart_of_the_storm", "birds_of_paradise"])
        old = only_oid(game, "birds_of_paradise")
        assert damage_player(game.state, 1, 2, old) == 2

    def test_stealing_a_creature_is_not_entering(self, builder):
        """The near miss, stated as the board that separates the two fields.

        Their Dragon has been standing there since before this turn. You gain
        control of it now. `entered_turn` says "this turn" -- it must, or the
        creature could attack -- and the printed clause is still false for it.
        """
        game = board(builder, mine=["neriv_heart_of_the_storm"], theirs=["goldspan_dragon"])
        stolen = only_oid(game, "goldspan_dragon", 1)
        change_control(game.state, stolen, 0)
        game.state.bump_chars()

        assert game.state.objects[stolen].controller == 0, "the steal happened"
        assert game.state.objects[stolen].summoning_sick(game.state.turn), (
            "the control change stamped `entered_turn` -- the field this card "
            "must not be reading"
        )
        assert damage_player(game.state, 1, 4, stolen) == 4, "it did not enter"

    def test_a_creature_that_entered_and_was_then_stolen_still_counts(self, builder):
        """The other direction, which the same wrong implementation also gets
        wrong: the ledger is keyed by oid, so an arrival survives the creature
        changing hands."""
        game = board(builder, mine=["neriv_heart_of_the_storm"])
        theirs = arrive(game, "goldspan_dragon", pid=1)
        change_control(game.state, theirs, 0)
        game.state.bump_chars()

        assert damage_player(game.state, 1, 4, theirs) == 8

    def test_an_opponents_new_creature_is_not_doubled(self, builder):
        """"a creature **you control**". The temporal clause does not swallow
        the possessive one."""
        game = board(builder, mine=["neriv_heart_of_the_storm"])
        theirs = arrive(game, "goldspan_dragon", pid=1)
        assert damage_player(game.state, 0, 4, theirs) == 4

    def test_it_doubles_damage_to_anything(self, builder):
        """No "combat" and no named recipient: a fresh creature's damage doubles
        wherever it lands, including onto a permanent and including yours."""
        game = board(builder, mine=["neriv_heart_of_the_storm"], theirs=["goldspan_dragon"])
        fresh = arrive(game, "old_gnawbone")
        target = only_oid(game, "goldspan_dragon", 1)
        assert damage_permanent(game.state, target, 3, fresh) == 6

    def test_the_doubling_ends_with_the_turn(self, builder):
        """The ledger is cleared at cleanup, so "entered this turn" expires with
        the turn. Played out rather than reset by hand: the claim is that the
        same cleanup step which already ends morbid and storm ends this too."""
        game = board(builder, mine=["neriv_heart_of_the_storm"])
        fresh = arrive(game, "birds_of_paradise")
        assert damage_player(game.state, 1, 2, fresh) == 4

        started = game.state.turn
        pass_until(game, lambda g: g.state.turn > started)
        assert damage_player(game.state, 1, 2, fresh) == 2


class TestDracogenesis:
    """"You may cast Dragon spells without paying their mana costs."

    Three claims, and gate 5 could reach none of them: it casts one card and
    stops, so a standing permission over the *next* spell is invisible to it.

    Rule 601.2b's "without paying its mana cost" is a **replacement of the
    payment**, not a reduction of it, and `spell_cost_reduction` -- the nearest
    static, and the one The Ur-Dragon itself prints -- cannot stand in for it at
    any amount: `cost_reduction.cost_reduction` clamps every reduction to the *generic*
    part of a cost, so no discount ever pays a coloured pip. Rule 107.3b is the
    sharper half: a cost reduced to nothing still has an X to announce, and this
    one has X = 0.

    ``t_swelling_wyrmling`` is the prop the X claim needs -- an ``{X}{R}`` Dragon
    that enters with X +1/+1 counters, so 107.3b's zero is a printed number on
    the battlefield rather than a field nobody looks at. The deck has no {X}
    Dragon of its own; it is not a card, only a ruler.
    """

    DRAGON = "ancient_copper_dragon"  # {4}{R}{R} -- pips a discount can never reach
    X_DRAGON = "t_swelling_wyrmling"  # {X}{R} Dragon 0/0, enters with X counters
    NOT_A_DRAGON = "steely_resolve"  # {1}{G} Enchantment from the same deck

    def position(self, builder, *, card, lands=0, genesis=True):
        return board(
            builder,
            mine=["dracogenesis"] if genesis else [],
            hand=[card],
            lands=lands,
        )

    def casts(self, game, card_id):
        oid = next(
            o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id
        )
        return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]

    def test_a_dragon_is_castable_off_an_empty_board(self, builder):
        """Not "cheaper" -- there is nothing to be cheap with. A reduction is
        clamped to the generic part of {4}{R}{R}, so it leaves {R}{R} owing and
        this line does not exist at all."""
        game = self.position(builder, card=self.DRAGON)
        assert [a.cast_free for a in self.casts(game, self.DRAGON)] == [True]

    def test_without_it_the_same_board_offers_nothing(self, builder):
        """The control."""
        game = self.position(builder, card=self.DRAGON, genesis=False)
        assert self.casts(game, self.DRAGON) == []

    def test_casting_it_spends_no_mana(self, builder):
        """Six untapped Mountains: the Dragon was affordable and none of it was
        paid. A discounted cost would have taken the {R}{R} at least."""
        game = self.position(builder, card=self.DRAGON, lands=6)
        free = next(a for a in self.casts(game, self.DRAGON) if a.cast_free)
        game.apply(free)
        settle(game)

        assert count_on_battlefield(game, self.DRAGON, 0) == 1
        assert not any(o.tapped for o in game.state.battlefield_objects(0))
        assert game.state.players[0].mana_pool.total() == 0

    def test_x_is_zero_and_is_never_announced(self, builder):
        """107.3b, as a number on the battlefield.

        The free line is priced on `casting.FREE_COST`, which has no X in it, so
        nothing stops to ask -- and the 0/0 Dragon that enters with X counters
        enters with none and is binned by a state-based action. A reduction to
        zero would have stopped at a `CHOOSE_X` decision, which is the shape of
        the mistake this card exists to rule out.
        """
        game = self.position(builder, card=self.X_DRAGON, lands=3)
        game.apply(next(a for a in self.casts(game, self.X_DRAGON) if a.cast_free))

        assert game.pending().kind is DecisionKind.PRIORITY, "no X was asked for"
        settle(game)
        graveyard = [game.state.objects[o].def_id for o in game.state.players[0].graveyard]
        assert self.X_DRAGON in graveyard
        assert count_on_battlefield(game, self.X_DRAGON, 0) == 0

    def test_the_paid_line_still_announces_an_x(self, builder):
        """The same board, the other line: three Mountains buy X = 2. This is
        the number a "costs {N} less" version gets wrong in one direction or the
        other, and it is the whole difference between the two statics."""
        game = self.position(builder, card=self.X_DRAGON, lands=3)
        game.apply(next(a for a in self.casts(game, self.X_DRAGON) if not a.cast_free))

        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X
        assert decision.context["max_x"] == 2

    def test_paying_normally_is_still_offered(self, builder):
        """"You **may**." A player who wants the mana actually spent -- for an
        Aetherflux Reservoir, a converge count, a "spend mana to cast a creature
        spell" trigger -- must still be able to spend it, so the printed line
        survives beside the free one."""
        game = self.position(builder, card=self.DRAGON, lands=6)
        assert sorted(a.cast_free for a in self.casts(game, self.DRAGON)) == [False, True]

    def test_a_non_dragon_spell_is_unaffected(self, builder):
        """"**Dragon** spells". Steely Resolve is {1}{G} and sits in the same
        deck; off an empty board it is uncastable with Dracogenesis out, exactly
        as it is without it."""
        game = self.position(builder, card=self.NOT_A_DRAGON)
        assert self.casts(game, self.NOT_A_DRAGON) == []

    def test_the_permission_does_not_spend_itself(self, builder):
        """"Dragon spell**s**". It is re-read every time legality builds the
        cast lines, so the second Dragon of the turn is free too -- and so is
        one drawn after the enchantment landed."""
        game = board(
            builder,
            mine=["dracogenesis"],
            hand=[self.DRAGON, "old_gnawbone"],
        )
        game.apply(next(a for a in self.casts(game, self.DRAGON) if a.cast_free))
        settle(game)

        assert [a.cast_free for a in self.casts(game, "old_gnawbone")] == [True]


class TestHellkiteCourser:
    """"When this creature enters, you may put a commander you own from the
    command zone onto the battlefield. It gains haste. Return it to the command
    zone at the beginning of the next end step."

    Gate 5's seat owns no commander and the harness answers "no" to every `may`,
    so the sandbox saw a 6/5 flier and nothing else.

    **One near miss cannot be asserted from this card, and saying so is more
    honest than a test that pretends.** `return_to_hand` over the same binding
    produces an identical board, because `zones.move_object` applies rule
    903.9a -- the commander zone-change replacement -- unconditionally to any
    commander told to go to a hand, and records the move as one `ZONE_CHANGE`
    into the command zone. Every observation the Courser can make is downstream
    of that replacement, so no position built from *this card* separates the two
    ops. What separates them is a permanent that is nobody's commander being
    sent to the command zone, which 903.9a would never do -- and that is
    `tests/unit/commander/test_command_zone.py::TestTheOpNamesTheZoneItself`, which has to
    invent a card to say it. The tests below therefore assert the printed
    outcome and the destinations it is *not*, which is what this layer can see.
    """

    COMMANDER = "the_ur_dragon"  # the deck's own, {4}{W}{U}{B}{R}{G}

    def position(self, builder, *, commander=True):
        return board(
            builder,
            hand=["hellkite_courser"],
            lands=8,
            commanders=[(0, [self.COMMANDER])] if commander else [],
        )

    def put_it_down(self, game):
        """Cast the Courser and take the `may`, choosing the one commander."""
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == "hellkite_courser"
            )
        )
        settle(game, accept=True)

    def oid_of(self, game, card_id: str) -> int:
        """Find one object wherever it is.

        `conftest.only_oid` walks the battlefield only, and half the claims here
        are about a card that has just left it.
        """
        found = [oid for oid, obj in game.state.objects.items() if obj.def_id == card_id]
        assert len(found) == 1, f"expected exactly one {card_id}, found {len(found)}"
        return found[0]

    def test_the_commander_arrives_from_the_command_zone(self, builder):
        game = self.position(builder)
        assert len(game.state.players[0].command) == 1

        self.put_it_down(game)

        assert game.state.players[0].command == []
        assert count_on_battlefield(game, self.COMMANDER, 0) == 1

    def test_it_arrives_with_haste(self, builder):
        """A 10/10 that cannot attack the turn it lands is the card doing
        nothing, and the sentence is three words long."""
        game = self.position(builder)
        self.put_it_down(game)

        commander = only_oid(game, self.COMMANDER, 0)
        assert "haste" in keywords(game, commander)

    def test_declining_leaves_it_in_the_command_zone(self, builder):
        """"you **may**" -- and a declined `may` schedules nothing, so there is
        no delayed return waiting to fire over an empty binding."""
        game = self.position(builder)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == "hellkite_courser"
            )
        )
        settle(game)  # the passive answer declines the `may`

        assert len(game.state.players[0].command) == 1
        assert not game.state.delayed_triggers

    def test_the_return_is_scheduled_for_the_end_step(self, builder):
        game = self.position(builder)
        self.put_it_down(game)

        assert [d.step for d in game.state.delayed_triggers] == ["end_step"]

    def test_it_goes_back_to_the_command_zone(self, builder):
        game = self.position(builder)
        self.put_it_down(game)
        commander = self.oid_of(game, self.COMMANDER)

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)

        assert game.state.objects[commander].zone is Zone.COMMAND
        assert game.state.players[0].command == [commander]
        assert count_on_battlefield(game, self.COMMANDER, 0) == 0

    def test_and_not_to_a_hand_or_a_graveyard(self, builder):
        """The two destinations a mis-written last clause would reach.

        "Return it to the command zone" is not "return it to its owner's hand"
        and not "sacrifice it": either would cost its controller the card, and
        the second would put a commander tax on getting it back. The move is
        also **one** zone change -- out and home, with nothing in between --
        which is what rules out a version that bounced it and let 903.9a catch
        the rebound. (That version would still land in the command zone; see the
        class docstring for why this card cannot tell the two apart.)
        """
        game = self.position(builder)
        self.put_it_down(game)
        commander = self.oid_of(game, self.COMMANDER)

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)

        assert commander not in game.state.players[0].hand
        assert commander not in game.state.players[0].graveyard
        moves = [
            e
            for e in game.state.events
            if e.type == "zone_change" and e.data.get("oid") == commander
        ]
        assert [e.data["to"] for e in moves] == ["battlefield", "command"], (
            "one trip out and one trip home, with no hand in between"
        )

    def test_the_courser_itself_stays(self, builder):
        """Only the borrowed commander goes home. A delayed return pointed at
        the wrong binding would send the Dragon that made it."""
        game = self.position(builder)
        self.put_it_down(game)

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)

        assert count_on_battlefield(game, "hellkite_courser", 0) == 1

    def test_an_empty_command_zone_is_not_an_error(self, builder):
        """The gate-5 position exactly: nothing to put down, and the card still
        resolves and stays."""
        game = self.position(builder, commander=False)
        self.put_it_down(game)

        assert count_on_battlefield(game, "hellkite_courser", 0) == 1


class TestSteelyResolve:
    """"As this enchantment enters, choose a creature type. Creatures of the
    chosen type have shroud."

    Gate 5 takes the first option of any choice and reads the board once, so the
    sandbox recorded an enchantment on the battlefield and a type nobody looked
    at afterwards.

    Two near misses. The first is scope: ``affects.controller`` is ``"any"``,
    and a card that read ``"you"`` would be a one-sided protection spell -- which
    is strictly better, plausible-looking, and not this card. In a Dragon deck
    the symmetry is the drawback, so it has to be asserted on an opponent's
    creature. The second is the type itself: the grant has to follow the choice,
    not attach to whatever the board happens to hold.
    """

    MY_DRAGON = "old_gnawbone"
    MY_NON_DRAGON = "birds_of_paradise"
    THEIR_DRAGON = "goldspan_dragon"

    def position(self, builder, *, choose="Dragon"):
        game = board(
            builder,
            mine=[self.MY_DRAGON, self.MY_NON_DRAGON],
            theirs=[self.THEIR_DRAGON],
            hand=["steely_resolve"],
            lands=2,
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == "steely_resolve"
            )
        )
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_MODE
        index = next(i for i, o in enumerate(decision.options) if o.label == choose)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == index
            )
        )
        settle(game)
        return game

    def test_the_type_is_recorded_on_the_enchantment(self, builder):
        """The choice is a real, stored fact -- `{"chosen_type_of": "self"}`
        reads it back -- and not an index thrown away with the decision."""
        game = self.position(builder)
        assert game.state.objects[only_oid(game, "steely_resolve")].chosen_type == "Dragon"

    def test_creatures_of_the_chosen_type_have_shroud(self, builder):
        game = self.position(builder)
        assert "shroud" in keywords(game, only_oid(game, self.MY_DRAGON))

    def test_creatures_of_other_types_do_not(self, builder):
        """The boundary. Birds of Paradise is a Bird and stays targetable."""
        game = self.position(builder)
        assert "shroud" not in keywords(game, only_oid(game, self.MY_NON_DRAGON))

    def test_it_reaches_every_player_s_creatures(self, builder):
        """"Creatures of the chosen type", with no possessive. The symmetry is
        the drawback, and a card that granted shroud only to yours would be a
        different and much better one."""
        game = self.position(builder)
        assert "shroud" in keywords(game, only_oid(game, self.THEIR_DRAGON, 1))

    def test_choosing_another_type_moves_the_grant(self, builder):
        """The grant follows the choice. Choosing Bird takes the shroud off
        every Dragon on the board and puts it on the 0/1 -- which is what makes
        the stored type load bearing rather than decorative."""
        game = self.position(builder, choose="Bird")
        assert "shroud" in keywords(game, only_oid(game, self.MY_NON_DRAGON))
        assert "shroud" not in keywords(game, only_oid(game, self.MY_DRAGON))
        assert "shroud" not in keywords(game, only_oid(game, self.THEIR_DRAGON, 1))

    def test_without_the_enchantment_nothing_has_shroud(self, builder):
        """The control."""
        game = board(
            builder,
            mine=[self.MY_DRAGON, self.MY_NON_DRAGON],
            theirs=[self.THEIR_DRAGON],
        )
        for oid in (
            only_oid(game, self.MY_DRAGON),
            only_oid(game, self.MY_NON_DRAGON),
            only_oid(game, self.THEIR_DRAGON, 1),
        ):
            assert "shroud" not in keywords(game, oid)

    def test_a_shrouded_dragon_cannot_be_targeted(self, builder):
        """Shroud is what the card buys, so it is read once as a rules fact and
        not only as a word in a keyword set."""
        from automtg.engine.targeting import can_be_targeted

        game = self.position(builder)
        dragon = only_oid(game, self.MY_DRAGON)
        birds = only_oid(game, self.MY_NON_DRAGON)

        # Asked for *its own controller*, which is where shroud and hexproof
        # part company (702.18a): a hexproof-shaped implementation would let
        # player 0 target their own Dragon all day.
        assert not can_be_targeted(game.state, 0, dragon)
        assert not can_be_targeted(game.state, 1, dragon)
        assert can_be_targeted(game.state, 0, birds)
