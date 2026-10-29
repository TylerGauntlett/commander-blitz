""""As long as an opponent has cast a spell this turn": `spells_cast_this_turn` in a static.

    "Cosmic Awareness -- **As long as an opponent has cast a spell this turn**,
    you may cast spells as though they had flash."
                                          -- Captain Mar-Vell, Space-Born

Rule 604.3: a static ability with a condition exists whenever the condition is
met and not otherwise. The condition here is a fact about the turn, not the
board, so it is read off `TurnLedger.spells_cast` -- the per-seat count storm
reads on the effect side -- which `GameState._tally` writes off every SPELL_CAST
whatever was watching, so a spell cast before the Captain arrived counts too.
A `spell_cast` trigger setting a flag would be an unprinted ability and would
miss exactly that spell.

It is admissible in a static under ADR 0001 because it is a pipeline **input**:
no layer writes the ledger, only the cast fold and the cleanup step do, and
both bump `char_version` so a cached answer cannot outlive either. That is what
`TestALayeredReaderSeesItToo` pins, on a buff that reads the same leaf.

What each reading rests on, and each has a test class:

- **Before any opponent casts**, the static does not exist: no sorcery-speed
  spell is offered outside the sorcery window.
- **After an opponent casts**, you may cast a sorcery at instant speed -- in
  response to that very spell, after it resolves, and on your own turn in a
  step that is not a main phase.
- **"An opponent"** -- your own casts do not turn it on, and in a pod any one
  opponent's cast is enough.
- **"This turn"** -- the ledger is emptied at cleanup, so the permission ends
  with the turn the spell was cast in.

Captain Mar-Vell, Space-Born is the witness; `t_ssct_awareness` in
`tests/data/static_spells_cast_this_turn.cards.json` is its Cosmic Awareness on
a {4} artifact.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import legality
from commanderblitz.engine import turn as turn_module
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.player_statics import player_casts_as_though_flash
from tests.conftest import (
    action_for_card,
    find_action,
    only_oid,
    pass_until,
    pt,
    settle,
    static_probe,
)

AWARENESS = "t_ssct_awareness"  # you: flash while an opponent has cast a spell this turn
BRAWLER = "t_ssct_brawler"  # 1/1, +2/+0 under the same condition
SORCERY = "t_sorcery"  # {R} sorcery, no flash of its own
BOLT = "t_bolt"  # {R} instant, so an opponent can cast on your turn
MOUNTAIN = "mountain"


def position(
    builder,
    *,
    players: int = 2,
    active: int = 0,
    step: Step = Step.PRECOMBAT_MAIN,
    hand0: tuple[str, ...] = (SORCERY,),
    theirs: tuple[str, ...] = (SORCERY,),
    mine: tuple[str, ...] = (AWARENESS,),
    advance: bool = True,
):
    """Player 0 controls the Awareness; every other seat holds ``theirs``.

    Everyone has Mountains, so the only thing that can withhold a cast is the
    timing window. ``active`` is whose turn it is. ``advance=False`` freezes the
    position in ``step``; otherwise the engine auto-passes to the first player
    with something to do, which is how a spell is cast and answered here.
    """
    b = builder(players=players).battlefield(0, [MOUNTAIN] * 3 + list(mine)).hand(0, list(hand0))
    b = b.library(0, ["forest"] * 10)
    for pid in range(1, players):
        b = b.battlefield(pid, [MOUNTAIN] * 3).hand(pid, list(theirs)).library(pid, ["forest"] * 10)
    return b.step(step).active(active).build(advance=advance)


def can_cast(game, pid: int, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in legality._priority_actions(game.state, pid)
    )


def cast(game, card_id: str) -> None:
    """The player with priority casts ``card_id``; it stays on the stack."""
    game.apply(action_for_card(game, ActionKind.CAST, card_id))


def flash(game, pid: int = 0) -> bool:
    return player_casts_as_though_flash(game.state, pid)


class TestBeforeAnOpponentCasts:
    def test_no_sorcery_on_the_opponents_turn(self, builder):
        game = position(builder, active=1, advance=False)
        assert not flash(game)
        assert not can_cast(game, 0, SORCERY)

    def test_nor_outside_a_main_phase_on_your_own(self, builder):
        game = position(builder, active=0, step=Step.BEGIN_COMBAT, advance=False)
        assert not flash(game)
        assert not can_cast(game, 0, SORCERY)

    def test_the_sorcery_window_is_untouched(self, builder):
        """The control: a sorcery in your own main phase was always castable."""
        game = position(builder, active=0, advance=False)
        assert can_cast(game, 0, SORCERY)


class TestAfterAnOpponentCasts:
    def test_you_may_respond_to_that_spell_with_a_sorcery(self, builder):
        game = position(builder, active=1)
        cast(game, SORCERY)
        assert game.state.stack, "the opponent's sorcery is still waiting"
        assert flash(game)
        assert can_cast(game, 0, SORCERY)

    def test_and_after_it_resolves(self, builder):
        """Still the opponent's turn, with an empty stack: the window stays open."""
        game = position(builder, active=1, theirs=(SORCERY, SORCERY))
        cast(game, SORCERY)
        settle(game)
        assert not game.state.stack
        assert game.state.active_player == 1
        assert can_cast(game, 0, SORCERY)

    def test_an_opponents_instant_on_your_own_turn(self, builder):
        """You pass in your main phase, an opponent answers with an instant, and
        you may respond to it with a sorcery -- which the empty-stack half of
        the sorcery window would otherwise forbid."""
        game = position(builder, active=0, hand0=(SORCERY, SORCERY), theirs=(BOLT,))
        game.apply(find_action(game, ActionKind.PASS))
        assert game.pending().player == 1
        cast(game, BOLT)
        assert game.state.stack and game.pending().player == 0
        assert flash(game)
        assert can_cast(game, 0, SORCERY)

    def test_it_reaches_only_you(self, builder):
        """"You may cast": the opponent who cast is not given flash."""
        game = position(builder, active=1, theirs=(SORCERY, SORCERY))
        cast(game, SORCERY)
        assert not flash(game, 1)


class TestOnlyAnOpponentsCastCounts:
    def test_your_own_cast_does_not_turn_it_on(self, builder):
        """A second Bolt in hand keeps your priority while the first waits."""
        game = position(builder, active=0, hand0=(BOLT, BOLT, SORCERY))
        cast(game, BOLT)
        assert game.state.stack and game.pending().player == 0
        assert game.state.turn_ledger.spells_cast == {0: 1}
        assert not flash(game)
        assert not can_cast(game, 0, SORCERY), "the stack is not empty and nothing lifted that"

    def test_in_a_pod_any_one_opponent_is_enough(self, builder):
        game = position(builder, players=3, active=2)
        cast(game, SORCERY)
        assert game.state.turn_ledger.spells_cast == {2: 1}
        assert flash(game)
        assert can_cast(game, 0, SORCERY)


class TestItEndsWithTheTurn:
    def test_the_next_turn_starts_without_it(self, builder):
        game = position(builder, active=1)
        cast(game, SORCERY)
        assert flash(game)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn != turn)
        assert game.state.active_player == 0
        assert not game.state.turn_ledger.spells_cast
        assert not flash(game)

    def test_a_cast_last_turn_is_not_a_cast_this_turn(self, builder):
        """Into your own turn, past the main phase: the window is shut again."""
        game = position(builder, active=1)
        cast(game, SORCERY)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn != turn)
        game.state.step = Step.BEGIN_COMBAT
        assert not can_cast(game, 0, SORCERY)


class TestALayeredReaderSeesItToo:
    """The same leaf on a buff, so the characteristics cache must be told.

    `chars` is cached per `char_version`. In an ordinary game something else
    usually bumps it nearby -- the cast's move to the stack, the next turn's
    untap -- so the last two tests take those away: the ledger's own writer and
    its own reset must each bump it, or the Brawler keeps a stale answer.
    """

    def test_it_grows_the_moment_an_opponent_casts(self, builder):
        game = position(builder, active=1, mine=(BRAWLER,), theirs=(SORCERY, SORCERY))
        brawler = only_oid(game, BRAWLER, 0)
        assert pt(game, brawler) == (1, 1)
        cast(game, SORCERY)
        assert pt(game, brawler) == (3, 1)

    def test_and_shrinks_when_the_turn_ends(self, builder):
        game = position(builder, active=1, mine=(BRAWLER,), theirs=(SORCERY, SORCERY))
        brawler = only_oid(game, BRAWLER, 0)
        cast(game, SORCERY)
        assert pt(game, brawler) == (3, 1)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn != turn)
        assert pt(game, brawler) == (1, 1)

    def test_the_cast_fold_itself_invalidates_the_cache(self, builder):
        """SPELL_CAST alone, with no zone change beside it."""
        game = position(builder, active=1, mine=(BRAWLER,), advance=False)
        brawler = only_oid(game, BRAWLER, 0)
        assert pt(game, brawler) == (1, 1)
        game.state.emit(EventType.SPELL_CAST, player=1, card=SORCERY)
        assert pt(game, brawler) == (3, 1)

    def test_the_cleanup_reset_itself_invalidates_the_cache(self, builder, monkeypatch):
        """The cleanup step alone, with no untap step after it.

        The step's earlier clears bump the version before the ledger is reset,
        so a reader in between -- here, one planted beside a clear -- caches the
        3/1, and only a bump at the reset itself throws it away.
        """
        game = position(builder, active=1, mine=(BRAWLER,), advance=False, step=Step.CLEANUP)
        brawler = only_oid(game, BRAWLER, 0)
        game.state.emit(EventType.SPELL_CAST, player=1, card=SORCERY)
        original = turn_module.clear_sacrifice_restrictions

        def reading(state, *args):
            assert pt(game, brawler) == (3, 1), "still this turn"
            return original(state, *args)

        monkeypatch.setattr(turn_module, "clear_sacrifice_restrictions", reading)
        for _ in turn_module._cleanup_step(game.state):
            raise AssertionError("nothing to discard, so cleanup asks nothing")
        assert not game.state.turn_ledger.spells_cast
        assert pt(game, brawler) == (1, 1)


class TestTheLoader:
    def compile(self, left):
        static = {
            "effect": "cast_as_though_flash",
            "affects_player": "you",
            "condition": {"cmp": ">", "left": left, "right": {"const": 0}},
        }
        return compile_card(CardModel.model_validate(static_probe(static)))

    @pytest.mark.parametrize("who", ["opponent", "each_opponent", "you", "all"])
    def test_a_player_spec_loads(self, who):
        self.compile({"spells_cast_this_turn": who})

    def test_the_typed_form_is_refused(self):
        """The effect side's `{"player", "filter"}` matches cast cards' faces,
        which no static reads; refused by name rather than read as 0."""
        with pytest.raises(DslError, match="bare player spec"):
            self.compile({"spells_cast_this_turn": {"player": "opponent", "filter": {"types": ["Instant"]}}})

    @pytest.mark.parametrize("who", ["active_player", "opponents", True])
    def test_an_unknown_player_spec_is_refused(self, who):
        with pytest.raises(DslError, match="spells_cast_this_turn"):
            self.compile({"spells_cast_this_turn": who})
