"""The other half of Grand Abolisher: "…or activate abilities of artifacts,
creatures, or enchantments."

`tests/unit/statics/test_cant_cast_spells.py` builds the casting half and says in its own
docstring that this one is *a different static* -- and `player_cant_cast_spells`
repeats it, listing "activating abilities" among the things it deliberately does
not stop. So Voice of Victory shipped and Grand Abolisher did not. Myrel, Shield
of Argive is the card that forced it: its first line is that whole sentence, and
writing it as `cant_cast_spells` alone would have dropped a printed clause.

Three claims, and each is a different way to get the prohibition wrong.

**It names permanents, not just seats.** Casting is something a player does;
activating is something a player does *to a permanent*. Every printed card in
this family says which permanents -- "of artifacts, creatures, or enchantments"
-- so the predicate takes the object as well as the player, and the filter is
required vocabulary rather than a refusable extra. Filterless, the card would
also stop an opponent cracking a fetchland or moving a planeswalker's loyalty,
which is a strictly stronger lock than anything ever printed and one that looks
correct on the board. The loader refuses it; `TestTheLoaderRefusesTheSilentFailures`
is that refusal, and `TestTheFilterIsReal` is the land that proves the clause
does work.

**It stops mana abilities.** 605.1a: a mana ability is an activated ability, and
the printed line excepts nothing. A lock read only at `legality` would leave an
opponent's Llanowar Elves tapping for mana all through your turn, because the
mana solver reaches `_sources_of` without going near the priority actions -- the
same split `ObjectState.abilities_locked` already documents for `lock_abilities`,
which is why both sites ask. `TestItReachesTheManaSolver` is the boundary, and it
is the one a version that passed every legality test would still fail.

**It lifts.** `affects_player` picks the seats and `condition` picks the turn,
both through `_active_player_statics`, so the lock is gone the instant the source
leaves or the turn passes. A prohibition that outlived either would be a
different card.

Witness: Myrel, Shield of Argive
(`myrel_shield_of_argive` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import legality
from commanderblitz.engine.costs import _sources_of
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import player_cant_activate
from tests.conftest import oids_of, only_oid

ABOLISHER = "t_abolisher"  # opponents can't activate, during your turn
QUIET = "t_quiet_abolisher"  # the same, on any turn
MUTATOR = "t_mutator"  # creature, {G}: +1/+1 until end of turn
BOBBLEHEAD = "t_bobblehead"  # artifact, {1}, {T}: roll dice
OUTLET = "t_sac_outlet"  # enchantment, sacrifice a creature: gain 1 life
PASSAGE = "t_passage"  # land, {T}: add {C} -- the clause's other side
DORK = "t_dork"  # creature, {T}: add {G} -- 605.1a
FOREST = "forest"
PLAINS = "plains"


def position(
    builder,
    lock: str | None = ABOLISHER,
    *,
    active: int = 0,
    board1: tuple[str, ...] = (MUTATOR, BOBBLEHEAD, OUTLET),
):
    """Player 0 holds the lock; player 1 is the opponent it names.

    Player 1 keeps the permanents whose abilities are under test, plus Forests to
    pay for them, so the only thing that can withhold an activation is the
    static. ``active`` is whose turn it is -- the one thing the condition reads.
    """
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * 3 + ([lock] if lock else []))
        .battlefield(1, [FOREST] * 3 + list(board1))
        .hand(0, [PLAINS])
        .hand(1, [PLAINS])
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
        .build(advance=False)
    )


def activatable(game, pid: int) -> set[int]:
    """The source oids of every activate action legality offers ``pid``."""
    return {
        a.source
        for a in legality._priority_actions(game.state, pid)
        if a.kind.value == "activate"
    }


class TestTheLock:
    def test_the_opponent_may_not_activate_during_your_turn(self, builder):
        game = position(builder, active=0)
        for card in (MUTATOR, BOBBLEHEAD, OUTLET):
            oid = only_oid(game, card, 1)
            assert player_cant_activate(game.state, 1, oid), card
            assert oid not in activatable(game, 1), card

    def test_without_the_static_they_could(self, builder):
        """Pins that the refusal above is the static's and not the position's."""
        game = position(builder, lock=None, active=0)
        offered = activatable(game, 1)
        for card in (MUTATOR, BOBBLEHEAD, OUTLET):
            assert only_oid(game, card, 1) in offered, card

    def test_its_controller_is_unaffected(self, builder):
        """"Your *opponents*" -- `affects_player` is not decoration."""
        game = position(builder, lock=QUIET, active=0, board1=())
        assert not player_cant_activate(game.state, 0, only_oid(game, QUIET, 0))


class TestItLifts:
    def test_it_sleeps_on_the_opponents_turn(self, builder):
        """The `condition`. Myrel says "during your turn", and the other player's
        turn is the whole of when the opponent is meant to be free."""
        game = position(builder, active=1)
        for card in (MUTATOR, BOBBLEHEAD, OUTLET):
            oid = only_oid(game, card, 1)
            assert not player_cant_activate(game.state, 1, oid), card
            assert oid in activatable(game, 1), card

    def test_the_unconditional_version_holds_on_either_turn(self, builder):
        """Pins that the turn-sleeping above is the condition's doing and not a
        hole in the static itself."""
        game = position(builder, lock=QUIET, active=1)
        for card in (MUTATOR, BOBBLEHEAD, OUTLET):
            assert player_cant_activate(game.state, 1, only_oid(game, card, 1)), card


class TestTheFilterIsReal:
    """The reason `affects` is required rather than defaulted.

    A filterless version would load clean and read as the printed card while
    quietly also stopping lands and planeswalkers. The land is how that
    difference is measured rather than described.
    """

    def test_a_land_is_not_stopped(self, builder):
        game = position(builder, lock=QUIET, active=0, board1=(PASSAGE,))
        oid = only_oid(game, PASSAGE, 1)
        assert not player_cant_activate(game.state, 1, oid)

    def test_the_lands_mana_ability_still_answers_the_solver(self, builder):
        """The other half of the same claim, at the seam that would matter in a
        real game: the opponent can still tap the land for mana."""
        game = position(builder, lock=QUIET, active=0, board1=(PASSAGE,))
        oid = only_oid(game, PASSAGE, 1)
        assert _sources_of(game.state, oid, game.state.objects[oid])

    def test_a_creature_on_the_same_board_is_still_stopped(self, builder):
        """Pins that the land above is exempt by its *type* and not because the
        static stopped applying to that board."""
        game = position(builder, lock=QUIET, active=0, board1=(PASSAGE, MUTATOR))
        assert not player_cant_activate(game.state, 1, only_oid(game, PASSAGE, 1))
        assert player_cant_activate(game.state, 1, only_oid(game, MUTATOR, 1))


class TestItReachesTheManaSolver:
    """605.1a -- a mana ability is an activated ability, and the printed line
    excepts nothing.

    This is the boundary a version read only at `legality` would fail while
    passing every test above: the mana solver reaches `_sources_of` without ever
    building a priority action, so an opponent's mana creature would keep
    tapping right through the lock. `ObjectState.abilities_locked` documents the
    same split for `lock_abilities`, which is why `_sources_of` asks both.
    """

    def test_a_locked_creatures_mana_ability_is_withheld(self, builder):
        game = position(builder, lock=QUIET, active=0, board1=(DORK,))
        oid = only_oid(game, DORK, 1)
        assert player_cant_activate(game.state, 1, oid)
        assert _sources_of(game.state, oid, game.state.objects[oid]) == []

    def test_without_the_lock_it_is_a_mana_source(self, builder):
        """Pins that the empty list above is the lock's and not the creature's
        -- summoning sickness would produce the same empty list."""
        game = position(builder, lock=None, active=0, board1=(DORK,))
        oid = only_oid(game, DORK, 1)
        assert _sources_of(game.state, oid, game.state.objects[oid])

    def test_the_lock_holder_still_taps_their_own(self, builder):
        """"Your opponents" again, measured at the solver rather than legality."""
        game = position(builder, lock=QUIET, active=0, board1=())
        oid = oids_of(game, PLAINS, 0)[0]
        assert _sources_of(game.state, oid, game.state.objects[oid])


class TestTheLoaderRefusesTheSilentFailures:
    def _card(self, **extra) -> CardModel:
        static = {
            "kind": "static",
            "text": "Your opponents can't activate abilities of artifacts, "
            "creatures, or enchantments.",
            "effect": "cant_activate_abilities",
            "affects_player": "opponent",
            "affects": {
                "controller": "opponent",
                "any_types": ["Artifact", "Creature", "Enchantment"],
            },
        }
        static.update(extra)
        return CardModel.model_validate(
            {
                "id": "t_abolisher_probe",
                "name": "Abolisher Probe",
                "mana_cost": "{2}{W}",
                "oracle_text": "Your opponents can't activate abilities of "
                "artifacts, creatures, or enchantments.",
                "types": ["Creature"],
                "power": 2,
                "toughness": 2,
                "abilities": [static],
            }
        )

    def test_the_printed_shape_loads(self):
        assert compile_card(self._card()) is not None

    def test_a_missing_filter_is_refused(self):
        """The strictly stronger card. Without the types it also stops lands and
        planeswalkers, and nothing on the board would say so."""
        with pytest.raises(DslError, match="needs 'affects'"):
            compile_card(self._card(affects=None))

    def test_an_amount_is_refused(self):
        """A prohibition has no size. A number here would read as "can't
        activate more than N", which is a different card and one nothing
        enforces."""
        with pytest.raises(DslError, match="prohibition, not a limit"):
            compile_card(self._card(amount={"const": 1}))

    def test_a_missing_affects_player_is_refused(self):
        """Inherited from the player-wide family: with no seats named, the lock
        would silently bind nobody."""
        with pytest.raises(DslError, match="affects_player"):
            compile_card(self._card(affects_player=None))
