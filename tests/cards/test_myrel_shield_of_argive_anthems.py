"""The Myrel deck's anthems, keyword sharing and token multipliers, doing what they print.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card once, in one fixed
sandbox, and reads the board. Three of its documented limits bite this group
harder than any other in the deck:

- **It never activates an ability.** Prava's ``{3}{W}`` and Mondrak's sacrifice
  are the only repeatable token sources in the deck, and the harness stops before
  either of them -- which also means no *later* token creation exists for
  Mondrak's and Exalted Sunborn's replacements to intercept.
- **A trigger that never fires cannot be asserted.** Nothing in that position
  enters, dies, gains life or reaches a combat *after* the card under test, so
  for Cathars' Crusade, Goldnight Commander, Soul Warden, Ocelot Pride, Anafenza
  and both Odrics the recorded expectation is "it entered, and nothing
  misfired".
- **It reads one board, not two.** A static anthem is a claim about *whose*
  creatures and *which* ones, and a sandbox with one player's board and one
  creature cannot tell a right anthem from one that also pumps the wrong side,
  itself, or a nontoken.

So the authoring expectations are floors, and these are the observations. Each
class is one card, each test names the printed sentence it drives, and every
"whose", "other", "for each" and "until end of turn" in this group is pinned from
*both* sides -- because a mis-written anthem still produces bigger numbers, and a
test that only checks the number goes green.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.primitives import add_counters, create_token
from tests.conftest import (
    _default_answer,
    activations,
    find_action,
    keywords,
    oids_of,
    only_oid,
    pass_until,
)

# A castable instant in a hand, and it is load bearing rather than scenery. With
# no play available to anybody the engine's auto-pass runs from one spell
# resolving through cleanup and into the next turn inside a single `apply` --
# which wipes every "until end of turn" grant before it can be read and rolls
# past the end step a trigger was waiting in. Every seat that has to be seen
# stopping holds one.
ANCHOR = "t_plain_instant"  # {W} instant, "You gain 1 life"
BEAR = "t_bear"  # a vanilla nontoken 2/2
# A 1/1 rather than the obvious 2/2, and the difference is Angelic Aberration:
# "base power or toughness 1 or less" cannot reach a Bear, so the creatures that
# have to be sacrificeable are Squires and the ones that must be safe are Bears.
SQUIRE = "t_small"  # a vanilla nontoken 1/1
FIRST_STRIKER = "t_first_striker"  # 2/2, first strike printed
LIFELINKER = "t_lifelinker"  # 2/2, lifelink printed

# Prava's own ability is the token source for every doubling and "for each"
# test: it is the deck's only token creation that needs neither an attack step
# nor a creature dying, so a replacement can be measured off one activation.
TOKEN_MAKER = "prava_of_the_steel_legion"
MAKER_ABILITY = 1  # ability 0 is the static buff; 1 is "{3}{W}: Create a … Soldier"
SOLDIER = "soldier_1_1_w"
CAT = "cat_1_1_w"
SPIRIT = "spirit_2_2_w"
ANGEL = "eldrazi_angel_4_4_c_flying_vigilance"
TREASURE = "treasure_token"
CITIZEN = "citizen_1_1_gw"


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _settled(game) -> bool:
    """Nothing on the stack, nothing waiting to go on it, nobody mid-resolution.

    ``pending_triggers`` is in the condition and is load bearing. A test that
    puts a token onto the battlefield with `create_token` is not inside a
    resolution, so the stack is *already* empty and the arrival's triggers are
    still queued -- a settle that read the stack alone would return before they
    were ever put on it and measure nothing.
    """
    pending = game.pending()
    return (
        not game.state.stack
        and not game.state.pending_triggers
        and (pending is None or pending.kind is DecisionKind.PRIORITY)
    )


def settle(game) -> None:
    pass_until(game, _settled)


def _can_cast(game, card_id: str, pid: int) -> bool:
    pending = game.pending()
    if pending is None or pending.player != pid:
        return False
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


def cast_action(game, card_id: str):
    return next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )


def cast(game, card_id: str, pid: int = 0) -> int:
    """Cast ``card_id`` from ``pid``'s hand and let it resolve. Returns its oid."""
    pass_until(game, lambda g: _can_cast(g, card_id, pid))
    action = cast_action(game, card_id)
    game.apply(action)
    settle(game)
    return action.source


def activate(game, oid: int, index: int) -> None:
    game.apply(activations(game, oid, index)[0])
    settle(game)


def make_tokens(game, pid: int = 0, count: int = 1) -> list[int]:
    """Put ``count`` Soldier tokens onto the battlefield under ``pid``, and settle.

    Used wherever the assertion is about a *token's own size*: Prava is the
    deck's token source and Prava is also a +1/+4 anthem on tokens, so a test
    that read a Prava-made Soldier's power could not say which half it was
    seeing. One engine call, then the arrival triggers resolve exactly as they
    would from a card.
    """
    made = create_token(game.state, SOLDIER, pid, count=count)
    settle(game)
    return made


def tokens(game, def_id: str, pid: int | None = None) -> list:
    return [o for o in game.state.battlefield_objects(pid) if o.def_id == def_id and o.is_token]


def size(game, oid: int) -> tuple[int, int]:
    derived = chars(game.state, oid)
    return derived.power, derived.toughness


def _at(game, kind: DecisionKind) -> bool:
    pending = game.pending()
    return pending is not None and pending.kind is kind


def at_decision(game, kind: DecisionKind):
    """Pass until ``kind`` is the pending decision, and hand it back."""
    pass_until(game, lambda g: _at(g, kind))
    pending = game.pending()
    assert pending is not None and pending.kind is kind, f"never reached {kind}"
    return pending


def choose(game, value: int) -> None:
    game.apply(find_action(game, ActionKind.CHOOSE, choice=value))


def to_step(game, step: Step, active: int = 0) -> None:
    pass_until(game, lambda g: g.state.step is step and g.state.active_player == active)


def counters(game, oid: int, kind: str = "+1/+1") -> int:
    return game.state.objects[oid].counters.get(kind, 0)


def cast_aberration(game, *, sacrifice: bool) -> None:
    """Cast Angelic Aberration -- by whoever holds priority -- and answer its sacrifice.

    The choice has to be driven either way round. ``sacrifice=False`` is not the
    lazy path: "any number" includes none, so the passive answer to the
    declaration is to sacrifice nothing -- which is what `pass_until` would do on
    its own, and it is a real mode of the card rather than a test that forgot to
    choose. With nothing on the board small enough, the effect asks nothing at
    all, which is why the wait below accepts a settled game as well.
    """
    game.apply(cast_action(game, "angelic_aberration"))
    pass_until(game, lambda g: _at(g, DecisionKind.CHOOSE_OBJECTS) or _settled(g))
    while _at(game, DecisionKind.CHOOSE_OBJECTS):
        picks = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
        if sacrifice and picks:
            game.apply(picks[0])
            continue
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def attack_with_all(game, *, skip: str | None = None) -> int:
    """Declare every attacker the game offers, optionally holding one card back."""
    at_decision(game, DecisionKind.DECLARE_ATTACKERS)
    while True:
        adds = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER
            and (skip is None or game.state.objects[a.source].def_id != skip)
        ]
        if not adds:
            break
        game.apply(adds[0])
    declared = len(game.state.combat.attackers)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    return declared


def blockers_asked(game, limit: int = 200) -> set[int]:
    """Which seats were asked to declare blocks, through to the end of combat."""
    asked: set[int] = set()
    for _ in range(limit):
        decision = game.pending()
        if decision is None or game.state.step is Step.END_OF_COMBAT:
            break
        if decision.kind is DecisionKind.DECLARE_BLOCKERS:
            asked.add(decision.player)
        game.apply(_default_answer(game, decision))
    return asked


# ----------------------------------------------------------------------
# the counter and token multipliers
# ----------------------------------------------------------------------


class TestCatharsCrusade:
    """ "Whenever a creature you control enters, put a +1/+1 counter on each creature you control."

    One creature entering is already pinned elsewhere. The interesting case is
    **two at once**: the trigger is per arrival, so a doubled token creation
    fires it twice and every creature ends on two counters, the newcomers
    included -- both are already on the battlefield when the first trigger
    resolves.
    """

    def position(self, builder, *, doubler: bool):
        board = ["cathars_crusade", TOKEN_MAKER, *["plains"] * 4]
        if doubler:
            board.insert(1, "mondrak_glory_dominus")
        return (
            builder(players=2)
            .battlefield(0, board)
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_two_creatures_entering_at_once_is_two_counters_each(self, builder):
        """ "For each" is the whole card: two arrivals, two triggers, two counters."""
        game = self.position(builder, doubler=True)
        activate(game, only_oid(game, TOKEN_MAKER), MAKER_ABILITY)

        soldiers = tokens(game, SOLDIER, 0)
        assert len(soldiers) == 2, "Mondrak doubled the creation"
        for obj in soldiers:
            assert counters(game, obj.oid) == 2, "a token that arrived with the other one"
        assert counters(game, only_oid(game, TOKEN_MAKER)) == 2
        assert counters(game, only_oid(game, "mondrak_glory_dominus")) == 2

    def test_one_creature_entering_is_one_counter(self, builder):
        """The control. Without it the test above is just "a counter appeared"."""
        game = self.position(builder, doubler=False)
        activate(game, only_oid(game, TOKEN_MAKER), MAKER_ABILITY)

        assert len(tokens(game, SOLDIER, 0)) == 1
        assert counters(game, only_oid(game, TOKEN_MAKER)) == 1

    def test_an_opponents_arrival_does_not_count(self, builder):
        """ "A creature **you control** enters." Their Soldier is not your trigger."""
        game = (
            builder(players=2)
            .battlefield(0, ["cathars_crusade", BEAR, "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        make_tokens(game, pid=1)

        assert counters(game, bear) == 0


class TestMondrakGloryDominus:
    """ "If one or more tokens would be created under your control, twice that many of
    those tokens are created instead." / "{1}{W/P}{W/P}, Sacrifice two other artifacts
    and/or creatures: Put an indestructible counter on Mondrak."

    A replacement on an event the sandbox never reaches, and an ability the
    harness never activates: the gate could only say Mondrak is on the
    battlefield.
    """

    def test_a_token_creation_is_doubled(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["mondrak_glory_dominus", TOKEN_MAKER, *["plains"] * 4])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        activate(game, only_oid(game, TOKEN_MAKER), MAKER_ABILITY)

        assert len(tokens(game, SOLDIER, 0)) == 2

    def test_without_it_the_same_activation_makes_one(self, builder):
        """The control."""
        game = (
            builder(players=2)
            .battlefield(0, [TOKEN_MAKER, *["plains"] * 4])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        activate(game, only_oid(game, TOKEN_MAKER), MAKER_ABILITY)

        assert len(tokens(game, SOLDIER, 0)) == 1

    def test_a_nontoken_permanent_is_not_doubled(self, builder):
        """ "**Tokens** would be created" -- a creature spell resolving is not that.

        The near miss is a doubler written as "a permanent entering", which would
        make a second Bear out of thin air.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["mondrak_glory_dominus", "forest", "forest"])
            .battlefield(1, ["plains"])
            .hand(0, [BEAR])
            .hand(1, [ANCHOR])
            .build()
        )
        cast(game, BEAR)

        assert len(oids_of(game, BEAR, 0)) == 1
        assert tokens(game, BEAR, 0) == []

    def test_an_opponents_token_is_not_doubled(self, builder):
        """ "Under **your** control." The replacement belongs to the token's controller."""
        game = (
            builder(players=2)
            .battlefield(0, ["mondrak_glory_dominus"])
            .battlefield(1, [TOKEN_MAKER, *["plains"] * 4])
            .active(1)
            .build()
        )
        activate(game, only_oid(game, TOKEN_MAKER, 1), MAKER_ABILITY)

        assert len(tokens(game, SOLDIER, 1)) == 1

    def test_the_sacrifice_ability_puts_a_working_indestructible_counter(self, builder):
        """Two *other* permanents go, and the counter is a keyword rather than a note."""
        game = (
            builder(players=2)
            .battlefield(0, ["mondrak_glory_dominus", SQUIRE, SQUIRE, *["plains"] * 3])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        mondrak = only_oid(game, "mondrak_glory_dominus")
        assert "indestructible" not in keywords(game, mondrak), "the premise"

        activate(game, mondrak, 1)

        assert counters(game, mondrak, "indestructible") == 1
        assert "indestructible" in keywords(game, mondrak)
        assert oids_of(game, SQUIRE, 0) == [], "two others, and Mondrak is not one of them"
        assert mondrak in game.state.battlefield


class TestExaltedSunborn:
    """ "If one or more tokens would be created under your control, twice that many of
    those tokens are created instead." / "Warp {1}{W}."

    The same replacement as Mondrak's, and the reason both are tested is what
    happens when they are on the battlefield together: two replacements of one
    event, each applying once (614.5), compound.
    """

    def position(self, builder, board):
        return (
            builder(players=2)
            .battlefield(0, [*board, TOKEN_MAKER, *["plains"] * 4])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_it_doubles_a_token_creation(self, builder):
        game = self.position(builder, ["exalted_sunborn"])
        activate(game, only_oid(game, TOKEN_MAKER), MAKER_ABILITY)

        assert len(tokens(game, SOLDIER, 0)) == 2

    def test_two_doublers_make_four_and_not_three(self, builder):
        """The near miss is a doubler family that *sums*: 1 + 1 + 1 is three."""
        game = self.position(builder, ["exalted_sunborn", "mondrak_glory_dominus"])
        activate(game, only_oid(game, TOKEN_MAKER), MAKER_ABILITY)

        assert len(tokens(game, SOLDIER, 0)) == 4

    def test_the_warp_cost_buys_it_early_and_takes_it_back(self, builder):
        """ "Warp {1}{W} … Exile this creature at the beginning of the next end step."

        A {3}{W}{W} creature cast off two lands, which is the whole of warp, and
        the exile that pays for it. Casting it again *from exile* on a later turn
        is the half this does not reach.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["plains", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, ["exalted_sunborn"])
            .hand(1, [ANCHOR])
            .build()
        )
        sunborn = cast(game, "exalted_sunborn")
        assert game.state.objects[sunborn].zone is Zone.BATTLEFIELD
        assert keywords(game, sunborn) >= {"flying", "lifelink"}

        to_step(game, Step.END_STEP)
        settle(game)
        assert game.state.objects[sunborn].zone is Zone.EXILE


class TestOcelotPride:
    """ "At the beginning of your end step, if you gained life this turn, create a 1/1
    white Cat creature token. Then if you have the city's blessing, for each token you
    control that entered this turn, create a token that's a copy of it."

    Three gates on one trigger -- the end step, the life gained, the blessing --
    and the sandbox reaches none of them.
    """

    def position(self, builder, *, lands: int):
        return (
            builder(players=2)
            .battlefield(0, ["ocelot_pride", *["plains"] * lands])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_no_life_gained_means_no_cat(self, builder):
        """The intervening if, and the near miss: an unconditional end-step token."""
        game = self.position(builder, lands=2)
        to_step(game, Step.END_STEP)
        settle(game)

        assert game.state.players[0].life == 40, "the premise -- nothing gained life"
        assert tokens(game, CAT, 0) == []

    def test_gaining_life_makes_one_cat(self, builder):
        game = self.position(builder, lands=2)
        cast(game, ANCHOR)
        assert game.state.players[0].life == 41

        to_step(game, Step.END_STEP)
        settle(game)

        assert not game.state.players[0].has_city_s_blessing, "three permanents"
        assert len(tokens(game, CAT, 0)) == 1, "the Cat, and no copy of it"

    def test_the_citys_blessing_copies_the_turns_tokens(self, builder):
        """Ten permanents, so Ascend has fired, and the Cat copies itself once."""
        game = self.position(builder, lands=9)
        assert game.state.players[0].has_city_s_blessing

        cast(game, ANCHOR)
        to_step(game, Step.END_STEP)
        settle(game)

        assert len(tokens(game, CAT, 0)) == 2, "the Cat plus one copy"

    def test_every_token_that_entered_this_turn_is_copied_and_not_just_the_cat(self, builder):
        """ "For **each** token you control that entered this turn" -- the near
        miss copies the Cat it just made and nothing else, which is the reading
        the printed wording is one word away from."""
        game = self.position(builder, lands=9)
        make_tokens(game)
        cast(game, ANCHOR)

        to_step(game, Step.END_STEP)
        settle(game)

        assert len(tokens(game, CAT, 0)) == 2, "the Cat and its copy"
        assert len(tokens(game, SOLDIER, 0)) == 2, "the Soldier entered this turn too"


# ----------------------------------------------------------------------
# the static anthems
# ----------------------------------------------------------------------


class TestIntangibleVirtue:
    """ "Creature tokens you control get +1/+1 and have vigilance."

    Two "whose" questions in eleven words, and neither is reachable from a
    one-board sandbox: *tokens*, and *you control*.
    """

    def test_a_token_gets_the_buff_and_the_keyword(self, builder):
        game = builder(players=2).battlefield(0, ["intangible_virtue", BEAR]).build()
        (soldier,) = make_tokens(game)

        assert size(game, soldier) == (2, 2)
        assert "vigilance" in keywords(game, soldier)

    def test_a_nontoken_creature_gets_neither(self, builder):
        """ "Creature **tokens**." The near miss is a plain team anthem."""
        game = builder(players=2).battlefield(0, ["intangible_virtue", BEAR]).build()
        make_tokens(game)
        bear = only_oid(game, BEAR, 0)

        assert size(game, bear) == (2, 2)
        assert "vigilance" not in keywords(game, bear)

    def test_their_virtue_does_not_buff_your_token(self, builder):
        """ "Tokens **you control**." An anthem read off the wrong seat passes a
        naive test, because the numbers still go up."""
        game = builder(players=2).battlefield(1, ["intangible_virtue"]).build()
        (soldier,) = make_tokens(game, pid=0)

        assert size(game, soldier) == (1, 1)
        assert "vigilance" not in keywords(game, soldier)


class TestPravaOfTheSteelLegion:
    """ "During your turn, creature tokens you control get +1/+4." / "{3}{W}: Create a
    1/1 white Soldier creature token."

    A conditioned anthem and an activated ability: the gate saw a 1/4 on the
    battlefield and nothing else.
    """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [TOKEN_MAKER, BEAR, "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_a_token_gets_plus_one_plus_four_on_your_turn(self, builder):
        game = self.position(builder)
        (soldier,) = make_tokens(game)

        assert game.state.active_player == 0, "the premise"
        assert size(game, soldier) == (2, 5)

    def test_a_nontoken_creature_and_prava_itself_get_nothing(self, builder):
        """ "Creature **tokens**", and Prava is not one. The near miss pumps the
        whole team, which on this board is +1/+4 on a 1/4 legend."""
        game = self.position(builder)
        make_tokens(game)

        assert size(game, only_oid(game, BEAR, 0)) == (2, 2)
        assert size(game, only_oid(game, TOKEN_MAKER)) == (1, 4)

    def test_the_buff_is_gone_on_an_opponents_turn(self, builder):
        """ "**During your turn**" -- a condition the sandbox's single turn hides."""
        game = self.position(builder)
        (soldier,) = make_tokens(game)
        assert size(game, soldier) == (2, 5)

        pass_until(game, lambda g: g.state.active_player == 1 and g.pending() is not None)

        assert size(game, soldier) == (1, 1)

    def test_the_ability_makes_one_soldier_token(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [TOKEN_MAKER, *["plains"] * 4])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        activate(game, only_oid(game, TOKEN_MAKER), MAKER_ABILITY)

        made = tokens(game, SOLDIER, 0)
        assert len(made) == 1
        assert made[0].is_token, "a token, which is what its own anthem then reads"


class TestBastionProtector:
    """ "Commander creatures you control get +2/+2 and have indestructible."

    The narrowest "whose" in the deck: not your creatures, not every commander --
    the commanders *you control*. The sandbox has no commander on the
    battlefield at all, so the gate could assert none of it.
    """

    def position(self, builder, *, mine: bool = True, theirs: bool = False):
        game = (
            builder(players=2)
            .battlefield(0, ["bastion_protector", "myrel_shield_of_argive", BEAR])
            .battlefield(1, ["myrel_shield_of_argive"])
            .build()
        )
        if mine:
            game.state.objects[only_oid(game, "myrel_shield_of_argive", 0)].is_commander = True
        if theirs:
            game.state.objects[only_oid(game, "myrel_shield_of_argive", 1)].is_commander = True
        game.state.bump_chars()
        return game

    def test_your_commander_is_bigger_and_indestructible(self, builder):
        game = self.position(builder)
        myrel = only_oid(game, "myrel_shield_of_argive", 0)

        assert size(game, myrel) == (5, 6), "a printed 3/4"
        assert "indestructible" in keywords(game, myrel)

    def test_a_noncommander_creature_you_control_gets_nothing(self, builder):
        """ "**Commander** creatures." The near miss is a team anthem."""
        game = self.position(builder)
        bear = only_oid(game, BEAR, 0)

        assert size(game, bear) == (2, 2)
        assert "indestructible" not in keywords(game, bear)

    def test_the_same_legend_without_the_flag_gets_nothing(self, builder):
        """The boundary is the flag and not the card: an unflagged Myrel is a 3/4."""
        game = self.position(builder, mine=False)
        myrel = only_oid(game, "myrel_shield_of_argive", 0)

        assert size(game, myrel) == (3, 4)
        assert "indestructible" not in keywords(game, myrel)

    def test_an_opponents_commander_gets_nothing(self, builder):
        """ "Commander creatures **you control**"."""
        game = self.position(builder, theirs=True)
        theirs = only_oid(game, "myrel_shield_of_argive", 1)

        assert size(game, theirs) == (3, 4)
        assert "indestructible" not in keywords(game, theirs)


class TestArchetypeOfCourage:
    """ "Creatures you control have first strike." / "Creatures your opponents control
    lose first strike and can't have or gain first strike."

    The gate read an untouched opponent board (``opponent_battlefield_count: 6``)
    and could say nothing about either half: both are statics about creatures
    other than the card under test.
    """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["archetype_of_courage", BEAR])
            .battlefield(1, [FIRST_STRIKER, BEAR])
            .build()
        )

    def test_your_creatures_have_it(self, builder):
        game = self.position(builder)

        assert "first_strike" in keywords(game, only_oid(game, BEAR, 0))
        assert "first_strike" in keywords(game, only_oid(game, "archetype_of_courage"))

    def test_their_printed_first_striker_loses_it(self, builder):
        game = self.position(builder)

        assert "first_strike" not in keywords(game, only_oid(game, FIRST_STRIKER, 1))
        assert "first_strike" not in keywords(game, only_oid(game, BEAR, 1))

    def test_a_first_strike_counter_cannot_give_it_back(self, builder):
        """ "…and **can't have or gain** first strike." The near miss stops at
        "lose", which any later grant then undoes."""
        game = self.position(builder)
        theirs = only_oid(game, BEAR, 1)
        add_counters(game.state, theirs, "first_strike", 1)
        game.state.bump_chars()

        assert counters(game, theirs, "first_strike") == 1, "the counter is really there"
        assert "first_strike" not in keywords(game, theirs)

    def test_the_counter_works_once_the_archetype_is_gone(self, builder):
        """The control: the counter is a real grant, so the test above measures
        the static and not a broken counter."""
        game = builder(players=2).battlefield(1, [BEAR]).build()
        theirs = only_oid(game, BEAR, 1)
        add_counters(game.state, theirs, "first_strike", 1)
        game.state.bump_chars()

        assert "first_strike" in keywords(game, theirs)


# ----------------------------------------------------------------------
# the triggered anthems
# ----------------------------------------------------------------------


class TestGoldnightCommander:
    """ "Whenever another creature you control enters, creatures you control get +1/+1
    until end of turn."

    "Another", "you control", "for each arrival" and "until end of turn" -- four
    ways to be wrong, and the sandbox reaches none of them.
    """

    def position(self, builder, *, doubler: bool = False):
        board = ["goldnight_commander", TOKEN_MAKER, *["plains"] * 4]
        if doubler:
            board.insert(1, "mondrak_glory_dominus")
        return (
            builder(players=2)
            .battlefield(0, board)
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_a_creature_entering_pumps_the_team(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["goldnight_commander", BEAR, "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )
        commander = only_oid(game, "goldnight_commander")
        bear = only_oid(game, BEAR, 0)
        (soldier,) = make_tokens(game)

        assert size(game, commander) == (3, 3), "itself included -- it is a creature you control"
        assert size(game, bear) == (3, 3)
        assert size(game, soldier) == (2, 2), "and the newcomer"

    def test_two_entering_at_once_is_plus_two(self, builder):
        """The "for each" pin: two arrivals are two triggers, not one."""
        game = self.position(builder, doubler=True)
        commander = only_oid(game, "goldnight_commander")
        activate(game, only_oid(game, TOKEN_MAKER), MAKER_ABILITY)

        assert len(tokens(game, SOLDIER, 0)) == 2, "the premise"
        assert size(game, commander) == (4, 4)

    def test_one_entering_is_only_plus_one(self, builder):
        """The control for the test above."""
        game = self.position(builder)
        commander = only_oid(game, "goldnight_commander")
        activate(game, only_oid(game, TOKEN_MAKER), MAKER_ABILITY)

        assert size(game, commander) == (3, 3)

    def test_its_own_arrival_does_not_trigger(self, builder):
        """ "**Another** creature." The near miss pumps the team as it lands."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, *["plains"] * 4])
            .battlefield(1, ["plains"])
            .hand(0, ["goldnight_commander"])
            .hand(1, [ANCHOR])
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        commander = cast(game, "goldnight_commander")

        assert size(game, bear) == (2, 2)
        assert size(game, commander) == (2, 2)

    def test_an_opponents_creature_entering_does_nothing(self, builder):
        """ "Another creature **you control**"."""
        game = (
            builder(players=2)
            .battlefield(0, ["goldnight_commander", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )
        commander = only_oid(game, "goldnight_commander")
        make_tokens(game, pid=1)

        assert size(game, commander) == (2, 2)

    def test_the_pump_does_not_survive_the_turn(self, builder):
        """ "**Until end of turn**" -- the near miss is a counter, which would."""
        game = self.position(builder)
        commander = only_oid(game, "goldnight_commander")
        activate(game, only_oid(game, TOKEN_MAKER), MAKER_ABILITY)
        assert size(game, commander) == (3, 3)

        pass_until(game, lambda g: g.state.active_player == 1 and g.pending() is not None)

        assert size(game, commander) == (2, 2)
        assert counters(game, commander) == 0, "and it was never a counter"


class TestSoulWarden:
    """ "Whenever another creature enters, you gain 1 life."

    The card prints no "you control", and that absence is the whole test: a Soul
    Warden written as your own arrivals is a strictly worse card that a
    one-board sandbox cannot tell apart.
    """

    def test_your_creature_entering_gains_a_life(self, builder):
        game = builder(players=2).battlefield(0, ["soul_warden", "plains"]).build()
        make_tokens(game)

        assert game.state.players[0].life == 41

    def test_an_opponents_creature_entering_gains_a_life_too(self, builder):
        """The near miss, and the only one that matters on this card."""
        game = (
            builder(players=2)
            .battlefield(0, ["soul_warden", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )
        make_tokens(game, pid=1)

        assert game.state.players[0].life == 41

    def test_two_creatures_entering_at_once_gains_two(self, builder):
        """One trigger per arrival, not one per event: a doubled token creation
        is two lives."""
        game = (
            builder(players=2)
            .battlefield(0, ["soul_warden", "mondrak_glory_dominus", TOKEN_MAKER, *["plains"] * 4])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        activate(game, only_oid(game, TOKEN_MAKER), MAKER_ABILITY)

        assert len(tokens(game, SOLDIER, 0)) == 2, "the premise"
        assert game.state.players[0].life == 42

    def test_its_own_arrival_gains_nothing(self, builder):
        """ "**Another** creature"."""
        game = (
            builder(players=2)
            .battlefield(0, ["plains"])
            .battlefield(1, ["plains"])
            .hand(0, ["soul_warden"])
            .hand(1, [ANCHOR])
            .build()
        )
        cast(game, "soul_warden")

        assert game.state.players[0].life == 40

    def test_a_noncreature_permanent_gains_nothing(self, builder):
        """ "Another **creature**"."""
        game = (
            builder(players=2)
            .battlefield(0, ["soul_warden", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, ["sol_ring"])
            .hand(1, [ANCHOR])
            .build()
        )
        cast(game, "sol_ring")

        assert game.state.players[0].life == 40


class TestHaliyaGuidedByLight:
    """ "Whenever Haliya or another creature or artifact you control enters, you gain 1
    life." / "At the beginning of your end step, draw a card if you've gained 3 or more
    life this turn."

    The gate cast Haliya and read ``life: {0: 41}`` -- the first clause's *own*
    arrival, and nothing else. Haliya is Soul Warden's mirror and the pair is why
    both are here: this one *does* say "you control", and it also counts
    artifacts.
    """

    def position(self, builder, hand):
        return (
            builder(players=2)
            .battlefield(0, ["haliya_guided_by_light", *["plains"] * 3])
            .battlefield(1, ["plains"])
            .hand(0, hand)
            .hand(1, [ANCHOR])
            .library(0, ["plains"] * 20)
            .build()
        )

    def test_an_artifact_entering_gains_a_life(self, builder):
        """ "…or **artifact** you control" -- the half Soul Warden does not print."""
        game = self.position(builder, ["sol_ring"])
        cast(game, "sol_ring")

        assert game.state.players[0].life == 41

    def test_an_enchantment_entering_gains_nothing(self, builder):
        """ "Creature or artifact", and an Intangible Virtue is neither."""
        game = self.position(builder, ["intangible_virtue"])
        cast(game, "intangible_virtue")

        assert game.state.players[0].life == 40

    def test_an_opponents_creature_entering_gains_nothing(self, builder):
        """ "…you control". The near miss here is Soul Warden's text, which would
        gain a life off their Soldier."""
        game = (
            builder(players=2)
            .battlefield(0, ["haliya_guided_by_light", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )
        make_tokens(game, pid=1)

        assert game.state.players[0].life == 40

    def test_three_life_gained_draws_at_the_end_step(self, builder):
        game = self.position(builder, [ANCHOR] * 3)
        for _ in range(3):
            cast(game, ANCHOR)
        assert game.state.players[0].life == 43
        before = len(game.state.players[0].library)

        to_step(game, Step.END_STEP)
        settle(game)

        assert before - len(game.state.players[0].library) == 1

    def test_two_life_gained_draws_nothing(self, builder):
        """The off-by-one: "**3 or more**", and two is not three."""
        game = self.position(builder, [ANCHOR] * 2)
        for _ in range(2):
            cast(game, ANCHOR)
        assert game.state.players[0].life == 42
        before = len(game.state.players[0].library)

        to_step(game, Step.END_STEP)
        settle(game)

        assert before - len(game.state.players[0].library) == 0


class TestAnafenzaUnyieldingLineage:
    """ "Whenever another nontoken creature you control dies, Anafenza endures 2. (Put
    two +1/+1 counters on it or create a 2/2 white Spirit creature token.)"

    Nothing dies in the sandbox, so the gate could not reach the trigger, and
    endure is modal -- the harness takes the first mode, so the Spirit is
    unreachable even where something does die. The deaths here are driven by
    Angelic Aberration's own sacrifice, which is the deck's way of killing a
    creature on demand.
    """

    def position(self, builder, victims, *, pid: int = 0):
        """``pid`` is who casts the Aberration, and so whose creatures die."""
        if pid == 0:
            board = ["anafenza_unyielding_lineage", *victims, *["plains"] * 6]
            theirs = ["plains"]
        else:
            board = ["anafenza_unyielding_lineage", "plains"]
            theirs = [*victims, *["plains"] * 6]
        b = (
            builder(players=2)
            .battlefield(0, board)
            .battlefield(1, theirs)
            .hand(pid, ["angelic_aberration"])
            .hand(1 - pid, [ANCHOR])
        )
        if pid == 1:
            b = b.active(1)
        return b.build()

    def test_endure_two_puts_two_counters_on_it(self, builder):
        game = self.position(builder, [SQUIRE])
        anafenza = only_oid(game, "anafenza_unyielding_lineage")
        cast_aberration(game, sacrifice=True)
        at_decision(game, DecisionKind.CHOOSE_MODE)
        choose(game, 0)
        settle(game)

        assert counters(game, anafenza) == 2
        assert size(game, anafenza) == (4, 4)
        assert tokens(game, SPIRIT, 0) == []

    def test_or_creates_a_two_two_spirit(self, builder):
        """The second mode, which the gate's first-mode-only harness cannot see."""
        game = self.position(builder, [SQUIRE])
        anafenza = only_oid(game, "anafenza_unyielding_lineage")
        cast_aberration(game, sacrifice=True)
        at_decision(game, DecisionKind.CHOOSE_MODE)
        choose(game, 1)
        settle(game)

        assert counters(game, anafenza) == 0
        spirits = tokens(game, SPIRIT, 0)
        assert len(spirits) == 1
        assert size(game, spirits[0].oid) == (2, 2)

    def test_a_token_dying_does_not_trigger_it(self, builder):
        """ "Another **nontoken** creature." A Soldier token dying is not it, and
        in this deck that is most of what dies."""
        game = self.position(builder, [])
        anafenza = only_oid(game, "anafenza_unyielding_lineage")
        make_tokens(game)
        cast_aberration(game, sacrifice=True)
        settle(game)

        assert tokens(game, SOLDIER, 0) == [], "the token really did die"
        assert len(tokens(game, ANGEL, 0)) == 1
        assert counters(game, anafenza) == 0
        assert tokens(game, SPIRIT, 0) == []

    def test_an_opponents_creature_dying_does_not_trigger_it(self, builder):
        """ "…creature **you control** dies"."""
        game = self.position(builder, [SQUIRE], pid=1)
        anafenza = only_oid(game, "anafenza_unyielding_lineage")
        cast_aberration(game, sacrifice=True)
        settle(game)

        assert oids_of(game, SQUIRE, 1) == [], "their Squire really did die"
        assert counters(game, anafenza) == 0
        assert tokens(game, SPIRIT, 0) == []

    def test_flash_makes_it_castable_on_their_turn(self, builder):
        """ "Flash." The sandbox casts every card in its own main phase, so a
        creature that may be cast at instant speed and one that may not look
        identical to the gate.

        Soul Warden is in the same hand as the control: a {W} creature with no
        flash, affordable off the same three Plains, and never offered. Without
        it the assertion above is about timing rather than about the keyword.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 3)
            .battlefield(1, ["plains"])
            .hand(0, ["anafenza_unyielding_lineage", "soul_warden"])
            .hand(1, [ANCHOR])
            .active(1)
            .build()
        )
        # The active player is offered priority first, so hold on until the
        # question reaches the seat holding the creature.
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 0)
        assert game.state.active_player == 1, "the premise -- not your turn"

        assert _can_cast(game, "anafenza_unyielding_lineage", 0)
        assert not _can_cast(game, "soul_warden", 0)


# ----------------------------------------------------------------------
# keyword sharing, and the combat-shaped cards
# ----------------------------------------------------------------------


class TestOdricLunarchMarshal:
    """ "At the beginning of each combat, creatures you control gain first strike until
    end of turn if a creature you control has first strike. The same is true for flying,
    deathtouch, double strike, haste, hexproof, indestructible, lifelink, menace, reach,
    skulk, trample, and vigilance."

    Not a grant of a fixed list -- a *share* of what is already there, and the
    difference is the whole card. The sandbox never reaches a combat, so every
    test here is new, and the negative matters more than the positive: the near
    miss is thirteen keywords conjured out of nothing.
    """

    def position(self, builder, mine, theirs=()):
        return (
            builder(players=2)
            .battlefield(0, ["odric_lunarch_marshal", *mine, "plains"])
            .battlefield(1, [*theirs, "plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_a_keyword_one_creature_has_spreads_to_the_team(self, builder):
        game = self.position(builder, [FIRST_STRIKER, BEAR])
        bear = only_oid(game, BEAR, 0)
        assert keywords(game, bear) == set(), "the premise"

        to_step(game, Step.BEGIN_COMBAT)
        settle(game)

        assert "first_strike" in keywords(game, bear)
        assert "first_strike" in keywords(game, only_oid(game, "odric_lunarch_marshal"))

    def test_a_keyword_nobody_has_is_not_conjured(self, builder):
        """The near miss: a card that grants the printed list rather than sharing
        what is on the board would hand this Bear all thirteen."""
        game = self.position(builder, [FIRST_STRIKER, BEAR])
        bear = only_oid(game, BEAR, 0)

        to_step(game, Step.BEGIN_COMBAT)
        settle(game)

        assert keywords(game, bear) == {"first_strike"}

    def test_two_keywords_on_the_board_both_spread(self, builder):
        """ "The same is true for …" -- every clause, not the first one."""
        game = self.position(builder, [FIRST_STRIKER, LIFELINKER, BEAR])
        bear = only_oid(game, BEAR, 0)

        to_step(game, Step.BEGIN_COMBAT)
        settle(game)

        assert keywords(game, bear) == {"first_strike", "lifelink"}

    def test_a_granted_keyword_spreads_as_readily_as_a_printed_one(self, builder):
        """ "…if a creature you control **has** first strike" -- has, however it
        came by it. Intangible Virtue gives a Soldier token vigilance and Odric
        hands that vigilance to the Bear, which is the layer-order claim: the
        trigger reads computed characteristics and not printed faces. The near
        miss walks the printed keyword lists and finds nothing to share."""
        game = self.position(builder, ["intangible_virtue", BEAR])
        (soldier,) = make_tokens(game)
        assert keywords(game, soldier) == {"vigilance"}, "the premise, and it is granted"
        bear = only_oid(game, BEAR, 0)

        to_step(game, Step.BEGIN_COMBAT)
        settle(game)

        assert keywords(game, bear) == {"vigilance"}

    def test_a_keyword_only_an_opponent_has_does_not_spread(self, builder):
        """ "…if a creature **you control** has first strike"."""
        game = self.position(builder, [BEAR], theirs=[FIRST_STRIKER])
        bear = only_oid(game, BEAR, 0)

        to_step(game, Step.BEGIN_COMBAT)
        settle(game)

        assert keywords(game, bear) == set()

    def test_their_creatures_gain_nothing(self, builder):
        """ "**Creatures you control** gain first strike"."""
        game = self.position(builder, [FIRST_STRIKER], theirs=[BEAR])
        theirs = only_oid(game, BEAR, 1)

        to_step(game, Step.BEGIN_COMBAT)
        settle(game)

        assert keywords(game, theirs) == set()

    def test_it_expires_and_fires_again_in_their_combat(self, builder):
        """ "Until end of turn", and "at the beginning of **each** combat" -- the
        pair. Read at their main phase the grant is gone; read at their combat it
        is back, because Odric triggers on a combat that is not yours."""
        game = self.position(builder, [FIRST_STRIKER, BEAR])
        bear = only_oid(game, BEAR, 0)
        to_step(game, Step.BEGIN_COMBAT)
        settle(game)
        assert "first_strike" in keywords(game, bear)

        to_step(game, Step.PRECOMBAT_MAIN, active=1)
        assert keywords(game, bear) == set(), "the turn ended and took the grant with it"

        to_step(game, Step.BEGIN_COMBAT, active=1)
        settle(game)
        assert "first_strike" in keywords(game, bear)


class TestOdricMasterTactician:
    """ "Whenever Odric and at least three other creatures attack, you choose which
    creatures block this combat and how those creatures block."

    The gate never attacks, so it could only record that Odric entered and a card
    stayed in hand. Both halves of the condition -- Odric among the attackers,
    and three others beside him -- are asserted from the far side as well as the
    near one, because the failure mode of a battalion clause is firing a creature
    early.
    """

    def position(self, builder, mine):
        return (
            builder(players=2)
            .battlefield(0, [*mine, "plains", "plains"])
            .battlefield(1, [SQUIRE])
            .library(0, ["plains"] * 20)
            .library(1, ["plains"] * 20)
            .step(Step.UNTAP)
            .max_turns(2)
            .build()
        )

    def test_four_attackers_move_the_declaration_to_you(self, builder):
        game = self.position(builder, ["odric_master_tactician", BEAR, BEAR, BEAR])
        assert attack_with_all(game) == 4

        assert blockers_asked(game) == {0}, "the attacker declares the defender's blocks"

    def test_three_attackers_leave_it_with_the_defender(self, builder):
        """ "…and at least **three other** creatures." Odric plus two is not it,
        and this is the off-by-one the condition exists for."""
        game = self.position(builder, ["odric_master_tactician", BEAR, BEAR])
        assert attack_with_all(game) == 3

        assert blockers_asked(game) == {1}

    def test_four_attackers_without_odric_leave_it_with_the_defender(self, builder):
        """ "Whenever **Odric** and …" -- he has to be one of them."""
        game = self.position(builder, ["odric_master_tactician", BEAR, BEAR, BEAR, BEAR])
        assert attack_with_all(game, skip="odric_master_tactician") == 4

        assert blockers_asked(game) == {1}


class TestMoonshakerCavalry:
    """ "When this creature enters, creatures you control gain flying and get +X/+X
    until end of turn, where X is the number of creatures you control."

    The gate saw ``granted: {count: 3, keywords: [flying]}`` -- that three
    creatures had flying, and nothing about the size or about how long either
    lasts. X counting the team is pinned elsewhere; what is left is the duration
    and the other seat.
    """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [BEAR, BEAR, *["plains"] * 8])
            .battlefield(1, [BEAR, "plains"])
            .hand(0, ["moonshaker_cavalry"])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_their_creatures_gain_neither(self, builder):
        """ "**Creatures you control**"."""
        game = self.position(builder)
        theirs = only_oid(game, BEAR, 1)
        cast(game, "moonshaker_cavalry")

        assert size(game, theirs) == (2, 2)
        assert "flying" not in keywords(game, theirs)

    def test_both_halves_expire_with_the_turn(self, builder):
        """ "**Until end of turn**" governs the keyword as well as the size -- the
        near miss grants the flying permanently and only times out the pump."""
        game = self.position(builder)
        bear = oids_of(game, BEAR, 0)[0]
        cast(game, "moonshaker_cavalry")
        assert size(game, bear) == (5, 5), "three creatures you control"
        assert "flying" in keywords(game, bear)

        pass_until(game, lambda g: g.state.active_player == 1 and g.pending() is not None)

        assert size(game, bear) == (2, 2)
        assert "flying" not in keywords(game, bear)


class TestAngelicAberration:
    """ "When this creature enters, sacrifice any number of creatures each with base
    power or toughness 1 or less. Create that many 4/4 colorless Eldrazi Angel creature
    tokens with flying and vigilance."

    The gate recorded ``graveyard_size: {0: 2}`` and one flying, vigilant
    creature -- a single sacrifice, once, with the choice made for it. "Any
    number" and "that many" are a count, and a count needs two.
    """

    def position(self, builder, mine):
        return (
            builder(players=2)
            .battlefield(0, [*mine, *["plains"] * 6])
            .battlefield(1, ["plains"])
            .hand(0, ["angelic_aberration"])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_two_sacrifices_make_two_angels(self, builder):
        """ "**That many**" -- the near miss makes one token however many died."""
        game = self.position(builder, [SQUIRE, SQUIRE])
        cast_aberration(game, sacrifice=True)
        settle(game)

        angels = tokens(game, ANGEL, 0)
        assert len(angels) == 2
        assert oids_of(game, SQUIRE, 0) == []
        assert size(game, angels[0].oid) == (4, 4)
        assert keywords(game, angels[0].oid) >= {"flying", "vigilance"}
        assert chars(game.state, angels[0].oid).colors == frozenset(), "colorless"

    def test_devoid_makes_the_card_itself_colorless(self, builder):
        """ "Devoid (This card has no color.)" -- a white mana cost and no color,
        which no expectation key looks at."""
        game = self.position(builder, [])
        aberration = cast(game, "angelic_aberration")

        assert chars(game.state, aberration).colors == frozenset()

    def test_sacrificing_none_makes_none(self, builder):
        """ "**Any number**" includes zero, and zero of them is zero Angels."""
        game = self.position(builder, [SQUIRE, SQUIRE])
        cast_aberration(game, sacrifice=False)
        settle(game)

        assert tokens(game, ANGEL, 0) == []
        assert len(oids_of(game, SQUIRE, 0)) == 2

    def test_a_two_two_is_out_of_reach(self, builder):
        """ "Base power or toughness **1 or less**" -- a 2/2 is neither, so the
        card cannot eat its own team."""
        game = self.position(builder, [BEAR])
        cast_aberration(game, sacrifice=True)
        settle(game)

        assert len(oids_of(game, BEAR, 0)) == 1
        assert tokens(game, ANGEL, 0) == []

    def test_counters_do_not_lift_a_one_one_out_of_reach(self, builder):
        """ "**Base** power or toughness": a 1/1 wearing two +1/+1 counters reads
        3/3 and is still base 1/1. The near miss asks `chars` and finds a 3/3."""
        game = self.position(builder, [SQUIRE])
        squire = only_oid(game, SQUIRE, 0)
        add_counters(game.state, squire, "+1/+1", 2)
        game.state.bump_chars()
        assert size(game, squire) == (3, 3), "the premise"

        cast_aberration(game, sacrifice=True)
        settle(game)

        assert squire not in game.state.battlefield
        assert len(tokens(game, ANGEL, 0)) == 1


class TestMasterOfCeremonies:
    """ "At the beginning of your upkeep, each opponent chooses money, friends, or
    secrets. For each player who chose money, you and that player each create a Treasure
    token. For each player who chose friends, you and that player each create a 1/1 green
    and white Citizen creature token. For each player who chose secrets, you and that
    player each draw a card."

    Three modes chosen by somebody else, at a step the sandbox never reaches. The
    gate could only say a Rhino entered, and the near miss on every clause is
    "you", forgetting the half that makes this a group-hug card: *and that
    player*.
    """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["master_of_ceremonies", "plains"])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, ["plains"] * 20)
            .library(1, ["plains"] * 20)
            .step(Step.UNTAP)
            .build()
        )

    def test_the_opponent_is_the_one_who_chooses(self, builder):
        """ "**Each opponent** chooses" -- the decision is not yours."""
        game = self.position(builder)
        pending = at_decision(game, DecisionKind.CHOOSE_MODE)

        assert pending.player == 1
        assert [option.value for option in pending.options] == [0, 1, 2]

    def test_money_makes_a_treasure_for_each_of_you(self, builder):
        game = self.position(builder)
        at_decision(game, DecisionKind.CHOOSE_MODE)
        choose(game, 0)
        settle(game)

        assert len(tokens(game, TREASURE, 0)) == 1
        assert len(tokens(game, TREASURE, 1)) == 1, "…and that player"

    def test_friends_makes_a_citizen_for_each_of_you(self, builder):
        game = self.position(builder)
        at_decision(game, DecisionKind.CHOOSE_MODE)
        choose(game, 1)
        settle(game)

        assert len(tokens(game, CITIZEN, 0)) == 1
        assert len(tokens(game, CITIZEN, 1)) == 1
        assert tokens(game, TREASURE) == [], "one mode, not all three"

    def test_secrets_draws_for_each_of_you(self, builder):
        game = self.position(builder)
        at_decision(game, DecisionKind.CHOOSE_MODE)
        before = [len(game.state.players[pid].library) for pid in (0, 1)]
        choose(game, 2)
        settle(game)

        after = [len(game.state.players[pid].library) for pid in (0, 1)]
        assert [before[pid] - after[pid] for pid in (0, 1)] == [1, 1]
