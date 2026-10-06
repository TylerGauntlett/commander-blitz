"""The Myrel deck's gear, card by card: Skullclamp, Lightning Greaves and the
other utility pieces that are neither a land nor a mana rock.

Split from `test_myrel_shield_of_argive_mana.py` -- the mana base and the rocks --
which says why these files exist and holds the helpers this file shares.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars, prevents_all_damage
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.targeting import can_be_targeted
from tests.cards.test_myrel_shield_of_argive_mana import (
    ANCHOR,
    BEAR,
    DRAW_TWO,
    PLAINS,
    SOLDIER,
    WALL,
    WHITE_TWO,
    acts,
    attack_with,
    cast,
    castable,
    keywords_of,
    library,
    resolve,
    scries,
    to_declaration,
    tokens,
)
from tests.conftest import only_oid, pass_until

# ----------------------------------------------------------------------
# the gear
# ----------------------------------------------------------------------


class TestSkullclamp:
    """ "Equipped creature gets +1/-1." / "Whenever equipped creature dies, draw
    two cards." / "Equip {1}"

    The expectation is `{"battlefield_count": 33, "hand_size": {"0": 1}, "zone":
    "battlefield"}`. Equip is an activated ability, so the gate never attached
    the Clamp to anything and neither the buff, the drawback nor the draw was
    ever observed.
    """

    def board(self, builder, creature: str, *, plains: int = 3):
        game = (
            builder(players=2)
            .battlefield(0, ["skullclamp", creature, *[PLAINS] * plains])
            .hand(0, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "skullclamp", 0), only_oid(game, creature, 0)

    def equip(self, game, clamp: int, target: int) -> int:
        before = library(game)
        game.apply(next(a for a in acts(game, clamp) if a.targets and a.targets[0].id == target))
        resolve(game)
        return before - library(game)

    def test_it_gives_plus_one_minus_one(self, builder):
        """Read on a 2/2, where both halves show and nothing dies."""
        game, clamp, bear = self.board(builder, BEAR)
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (2, 2)
        drawn = self.equip(game, clamp, bear)

        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (3, 1)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert drawn == 0, "nothing died, so nothing was drawn"

    def test_a_one_toughness_creature_dies_and_draws_two(self, builder):
        """The card, and the reason it is banned in Commander's smaller cousins.
        Recruitment Officer is a 2/1 Soldier out of this very deck: the `-1`
        kills it and the trigger pays for it twice over.

        A Clamp written `+1/+0`, or one whose trigger drew **one**, leaves a
        board that looks identical the moment anything else kills the creature.
        """
        game, clamp, officer = self.board(builder, SOLDIER)
        assert chars(game.state, officer).toughness == 1, "the premise"
        drawn = self.equip(game, clamp, officer)

        assert game.state.objects[officer].zone is Zone.GRAVEYARD
        assert drawn == 2

    def test_equip_is_sorcery_speed_only(self, builder):
        """702.6b. Offered on your own main phase and nowhere else -- so the
        Clamp cannot be moved onto a creature mid-combat in response to
        anything."""
        game = (
            builder(players=2)
            .battlefield(0, ["skullclamp", BEAR, *[PLAINS] * 3])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        clamp = only_oid(game, "skullclamp", 0)
        assert acts(game, clamp), "your own main phase"
        pass_until(
            game,
            lambda g: (
                g.state.active_player == 1 and g.pending() is not None and g.pending().player == 0
            ),
        )
        assert acts(game, clamp) == [], "the opponent's turn"


class TestLightningGreaves:
    """ "Equipped creature has haste and shroud." / "Equip {0}"

    The expectation is `{"zone": "battlefield"}`, and both printed clauses are
    behind an Equip the gate never activates. Shroud is the half that is easy to
    lose: it is the card's **drawback**, and a Greaves that granted only haste --
    or that granted hexproof, which stops opponents and not you -- is a strictly
    better card that nothing on the board would look wrong about.
    """

    def board(self, builder, *, lands: int = 2, second_attacker: bool = False):
        b = builder(players=2).battlefield(
            0, ["lightning_greaves", *[PLAINS] * lands] + ([SOLDIER] if second_attacker else [])
        )
        game = (
            b.battlefield(0, [BEAR], sick=True)
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "lightning_greaves", 0), only_oid(game, BEAR, 0)

    def test_equip_costs_nothing(self, builder):
        """ "Equip **{0}**", which is why the Greaves go on the commander the turn
        it lands. Offered on a board with no untapped mana at all."""
        game, greaves, bear = self.board(builder, lands=0)
        assert [t.id for a in acts(game, greaves) for t in a.targets] == [bear]

    def test_it_grants_haste_and_shroud(self, builder):
        game, greaves, bear = self.board(builder)
        assert keywords_of(game, bear) == set(), "a vanilla 2/2 before the Greaves"
        game.apply(next(a for a in acts(game, greaves) if a.targets[0].id == bear))
        resolve(game)

        assert keywords_of(game, bear) == {"haste", "shroud"}

    def test_a_summoning_sick_creature_attacks_that_turn(self, builder):
        """The assertion every wrong haste implementation fails silently: on the
        battlefield, this turn, in the declaration."""
        game, greaves, bear = self.board(builder, second_attacker=True)
        game.apply(next(a for a in acts(game, greaves) if a.targets[0].id == bear))
        resolve(game)
        to_declaration(game, DecisionKind.DECLARE_ATTACKERS)

        assert any(
            a.kind is ActionKind.ADD_ATTACKER and a.source == bear for a in game.legal_actions()
        )

    def test_and_without_the_greaves_it_cannot(self, builder):
        """The control, on the same turn. Recruitment Officer is the second
        attacker and is load bearing: without a creature that *can* attack there
        is no declaration this turn at all, and the engine walks two turns
        forward to find one -- by which time the sickness has gone and both
        halves of this pair look alike."""
        game, _greaves, bear = self.board(builder, second_attacker=True)
        to_declaration(game, DecisionKind.DECLARE_ATTACKERS)

        assert not any(
            a.kind is ActionKind.ADD_ATTACKER and a.source == bear for a in game.legal_actions()
        )

    def test_the_shroud_stops_your_own_spells_too(self, builder):
        """702.18a, and the difference from hexproof. `can_be_targeted` asked as
        **player 0**, who controls the creature."""
        game, greaves, bear = self.board(builder)
        assert can_be_targeted(game.state, 0, bear), "before"
        game.apply(next(a for a in acts(game, greaves) if a.targets[0].id == bear))
        resolve(game)

        assert not can_be_targeted(game.state, 0, bear)

    def test_no_other_equipment_can_be_moved_onto_it(self, builder):
        """The drawback, played out of this deck's own two Equipment. Equip
        targets, so once the Greaves are on, Skullclamp has no legal target --
        which is a real cost in a deck that wants the Clamp on the same body."""
        game = (
            builder(players=2)
            .battlefield(0, ["lightning_greaves", "skullclamp", BEAR, *[PLAINS] * 3])
            .hand(0, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        greaves = only_oid(game, "lightning_greaves", 0)
        clamp = only_oid(game, "skullclamp", 0)
        bear = only_oid(game, BEAR, 0)
        assert acts(game, clamp), "the Clamp could be equipped before"

        game.apply(next(a for a in acts(game, greaves) if a.targets[0].id == bear))
        resolve(game)

        assert acts(game, clamp) == []


class TestSentinelTotem:
    """ "When this artifact enters, scry 1." / "{T}, Exile this artifact: Exile all
    graveyards."

    Gate 5 recorded `{"library_size": {"0": 40}, ...}` for the scry -- which is
    correct and says nothing, since a scry that bottoms nothing moves no cards.
    The ability is the card and was never activated.
    """

    def test_it_scries_one_on_entering(self, builder):
        """Read off the event, because the board cannot show it: a scry that
        keeps the card on top is indistinguishable from no scry at all."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS])
            .hand(0, ["sentinel_totem"])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        mark = len(game.state.events)
        cast(game, "sentinel_totem")

        assert [e["looked"] for e in scries(game, mark)] == [1], "scry 1, not scry 2"

    def board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["sentinel_totem", PLAINS])
            .graveyard(0, [PLAINS, BEAR])
            .graveyard(1, [PLAINS])
            .hand(0, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "sentinel_totem", 0)

    def test_it_exiles_every_graveyard_including_your_own(self, builder):
        """ "**all** graveyards". The near miss is "each opponent's", which in a
        deck running Rest in Peace and Approach of the Second Sun is a different
        and much better card -- and on a board where only the opponent has a
        graveyard the two readings are the same."""
        game, totem = self.board(builder)
        game.apply(acts(game, totem, 1)[0])
        resolve(game)

        assert game.state.players[0].graveyard == []
        assert game.state.players[1].graveyard == []

    def test_it_exiles_itself_rather_than_dying(self, builder):
        """ "**Exile** this artifact" is the cost, not a sacrifice: the Totem does
        not end up in the graveyard it just emptied, and nothing that watches for
        an artifact dying sees anything."""
        game, totem = self.board(builder)
        game.apply(acts(game, totem, 1)[0])
        resolve(game)

        assert game.state.objects[totem].zone is Zone.EXILE


class TestPeterParkersCamera:
    """ "This artifact enters with three film counters on it." / "{2}, {T}, Remove a
    film counter from this artifact: Copy target activated or triggered ability
    you control. You may choose new targets for the copy."

    The entry counters are the one thing gate 5 did pin
    (`{"counters": {"amount": 3, "kind": "film"}}`), so they are not re-asserted.
    Everything past them needs an ability already on the stack, which the gate
    never puts there. `tests/unit/copies/test_copy_ability.py` pins the capability on a
    test-only card called `t_camera`.
    """

    def board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["peter_parker_s_camera"], counters={"film": 3})
            .battlefield(0, ["castle_ardenvale", *[PLAINS] * 6])
            .hand(0, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return (
            game,
            only_oid(game, "peter_parker_s_camera", 0),
            only_oid(game, "castle_ardenvale", 0),
        )

    def test_it_is_not_offered_with_an_empty_stack(self, builder):
        """ "Copy **target** activated or triggered ability": with nothing on the
        stack there is no legal target, so the film counters cannot be burned for
        nothing."""
        game, camera, _castle = self.board(builder)
        assert acts(game, camera) == []

    def copied(self, builder):
        game, camera, castle = self.board(builder)
        game.apply(acts(game, castle, 1)[0])
        assert game.state.stack, "the Castle's ability is waiting to resolve"
        game.apply(acts(game, camera, 0)[0])
        resolve(game)
        return game, camera

    def test_it_copies_an_activated_ability_and_both_resolve(self, builder):
        """The Castle's token ability, copied: two 1/1 Humans off one {2}{W}{W}.
        A copy that replaced the original, or one that never resolved, leaves one
        token and looks like a card that did nothing."""
        game, _camera = self.copied(builder)
        assert len(tokens(game)) == 2

    def test_a_film_counter_is_spent(self, builder):
        """ "**Remove a film counter**" is part of the cost, and it is what makes
        the Camera a three-shot rather than an engine."""
        game, camera = self.copied(builder)
        assert game.state.objects[camera].counters.get("film") == 2


class TestGleamingSplendor:
    """ "Whenever an opponent draws their second card each turn, you create a
    Treasure token." / "{2}{W}: Two target players each draw a card."

    Gate 5's expectation is `{"battlefield_count": 33, "hand_size": {"0": 1},
    "zone": "battlefield"}`: nothing in its sandbox draws a second card after the
    card under test, and it never activates the ability.
    """

    def their_turn(self, builder, spell: str):
        return (
            builder(players=2)
            .battlefield(0, ["gleaming_splendor", PLAINS])
            .battlefield(1, ["island"] * 3)
            .hand(0, [ANCHOR])
            .hand(1, [spell])
            .library(0, [PLAINS] * 20)
            .library(1, ["island"] * 20)
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_an_opponents_second_draw_makes_a_treasure(self, builder):
        game = self.their_turn(builder, DRAW_TWO)
        cast(game, DRAW_TWO, pid=1)

        assert len(tokens(game, 0)) == 1
        assert tokens(game, 0)[0].def_id == "treasure_token"

    def test_the_treasure_is_yours_and_not_theirs(self, builder):
        """ "**you** create". The Splendor is a group-hug enchantment whose whole
        payoff is which side of the table the Treasure lands on."""
        game = self.their_turn(builder, DRAW_TWO)
        cast(game, DRAW_TWO, pid=1)

        assert tokens(game, 1) == []

    def test_two_draws_make_one_treasure_and_not_two(self, builder):
        """ "their **second** card", and only it. Divination draws two, so a
        trigger written on every draw makes two Treasures off this one spell."""
        game = self.their_turn(builder, DRAW_TWO)
        cast(game, DRAW_TWO, pid=1)

        assert len(tokens(game, 0)) == 1

    def from_their_upkeep(self, builder):
        """Seat 1's whole turn, from before the draw step.

        The draw-step draw is their **first** card, which is the half a trigger
        on "an opponent draws" gets wrong every single turn of the game.
        """
        return (
            builder(players=2)
            .battlefield(0, ["gleaming_splendor", PLAINS])
            .battlefield(1, ["island"] * 3)
            .hand(0, [ANCHOR])
            .hand(1, [DRAW_TWO])
            .library(0, [PLAINS] * 20)
            .library(1, ["island"] * 20)
            .active(1)
            .step(Step.UNTAP)
            .build()
        )

    def test_their_draw_step_draw_makes_none(self, builder):
        game = self.from_their_upkeep(builder)
        pass_until(
            game,
            lambda g: g.state.step is Step.PRECOMBAT_MAIN and g.state.active_player == 1,
        )
        assert library(game, 1) == 19, "the premise: they drew exactly one card"
        assert tokens(game, 0) == []

    def test_and_the_next_card_after_it_does(self, builder):
        """The boundary read across a step. One card drawn in the draw step, two
        more off Divination, and exactly one of the three is a second card."""
        game = self.from_their_upkeep(builder)
        pass_until(
            game,
            lambda g: g.state.step is Step.PRECOMBAT_MAIN and g.state.active_player == 1,
        )
        cast(game, DRAW_TWO, pid=1)

        assert library(game, 1) == 17, "three cards drawn this turn"
        assert len(tokens(game, 0)) == 1

    def test_your_own_draws_make_none(self, builder):
        """ "…an **opponent** draws"."""
        game = (
            builder(players=2)
            .battlefield(0, ["gleaming_splendor", *["island"] * 3])
            .battlefield(1, [PLAINS])
            .hand(0, [DRAW_TWO])
            .hand(1, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast(game, DRAW_TWO)

        assert tokens(game, 0) == []

    def test_the_activated_ability_draws_for_two_players(self, builder):
        """ "**Two** target players each draw a card" -- one card each, two seats,
        and one of them is you. A single-target version is a different card and
        would read as the same draw."""
        game = (
            builder(players=2)
            .battlefield(0, ["gleaming_splendor", *[PLAINS] * 4])
            .hand(0, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .library(1, ["island"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        splendor = only_oid(game, "gleaming_splendor", 0)
        [action] = acts(game, splendor, 1)
        assert sorted(t.id for t in action.targets) == [0, 1], "both seats, in one activation"
        before = [library(game, 0), library(game, 1)]

        game.apply(action)
        resolve(game)

        assert [before[0] - library(game, 0), before[1] - library(game, 1)] == [1, 1]


class TestRescueRetriever:
    """ "Flash" / "When this creature enters, put a +1/+1 counter on each other
    Soldier you control." / "Prevent all damage that would be dealt to other
    attacking Soldiers you control."

    Gate 5's expectation is `{"battlefield_count": 33, "hand_size": {"0": 1},
    "zone": "battlefield"}` -- no counters recorded, because its sandbox has no
    other Soldier for them to go on, and no combat for the prevention to reach.
    `tests/unit/damage/test_prevent_all_damage.py` pins the capability on a test-only
    card called `t_retriever`; this is the shipped card, in a declared combat.
    """

    def test_it_has_flash(self, builder):
        """A {3}{W}{W} creature this deck holds up, so the timing is the card."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 5)
            .battlefield(1, [PLAINS])
            .hand(0, ["rescue_retriever"])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        pass_until(
            game,
            lambda g: (
                g.state.active_player == 1 and g.pending() is not None and g.pending().player == 0
            ),
        )
        assert "rescue_retriever" in castable(game)

    def test_the_counters_go_on_other_soldiers_you_control(self, builder):
        """One board, four answers, and each is a clause of the sentence.

        Recruitment Officer is a Soldier of mine and gets one; the Bear is mine
        and is not a Soldier; Ballyrush Banneret is a Soldier and is not mine;
        and the Retriever is a Soldier of mine that the word "other" excludes.
        """
        game = (
            builder(players=2)
            .battlefield(0, [SOLDIER, BEAR, *[PLAINS] * 5])
            .battlefield(1, [WHITE_TWO])
            .hand(0, ["rescue_retriever"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        officer, bear = only_oid(game, SOLDIER, 0), only_oid(game, BEAR, 0)
        theirs = only_oid(game, WHITE_TWO, 1)
        dog = cast(game, "rescue_retriever")

        assert game.state.objects[officer].counters.get("+1/+1") == 1
        assert not game.state.objects[bear].counters.get("+1/+1"), "a Bear is not a Soldier"
        assert not game.state.objects[theirs].counters.get("+1/+1"), "not yours"
        assert not game.state.objects[dog].counters.get("+1/+1"), "'each OTHER Soldier'"

    def combat(self, builder, *, retriever: bool):
        """Attack with the Officer into a 2/2, with or without the Retriever.

        Recruitment Officer is a 2/1: one point of combat damage kills it, so the
        shield is the only thing between it and the graveyard.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["rescue_retriever" if retriever else WALL, SOLDIER])
            .battlefield(1, [BEAR, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        officer, bear = only_oid(game, SOLDIER, 0), only_oid(game, BEAR, 1)
        attackers = [officer]
        if retriever:
            attackers.append(only_oid(game, "rescue_retriever", 0))
        to_declaration(game, DecisionKind.DECLARE_ATTACKERS)
        attack_with(game, *attackers)
        to_declaration(game, DecisionKind.DECLARE_BLOCKERS)
        return game, officer, bear

    def test_a_blocked_soldier_takes_no_damage(self, builder):
        game, officer, bear = self.combat(builder, retriever=True)
        assert prevents_all_damage(game.state, officer) is True
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_BLOCKER
                and a.source == bear
                and a.targets[0].id == officer
            )
        )
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)

        assert game.state.objects[officer].damage == 0
        assert game.state.objects[officer].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].zone is Zone.GRAVEYARD, "and it still dealt its own 2"

    def test_and_without_the_retriever_the_same_soldier_dies(self, builder):
        """The control, so the row above is about the static and not about the
        arithmetic of a 2/1 against a 2/2."""
        game, officer, bear = self.combat(builder, retriever=False)
        assert prevents_all_damage(game.state, officer) is False
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_BLOCKER
                and a.source == bear
                and a.targets[0].id == officer
            )
        )
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)

        assert game.state.objects[officer].zone is Zone.GRAVEYARD

    def test_it_does_not_shield_itself(self, builder):
        """ "…**other** attacking Soldiers". The Retriever is an attacking Soldier
        its controller controls, so without the clause it is immune to everything
        while attacking -- and on a board where every Soldier is attacking, the
        narrowed and unnarrowed readings agree about all of them but this one."""
        game, _officer, _bear = self.combat(builder, retriever=True)
        dog = only_oid(game, "rescue_retriever", 0)
        assert prevents_all_damage(game.state, dog) is False
