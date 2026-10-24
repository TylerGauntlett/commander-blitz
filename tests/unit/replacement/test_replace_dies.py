"""Replacing a death, with a rider — "instead exile that card and create a Zombie".

    Kalitas, Traitor of Ghet — "If a nontoken creature an opponent controls would
    die, instead exile that card and create a 2/2 black Zombie creature token."

A replacement effect (614.1a), and 614.6 is the half that matters: the event is
replaced, so the creature **never dies**. Nothing listening for a death hears
one, and the Zombie cannot be a `creature_dies` trigger — that would be a card
that lets the opponent's "when this dies" fire and hands its controller a
Zombie on the stack, where it can be answered, rather than as part of the
event.

`replace_graveyard` is the near miss and it cannot say this sentence: it is
gated on the destination alone ("from anywhere"), it filters by the
*graveyard's owner* rather than the dying permanent's controller, and it
creates nothing. `replace_deaths` is a one-shot mark on chosen objects, not a
standing static. So `replace_dies` is its own static: a battlefield-to-graveyard
move only, `affects` read against the permanent while it still stands, and
`and_create` made under the **replacement's** controller.

Three orderings are argued in `zones._dies_replacement` and pinned here:

- **The commander** (903.9a): exiled first, so its owner's opponent still gets
  the Zombie, and then it goes home — `TestTheCommander`.
- **The affected player's own replacement** (616.1): a creature under Rest in
  Peace belongs to a player who would apply that one first and leave nothing
  dying — `TestTheAffectedPlayerChoosesFirst`.
- **Dying together** (Kalitas's ruling): Kalitas dying in the same wrath as the
  opponent's creatures still exiles them, though the engine moves them one at a
  time — `TestDyingTogether`.

Witness: Kalitas, Traitor of Ghet (`kalitas_traitor_of_ghet` in
`data/cards/auto/`).
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy, exile, move_object, sacrifice
from tests.conftest import oids_of, only_oid, settle, static_probe

KALITAS = "t_kalitas_like"
BEAR = "t_bear"
THIS_DIES = "t_this_dies"  # "When this creature dies, you gain 1 life."
RIP = "t_rip"
ZOMBIE = "zombie_2_2_b"


def board(builder, mine=(KALITAS,), theirs=(BEAR,)):
    """Player 0's Kalitas facing player 1's creatures, in a main phase."""
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["plains"] * 5)
        .library(1, ["plains"] * 5)
        .build()
    )
    return game, only_oid(game, KALITAS) if KALITAS in mine else None


def zombies(game, pid: int) -> int:
    return len(oids_of(game, ZOMBIE, pid))


def zone_of(game, oid: int) -> Zone:
    return game.state.objects[oid].zone


def run_op(game, spec: dict, *, controller: int = 0) -> None:
    """Resolve one effect op with no card in the way -- one simultaneous event."""
    gen = execute(EffectContext(state=game.state, controller=controller), [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


class TestAnOpponentsCreature:
    def test_it_is_exiled_instead(self, builder):
        game, _ = board(builder)
        bear = only_oid(game, BEAR)

        destroy(game.state, bear)

        assert zone_of(game, bear) is Zone.EXILE
        assert game.state.players[1].graveyard == []

    def test_kalitass_controller_gets_the_zombie(self, builder):
        """Under the replacement's controller, not the dead creature's."""
        game, _ = board(builder)
        destroy(game.state, only_oid(game, BEAR))

        assert zombies(game, 0) == 1
        assert zombies(game, 1) == 0

    def test_every_route_to_dying_is_replaced(self, builder):
        """The printed word is *die*: sacrificed and put into the graveyard die
        too, and neither goes near `destroy`."""
        game, _ = board(builder, theirs=(BEAR, BEAR))
        first, second = oids_of(game, BEAR, 1)

        sacrifice(game.state, first)
        move_object(game.state, second, Zone.GRAVEYARD)

        assert zone_of(game, first) is Zone.EXILE
        assert zone_of(game, second) is Zone.EXILE
        assert zombies(game, 0) == 2

    def test_one_zombie_per_death(self, builder):
        game, _ = board(builder, theirs=(BEAR, BEAR, BEAR))
        run_op(game, {"op": "destroy", "objects": {"types": ["Creature"], "controller": "opponent"}})

        assert zombies(game, 0) == 3


class TestItIsNotADeath:
    """614.6: the event is replaced, so no dies trigger has anything to fire on."""

    def test_the_creatures_own_dies_trigger_does_not_fire(self, builder):
        game, _ = board(builder, theirs=(THIS_DIES,))
        life = game.state.players[1].life

        destroy(game.state, only_oid(game, THIS_DIES))

        assert game.state.pending_triggers == []
        settle(game)
        assert game.state.players[1].life == life

    def test_the_same_creature_without_kalitas_does_trigger(self, builder):
        """The control: the trigger is real and would have fired."""
        game, _ = board(builder, mine=(), theirs=(THIS_DIES,))
        life = game.state.players[1].life

        destroy(game.state, only_oid(game, THIS_DIES))
        settle(game)

        assert game.state.players[1].life == life + 1


class TestWhatItLeavesAlone:
    def test_your_own_creature_dies_normally(self, builder):
        """"an **opponent** controls" -- read against the dying permanent's
        controller."""
        game, _ = board(builder, mine=(KALITAS, BEAR), theirs=())
        bear = only_oid(game, BEAR, 0)

        destroy(game.state, bear)

        assert zone_of(game, bear) is Zone.GRAVEYARD
        assert zombies(game, 0) == 0

    def test_an_opponents_token_is_not_replaced(self, builder):
        """"**nontoken**" -- a token dies, and makes no Zombie."""
        game, _ = board(builder)
        bear = only_oid(game, BEAR)
        game.state.objects[bear].is_token = True

        destroy(game.state, bear)

        assert zombies(game, 0) == 0
        assert bear not in game.state.players[1].exile

    def test_a_card_milled_or_discarded_is_not_dying(self, builder):
        """Only a death: the graveyard from anywhere is `replace_graveyard`'s."""
        game, _ = board(builder)
        top = game.state.players[1].library[0]

        move_object(game.state, top, Zone.GRAVEYARD)

        assert zone_of(game, top) is Zone.GRAVEYARD
        assert zombies(game, 0) == 0

    def test_leaving_another_way_is_not_dying(self, builder):
        game, _ = board(builder)
        bear = only_oid(game, BEAR)

        exile(game.state, bear)

        assert zone_of(game, bear) is Zone.EXILE
        assert zombies(game, 0) == 0


class TestItStopsWhenKalitasLeaves:
    def test_after_kalitas_is_exiled_deaths_are_deaths(self, builder):
        game, kalitas = board(builder)
        exile(game.state, kalitas)
        sba.check(game.state)

        bear = only_oid(game, BEAR)
        destroy(game.state, bear)

        assert zone_of(game, bear) is Zone.GRAVEYARD
        assert zombies(game, 0) == 0

    def test_a_death_in_a_later_event_is_not_replaced(self, builder):
        """The look-back below is for one simultaneous event only: an op that
        exiles Kalitas and a later op that kills the Bear are two events."""
        game, kalitas = board(builder)
        bear = only_oid(game, BEAR)
        run_op(game, {"op": "exile", "objects": {"types": ["Creature"], "controller": "you"}})
        assert zone_of(game, kalitas) is Zone.EXILE

        run_op(game, {"op": "destroy", "objects": {"types": ["Creature"], "controller": "any"}})

        assert zone_of(game, bear) is Zone.GRAVEYARD
        assert zombies(game, 0) == 0


class TestDyingTogether:
    """Kalitas's ruling: dying at the same time as the opponent's creatures, its
    ability still applies to them. The engine moves a wrath's creatures one at a
    time, so Kalitas may be first out of the door -- both orders are pinned."""

    @pytest.mark.parametrize("kalitas_first", [True, False])
    def test_a_wrath_that_takes_kalitas_too(self, builder, kalitas_first):
        mine, theirs = (KALITAS,), (BEAR, BEAR)
        game, kalitas = board(builder, mine=mine, theirs=theirs)
        if not kalitas_first:
            game.state.battlefield.remove(kalitas)
            game.state.battlefield.append(kalitas)

        run_op(game, {"op": "destroy", "objects": {"types": ["Creature"], "controller": "any"}})

        assert zone_of(game, kalitas) is Zone.GRAVEYARD
        assert all(zone_of(game, oid) is Zone.EXILE for oid in oids_of(game, BEAR, 1))
        assert zombies(game, 0) == 2

    def test_a_state_based_action_pass_forgets_it(self, builder):
        """704.3: each pass is its own event, and the batch counter does not move
        between them -- so the pass clears what the last event left behind."""
        game, kalitas = board(builder)
        destroy(game.state, kalitas)
        assert zone_of(game, kalitas) is Zone.GRAVEYARD
        sba.check(game.state)

        bear = only_oid(game, BEAR)
        move_object(game.state, bear, Zone.GRAVEYARD)

        assert zone_of(game, bear) is Zone.GRAVEYARD
        assert zombies(game, 0) == 0


class TestTheCommander:
    """903.9a moves a commander home *after* it has been exiled, so the
    replacement applies and the commander still reaches the command zone."""

    def test_an_opponents_commander_goes_home_and_makes_a_zombie(self, builder):
        game, _ = board(builder)
        bear = only_oid(game, BEAR)
        game.state.objects[bear].is_commander = True

        destroy(game.state, bear)

        assert zone_of(game, bear) is Zone.COMMAND
        assert zombies(game, 0) == 1


class TestTheAffectedPlayerChoosesFirst:
    """616.1: the dying creature's controller orders the replacements, and
    applying their own first leaves nothing dying for Kalitas."""

    def test_rest_in_peace_exiles_it_and_no_zombie_is_made(self, builder):
        game, _ = board(builder, mine=(KALITAS, RIP))
        bear = only_oid(game, BEAR)

        destroy(game.state, bear)

        assert zone_of(game, bear) is Zone.EXILE
        assert zombies(game, 0) == 0

    def test_a_dies_to_mark_is_applied_instead(self, builder):
        game, _ = board(builder)
        bear = only_oid(game, BEAR)
        game.state.objects[bear].dies_to = "exile"

        destroy(game.state, bear)

        assert zone_of(game, bear) is Zone.EXILE
        assert zombies(game, 0) == 0


class TestTheLoaderRefusals:
    SHAPE = {
        "effect": "replace_dies",
        "affects": {"types": ["Creature"], "controller": "opponent", "is_token": False},
        "destination": "exile",
        "and_create": [ZOMBIE],
    }

    def _compile(self, **changes):
        static = {**self.SHAPE, **changes}
        static = {k: v for k, v in static.items() if v is not None}
        return compile_card(CardModel.model_validate(static_probe(static)))

    def test_the_printed_shape_loads(self):
        assert self._compile() is not None

    def test_the_rider_is_optional(self):
        """"If another creature would die, exile it instead" (Void Maw) creates
        nothing."""
        assert self._compile(and_create=[]) is not None

    def test_affects_is_required(self):
        with pytest.raises(DslError, match="needs 'affects'"):
            self._compile(affects=None)

    def test_the_destination_is_required(self):
        with pytest.raises(DslError, match="needs 'destination': 'exile'"):
            self._compile(destination=None)

    def test_affects_player_is_refused(self):
        with pytest.raises(DslError, match="'affects_player' is replace_graveyard's"):
            self._compile(affects_player="opponent")

    def test_and_create_elsewhere_is_refused(self):
        with pytest.raises(DslError, match="'and_create' is a replace_dies rider"):
            compile_card(
                CardModel.model_validate(
                    static_probe(
                        {
                            "effect": "replace_graveyard",
                            "affects_player": "any",
                            "destination": "exile",
                            "and_create": [ZOMBIE],
                        }
                    )
                )
            )
