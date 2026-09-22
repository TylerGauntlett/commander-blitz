"""A casting prohibition with a zone filter and a clock, installed by a sorcery.

    Until your next turn, your opponents can't cast spells from anywhere other
    than their hands.

Three things at once, and the engine had no piece with more than one of them.

**The filter.** `cant_cast_spells`, the player-wide static, is total on
purpose: `cards/loader/__init__.py` raises a `DslError` if an `affects` or an
`amount` appears beside it, precisely so a narrower printed line cannot load as
a strictly stronger lock. Written bare here it would shut the opponents' *hand*
casts too -- a far harsher card than the printed one, and silently harsher,
which is the worst way for a card to be wrong. So the lock names zones, and the
test that matters is the one that keeps a hand cast legal in the same breath
that it refuses a graveyard cast. `t_ember_recall` is a flashback instant so
that both lines belong to one card in one position: nothing about the card
separates them, only where it is.

**The clock.** "Until **your** next turn" is not "this turn": at a table of
two, the locked opponent takes a whole turn in between, and an implementation
that expired at cleanup would hand it back a turn early. It is keyed to the
*caster's* seat and never to a turn number, the choice detain, goad, block
prohibitions, player protections and life locks all made, and for their reason
-- eliminate a player and everybody's "next turn" moves.

**The installer.** A sorcery leaves no permanent behind to carry a static, and
`set_turn_flag` is inert: no legality path reads `has_turn_flag`. So the lock
is a row in a timed table (`structs.CastLock`) beside the life lock, read back
by `primitives.cast_locked_zones` on the three roads a cast can take that
ask a zone at all.

Witness: Avatar's Wrath (`data/authoring/answers/avatar_s_wrath.json`), whose
second line this is. Without it the card is either missing a sentence or
carrying one three times as harsh.
"""

from __future__ import annotations

from automtg.engine.casting import _cast_actions
from automtg.engine.enums import ActionKind, Step
from tests.conftest import pass_until

DECREE = "t_hand_only_decree"  # {0} sorcery: opponents cast from hands only
GRAVE_ONLY = "t_total_silence_decree"  # {0} sorcery: opponents cast from no graveyard
RECALL = "t_ember_recall"  # {R} instant with flashback {R} -- hand and graveyard at once
WARDEN = "t_ashen_warden"  # {R} 1/1, the commander


def board(builder, *, spell=DECREE, caster_graveyard=False):
    """p0 holds a free decree; p1 holds a Recall, has one in the yard and a commander.

    p1 is given Mountains enough for any of the three lines, so every refusal
    below is the lock's and not the mana's.
    """
    b = (
        builder(players=2)
        .hand(0, [spell])
        .battlefield(0, ["mountain"] * 3)
        .hand(1, [RECALL])
        .graveyard(1, [RECALL])
        .commander(1, [WARDEN])
        .battlefield(1, ["mountain"] * 3)
        .step(Step.PRECOMBAT_MAIN)
    )
    if caster_graveyard:
        # The lock names the opponents, so the caster's own graveyard has to
        # stay open -- "**your opponents** can't cast".
        b = b.graveyard(0, [RECALL])
    return b.build()


def cast_decree(game, spell=DECREE):
    oid = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == spell)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid)
    )
    for _ in range(4):
        if not game.state.stack:
            break
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    return game


def lines(game, pid, zone):
    """Every cast line offered to ``pid`` for a card sitting in ``zone``.

    `_cast_actions` rather than `game.legal_actions()`, because the interesting
    seat is usually the one without priority -- and because the claim is about
    what legality *builds*, which is where the gate lives. Asked with the
    sorcery window open so that the commander, a creature, is a line at all:
    the gate under test reads the zone and nothing else, and a test that could
    only see instants would leave two of the three zones unmeasured.
    """
    return [
        a
        for a in _cast_actions(game.state, pid, sorcery_speed=True)
        if game.state.objects[a.source].zone.value == zone
    ]


def setup(builder, **kw):
    return cast_decree(board(builder, **kw), kw.get("spell", DECREE))


class TestTheHandStaysOpenWhileTheOtherZonesShut:
    """"…from anywhere **other than their hands**", which `cant_cast_spells` can't say."""

    def test_the_locked_player_may_still_cast_from_hand(self, builder):
        game = setup(builder)
        assert len(lines(game, 1, "hand")) == 1

    def test_the_locked_player_may_not_flash_a_card_back(self, builder):
        # The same card, in the other zone. Nothing about `t_ember_recall`
        # separates these two lines except where the copy is sitting, which is
        # the whole of what this lock reads.
        game = setup(builder)
        assert lines(game, 1, "graveyard") == []

    def test_the_locked_player_may_not_cast_their_commander(self, builder):
        game = setup(builder)
        assert lines(game, 1, "command") == []

    def test_without_the_lock_all_three_lines_exist(self, builder):
        game = board(builder)
        assert len(lines(game, 1, "hand")) == 1
        assert len(lines(game, 1, "graveyard")) == 1
        assert len(lines(game, 1, "command")) == 1

    def test_the_caster_is_not_locked(self, builder):
        # "**Your opponents** can't cast." p0 flashes the same card back out of
        # p0's own graveyard while p1 cannot.
        game = setup(builder, caster_graveyard=True)
        assert len(lines(game, 0, "graveyard")) == 1
        assert lines(game, 1, "graveyard") == []

    def test_a_narrower_lock_shuts_only_what_it_names(self, builder):
        # The positive `zones` spelling, so that the inverse one above is not
        # the only shape with a test. A lock naming the graveyard alone leaves
        # the command zone open.
        game = setup(builder, spell=GRAVE_ONLY)
        assert lines(game, 1, "graveyard") == []
        assert len(lines(game, 1, "command")) == 1
        assert len(lines(game, 1, "hand")) == 1


class TestItExpiresAtTheCastersNextTurnAndNotBefore:
    """"Until **your** next turn" -- the caster's, which is a turn later."""

    def test_it_holds_through_the_locked_players_whole_turn(self, builder):
        # The boundary that separates this from `this_turn`. p1 takes an entire
        # turn under the lock; an implementation that expired at cleanup would
        # have handed the graveyard back at the start of it.
        game = setup(builder)
        start = game.state.turn
        pass_until(game, lambda g: g.state.turn == start + 1)
        assert game.state.active_player == 1
        assert lines(game, 1, "graveyard") == []

    def test_it_is_gone_by_the_casters_next_turn(self, builder):
        game = setup(builder)
        start = game.state.turn
        pass_until(game, lambda g: g.state.turn == start + 2)
        assert game.state.active_player == 0
        assert len(lines(game, 1, "graveyard")) == 1

    def test_the_table_is_empty_afterwards(self, builder):
        # Cleared rather than merely ignored: a row nothing sweeps is a
        # prohibition that answers True for the rest of the game.
        game = setup(builder)
        assert len(game.state.cast_locks) == 1
        start = game.state.turn
        pass_until(game, lambda g: g.state.turn == start + 2)
        assert game.state.cast_locks == []
