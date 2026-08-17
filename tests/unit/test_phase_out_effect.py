""""Target creature phases out." (702.26)

    Gallifrey Falls // No More, Teferi's Veil, Vanishing.

Phasing shipped as a *keyword the untap step reads* and nothing else. The whole
mechanism lived in `turn.py` behind two private functions whose only caller was
the untap walk, so a card could say "this creature has phasing" and no card
could say "this creature phases out".

The two workarounds both make a different card:

- **`grant_keyword: "phasing"`** does nothing *now* — the creature is still on
  the battlefield — and then flickers it out and back for the rest of the game.
- **A blink** (exile and return) is not phasing at all. A phased-out permanent
  never leaves the battlefield: it keeps its counters, its attachments and every
  continuous effect on it, its controller keeps controlling it, and nothing that
  watches for a zone change sees anything happen.

So the op is a thin call onto the mechanism that already existed, made public.
Two things come with it for free because they were already there: 702.26e takes
whatever is attached along, and the untap walk phases the permanent back in
before its controller's next untap step and leaves it there — a permanent
phased out *by an effect* has no `phasing` keyword, so it does not go straight
back out.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step, Zone
from tests.conftest import only_oid, pass_until

SPELL = "t_phase_out"  # "Target creature phases out."
BEAR = "t_bear"
EQUIPMENT = "t_clamp"  # Skullclamp; on the board and attached by hand


def board(builder):
    """The victim is the caster's own creature, deliberately.

    "Phases back in before its controller's next untap step" is the whole
    duration, and an opponent's creature phased out on your turn comes back one
    step later -- which the engine does correctly and which leaves no window to
    observe, because priority auto-passes straight through it.
    """
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 5 + [BEAR, EQUIPMENT])
        .hand(0, [SPELL])
        .library(0, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def cast_it(game) -> None:
    """Cast it and stop the instant it has resolved.

    Deliberately not `pass_until(not stack)`: auto-pass runs the game forward
    through every step nobody can act in, all inside one `apply`, so a
    predicate checked between applies can land two turns later. The event log
    is the honest place to ask whether this has happened yet.
    """
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == SPELL
        )
    )
    pass_until(game, lambda g: any(e.type == "phased_out" for e in g.state.events))


class TestItLeavesTheBattlefieldList:
    def test_the_creature_is_phased_out(self, builder):
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        cast_it(game)
        assert game.state.objects[bear].phased_out

    def test_it_is_off_the_battlefield_list(self, builder):
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        cast_it(game)
        assert bear not in game.state.battlefield


class TestItIsNotABlink:
    def test_the_object_never_changes_zone(self, builder):
        """The whole difference from exile-and-return: no zone change happens,
        so nothing that watches for one sees anything."""
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        before = len(game.state.events)
        cast_it(game)

        zone_changes = [
            e
            for e in game.state.events[before:]
            if e.type == "zone_change" and e.data.get("oid") == bear
        ]
        assert not zone_changes
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_counters_survive(self, builder):
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        game.state.objects[bear].add_counter("+1/+1", 2)
        cast_it(game)
        assert game.state.objects[bear].counter("+1/+1") == 2

    def test_its_controller_still_controls_it(self, builder):
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        cast_it(game)
        assert game.state.objects[bear].controller == 0


class TestItComesBack:
    def test_before_its_controllers_next_untap_step(self, builder):
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        cast_it(game)
        assert game.state.objects[bear].phased_out

        pass_until(game, lambda g: any(e.type == "phased_in" for e in g.state.events))
        assert not game.state.objects[bear].phased_out
        assert bear in game.state.battlefield

    def test_and_stays(self, builder):
        """A permanent phased out by an *effect* has no `phasing` keyword, so
        the untap walk does not send it straight back out."""
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        cast_it(game)
        pass_until(game, lambda g: g.state.turn >= 4)
        assert not game.state.objects[bear].phased_out


class TestWhatItTakesWithIt:
    def test_an_attached_permanent_goes_too(self, builder):
        """702.26e. Free, because the mechanism already did it for the keyword."""
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        # Attached by hand: what matters here is the link, not how it got there.
        equipment = only_oid(game, EQUIPMENT, 0)
        game.state.objects[equipment].attached_to = bear
        game.state.bump_chars()
        cast_it(game)
        assert game.state.objects[equipment].phased_out
        assert game.state.objects[equipment].phased_out_indirectly
