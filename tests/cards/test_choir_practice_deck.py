"""The Choir Practice deck (Giada, Font of Hope), card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card **once**, in one
fixed sandbox, and reads the board. Its documented limits land on almost every
card in an Angel tribal deck:

- **It never activates an ability.** Bonders' Enclave's draw, Three Tree City's
  big mana and Resplendent Angel's pump are the reason those cards are in the
  list, and the harness stops before any of them.
- **A trigger that never fires cannot be asserted.** Nothing enters after the
  card under test, so Bishop of Wings, Seraph Sanctuary, Youthful Valkyrie and
  Lyra all recorded "zero"; nobody reaches an upkeep, so Court of Grace's Angel
  and Emeria's reanimation are unobserved; nobody reaches an end step, so the
  three "if you gained life this turn" Angel makers never ran.
- **A static that prices a later spell is invisible.** Starnheim Aspirant and
  Urza's Incubator discount a *different* card, and the sandbox casts one.
- **A static that reads the board is only ever read on the sandbox's board.** A
  sandbox where the card under test is the only Angel cannot tell "Angels" from
  "creatures", and one without a commander on the battlefield cannot tell
  Lieutenant from a printed 5/5.

So the authored expectations are floors, and these are the observations. Each
class is one card, and each pins the **near miss** as well -- the reading that
would be wrong if the card had been written the other way: an opponent's Angel,
a non-Angel, a token, one point of life short of a threshold.

Cards whose own lanes wrote unit tests with the real card (Giada, Angel of
Vitality, Archangel of Tithes, Righteous Valkyrie, Angel of Destiny, Archivist of
Oghma, Folk Hero, Exemplar of Light, Drannith Magistrate, Giver of Runes) are not
repeated here; `TestGiadaWithTheDeck` covers the commander only where it meets
the rest of the list.

**Why positions hold an `ANCHOR`.** With no play available to anybody the
engine's auto-pass runs whole turns inside a single `apply`, wiping an
until-end-of-turn grant before it can be read and overshooting an end step. A
castable instant in each seat's hand is a reason for priority to stop.
"""

from __future__ import annotations

from automtg.engine import legality
from automtg.engine.characteristics import chars
from automtg.engine.cost_reduction import cost_reduction
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.primitives import create_token
from tests.conftest import (
    _default_answer,
    find_action,
    only_oid,
    pass_until,
)

PLAINS = "plains"
ANCHOR = "t_plain_instant"  # {W}, gain 1 life -- a reason for priority to stop
BEAR = "t_bear"  # {1}{G} vanilla 2/2 Bear: a creature that is not an Angel
# The deck's cheapest Angel shape, and a real card: {W} 1/1 flying, vigilance,
# no text that could confuse the card under test.
SMALL_ANGEL = "segovian_angel"
# A real Angel with generic mana in its cost, so a {2} discount has something to
# take off. {3}{W}{W}, 4/4 flying vigilance.
BIG_ANGEL = "serra_angel"
# A real white non-Angel creature from the deck with {2} generic in its cost --
# the control for every "Angel spell" discount.
NOT_AN_ANGEL = "magus_of_the_moat"  # {2}{W}{W} Human Wizard 0/3
ANGEL_TOKEN = "angel_4_4_w_flying"
VIGILANT_ANGEL_TOKEN = "angel_4_4_w_flying_vigilance"
SPIRIT_TOKEN = "spirit_1_1_w_flying"
GIADA = "giada_font_of_hope"


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


def answer(game, *, yes: bool = False, limit: int = 200) -> None:
    """Let the stack empty, saying yes to every `MAY` when ``yes``."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if yes and decision.kind is DecisionKind.MAY:
            game.apply(find_action(game, ActionKind.YES))
            continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def castable(game, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


def cast_only(game, card_id: str, pid: int = 0) -> int:
    """Put ``card_id`` on the stack from ``pid``'s hand and stop."""
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().player == pid and castable(g, card_id),
    )
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    return action.source


def cast(game, card_id: str, pid: int = 0, *, yes: bool = False) -> int:
    """Cast ``card_id`` and let everything resolve. Returns its oid."""
    oid = cast_only(game, card_id, pid)
    answer(game, yes=yes)
    return oid


def offers(game, pid: int, kind: ActionKind) -> set[str]:
    """The def_ids ``pid`` would be offered ``kind`` for, asked of legality directly."""
    return {
        game.state.objects[a.source].def_id
        for a in legality._priority_actions(game.state, pid)
        if a.kind is kind and a.source is not None
    }


def activations(game, oid: int, index: int | None = None) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and a.source == oid
        and (index is None or a.ability_index == index)
    ]


def discount(game, card_id: str, pid: int = 0) -> int:
    return cost_reduction(game.state, pid, game.state.registry.get(card_id))


def pt(game, oid: int) -> tuple[int, int]:
    c = chars(game.state, oid)
    return c.power, c.toughness


def keywords(game, oid: int) -> set[str]:
    return {str(k) for k in chars(game.state, oid).keywords}


def plus(game, oid: int) -> int:
    return game.state.objects[oid].counters.get("+1/+1", 0)


def tokens(game, def_id: str, pid: int = 0) -> list:
    return [o for o in game.state.battlefield_objects(pid) if o.def_id == def_id and o.is_token]


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


def make_commander(game, oid: int, pid: int = 0) -> None:
    """Mark a permanent already on the battlefield as ``pid``'s commander."""
    game.state.objects[oid].is_commander = True
    game.state.players[pid].commanders.append(oid)
    game.state.bump_chars()


def choose_type(game, oid: int, type_name: str) -> None:
    """Set the type a permanent named, the way its own enters trigger would."""
    game.state.objects[oid].chosen_type = type_name
    game.state.bump_chars()


def answer_type(game, type_name: str) -> None:
    """Answer a pending "Choose a creature type" with ``type_name``."""
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_MODE,
    )
    labels = [o.label for o in game.pending().options]
    index = labels.index(type_name)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )


def attack_options(game, pid: int = 0) -> set[str]:
    """The def_ids ``pid`` may declare as attackers, read at the declaration."""
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        and g.pending().player == pid,
    )
    return {
        game.state.objects[a.source].def_id
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER
    }


def frozen(builder, mine=(), theirs=(), *, hand=(), their_hand=(), step=Step.PRECOMBAT_MAIN):
    """A position exactly as written, nobody advanced into anything."""
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .hand(1, list(their_hand))
        .step(step)
        .active(0)
        .build(advance=False)
    )


def anchored(builder, mine=(), theirs=(), *, hand=(), step=Step.PRECOMBAT_MAIN, yard=()):
    """Player 0's turn, both seats holding an anchor and a Plains to cast it."""
    return (
        builder(players=2)
        .battlefield(0, [*mine, PLAINS])
        .battlefield(1, [*theirs, PLAINS])
        .hand(0, [*hand, ANCHOR])
        .hand(1, [ANCHOR])
        .graveyard(0, list(yard))
        .step(step)
        .active(0)
        .build()
    )


# ----------------------------------------------------------------------
# statics: lords, Lieutenant, and the discounts
# ----------------------------------------------------------------------


class TestAngelicFieldMarshal:
    """ "Lieutenant -- As long as you control your commander, this creature gets
    +2/+2 and creatures you control have vigilance."

    The authoring sandbox has no commander on the battlefield, so the gate saw a
    3/3 and could not tell Lieutenant from a card with no second line at all.
    """

    def board(self, builder, *, commander: bool, theirs=(BEAR,)):
        game = frozen(builder, ["angelic_field_marshal", GIADA, BEAR, PLAINS], [*theirs, PLAINS])
        if commander:
            make_commander(game, only_oid(game, GIADA, 0))
        return game

    def test_with_your_commander_it_is_a_5_5(self, builder):
        game = self.board(builder, commander=True)

        assert pt(game, only_oid(game, "angelic_field_marshal")) == (5, 5)

    def test_with_your_commander_your_creatures_have_vigilance(self, builder):
        """ "**creatures you control**" -- a Bear, not only Angels."""
        game = self.board(builder, commander=True)

        assert "vigilance" in keywords(game, only_oid(game, BEAR, 0))
        assert "vigilance" in keywords(game, only_oid(game, "angelic_field_marshal"))

    def test_the_opponents_creatures_do_not_get_vigilance(self, builder):
        game = self.board(builder, commander=True)

        assert "vigilance" not in keywords(game, only_oid(game, BEAR, 1))

    def test_the_bear_does_not_get_the_plus_two(self, builder):
        """The +2/+2 is "this creature"; only the vigilance is team-wide."""
        game = self.board(builder, commander=True)

        assert pt(game, only_oid(game, BEAR, 0)) == (2, 2)

    def test_the_same_legend_that_is_not_your_commander_does_nothing(self, builder):
        """The near miss: "a legendary Angel" is not "your commander"."""
        game = self.board(builder, commander=False)

        assert pt(game, only_oid(game, "angelic_field_marshal")) == (3, 3)
        assert "vigilance" not in keywords(game, only_oid(game, BEAR, 0))

    def test_a_commander_in_the_command_zone_does_not_count(self, builder):
        """ "As long as you **control** your commander" -- the command zone is not control."""
        game = (
            builder(players=2)
            .battlefield(0, ["angelic_field_marshal", BEAR, PLAINS])
            .commander(0, [GIADA])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

        assert pt(game, only_oid(game, "angelic_field_marshal")) == (3, 3)
        assert "vigilance" not in keywords(game, only_oid(game, BEAR, 0))

    def test_an_opponents_commander_does_not_turn_it_on(self, builder):
        """ "**your** commander"."""
        game = frozen(builder, ["angelic_field_marshal", BEAR, PLAINS], [GIADA, PLAINS])
        make_commander(game, only_oid(game, GIADA, 1), pid=1)

        assert pt(game, only_oid(game, "angelic_field_marshal")) == (3, 3)

    def test_it_switches_off_when_the_commander_leaves(self, builder):
        """A condition, re-read every time -- not a bonus banked on arrival."""
        from automtg.engine.zones import move_object

        game = self.board(builder, commander=True)
        assert pt(game, only_oid(game, "angelic_field_marshal")) == (5, 5)

        move_object(game.state, only_oid(game, GIADA, 0), Zone.COMMAND)
        game.state.bump_chars()

        assert pt(game, only_oid(game, "angelic_field_marshal")) == (3, 3)
        assert "vigilance" not in keywords(game, only_oid(game, BEAR, 0))


class TestThrabenWatcher:
    """ "Other nontoken creatures you control get +1/+1 and have vigilance." """

    def board(self, builder):
        game = frozen(builder, ["thraben_watcher", BEAR, PLAINS], [SMALL_ANGEL, PLAINS])
        (token,) = create_token(game.state, ANGEL_TOKEN, 0)
        game.state.bump_chars()
        return game, token

    def test_a_nontoken_creature_gets_plus_one_and_vigilance(self, builder):
        game, _token = self.board(builder)
        bear = only_oid(game, BEAR, 0)

        assert pt(game, bear) == (3, 3)
        assert "vigilance" in keywords(game, bear)

    def test_a_token_gets_nothing(self, builder):
        """ "**nontoken**" -- the deck makes a lot of 4/4 Angel tokens, and none of them grow."""
        game, token = self.board(builder)

        assert pt(game, token) == (4, 4)
        assert "vigilance" not in keywords(game, token)

    def test_it_does_not_buff_itself(self, builder):
        """ "**Other**" -- a printed 2/2 stays 2/2."""
        game, _token = self.board(builder)

        assert pt(game, only_oid(game, "thraben_watcher")) == (2, 2)

    def test_the_opponents_creatures_get_nothing(self, builder):
        game, _token = self.board(builder)
        theirs = only_oid(game, SMALL_ANGEL, 1)

        assert pt(game, theirs) == (1, 1)


class TestAvacynAngelOfHope:
    """ "Other permanents you control have indestructible." """

    def board(self, builder):
        return frozen(builder, ["avacyn_angel_of_hope", BEAR, PLAINS], [BEAR, PLAINS])

    def test_a_creature_and_a_land_you_control_are_indestructible(self, builder):
        """ "**permanents**", not creatures -- the Plains is covered too."""
        game = self.board(builder)

        assert "indestructible" in keywords(game, only_oid(game, BEAR, 0))
        assert "indestructible" in keywords(game, only_oid(game, PLAINS, 0))

    def test_the_opponents_permanents_are_not(self, builder):
        game = self.board(builder)

        assert "indestructible" not in keywords(game, only_oid(game, BEAR, 1))
        assert "indestructible" not in keywords(game, only_oid(game, PLAINS, 1))

    def test_a_wrath_kills_only_the_opponents_bear(self, builder):
        """The grant read by the destroy, not just printed on the frame."""
        from automtg.engine.zones import destroy

        game = self.board(builder)
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        destroy(game.state, mine)
        destroy(game.state, theirs)

        assert game.state.objects[mine].zone is Zone.BATTLEFIELD
        assert game.state.objects[theirs].zone is Zone.GRAVEYARD


class TestMagusOfTheMoat:
    """ "Creatures without flying can't attack." """

    def test_only_fliers_may_attack(self, builder):
        game = anchored(builder, ["magus_of_the_moat", BEAR, SMALL_ANGEL], step=Step.BEGIN_COMBAT)

        assert attack_options(game) == {SMALL_ANGEL}

    def test_it_stops_its_own_controller_too(self, builder):
        """No "your opponents'" in the line: the Bear above is the Magus's own, and
        so is the Magus -- a 0/3 without flying."""
        game = anchored(builder, ["magus_of_the_moat", BEAR], step=Step.BEGIN_COMBAT)

        options = attack_options(game)
        assert BEAR not in options
        assert "magus_of_the_moat" not in options

    def test_it_stops_the_opponents_ground_creatures(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["magus_of_the_moat", PLAINS])
            .battlefield(1, [BEAR, SMALL_ANGEL, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.END_STEP)
            .active(0)
            .build()
        )

        assert attack_options(game, pid=1) == {SMALL_ANGEL}

    def test_without_it_the_bear_attacks(self, builder):
        """The control: the position above with the Magus taken out."""
        game = anchored(builder, [BEAR], step=Step.BEGIN_COMBAT)

        assert BEAR in attack_options(game)


class TestPatchworkBanner:
    """ "Creatures you control of the chosen type get +1/+1." """

    def board(self, builder):
        game = frozen(builder, ["patchwork_banner", SMALL_ANGEL, BEAR, PLAINS], [SMALL_ANGEL])
        choose_type(game, only_oid(game, "patchwork_banner"), "Angel")
        return game

    def test_casting_it_asks_for_the_type_and_buffs_that_type(self, builder):
        game = anchored(builder, [SMALL_ANGEL, BEAR, PLAINS, PLAINS], hand=["patchwork_banner"])
        cast_only(game, "patchwork_banner")
        answer_type(game, "Angel")
        settle(game)

        assert game.state.objects[only_oid(game, "patchwork_banner")].chosen_type == "Angel"
        assert pt(game, only_oid(game, SMALL_ANGEL, 0)) == (2, 2)

    def test_a_creature_of_another_type_gets_nothing(self, builder):
        game = self.board(builder)

        assert pt(game, only_oid(game, SMALL_ANGEL, 0)) == (2, 2)
        assert pt(game, only_oid(game, BEAR, 0)) == (2, 2), "a Bear, still printed"

    def test_the_opponents_creature_of_that_type_gets_nothing(self, builder):
        """ "Creatures **you control** of the chosen type"."""
        game = self.board(builder)

        assert pt(game, only_oid(game, SMALL_ANGEL, 1)) == (1, 1)


class TestThreeTreeCity:
    """ "{2}, {T}: Choose a color. Add an amount of mana of that color equal to the
    number of creatures you control of the chosen type." """

    def board(self, builder, theirs=()):
        game = anchored(
            builder,
            ["three_tree_city", SMALL_ANGEL, SMALL_ANGEL, BIG_ANGEL, BEAR, PLAINS],
            theirs,
        )
        choose_type(game, only_oid(game, "three_tree_city"), "Angel")
        return game

    def big_mana(self, game) -> int:
        city = only_oid(game, "three_tree_city")
        game.apply(activations(game, city, 2)[0])
        # "Choose a color" -- take whatever is asked first; the claim is the amount.
        pass_until(
            game,
            lambda g: g.pending() is None or g.pending().kind is DecisionKind.PRIORITY,
        )
        assert game.state.objects[city].tapped
        return game.state.players[0].mana_pool.total()

    def test_it_adds_one_per_creature_of_the_chosen_type(self, builder):
        """Three Angels and a Bear: three, not four."""
        game = self.board(builder, theirs=[SMALL_ANGEL, SMALL_ANGEL])

        assert self.big_mana(game) == 3

    def test_the_mana_is_all_one_color(self, builder):
        game = self.board(builder)
        self.big_mana(game)

        pool = game.state.players[0].mana_pool.to_dict()
        assert len([c for c, n in pool.items() if n]) == 1

    def test_casting_it_asks_for_the_type(self, builder):
        game = anchored(builder, [SMALL_ANGEL], hand=["three_tree_city"])
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.PLAY_LAND for a in g.legal_actions()
            ),
        )
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND)
        )
        answer_type(game, "Angel")
        settle(game)

        assert game.state.objects[only_oid(game, "three_tree_city")].chosen_type == "Angel"


class TestUrzasIncubator:
    """ "Creature spells of the chosen type cost {2} less to cast." """

    def board(self, builder, *, lands: int = 3, incubator: bool = True, hand=(BIG_ANGEL,)):
        mine = [PLAINS] * lands + (["urza_s_incubator"] if incubator else [])
        game = frozen(builder, mine, [PLAINS] * lands, hand=hand, their_hand=hand)
        if incubator:
            choose_type(game, only_oid(game, "urza_s_incubator"), "Angel")
        return game

    def test_an_angel_spell_costs_two_less(self, builder):
        game = self.board(builder)

        assert discount(game, BIG_ANGEL) == 2

    def test_an_opponents_angel_spell_costs_two_less_too(self, builder):
        """The near miss, and the expensive one: Incubator has no "you cast".
        It discounts the chosen type for **every** player."""
        game = self.board(builder)

        assert discount(game, BIG_ANGEL, pid=1) == 2

    def test_another_type_pays_full_price(self, builder):
        game = self.board(builder)

        assert discount(game, NOT_AN_ANGEL) == 0
        assert discount(game, BEAR) == 0

    def test_the_discount_is_charged(self, builder):
        """Serra Angel is {3}{W}{W}; three Plains pay {1}{W}{W} and nothing more."""
        game = self.board(builder)

        assert BIG_ANGEL in offers(game, 0, ActionKind.CAST)

    def test_and_without_it_three_plains_are_short(self, builder):
        game = self.board(builder, incubator=False)

        assert BIG_ANGEL not in offers(game, 0, ActionKind.CAST)

    def test_casting_it_asks_for_the_type(self, builder):
        game = anchored(builder, [PLAINS, PLAINS], hand=["urza_s_incubator"])
        cast_only(game, "urza_s_incubator")
        answer_type(game, "Angel")
        settle(game)

        incubator = only_oid(game, "urza_s_incubator")
        assert game.state.objects[incubator].chosen_type == "Angel"
        assert discount(game, BIG_ANGEL) == 2


class TestStarnheimAspirant:
    """ "Angel spells you cast cost {2} less to cast." """

    def board(self, builder, *, aspirant: bool = True, lands: int = 3):
        mine = [PLAINS] * lands + (["starnheim_aspirant"] if aspirant else [])
        return frozen(builder, mine, [PLAINS] * lands, hand=[BIG_ANGEL], their_hand=[BIG_ANGEL])

    def test_an_angel_spell_you_cast_costs_two_less(self, builder):
        game = self.board(builder)

        assert discount(game, BIG_ANGEL) == 2

    def test_a_non_angel_pays_full_price(self, builder):
        """ "**Angel** spells" -- Magus of the Moat has {2} to take off and keeps it."""
        game = self.board(builder)

        assert discount(game, NOT_AN_ANGEL) == 0

    def test_an_opponents_angel_pays_full_price(self, builder):
        """ "Angel spells **you cast**" -- the near miss is Urza's Incubator."""
        game = self.board(builder)

        assert discount(game, BIG_ANGEL, pid=1) == 0

    def test_the_discount_is_charged(self, builder):
        game = self.board(builder)

        assert BIG_ANGEL in offers(game, 0, ActionKind.CAST)

    def test_and_without_it_three_plains_are_short(self, builder):
        game = self.board(builder, aspirant=False)

        assert BIG_ANGEL not in offers(game, 0, ActionKind.CAST)


# ----------------------------------------------------------------------
# triggers on later events: arrivals, deaths, upkeeps, life gained
# ----------------------------------------------------------------------


def to_my_main(game, pid: int = 0) -> None:
    """Run on to ``pid``'s precombat main, through its upkeep and draw."""
    pass_until(game, lambda g: g.state.step is Step.PRECOMBAT_MAIN and g.state.active_player == pid)
    settle(game)


def before_my_turn(builder, mine=(), theirs=(), *, players: int = 2, hands=None):
    """The last opponent's end step, every seat anchored; player 0 is next."""
    hands = hands or {}
    b = builder(players=players)
    for pid in range(players):
        board = [PLAINS, *(mine if pid == 0 else theirs if pid == 1 else ())]
        b = b.battlefield(pid, board).hand(pid, [ANCHOR, *hands.get(pid, ())])
    return b.active(players - 1).step(Step.END_STEP).build()


def pick_everything(game, limit: int = 200) -> None:
    """Settle, choosing every offered object on each `CHOOSE_OBJECTS` (proliferate)."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choice = next((a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None)
            game.apply(choice or find_action(game, ActionKind.FINISH_DECLARATION))
            continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def kill(game, oid: int) -> None:
    """Destroy ``oid`` and let whatever watches for a death resolve."""
    from automtg.engine.zones import destroy

    assert destroy(game.state, oid)
    game.state.bump_chars()
    settle(game)


class TestCourtOfGrace:
    """ "When this enchantment enters, you become the monarch." / "At the beginning
    of your upkeep, create a 1/1 white Spirit creature token with flying. If you're
    the monarch, create a 4/4 white Angel creature token with flying instead." """

    def test_casting_it_makes_you_the_monarch(self, builder):
        game = anchored(builder, [PLAINS] * 3, hand=["court_of_grace"])
        assert game.state.monarch is None
        cast(game, "court_of_grace")

        assert game.state.monarch == 0

    def upkeep(self, builder, *, monarch):
        game = before_my_turn(builder, ["court_of_grace"])
        game.state.monarch = monarch
        to_my_main(game)
        return game

    def test_as_the_monarch_your_upkeep_makes_an_angel_and_no_spirit(self, builder):
        """ "…**instead**" -- exactly one token, never both."""
        game = self.upkeep(builder, monarch=0)

        assert len(tokens(game, ANGEL_TOKEN)) == 1
        assert tokens(game, SPIRIT_TOKEN) == []

    def test_not_the_monarch_your_upkeep_makes_a_spirit_and_no_angel(self, builder):
        game = self.upkeep(builder, monarch=1)

        assert len(tokens(game, SPIRIT_TOKEN)) == 1
        assert tokens(game, ANGEL_TOKEN) == []

    def test_with_no_monarch_at_all_it_is_a_spirit(self, builder):
        game = self.upkeep(builder, monarch=None)

        assert len(tokens(game, SPIRIT_TOKEN)) == 1
        assert tokens(game, ANGEL_TOKEN) == []

    def test_an_opponents_upkeep_makes_nothing(self, builder):
        """ "At the beginning of **your** upkeep"."""
        game = (
            builder(players=2)
            .battlefield(0, ["court_of_grace", PLAINS])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.END_STEP)
            .build()
        )
        game.state.monarch = 0
        to_my_main(game, pid=1)

        assert tokens(game, ANGEL_TOKEN) == [] and tokens(game, SPIRIT_TOKEN) == []


class TestBishopOfWings:
    """ "Whenever an Angel you control enters, you gain 4 life." / "Whenever an
    Angel you control dies, create a 1/1 white Spirit creature token with flying." """

    def test_an_angel_entering_gains_four(self, builder):
        game = anchored(builder, ["bishop_of_wings", PLAINS], hand=[SMALL_ANGEL])
        before = life(game)
        cast(game, SMALL_ANGEL)

        assert life(game) == before + 4

    def test_a_non_angel_entering_gains_nothing(self, builder):
        game = anchored(builder, ["bishop_of_wings", *[PLAINS] * 4], hand=[NOT_AN_ANGEL])
        before = life(game)
        cast(game, NOT_AN_ANGEL)

        assert life(game) == before

    def test_an_opponents_angel_entering_gains_nothing(self, builder):
        """ "an Angel **you control**"."""
        game = (
            builder(players=2)
            .battlefield(0, ["bishop_of_wings", PLAINS])
            .battlefield(1, [PLAINS, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [SMALL_ANGEL, ANCHOR])
            .active(1)
            .build()
        )
        before = life(game, 0), life(game, 1)
        cast(game, SMALL_ANGEL, pid=1)

        assert (life(game, 0), life(game, 1)) == before, "nor its controller"

    def test_an_angel_dying_makes_a_spirit(self, builder):
        game = anchored(builder, ["bishop_of_wings", SMALL_ANGEL])
        kill(game, only_oid(game, SMALL_ANGEL, 0))

        assert len(tokens(game, SPIRIT_TOKEN)) == 1

    def test_a_non_angel_dying_makes_nothing(self, builder):
        game = anchored(builder, ["bishop_of_wings", BEAR])
        kill(game, only_oid(game, BEAR, 0))

        assert tokens(game, SPIRIT_TOKEN) == []

    def test_an_opponents_angel_dying_makes_nothing(self, builder):
        game = anchored(builder, ["bishop_of_wings"], [SMALL_ANGEL])
        kill(game, only_oid(game, SMALL_ANGEL, 1))

        assert tokens(game, SPIRIT_TOKEN) == [] and tokens(game, SPIRIT_TOKEN, 1) == []


class TestSeraphSanctuary:
    """ "When this land enters, you gain 1 life." / "Whenever an Angel you control
    enters, you gain 1 life." """

    def test_an_angel_entering_gains_one(self, builder):
        game = anchored(builder, ["seraph_sanctuary"], hand=[SMALL_ANGEL])
        before = life(game)
        cast(game, SMALL_ANGEL)

        assert life(game) == before + 1

    def test_a_non_angel_entering_gains_nothing(self, builder):
        game = anchored(builder, ["seraph_sanctuary", *[PLAINS] * 3], hand=[NOT_AN_ANGEL])
        before = life(game)
        cast(game, NOT_AN_ANGEL)

        assert life(game) == before

    def test_an_opponents_angel_gains_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["seraph_sanctuary", PLAINS])
            .battlefield(1, [PLAINS, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [SMALL_ANGEL, ANCHOR])
            .active(1)
            .build()
        )
        before = life(game, 0)
        cast(game, SMALL_ANGEL, pid=1)

        assert life(game, 0) == before

    def test_its_own_arrival_gains_exactly_one(self, builder):
        """The first line, and not the second too: a land entering is not an Angel."""
        game = anchored(builder, [], hand=["seraph_sanctuary"])
        before = life(game)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND))
        settle(game)

        assert life(game) == before + 1


class TestYouthfulValkyrie:
    """ "Whenever another Angel you control enters, put a +1/+1 counter on this creature." """

    def test_another_angel_grows_it(self, builder):
        game = anchored(builder, ["youthful_valkyrie"], hand=[SMALL_ANGEL])
        cast(game, SMALL_ANGEL)

        assert plus(game, only_oid(game, "youthful_valkyrie")) == 1
        assert plus(game, only_oid(game, SMALL_ANGEL)) == 0, "the counter is on this creature"

    def test_a_non_angel_does_not(self, builder):
        game = anchored(builder, ["youthful_valkyrie", *[PLAINS] * 3], hand=[NOT_AN_ANGEL])
        cast(game, NOT_AN_ANGEL)

        assert plus(game, only_oid(game, "youthful_valkyrie")) == 0

    def test_its_own_arrival_does_not(self, builder):
        """ "**another** Angel" -- the Valkyrie is an Angel itself."""
        game = anchored(builder, [PLAINS], hand=["youthful_valkyrie"])
        cast(game, "youthful_valkyrie")

        assert plus(game, only_oid(game, "youthful_valkyrie")) == 0

    def test_an_opponents_angel_does_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["youthful_valkyrie", PLAINS])
            .battlefield(1, [PLAINS, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [SMALL_ANGEL, ANCHOR])
            .active(1)
            .build()
        )
        cast(game, SMALL_ANGEL, pid=1)

        assert plus(game, only_oid(game, "youthful_valkyrie")) == 0


class TestDazzlingAngel:
    """ "Whenever another creature you control enters, you gain 1 life." """

    def test_another_creature_gains_one(self, builder):
        """A creature, not an Angel: the Magus is a Human Wizard."""
        game = anchored(builder, ["dazzling_angel", *[PLAINS] * 3], hand=[NOT_AN_ANGEL])
        before = life(game)
        cast(game, NOT_AN_ANGEL)

        assert life(game) == before + 1

    def test_a_token_counts(self, builder):
        """No "nontoken" here, unlike Metastatic Evangel's line."""
        game = anchored(builder, ["dazzling_angel"])
        before = life(game)
        create_token(game.state, ANGEL_TOKEN, 0)
        settle(game)

        assert life(game) == before + 1

    def test_its_own_arrival_gains_nothing(self, builder):
        game = anchored(builder, [PLAINS, PLAINS], hand=["dazzling_angel"])
        before = life(game)
        cast(game, "dazzling_angel")

        assert life(game) == before

    def test_an_opponents_creature_gains_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["dazzling_angel", PLAINS])
            .battlefield(1, [PLAINS, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [SMALL_ANGEL, ANCHOR])
            .active(1)
            .build()
        )
        before = life(game, 0)
        cast(game, SMALL_ANGEL, pid=1)

        assert life(game, 0) == before


class TestMetastaticEvangel:
    """ "Whenever another nontoken creature you control enters, proliferate." """

    def board(self, builder, hand=()):
        return (
            builder(players=2)
            .battlefield(0, ["metastatic_evangel", *[PLAINS] * 5])
            .battlefield(0, [BEAR], counters={"+1/+1": 1})
            .battlefield(1, [PLAINS])
            .hand(0, [*hand, ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .build()
        )

    def test_a_nontoken_creature_proliferates(self, builder):
        game = self.board(builder, hand=[SMALL_ANGEL])
        cast_only(game, SMALL_ANGEL)
        pick_everything(game)

        assert plus(game, only_oid(game, BEAR, 0)) == 2

    def test_a_token_does_not(self, builder):
        """ "**nontoken**" -- the deck's 4/4 Angel tokens never proliferate."""
        game = self.board(builder)
        create_token(game.state, ANGEL_TOKEN, 0)
        pick_everything(game)

        assert plus(game, only_oid(game, BEAR, 0)) == 1

    def test_its_own_arrival_does_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS, PLAINS])
            .battlefield(0, [BEAR], counters={"+1/+1": 1})
            .battlefield(1, [PLAINS])
            .hand(0, ["metastatic_evangel", ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .build()
        )
        cast_only(game, "metastatic_evangel")
        pick_everything(game)

        assert plus(game, only_oid(game, BEAR, 0)) == 1

    def test_a_noncreature_permanent_does_not(self, builder):
        game = self.board(builder, hand=["court_of_grace"])
        cast_only(game, "court_of_grace")
        pick_everything(game)

        assert plus(game, only_oid(game, BEAR, 0)) == 1


class TestNornsChoirmaster:
    """ "Whenever a commander you control enters or attacks, proliferate." """

    def test_your_commander_entering_proliferates(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["norn_s_choirmaster", PLAINS, PLAINS])
            .battlefield(0, [BEAR], counters={"+1/+1": 1})
            .commander(0, [GIADA])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .build()
        )
        cast_only(game, GIADA)
        pick_everything(game)

        assert game.state.objects[only_oid(game, GIADA, 0)].zone is Zone.BATTLEFIELD
        assert plus(game, only_oid(game, BEAR, 0)) == 2

    def test_the_same_card_that_is_not_your_commander_does_not(self, builder):
        """The near miss: "a legendary creature" or "an Angel" is not "a commander"."""
        game = (
            builder(players=2)
            .battlefield(0, ["norn_s_choirmaster", PLAINS, PLAINS])
            .battlefield(0, [BEAR], counters={"+1/+1": 1})
            .battlefield(1, [PLAINS])
            .hand(0, [GIADA, ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .build()
        )
        cast_only(game, GIADA)
        pick_everything(game)

        assert plus(game, only_oid(game, BEAR, 0)) == 1

    def test_an_opponents_commander_entering_does_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["norn_s_choirmaster", PLAINS])
            .battlefield(0, [BEAR], counters={"+1/+1": 1})
            .battlefield(1, [PLAINS, PLAINS])
            .commander(1, [GIADA])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(1)
            .build()
        )
        cast_only(game, GIADA, pid=1)
        pick_everything(game)

        assert plus(game, only_oid(game, BEAR, 0)) == 1

    def swing(self, builder, *, commander: bool):
        game = (
            builder(players=2)
            .battlefield(0, ["norn_s_choirmaster", GIADA, PLAINS])
            .battlefield(0, [BEAR], counters={"+1/+1": 1})
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.BEGIN_COMBAT)
            .build()
        )
        giada = only_oid(game, GIADA, 0)
        if commander:
            make_commander(game, giada)
        attack_options(game)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER and a.source == giada
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pick_everything(game)
        return game

    def test_your_commander_attacking_proliferates(self, builder):
        game = self.swing(builder, commander=True)

        assert plus(game, only_oid(game, BEAR, 0)) == 2

    def test_a_non_commander_attacking_does_not(self, builder):
        game = self.swing(builder, commander=False)

        assert plus(game, only_oid(game, BEAR, 0)) == 1


class TestWojekInvestigator:
    """ "At the beginning of your upkeep, investigate once for each opponent who has
    more cards in hand than you." """

    def clues(self, builder, hands):
        game = before_my_turn(builder, ["wojek_investigator"], players=3, hands=hands)
        to_my_main(game)
        return len(tokens(game, "clue_token"))

    def test_one_clue_per_opponent_with_more_cards(self, builder):
        """Seat 1 holds three to my one; seat 2 holds one, the same as me."""
        assert self.clues(builder, {1: [BEAR, BEAR]}) == 1

    def test_an_equal_hand_is_not_more(self, builder):
        """ "**more** cards" -- the boundary. Everyone holds one."""
        assert self.clues(builder, {}) == 0

    def test_two_such_opponents_are_two_clues(self, builder):
        """ "once **for each** opponent", not once if any."""
        assert self.clues(builder, {1: [BEAR, BEAR], 2: [BEAR, BEAR]}) == 2

    def test_it_reads_your_hand_not_a_fixed_number(self, builder):
        """Hold three and the seat holding three no longer counts."""
        assert self.clues(builder, {0: [BEAR, BEAR], 1: [BEAR, BEAR]}) == 0


class TestLyraArchangelOfDawn:
    """ "Whenever you gain life, put a +1/+1 counter on each Angel you control."

    Her printed text is the trigger and flying; there is no anthem line to test.
    """

    def board(self, builder, *, active: int = 0):
        return (
            builder(players=2)
            .battlefield(0, ["lyra_archangel_of_dawn", SMALL_ANGEL, BEAR, PLAINS, PLAINS])
            .battlefield(1, [SMALL_ANGEL, PLAINS, PLAINS])
            .hand(0, [ANCHOR, ANCHOR])
            .hand(1, [ANCHOR, ANCHOR])
            .active(active)
            .build()
        )

    def test_gaining_life_grows_each_of_your_angels(self, builder):
        """Lyra herself included -- "each Angel you control" has no "other"."""
        game = self.board(builder)
        cast(game, ANCHOR)

        assert plus(game, only_oid(game, "lyra_archangel_of_dawn")) == 1
        assert plus(game, only_oid(game, SMALL_ANGEL, 0)) == 1

    def test_a_non_angel_gets_nothing(self, builder):
        game = self.board(builder)
        cast(game, ANCHOR)

        assert plus(game, only_oid(game, BEAR, 0)) == 0

    def test_an_opponents_angel_gets_nothing(self, builder):
        game = self.board(builder)
        cast(game, ANCHOR)

        assert plus(game, only_oid(game, SMALL_ANGEL, 1)) == 0

    def test_an_opponent_gaining_life_does_nothing(self, builder):
        """ "Whenever **you** gain life"."""
        game = self.board(builder, active=1)
        cast(game, ANCHOR, pid=1)

        assert plus(game, only_oid(game, "lyra_archangel_of_dawn")) == 0
        assert plus(game, only_oid(game, SMALL_ANGEL, 1)) == 0

    def test_each_gain_is_its_own_counter(self, builder):
        game = self.board(builder)
        cast(game, ANCHOR)
        cast(game, ANCHOR)

        assert plus(game, only_oid(game, SMALL_ANGEL, 0)) == 2


# ----------------------------------------------------------------------
# "if you gained life this turn": the end-step Angel makers
# ----------------------------------------------------------------------


def end_step_tokens(builder, card: str, gained: int, *, active: int = 0, token: str) -> int:
    """``card`` on player 0's side; player 0 gains ``gained`` during ``active``'s
    main phase; run to that turn's end step and count player 0's ``token``s.

    The gain is the primitive rather than a spell so the amount is exact: every
    gain spell in the pool is a fixed number, and the claims are about the
    boundary between two adjacent ones.
    """
    from automtg.engine.primitives import gain_life

    game = (
        builder(players=2)
        .battlefield(0, [card, PLAINS])
        .battlefield(1, [PLAINS])
        .hand(0, [ANCHOR])
        .hand(1, [ANCHOR])
        .active(active)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    if gained:
        assert gain_life(game.state, 0, gained) == gained
    pass_until(game, lambda g: g.state.step is Step.END_STEP and g.state.active_player == active)
    settle(game)
    assert game.state.active_player == active, "measured in the same turn's end step"
    return len(tokens(game, token))


class TestObNixilisTheAscended:
    """ "When Ob Nixilis enters, destroy all tapped creatures your opponents
    control. You gain 1 life for each creature destroyed this way." / "At the
    beginning of each end step, if you gained life this turn, create a 4/4 white
    Angel creature token with flying." """

    def arrive(self, builder, theirs_tapped, theirs_untapped=(), mine_tapped=()):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 7)
            .battlefield(0, list(mine_tapped), tapped=True)
            .battlefield(1, list(theirs_tapped), tapped=True)
            .battlefield(1, [*theirs_untapped, PLAINS])
            .hand(0, ["ob_nixilis_the_ascended", ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .build()
        )
        before = life(game)
        cast(game, "ob_nixilis_the_ascended")
        return game, life(game) - before

    def test_it_destroys_the_tapped_and_gains_one_each(self, builder):
        game, gained = self.arrive(builder, [BEAR, BEAR], [BEAR])

        assert [o.def_id for o in game.state.battlefield_objects(1) if o.def_id == BEAR] == [BEAR]
        assert not game.state.objects[only_oid(game, BEAR, 1)].tapped, "the untapped one stays"
        assert gained == 2

    def test_your_own_tapped_creatures_are_spared(self, builder):
        """ "tapped creatures **your opponents** control"."""
        game, gained = self.arrive(builder, [], mine_tapped=[BEAR])

        assert game.state.objects[only_oid(game, BEAR, 0)].zone is Zone.BATTLEFIELD
        assert gained == 0

    def test_an_indestructible_creature_survives_and_is_not_counted(self, builder):
        """ "for each creature **destroyed this way**", not for each tapped creature.

        Two tapped creatures, one of them Darksteel Myr: one destroyed, one life.
        """
        game, gained = self.arrive(builder, ["darksteel_myr", BEAR])

        assert game.state.objects[only_oid(game, "darksteel_myr", 1)].zone is Zone.BATTLEFIELD
        assert [o for o in game.state.battlefield_objects(1) if o.def_id == BEAR] == []
        assert gained == 1

    def test_its_arrival_gain_turns_on_its_own_end_step_angel(self, builder):
        """The two lines are one engine: kill one tapped creature, gain 1, and the
        same turn's end step makes the Angel."""
        game, gained = self.arrive(builder, [BEAR])
        assert gained == 1
        pass_until(game, lambda g: g.state.step is Step.END_STEP)
        settle(game)

        assert len(tokens(game, ANGEL_TOKEN)) == 1

    def test_gaining_life_makes_an_angel_at_your_end_step(self, builder):
        assert end_step_tokens(builder, "ob_nixilis_the_ascended", 1, token=ANGEL_TOKEN) == 1

    def test_no_life_gained_no_angel(self, builder):
        assert end_step_tokens(builder, "ob_nixilis_the_ascended", 0, token=ANGEL_TOKEN) == 0

    def test_it_also_fires_at_an_opponents_end_step(self, builder):
        """ "At the beginning of **each** end step" -- gain on their turn, Angel on theirs."""
        assert (
            end_step_tokens(builder, "ob_nixilis_the_ascended", 1, active=1, token=ANGEL_TOKEN)
            == 1
        )


class TestResplendentAngel:
    """ "At the beginning of each end step, if you gained 5 or more life this turn,
    create a 4/4 white Angel creature token with flying and vigilance." /
    "{3}{W}{W}{W}: Until end of turn, this creature gets +2/+2 and gains lifelink." """

    def test_five_life_makes_an_angel(self, builder):
        assert end_step_tokens(builder, "resplendent_angel", 5, token=VIGILANT_ANGEL_TOKEN) == 1

    def test_four_life_is_one_short(self, builder):
        """ "5 **or more**" -- the boundary, from below."""
        assert end_step_tokens(builder, "resplendent_angel", 4, token=VIGILANT_ANGEL_TOKEN) == 0

    def test_it_fires_at_an_opponents_end_step(self, builder):
        assert (
            end_step_tokens(builder, "resplendent_angel", 6, active=1, token=VIGILANT_ANGEL_TOKEN)
            == 1
        )

    def test_the_token_has_flying_and_vigilance(self, builder):
        """The plain Angel token would pass a count; this one has vigilance too."""
        from automtg.engine.primitives import gain_life

        game = anchored(builder, ["resplendent_angel"])
        gain_life(game.state, 0, 5)
        pass_until(game, lambda g: g.state.step is Step.END_STEP)
        settle(game)
        (token,) = tokens(game, VIGILANT_ANGEL_TOKEN)

        assert {"flying", "vigilance"} <= keywords(game, token.oid)
        assert pt(game, token.oid) == (4, 4)

    def pumped(self, builder):
        game = anchored(builder, ["resplendent_angel", *[PLAINS] * 6])
        angel = only_oid(game, "resplendent_angel")
        (pump,) = activations(game, angel)
        game.apply(pump)
        settle(game)
        return game, angel

    def test_the_activation_gives_plus_two_and_lifelink(self, builder):
        game, angel = self.pumped(builder)

        assert pt(game, angel) == (5, 5)
        assert "lifelink" in keywords(game, angel)

    def test_and_both_wear_off_at_end_of_turn(self, builder):
        """ "**Until end of turn**" -- the pump is not a counter."""
        game, angel = self.pumped(builder)
        pass_until(game, lambda g: g.state.active_player == 1 and g.state.step is Step.UPKEEP)

        assert pt(game, angel) == (3, 3)
        assert "lifelink" not in keywords(game, angel)
        assert plus(game, angel) == 0


class TestValkyrieHarbinger:
    """ "At the beginning of each end step, if you gained 4 or more life this turn,
    create a 4/4 white Angel creature token with flying and vigilance." """

    def test_four_life_makes_an_angel(self, builder):
        assert end_step_tokens(builder, "valkyrie_harbinger", 4, token=VIGILANT_ANGEL_TOKEN) == 1

    def test_three_life_is_one_short(self, builder):
        """The threshold is 4, not Resplendent's 5 -- and not "any life"."""
        assert end_step_tokens(builder, "valkyrie_harbinger", 3, token=VIGILANT_ANGEL_TOKEN) == 0

    def test_it_fires_at_an_opponents_end_step(self, builder):
        assert (
            end_step_tokens(builder, "valkyrie_harbinger", 4, active=1, token=VIGILANT_ANGEL_TOKEN)
            == 1
        )

    def test_an_opponent_gaining_life_does_not_count(self, builder):
        """ "if **you** gained" -- player 1 gains 10 and the Harbinger's side sees none."""
        from automtg.engine.primitives import gain_life

        game = anchored(builder, ["valkyrie_harbinger"])
        gain_life(game.state, 1, 10)
        pass_until(game, lambda g: g.state.step is Step.END_STEP)
        settle(game)

        assert tokens(game, VIGILANT_ANGEL_TOKEN) == []


# ----------------------------------------------------------------------
# lands, removal and the sweeper
# ----------------------------------------------------------------------


class TestBondersEnclave:
    """ "{3}, {T}: Draw a card. Activate only if you control a creature with power
    4 or greater." """

    def board(self, builder, mine=(), theirs=()):
        game = anchored(builder, ["bonders_enclave", *[PLAINS] * 3, *mine], theirs)
        return game, only_oid(game, "bonders_enclave")

    def test_with_a_power_four_creature_it_draws(self, builder):
        game, enclave = self.board(builder, [BIG_ANGEL])
        before = len(game.state.players[0].hand)
        (draw,) = activations(game, enclave, 1)
        game.apply(draw)
        settle(game)

        assert len(game.state.players[0].hand) == before + 1
        assert game.state.objects[enclave].tapped

    def test_power_three_is_not_enough(self, builder):
        """The boundary: a 3/3 Resplendent Angel does not turn it on."""
        game, enclave = self.board(builder, ["resplendent_angel"])

        assert activations(game, enclave, 1) == []

    def test_an_opponents_big_creature_does_not_count(self, builder):
        """ "if **you** control"."""
        game, enclave = self.board(builder, [SMALL_ANGEL], [BIG_ANGEL])

        assert activations(game, enclave, 1) == []

    def test_a_counter_grown_creature_counts(self, builder):
        """Power, not printed power: a 1/1 with three +1/+1 counters is a 4/4."""
        game = (
            builder(players=2)
            .battlefield(0, ["bonders_enclave", *[PLAINS] * 4])
            .battlefield(0, [SMALL_ANGEL], counters={"+1/+1": 3})
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .build()
        )

        assert len(activations(game, only_oid(game, "bonders_enclave"), 1)) == 1


class TestEmeriaTheSkyRuin:
    """ "At the beginning of your upkeep, if you control seven or more Plains, you
    may return target creature card from your graveyard to the battlefield." """

    def upkeep(self, builder, *, plains: int, their_plains: int = 0):
        """``plains`` counts every Plains player 0 controls, the anchor's included."""
        b = (
            builder(players=2)
            .battlefield(0, ["emeria_the_sky_ruin", *[PLAINS] * plains])
            .battlefield(1, [PLAINS] * max(1, their_plains))
            .graveyard(0, [BIG_ANGEL])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(1)
            .step(Step.END_STEP)
        )
        game = b.build()
        pass_until(game, lambda g: g.state.active_player == 0 and g.state.step is Step.UPKEEP)
        for _ in range(50):
            decision = game.pending()
            if decision is None or (
                decision.kind is DecisionKind.PRIORITY
                and not game.state.stack
                and not game.state.pending_triggers
            ):
                break
            if decision.kind is DecisionKind.MAY:
                game.apply(find_action(game, ActionKind.YES))
            elif decision.kind is DecisionKind.CHOOSE_OBJECTS:
                choice = next(
                    (a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None
                )
                game.apply(choice or find_action(game, ActionKind.FINISH_DECLARATION))
            else:
                game.apply(_default_answer(game, decision))
        return game

    def returned(self, game) -> bool:
        return any(o.def_id == BIG_ANGEL for o in game.state.battlefield_objects(0))

    def test_seven_plains_returns_a_creature(self, builder):
        game = self.upkeep(builder, plains=7)

        assert self.returned(game)

    def test_six_plains_is_one_short(self, builder):
        """Emeria is a land but not a Plains, so it does not count itself."""
        game = self.upkeep(builder, plains=6)

        assert not self.returned(game)

    def test_the_opponents_plains_do_not_count(self, builder):
        """ "if **you** control seven or more Plains"."""
        game = self.upkeep(builder, plains=6, their_plains=10)

        assert not self.returned(game)

    def test_it_enters_tapped(self, builder):
        game = anchored(builder, [], hand=["emeria_the_sky_ruin"])
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND))
        settle(game)

        assert game.state.objects[only_oid(game, "emeria_the_sky_ruin")].tapped


class TestGraspOfFate:
    """ "When this enchantment enters, for each opponent, exile up to one target
    nonland permanent that player controls until this enchantment leaves the
    battlefield." """

    def cast(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, [*[PLAINS] * 3, SMALL_ANGEL])
            .battlefield(1, [BEAR, PLAINS])
            .battlefield(2, ["sol_ring", PLAINS])
            .hand(0, ["grasp_of_fate", ANCHOR])
            .hand(1, [ANCHOR])
            .hand(2, [ANCHOR])
            .active(0)
            .build()
        )
        cast_only(game, "grasp_of_fate")
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_OBJECTS,
        )
        offered = {
            game.state.objects[t.id].def_id
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE
            for t in a.targets
        }
        pick_everything(game)
        return game, offered

    def test_only_opponents_nonland_permanents_are_offered(self, builder):
        """No land, and nothing of yours -- the Segovian Angel is not on the list."""
        _game, offered = self.cast(builder)

        assert offered == {BEAR, "sol_ring"}

    def test_one_from_each_opponent_is_exiled(self, builder):
        """ "for **each** opponent" -- a Bear from one seat and a Sol Ring from the other."""
        game, _offered = self.cast(builder)

        assert game.state.objects[oid_of(game, BEAR)].zone is Zone.EXILE
        assert game.state.objects[oid_of(game, "sol_ring")].zone is Zone.EXILE

    def test_they_come_back_when_it_leaves(self, builder):
        """ "**until** this enchantment leaves the battlefield" -- under their owners."""
        from automtg.engine.zones import destroy

        game, _offered = self.cast(builder)
        destroy(game.state, only_oid(game, "grasp_of_fate"))
        game.state.bump_chars()
        settle(game)

        bear, ring = oid_of(game, BEAR), oid_of(game, "sol_ring")
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[ring].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].controller == 1
        assert game.state.objects[ring].controller == 2


def oid_of(game, def_id: str) -> int:
    """The one object with this def_id, in whatever zone it is."""
    (oid,) = [o.oid for o in game.state.objects.values() if o.def_id == def_id]
    return oid


class TestFarewell:
    """ "Choose one or more -- Exile all artifacts. / Exile all creatures. / Exile
    all enchantments. / Exile all graveyards." """

    def table(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * 6, SMALL_ANGEL, "sol_ring", "court_of_grace"])
            .battlefield(1, [PLAINS, BEAR, "sol_ring", "grasp_of_fate"])
            .graveyard(0, [BIG_ANGEL])
            .graveyard(1, [BEAR])
            .hand(0, ["farewell", ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .build()
        )

    def cast_modes(self, game, picks) -> None:
        cast_only(game, "farewell")
        for _ in range(200):
            decision = game.pending()
            if decision is None:
                break
            if decision.kind is DecisionKind.CHOOSE_MODE:
                for want in picks:
                    game.apply(
                        next(
                            a
                            for a in game.legal_actions()
                            if a.kind is ActionKind.CHOOSE and a.choice == want
                        )
                    )
                done = next(
                    (a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION),
                    None,
                )
                if done is not None:
                    game.apply(done)
                continue
            if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
                break
            game.apply(_default_answer(game, decision))

    def on_battlefield(self, game, def_id: str) -> int:
        return sum(1 for o in game.state.battlefield if game.state.objects[o].def_id == def_id)

    def test_all_four_modes_are_offered(self, builder):
        game = self.table(builder)
        cast_only(game, "farewell")
        pass_until(
            game, lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_MODE
        )

        assert [o.value for o in game.pending().options] == [0, 1, 2, 3]

    def test_creatures_only_leaves_the_rest(self, builder):
        """One mode is one mode: artifacts, enchantments and graveyards stay."""
        game = self.table(builder)
        self.cast_modes(game, [1])

        assert self.on_battlefield(game, SMALL_ANGEL) == 0
        assert self.on_battlefield(game, BEAR) == 0
        assert self.on_battlefield(game, "sol_ring") == 2
        assert self.on_battlefield(game, "court_of_grace") == 1
        assert len(game.state.players[1].graveyard) == 1

    def test_the_creatures_are_exiled_not_destroyed(self, builder):
        """ "**Exile** all creatures" -- not destroy, so nothing lands in a graveyard
        and indestructible would not save anything."""
        game = self.table(builder)
        angel = only_oid(game, SMALL_ANGEL, 0)
        self.cast_modes(game, [1])

        assert game.state.objects[angel].zone is Zone.EXILE

    def test_two_modes_both_happen(self, builder):
        """Artifacts and graveyards: both Sol Rings and both yards, and the creatures stay."""
        game = self.table(builder)
        self.cast_modes(game, [0, 3])

        assert self.on_battlefield(game, "sol_ring") == 0
        assert self.on_battlefield(game, SMALL_ANGEL) == 1
        assert self.on_battlefield(game, "grasp_of_fate") == 1
        assert game.state.players[1].graveyard == []
        assert [game.state.objects[o].def_id for o in game.state.players[0].graveyard] == [
            "farewell"
        ], "the yards were exiled, then Farewell itself went to the graveyard"

    def test_enchantments_mode_exiles_both_sides(self, builder):
        game = self.table(builder)
        self.cast_modes(game, [2])

        assert self.on_battlefield(game, "court_of_grace") == 0
        assert self.on_battlefield(game, "grasp_of_fate") == 0
        assert self.on_battlefield(game, SMALL_ANGEL) == 1
        assert self.on_battlefield(game, PLAINS) == 7, "lands are never touched"


# ----------------------------------------------------------------------
# the commander with the rest of the list
# ----------------------------------------------------------------------


class TestGiadaWithTheDeck:
    """Giada's own lines have their unit tests (`test_enters_with_counters_per_angel.py`
    on a stand-in, and the lane's tests on the real card); these are the places
    the deck leans on her together with another card."""

    def test_an_angel_entering_beside_giada_and_another_angel_gets_two(self, builder):
        """One counter for each Angel already there: Giada and the Segovian Angel."""
        game = anchored(builder, [GIADA, SMALL_ANGEL, *[PLAINS] * 4], hand=[BIG_ANGEL])
        make_commander(game, only_oid(game, GIADA))
        serra = cast(game, BIG_ANGEL)

        assert plus(game, serra) == 2
        assert pt(game, serra) == (6, 6)

    def test_a_non_angel_beside_her_gets_none(self, builder):
        game = anchored(builder, [GIADA, *[PLAINS] * 3], hand=[NOT_AN_ANGEL])
        magus = cast(game, NOT_AN_ANGEL)

        assert plus(game, magus) == 0

    def test_youthful_valkyrie_sees_the_counters_and_grows_too(self, builder):
        """Giada's counters go on the arrival, Youthful Valkyrie's on herself."""
        game = anchored(builder, [GIADA, "youthful_valkyrie"], hand=[SMALL_ANGEL])
        angel = cast(game, SMALL_ANGEL)

        assert plus(game, angel) == 2, "Giada and the Valkyrie were already there"
        assert plus(game, only_oid(game, "youthful_valkyrie")) == 1

    def aspirant(self, builder, *, giada: bool, hand):
        mine = ["starnheim_aspirant", PLAINS, PLAINS] + ([GIADA] if giada else [])
        return frozen(builder, mine, [PLAINS], hand=hand)

    def test_aspirant_and_giadas_mana_cast_a_five_drop_angel_off_two_plains(self, builder):
        """Serra Angel is {3}{W}{W}; the Aspirant takes {2}, and Giada's Angel-only
        {W} plus two Plains pay the {1}{W}{W} that is left."""
        game = self.aspirant(builder, giada=True, hand=[BIG_ANGEL])

        assert BIG_ANGEL in offers(game, 0, ActionKind.CAST)

    def test_and_it_resolves_with_giadas_counter(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["starnheim_aspirant", PLAINS, PLAINS, GIADA])
            .battlefield(1, [PLAINS])
            .hand(0, [BIG_ANGEL])
            .hand(1, [ANCHOR])
            .active(0)
            .build()
        )
        serra = cast(game, BIG_ANGEL)

        assert game.state.objects[serra].zone is Zone.BATTLEFIELD
        assert game.state.objects[only_oid(game, GIADA)].tapped, "Giada's mana was spent"
        assert plus(game, serra) == 1, "one Angel already there -- the Aspirant is a Human"

    def test_without_giada_two_plains_are_short(self, builder):
        game = self.aspirant(builder, giada=False, hand=[BIG_ANGEL])

        assert BIG_ANGEL not in offers(game, 0, ActionKind.CAST)

    def test_giadas_mana_does_not_pay_for_a_non_angel(self, builder):
        """The near miss: three sources and a three-mana non-Angel, still uncastable,
        because one of the three only pays for Angels. Starnheim Aspirant itself is
        the {2}{W} non-Angel here."""
        game = frozen(builder, [PLAINS, PLAINS, GIADA], [PLAINS], hand=["starnheim_aspirant"])

        assert "starnheim_aspirant" not in offers(game, 0, ActionKind.CAST)

    def test_and_three_plains_do_pay_for_it(self, builder):
        """The control: the same spell, with an unrestricted third source."""
        game = frozen(builder, [PLAINS, PLAINS, PLAINS], [PLAINS], hand=["starnheim_aspirant"])

        assert "starnheim_aspirant" in offers(game, 0, ActionKind.CAST)
