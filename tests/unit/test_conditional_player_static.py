""""As long as…" on a static that describes a *player* rather than a permanent.

Rule 604.3: a static ability with a condition is a continuous effect that exists
whenever the condition is met and stops existing the instant it is not. That is
already pinned for the statics the characteristics pipeline reads --
`test_static_condition.py` is where Nimble Mongoose lives. This file pins it for
the other eight, the ones that take `affects_player` and describe the player:
`no_hand_limit`, `extra_land_drops`, `play_lands_from_graveyard`,
`play_lands_from_library_top`, `reveal_library_top`, `double_land_triggers`,
`double_land_mana` and `freeze_opponent_lands`.

**This was a silent over-grant, not a missing feature.** The loader validated a
`condition` on any static and stored it on the ability. But `_static_active` had
exactly one call site, `_battlefield_statics`, which feeds only the
object-characteristics pipeline; the four hand-rolled walks that read the
player-wide effects matched on `effect` and `affects_player` and never asked. So
a card could load clean, print its "as long as" clause, pass every gate looking
correct, and grant the permission **unconditionally**. A permission that is
always on is strictly better than the printed card, and nothing in the suite
would have said so -- which is why :class:`TestTheGateWithholds` is the class
this file exists for, and why every claim here is asserted in both directions.

**Verge Rangers is the witness** -- "As long as an opponent controls more lands
than you, you may play lands from the top of your library." Written before the
gate existed it would have been Oracle of Mul Daya's unconditional permission
stapled to a 3/2 first striker, switched on while you are the one ahead. No
shipped card carried a condition on a player-wide static when the gate landed,
so nothing was playing wrong; `TestTheUngatedStaticsAreUntouched` is the guard
that keeps the fourteen that carry none reading exactly as they did.

`t_verge_scout` and `t_conditional_ramp` carry the Verge Rangers clause, which
reaches through the board. `t_all_player_statics` carries all eight gated on
`is_your_turn`, so :class:`TestEveryPlayerWideStatic` can walk every reader --
one per effect -- rather than trusting that a fix to two of them reached the
other six.
"""

from __future__ import annotations

import pytest

from automtg.engine.characteristics import (
    player_doubles_land_mana,
    player_extra_land_drops,
    player_has_no_hand_limit,
    player_plays_lands_from_graveyard,
    player_plays_lands_from_library_top,
    player_reveals_library_top,
    players_doubling_land_triggers,
    players_freezing_opponent_lands,
)
from automtg.engine.enums import ActionKind
from tests.conftest import only_oid

FOREST = "forest"
PLAINS = "plains"
BEAR = "t_bear"

#: "…you may play lands from the top of your library", gated on Verge Rangers'
#: own clause.
SCOUT = "t_verge_scout"
#: The same clause switching an *amount* rather than a permission.
RAMP = "t_conditional_ramp"
#: All eight player-wide effects at once, gated on `is_your_turn`.
EVERY = "t_all_player_statics"

#: The shipped cards that carry the same effects with **no** condition.
ORACLE = "oracle_of_mul_daya"
TOWER = "reliquary_tower"


def table(builder, card: str, mine: int, *theirs: int, **kwargs):
    """``card`` and ``mine`` Plains for seat 0, ``theirs[i]`` Forests per opponent.

    Seat 0's library is all Forests, so "is the top card offered?" is only ever
    a question about the permission -- never about what happens to be on top.
    """
    b = builder(players=1 + len(theirs))
    b.battlefield(0, [card] + [PLAINS] * mine)
    for pid, count in enumerate(theirs, start=1):
        b.battlefield(pid, [FOREST] * count)
    b.library(0, [FOREST] * 10).active(0).max_turns(1)
    for key, value in kwargs.items():
        getattr(b, key)(0, value)
    return b.build()


def top_offered(game, pid: int = 0) -> bool:
    """Is the top card of ``pid``'s library offered as a land drop?"""
    top = game.state.players[pid].library[0]
    return any(
        a.kind is ActionKind.PLAY_LAND and a.source == top for a in game.legal_actions()
    )


def hand_land_offered(game, pid: int = 0) -> bool:
    hand = set(game.state.players[pid].hand)
    return any(a.kind is ActionKind.PLAY_LAND and a.source in hand for a in game.legal_actions())


class TestTheGateHolds:
    """Behind on lands, the permission is granted -- the printed card."""

    def test_the_reader_says_yes(self, builder):
        game = table(builder, SCOUT, 2, 5, hand=[PLAINS])
        assert player_plays_lands_from_library_top(game.state, 0)

    def test_the_top_card_is_offered(self, builder):
        game = table(builder, SCOUT, 2, 5, hand=[PLAINS])
        assert top_offered(game)

    def test_playing_it_puts_the_land_onto_the_battlefield(self, builder):
        """The permission has to reach `apply`, not only `legal_actions`."""
        game = table(builder, SCOUT, 2, 5, hand=[PLAINS])
        top = game.state.players[0].library[0]
        before = len(game.state.players[0].library)

        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.PLAY_LAND and a.source == top
            )
        )

        assert top in game.state.battlefield
        assert len(game.state.players[0].library) == before - 1


class TestTheGateWithholds:
    """The half that silently failed: the permission is **not** granted.

    Every assertion here passed before the fix for the wrong reason -- the
    permission was on in all of them, and only the "behind on lands" tests were
    ever written.
    """

    def test_ahead_on_lands_the_reader_says_no(self, builder):
        game = table(builder, SCOUT, 5, 2, hand=[PLAINS])
        assert not player_plays_lands_from_library_top(game.state, 0)

    def test_ahead_on_lands_the_top_card_is_not_offered(self, builder):
        game = table(builder, SCOUT, 5, 2, hand=[PLAINS])
        assert not top_offered(game)
        assert hand_land_offered(game), "…while the ordinary land drop is untouched"

    def test_level_on_lands_it_is_not_offered(self, builder):
        """"More than" is strict -- equal land counts are not behind."""
        game = table(builder, SCOUT, 3, 3, hand=[PLAINS])
        assert not top_offered(game)

    def test_a_pod_where_only_the_sum_is_ahead_does_not_offer_it(self, builder):
        """Three opponents on two lands each do not add up to one opponent."""
        game = table(builder, SCOUT, 5, 2, 2, 2, hand=[PLAINS])
        assert not player_plays_lands_from_library_top(game.state, 0)
        assert not top_offered(game)

    def test_the_opponent_never_gets_the_permission(self, builder):
        """`affects_player: "you"` still scopes it, gate or no gate."""
        game = table(builder, SCOUT, 2, 5, hand=[PLAINS])
        assert not player_plays_lands_from_library_top(game.state, 1)


class TestItSwitchesWithTheBoard:
    """An "as long as…" clause is re-read, not latched at any moment."""

    def test_it_switches_off_when_the_opponent_loses_lands(self, builder):
        from automtg.engine.zones import destroy

        game = table(builder, SCOUT, 2, 4, hand=[PLAINS])
        assert top_offered(game), "an opponent is ahead four lands to two"

        for land in list(game.state.battlefield_objects(1))[:3]:
            destroy(game.state, land.oid)

        assert not top_offered(game), "one land to two -- nobody is ahead"

    def test_it_switches_on_when_the_opponent_gains_lands(self, builder):
        from automtg.engine.enums import Zone
        from automtg.engine.state import new_object

        game = table(builder, SCOUT, 3, 3, hand=[PLAINS])
        assert not top_offered(game), "level on lands"

        obj = new_object(game.state, FOREST, owner=1, zone=Zone.BATTLEFIELD)
        game.state.battlefield.append(obj.oid)
        game.state.bump_chars()

        assert top_offered(game), "four to three -- the permission arrives"

    def test_it_switches_off_when_its_own_source_leaves(self, builder):
        """The gate is additional to the source being on the battlefield."""
        from automtg.engine.zones import destroy

        game = table(builder, SCOUT, 2, 5, hand=[PLAINS])
        assert top_offered(game)

        destroy(game.state, only_oid(game, SCOUT))

        assert not top_offered(game)


class TestTheAmount:
    """`extra_land_drops` is the one gated static that switches a *number*."""

    def test_behind_on_lands_it_grants_the_drop(self, builder):
        game = table(builder, RAMP, 2, 5, hand=[PLAINS])
        assert player_extra_land_drops(game.state, 0) == 1

    def test_ahead_on_lands_it_grants_nothing(self, builder):
        """Zero rather than one -- a switched-off amount is not a small amount."""
        game = table(builder, RAMP, 5, 2, hand=[PLAINS])
        assert player_extra_land_drops(game.state, 0) == 0

    def test_the_second_land_drop_is_offered_only_while_it_holds(self, builder):
        """Through `costs.land_drops_available`, which prices the real action."""
        from automtg.engine.costs import land_drops_available

        behind = table(builder, RAMP, 2, 5, hand=[PLAINS], lands_played=1)
        assert land_drops_available(behind.state, 0) == 1
        assert hand_land_offered(behind)

        ahead = table(builder, RAMP, 5, 2, hand=[PLAINS], lands_played=1)
        assert land_drops_available(ahead.state, 0) == 0
        assert not hand_land_offered(ahead)


#: One probe per player-wide static effect: ``(effect, reader)``, where the
#: reader answers "is it switched on for seat 0?".  Written as a table rather
#: than eight test methods because the claim is the same claim eight times, and
#: an effect added to the loader's player-wide list and not to this table should
#: read as a missing row.
READERS = [
    ("no_hand_limit", lambda state: player_has_no_hand_limit(state, 0)),
    ("extra_land_drops", lambda state: player_extra_land_drops(state, 0) > 0),
    ("play_lands_from_graveyard", lambda state: player_plays_lands_from_graveyard(state, 0)),
    (
        "play_lands_from_library_top",
        lambda state: player_plays_lands_from_library_top(state, 0),
    ),
    ("reveal_library_top", lambda state: player_reveals_library_top(state, 0)),
    ("double_land_triggers", lambda state: 0 in players_doubling_land_triggers(state)),
    ("double_land_mana", lambda state: player_doubles_land_mana(state, 0)),
    ("freeze_opponent_lands", lambda state: 0 in players_freezing_opponent_lands(state)),
]


class TestEveryPlayerWideStatic:
    """All eight, gated on `is_your_turn`, read through their own readers.

    Two of them (`freeze_opponent_lands`, `double_land_triggers`) are asked as a
    *set of players* rather than per player, and they were separate walks -- so
    fixing `_player_static` alone would have left them granting unconditionally.
    """

    def position(self, builder, active: int):
        return (
            builder(players=2)
            .battlefield(0, [EVERY, PLAINS])
            .battlefield(1, [FOREST])
            .active(active)
            .build(advance=False)
        )

    @pytest.mark.parametrize("effect,reader", READERS, ids=[e for e, _ in READERS])
    def test_it_is_on_while_the_condition_holds(self, builder, effect, reader):
        game = self.position(builder, active=0)
        assert reader(game.state), f"{effect} should be on during its controller's turn"

    @pytest.mark.parametrize("effect,reader", READERS, ids=[e for e, _ in READERS])
    def test_it_is_off_while_the_condition_does_not(self, builder, effect, reader):
        """The silent-over-grant case, once per effect."""
        game = self.position(builder, active=1)
        assert not reader(game.state), f"{effect} should be off on someone else's turn"

    def test_the_table_covers_every_gated_effect_on_the_card(self, registry):
        """A ninth player-wide effect must not be able to slip in ungated."""
        card = registry.get(EVERY)
        on_card = {
            a.static["effect"] for a in card.abilities if a.is_static and a.static
        }
        assert on_card == {effect for effect, _ in READERS}


class TestSerializationFollowsTheGate:
    """`reveal_library_top` changes no rule -- it decides what the seats see."""

    def library_top_visible(self, game) -> bool:
        from automtg.engine.serialize import player_view

        # Read from the *opponent's* seat: `library_top` is public whenever it is
        # sent at all, so the seat that must stop seeing it is seat 1.
        return player_view(game.state, 1)["players"][0]["library_top"] is not None

    def test_visible_while_the_condition_holds(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [EVERY])
            .library(0, [FOREST] * 5)
            .active(0)
            .build(advance=False)
        )
        assert self.library_top_visible(game)

    def test_hidden_while_it_does_not(self, builder):
        """A card the opponent may no longer see has to stop being sent."""
        game = (
            builder(players=2)
            .battlefield(0, [EVERY])
            .library(0, [FOREST] * 5)
            .active(1)
            .build(advance=False)
        )
        assert not self.library_top_visible(game)


class TestTheUngatedStaticsAreUntouched:
    """No shipped card carried a condition on a player-wide static.

    So the gate changed no card's behaviour, and these are the assertions that
    say so: a static with no `condition` is unconditionally on, exactly as
    before, and `_static_active` returns True for it without evaluating
    anything.
    """

    def test_oracle_of_mul_daya_still_plays_off_the_top(self, builder):
        game = table(builder, ORACLE, 5, 2, hand=[PLAINS])
        assert player_plays_lands_from_library_top(game.state, 0)
        assert top_offered(game), "ahead on lands, and still unconditional"

    def test_oracle_of_mul_daya_still_grants_its_extra_drop(self, builder):
        game = table(builder, ORACLE, 5, 2, hand=[PLAINS])
        assert player_extra_land_drops(game.state, 0) == 1

    def test_reliquary_tower_still_lifts_the_hand_limit(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["reliquary_tower"])
            .build(advance=False)
        )
        assert player_has_no_hand_limit(game.state, 0)

    def test_no_shipped_card_gates_a_player_wide_static(self, real_registry):
        """The claim behind "nothing was playing wrong", asserted on the pool.

        If this ever fails, a card has been authored with a gated player-wide
        static -- which is now correct behaviour rather than a silent
        over-grant, and this test should be retired with a note naming the card.
        """
        gated = [
            (card.id, ability.static["effect"])
            for card in real_registry
            for ability in card.abilities
            if ability.is_static
            and ability.static
            and ability.static.get("affects_player") is not None
            and ability.static.get("condition") is not None
        ]
        assert gated == []


class TestTheTwoHalvesCannotDrift:
    def test_the_loader_keeps_the_condition_on_a_player_wide_static(self, registry):
        """It always did -- and that was the bug, because nothing read it."""
        card = registry.get(SCOUT)
        static = next(a.static for a in card.abilities if a.is_static and a.static)
        assert static["effect"] == "play_lands_from_library_top"
        assert "max_count_of" in str(static["condition"])

    def test_an_unconditional_player_wide_static_stores_no_condition(self, registry):
        card = registry.get(ORACLE)
        for ability in card.abilities:
            if ability.is_static and ability.static:
                assert "condition" not in ability.static
