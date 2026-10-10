"""A player who can't cast spells: "Your opponents can't cast spells during your turn."

Voice of Victory is the witness. The line is a *static* on a permanent, scoped to
a set of seats and to a turn, and the engine's two existing cast prohibitions
are each the wrong shape: split second (702.61a) lives on the stack and binds
every player including its own caster, and epic (702.50a) is a card-level rider
that locks its own controller for the rest of the game. Neither can say "these
players, while this permanent is here, during this turn".

Three claims carry the rules argument.

**It stops casting, wherever the card is.** 601.2 has no zone in it: a flashback
from the graveyard, a foretold card from exile and a commander from the command
zone are all casts. So the gate is at the top of `casting._cast_actions`, before
any zone is walked, rather than in the hand loop where the obvious version would
put it -- that version passes every hand test and lets flashback straight
through.

**It stops the casts a resolving effect makes, too.** Rule 101.2: when an effect
says a player may do something and another says they can't, the "can't" wins.
Cascade, suspend, rebound, madness, miracle, `cast_from_hand`, `play_exiled` and
`cast_copy` all cast without ever going through legality, so a lock that only
withheld priority actions would let an opponent's cascade -- already on the
stack when Voice's controller's turn came round, or triggered from a spell cast
before Voice arrived -- put a free spell on the stack straight through it.
`suspend.cast_for_free` and `replacements._offer_cast` are the floors, and the
ops that ask "you may cast" first check before asking, so no prompt is shown
whose yes would do nothing. `cast_copy` is refused as well, because 707.12 says
casting a copy of a card is casting a spell.

**It stops nothing else.** Copying a spell is not casting it (707.10), playing a
land and suspending are special actions (116.2), and activated abilities are
Grand Abolisher's *other* half -- a different static. Each of these still works
under the lock, and each is pinned below, because a lock that also withheld one
of them would be a strictly stronger card that looks identical on the board.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import legality
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_stack import put_copy_on_stack
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import player_cant_cast_spells
from commanderblitz.engine.replacements import discard as discard_with_replacements
from commanderblitz.engine.structs import StackItem
from commanderblitz.engine.suspend import cast_for_free
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

VOICE = "t_voice"  # opponents can't cast spells during your turn
QUIET = "t_quiet_voice"  # opponents can't cast spells, on any turn
BOLT = "t_bolt"  # {R} instant, 3 damage to a creature
FLASHBACK = "t_flashback_shock"  # {R} instant, flashback {R}
MADNESS = "t_madness"  # {2}{R} instant, madness {R}
CIPHER = "t_cipher"  # its encoded trigger casts a copy of itself
BEAR = "t_bear"  # {1}{G} creature, mana value 2
DORK = "t_dork"  # 1/1 with a mana ability
MOUNTAIN = "mountain"


def position(
    builder,
    lock: str | None = VOICE,
    *,
    active: int = 0,
    hand0: tuple[str, ...] = (),
    hand1: tuple[str, ...] = (BOLT,),
    graveyard1: tuple[str, ...] = (),
    library1: tuple[str, ...] | None = None,
    board1: tuple[str, ...] = (),
):
    """Player 0 holds the lock; player 1 is the opponent it names.

    Both have Mountains and a Bear on the battlefield, so every red instant in
    either hand has mana and a target, and the only thing that can withhold a
    cast is the static. ``active`` is whose turn it is -- the one thing Voice's
    condition reads. ``board1`` is anything else player 1 needs on the table.
    """
    b = (
        builder(players=2)
        .battlefield(0, [MOUNTAIN] * 3 + [BEAR] + ([lock] if lock else []))
        .battlefield(1, [MOUNTAIN] * 3 + [DORK, *board1])
        .hand(0, list(hand0))
        .hand(1, list(hand1))
        .graveyard(1, list(graveyard1))
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
    )
    if library1 is not None:
        b = b.library(1, list(library1))
    return b.build(advance=False)


def kinds(game, pid: int) -> set[str]:
    return {a.kind.value for a in legality._priority_actions(game.state, pid)}


def run(game, op: str, spec, *, controller: int, source: int) -> list:
    """Drive one op to completion, answering every question "yes".

    Returns the questions asked, so a test can pin that a refused cast was not
    offered at all rather than offered and then quietly dropped.
    """
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    gen = OPS[op](ctx, spec)
    asked: list = []
    send = None
    while True:
        try:
            asked.append(gen.send(send))
        except StopIteration:
            return asked[1:] if asked and asked[0] is None else asked
        send = [0]


class TestTheLock:
    def test_the_opponent_may_not_cast_during_your_turn(self, builder):
        game = position(builder, active=0)
        assert player_cant_cast_spells(game.state, 1)
        assert "cast" not in kinds(game, 1)

    def test_without_the_static_they_could(self, builder):
        """Pins that the refusal above is the static's and not the position's."""
        game = position(builder, lock=None, active=0)
        assert "cast" in kinds(game, 1)

    def test_its_controller_is_unaffected(self, builder):
        """"Your *opponents*" -- `affects_player` is not decoration."""
        game = position(builder, active=0, hand0=(BOLT,))
        assert not player_cant_cast_spells(game.state, 0)
        assert "cast" in kinds(game, 0)


class TestTheBoundary:
    def test_on_the_opponents_own_turn_they_may_cast(self, builder):
        """"During your turn" is a `condition`, and it is actually read."""
        game = position(builder, active=1)
        assert not player_cant_cast_spells(game.state, 1)
        assert "cast" in kinds(game, 1)

    def test_the_turn_passing_lifts_it(self, builder):
        game = position(builder, active=0)
        assert "cast" not in kinds(game, 1)
        game.state.active_idx = 1
        assert "cast" in kinds(game, 1)

    def test_the_unconditional_twin_locks_either_turn(self, builder):
        """Pins that the result above comes from the condition, not the walk."""
        for active in (0, 1):
            game = position(builder, QUIET, active=active)
            assert "cast" not in kinds(game, 1)

    def test_the_static_leaving_makes_them_castable_again(self, builder):
        """Read live off the battlefield, so there is nothing to clear."""
        game = position(builder, active=0)
        assert "cast" not in kinds(game, 1)
        move_object(game.state, only_oid(game, VOICE), Zone.GRAVEYARD)
        assert "cast" in kinds(game, 1)


class TestEveryZone:
    def test_flashback_from_the_graveyard_is_withheld(self, builder):
        """601.2 names no zone. A gate in the hand loop alone lets this through."""
        open_game = position(builder, lock=None, hand1=(), graveyard1=(FLASHBACK,))
        assert "cast" in kinds(open_game, 1), "flashback is on offer without the lock"

        game = position(builder, QUIET, hand1=(), graveyard1=(FLASHBACK,))
        assert "cast" not in kinds(game, 1)


class TestWhatItDoesNotStop:
    def test_abilities_are_still_activated(self, builder):
        """Grand Abolisher's second half is a different static.

        A sacrifice outlet with a creature to eat, because a tap-only mana
        ability is not offered as an action at all (the payment solver owns it)
        and so could not show the difference.
        """
        game = position(builder, QUIET, board1=("t_sac_outlet", BEAR))
        assert "activate" in kinds(game, 1)
        assert "cast" not in kinds(game, 1)

    def test_a_land_is_still_played(self, builder):
        """Playing a land is a special action (116.2), not a cast."""
        game = position(builder, QUIET, active=1, hand1=(BOLT, "forest"))
        assert "play_land" in kinds(game, 1)
        assert "cast" not in kinds(game, 1)

    def test_a_spell_is_still_copied(self, builder):
        """707.10: a copy put on the stack was never cast."""
        game = position(builder, active=0)
        template = StackItem(sid=-1, kind="spell", controller=1, def_id=BOLT, oid=0)
        put_copy_on_stack(game.state, 1, template)
        assert [item.def_id for item in game.state.stack] == [BOLT]


class TestResolutionTimeCasts:
    """101.2: the "can't" beats every "you may cast" a resolving effect offers."""

    def cascade(self, builder, *, active: int):
        """Player 1's cascade resolving, ceiling 5, over a library of one Bear.

        The source is only where the ability comes from; the ceiling is written
        out, so no cascade spell has to be cast -- which is the whole point,
        since during player 0's turn player 1 could not cast one.
        """
        game = position(builder, active=active, hand1=(), library1=(BEAR,))
        spec = {"op": "cascade", "max_mana_value": {"const": 5}}
        asked = run(game, "cascade", spec, controller=1, source=only_oid(game, DORK))
        return game, asked

    def test_a_cascade_during_your_turn_is_refused(self, builder):
        game, asked = self.cascade(builder, active=0)
        assert game.state.stack == []
        assert asked == [], "no 'cast it for free?' whose yes could do nothing"
        library = [game.state.objects[o].def_id for o in game.state.players[1].library]
        assert library == [BEAR], "the refused card is bottomed with the rest"

    def test_the_same_cascade_on_their_own_turn_casts(self, builder):
        game, asked = self.cascade(builder, active=1)
        assert [item.def_id for item in game.state.stack] == [BEAR]
        assert asked, "the cast was offered"

    def test_the_free_cast_floor_refuses_directly(self, builder):
        """`cast_for_free` is what suspend, rebound and `play_exiled` share."""
        game = position(builder, active=0, hand1=(BOLT,))
        bolt = game.state.players[1].hand[0]
        move_object(game.state, bolt, Zone.EXILE, to_player=1)
        assert cast_for_free(game.state, 1, bolt) is False
        assert game.state.objects[bolt].zone is Zone.EXILE
        assert game.state.stack == []

    def test_madness_is_exiled_and_not_cast(self, builder):
        """The exile still happens -- it is the replacement, not the cast."""
        game = position(builder, active=0, hand1=(MADNESS,))
        card = game.state.players[1].hand[0]
        gen = discard_with_replacements(game.state, 1, [card])
        with pytest.raises(StopIteration):
            gen.send(None)
        assert game.state.objects[card].zone is Zone.EXILE
        assert game.state.stack == []

    def test_casting_a_copy_is_casting(self, builder):
        """707.12: cipher's "cast a copy" is a cast, where `copy_spell` is not."""
        game = position(builder, active=0, hand1=(CIPHER,))
        cipher = game.state.players[1].hand[0]
        move_object(game.state, cipher, Zone.EXILE, to_player=1)
        run(game, "cast_copy", {"op": "cast_copy"}, controller=1, source=cipher)
        assert game.state.stack == []

        game.state.active_idx = 1
        run(game, "cast_copy", {"op": "cast_copy"}, controller=1, source=cipher)
        assert [item.def_id for item in game.state.stack] == [CIPHER]


class TestTheLoader:
    def _card(self, **static) -> dict:
        return {
            "id": "t_bad_voice",
            "name": "Test Bad Voice",
            "oracle_text": "Your opponents can't cast creature spells.",
            "mana_cost": "{1}{W}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 3,
            "abilities": [
                {
                    "kind": "static",
                    "text": "Your opponents can't cast creature spells.",
                    "effect": "cant_cast_spells",
                    **static,
                }
            ],
        }

    def test_the_seats_are_required(self):
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(self._card()))

    def test_a_filter_is_refused_rather_than_ignored(self):
        """Ignored, "creature spells" would load as a lock on every spell."""
        card = self._card(affects_player="opponent", affects={"types": ["Creature"]})
        with pytest.raises(DslError, match="cant_cast_spells"):
            compile_card(CardModel.model_validate(card))

    def test_voice_of_victorys_line_loads(self):
        card = self._card(affects_player="opponent", condition={"is_your_turn": True})
        compile_card(CardModel.model_validate(card))
