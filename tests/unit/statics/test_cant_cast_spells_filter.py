"""A filtered cast prohibition: "Your opponents can't cast noncreature spells."

Narset Transcendent's -9 emblem is the witness. `cant_cast_spells` was total by
construction -- the loader refused any filter beside it, because nothing read
one -- so the only way to write the emblem was as Voice of Victory's lock on
*every* spell: a strictly stronger card that stops creature spells too.

Rule 601.2 names no zone and 101.2 lets a "can't" beat every "may", which is why
the unfiltered static is read at the top of `casting._cast_actions` and at every
resolution-time cast. A *filtered* lock cannot be answered there: whether the
seat may cast depends on which spell. So the filter is read where the spell is
known -- `casting._cast_variant`, the one function every offered cast passes
through with the face actually being cast, and the resolution-time floors
(`suspend.cast_for_free`, the "you may cast" offers) with the card they would
cast. Asked about the seat alone, only an unfiltered lock answers yes.

The face being cast is what the filter reads, and two cast variants change it:
a creature card cast for its bestow cost is an **Aura spell**, not a creature
spell (702.103b), so the emblem stops it; a face-down spell is a creature spell
(708.2a) whatever card is underneath.

Cards: `t_noncreature_lock_walker` (the emblem) and `t_noncreature_lock` (the
same line on a permanent), in tests/data/cant_cast_spells_filter.cards.json.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import legality
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import player_cant_cast_spells
from commanderblitz.engine.primitives import give_emblem
from commanderblitz.engine.suspend import cast_for_free
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

WALKER = "t_noncreature_lock_walker"  # its emblem: opponents can't cast noncreature spells
LOCK = "t_noncreature_lock"  # the same line on an enchantment
BOLT = "t_bolt"  # {R} instant
BEAR = "t_bear"  # {1}{G} creature
BESTOWER = "t_bestower"  # {2}{W} creature, bestow {5}{W}
FLASHBACK = "t_flashback_shock"  # {R} instant, flashback {R}


def position(
    builder,
    *,
    emblem: bool = True,
    board0: tuple[str, ...] = (),
    hand0: tuple[str, ...] = (),
    hand1: tuple[str, ...] = (BOLT, BEAR),
    graveyard1: tuple[str, ...] = (),
):
    """Player 0 holds the lock; player 1, whose main phase it is, is named by it.

    Player 1 has mana for everything in hand -- the bestow cost included -- and
    a creature of each side to aim at, so the only thing that can withhold a
    cast is the static.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["mountain", "forest", BEAR, *board0])
        .battlefield(1, ["mountain"] * 2 + ["forest"] * 2 + ["plains"] * 6 + [BEAR])
        .hand(0, list(hand0))
        .hand(1, list(hand1))
        .graveyard(1, list(graveyard1))
        .step(Step.PRECOMBAT_MAIN)
        .active(1)
        .build(advance=False)
    )
    if emblem:
        give_emblem(game.state, WALKER, 0, 0)
    return game


def cast_ids(game, pid: int) -> set[str]:
    """The card of every cast ``pid`` is offered."""
    return {
        game.state.objects[a.source].def_id
        for a in legality._priority_actions(game.state, pid)
        if a.kind is ActionKind.CAST
    }


def in_hand(game, card_id: str) -> int:
    return next(o for o in game.state.players[1].hand if game.state.objects[o].def_id == card_id)


def run(game, op: str, spec, *, controller: int, source: int) -> list:
    """Drive one op to completion, picking the first option of every question."""
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


class TestTheFilter:
    def test_noncreature_spells_are_withheld_and_creatures_are_not(self, builder):
        game = position(builder)
        assert cast_ids(game, 1) == {BEAR}

    def test_without_the_emblem_both_are_offered(self, builder):
        """Pins that the refusal above is the emblem's, not the position's."""
        game = position(builder, emblem=False)
        assert cast_ids(game, 1) == {BEAR, BOLT}

    def test_its_owner_is_unaffected(self, builder):
        """"Your *opponents*": the emblem's owner still casts noncreature spells."""
        game = position(builder, hand0=(BOLT,))
        game.state.active_idx = 0
        assert BOLT in cast_ids(game, 0)

    def test_the_seat_alone_is_not_locked(self, builder):
        """Asked with no spell, a filtered lock says no -- creature spells are open."""
        game = position(builder)
        assert not player_cant_cast_spells(game.state, 1)
        assert player_cant_cast_spells(game.state, 1, game.state.registry.get(BOLT))
        assert not player_cant_cast_spells(game.state, 1, game.state.registry.get(BEAR))


class TestTheSpellAsCast:
    def test_a_bestowed_creature_is_an_aura_spell(self, builder):
        """702.103b: cast for bestow it is an Aura spell, which the emblem stops."""
        game = position(builder, hand1=(BESTOWER,))
        casts = [
            a
            for a in legality._priority_actions(game.state, 1)
            if a.kind is ActionKind.CAST
        ]
        assert casts, "the creature cast is still offered"
        assert not any(a.bestowed for a in casts)

    def test_without_the_emblem_bestow_is_offered(self, builder):
        game = position(builder, emblem=False, hand1=(BESTOWER,))
        assert any(
            a.bestowed
            for a in legality._priority_actions(game.state, 1)
            if a.kind is ActionKind.CAST
        )


class TestEveryZone:
    def test_flashback_from_the_graveyard_is_withheld(self, builder):
        """The filter is read per cast variant, so a graveyard cast meets it too."""
        open_game = position(builder, emblem=False, hand1=(), graveyard1=(FLASHBACK,))
        assert cast_ids(open_game, 1), "flashback is on offer without the emblem"
        game = position(builder, hand1=(), graveyard1=(FLASHBACK,))
        assert cast_ids(game, 1) == set()


class TestResolutionTimeCasts:
    def test_the_free_cast_floor_refuses_a_noncreature_spell(self, builder):
        game = position(builder)
        bolt = in_hand(game, BOLT)
        move_object(game.state, bolt, Zone.EXILE, to_player=1)
        assert cast_for_free(game.state, 1, bolt) is False
        assert game.state.objects[bolt].zone is Zone.EXILE

    def test_the_free_cast_floor_lets_a_creature_through(self, builder):
        game = position(builder)
        bear = in_hand(game, BEAR)
        move_object(game.state, bear, Zone.EXILE, to_player=1)
        assert cast_for_free(game.state, 1, bear) is True
        assert [item.def_id for item in game.state.stack] == [BEAR]

    def test_cast_from_hand_offers_only_what_may_be_cast(self, builder):
        """A "cast a spell from your hand" offer does not list the locked card."""
        game = position(builder)
        spec = {"op": "cast_from_hand", "player": "you"}
        asked = run(game, "cast_from_hand", spec, controller=1, source=only_oid(game, BEAR, 1))
        assert asked, "the creature was offered"
        assert [item.def_id for item in game.state.stack] == [BEAR]


class TestTheWearingOff:
    def test_a_permanent_lock_lifts_when_it_leaves(self, builder):
        game = position(builder, emblem=False, board0=(LOCK,))
        assert cast_ids(game, 1) == {BEAR}
        move_object(game.state, only_oid(game, LOCK), Zone.GRAVEYARD)
        assert cast_ids(game, 1) == {BEAR, BOLT}


class TestTheLoader:
    def _card(self, **static) -> dict:
        return {
            "id": "t_bad_lock",
            "name": "Test Bad Lock",
            "oracle_text": "Your opponents can't cast noncreature spells.",
            "mana_cost": "{1}{W}",
            "types": ["Enchantment"],
            "abilities": [
                {
                    "kind": "static",
                    "text": "Your opponents can't cast noncreature spells.",
                    "effect": "cant_cast_spells",
                    "affects_player": "opponent",
                    **static,
                }
            ],
        }

    def test_a_spell_filter_loads(self):
        compile_card(
            CardModel.model_validate(self._card(affects_spells={"not_types": ["Creature"]}))
        )

    def test_a_permanent_filter_is_still_refused(self):
        with pytest.raises(DslError, match="affects_spells"):
            compile_card(CardModel.model_validate(self._card(affects={"types": ["Creature"]})))

    def test_a_controller_key_is_refused(self):
        """`affects_player` already says whose casts; a second answer could contradict it."""
        card = self._card(affects_spells={"controller": "you", "not_types": ["Creature"]})
        with pytest.raises(DslError, match="controller"):
            compile_card(CardModel.model_validate(card))

    def test_a_board_state_key_is_refused(self):
        card = self._card(affects_spells={"tapped": True})
        with pytest.raises(DslError, match="tapped"):
            compile_card(CardModel.model_validate(card))
