"""The Lucy MacLean, Positively Armed deck: the token cards, doing what they print.

`test_lucy_maclean_import.py` pins that every card in this list resolves
`native`. That is a statement about the importer, not about the cards, and the
authoring gate that let them in measured most of the interesting ones at almost
nothing. Gate 5 casts a card once, in one sandbox, and reads the board -- and its
documented limits are exactly where this deck lives:

- **Nothing makes a token after the card under test.** Lucy's Golden Rule,
  Divine Visitation's replacement and Intangible Virtue's anthem all act on a
  token *entering*, and their recorded expectation is "it is on the
  battlefield".
- **It never activates an ability, attacks, or reaches an end step.** Halo
  Fountain is three activated abilities, Hero of Bladehold is two attack
  triggers, Keeper of the Accord is two end-step triggers on an *opponent's*
  turn, and Felidar Retreat is a landfall trigger the sandbox never plays a land
  for.

So these are the observations, a class per card quoting its printed text. Each
pins a near miss as well: Golden Rule fires once a turn and draws only when an
opponent got the copy, Visitation replaces only *your* tokens, the Keeper does
nothing on your own end step, and so on.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars, has_keyword
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import _default_answer, action_for_card, oids_of, pass_until

LUCY = "lucy_maclean_positively_armed"
HERO = "hero_of_bladehold"
VISITATION = "divine_visitation"
VIRTUE = "intangible_virtue"
RETREAT = "felidar_retreat"
KEEPER = "keeper_of_the_accord"
FOUNTAIN = "halo_fountain"

ALARM = "raise_the_alarm"  # {1}{W} Instant: create two 1/1 white Soldier tokens
SOLDIER = "soldier_1_1_w"
ANGEL = "angel_4_4_w_flying_vigilance"
CAT_BEAST = "cat_beast_2_2_w"
CITIZEN = "citizen_1_1_gw"
BEAR = "t_bear"  # a vanilla 2/2
# A castable instant in each seat's hand: with no play available to anybody the
# engine's auto-pass runs whole turns inside one `apply` and overshoots the step
# under test.
ANCHOR = "t_plain_instant"


def settle(game, *, yes: bool = True, mode: int = 0, limit: int = 200) -> None:
    """Let the stack empty, saying ``yes`` to every `MAY` (and taking the first
    card a search offers) and picking ``mode``."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if yes else ActionKind.NO
            game.apply(next(a for a in actions if a.kind is want))
            continue
        if decision.kind is DecisionKind.CHOOSE_MODE:
            game.apply(next(a for a in actions if a.kind is ActionKind.CHOOSE and a.choice == mode))
            continue
        if decision.kind is DecisionKind.CHOOSE_OBJECTS and yes:
            # A search you said yes to takes what it finds; the passive default
            # would finish the declaration with nothing chosen.
            pick = next((a for a in actions if a.kind is ActionKind.CHOOSE), None)
            if pick is not None:
                game.apply(pick)
                continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def cast(game, card_id: str, *, yes: bool = True, mode: int = 0) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    settle(game, yes=yes, mode=mode)


def position(builder, mine=(), theirs=(), *, hand=(ALARM,), active: int = 0):
    """Each seat with three Plains, an anchor, and a counted library."""
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 3 + list(mine))
        .battlefield(1, ["plains"] * 3 + list(theirs))
        .hand(active, [*hand, ANCHOR])
        .hand(1 - active, [ANCHOR])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .active(active)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


class TestLucyMacLean:
    """"Golden Rule -- Whenever a token enters, you may have target player other
    than its controller create a token that's a copy of it, then you draw a card
    if an opponent created a token this way. Do this only once each turn." """

    def test_your_token_is_copied_for_an_opponent_and_you_draw(self, builder):
        game = position(builder, mine=[LUCY])
        cast(game, ALARM)
        assert len(oids_of(game, SOLDIER, 0)) == 2
        [copy] = oids_of(game, SOLDIER, 1)
        assert game.state.objects[copy].is_token
        assert len(game.state.players[0].library) == 20 - 1
        assert len(game.state.players[1].library) == 20

    def test_only_once_each_turn(self, builder):
        """Raise the Alarm makes two tokens and Felidar Retreat's Cat Beast a
        third: one copy for the whole turn, not three."""
        game = position(builder, mine=[LUCY, RETREAT], hand=(ALARM, "plains"))
        cast(game, ALARM)
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "plains"))
        settle(game, mode=0)
        assert len(oids_of(game, CAT_BEAST, 0)) == 1
        assert len(oids_of(game, SOLDIER, 1)) == 1
        assert oids_of(game, CAT_BEAST, 1) == []
        assert len(game.state.players[0].library) == 20 - 1

    def test_declining_copies_nothing_and_draws_nothing(self, builder):
        game = position(builder, mine=[LUCY])
        cast(game, ALARM, yes=False)
        assert len(oids_of(game, SOLDIER, 0)) == 2
        assert oids_of(game, SOLDIER, 1) == []
        assert len(game.state.players[0].library) == 20

    def test_an_opponents_token_is_copied_for_you_without_a_draw(self, builder):
        """"Whenever a token enters" is anybody's token, and the copy goes to a
        player other than its controller -- you. You are not an opponent, so
        nobody draws."""
        game = position(builder, mine=[LUCY], active=1)
        cast(game, ALARM)
        assert len(oids_of(game, SOLDIER, 1)) == 2
        assert len(oids_of(game, SOLDIER, 0)) == 1
        assert len(game.state.players[0].library) == 20
        assert len(game.state.players[1].library) == 20


class TestHeroOfBladehold:
    """"Battle cry (Whenever this creature attacks, each other attacking creature
    gets +1/+0 until end of turn.) Whenever this creature attacks, create two 1/1
    white Soldier creature tokens that are tapped and attacking." """

    def attack(self, builder):
        game = position(builder, mine=[HERO, BEAR], hand=())
        pass_until(game, lambda g: g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
        for oid in [*oids_of(game, HERO, 0), *oids_of(game, BEAR, 0)]:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
                )
            )
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )
        settle(game)
        return game

    def test_two_soldiers_enter_tapped_and_attacking(self, builder):
        game = self.attack(builder)
        soldiers = oids_of(game, SOLDIER, 0)
        assert len(soldiers) == 2
        for oid in soldiers:
            assert game.state.objects[oid].tapped
            assert oid in game.state.combat.attackers

    def test_battle_cry_pumps_the_others_but_not_the_hero(self, builder):
        game = self.attack(builder)
        [hero] = oids_of(game, HERO, 0)
        [bear] = oids_of(game, BEAR, 0)
        assert (chars(game.state, hero).power, chars(game.state, hero).toughness) == (3, 4)
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (3, 2)

    def test_the_unblocked_attack_deals_ten(self, builder):
        """Hero 3, the bear 2 + 1, and the soldiers -- ordered ahead of the battle
        cry so it reaches them -- 1 + 1 each."""
        game = self.attack(builder)
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)
        assert game.state.players[1].life == 40 - 10


class TestDivineVisitation:
    """"If one or more creature tokens would be created under your control, that
    many 4/4 white Angel creature tokens with flying and vigilance are created
    instead." """

    def test_your_soldiers_become_angels(self, builder):
        game = position(builder, mine=[VISITATION])
        cast(game, ALARM)
        assert oids_of(game, SOLDIER, 0) == []
        angels = oids_of(game, ANGEL, 0)
        assert len(angels) == 2
        for oid in angels:
            c = chars(game.state, oid)
            assert (c.power, c.toughness) == (4, 4)
            assert has_keyword(game.state, oid, "flying")
            assert has_keyword(game.state, oid, "vigilance")

    def test_an_opponents_tokens_are_untouched(self, builder):
        game = position(builder, mine=[VISITATION], active=1)
        cast(game, ALARM)
        assert len(oids_of(game, SOLDIER, 1)) == 2
        assert oids_of(game, ANGEL) == []


class TestIntangibleVirtue:
    """"Creature tokens you control get +1/+1 and have vigilance." """

    def test_your_tokens_only(self, builder):
        """Lucy hands the opponent a copy of a soldier: theirs stays a 1/1, and
        Lucy herself is no token."""
        game = position(builder, mine=[VIRTUE, LUCY])
        cast(game, ALARM)
        for oid in oids_of(game, SOLDIER, 0):
            assert (chars(game.state, oid).power, chars(game.state, oid).toughness) == (2, 2)
            assert has_keyword(game.state, oid, "vigilance")
        [theirs] = oids_of(game, SOLDIER, 1)
        assert (chars(game.state, theirs).power, chars(game.state, theirs).toughness) == (1, 1)
        assert not has_keyword(game.state, theirs, "vigilance")
        [lucy] = oids_of(game, LUCY, 0)
        assert (chars(game.state, lucy).power, chars(game.state, lucy).toughness) == (3, 5)


class TestFelidarRetreat:
    """"Landfall -- Whenever a land you control enters, choose one --
    * Create a 2/2 white Cat Beast creature token.
    * Put a +1/+1 counter on each creature you control. Those creatures gain
      vigilance until end of turn." """

    def land(self, builder, mode: int):
        game = position(builder, mine=[RETREAT, BEAR], theirs=[BEAR], hand=("plains",))
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "plains"))
        settle(game, mode=mode)
        return game

    def test_first_mode_makes_a_cat_beast(self, builder):
        game = self.land(builder, 0)
        [cat] = oids_of(game, CAT_BEAST, 0)
        assert (chars(game.state, cat).power, chars(game.state, cat).toughness) == (2, 2)
        [bear] = oids_of(game, BEAR, 0)
        assert game.state.objects[bear].counters.get("+1/+1", 0) == 0

    def test_second_mode_counters_your_creatures_not_theirs(self, builder):
        game = self.land(builder, 1)
        assert oids_of(game, CAT_BEAST) == []
        [mine] = oids_of(game, BEAR, 0)
        [theirs] = oids_of(game, BEAR, 1)
        assert game.state.objects[mine].counters == {"+1/+1": 1}
        assert has_keyword(game.state, mine, "vigilance")
        assert game.state.objects[theirs].counters.get("+1/+1", 0) == 0
        assert not has_keyword(game.state, theirs, "vigilance")


class TestKeeperOfTheAccord:
    """"At the beginning of each opponent's end step, if that player controls
    more creatures than you, create a 1/1 white Soldier creature token.
    At the beginning of each opponent's end step, if that player controls more
    lands than you, you may search your library for a basic Plains card, put it
    onto the battlefield tapped, then shuffle." """

    def end_step(self, builder, *, theirs, their_lands: int, active: int = 1, yes: bool = True):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", KEEPER])
            .battlefield(1, ["plains"] * their_lands + list(theirs))
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, ["plains"] * 10)
            .library(1, ["plains"] * 10)
            .active(active)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        pass_until(game, lambda g: g.state.step is Step.END_STEP)
        settle(game, yes=yes)
        return game

    def test_behind_on_both_you_get_a_soldier_and_a_tapped_plains(self, builder):
        game = self.end_step(builder, theirs=[BEAR, BEAR], their_lands=2)
        assert len(oids_of(game, SOLDIER, 0)) == 1
        plains = oids_of(game, "plains", 0)
        assert len(plains) == 2
        assert sum(game.state.objects[o].tapped for o in plains) == 1
        assert len(game.state.players[0].library) == 10 - 1

    def test_level_on_both_nothing(self, builder):
        """One creature and one land each: "more", not "at least as many"."""
        game = self.end_step(builder, theirs=[BEAR], their_lands=1)
        assert oids_of(game, SOLDIER, 0) == []
        assert len(oids_of(game, "plains", 0)) == 1
        assert len(game.state.players[0].library) == 10

    def test_not_on_your_own_end_step(self, builder):
        game = self.end_step(builder, theirs=[BEAR, BEAR], their_lands=2, active=0)
        assert oids_of(game, SOLDIER, 0) == []
        assert len(oids_of(game, "plains", 0)) == 1

    def test_the_search_is_a_may(self, builder):
        game = self.end_step(builder, theirs=[BEAR, BEAR], their_lands=2, yes=False)
        assert len(oids_of(game, SOLDIER, 0)) == 1
        assert len(oids_of(game, "plains", 0)) == 1
        assert len(game.state.players[0].library) == 10


class TestHaloFountain:
    """"{W}, {T}, Untap a tapped creature you control: Create a 1/1 green and
    white Citizen creature token." (Its draw and win abilities cost two and
    fifteen untaps.)"""

    def fountain(self, builder, *, bear_tapped: bool):
        return (
            builder(players=2)
            .battlefield(0, ["plains", "plains", FOUNTAIN])
            .battlefield(0, [BEAR], tapped=bear_tapped)
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_untapping_a_creature_makes_a_citizen(self, builder):
        game = self.fountain(builder, bear_tapped=True)
        [fountain] = oids_of(game, FOUNTAIN, 0)
        [bear] = oids_of(game, BEAR, 0)
        line = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == fountain and a.ability_index == 0
        )
        game.apply(line)
        settle(game)
        [citizen] = oids_of(game, CITIZEN, 0)
        assert (chars(game.state, citizen).power, chars(game.state, citizen).toughness) == (1, 1)
        assert not game.state.objects[bear].tapped
        assert game.state.objects[fountain].tapped

    def test_no_tapped_creature_no_activation(self, builder):
        """And one tapped creature is not the two the draw ability needs."""
        game = self.fountain(builder, bear_tapped=False)
        assert not [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE]
        game = self.fountain(builder, bear_tapped=True)
        indices = {a.ability_index for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE}
        assert indices == {0}
