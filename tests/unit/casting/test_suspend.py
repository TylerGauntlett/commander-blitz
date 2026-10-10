"""Suspend: paying a card out of your hand now to cast it for free later.

Three things make this unlike anything else the engine plays, and each is a way
to get it quietly wrong:

1. **Suspending is not casting.** Nothing goes on the stack, so a version built
   as a variant of `CAST` would let an opponent counter it.
2. **The ticking is a rule, not an ability.** A suspended card sits in exile
   with no abilities, so the upkeep removal has to belong to the game the way
   the untap step does.
3. **The free cast is still a cast.** It uses the stack and can be countered —
   it simply costs nothing.

The timing is the substance: Suspend 2 means it resolves on your *second*
upkeep, not your first and not immediately.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.suspend import TIME_COUNTER
from tests.conftest import pass_until


def board(builder, forests: int = 1):
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * forests)
        .hand(0, ["search_for_tomorrow"])
        .library(0, ["forest"] * 20)
        .build()
    )


def suspend_action(game):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.SUSPEND
            and game.state.objects[a.source].def_id == "search_for_tomorrow"
        ),
        None,
    )


def take_choices(game, predicate, limit: int = 400) -> None:
    """Advance, but *accept* every optional choice rather than declining it.

    `pass_until` answers as passively as it can, which for a library search
    means fetching nothing -- fine when the assertion is about timing, useless
    when it is about what the spell did.
    """
    from tests.conftest import _default_answer

    for _ in range(limit):
        if predicate(game) or game.over:
            return
        decision = game.pending()
        if decision is None:
            return
        choose = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None
        )
        game.apply(choose or _default_answer(game, decision))
    raise AssertionError("take_choices did not reach its condition")


class TestWhatIsOffered:
    def test_one_mana_suspends_it_where_three_would_cast_it(self, builder):
        """Suspend {G} off a single Forest; the card itself costs {2}{G}."""
        game = board(builder, forests=1)
        assert suspend_action(game) is not None
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "search_for_tomorrow"
        ], "one Forest does not pay {2}{G}"

    def test_with_no_mana_it_is_not_offered(self, builder):
        assert suspend_action(board(builder, forests=0)) is None

    def test_both_lines_when_both_are_affordable(self, builder):
        game = board(builder, forests=3)
        assert suspend_action(game) is not None
        assert [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "search_for_tomorrow"
        ], "three Forests can also just cast it"

    def test_it_is_sorcery_speed(self, builder):
        """Search for Tomorrow is a Sorcery, so suspending it is too."""
        game = board(builder, forests=1)
        pass_until(game, lambda g: g.state.step is Step.END_STEP)
        assert suspend_action(game) is None


class TestSuspending:
    def test_it_exiles_the_card_with_its_time_counters(self, builder):
        game = board(builder, forests=1)
        action = suspend_action(game)
        oid = action.source
        game.apply(action)

        obj = game.state.objects[oid]
        assert obj.zone is Zone.EXILE
        assert obj.counter(TIME_COUNTER) == 2
        assert obj.suspended_by == 0

    def test_it_pays_the_suspend_cost_not_the_mana_cost(self, builder):
        game = board(builder, forests=3)
        game.apply(suspend_action(game))
        tapped = sum(1 for o in game.state.battlefield_objects(0) if o.tapped)
        assert tapped == 1, "{G}, not {2}{G}"

    def test_nothing_goes_on_the_stack(self, builder):
        """Suspending is a special action -- there is nothing to respond to."""
        game = board(builder, forests=1)
        game.apply(suspend_action(game))
        assert game.state.stack == []


def past_the_next_upkeep_of(game, pid: int) -> None:
    """Advance to the far side of ``pid``'s next upkeep.

    By turn *number* would be wrong and quietly so: applying the suspend already
    rolls the game into the opponent's turn, so "start + 1" is the caster's own
    next turn rather than the opponent's.
    """
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn > turn
        and g.state.active_player == pid
        and g.state.step > Step.UPKEEP,
    )


class TestTheTiming:
    def suspend_it(self, builder):
        game = board(builder, forests=1)
        action = suspend_action(game)
        oid = action.source
        game.apply(action)
        return game, oid

    def test_it_does_not_resolve_on_the_upkeep_it_was_suspended(self, builder):
        game, oid = self.suspend_it(builder)
        assert game.state.objects[oid].counter(TIME_COUNTER) == 2

    def test_nothing_comes_off_on_the_opponents_upkeep(self, builder):
        """"At the beginning of **your** upkeep"."""
        game, oid = self.suspend_it(builder)
        assert game.state.active_player == 1, "the suspend handed the turn over"
        pass_until(game, lambda g: g.state.active_player == 1 and g.state.step > Step.UPKEEP)
        assert game.state.objects[oid].counter(TIME_COUNTER) == 2

    def test_one_counter_comes_off_on_each_of_your_upkeeps(self, builder):
        game, oid = self.suspend_it(builder)

        past_the_next_upkeep_of(game, 0)
        assert game.state.objects[oid].counter(TIME_COUNTER) == 1
        assert game.state.objects[oid].zone is Zone.EXILE, "one counter left, still waiting"

        past_the_next_upkeep_of(game, 0)
        assert game.state.objects[oid].counter(TIME_COUNTER) == 0

    def test_it_resolves_on_your_second_upkeep(self, builder):
        """Suspend *2*. Off by one in either direction is the likeliest slip."""
        game, oid = self.suspend_it(builder)

        past_the_next_upkeep_of(game, 0)
        assert game.state.objects[oid].zone is Zone.EXILE, "not the first upkeep"

        past_the_next_upkeep_of(game, 0)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD, "the second one, though"

    def test_it_actually_does_what_it_says_when_it_resolves(self, builder):
        """Resolving is not the claim -- fetching a basic land is."""
        game, oid = self.suspend_it(builder)
        lands = len(game.state.battlefield_objects(0))
        take_choices(game, lambda g: g.state.objects[oid].zone is Zone.GRAVEYARD)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert len(game.state.battlefield_objects(0)) == lands + 1


class TestTheFreeCast:
    def test_it_costs_nothing(self, builder):
        """It resolves off a board with no mana at all, which is the proof."""
        game = board(builder, forests=1)
        action = suspend_action(game)
        oid = action.source
        game.apply(action)

        # Strip the mana base: nothing is left that could pay {2}{G}.
        for land in [o.oid for o in game.state.battlefield_objects(0)]:
            game.state.battlefield.remove(land)
        game.state.bump_chars()

        pass_until(
            game,
            lambda g: g.state.objects[oid].zone is Zone.GRAVEYARD or g.state.turn > 8,
        )
        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_a_suspended_creature_would_have_haste(self, registry, builder):
        """The reason suspend is ever better than waiting.

        No creature in this pool suspends, so the flag is exercised directly --
        the alternative is asserting nothing about a rule 65 catalog cards need.
        """
        from commanderblitz.engine.characteristics import chars

        game = builder(players=2).battlefield(0, ["grizzly_bears"]).build()
        bear = game.state.battlefield[0]
        game.state.objects[bear].entered_turn = game.state.turn  # just arrived
        game.state.bump_chars()
        assert "haste" not in chars(game.state, bear).keywords

        game.state.objects[bear].hasted_by_suspend = True
        game.state.bump_chars()
        assert "haste" in chars(game.state, bear).keywords

        # And it survives the turn -- an `until_eot` entry would not.
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        assert "haste" in chars(game.state, bear).keywords
