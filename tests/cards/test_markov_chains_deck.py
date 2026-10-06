"""The Markov Chains deck, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is why this
file exists. Gate 5 casts a card once in a fixed sandbox and reads the board,
and it **declines combat** -- so a pillowfort, whose entire rules text is about
somebody else's attack, reaches the pool with the weakest honest expectation
there is: "it is on the battlefield". That is a statement that the card did not
misfire, not that it works.

So the authoring expectation is a floor, and these are the observations. Each
class is one card and asserts the printed sentence the gate could not reach.
"""

from __future__ import annotations

from automtg.engine import zones
from automtg.engine.characteristics import chars, has_keyword
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import (
    _default_answer,
    advance_to_step,
    count_on_battlefield,
    find_action,
    only_oid,
    pass_until,
)

BEAR = "grizzly_bears"  # a plain 2/2
WALKER = "t_walker"  # a loyalty-4 planeswalker with no static of its own
PRISON = "ghostly_prison"


def attack_actions(game, oid: int | None = None):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and (oid is None or a.source == oid)
    ]


def player_attacks(game, oid: int) -> dict[int, str]:
    """Each *player* this creature is offered against, with the action's label."""
    return {
        a.targets[0].id: a.label or ""
        for a in attack_actions(game, oid)
        if a.targets[0].kind == "player"
    }


def walker_attacks(game, oid: int) -> dict[int, str]:
    """Each *planeswalker* this creature is offered against, with the label."""
    return {
        a.targets[0].id: a.label or ""
        for a in attack_actions(game, oid)
        if a.targets[0].kind == "object"
    }


def untapped_forests(game, pid: int = 0) -> int:
    return sum(
        1
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == "forest"
        and game.state.objects[oid].controller == pid
        and not game.state.objects[oid].tapped
    )


class TestGhostlyPrison:
    """"Creatures can't attack you unless their controller pays {2} for each
    creature they control that's attacking you."

    The same sentence as Propaganda, on a white enchantment. The near misses a
    mis-written card would land on are each visible here: a `cant_attack`
    static locks the attack instead of pricing it, a `controller: "you"` filter
    taxes only the Prison's own creatures (which never attack its controller),
    and a tax charged against the seat rather than the player would reach the
    planeswalkers 506.2 leaves out.
    """

    def position(self, builder, *, lands: int, bears: int = 1, walker: bool = False):
        """Player 0 attacks; player 1 sits behind a Ghostly Prison."""
        b = (
            builder(players=2)
            .battlefield(0, [BEAR] * bears)
            .battlefield(0, ["forest"] * lands)
            .battlefield(1, [PRISON] + ([WALKER] if walker else []))
        )
        game = b.build()
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        return game

    def test_an_opponents_attack_is_priced_at_two(self, builder):
        """The filter is `controller: any`: the creatures taxed are the ones
        the Prison's controller does *not* control."""
        game = self.position(builder, lands=2)
        bear = only_oid(game, BEAR, 0)
        assert "pay {2}" in player_attacks(game, bear)[1]

    def test_paying_it_taps_the_mana_and_the_creature_attacks(self, builder):
        game = self.position(builder, lands=2)
        bear = only_oid(game, BEAR, 0)
        game.apply(next(a for a in attack_actions(game, bear) if a.targets[0].kind == "player"))
        assert untapped_forests(game) == 0
        assert game.state.combat.attackers[bear] == 1

    def test_it_is_a_price_not_a_wall(self, builder):
        """An unpayable tax withholds the attack (508.1g); a payable one does
        not. A Prison written as `cant_attack` fails the second half."""
        poor = self.position(builder, lands=1)
        assert player_attacks(poor, only_oid(poor, BEAR, 0)) == {}
        rich = self.position(builder, lands=2)
        assert 1 in player_attacks(rich, only_oid(rich, BEAR, 0))

    def test_it_is_two_for_each_attacking_creature(self, builder):
        """Four Forests fund two attackers and not a third."""
        game = self.position(builder, lands=4, bears=3)
        for _ in range(2):
            game.apply(next(a for a in attack_actions(game) if a.targets[0].kind == "player"))
        assert untapped_forests(game) == 0
        assert len(game.state.combat.attackers) == 2
        assert attack_actions(game) == []

    def test_attacking_its_controllers_planeswalker_is_free(self, builder):
        """The near miss. "Can't attack **you**" is about the player; attacking
        a planeswalker they control is a different thing being attacked (506.2),
        so the walker is offered with no price and even with no mana at all."""
        game = self.position(builder, lands=0, walker=True)
        bear = only_oid(game, BEAR, 0)
        walker = only_oid(game, WALKER, 1)
        assert player_attacks(game, bear) == {}, "no mana: the player is out of reach"
        assert walker in walker_attacks(game, bear)
        assert "pay" not in walker_attacks(game, bear)[walker]

    def test_the_tax_ends_when_the_prison_leaves(self, builder):
        """Read live off the battlefield, so there is nothing left to wear off."""
        game = self.position(builder, lands=0)
        bear = only_oid(game, BEAR, 0)
        assert player_attacks(game, bear) == {}
        zones.destroy(game.state, only_oid(game, PRISON, 1))
        offered = player_attacks(game, bear)
        assert 1 in offered
        assert "pay" not in offered[1]


EDGAR = "edgar_ancient_bloodlord"
#: "Destroy target creature or planeswalker." Not Hero's Downfall: the hand-written
#: one in `edgar.cards.json` targets creatures only and could not kill the walker.
REMOVAL = "fateful_absence"


class TestEdgarAncientBloodlord:
    """"Whenever another creature or planeswalker you control dies, you gain 1
    life." / "{2}, Sacrifice another creature or planeswalker: Put a +1/+1
    counter on Edgar. He gains menace until end of turn."

    Gate 5 casts Edgar into a board where nothing dies and never activates the
    ability, so both sentences reached the pool asserted only as "he is on the
    battlefield". The near misses are each a word of the printed text: "another"
    (his own death, and sacrificing himself), "you control" (an opponent's
    creature dying), "or planeswalker" (a walker counts on both lines), and
    "until end of turn" (the menace goes, the counter stays).
    """

    def position(self, builder, *, theirs: tuple[str, ...] = ()):
        game = (
            builder(players=2)
            .battlefield(0, [EDGAR, BEAR, WALKER, "plains", "plains"])
            .battlefield(0, ["plains"] * 2)
            .hand(0, [REMOVAL])
            .battlefield(1, list(theirs))
            .build()
        )
        return game, only_oid(game, EDGAR, 0)

    def kill(self, game, victim: int) -> None:
        """A real removal spell, so the death goes through the game loop that
        collects triggers -- `zones.destroy` called from a test does not, and the
        "gains nothing" cases below would pass whatever the card said."""
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == REMOVAL
                and (not a.targets or a.targets[0].id == victim)
            )
        )
        while (p := game.pending()) is not None and p.kind is DecisionKind.CHOOSE_OBJECTS:
            game.apply(next(a for a in game.legal_actions() if a.targets[0].id == victim))
        self.settle(game)
        assert victim not in game.state.battlefield

    def settle(self, game) -> None:
        pass_until(
            game,
            lambda g: (
                not g.state.stack
                and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY)
            ),
        )

    def life(self, game) -> int:
        return game.state.players[0].life

    def sacrifice_for(self, game, edgar: int, victim: int) -> None:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == edgar
            )
        )
        assert game.pending().kind is DecisionKind.CHOOSE_OBJECTS
        game.apply(next(a for a in game.legal_actions() if a.targets[0].id == victim))
        self.settle(game)

    def test_another_creature_dying_gains_one(self, builder):
        game, _ = self.position(builder)
        before = self.life(game)
        self.kill(game, only_oid(game, BEAR, 0))
        assert self.life(game) == before + 1

    def test_a_planeswalker_dying_gains_one_too(self, builder):
        """"Or planeswalker": a `creature_dies` trigger would miss this one."""
        game, _ = self.position(builder)
        before = self.life(game)
        self.kill(game, only_oid(game, WALKER, 0))
        assert self.life(game) == before + 1

    def test_edgar_s_own_death_gains_nothing(self, builder):
        game, edgar = self.position(builder)
        before = self.life(game)
        self.kill(game, edgar)
        assert self.life(game) == before

    def test_an_opponent_s_creature_dying_gains_nothing(self, builder):
        game, _ = self.position(builder, theirs=(BEAR,))
        before = self.life(game)
        self.kill(game, only_oid(game, BEAR, 1))
        assert self.life(game) == before

    def test_the_sacrifice_offers_creatures_and_walkers_but_not_edgar(self, builder):
        game, edgar = self.position(builder)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == edgar
            )
        )
        offered = {a.targets[0].id for a in game.legal_actions()}
        assert offered == {only_oid(game, BEAR, 0), only_oid(game, WALKER, 0)}

    def test_with_nothing_else_to_sacrifice_it_cannot_be_activated(self, builder):
        game = builder(players=2).battlefield(0, [EDGAR, "plains", "plains"]).build()
        edgar = only_oid(game, EDGAR, 0)
        assert not any(
            a.kind is ActionKind.ACTIVATE and a.source == edgar for a in game.legal_actions()
        )

    def test_sacrificing_grows_him_grants_menace_and_feeds_the_trigger(self, builder):
        """The two lines meet: the sacrifice is a death, so it also gains 1."""
        game, edgar = self.position(builder)
        before = self.life(game)
        self.sacrifice_for(game, edgar, only_oid(game, BEAR, 0))
        assert count_on_battlefield(game, BEAR, 0) == 0
        assert game.state.objects[edgar].counters.get("+1/+1") == 1
        c = chars(game.state, edgar)
        assert (c.power, c.toughness) == (3, 4)
        assert has_keyword(game.state, edgar, "menace")
        assert self.life(game) == before + 1

    def test_sacrificing_a_planeswalker_works_the_same(self, builder):
        game, edgar = self.position(builder)
        self.sacrifice_for(game, edgar, only_oid(game, WALKER, 0))
        assert count_on_battlefield(game, WALKER, 0) == 0
        assert game.state.objects[edgar].counters.get("+1/+1") == 1

    def test_the_menace_ends_with_the_turn_and_the_counter_stays(self, builder):
        game, edgar = self.position(builder)
        self.sacrifice_for(game, edgar, only_oid(game, BEAR, 0))
        pass_until(game, lambda g: g.state.active_player == 1)
        assert not has_keyword(game.state, edgar, "menace")
        assert game.state.objects[edgar].counters.get("+1/+1") == 1


CARMEN = "carmen_cruel_skymarcher"
SERRA = "serra_angel"  # {3}{W}{W}, mana value 5
RITE = "village_rites"  # an instant card in the graveyard: not a permanent card
ANCHOR = "t_plain_instant"  # a reason for priority to stop in each seat


class TestCarmenCruelSkymarcher:
    """"Whenever a player sacrifices a permanent, put a +1/+1 counter on Carmen and
    you gain 1 life." / "Whenever Carmen attacks, return up to one target
    permanent card with mana value less than or equal to Carmen's power from your
    graveyard to the battlefield."

    Neither line is reachable by gate 5: nothing is sacrificed in its sandbox and
    combat is declined. The near misses are each one word: **a player** (an
    opponent's sacrifice counts), **sacrifices** (a destroyed creature does not),
    **permanent card** (an instant does not come back), and **Carmen's power** --
    her current power, counters included, not the printed 2.
    """

    def board(self, builder, *, graveyard=(), active: int = 0, counters: int = 0):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 3 + [BEAR])
            .battlefield(0, [CARMEN], counters={"+1/+1": counters} if counters else None)
            .battlefield(1, ["plains", BEAR])
            .graveyard(0, list(graveyard))
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, ["plains"] * 20)
            .library(1, ["plains"] * 20)
            .active(active)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(3)
            .build()
        )
        return game, only_oid(game, CARMEN, 0)

    def settle(self, game, *, targets=(), limit: int = 300) -> list[set[int]]:
        """Empty the stack, choosing ``targets`` wherever objects are chosen.
        Returns the object ids each choice offered."""
        offered: list[set[int]] = []
        for _ in range(limit):
            decision = game.pending()
            if decision is None:
                return offered
            if decision.kind is DecisionKind.CHOOSE_OBJECTS:
                if not decision.selected:
                    offered.append(
                        {o.ref.id for o in decision.options if getattr(o.ref, "kind", "") == "object"}
                    )
                choice = next(
                    (
                        a
                        for a in game.legal_actions()
                        if a.kind is ActionKind.CHOOSE
                        and a.targets
                        and a.targets[0].id in set(targets)
                        and a.targets[0].id not in set(decision.selected or ())
                    ),
                    None,
                )
                if choice is None and not targets:
                    # "Up to one": a trigger's target combinations include the
                    # empty one, offered as its own choice rather than a finish.
                    choice = next(
                        (
                            a
                            for a in game.legal_actions()
                            if a.kind is ActionKind.CHOOSE and not a.targets
                        ),
                        None,
                    )
                game.apply(choice or find_action(game, ActionKind.FINISH_DECLARATION))
                continue
            if (
                decision.kind is DecisionKind.PRIORITY
                and not game.state.stack
                and not game.state.pending_triggers
            ):
                return offered
            game.apply(_default_answer(game, decision))
        raise AssertionError("the stack did not empty")

    def life(self, game) -> int:
        return game.state.players[0].life

    def test_your_sacrifice_grows_her_and_gains_one(self, builder):
        game, carmen = self.board(builder)
        zones.sacrifice(game.state, only_oid(game, BEAR, 0))
        self.settle(game)
        assert game.state.objects[carmen].counters.get("+1/+1") == 1
        assert self.life(game) == 41

    def test_an_opponents_sacrifice_counts_too(self, builder):
        """"Whenever **a player** sacrifices" -- not "you"."""
        game, carmen = self.board(builder)
        zones.sacrifice(game.state, only_oid(game, BEAR, 1))
        self.settle(game)
        assert game.state.objects[carmen].counters.get("+1/+1") == 1
        assert self.life(game) == 41
        assert game.state.players[1].life == 40, "**you** gain 1 life, not the sacrificer"

    def test_a_land_is_a_permanent(self, builder):
        game, carmen = self.board(builder)
        zones.sacrifice(game.state, only_oid(game, "plains", 1))
        self.settle(game)
        assert game.state.objects[carmen].counters.get("+1/+1") == 1

    def test_a_destroyed_creature_is_not_a_sacrifice(self, builder):
        game, carmen = self.board(builder)
        zones.destroy(game.state, only_oid(game, BEAR, 1))
        self.settle(game)
        assert game.state.objects[carmen].counters.get("+1/+1") is None
        assert self.life(game) == 40

    def test_each_sacrifice_is_its_own_trigger(self, builder):
        game, carmen = self.board(builder)
        zones.sacrifice(game.state, only_oid(game, BEAR, 0))
        zones.sacrifice(game.state, only_oid(game, BEAR, 1))
        self.settle(game)
        assert game.state.objects[carmen].counters.get("+1/+1") == 2
        assert self.life(game) == 42

    def attack(self, game, carmen: int) -> None:
        pass_until(
            game,
            lambda g: g.pending() is not None
            and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == carmen
                and a.targets[0].kind == "player"
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))

    def test_attacking_returns_a_card_her_power_reaches(self, builder):
        game, carmen = self.board(builder, graveyard=[BEAR, SERRA, RITE])
        bear, serra, rite = list(game.state.players[0].graveyard)
        self.attack(game, carmen)
        offered = self.settle(game, targets=[bear])
        assert offered and offered[0] == {bear}, "power 2: the 2-drop, not the 5 or the instant"
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[serra].zone is Zone.GRAVEYARD
        assert game.state.objects[rite].zone is Zone.GRAVEYARD

    def test_her_power_is_her_current_power(self, builder):
        """Three counters make her a 5/5, and Serra Angel's 5 is now in reach."""
        game, carmen = self.board(builder, graveyard=[BEAR, SERRA, RITE], counters=3)
        bear, serra, rite = list(game.state.players[0].graveyard)
        self.attack(game, carmen)
        offered = self.settle(game, targets=[serra])
        assert offered and offered[0] == {bear, serra}
        assert game.state.objects[serra].zone is Zone.BATTLEFIELD
        assert game.state.objects[rite].zone is Zone.GRAVEYARD

    def test_up_to_one_may_return_nothing(self, builder):
        game, carmen = self.board(builder, graveyard=[BEAR])
        [bear] = list(game.state.players[0].graveyard)
        self.attack(game, carmen)
        self.settle(game, targets=[])
        assert game.state.objects[bear].zone is Zone.GRAVEYARD
