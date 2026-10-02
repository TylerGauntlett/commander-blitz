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
