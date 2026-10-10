"""The Millton deck, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card once, in one fixed
sandbox, and reads the board. Three of its documented limits bite most of this
deck:

- **It never activates an ability.** Cryptic Trilobite's two lines and Sphinx's
  Tutelage's loot are the whole of those cards below the first sentence.
- **A trigger that never fires cannot be asserted.** Nothing in that position
  draws a card, mills, casts a spell *after* the card under test, or discards
  one, so Sphinx's Tutelage, Bruvac, Cloudstone Curio and both of Orvar's
  triggers have honest expectations of "nothing happened".
- **A static that changes a later event is invisible.** Bruvac doubles a mill
  nobody performs; Jace replaces a draw from a library the sandbox keeps full.

So the authoring expectations are floors, and these are the observations. Each
class is one card and asserts the printed sentence the gate could not reach --
and, where the card was written against a near miss, the thing that would be
wrong if it had been written the other way.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.primitives import mill_cards
from commanderblitz.engine.replacements import draw as draw_with_replacements
from tests.conftest import action_for_card, count_on_battlefield, only_oid, pass_until

ISLAND = "island"


def cast(game, card_id: str, pid: int = 0) -> int:
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
    action = action_for_card(game, ActionKind.CAST, card_id)
    oid = action.source
    game.apply(action)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return oid


def cast_only(game, card_id: str, pid: int = 0) -> int:
    """Put ``card_id`` on the stack and stop, leaving its triggers to `settle`.

    `cast` drives to an empty stack through `pass_until`, which declines every
    `may` on the way -- so a card whose trigger asks one has already been
    answered no by the time a test could say yes.
    """
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().player == pid
        and any(
            a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == card_id
            for a in g.legal_actions()
        ),
    )
    action = action_for_card(game, ActionKind.CAST, card_id)
    oid = action.source
    game.apply(action)
    return oid


def draw(game, pid: int, count: int = 1):
    """Run a draw through the replacement seam, declining every question.

    `primitives.draw_cards` is the wrong door and is the whole subtlety of two
    of the cards below: the draw replacements and the draw trigger both live in
    `replacements._draw_one`, so a test that called the primitive would bypass
    Jace's replacement and never fire Sphinx's Tutelage.
    """
    gen = draw_with_replacements(game.state, pid, count)
    send = None
    while True:
        try:
            gen.send(send)
        except StopIteration as stop:
            return stop.value
        send = []


def settle(game, *, accept: bool = False, limit: int = 200) -> None:
    """Drive to the next empty-stack priority window.

    ``accept`` answers a `may` with **yes**. `conftest._default_answer` is
    deliberately "the most passive legal answer" and says no, which is right for
    a test asking whether a card misfires and wrong for one asking whether its
    optional half works at all -- Cloudstone Curio's "you **may** return" is the
    whole of its second sentence, and declining it reads exactly like a trigger
    that never fired.
    """
    from tests.conftest import _default_answer

    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            return
        if accept and decision.kind is DecisionKind.MAY:
            yes = next(a for a in game.legal_actions() if a.kind is ActionKind.YES)
            game.apply(yes)
            continue
        game.apply(_default_answer(game, decision))


def activation(game, card_id: str, index: int):
    oid = only_oid(game, card_id)
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid and a.ability_index == index
        ),
        None,
    )


class TestBruvacTheGrandiloquent:
    """"If an opponent would mill one or more cards, they mill twice that many
    cards instead."

    The commander, and the card the whole list is built on. A replacement on an
    event the gate never causes, so its authoring expectation can only say that
    a 2/3 arrived.
    """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["bruvac_the_grandiloquent", *([ISLAND] * 4)])
            .library(1, ["plains"] * 40)
            .library(0, ["plains"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_an_opponents_mill_is_doubled(self, builder):
        game = self.position(builder)
        mill_cards(game.state, 1, 2)
        assert len(game.state.players[1].graveyard) == 4

    def test_your_own_mill_is_not(self, builder):
        """"an **opponent** would mill" -- a doubler that read both sides would
        deck its own controller, and the board looks identical either way."""
        game = self.position(builder)
        mill_cards(game.state, 0, 2)
        assert len(game.state.players[0].graveyard) == 2

    def test_it_doubles_a_mill_the_opponent_caused_themselves(self, builder):
        """The reason the replacement lives in `mill_cards` rather than in the
        `mill` op: it applies whoever is doing the milling."""
        game = self.position(builder)
        mill_cards(game.state, 1, 5)
        assert len(game.state.players[1].graveyard) == 10

    def test_it_stops_when_bruvac_leaves(self, builder):
        game = self.position(builder)
        game.state.battlefield.remove(only_oid(game, "bruvac_the_grandiloquent"))
        game.state.bump_chars()
        mill_cards(game.state, 1, 2)
        assert len(game.state.players[1].graveyard) == 2


class TestJaceWielderOfMysteries:
    """"If you would draw a card while your library has no cards in it, you win
    the game instead."

    A replacement on the one draw the sandbox never makes.
    """

    def position(self, builder, library: int):
        return (
            builder(players=2)
            .battlefield(0, ["jace_wielder_of_mysteries", *([ISLAND] * 4)])
            .library(0, ["plains"] * library)
            .library(1, ["plains"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_drawing_from_an_empty_library_wins(self, builder):
        game = self.position(builder, library=0)
        draw(game, 0)
        assert game.state.game_over
        assert not game.state.players[0].has_lost

    def test_the_will_lose_flag_is_never_set(self, builder):
        """The whole design. `draw_cards` treats an empty library as an attempt
        and sets the 104.3c flag; replacing means it is never called, and a card
        that won *after* drawing would lose the race to the state-based action."""
        game = self.position(builder, library=0)
        draw(game, 0)
        assert not game.state.players[0].attempted_draw_from_empty

    def test_an_ordinary_draw_is_untouched(self, builder):
        game = self.position(builder, library=5)
        before = len(game.state.players[0].hand)
        draw(game, 0)
        assert len(game.state.players[0].hand) == before + 1
        assert not game.state.game_over

    def test_an_opponent_decking_is_unaffected(self, builder):
        """The near miss a player-agnostic implementation passes silently."""
        game = self.position(builder, library=5)
        game.state.players[1].library.clear()
        draw(game, 1)
        assert game.state.players[1].attempted_draw_from_empty, (
            "the opponent decks as usual -- Jace is not a player-agnostic replacement"
        )


class TestSphinxsTutelage:
    """"Whenever you draw a card, target opponent mills two cards. If two nonland
    cards that share a color were milled this way, repeat this process."

    The gate draws nothing after the cast, so its expectation is that an
    enchantment arrived.
    """

    def position(self, builder, top: list[str]):
        return (
            builder(players=2)
            .battlefield(0, ["sphinx_s_tutelage", *([ISLAND] * 6)])
            .library(0, ["plains"] * 20)
            .library(1, [*top, *["plains"] * 40])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_drawing_mills_the_opponent_two(self, builder):
        game = self.position(builder, ["forest", "plains"])
        draw(game, 0)
        game._advance()
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert len(game.state.players[1].graveyard) == 2

    def test_two_cards_sharing_a_colour_repeat_the_process(self, builder):
        """Two blue cards on top, then two lands to stop it."""
        game = self.position(builder, ["counterspell", "opt", "plains", "plains"])
        draw(game, 0)
        game._advance()
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert len(game.state.players[1].graveyard) == 4

    def test_two_lands_do_not(self, builder):
        """The `not_types` filter: lands are dropped before the pairing."""
        game = self.position(builder, ["plains", "plains"])
        draw(game, 0)
        game._advance()
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert len(game.state.players[1].graveyard) == 2

    def test_the_loot_ability_is_offered(self, builder):
        """"{5}{U}: Draw a card, then discard a card." -- gate 5 never activates."""
        game = self.position(builder, ["plains", "plains"])
        game._advance()
        assert activation(game, "sphinx_s_tutelage", 1) is not None


class TestCrypticTrilobite:
    """A printed 0/0 whose size, mana and growth are three separate lines the
    gate reaches none of."""

    def position(self, builder, counters: int = 3):
        game = (
            builder(players=2)
            .battlefield(0, ["cryptic_trilobite", *([ISLAND] * 4)])
            .library(0, ["plains"] * 20)
            .library(1, ["plains"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        oid = only_oid(game, "cryptic_trilobite")
        game.state.objects[oid].counters["+1/+1"] = counters
        game.state.objects[oid].entered_turn = -1
        game.state.bump_chars()
        return game, oid

    def test_it_is_as_big_as_its_counters(self, builder):
        game, oid = self.position(builder, counters=3)
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (3, 3)

    def test_the_mana_ability_is_offered(self, builder):
        game, _ = self.position(builder)
        game._advance()
        assert activation(game, "cryptic_trilobite", 0) is not None

    def test_the_counter_ability_is_offered(self, builder):
        game, _ = self.position(builder)
        game._advance()
        assert activation(game, "cryptic_trilobite", 1) is not None

    def test_its_mana_cannot_pay_for_a_spell(self, builder):
        """"Spend this mana only to activate abilities." The whole restriction,
        and the half that makes it not just ordinary colourless mana."""
        from commanderblitz.engine.costs import mana_sources
        from commanderblitz.engine.mana import CAST, SpendPurpose

        game, oid = self.position(builder)
        for source in mana_sources(game.state, 0, purpose=SpendPurpose(CAST, frozenset())):
            assert source.oid != oid


class TestTidalBarracuda:
    """Two sentences pointing opposite ways, on one card."""

    def position(self, builder, active: int = 0):
        return (
            builder(players=2)
            .battlefield(0, ["tidal_barracuda", *([ISLAND] * 4)])
            .battlefield(1, [ISLAND] * 4)
            .hand(0, ["opt"])
            .hand(1, ["opt"])
            .library(0, ["plains"] * 20)
            .library(1, ["plains"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(active)
            .build(advance=False)
        )

    def test_its_controller_casts_at_instant_speed(self, builder):
        from commanderblitz.engine.player_statics import player_casts_as_though_flash

        game = self.position(builder, active=1)
        assert player_casts_as_though_flash(game.state, 0)

    def test_and_so_does_the_opponent_on_their_own_turn(self, builder):
        """"**Any** player", which is the half that makes this a group hug card."""
        from commanderblitz.engine.player_statics import player_casts_as_though_flash

        game = self.position(builder, active=1)
        assert player_casts_as_though_flash(game.state, 1)

    def test_the_opponent_holds_something_castable_at_all(self, builder):
        """The control that keeps the next assertion from passing for the wrong
        reason: Opt targets nothing, so the only thing that can withhold it is
        the prohibition."""
        from commanderblitz.engine import legality

        game = self.position(builder, active=1)
        assert any(
            a.kind is ActionKind.CAST for a in legality._priority_actions(game.state, 1)
        )

    def test_but_the_opponent_casts_nothing_during_your_turn(self, builder):
        """The second sentence, and 101.2: the "can't" beats the "may" the first
        sentence just handed out."""
        from commanderblitz.engine import legality

        game = self.position(builder, active=0)
        assert not any(
            a.kind is ActionKind.CAST
            for a in legality._priority_actions(game.state, 1)
        )

    def test_and_does_on_their_own(self, builder):
        from commanderblitz.engine import legality

        game = self.position(builder, active=1)
        assert any(
            a.kind is ActionKind.CAST
            for a in legality._priority_actions(game.state, 1)
        )


class TestCloudstoneCurio:
    """"Whenever a nonartifact permanent you control enters, you may return
    another permanent you control that shares a permanent type with it."

    Nothing enters after the card under test in the gate's sandbox.
    """

    def position(self, builder, hand: list[str], board: list[str]):
        return (
            builder(players=2)
            .battlefield(0, ["cloudstone_curio", *board, *([ISLAND] * 6)])
            .hand(0, list(hand))
            .library(0, ["plains"] * 20)
            .library(1, ["plains"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_a_creature_entering_can_bounce_another_creature(self, builder):
        game = self.position(builder, ["persistent_petitioners"], ["persistent_petitioners"])
        cast_only(game, "persistent_petitioners")
        settle(game, accept=True)
        # Two entered the battlefield over the game and one went back to hand.
        assert count_on_battlefield(game, "persistent_petitioners", 0) == 1
        assert len(game.state.players[0].hand) == 1

    def test_an_artifact_entering_does_not_trigger_it(self, builder):
        """"a **nonartifact** permanent you control enters"."""
        game = self.position(builder, ["alloy_myr"], ["persistent_petitioners"])
        cast_only(game, "alloy_myr")
        settle(game, accept=True)
        assert count_on_battlefield(game, "persistent_petitioners", 0) == 1
        assert game.state.players[0].hand == [], "nothing was returned"


class TestTeferiMasterOfTime:
    """A planeswalker whose first line is about *when* its other three work."""

    def position(self, builder, active: int = 1):
        game = (
            builder(players=2)
            .battlefield(0, ["teferi_master_of_time", *([ISLAND] * 4)])
            .battlefield(1, [ISLAND, "t_bear"])
            .library(0, ["plains"] * 20)
            .library(1, ["plains"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(active)
            .build(advance=False)
        )
        return game, only_oid(game, "teferi_master_of_time")

    def test_he_enters_with_three_loyalty(self, builder):
        game, teferi = self.position(builder)
        assert game.state.objects[teferi].counters.get("loyalty") == 3

    def test_his_loyalty_abilities_work_on_an_opponents_turn(self, builder):
        """The printed first line, and the only one gate 5 could never see."""
        from commanderblitz.engine import legality

        game, teferi = self.position(builder, active=1)
        offered = [
            a
            for a in legality._priority_actions(game.state, 0)
            if a.kind is ActionKind.ACTIVATE and a.source == teferi
        ]
        assert offered, "on any player's turn, any time you could cast an instant"

    def test_but_still_only_one_of_them_a_turn(self, builder):
        """606.3's other half, which the permission does not lift."""
        from commanderblitz.engine import legality

        game, teferi = self.position(builder, active=1)
        first = next(
            a
            for a in legality._priority_actions(game.state, 0)
            if a.kind is ActionKind.ACTIVATE and a.source == teferi
        )
        game.state.turn_ledger.activated(teferi, first.ability_index)
        assert not [
            a
            for a in legality._priority_actions(game.state, 0)
            if a.kind is ActionKind.ACTIVATE and a.source == teferi
        ]


class TestPersistentPetitioners:
    """"A deck can have any number of cards named Persistent Petitioners", and a
    second ability whose cost is four other Advisors."""

    def position(self, builder, advisors: int):
        return (
            builder(players=2)
            .battlefield(0, ["persistent_petitioners"] * advisors + [ISLAND] * 4)
            .library(0, ["plains"] * 20)
            .library(1, ["plains"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_the_tap_four_advisors_ability_needs_four_advisors(self, builder):
        game = self.position(builder, advisors=2)
        game._advance()
        oid = next(
            o
            for o in game.state.battlefield
            if game.state.objects[o].def_id == "persistent_petitioners"
        )
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid and a.ability_index == 1
        ]

    def test_and_is_offered_with_five(self, builder):
        """Four to tap, plus the one whose ability it is."""
        game = self.position(builder, advisors=5)
        for oid in list(game.state.battlefield):
            game.state.objects[oid].entered_turn = -1
        game.state.bump_chars()
        game._advance()
        assert any(
            a.kind is ActionKind.ACTIVATE
            and game.state.objects[a.source].def_id == "persistent_petitioners"
            and a.ability_index == 1
            for a in game.legal_actions()
        )
