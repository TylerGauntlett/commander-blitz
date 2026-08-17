""""If **an opponent** controls more lands than you" -- one opponent, not all of them.

    Knight of the White Orchid -- "When this creature enters, if an opponent
    controls more lands than you, you may search your library for a Plains card,
    put it onto the battlefield, then shuffle."

    Weathered Wayfarer -- "{W}, {T}: Search your library for a land card, reveal
    it, put it into your hand, then shuffle. Activate only if an opponent
    controls more lands than you."

Rule 102.1: an opponent is *a* player, singular. So the clause is a comparison
against one player's land count at a time, and it is true when any single
opponent's beats yours.

`count` cannot say it. It resolves **one** pool, and `controller: "opponent"` is
"every opponent at once" (`selectors._zone_owners`, and the comment beside it),
so `{"count": {"types": ["Land"], "controller": "opponent"}}` is the *sum* across
the table. In a duel that is the printed card. At a four-player pod it is a
different and strictly better one: three opponents holding two lands each total
six and beat your five, so the Knight becomes an unconditional two-mana 2/2 that
ramps and the Wayfarer an unconditional one-mana repeatable land tutor -- while
both printed cards are switched off whenever you are the one who is ahead. That
inversion is the single claim this file exists to pin, and
:class:`TestOnePlayerAtATime` is where it lives.

`max_count_of` is the existential ("an opponent controls more…") and
`min_count_of` the universal ("each opponent controls more…"), exactly the
`min_life_of` / `max_life_of` split already in `effects/values.py` and for
exactly the reason recorded there. The empty-table bias goes the same way too:
the existential over nobody is 0 and false, the universal over nobody is
`NO_PLAYERS_COUNT` and vacuously true.

Three call sites reach the leaf and each is a different language, so each is
covered separately: a trigger's intervening-``if`` (rule 603.4, checked both when
the trigger fires and again on resolution), an activated ability's ``condition``
(rule 602.5c, a legality question asked only at activation), and a static's
``condition`` -- which is the *mirror* condition language in
`characteristics._condition_met`, so a leaf added to one and not the other would
load in a card that then quietly read 0.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import _validate_static_value
from automtg.engine.characteristics import NO_PLAYERS_COUNT, chars
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value, validate_value
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError
from tests.conftest import action_for_card, find_action, only_oid, pass_until

FOREST = "forest"
PLAINS = "plains"
KNIGHT = "knight_of_the_white_orchid"
WAYFARER = "weathered_wayfarer"
WATCHER = "t_land_watcher"  # flying while an opponent is ahead on lands

LANDS = {"zone": "battlefield", "types": ["Land"]}
MOST = {"max_count_of": {"player": "each_opponent", "objects": LANDS}}
FEWEST = {"min_count_of": {"player": "each_opponent", "objects": LANDS}}
ANYBODY = {"max_count_of": {"player": "each_player", "objects": LANDS}}
#: The near miss, and the whole reason for the leaf: one merged pool.
POOLED = {"count": {"zone": "battlefield", "controller": "opponent", "types": ["Land"]}}


def value(game, expr, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), expr)


def table(builder, *lands_each: int):
    """A position with ``lands_each[pid]`` Forests in front of each seat."""
    b = builder(players=len(lands_each))
    for pid, count in enumerate(lands_each):
        if count:
            b.battlefield(pid, [FOREST] * count)
    return b.build(advance=False)


class TestOnePlayerAtATime:
    def test_a_duel_agrees_with_the_pooled_count(self, builder):
        """With one opponent there is nothing to pool, so both readings match."""
        game = table(builder, 3, 5)
        assert value(game, MOST) == 5
        assert value(game, POOLED) == 5

    def test_a_pod_does_not(self, builder):
        """The claim. Nobody is ahead of your five; the sum says somebody is."""
        game = table(builder, 5, 2, 2, 2)
        assert value(game, MOST) == 2, "the most any one opponent controls"
        assert value(game, POOLED) == 6, "…and the summed reading, for contrast"
        assert value(game, MOST) <= 5, "so 'an opponent controls more' is false"
        assert value(game, POOLED) > 5, "which the pooled count gets backwards"

    def test_it_finds_the_one_opponent_who_is_ahead(self, builder):
        game = table(builder, 5, 1, 6, 1)
        assert value(game, MOST) == 6

    def test_your_own_lands_are_not_in_it(self, builder):
        """It is the right-hand side of the comparison, not part of the left."""
        game = table(builder, 30, 2)
        assert value(game, MOST) == 2

    def test_each_player_includes_you(self, builder):
        """"…more than each other player" needs the whole table in the pool."""
        game = table(builder, 7, 2, 2)
        assert value(game, ANYBODY) == 7

    def test_an_opponent_with_no_lands_counts_as_zero(self, builder):
        game = table(builder, 1, 0)
        assert value(game, MOST) == 0

    def test_only_matching_objects_are_counted(self, builder):
        """The filter still filters -- a creature is not a land."""
        game = builder(players=2).battlefield(1, [FOREST, "t_bear", "t_bear"]).build(
            advance=False
        )
        assert value(game, MOST) == 1


class TestTheTwoAggregations:
    def test_the_fewest_is_the_universal(self, builder):
        """"Each opponent controls more lands than you" -- true only of the lowest."""
        game = table(builder, 5, 6, 7, 8)
        assert value(game, FEWEST) == 6, "so 'each opponent controls more' holds"

    def test_one_opponent_behind_breaks_the_universal(self, builder):
        game = table(builder, 5, 6, 7, 1)
        assert value(game, FEWEST) == 1
        assert value(game, MOST) == 7, "…while the existential still holds"

    def test_the_existential_over_nobody_is_zero(self, builder):
        """"An opponent controls more lands than you" must be **false** alone."""
        game = table(builder, 4)
        assert value(game, MOST) == 0
        assert value(game, MOST) <= 4

    def test_the_universal_over_nobody_is_unreachable(self, builder):
        """The `min_life_of` bias, in the same direction and for the same reason.

        "Each opponent controls more lands than you" over an empty set is
        vacuously true, and a minimum of 0 would report the opposite -- that
        every opponent is behind you -- at the moment the last one died.
        """
        game = table(builder, 4)
        assert value(game, FEWEST) == NO_PLAYERS_COUNT


class TestZonesSomebodyOwns:
    """The battlefield is shared and a hand is not, so the scope is injected
    differently -- as a `controller` filter over the one pool, or as a choice of
    whose list to walk. Both spellings have to reach the same answer."""

    def hands(self, builder, *sizes: int):
        b = builder(players=len(sizes))
        for pid, size in enumerate(sizes):
            b.hand(pid, [FOREST] * size)
        return b.build(advance=False)

    def test_it_reads_the_fullest_hand(self, builder):
        game = self.hands(builder, 0, 2, 4, 1)
        expr = {"max_count_of": {"player": "each_opponent", "objects": {"zone": "hand"}}}
        assert value(game, expr) == 4

    def test_it_reads_the_emptiest_hand(self, builder):
        game = self.hands(builder, 0, 2, 4, 1)
        expr = {"min_count_of": {"player": "each_opponent", "objects": {"zone": "hand"}}}
        assert value(game, expr) == 1

    def test_cards_in_hand_sums_the_same_board(self, builder):
        """The existing leaf, for contrast: seven where no hand holds seven."""
        game = self.hands(builder, 0, 2, 4, 1)
        assert value(game, {"cards_in_hand": "each_opponent"}) == 7


class TestTheInterveningIf:
    """Knight of the White Orchid -- rule 603.4."""

    def position(self, builder, mine: int, theirs: int):
        return (
            builder(players=2)
            .battlefield(0, [PLAINS] * mine)
            .battlefield(1, [FOREST] * theirs)
            .hand(0, [KNIGHT])
            .library(0, [PLAINS] + [FOREST] * 10)
            .active(0)
            .max_turns(1)
            .build()
        )

    def cast_knight(self, game):
        """Cast it and take every offer -- the search is a "you may"."""
        game.apply(action_for_card(game, ActionKind.CAST, KNIGHT))
        for _ in range(40):
            decision = game.pending()
            if decision is None:
                return
            actions = game.legal_actions()
            if decision.kind is DecisionKind.MAY:
                game.apply(find_action(game, ActionKind.YES))
                continue
            if decision.kind is DecisionKind.CHOOSE_OBJECTS:
                choices = [a for a in actions if a.kind is ActionKind.CHOOSE]
                game.apply(choices[0] if choices else actions[0])
                continue
            if not game.state.pending_triggers and not game.state.stack:
                return
            passes = [a for a in actions if a.kind is ActionKind.PASS]
            if not passes:
                return
            game.apply(passes[0])

    def plains(self, game) -> int:
        """Plains you control -- the Knight's own board starts with some."""
        return sum(
            1
            for o in game.state.battlefield_objects(0)
            if game.state.card_of(game.state.objects[o.oid]).id == PLAINS
        )

    def play(self, game) -> tuple[int, int]:
        """Cast the Knight; return the change in Plains and in library size."""
        plains_before, library_before = self.plains(game), len(game.state.players[0].library)
        self.cast_knight(game)
        return (
            self.plains(game) - plains_before,
            len(game.state.players[0].library) - library_before,
        )

    def test_behind_on_lands_it_fetches(self, builder):
        game = self.position(builder, 2, 5)
        assert self.play(game) == (1, -1), "an opponent is ahead, so the trigger resolves"

    def test_ahead_on_lands_it_does_nothing(self, builder):
        """The gate, and the half a `count` implementation would still pass."""
        game = self.position(builder, 2, 1)
        assert self.play(game) == (0, 0)

    def test_level_on_lands_it_does_nothing(self, builder):
        """"More than" is strict: equal land counts are not behind."""
        game = self.position(builder, 2, 2)
        assert self.play(game) == (0, 0)

    def test_a_pod_where_only_the_sum_is_ahead_does_nothing(self, builder):
        """Three opponents on two lands each. The Knight stays a 2/2."""
        game = (
            builder(players=4)
            .battlefield(0, [PLAINS] * 3)
            .battlefield(1, [FOREST] * 2)
            .battlefield(2, [FOREST] * 2)
            .battlefield(3, [FOREST] * 2)
            .hand(0, [KNIGHT])
            .library(0, [PLAINS] + [FOREST] * 10)
            .active(0)
            .max_turns(1)
            .build()
        )
        assert self.play(game) == (0, 0), "six pooled lands are not one opponent's six"


class TestTheActivationRestriction:
    """Weathered Wayfarer -- rule 602.5c, asked at activation and nowhere else."""

    def position(self, builder, mine: int, *theirs: int):
        b = builder(players=1 + len(theirs))
        b.battlefield(0, [WAYFARER] + [PLAINS] * mine)
        for pid, count in enumerate(theirs, start=1):
            b.battlefield(pid, [FOREST] * count)
        b.library(0, [FOREST] * 10).active(0).max_turns(2)
        return b.build()

    def offered(self, game) -> bool:
        wayfarer = only_oid(game, WAYFARER)
        return any(
            a.kind is ActionKind.ACTIVATE and a.source == wayfarer
            for a in game.legal_actions()
        )

    def test_behind_on_lands_it_is_offered(self, builder):
        game = self.position(builder, 2, 5)
        assert self.offered(game)

    def test_ahead_on_lands_it_is_not(self, builder):
        game = self.position(builder, 5, 2)
        assert not self.offered(game)

    def test_level_on_lands_it_is_not(self, builder):
        game = self.position(builder, 3, 3)
        assert not self.offered(game)

    def test_a_pod_where_only_the_sum_is_ahead_does_not_offer_it(self, builder):
        """The pooled reading makes this the strongest one-drop in the format."""
        game = self.position(builder, 5, 2, 2, 2)
        assert not self.offered(game)

    def test_taking_it_finds_a_land(self, builder):
        """The gate is the only new part, so the tutor is checked once."""
        game = self.position(builder, 2, 5)
        before = len(game.state.players[0].hand)
        game.apply(
            find_action(game, ActionKind.ACTIVATE, source=only_oid(game, WAYFARER))
        )
        for _ in range(40):
            decision = game.pending()
            if decision is None:
                break
            if decision.kind is DecisionKind.CHOOSE_OBJECTS:
                choices = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
                if choices:
                    game.apply(choices[0])
                    continue
            if not game.state.stack:
                break
            passes = [a for a in game.legal_actions() if a.kind is ActionKind.PASS]
            if not passes:
                break
            game.apply(passes[0])

        assert len(game.state.players[0].hand) == before + 1


class TestInsideAStatic:
    """The mirror condition language, which is a separate implementation."""

    def watcher(self, builder, mine: int, *theirs: int):
        b = builder(players=1 + len(theirs))
        b.battlefield(0, [WATCHER] + [PLAINS] * mine)
        for pid, count in enumerate(theirs, start=1):
            b.battlefield(pid, [FOREST] * count)
        game = b.build(advance=False)
        return game, only_oid(game, WATCHER)

    def test_behind_on_lands_the_static_is_on(self, builder):
        game, oid = self.watcher(builder, 2, 5)
        assert "flying" in chars(game.state, oid).keywords

    def test_ahead_on_lands_it_is_off(self, builder):
        game, oid = self.watcher(builder, 5, 2)
        assert "flying" not in chars(game.state, oid).keywords

    def test_a_pod_where_only_the_sum_is_ahead_leaves_it_off(self, builder):
        game, oid = self.watcher(builder, 5, 2, 2, 2)
        assert "flying" not in chars(game.state, oid).keywords

    def test_it_switches_off_when_the_board_moves(self, builder):
        """An "as long as" clause is re-read, not latched."""
        from automtg.engine.zones import destroy

        game, oid = self.watcher(builder, 2, 3)
        assert "flying" in chars(game.state, oid).keywords

        for land in list(game.state.battlefield_objects(1))[:2]:
            destroy(game.state, land.oid)
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        assert "flying" not in chars(game.state, oid).keywords


class TestTheGuards:
    """A misspelling has to be a load error. Read as 0 the gate stands open."""

    def test_both_languages_accept_a_well_formed_leaf(self):
        validate_value(MOST, "test")
        _validate_static_value(MOST, "test")

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(DslError, match="unknown value keys"):
            validate_value({"max_count_off": {"player": "you", "objects": LANDS}}, "test")

    def test_a_missing_player_is_refused(self):
        """"each_opponent" and "each_player" are different cards."""
        with pytest.raises(DslError, match="must name one of"):
            validate_value({"max_count_of": {"objects": LANDS}}, "test")

    def test_an_unknown_player_is_refused(self):
        with pytest.raises(DslError, match="must name one of"):
            validate_value(
                {"max_count_of": {"player": "each_teammate", "objects": LANDS}}, "test"
            )

    def test_a_missing_objects_is_refused(self):
        with pytest.raises(DslError, match="needs 'objects'"):
            validate_value({"max_count_of": {"player": "each_opponent"}}, "test")

    def test_a_controller_clause_inside_objects_is_refused(self):
        """It is the summing filter the leaf replaces, and it would be overwritten."""
        with pytest.raises(DslError, match="injected per player"):
            validate_value(
                {
                    "max_count_of": {
                        "player": "each_opponent",
                        "objects": {"types": ["Land"], "controller": "opponent"},
                    }
                },
                "test",
            )

    def test_a_player_clause_inside_objects_is_refused(self):
        with pytest.raises(DslError, match="injected per player"):
            validate_value(
                {
                    "min_count_of": {
                        "player": "each_opponent",
                        "objects": {"zone": "graveyard", "player": "you"},
                    }
                },
                "test",
            )

    def test_the_filter_is_still_validated(self):
        with pytest.raises(DslError, match="unknown card type"):
            validate_value(
                {"max_count_of": {"player": "each_opponent", "objects": {"types": ["Lnad"]}}},
                "test",
            )

    def test_the_static_language_refuses_it_too(self):
        with pytest.raises(DslError, match="must name one of"):
            _validate_static_value({"max_count_of": {"objects": LANDS}}, "test")

    def test_the_static_language_applies_its_own_filter_rules(self):
        """Off the battlefield a card has a printed face and an owner, no more."""
        with pytest.raises(DslError, match="unsupported keys"):
            _validate_static_value(
                {
                    "max_count_of": {
                        "player": "each_opponent",
                        "objects": {"zone": "graveyard", "tapped": True},
                    }
                },
                "test",
            )


class TestTheShippedCards:
    def test_the_knight_asks_about_one_opponent(self, registry):
        card = registry.get(KNIGHT)
        trigger = next(a.trigger for a in card.abilities if a.trigger is not None)
        assert "max_count_of" in str(trigger.condition), "not a pooled `count`"

    def test_the_wayfarer_asks_at_activation(self, registry):
        card = registry.get(WAYFARER)
        ability = next(a for a in card.abilities if a.kind == "activated")
        assert "max_count_of" in str(ability.activation_condition)

    def test_the_knight_is_still_a_first_striker(self, registry):
        """The printed first line, which no gate about the second would catch."""
        assert "first_strike" in {str(k) for k in registry.get(KNIGHT).keywords}
