"""Permanents a static stops from untapping.

    Back to Basics — "Nonbasic lands don't untap during their controllers'
    untap steps."
    Intruder Alarm — "Creatures don't untap during their controllers' untap
    steps."
    Mana Vault — "This artifact doesn't untap during your untap step."

`static_effects` carried `untap_during_each_untap_step`, the exact inverse, and
nothing that suppressed untapping. The two engine fields that *do* suppress it
are both written by resolution rather than printed on a card:
`skip_next_untap` is a one-shot that `untap_all` spends in the very untap step
it skips, and `frozen_by` is set by the `freeze` op. Both are ops, so the only
way to reach either from a printed static was to invent a `self_enters` trigger
to carry a line that is printed as a static — which would sit on the stack, be
respondable, and be re-installed on every re-entry rather than simply being true
while the permanent is on the battlefield.

So it is read where it happens, beside its inverse, rather than layered into
`chars`: whether a permanent untaps is a fact about a set of permanents at one
moment in the turn, and no characteristic carries it.

Four things that would each be a different card:

- **Any controller.** Both enchantments say "their controllers' untap steps".
  Intruder Alarm stopping only its own controller's creatures would be a
  one-sided lock rather than the symmetric drawback the card is built around —
  and the deck that plays it is relying on the opponent being locked too.
- **No lifetime of its own.** It holds for exactly as long as the source is on
  the battlefield and is spent by nothing. A `skip_next_untap` version releases
  the permanent on the following turn.
- **It must not spend `skip_next_untap`.** A permanent held by both must not
  burn the one-shot while the static is already holding it, or the flag is
  consumed by an untap step that was never going to untap it anyway.
- **Explicit untap effects still work.** Mana Vault's own upkeep payment untaps
  it; the static is read by the untap step alone.

`not_supertypes` arrived with this for Back to Basics — the negation of
`supertypes` that the effect-side selector language always had and the static
one did not, the same asymmetry `not_keywords` was added to close. A `not_types`
complement is not a spelling of it: that is every permanent which is not a land.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.player_statics import untap_held
from commanderblitz.engine.primitives import untap_all, untap_permanent
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

VAULT = "t_vault_self_lock"
BASICS = "t_back_to_basics"
ALARM = "t_intruder_alarm_lock"
BEAR = "t_bear"
DORK = "t_dork"


def _pass_to_next_untap(game) -> None:
    """Advance until the active player changes and a new turn has begun.

    The untap step grants no priority, so it cannot be observed from inside.
    The first moment anybody can look is once the next player holds priority.
    """
    start = game.state.active_player
    for _ in range(400):
        if game.state.active_player != start and game.state.turn > 1:
            return
        action = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.PASS), None
        ) or next(
            (a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION),
            None,
        )
        if action is None:
            raise AssertionError(f"stuck at {game.state.step} with no way to pass")
        game.apply(action)
    raise AssertionError("never reached the next turn")


class TestASelfLock:
    """Mana Vault's shape: `affects: {"self_only": true}`."""

    def test_the_source_stays_tapped_through_its_own_untap_step(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .battlefield(0, [VAULT], tapped=True)
            .build()
        )
        vault = only_oid(game, VAULT)
        untap_all(game.state, 0)
        assert game.state.objects[vault].tapped, "the static did not hold it down"

    def test_without_the_static_it_untaps(self, builder):
        """The pair, and the one that makes the test above mean anything."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .battlefield(0, [BEAR], tapped=True)
            .build()
        )
        bear = only_oid(game, BEAR)
        untap_all(game.state, 0)
        assert not game.state.objects[bear].tapped

    def test_an_explicit_untap_still_works(self, builder):
        """Mana Vault's own upkeep payment untaps it (the printed card).

        The static is read by the untap step alone, so a targeted untap is
        untouched -- exactly as `frozen_by` leaves explicit untaps alone.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .battlefield(0, [VAULT], tapped=True)
            .build()
        )
        vault = only_oid(game, VAULT)
        untap_permanent(game.state, vault)
        assert not game.state.objects[vault].tapped

    def test_the_hold_ends_when_the_source_leaves(self, builder):
        """No lifetime of its own: it is true while the permanent is out."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .battlefield(0, [VAULT], tapped=True)
            .build()
        )
        vault = only_oid(game, VAULT)
        untap_all(game.state, 0)
        assert game.state.objects[vault].tapped
        move_object(game.state, vault, Zone.GRAVEYARD)
        # A second permanent proves the set is recomputed rather than cached.
        assert untap_held(game.state, 0) == set()


class TestItReachesEveryController:
    """"…their controllers' untap steps" -- Intruder Alarm locks the table."""

    def test_an_opponents_creature_is_held_on_their_own_untap_step(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 3 + [ALARM])
            .battlefield(1, [BEAR], tapped=True)
            .build()
        )
        bear = only_oid(game, BEAR)
        assert game.state.objects[bear].tapped
        _pass_to_next_untap(game)
        assert game.state.objects[bear].tapped, (
            "Intruder Alarm only locked its own controller -- a one-sided card"
        )

    def test_without_the_static_the_opponent_untaps(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 3)
            .battlefield(1, [BEAR], tapped=True)
            .build()
        )
        bear = only_oid(game, BEAR)
        _pass_to_next_untap(game)
        assert not game.state.objects[bear].tapped

    def test_the_controllers_own_creature_is_held_too(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 3 + [ALARM])
            .battlefield(0, [BEAR], tapped=True)
            .build()
        )
        bear = only_oid(game, BEAR)
        untap_all(game.state, 0)
        assert game.state.objects[bear].tapped


class TestTheFilterIsRead:
    """Back to Basics: lands, and only the nonbasic ones."""

    def test_a_nonbasic_land_is_held(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 3 + [BASICS])
            .battlefield(0, ["command_tower"], tapped=True)
            .build()
        )
        tower = only_oid(game, "command_tower")
        untap_all(game.state, 0)
        assert game.state.objects[tower].tapped

    def test_a_basic_land_is_not(self, builder):
        """The clause the card is named for. Without `not_supertypes` this is
        the assertion that fails: the static would lock every land, which is a
        strictly stronger card that also locks its own controller's Islands."""
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 3 + [BASICS])
            .battlefield(0, ["forest"], tapped=True)
            .build()
        )
        forest = only_oid(game, "forest")
        untap_all(game.state, 0)
        assert not game.state.objects[forest].tapped, (
            "a basic land was held -- not_supertypes was not read"
        )

    def test_a_creature_is_not_held_by_a_land_lock(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 3 + [BASICS])
            .battlefield(0, [BEAR], tapped=True)
            .build()
        )
        bear = only_oid(game, BEAR)
        untap_all(game.state, 0)
        assert not game.state.objects[bear].tapped


class TestItDoesNotFightTheOneShot:
    def test_a_held_permanent_keeps_its_skip_next_untap(self, builder):
        """`untap_all` spends `skip_next_untap` whether or not it mattered.

        A permanent the static is already holding must not burn the flag: the
        one-shot is somebody else's effect, and it should still be waiting when
        this static's source leaves.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .battlefield(0, [VAULT], tapped=True)
            .build()
        )
        vault = only_oid(game, VAULT)
        game.state.objects[vault].skip_next_untap = True
        untap_all(game.state, 0)
        assert game.state.objects[vault].tapped
        assert game.state.objects[vault].skip_next_untap, (
            "the static spent a one-shot it was already covering"
        )

    def test_an_unheld_permanent_still_spends_it(self, builder):
        """The near miss: the ordinary one-shot path is unchanged."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .battlefield(0, [BEAR], tapped=True)
            .build()
        )
        bear = only_oid(game, BEAR)
        game.state.objects[bear].skip_next_untap = True
        untap_all(game.state, 0)
        assert game.state.objects[bear].tapped
        assert not game.state.objects[bear].skip_next_untap
