"""Vorinclex, and the two things that happen when a land taps for mana.

Neither half can be a triggered ability. Tapping for mana happens *inside*
payment, where nothing may go on the stack and nothing may stop to ask — so both
are read at the choke point in `activate_mana_ability` instead.

The half worth being frightened of is the doubling, because it is computed in
two places: `_sources_of`, so legality knows what is castable, and
`activate_mana_ability`, so payment adds it. If those two ever disagree, a spell
gets offered on doubled mana and then paid for on single mana, which strands the
payment mid-cast. They share `mana_produced` for exactly that reason, and the
last test here is the one that would catch them drifting apart.
"""

from __future__ import annotations

from commanderblitz.engine.costs import available_mana, mana_sources
from commanderblitz.engine.enums import ActionKind, Step
from tests.conftest import only_oid, pass_until


def board(builder, *, with_vorinclex: bool, forests: int = 3):
    extra = ["vorinclex_voice_of_hunger"] if with_vorinclex else []
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * forests + extra)
        .battlefield(1, ["forest"] * forests)
        .build()
    )


class TestYourLandsMakeTwice:
    def test_each_land_taps_for_two(self, builder):
        plain = board(builder, with_vorinclex=False)
        doubled = board(builder, with_vorinclex=True)
        assert available_mana(plain.state, 0) == 3
        assert available_mana(doubled.state, 0) == 6

    def test_only_lands_are_doubled(self, registry, builder):
        """"Whenever you tap a *land*" -- a mana rock is untouched."""
        if "sol_ring" not in registry:
            import pytest

            pytest.skip("no mana rock in the pool")
        game = (
            builder(players=2)
            .battlefield(0, ["forest", "sol_ring", "vorinclex_voice_of_hunger"])
            .build()
        )
        rock = only_oid(game, "sol_ring")
        source = next(s for s in mana_sources(game.state, 0) if s.oid == rock)
        assert source.max_output() == 2, "Sol Ring's own two, not four"

    def test_the_opponent_is_not_helped(self, builder):
        game = board(builder, with_vorinclex=True)
        assert available_mana(game.state, 1) == 3, "'whenever *you* tap a land'"

    def test_the_pool_actually_receives_the_doubled_mana(self, builder):
        """Legality's count and payment's addition must be the same number."""
        from commanderblitz.engine.costs import activate_mana_ability

        game = board(builder, with_vorinclex=True)
        forest = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == "forest")
        activate_mana_ability(game.state, forest, 0, 0)
        assert game.state.players[0].mana_pool.total() == 2


class TestOpponentLandsStayTapped:
    def play_a_spell(self, game, pid: int):
        """Tap one of this player's lands for mana by casting something."""
        from commanderblitz.engine.costs import activate_mana_ability

        land = next(o.oid for o in game.state.battlefield_objects(pid) if o.def_id == "forest")
        activate_mana_ability(game.state, land, 0, pid)
        return land

    def test_an_opponents_land_does_not_untap(self, builder):
        game = board(builder, with_vorinclex=True)
        land = self.play_a_spell(game, 1)
        assert game.state.objects[land].tapped
        assert game.state.objects[land].skip_next_untap

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn + 1)
        assert game.state.objects[land].tapped, "it skipped its untap step"

    def test_it_untaps_the_turn_after(self, builder):
        """A *one-shot*. The land is not locked down forever."""
        game = board(builder, with_vorinclex=True)
        land = self.play_a_spell(game, 1)

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn + 1)
        assert game.state.objects[land].tapped
        assert not game.state.objects[land].skip_next_untap, "the flag was spent"

        pass_until(game, lambda g: g.state.turn > turn + 3)
        assert not game.state.objects[land].tapped

    def test_your_own_lands_are_unaffected(self, builder):
        game = board(builder, with_vorinclex=True)
        land = self.play_a_spell(game, 0)
        assert not game.state.objects[land].skip_next_untap, "'an *opponent* taps'"

    def test_nothing_happens_without_vorinclex(self, builder):
        game = board(builder, with_vorinclex=False)
        land = self.play_a_spell(game, 1)
        assert not game.state.objects[land].skip_next_untap


class TestTheSkipUntapOp:
    """The same flag, reachable by a card rather than only by Vorinclex.

    `skip_untap` and `freeze` look alike and are not: this one is spent by the
    untap step it skips, where a freeze holds for as long as its source is on
    the battlefield. Both directions of that confusion are pinned here.
    """

    def tap_and_skip(self, builder):
        """A creature the opponent controls, tapped, told not to untap."""
        from commanderblitz.engine.effects import execute
        from commanderblitz.engine.effects.context import EffectContext

        game = builder(players=2).battlefield(1, ["grizzly_bears"]).build()
        bear = only_oid(game, "grizzly_bears", 1)
        game.state.objects[bear].tapped = True
        game.state.bump_chars()

        ctx = EffectContext(state=game.state, controller=0, bindings={"it": bear})
        list(execute(ctx, [{"op": "skip_untap", "objects": {"binding": "it"}}]))
        return game, bear

    def test_it_holds_a_permanent_down_for_one_untap_step(self, builder):
        game, bear = self.tap_and_skip(builder)
        assert game.state.objects[bear].skip_next_untap

        owner = 1
        turn = game.state.turn
        pass_until(
            game,
            lambda g: g.state.turn > turn and g.state.active_player == owner
            and g.state.step > Step.UNTAP,
        )
        assert game.state.objects[bear].tapped, "it skipped its untap step"
        assert not game.state.objects[bear].skip_next_untap, "and the flag is spent"

    def test_it_untaps_the_time_after(self, builder):
        """One step only -- it is not a permanent lock."""
        game, bear = self.tap_and_skip(builder)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn + 3)
        assert not game.state.objects[bear].tapped

    def test_an_already_untapped_permanent_still_spends_it(self, builder):
        """Otherwise the flag waits around and skips some later, unrelated step."""
        from commanderblitz.engine.effects import execute
        from commanderblitz.engine.effects.context import EffectContext

        game = builder(players=2).battlefield(1, ["grizzly_bears"]).build()
        bear = only_oid(game, "grizzly_bears", 1)
        ctx = EffectContext(state=game.state, controller=0, bindings={"it": bear})
        list(execute(ctx, [{"op": "skip_untap", "objects": {"binding": "it"}}]))

        turn = game.state.turn
        pass_until(
            game,
            lambda g: g.state.turn > turn and g.state.active_player == 1
            and g.state.step > Step.UNTAP,
        )
        assert not game.state.objects[bear].skip_next_untap


class TestTheTwoHalvesTogether:
    def test_a_spell_offered_on_doubled_mana_can_be_paid_for(self, builder):
        """The drift test: legality says castable, payment must agree.

        Terastodon costs {6}{G}{G}. Four Forests is four mana on their own and
        eight with Vorinclex out, so this cast exists *only* because of the
        doubling — and going through with it proves both sides of the mechanic
        computed the same number.
        """

        def can_cast(with_vorinclex: bool):
            extra = ["vorinclex_voice_of_hunger"] if with_vorinclex else []
            game = (
                builder(players=2)
                .battlefield(0, ["forest"] * 4 + extra)
                .hand(0, ["terastodon"])
                .build()
            )
            action = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CAST
                    and game.state.objects[a.source].def_id == "terastodon"
                ),
                None,
            )
            return game, action

        _, without = can_cast(False)
        assert without is None, "four Forests do not pay eight"

        game, cast = can_cast(True)
        assert cast is not None, "{6}{G}{G} off four doubled Forests"
        game.apply(cast)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert [o for o in game.state.battlefield_objects(0) if o.def_id == "terastodon"]
