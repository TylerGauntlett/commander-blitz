"""Phasing something out *until this permanent leaves* — Oubliette.

"When this enchantment enters, target creature phases out until this enchantment
leaves the battlefield. Tap that creature as it phases in this way."

`phase_out` already shipped (see `test_phase_out_effect.py`) and could not say
this card. Two things were missing and they fail in opposite directions:

**The duration.** `turn.phase_out` recorded nothing about its cause, and the
untap walk phased every phased-out permanent back in at its controller's very
next untap step, unconditionally. A card written with the plain op therefore
returns the creature with the enchantment still on the board — a materially
weaker card that looks completely right for one turn, which is the worst kind of
wrong. `t_loose_oubliette` is that card, kept here so the pair pins that the link
is what does the work.

**Naming it again.** A phased-out permanent is "treated as though it does not
exist" (702.26c) and is out of `state.battlefield` entirely, so no ordinary
selector could reach it — the enchantment's own leaves-trigger could not find
the creature it had sent away. `phased_out_with` is the phasing twin of
`exiled_with`, and it is narrow for the same reason: a filter matching every
phased-out permanent would hand back creatures this card never touched.

Why exile is not a substitute, even though `until_leaves` is exactly the O-Ring
shape: exiling loses counters, attachments and continuous effects and fires zone
changes, and phasing deliberately does none of that.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Step, Zone
from tests.conftest import only_oid, pass_until

OUBLIETTE = "t_oubliette"  # links, and taps on the way back
UNTAPPED = "t_untapped_oubliette"  # links, but no `tapped` rider
LOOSE = "t_loose_oubliette"  # no link -- the card the engine could already say
BEAR = "t_bear"


def board(builder, card: str):
    """The victim is the caster's own creature, as in `test_phase_out_effect`.

    Its controller's untap step is the clock the link has to defeat, so the
    creature has to be somewhere that clock actually reaches.
    """
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 5 + [BEAR])
        .hand(0, [card])
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def cast_it(game, card: str) -> None:
    """Cast it and stop the instant the creature has phased out.

    Not `pass_until(not stack)`: auto-pass runs the game forward through every
    step nobody can act in inside a single `apply`, so a predicate checked
    between applies can land turns later. The event log is the honest place to
    ask whether this has happened yet.
    """
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == card
        )
    )
    pass_until(game, lambda g: any(e.type == "phased_out" for e in g.state.events))


def setup(builder, card: str) -> tuple:
    game = board(builder, card)
    bear = only_oid(game, BEAR, 0)
    cast_it(game, card)
    return game, bear, only_oid(game, card, 0)


def destroy_it(game, oid: int) -> None:
    """Destroy the enchantment and let its leaves-trigger actually resolve.

    Deliberately not `pass_until(not stack)`: `destroy` only *queues* the
    trigger, so the stack is still empty at the moment that predicate is first
    checked and `pass_until` returns immediately, before anything has happened.
    The trigger has not even drained yet. Waiting on the `phased_in` event waits
    for the thing the test is actually about.
    """
    from commanderblitz.engine.zones import destroy

    destroy(game.state, oid)
    pass_until(game, lambda g: any(e.type == "phased_in" for e in g.state.events))


class TestTheLinkIsRecorded:
    def test_the_creature_is_phased_out(self, builder):
        game, bear, _ = setup(builder, OUBLIETTE)
        assert game.state.objects[bear].phased_out
        assert bear not in game.state.battlefield

    def test_it_remembers_which_permanent_did_it(self, builder):
        game, bear, oubliette = setup(builder, OUBLIETTE)
        assert game.state.objects[bear].phased_out_by == oubliette

    def test_an_unlinked_phase_out_records_nothing(self, builder):
        """The plain printed one-shot is unchanged: no link, no suspension."""
        game, bear, _ = setup(builder, LOOSE)
        assert game.state.objects[bear].phased_out
        assert game.state.objects[bear].phased_out_by is None


class TestTheUntapStepDoesNotHandItBack:
    """The duration, and the reason the link exists at all."""

    def test_it_is_still_out_after_its_controllers_untap_step(self, builder):
        game, bear, _ = setup(builder, OUBLIETTE)
        pass_until(game, lambda g: g.state.turn >= 4)
        assert game.state.objects[bear].phased_out, (
            "the creature came back on its own clock; the link was not honoured"
        )
        assert bear not in game.state.battlefield

    def test_without_the_link_it_does_come_back(self, builder):
        """The other half of the pair. If this ever fails the test above proves
        nothing — it would just mean nothing phases in any more."""
        game, bear, _ = setup(builder, LOOSE)
        pass_until(game, lambda g: any(e.type == "phased_in" for e in g.state.events))
        assert not game.state.objects[bear].phased_out
        assert bear in game.state.battlefield


class TestItComesBackWhenTheSourceLeaves:
    def test_destroying_the_enchantment_phases_it_in(self, builder):
        game, bear, oubliette = setup(builder, OUBLIETTE)
        destroy_it(game, oubliette)
        assert not game.state.objects[bear].phased_out
        assert bear in game.state.battlefield

    def test_it_returns_tapped(self, builder):
        """"Tap that creature as it phases in this way." — the second sentence."""
        game, bear, oubliette = setup(builder, OUBLIETTE)
        assert not game.state.objects[bear].tapped
        destroy_it(game, oubliette)
        assert game.state.objects[bear].tapped

    def test_without_the_rider_it_returns_untapped(self, builder):
        """`tapped` is a real parameter, not something phasing in always does."""
        game, bear, oubliette = setup(builder, UNTAPPED)
        destroy_it(game, oubliette)
        assert not game.state.objects[bear].phased_out
        assert not game.state.objects[bear].tapped

    def test_the_link_is_cleared_on_the_way_in(self, builder):
        """Otherwise the creature is permanently unreachable by the untap walk,
        and a second phase-out would be stranded forever."""
        game, bear, oubliette = setup(builder, OUBLIETTE)
        destroy_it(game, oubliette)
        assert game.state.objects[bear].phased_out_by is None


class TestItIsStillNotABlink:
    """Everything `test_phase_out_effect` pins, still true across the link.

    The link changes *when* the permanent comes back and nothing else; if it had
    quietly become an exile-and-return, every one of these would break.
    """

    def test_the_object_never_changes_zone(self, builder):
        game = board(builder, OUBLIETTE)
        bear = only_oid(game, BEAR, 0)
        before = len(game.state.events)
        cast_it(game, OUBLIETTE)
        changes = [
            e
            for e in game.state.events[before:]
            if e.type == "zone_change" and e.data.get("oid") == bear
        ]
        assert not changes
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_counters_survive_the_whole_round_trip(self, builder):
        game = board(builder, OUBLIETTE)
        bear = only_oid(game, BEAR, 0)
        game.state.objects[bear].add_counter("+1/+1", 2)
        cast_it(game, OUBLIETTE)
        destroy_it(game, only_oid(game, OUBLIETTE, 0))
        assert game.state.objects[bear].counter("+1/+1") == 2

    def test_its_controller_still_controls_it(self, builder):
        game, bear, _ = setup(builder, OUBLIETTE)
        assert game.state.objects[bear].controller == 0
