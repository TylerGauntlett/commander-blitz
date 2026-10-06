"""The Aesi precon (Reap the Tides), card by card: the landfall engines, the
counter payoffs and the one static that works on someone else's turn.

Every card here cleared the six authoring gates, and gate 5 measured most of them
at "it is on the battlefield" -- the gate's documented limit, not the cards':

- **It never plays a land after the card under test.** Rampaging Baloths, Seer's
  Sundial, Retreat to Kazandu and the two Expeditions are landfall cards, and
  landfall is the only thing they do. The sandbox casts them and stops.
- **It never activates an ability.** The Expeditions' sacrifice and
  Sharktocrab's adapt are the payoffs, and nothing in the gate reaches them.
- **It never casts a second creature, and never reaches another turn.** Fathom
  Mage's evolve needs a bigger creature to enter after it, and Murkfiend Liege's
  third line happens during an *opponent's* untap step.

(Aesi itself, Verdant Kraken and Turntimber Symbiosis are covered in
test_lander_commander_deck.py.) Each class quotes the card and asserts what the
gate could not reach, and each pins a near miss: the opponent's land, the
declined `may`, the creature that is not bigger, the third quest counter that is
not there.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import (
    _default_answer,
    action_for_card,
    oids_of,
    only_oid,
    pass_until,
)

BALOTHS = "rampaging_baloths"
BEAST = "beast_4_4_g"
SUNDIAL = "seer_s_sundial"
IOR = "ior_ruin_expedition"
KHALNI = "khalni_heart_expedition"
KAZANDU = "retreat_to_kazandu"
FATHOM = "fathom_mage"
SHARKTOCRAB = "sharktocrab"
LIEGE = "murkfiend_liege"
BEAR = "t_bear"  # {1}{G} 2/2, green
# A castable instant in each seat's hand: with no play available to anybody the
# engine's auto-pass runs whole turns inside one `apply` and overshoots the step
# under test.
ANCHOR = "t_plain_instant"


def resolve(game, *, yes: bool = True, mode: int | None = None, limit: int = 200) -> None:
    """Let the stack empty: ``yes`` to every `MAY`, ``mode`` for a modal
    trigger, the first offered object for every choice."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if yes else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        if decision.kind is DecisionKind.CHOOSE_MODE and mode is not None:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == mode
                )
            )
            continue
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choose = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
            if choose:
                game.apply(choose[0])
                continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def position(builder, mine, *, theirs=("plains",), hand=("forest",), **kw):
    """Seat 0's precombat main, with ``mine`` in play and ``hand`` to play."""
    b = (
        builder(players=2)
        .battlefield(0, list(mine), **kw)
        .battlefield(1, list(theirs))
        .hand(0, [*hand, ANCHOR])
        .hand(1, [ANCHOR])
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .max_turns(4)
    )
    return b.build()


def play_land(game, card_id: str = "forest", **answers) -> None:
    game.apply(action_for_card(game, ActionKind.PLAY_LAND, card_id))
    resolve(game, **answers)


def hand_size(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


def library_size(game, pid: int = 0) -> int:
    return len(game.state.players[pid].library)


def in_graveyard(game, card_id: str, pid: int = 0) -> bool:
    return any(game.state.objects[o].def_id == card_id for o in game.state.players[pid].graveyard)


def activate(game, source: int) -> None:
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == source)
    )


def can_activate(game, source: int) -> bool:
    return any(a.kind is ActionKind.ACTIVATE and a.source == source for a in game.legal_actions())


class TestRampagingBaloths:
    """"Trample. Landfall -- Whenever a land you control enters, create a 4/4
    green Beast creature token." """

    def test_a_land_makes_a_four_four_beast(self, builder):
        game = position(builder, [BALOTHS, "plains"])
        play_land(game)
        [beast] = oids_of(game, BEAST, 0)
        c = chars(game.state, beast)
        assert (c.power, c.toughness) == (4, 4)
        assert "Beast" in c.subtypes
        assert game.state.objects[beast].is_token

    def test_a_land_you_do_not_control_makes_nothing(self, builder):
        """The Baloths are seat 1's; seat 0's land drop is not theirs."""
        game = position(builder, ["plains"], theirs=(BALOTHS, "plains"))
        play_land(game)
        assert oids_of(game, BEAST) == []


class TestSeersSundial:
    """"Landfall -- Whenever a land you control enters, you may pay {2}. If you
    do, draw a card." """

    def test_paying_two_draws_a_card(self, builder):
        game = position(builder, [SUNDIAL, "island", "island"])
        hand, library = hand_size(game), library_size(game)
        play_land(game, yes=True)
        assert library_size(game) == library - 1
        assert hand_size(game) == hand, "the forest left, the drawn card arrived"
        lands = [o for o in game.state.battlefield_objects(0) if o.def_id in ("island", "forest")]
        assert sum(o.tapped for o in lands) == 2, "the {2} was paid"

    def test_declining_draws_nothing_and_taps_nothing(self, builder):
        game = position(builder, [SUNDIAL, "island", "island"])
        library = library_size(game)
        play_land(game, yes=False)
        assert library_size(game) == library
        assert not any(o.tapped for o in game.state.battlefield_objects(0))

    def test_one_mana_cannot_pay_two(self, builder):
        """Only the new forest is untapped: saying yes buys nothing."""
        game = position(builder, [SUNDIAL, "island", "island"], tapped=True)
        library = library_size(game)
        play_land(game, yes=True)
        assert library_size(game) == library


class TestIorRuinExpedition:
    """"Landfall -- Whenever a land you control enters, you may put a quest
    counter on this enchantment. Remove three quest counters from this
    enchantment and sacrifice it: Draw two cards." """

    def test_a_land_adds_a_quest_counter(self, builder):
        game = position(builder, [IOR, "plains"])
        play_land(game, yes=True)
        assert game.state.objects[only_oid(game, IOR)].counters.get("quest") == 1

    def test_the_counter_is_a_may(self, builder):
        game = position(builder, [IOR, "plains"])
        play_land(game, yes=False)
        assert game.state.objects[only_oid(game, IOR)].counters.get("quest", 0) == 0

    def test_three_counters_draw_two_and_sacrifice_it(self, builder):
        game = position(builder, [IOR, "plains"], counters={"quest": 3})
        expedition = only_oid(game, IOR)
        library = library_size(game)
        activate(game, expedition)
        resolve(game)
        assert library_size(game) == library - 2
        assert game.state.objects[expedition].zone is not Zone.BATTLEFIELD
        assert in_graveyard(game, IOR)

    def test_two_counters_are_not_enough(self, builder):
        game = position(builder, [IOR, "plains"], counters={"quest": 2})
        assert not can_activate(game, only_oid(game, IOR))


class TestKhalniHeartExpedition:
    """"Landfall -- Whenever a land you control enters, you may put a quest
    counter on this enchantment. Remove three quest counters from this
    enchantment and sacrifice it: Search your library for up to two basic land
    cards, put them onto the battlefield tapped, then shuffle." """

    def test_three_counters_fetch_two_tapped_basics(self, builder):
        game = position(builder, [KHALNI, "plains"], counters={"quest": 3})
        expedition = only_oid(game, KHALNI)
        library = library_size(game)
        activate(game, expedition)
        resolve(game)
        islands = oids_of(game, "island", 0)
        assert len(islands) == 2
        assert all(game.state.objects[o].tapped for o in islands)
        assert library_size(game) == library - 2
        assert in_graveyard(game, KHALNI)

    def test_the_fetched_lands_are_landfall(self, builder):
        """Two lands entering is two landfall triggers: two Beasts."""
        game = position(builder, [KHALNI, BALOTHS, "plains"], counters={"quest": 3})
        activate(game, only_oid(game, KHALNI))
        resolve(game)
        assert len(oids_of(game, BEAST, 0)) == 2


class TestRetreatToKazandu:
    """"Landfall -- Whenever a land you control enters, choose one -- Put a
    +1/+1 counter on target creature. / You gain 2 life." """

    def test_the_counter_mode(self, builder):
        game = position(builder, [KAZANDU, BEAR, "plains"])
        bear = only_oid(game, BEAR)
        play_land(game, mode=0)
        assert game.state.objects[bear].counters == {"+1/+1": 1}
        assert game.state.players[0].life == 40

    def test_the_life_mode(self, builder):
        game = position(builder, [KAZANDU, BEAR, "plains"])
        bear = only_oid(game, BEAR)
        play_land(game, mode=1)
        assert game.state.players[0].life == 42
        assert game.state.objects[bear].counters == {}

    def test_the_counter_targets_any_creature(self, builder):
        """"Target creature", not "a creature you control": an opponent's
        creature is on offer, and choosing it grows it."""
        game = position(builder, [KAZANDU, BEAR, "plains"], theirs=("plains", BEAR))
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_MODE,
        )
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 0)
        )
        offered = {
            a.targets[0].id for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.targets
        }
        assert offered == {mine, theirs}
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.targets and a.targets[0].id == theirs
            )
        )
        resolve(game)
        assert game.state.objects[theirs].counters == {"+1/+1": 1}
        assert game.state.objects[mine].counters == {}

    def test_with_no_creature_only_the_life_mode_is_left(self, builder):
        """601.2b via 603.3d: a mode with no legal target is not offered."""
        game = position(builder, [KAZANDU, "plains"])
        play_land(game)
        assert game.state.players[0].life == 42


class TestFathomMage:
    """"Evolve (Whenever a creature you control enters, if that creature has
    greater power or toughness than this creature, put a +1/+1 counter on this
    creature.) Whenever a +1/+1 counter is put on this creature, you may draw a
    card." """

    def cast_bears(self, builder, n: int, *, yes: bool = True):
        game = (
            builder(players=2)
            .battlefield(0, [FATHOM, *["forest"] * (2 * n)])
            .battlefield(1, ["plains"])
            .hand(0, [BEAR] * n)
            .hand(1, [ANCHOR])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(4)
            .build()
        )
        library = library_size(game)
        for _ in range(n):
            game.apply(action_for_card(game, ActionKind.CAST, BEAR))
            resolve(game, yes=yes)
        return game, only_oid(game, FATHOM), library

    def test_a_bigger_creature_evolves_it_and_draws(self, builder):
        game, mage, library = self.cast_bears(builder, 1)
        assert game.state.objects[mage].counters == {"+1/+1": 1}
        assert (chars(game.state, mage).power, chars(game.state, mage).toughness) == (2, 2)
        assert library_size(game) == library - 1

    def test_the_draw_is_a_may(self, builder):
        game, mage, library = self.cast_bears(builder, 1, yes=False)
        assert game.state.objects[mage].counters == {"+1/+1": 1}
        assert library_size(game) == library

    def test_an_equal_creature_does_not_evolve_it(self, builder):
        """The second 2/2 meets a 2/2 Mage: not greater, no counter, no card."""
        game, mage, library = self.cast_bears(builder, 2)
        assert game.state.objects[mage].counters == {"+1/+1": 1}
        assert library_size(game) == library - 1


class TestSharktocrab:
    """"{2}{G}{U}: Adapt 1. Whenever one or more +1/+1 counters are put on this
    creature, tap target creature an opponent controls. That creature doesn't
    untap during its controller's next untap step." """

    def adapt(self, builder, *, counters=None):
        game = (
            builder(players=2)
            .battlefield(0, ["forest", "forest", "island", "island", "plains"])
            .battlefield(0, [SHARKTOCRAB], counters=counters)
            .battlefield(1, [BEAR, "plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(4)
            .build()
        )
        crab = only_oid(game, SHARKTOCRAB)
        activate(game, crab)
        resolve(game)
        return game, crab, only_oid(game, BEAR, 1)

    def test_adapting_taps_their_creature(self, builder):
        game, crab, bear = self.adapt(builder)
        assert game.state.objects[crab].counters == {"+1/+1": 1}
        assert (chars(game.state, crab).power, chars(game.state, crab).toughness) == (5, 5)
        assert game.state.objects[bear].tapped

    def test_it_stays_tapped_through_their_next_untap(self, builder):
        game, _crab, bear = self.adapt(builder)
        pass_until(game, lambda g: g.state.active_player == 1 and g.state.step is Step.UPKEEP)
        assert game.state.objects[bear].tapped

    def test_with_a_counter_already_adapt_does_nothing(self, builder):
        game, crab, bear = self.adapt(builder, counters={"+1/+1": 1})
        assert game.state.objects[crab].counters == {"+1/+1": 1}
        assert not game.state.objects[bear].tapped


class TestMurkfiendLiege:
    """"Other green creatures you control get +1/+1. Other blue creatures you
    control get +1/+1. Untap all green and/or blue creatures you control during
    each other player's untap step." """

    def test_green_gets_one_green_and_blue_gets_two(self, builder):
        game = position(builder, [LIEGE, BEAR, FATHOM], theirs=(BEAR,))
        bear, mage = only_oid(game, BEAR, 0), only_oid(game, FATHOM)
        liege, their_bear = only_oid(game, LIEGE), only_oid(game, BEAR, 1)
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (3, 3)
        assert (chars(game.state, mage).power, chars(game.state, mage).toughness) == (3, 3)
        assert (chars(game.state, liege).power, chars(game.state, liege).toughness) == (4, 4)
        assert (
            chars(game.state, their_bear).power,
            chars(game.state, their_bear).toughness,
        ) == (2, 2)

    def tapped_bear_at_their_upkeep(self, builder, mine):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", *mine])
            .battlefield(0, [BEAR], tapped=True)
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(4)
            .build()
        )
        pass_until(game, lambda g: g.state.active_player == 1 and g.state.step is Step.UPKEEP)
        return game.state.objects[only_oid(game, BEAR, 0)]

    def test_your_creatures_untap_in_an_opponents_untap_step(self, builder):
        assert not self.tapped_bear_at_their_upkeep(builder, [LIEGE]).tapped

    def test_without_the_liege_they_stay_tapped(self, builder):
        assert self.tapped_bear_at_their_upkeep(builder, []).tapped
