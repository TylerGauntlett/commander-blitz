"""The How to Train Ur-Dragon deck's engine, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card **once**, in one
fixed sandbox, and reads the board. Three of its documented limits land on the
six cards below, and they are the six the deck is actually built out of:

- **A trigger that never fires cannot be asserted.** Every card in this file is
  a Dragon-enters trigger or an attack trigger, and the sandbox casts the card
  under test and stops: nothing enters *after* it and nothing ever attacks. So
  the authored expectation for Dragon Tempest, Scourge of Valkas, Lathliss,
  Miirym and Terror of the Peaks is "it resolved onto the battlefield", which
  says nothing about the sentence each of them is bought for.
- **A static that changes a later spell's price is invisible.** The Ur-Dragon's
  eminence discount is charged to a *different* card, and it is charged from the
  **command zone**, which is a zone the sandbox never uses.
- **It never activates an ability.** Lathliss's `{1}{R}` team pump and
  Scourge's `{R}` self pump are therefore unasserted anywhere, and they are left
  unasserted here too: neither is why either card is in this deck, and a file
  that tried to cover both halves of six cards would stop being about the engine
  the deck is built out of. They are the honest gap in this file.

These six multiply each other -- one Dragon entering is three triggers and two
tokens -- so a card that is slightly wrong here is not slightly wrong on the
board. Each class is one card, and each asserts the **near miss** as well: the
reading that would be wrong if the card were mis-written. Several of these were
mis-written during authoring and caught, and the near misses are which ones.

**Why every position here is small.** "Any target" enumerates the battlefield
before it reaches the players, and legality caps one ability's target
combinations at `targeting.MAX_TARGET_OPTIONS` (12). The eleventh permanent
therefore pushes both seats off the end of the list, and a damage trigger that
can no longer be aimed at anybody quietly takes the first option instead --
which is a Mountain. `settle`'s ``aim`` asserts the seat was really on offer
rather than preferring it, so a position that outgrows the cap fails loudly here
instead of measuring a land.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.costs import cost_reduction
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.player_statics import spell_life_tax
from automtg.engine.primitives import create_token
from tests.conftest import (
    _default_answer,
    count_on_battlefield,
    oids_of,
    only_oid,
    pass_until,
)

DRAGON = "t_plain_dragon"  # {4}{R} 4/4 flying, no text -- a Dragon and nothing else
BEAR = "t_bear"  # {1}{G} 2/2 -- not a Dragon, and no flying either
BOLT = "t_bolt"  # {R} instant, 3 damage to any target -- the opponent's removal
ANCHOR = "t_plain_instant"  # {W}, gain 1 life -- a reason for priority to stop
LEGEND = "old_gnawbone"  # {5}{G}{G} 7/7 **Legendary** Dragon, for the legend rule
TOKEN = "dragon_5_5_r_flying"  # the token Lathliss makes, and a Dragon in its own right
#: Every position deals its owner an exact library, so a draw can be counted
#: without a "before" reading -- see `TestTheUrDragon.test_it_draws_one_card…`.
LIBRARY = 20


def board(
    builder,
    lands=("mountain",) * 5,
    *,
    mine=(),
    hand=(),
    theirs=(),
    hand1=(),
    life1=40,
):
    """Player 0's precombat main, with as few permanents as the claim allows.

    Small on purpose -- see the module docstring on `MAX_TARGET_OPTIONS`. The
    opponent gets a board only when a test needs them to hold priority or hold a
    spell, because every permanent either seat controls is counted by the cap.
    """
    return (
        builder(players=2)
        .battlefield(0, [*lands, *mine])
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .hand(1, list(hand1))
        .library(0, ["swamp"] * LIBRARY)
        .library(1, ["swamp"] * LIBRARY)
        .life(1, life1)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .max_turns(2)
        .build()
    )


def casts(game, card_id: str) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
    ]


def cast(game, card_id: str) -> int:
    """Cast ``card_id`` from hand. Returns its oid; does **not** settle."""
    action = next(iter(casts(game, card_id)))
    game.apply(action)
    return action.source


def settle(game, *, aim: int | None = None, accept: bool = False, limit: int = 400) -> None:
    """Let the stack empty.

    ``aim`` is the seat a trigger's "any target" is pointed at, and it is
    **asserted** rather than preferred: with no seat on offer `_default_answer`
    takes the first option, which on a board of Mountains is a Mountain, and the
    test would then read an unchanged life total as the card misfiring.

    ``accept`` says yes to the "you may" halves -- the passive default declines
    every `MAY`, which is right for a board that only needs to settle and wrong
    for The Ur-Dragon, whose second half lives behind the prompt.
    """
    hit = False
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            break
        if aim is not None:
            aimed = [
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE
                and any(t.kind == "player" and t.id == aim for t in (a.targets or ()))
            ]
            if aimed:
                game.apply(aimed[0])
                hit = True
                continue
        if accept and decision.kind is DecisionKind.MAY:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
            continue
        # Priority with nothing waiting is the end, and the stack being empty is
        # not enough on its own: a trigger that asks its question before
        # resolving leaves both the stack and the queue empty with its decision
        # still pending, and a loop that stopped there would answer nothing and
        # report that the card did nothing.
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            break
        game.apply(_default_answer(game, decision))
    else:
        raise AssertionError("the stack did not empty")
    if aim is not None:
        assert hit, f"P{aim} was never offered as a target -- see MAX_TARGET_OPTIONS"


def target_options(game) -> list:
    """The refs the pending target decision is offering."""
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS
    return [option.ref for option in decision.options]


def tokens_of(game, pid: int = 0) -> list[str]:
    return [obj.def_id for obj in game.state.battlefield_objects(pid) if obj.is_token]


def damage_to(game, pid: int = 1) -> int:
    return 40 - game.state.players[pid].life


class TestTheUrDragon:
    """The commander, and the card gate 5 could say the least about.

    "Eminence — As long as this is in the command zone or on the battlefield,
    other Dragon spells you cast cost {1} less to cast", and "Whenever one or
    more Dragons you control attack, draw that many cards, then you may put a
    permanent card from your hand onto the battlefield."

    Neither line is reachable in the authoring sandbox. The first is a *price*,
    charged to a different card, and the sandbox casts one card onto an empty
    board; worse, it is charged from the **command zone**, which is where this
    card starts every real game and where the sandbox never puts anything. The
    second needs a combat. So the authored expectation for a nine-mana commander
    was "it is on the battlefield".
    """

    def table(self, builder, *, command=(), battlefield=(), lands=6, spell=DRAGON):
        return (
            builder(players=2)
            .battlefield(0, ["mountain"] * lands + list(battlefield))
            .hand(0, [spell])
            .commander(0, list(command))
            .active(0)
            .max_turns(1)
            .build()
        )

    def discount(self, builder, spell: str, **kwargs) -> int:
        game = self.table(builder, spell=spell, **kwargs)
        return cost_reduction(game.state, 0, game.state.registry.get(spell))

    def test_a_dragon_spell_is_cheaper_from_the_command_zone(self, builder):
        """The zone is the whole card. A nine-mana commander is in the command
        zone for most of a game, and a battlefield-only reading of "as long as"
        passes all six gates while doing nothing for any of those turns."""
        assert self.discount(builder, DRAGON, command=["the_ur_dragon"]) == 1

    def test_and_it_is_the_commander_doing_it(self, builder):
        """The control. Without it the test above is "a Dragon costs what it costs"."""
        assert self.discount(builder, DRAGON) == 0

    def test_it_discounts_from_the_battlefield_too(self, builder):
        """"…or on the battlefield" is the second zone on one static."""
        assert self.discount(builder, DRAGON, battlefield=["the_ur_dragon"]) == 1

    def test_it_does_not_discount_itself(self, builder):
        """"**Other** Dragon spells." The near miss, and a live one.

        The Ur-Dragon is itself a Dragon spell, and it is cast *out of* the very
        zone its own static is now collected from -- the price is read while the
        object is still in the command zone -- so a static without the word
        would shave {1} off its own nine-mana cast.
        """
        assert self.discount(builder, "the_ur_dragon", command=["the_ur_dragon"]) == 0

    def test_a_non_dragon_spell_is_unaffected(self, builder):
        """"Dragon spells", not "spells". A Bear pays its own way."""
        assert self.discount(builder, BEAR, command=["the_ur_dragon"]) == 0

    def test_the_cast_is_offered_at_the_reduced_price(self, builder):
        """Legality and payment read one function, so the offer is the charge.

        {4}{R} on four Mountains is a mana short, which is the only boundary at
        which a {1} discount is observable from the action list at all.
        """
        assert not casts(self.table(builder, lands=4), DRAGON)
        assert casts(self.table(builder, lands=4, command=["the_ur_dragon"]), DRAGON)

    # -- the attack trigger ------------------------------------------------

    def combat(self, builder, creatures, *, attack=None, hand=()):
        """Player 0 controls ``creatures`` and swings with ``attack`` at player 1.

        The two lists are separate because one claim below is about a creature
        that stays home: "Dragons you control **attack**" is not "Dragons you
        control", and a position where every creature swings cannot tell them
        apart.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["forest", *creatures])
            .battlefield(1, ["plains"])
            .hand(0, list(hand))
            .library(0, ["swamp"] * LIBRARY)
            .library(1, ["swamp"] * LIBRARY)
            .active(0)
            .step(Step.UNTAP)
            .max_turns(2)
            .build()
        )
        pass_until(
            game,
            lambda g: g.pending() is not None
            and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        for card_id in creatures if attack is None else attack:
            for oid in oids_of(game, card_id, 0):
                game.apply(
                    next(
                        a
                        for a in game.legal_actions()
                        if a.kind is ActionKind.ADD_ATTACKER
                        and a.source == oid
                        and any(t.kind == "player" and t.id == 1 for t in a.targets)
                    )
                )
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )
        return game

    def test_it_draws_one_card_for_each_attacking_dragon(self, builder):
        """"Draw **that many** cards." Two Dragons in a three-creature swing.

        Counted against `LIBRARY` rather than a reading taken after the
        declaration closes, because with an empty hand nobody has a play and the
        engine's auto-pass resolves the trigger inside the very `apply` that
        finishes the attack -- a "before" read there is already the "after".
        """
        game = self.combat(builder, ["the_ur_dragon", DRAGON, BEAR])
        settle(game)

        assert len(game.state.players[0].library) == LIBRARY - 2

    def test_the_bear_in_that_swing_is_not_counted(self, builder):
        """The near miss: "that many" is the Dragons, not the attackers.

        Three creatures attacked and two cards were drawn, so the same position
        is the proof and the counterexample at once -- said as its own claim
        because a count of attackers is the obvious wrong reading of "one or
        more Dragons you control attack, draw that many".
        """
        game = self.combat(builder, ["the_ur_dragon", DRAGON, BEAR])
        settle(game)

        assert len(game.state.players[0].library) != LIBRARY - 3

    def test_a_dragon_that_stays_home_does_not_fire_it(self, builder):
        """The boundary, and the reason the trigger carries a condition at all:
        The Ur-Dragon is on the battlefield and only the Bear swings, so "one or
        more Dragons you control **attack**" is false and nothing is drawn."""
        game = self.combat(builder, ["the_ur_dragon", BEAR], attack=[BEAR])
        settle(game, accept=True)

        assert len(game.state.players[0].library) == LIBRARY

    def take_the_may(self, game, card_id: str) -> None:
        """Say yes to "you may put a permanent card…", and name the card.

        Named rather than left to the default chooser: the two cards the trigger
        just drew land in the same hand, so "the first option" is a Swamp as
        soon as the hand order changes, and the test would then pass while
        asserting nothing about the card it meant.
        """
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.MAY,
        )
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE
                and a.targets
                and game.state.objects[a.targets[0].id].def_id == card_id
            )
        )
        settle(game)

    def test_it_puts_a_permanent_from_hand_onto_the_battlefield(self, builder):
        """The second half, behind a "you may" the passive default declines."""
        game = self.combat(builder, ["the_ur_dragon"], hand=[DRAGON])
        self.take_the_may(game, DRAGON)

        assert count_on_battlefield(game, DRAGON, 0) == 1
        assert not any(
            game.state.objects[oid].def_id == DRAGON for oid in game.state.players[0].hand
        )

    def test_it_is_put_onto_the_battlefield_rather_than_cast(self, builder):
        """"Put onto the battlefield", and the whole value of the line.

        The position holds one Forest and no red source at all, so {4}{R} is
        unpayable -- the Dragon is not on offer as a cast and arrives anyway.
        """
        game = self.combat(builder, ["the_ur_dragon"], hand=[DRAGON])
        assert not casts(game, DRAGON), "the position cannot pay for it"
        self.take_the_may(game, DRAGON)

        assert count_on_battlefield(game, DRAGON, 0) == 1

    def test_an_instant_in_hand_is_not_offered(self, builder):
        """"A **permanent** card." The near miss, and it is one the trigger
        would otherwise take: the drawn cards land in the same hand."""
        game = self.combat(builder, ["the_ur_dragon"], hand=[DRAGON, BOLT])
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.MAY,
        )
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))

        offered = {
            game.state.objects[ref.id].def_id for ref in target_options(game) if ref is not None
        }
        assert DRAGON in offered
        assert BOLT not in offered, "an instant is not a permanent card"


class TestDragonTempest:
    """"Whenever a creature you control with flying enters, it gains haste until
    end of turn", and "Whenever a Dragon you control enters, it deals X damage
    to any target, where X is the number of Dragons you control."

    Two triggers on one enchantment, and the sandbox reaches neither: nothing
    enters after the enchantment it is testing. The authored expectation is that
    the enchantment is on the battlefield.
    """

    def test_a_lone_dragon_deals_one(self, builder):
        """X counts the Dragon that just arrived -- the trigger is "enters",
        so it is already on the battlefield when X is read."""
        game = board(builder, mine=["dragon_tempest"], hand=[DRAGON])
        cast(game, DRAGON)
        settle(game, aim=1)

        assert damage_to(game) == 1

    def test_the_damage_scales_with_the_dragon_count(self, builder):
        """The whole card. A static 1 damage would pass the test above."""
        game = board(builder, mine=["dragon_tempest", DRAGON, DRAGON], hand=[DRAGON])
        cast(game, DRAGON)
        settle(game, aim=1)

        assert damage_to(game) == 3, "the two already out, plus the one that just landed"

    def test_it_can_be_pointed_at_a_player(self, builder):
        """"Any target" -- the regression test, and the near miss that was
        really written during authoring.

        A sibling card in this deck had the same clause narrowed to creatures,
        which loads clean, passes every gate and turns a finisher into a
        removal spell that cannot close a game. A seat has to be on the list.
        """
        game = board(builder, mine=["dragon_tempest"], hand=[DRAGON])
        cast(game, DRAGON)

        assert any(ref is not None and ref.kind == "player" for ref in target_options(game))

    def test_and_at_a_creature(self, builder):
        """The other half of "any target": both readings have to be offered."""
        game = board(builder, mine=["dragon_tempest"], hand=[DRAGON], theirs=[BEAR])
        cast(game, DRAGON)
        refs = target_options(game)

        assert any(
            ref is not None and ref.kind == "object" and game.state.objects[ref.id].def_id == BEAR
            for ref in refs
        )

    def test_a_dragon_that_enters_gains_haste(self, builder):
        """The other trigger, and the reason this deck can cast a Dragon and
        attack with it on the same turn. Read before cleanup: the grant is
        until end of turn, and a test that let the turn roll over would see
        nothing whatever the card did -- hence the opponent's anchor."""
        game = board(
            builder,
            mine=["dragon_tempest"],
            hand=[DRAGON],
            theirs=["plains"],
            hand1=[ANCHOR],
        )
        dragon = cast(game, DRAGON)
        settle(game, aim=1)

        assert {"flying", "haste"} <= {str(k) for k in chars(game.state, dragon).keywords}

    def test_a_creature_without_flying_gains_nothing(self, builder):
        """"…with flying". The near miss on the first trigger, and a Bear is
        also not a Dragon, so the same cast shows the second one silent too."""
        game = board(
            builder,
            lands=("forest", "forest"),
            mine=["dragon_tempest"],
            hand=[BEAR],
            theirs=["plains"],
            hand1=[ANCHOR],
        )
        bear = cast(game, BEAR)
        settle(game)

        assert "haste" not in {str(k) for k in chars(game.state, bear).keywords}
        assert damage_to(game) == 0, "a Bear is not a Dragon"


class TestScourgeOfValkas:
    """"Whenever this creature or another Dragon you control enters, it deals X
    damage to any target, where X is the number of Dragons you control."

    Dragon Tempest's sentence with one word changed, and the word is the card:
    "**this creature** or another" means it fires as it lands. The gate casts it
    onto an empty board and can see neither half.
    """

    def test_it_counts_itself_as_it_enters(self, builder):
        """The near miss, and the one that makes the card look inert: Scourge
        arriving alone deals **1**, not 0. A trigger that read the board before
        the Dragon finished entering, or one written as "another Dragon", would
        deal nothing at all here and pass a gate that only checks the board."""
        game = board(builder, hand=["scourge_of_valkas"])
        cast(game, "scourge_of_valkas")
        settle(game, aim=1)

        assert damage_to(game) == 1

    def test_the_count_includes_every_dragon_you_control(self, builder):
        game = board(builder, mine=[DRAGON, DRAGON], hand=["scourge_of_valkas"])
        cast(game, "scourge_of_valkas")
        settle(game, aim=1)

        assert damage_to(game) == 3, "two already out, plus itself"

    def test_another_dragon_entering_fires_it_too(self, builder):
        """"…or another Dragon you control enters." The second clause, which
        needs a Dragon to arrive *after* the card under test -- exactly what the
        one-cast sandbox cannot arrange."""
        game = board(builder, mine=["scourge_of_valkas"], hand=[DRAGON])
        cast(game, DRAGON)
        settle(game, aim=1)

        assert damage_to(game) == 2, "Scourge and the newcomer"

    def test_a_non_dragon_entering_does_not_fire_it(self, builder):
        """The boundary: "Dragon", not "creature"."""
        game = board(
            builder,
            lands=("forest", "forest"),
            mine=["scourge_of_valkas"],
            hand=[BEAR],
        )
        cast(game, BEAR)
        settle(game)

        assert damage_to(game) == 0

    def test_it_can_be_pointed_at_a_player(self, builder):
        """The same regression as Dragon Tempest's, on the same clause."""
        game = board(builder, hand=["scourge_of_valkas"])
        cast(game, "scourge_of_valkas")

        assert any(ref is not None and ref.kind == "player" for ref in target_options(game))


class TestLathlissDragonQueen:
    """"Whenever another **nontoken** Dragon you control enters, create a 5/5 red
    Dragon creature token with flying."

    Two words carry the card, and gate 5 can test neither: "another" needs a
    second Dragon and "nontoken" needs the token it just made to *not* count.
    """

    def test_a_nontoken_dragon_makes_a_token(self, builder):
        game = board(builder, mine=["lathliss_dragon_queen"], hand=[DRAGON])
        cast(game, DRAGON)
        settle(game)

        assert tokens_of(game) == [TOKEN]

    def test_the_token_it_made_does_not_trigger_it_again(self, builder):
        """The near miss that does not merely mis-count -- it does not
        terminate. The token is a 5/5 Dragon entering under the same
        controller, so a trigger without "nontoken" makes a token that makes a
        token, forever. Exactly one, and the count is the whole assertion."""
        game = board(builder, mine=["lathliss_dragon_queen"], hand=[DRAGON])
        cast(game, DRAGON)
        settle(game)

        assert count_on_battlefield(game, TOKEN, 0) == 1

    def test_a_token_dragon_entering_does_not_trigger_it(self, builder):
        """The same word, asked directly: a token Dragon arriving from anywhere
        else -- another Lathliss, a copy effect, Dracogenesis -- is not a
        nontoken Dragon either."""
        game = board(builder, lands=(), mine=["lathliss_dragon_queen"])
        create_token(game.state, TOKEN, 0)
        settle(game)

        assert count_on_battlefield(game, TOKEN, 0) == 1, "the one that was made, and no reply"

    def test_lathliss_herself_entering_makes_nothing(self, builder):
        """"**Another**". She is a Dragon, and she is not another one."""
        game = board(builder, lands=("mountain",) * 6, hand=["lathliss_dragon_queen"])
        cast(game, "lathliss_dragon_queen")
        settle(game)

        assert tokens_of(game) == []

    def test_a_non_dragon_creature_makes_nothing(self, builder):
        game = board(
            builder,
            lands=("forest", "forest"),
            mine=["lathliss_dragon_queen"],
            hand=[BEAR],
        )
        cast(game, BEAR)
        settle(game)

        assert tokens_of(game) == []

    def test_the_token_is_a_5_5_flier(self, builder):
        """The printed body, which the gate could not see because the token is
        only ever made by a trigger that never fired."""
        game = board(builder, mine=["lathliss_dragon_queen"], hand=[DRAGON])
        cast(game, DRAGON)
        settle(game)

        token = only_oid(game, TOKEN, 0)
        body = chars(game.state, token)
        assert (body.power, body.toughness) == (5, 5)
        assert "flying" in {str(k) for k in body.keywords}
        assert "Dragon" in body.subtypes, "it counts itself for Scourge and Tempest"


class TestMiirymSentinelWyrm:
    """"Whenever another nontoken Dragon you control enters, create a token
    that's a copy of it, **except the token isn't legendary**."

    The exception is the card. Almost every Dragon worth copying in this deck is
    legendary, so a copy that kept the supertype would be binned by the legend
    rule (704.5j) the instant it arrived -- an ability that loads, resolves,
    creates a permanent and achieves nothing, which no board state would report.
    """

    def test_it_copies_an_entering_dragon(self, builder):
        game = board(builder, mine=["miirym_sentinel_wyrm"], hand=[DRAGON])
        cast(game, DRAGON)
        settle(game)

        assert count_on_battlefield(game, DRAGON, 0) == 2
        assert tokens_of(game) == [DRAGON], "the copy is a token; the original is not"

    def test_the_copy_of_a_legendary_dragon_is_not_legendary(self, builder):
        game = board(builder, lands=("forest",) * 7, mine=["miirym_sentinel_wyrm"], hand=[LEGEND])
        cast(game, LEGEND)
        settle(game)

        token = next(obj for obj in game.state.battlefield_objects(0) if obj.is_token)
        assert "Legendary" not in chars(game.state, token.oid).supertypes

    def test_and_both_of_them_survive(self, builder):
        """The claim the exception exists for, stated as the board: two Old
        Gnawbones, one legendary and one not, and the legend rule takes
        neither. A copy that kept the supertype would leave one."""
        game = board(builder, lands=("forest",) * 7, mine=["miirym_sentinel_wyrm"], hand=[LEGEND])
        original = cast(game, LEGEND)
        settle(game)

        assert count_on_battlefield(game, LEGEND, 0) == 2
        assert game.state.objects[original].zone is Zone.BATTLEFIELD
        assert "Legendary" in chars(game.state, original).supertypes, "the original is untouched"

    def test_it_is_a_copy_rather_than_a_5_5(self, builder):
        """"A copy **of it**" -- Lathliss's trigger one card over makes a fixed
        5/5, and these two are otherwise the same sentence."""
        game = board(builder, lands=("forest",) * 7, mine=["miirym_sentinel_wyrm"], hand=[LEGEND])
        cast(game, LEGEND)
        settle(game)

        token = next(obj for obj in game.state.battlefield_objects(0) if obj.is_token)
        body = chars(game.state, token.oid)
        assert (body.power, body.toughness) == (7, 7), "Old Gnawbone's body, not a 5/5"
        assert token.def_id == LEGEND

    def test_the_copy_does_not_copy_itself(self, builder):
        """"**Nontoken**", and the same non-termination Lathliss's word stops:
        the copy is a Dragon entering under the same controller."""
        game = board(builder, mine=["miirym_sentinel_wyrm"], hand=[DRAGON])
        cast(game, DRAGON)
        settle(game)

        assert count_on_battlefield(game, DRAGON, 0) == 2, "one card, one copy, and no more"

    def test_a_token_dragon_is_not_copied(self, builder):
        game = board(builder, lands=(), mine=["miirym_sentinel_wyrm"])
        create_token(game.state, TOKEN, 0)
        settle(game)

        assert count_on_battlefield(game, TOKEN, 0) == 1

    def test_miirym_herself_entering_copies_nothing(self, builder):
        """"Another". She is a nontoken Dragon entering under her own control."""
        game = board(
            builder,
            lands=("forest", "forest", "island", "mountain", "mountain", "mountain"),
            hand=["miirym_sentinel_wyrm"],
        )
        cast(game, "miirym_sentinel_wyrm")
        settle(game)

        assert tokens_of(game) == []


class TestTerrorOfThePeaks:
    """"Spells your opponents cast that target this creature cost an additional
    3 life to cast", and "Whenever another creature you control enters, this
    creature deals damage equal to **that creature's** power to any target."

    A price charged to somebody else's spell, and a trigger that needs a second
    creature: the sandbox casts one card, belonging to one player, and stops.
    """

    def test_the_damage_is_the_entering_creature_s_power(self, builder):
        game = board(
            builder,
            lands=("forest", "forest"),
            mine=["terror_of_the_peaks"],
            hand=[BEAR],
        )
        cast(game, BEAR)
        settle(game, aim=1)

        assert damage_to(game) == 2, "the Bear's power"

    def test_not_terror_s_own_power(self, builder):
        """The near miss. Terror is a 5/4 and "this creature deals damage" is
        the sentence's subject, so reading the power off the wrong creature is
        the natural mistake -- and invisible until two different creatures with
        two different powers have entered."""
        game = board(
            builder,
            lands=("forest", "forest"),
            mine=["terror_of_the_peaks"],
            hand=[BEAR],
        )
        cast(game, BEAR)
        settle(game, aim=1)

        assert damage_to(game) != 5

    def test_a_bigger_creature_deals_more(self, builder):
        """The other half of the same claim: the number moves with the arrival."""
        game = board(builder, mine=["terror_of_the_peaks"], hand=[DRAGON])
        cast(game, DRAGON)
        settle(game, aim=1)

        assert damage_to(game) == 4, "the Dragon is a 4/4"

    def test_it_does_not_fire_on_itself(self, builder):
        """"**Another** creature." Terror arriving alone deals nothing, which is
        also the only thing the authoring sandbox was in a position to check."""
        game = board(builder, hand=["terror_of_the_peaks"])
        cast(game, "terror_of_the_peaks")
        settle(game)

        assert damage_to(game) == 0

    def test_it_can_be_pointed_at_a_player(self, builder):
        game = board(
            builder,
            lands=("forest", "forest"),
            mine=["terror_of_the_peaks"],
            hand=[BEAR],
        )
        cast(game, BEAR)

        assert any(ref is not None and ref.kind == "player" for ref in target_options(game))

    # -- the life tax ------------------------------------------------------

    def duel(self, builder, *, life1=40, theirs=()):
        """Terror facing an opponent holding removal and the mana for it."""
        return board(
            builder,
            lands=("mountain",),
            mine=["terror_of_the_peaks"],
            theirs=["mountain", *theirs],
            hand1=[BOLT],
            life1=life1,
        )

    def aim(self, game, oid: int):
        """The target tuple an opponent's Bolt aimed at ``oid`` would carry."""
        pass_until(game, lambda g: bool(casts(g, BOLT)))
        return next(a for a in casts(game, BOLT) if any(t.id == oid for t in a.targets)).targets

    def test_an_opponent_s_spell_aimed_at_it_costs_three_life(self, builder):
        game = self.duel(builder)
        terror = only_oid(game, "terror_of_the_peaks", 0)

        assert spell_life_tax(game.state, 1, game.state.registry.get(BOLT), self.aim(game, terror)) == 3

    def test_the_same_spell_aimed_elsewhere_is_free(self, builder):
        """"…that target **this creature**". The clause is the card."""
        game = self.duel(builder, theirs=[BEAR])
        bear = only_oid(game, BEAR, 1)

        assert spell_life_tax(game.state, 1, game.state.registry.get(BOLT), self.aim(game, bear)) == 0

    def test_its_own_controller_is_not_taxed(self, builder):
        """"Spells your **opponents** cast."""
        game = self.duel(builder)
        terror = only_oid(game, "terror_of_the_peaks", 0)

        assert spell_life_tax(game.state, 0, game.state.registry.get(BOLT), self.aim(game, terror)) == 0

    def test_the_life_is_actually_paid(self, builder):
        """A cost, not a trigger: paid as the spell is cast, and paid whether or
        not the spell goes on to do anything."""
        game = self.duel(builder, life1=20)
        terror = only_oid(game, "terror_of_the_peaks", 0)
        pass_until(game, lambda g: bool(casts(g, BOLT)))
        game.apply(next(a for a in casts(game, BOLT) if any(t.id == terror for t in a.targets)))
        settle(game)

        assert game.state.players[1].life == 17
        assert game.state.objects[terror].zone is Zone.BATTLEFIELD, "a 5/4 survives 3 damage"

    def test_an_opponent_who_cannot_pay_cannot_aim_at_it(self, builder):
        """601.2h: an unpayable cost makes the line illegal, so the Dragon is
        not a legal target at all -- which is the whole difference from ward,
        where the spell is cast first and dies unpaid."""
        game = self.duel(builder, life1=2)
        terror = only_oid(game, "terror_of_the_peaks", 0)
        pass_until(game, lambda g: bool(casts(g, BOLT)) or not g.legal_actions())

        assert casts(game, BOLT), "the Bolt is still castable"
        assert not any(
            any(t.id == terror for t in a.targets) for a in casts(game, BOLT)
        ), "an opponent at 2 life cannot pay 3"

    def test_and_may_pay_down_to_exactly_zero(self, builder):
        """118.4. At 3 life the tax is payable, and the offer stands."""
        game = self.duel(builder, life1=3)
        terror = only_oid(game, "terror_of_the_peaks", 0)
        pass_until(game, lambda g: bool(casts(g, BOLT)))

        assert any(any(t.id == terror for t in a.targets) for a in casts(game, BOLT))
