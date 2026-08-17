"""Ninjutsu — swapping a creature into a combat already under way.

    "Ninjutsu {1}{U} ({1}{U}, Return an unblocked attacker you control to hand:
    Put this card onto the battlefield from your hand tapped and attacking.)"

The census filed this as blocked on "returning an unblocked attacker and putting
a creature in attacking, without casting". Both halves turned out to be one
missing word each:

- **"unblocked"** is a new selector key, and it is *not* the negation of
  `blocking`. That key asks whether a creature is blocking something; this asks
  whether anything is blocking **this attacker**, and the two are different
  creatures. `Cost.return_to_hand` already existed, for Meloku.
- **"attacking"** is `create_token`'s clause, moved onto
  `put_onto_battlefield`. The ninja joins the combat the returned attacker just
  left, which is why it arrives unblocked: the blocker that was there was
  blocking a creature now sitting in its owner's hand.

The ability is offered from **hand**, and it satisfies the outside-the-
battlefield guard through unearth's satisfier — an unconditional top-level
effect that moves `self_only` out. Ninjutsu was in fact the shape that made that
satisfier obviously right: the cost is mana plus a bounce, and the card leaves
hand because the *effect* puts it onto the battlefield.

A permanent put in this way was never **declared** as an attacker (508.4), so it
triggers nothing that fires on attacking — the same contract `create_token`
carries, and what keeps "when this attacks, put a creature in attacking" finite.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step, Zone
from tests.conftest import _default_answer, oids_of, only_oid

ISLAND = "island"
NINJA = "t_ninja"
BEAR = "t_bear"
WALL = "t_defensive_wall"


def position(builder, blockers: list[str] | None = None):
    return (
        builder(players=2)
        .battlefield(0, [ISLAND] * 3)
        .battlefield(0, [BEAR])
        .battlefield(1, blockers or [])
        .hand(0, [NINJA])
        .library(0, [ISLAND] * 20)
        .library(1, [ISLAND] * 20)
        .build()
    )


def run_combat(game, *, block: bool = False, ninjutsu: bool = False, after_blocks: bool = False):
    """Attack with the Bear and run the combat, watching for the ninjutsu offer.

    Returns ``(offered, activated)``. Written as a scan rather than a sequence
    of asserts because the engine auto-passes through any priority window where
    a seat has nothing to do -- so with the attacker blocked there is no moment
    at which to stand and look, and "it was never offered" is the observation.

    ``block`` has to be explicit: `_default_answer` finishes a block declaration
    without adding anyone, so a test that merely passed priority would leave the
    attacker unblocked and every "blocked" assertion would pass vacuously.
    """
    offered = False
    activated = False
    for _ in range(400):
        decision = game.pending()
        if decision is None:
            break
        # `after_blocks` is the honest window for the "blocked" claim. *Before*
        # blockers are declared no attacker is blocked, so ninjutsu is legally
        # offered then -- which is real, and is not what that test is about.
        watching = not after_blocks or (
            game.state.combat is not None and game.state.combat.blockers_declared
        )
        action = ninjutsu_action(game) if watching else None
        if action is not None:
            offered = True
            if ninjutsu and not activated:
                activated = True
                game.apply(action)
                return offered, activated
        if decision.kind.value == "declare_attackers" and decision.player == 0:
            add = next(
                (a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER),
                None,
            )
            if add is not None:
                game.apply(add)
                continue
        if block and decision.kind.value == "declare_blockers":
            add = next(
                (a for a in game.legal_actions() if a.kind is ActionKind.ADD_BLOCKER),
                None,
            )
            if add is not None:
                game.apply(add)
                continue
        if game.state.step is Step.END_OF_COMBAT:
            break
        game.apply(_default_answer(game, decision))
    return offered, activated


def ninjutsu_action(game):
    ninja = next(
        (o for o in game.state.players[0].hand if game.state.objects[o].def_id == NINJA),
        None,
    )
    if ninja is None:
        return None
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == ninja
        ),
        None,
    )


class TestWhenItIsOffered:
    def test_it_is_offered_with_an_unblocked_attacker(self, builder):
        game = position(builder)
        offered, _ = run_combat(game)
        assert offered

    def test_it_is_still_offered_after_blocks_are_declared_and_nobody_blocked(
        self, builder
    ):
        """The window the keyword is actually played in."""
        game = position(builder, blockers=[BEAR])
        offered, _ = run_combat(game, block=False, after_blocks=True)
        assert offered

    def test_it_is_not_offered_before_combat(self, builder):
        """Nothing is attacking, so the cost has nothing to return."""
        game = position(builder)
        assert ninjutsu_action(game) is None

    def test_it_is_not_offered_when_the_attacker_is_blocked(self, builder):
        """The whole of "unblocked", and the reason it is not `not blocking`."""
        game = position(builder, blockers=[BEAR])
        offered, _ = run_combat(game, block=True, after_blocks=True)
        assert not offered, "a blocked attacker cannot be swapped out"


class TestWhatItDoes:
    def _swap(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR)
        offered, activated = run_combat(game, ninjutsu=True)
        assert offered and activated
        return game, bear

    def test_the_attacker_goes_back_to_hand(self, builder):
        game, bear = self._swap(builder)
        assert game.state.objects[bear].zone is Zone.HAND

    def test_the_ninja_arrives_on_the_battlefield(self, builder):
        game, _ = self._swap(builder)
        assert len(oids_of(game, NINJA)) == 1

    def test_it_arrives_tapped(self, builder):
        game, _ = self._swap(builder)
        assert game.state.objects[only_oid(game, NINJA)].tapped

    def test_it_arrives_attacking(self, builder):
        game, _ = self._swap(builder)
        ninja = only_oid(game, NINJA)
        assert game.state.combat is not None
        assert game.state.combat.attacking(ninja)

    def test_it_connects_for_its_own_power(self, builder):
        """The observable consequence: a 3/2 ninja, not the 2/2 that was bounced."""
        game, _ = self._swap(builder)
        life = game.state.players[1].life
        for _ in range(200):
            decision = game.pending()
            if decision is None or game.state.players[1].life != life:
                break
            game.apply(_default_answer(game, decision))

        assert game.state.players[1].life == life - 3
