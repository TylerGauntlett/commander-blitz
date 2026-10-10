"""Monstrosity, and the lock that hangs off it.

Two one-way things worth pinning. Monstrosity is once-only -- without the flag
the ability is a repeatable pump and the trigger that reads it fires every time.
And the freeze it applies lasts "for as long as you control this creature",
which means it has to *end*: a lock with no way out is a different and much
stronger card than the one printed.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.zones import destroy
from tests.conftest import only_oid, pass_until


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 8 + ["shipbreaker_kraken"])
        .battlefield(1, ["grizzly_bears"] * 2)
        .build()
    )


def go_monstrous(game):
    kraken = only_oid(game, "shipbreaker_kraken")
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == kraken
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    return kraken


class TestMonstrosity:
    def test_it_adds_the_counters_and_sets_the_flag(self, builder):
        game = board(builder)
        kraken = go_monstrous(game)
        assert game.state.objects[kraken].monstrous
        assert chars(game.state, kraken).power == 10, "6/6 plus four counters"

    def test_it_only_happens_once(self, builder):
        game = board(builder)
        kraken = go_monstrous(game)
        counters = game.state.objects[kraken].counter("+1/+1")

        # Untap and try again; the ability is still legal, it just does nothing.
        for oid in list(game.state.battlefield):
            game.state.objects[oid].tapped = False
        game.state.bump_chars()
        again = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == kraken
        ]
        if again:
            game.apply(again[0])
            pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert game.state.objects[kraken].counter("+1/+1") == counters


class TestTheFreeze:
    def frozen(self, game):
        return [o for o in game.state.battlefield_objects(1) if o.frozen_by is not None]

    def test_becoming_monstrous_taps_and_holds_them(self, builder):
        game = board(builder)
        go_monstrous(game)
        held = self.frozen(game)
        assert held, "the trigger should have caught the opponent's creatures"
        assert all(o.tapped for o in held)

    def test_they_stay_tapped_through_their_untap_step(self, builder):
        game = board(builder)
        go_monstrous(game)
        held = [o.oid for o in self.frozen(game)]

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn + 1)
        assert all(game.state.objects[oid].tapped for oid in held)

    def test_the_hold_ends_when_the_kraken_does(self, builder):
        """'for as long as you control this creature' -- so it has to end."""
        game = board(builder)
        kraken = go_monstrous(game)
        held = [o.oid for o in self.frozen(game)]

        destroy(game.state, kraken)
        assert game.state.objects[kraken].zone is Zone.GRAVEYARD

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn + 1)
        assert not any(game.state.objects[oid].tapped for oid in held)
        assert not any(game.state.objects[oid].frozen_by for oid in held)
