""""If a creature dealt damage this way would die this turn, exile it instead."

    Gallifrey Falls // No More, and the whole exile-wrath family.

`ReplacementModel` is a three-value `Literal` and every one of its values is
about a permanent *entering* the battlefield. This is the moment one leaves, and
there was no spelling for it.

The engine did have a death-replacement site — `zones.destroy` — and it was
hard-coded to exactly three mechanisms (indestructible, a regeneration shield,
totem armor), none of them reachable from a card's own text.

**But `destroy` is the wrong site anyway.** The printed word is *die*, which is
broader than "be destroyed": a creature sacrificed has died, and so has one
whose toughness went to zero, and neither goes near `destroy`. So the redirect
lives on `move_object`, the single funnel every one of them shares.

**The set is snapshotted as the spell resolves.** "A creature dealt damage this
way" is decided then; a creature that arrives later was dealt no damage by it.
Evaluated lazily at death time this would catch the whole board for the rest of
the turn, which is a different and much stronger card. That is why the mark is
per object rather than a global replacement registered on the state.

---

One pre-existing bug came out with it. `sba._creature_deaths` called
`move_object` directly for lethal damage, so **no** death replacement fired
there — `destroy`'s own docstring claimed the lethal-damage state-based action
routed through it, and it did not. A regenerating creature that took lethal
damage died with its shield unspent. Lethal damage destroys (704.5g), so that
branch now goes through `destroy` like every other.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.structs import TempEffect
from commanderblitz.engine.zones import destroy, move_object, sacrifice
from tests.conftest import only_oid, pass_until

WRATH = "t_exile_wrath"  # 4 damage to each creature; they exile instead of dying
BEAR = "t_bear"  # 2/2
TRAMPLER = "t_trampler"
HOLD = "t_phase_out"  # an instant the opponent can always cast, so the turn stops


def board(builder, creatures=None):
    """The opponent holds an instant they can pay for, deliberately.

    Without it nobody has a legal action after the wrath resolves, auto-pass
    runs the rest of the turn inside the same `apply`, and the cleanup step
    wipes both the damage and the redirect before any assertion can see them.
    """
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * 5)
        .battlefield(1, list(creatures if creatures is not None else [BEAR, BEAR]))
        .battlefield(1, ["island"] * 3)
        .hand(0, [WRATH])
        .hand(1, [HOLD])
        .library(0, ["mountain"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def cast_the_wrath(game) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == WRATH
        )
    )
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def zone_of(game, card_id: str, pid: int = 1) -> list[Zone]:
    return [
        o.zone
        for o in game.state.objects.values()
        if o.def_id == card_id and o.owner == pid
    ]


class TestTheyGoToExile:
    def test_the_creatures_it_killed_are_exiled(self, builder):
        game = board(builder)
        cast_the_wrath(game)
        assert zone_of(game, BEAR) == [Zone.EXILE, Zone.EXILE]

    def test_and_not_to_the_graveyard(self, builder):
        game = board(builder)
        cast_the_wrath(game)
        assert not [
            oid
            for oid in game.state.players[1].graveyard
            if game.state.objects[oid].def_id == BEAR
        ]


class TestWhatItDoesNotCatch:
    def test_a_creature_that_arrived_later_dies_normally(self, builder):
        """The set is fixed as the spell resolves, so a creature that was not
        there was dealt no damage by it. Read lazily at death time instead, this
        would bury the whole board in exile for the rest of the turn."""
        game = (
            builder(players=2)
            .battlefield(0, ["mountain"] * 5)
            .battlefield(1, [BEAR])
            .hand(0, [WRATH])
            .hand(1, [TRAMPLER])
            .library(0, ["mountain"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        cast_the_wrath(game)

        latecomer = next(
            oid
            for oid in game.state.players[1].hand
            if game.state.objects[oid].def_id == TRAMPLER
        )
        move_object(game.state, latecomer, Zone.BATTLEFIELD, to_player=1)
        game.state.bump_chars()
        assert game.state.objects[latecomer].dies_to is None

        destroy(game.state, latecomer)
        assert game.state.objects[latecomer].zone is Zone.GRAVEYARD

    def test_a_creature_that_survived_is_unmarked_next_turn(self, builder):
        """"…would die **this turn**." A redirect that outlived the turn would
        make everything the wrath touched permanently un-buriable."""
        game = board(builder, [TRAMPLER])
        survivor = only_oid(game, TRAMPLER, 1)
        cast_the_wrath(game)
        assert game.state.objects[survivor].zone is Zone.BATTLEFIELD

        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.objects[survivor].dies_to is None


class TestEveryWayOfDying:
    def test_a_sacrifice_is_redirected_too(self, builder):
        """The printed word is "die", which is broader than "destroyed" -- and a
        sacrifice never goes near `destroy`."""
        game = board(builder, [TRAMPLER])
        survivor = only_oid(game, TRAMPLER, 1)
        cast_the_wrath(game)
        assert game.state.objects[survivor].dies_to == "exile"

        sacrifice(game.state, survivor)
        assert game.state.objects[survivor].zone is Zone.EXILE

    def test_and_so_is_a_plain_destruction(self, builder):
        game = board(builder, [TRAMPLER])
        survivor = only_oid(game, TRAMPLER, 1)
        cast_the_wrath(game)

        destroy(game.state, survivor)
        assert game.state.objects[survivor].zone is Zone.EXILE


class TestLethalDamageIsADestruction:
    def test_a_regeneration_shield_now_saves_a_creature(self, builder):
        """704.5g. `sba._creature_deaths` called `move_object` directly, so no
        death replacement fired there at all -- a regenerating creature that took
        lethal damage died with its shield unspent."""
        game = board(builder, [BEAR])
        bear = only_oid(game, BEAR, 1)
        game.state.objects[bear].regeneration_shields = 1
        cast_the_wrath(game)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].tapped
        assert game.state.objects[bear].damage == 0
        assert game.state.objects[bear].regeneration_shields == 0

    def test_indestructible_still_survives(self, builder):
        """It is never destroyed, so there is no death for the redirect to
        replace -- the ordering `destroy` already had, unchanged."""
        game = board(builder, [BEAR])
        bear = only_oid(game, BEAR, 1)
        game.state.objects[bear].until_eot.append(
            TempEffect(kind="keyword", keyword="indestructible")
        )
        game.state.bump_chars()
        cast_the_wrath(game)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
