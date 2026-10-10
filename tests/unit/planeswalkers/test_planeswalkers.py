"""Planeswalkers: loyalty, loyalty abilities, and being attacked.

    Sorin, Imperious Bloodlord.

`CardType.PLANESWALKER` existed and did nothing: a planeswalker entered play as
an inert permanent with no loyalty and no way to use its abilities. Four of the
pieces were already there and cost nothing to reuse, which is most of why this
is small:

| already there | what it becomes |
|---|---|
| counters are free-form strings | `"loyalty"` is a counter like any other |
| `self_enters_with_counters` | starting loyalty, with nothing new at ETB |
| `sorcery_speed_only` | half of 606.3's timing |
| defenders are a *slot map*, not a player list | room for a third kind of defender |

What had to be built:

**Loyalty is counters (306.5b).** So starting loyalty compiles into an
enters-with-counters replacement rather than into a new field the engine reads,
and proliferate, `counters_on` and the client's badge all read it for free.

**A loyalty cost is signed, and it is a cost.** Not `remove_counters`, which can
only ever take them off — a plus ability *adds*. And being a cost is what makes
it paid as the ability goes on the stack, unrefunded if the ability is
countered, which is why loyalty is spendable in response to removal.

**606.3 is a limit on the permanent, not on the ability.** Sorin has three
loyalty abilities and may use one per turn. `once_each_turn` counts a single
ability, so it would let him plus twice and then minus — three cards' worth of a
card. And the sorcery-speed half is applied by the *loader*, not left to an
author to remember: one omitted flag and the planeswalker ticks up at instant
speed on somebody else's turn.

**Zero loyalty is not destruction** (704.5i), so it goes through `move_object`
and indestructible does not save it — the same shape as zero toughness.

**Damage removes loyalty** (306.8), read in `damage_permanent` beside wither.
Marking `obj.damage` instead would be invisible: nothing compares a
planeswalker's damage to anything, so it would take damage for ever and never
die.

**Attacking one keeps `attackers[oid]` meaning "the defending player."** A
planeswalker's controller *is* that player (506.2), so the fifteen existing
reads stay true and only declaration, damage assignment and serialization learn
the difference — carried by a parallel `attacking_permanent` map rather than
by widening the value to a union.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.primitives import damage_permanent
from tests.conftest import only_oid, pass_until

WALKER = "t_walker"  # loyalty 4; "+1: gain 2 life" and "-3: draw a card"
BEAR = "t_bear"


def board(builder, *, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 5 + [WALKER, *mine])
        .battlefield(1, list(theirs))
        .hand(0, [])
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def walker_actions(game, oid: int) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == oid
    ]


class TestItArrivesWithLoyalty:
    def test_the_counters_are_there(self, builder):
        game = board(builder)
        walker = only_oid(game, WALKER, 0)
        assert game.state.objects[walker].counter("loyalty") == 4

    def test_it_is_a_planeswalker_on_the_board(self, builder):
        game = board(builder)
        walker = only_oid(game, WALKER, 0)
        assert "Planeswalker" in chars(game.state, walker).types


class TestLoyaltyAbilities:
    def test_both_are_offered(self, builder):
        game = board(builder)
        walker = only_oid(game, WALKER, 0)
        assert len(walker_actions(game, walker)) == 2

    def test_a_plus_adds_loyalty(self, builder):
        game = board(builder)
        walker = only_oid(game, WALKER, 0)
        game.apply(walker_actions(game, walker)[0])
        assert game.state.objects[walker].counter("loyalty") == 5

    def test_a_minus_spends_it(self, builder):
        game = board(builder)
        walker = only_oid(game, WALKER, 0)
        minus = next(a for a in walker_actions(game, walker) if "-3" in (a.label or ""))
        game.apply(minus)
        assert game.state.objects[walker].counter("loyalty") == 1

    def test_only_one_a_turn(self, builder):
        """606.3, and the point of asking the *permanent* rather than the
        ability: two pluses in a turn is three cards' worth of a card."""
        game = board(builder)
        walker = only_oid(game, WALKER, 0)
        game.apply(walker_actions(game, walker)[0])
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert not walker_actions(game, walker)

    def test_a_minus_it_cannot_afford_is_not_offered(self, builder):
        game = board(builder)
        walker = only_oid(game, WALKER, 0)
        game.state.objects[walker].counters["loyalty"] = 2
        assert not [a for a in walker_actions(game, walker) if "-3" in (a.label or "")]
        assert [a for a in walker_actions(game, walker) if "+1" in (a.label or "")]

    def test_it_is_sorcery_speed_without_the_flag(self, builder, registry):
        """Applied by the loader: 606.3's timing is the rule speaking, not the
        card, and the fixture never writes `sorcery_speed_only`."""
        assert all(a.sorcery_speed_only for a in registry.get(WALKER).abilities)


class TestZeroLoyalty:
    def test_it_goes_to_the_graveyard(self, builder):
        game = board(builder)
        walker = only_oid(game, WALKER, 0)
        game.state.objects[walker].counters["loyalty"] = 0
        pass_until(game, lambda g: g.state.objects[walker].zone is not Zone.BATTLEFIELD)
        assert game.state.objects[walker].zone is Zone.GRAVEYARD

    def test_damage_takes_loyalty_off(self, builder):
        """306.8. Marking `obj.damage` instead would be invisible: nothing
        compares a planeswalker's damage to anything."""
        game = board(builder)
        walker = only_oid(game, WALKER, 0)
        damage_permanent(game.state, walker, 3, None)
        assert game.state.objects[walker].counter("loyalty") == 1
        assert game.state.objects[walker].damage == 0

    def test_lethal_damage_kills_it(self, builder):
        game = board(builder)
        walker = only_oid(game, WALKER, 0)
        damage_permanent(game.state, walker, 4, None)
        pass_until(game, lambda g: g.state.objects[walker].zone is not Zone.BATTLEFIELD)
        assert game.state.objects[walker].zone is Zone.GRAVEYARD


class TestAttackingOne:
    def combat_board(self, builder):
        """The opponent's planeswalker, and a creature of mine to swing with."""
        game = (
            builder(players=2)
            .battlefield(0, ["swamp"] * 5 + [BEAR])
            .battlefield(1, [WALKER])
            .hand(0, [])
            .library(0, ["swamp"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        return game, only_oid(game, BEAR, 0), only_oid(game, WALKER, 1)

    def attacks(self, game, attacker: int) -> list:
        return [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER and a.source == attacker
        ]

    def test_it_is_offered_as_a_thing_to_attack(self, builder):
        game, bear, walker = self.combat_board(builder)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)

        targets = {ref.id for a in self.attacks(game, bear) for ref in a.targets}
        assert walker in targets, "only the player was offered"

    def test_the_player_is_still_offered_too(self, builder):
        game, bear, _ = self.combat_board(builder)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)

        kinds = {ref.kind for a in self.attacks(game, bear) for ref in a.targets}
        assert kinds == {"player", "object"}

    def swing_at_the_walker(self, game, bear: int, walker: int) -> None:
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
        game.apply(
            next(
                a
                for a in self.attacks(game, bear)
                if any(ref.id == walker and ref.kind == "object" for ref in a.targets)
            )
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.FINISH_DECLARATION
            )
        )

    def test_the_damage_lands_on_the_planeswalker(self, builder):
        game, bear, walker = self.combat_board(builder)
        life = game.state.players[1].life
        self.swing_at_the_walker(game, bear, walker)
        pass_until(game, lambda g: g.state.step is Step.END_OF_COMBAT)

        assert game.state.objects[walker].counter("loyalty") == 2
        assert game.state.players[1].life == life, "the controller took none of it"

    def test_the_defending_player_is_still_its_controller(self, builder):
        """506.2, and the whole reason `attackers[oid]` did not have to change:
        every existing read of it stays true."""
        game, bear, walker = self.combat_board(builder)
        self.swing_at_the_walker(game, bear, walker)
        assert game.state.combat.attackers[bear] == 1
        assert game.state.combat.attacking_permanent[bear] == walker


class TestTheActionSpaceCanSayIt:
    """The RL encoder is the one consumer that cannot simply be handed a new
    kind of target: its indices are flat and fixed, so a planeswalker needs a
    *slot*. `DEF_CAP` rose from 3 to 8 for this, which moved the action-space
    size and therefore invalidated every checkpoint trained before it."""

    def test_attacking_a_planeswalker_has_an_index(self, builder):
        from commanderblitz.ai import action_space

        game = (
            builder(players=2)
            .battlefield(0, ["swamp"] * 5 + [BEAR])
            .battlefield(1, [WALKER])
            .hand(0, [])
            .library(0, ["swamp"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        walker = only_oid(game, WALKER, 1)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)

        table = action_space.build(game.state)
        swings = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER
            and any(ref.id == walker and ref.kind == "object" for ref in a.targets)
        ]
        assert swings, "legality never offered the attack"
        assert not [a for a in table.dropped if a in swings], (
            "the encoder dropped it -- no slot"
        )
        assert all(table.encode(a) is not None for a in swings)

    def test_a_player_and_a_planeswalker_do_not_share_a_slot(self, builder):
        """A player id and an object id are both ints, and 1 is a legal value of
        each -- so the slot map is keyed by a tagged id rather than a bare one."""
        from commanderblitz.ai.action_space import _Slots

        game = (
            builder(players=2)
            .battlefield(0, ["swamp"] * 5 + [BEAR])
            .battlefield(1, [WALKER])
            .hand(0, [])
            .library(0, ["swamp"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        slots = _Slots(game.state, 0, None)
        assert len(set(slots.defenders.values())) == len(slots.defenders)
        assert len(slots.defenders) == 2  # one opponent, one planeswalker
