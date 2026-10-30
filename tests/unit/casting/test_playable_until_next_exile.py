"""A "you may play it" permission ended by the source's next exile, not by a clock.

    Whenever you cast a spell with mana value 4 or greater, you may exile the
    top card of your library. If you do, you may play that card until you exile
    another card with this creature.  (Superior Foes of Spider-Man)

Every other `playable` duration ends on a turn boundary or never. This one ends
when *this creature* exiles another card, so only the latest card it exiled is
playable. `while_exiled` is the near miss: every card the creature ever exiled
would stay playable, which is a strictly stronger card than printed.

The end is tied to the object (400.7). Once the creature leaves the battlefield
nothing can exile "another card with this creature", so the last card it exiled
stays playable for as long as it stays exiled -- and the creature coming back
is a new object whose exiles end only its own grants.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLAYABLE_DURATIONS
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

FOES = "t_foes_impulse"
BIG = "t_foes_big_spell"
OTHER = "t_brain_impulse"  # an instant that exiles with a permission of its own


def position(builder):
    """Seat 0 controls the creature and holds three four-drops and an impulse.

    The library is lands, which need no mana: the permission is the only thing
    that makes playing one legal, so `legal_actions` answers whether it stands.
    """
    return (
        builder(players=2)
        .battlefield(0, [FOES] + ["mountain"] * 16)
        .battlefield(1, ["mountain"] * 4)
        .library(0, ["mountain"] * 20)
        .library(1, ["mountain"] * 20)
        .hand(0, [BIG, BIG, BIG, OTHER])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def settle(game) -> None:
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def cast(game, def_id: str) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
        )
    )
    settle(game)


def exiled(game) -> list[int]:
    return list(game.state.players[0].exile)


def playable(game, oid: int) -> bool:
    return any(a.source == oid for a in game.legal_actions())


def foes(game) -> int:
    return next(o.oid for o in game.state.objects.values() if o.def_id == FOES)


def started(builder):
    game = position(builder)
    game._advance()
    return game


class TestTheLatestCardOnly:
    def test_it_is_a_known_duration(self):
        assert "until_next_exile_by_source" in PLAYABLE_DURATIONS

    def test_the_first_card_is_playable(self, builder):
        game = started(builder)
        cast(game, BIG)
        [first] = exiled(game)
        assert playable(game, first)
        assert game.state.objects[first].playable_source == foes(game)

    def test_a_second_exile_ends_the_first_and_grants_the_second(self, builder):
        game = started(builder)
        cast(game, BIG)
        [first] = exiled(game)
        cast(game, BIG)
        [second] = [oid for oid in exiled(game) if oid != first]
        assert not playable(game, first)
        assert game.state.objects[first].playable_by is None
        assert playable(game, second)

    def test_another_sources_exile_does_not_end_it(self, builder):
        game = started(builder)
        cast(game, BIG)
        [first] = exiled(game)
        cast(game, OTHER)
        assert len(exiled(game)) == 2
        assert playable(game, first)

    def test_it_lasts_across_turns(self, builder):
        game = started(builder)
        cast(game, BIG)
        [first] = exiled(game)
        turn = game.state.turn
        for seat in (1, 0):
            pass_until(
                game,
                lambda g, seat=seat: g.state.step is Step.PRECOMBAT_MAIN
                and g.state.active_player == seat
                and g.state.turn > turn,
            )
        assert game.state.objects[first].zone is Zone.EXILE
        assert playable(game, first)


class TestTheCreatureLeaving:
    def test_the_last_card_stays_playable(self, builder):
        game = started(builder)
        cast(game, BIG)
        cast(game, BIG)
        last = exiled(game)[-1]
        move_object(game.state, foes(game), Zone.GRAVEYARD)
        assert playable(game, last)

    def test_the_creature_back_is_a_new_object_that_cannot_end_it(self, builder):
        """400.7: the returned creature's exile is not "another card with this creature"."""
        game = started(builder)
        cast(game, BIG)
        [first] = exiled(game)
        oid = foes(game)
        move_object(game.state, oid, Zone.GRAVEYARD)
        move_object(game.state, oid, Zone.BATTLEFIELD)
        cast(game, BIG)
        [second] = [o for o in exiled(game) if o != first]
        assert playable(game, first)
        assert playable(game, second)
        # ...and the new object's own next exile still ends its own grant.
        cast(game, BIG)
        assert not playable(game, second)
        assert playable(game, first)

    def test_a_card_that_leaves_exile_loses_it(self, builder):
        game = started(builder)
        cast(game, BIG)
        [first] = exiled(game)
        move_object(game.state, first, Zone.GRAVEYARD)
        obj = game.state.objects[first]
        assert obj.playable_by is None
        assert obj.playable_source is None


class TestTheLoader:
    def spell(self, effect):
        return {
            "id": "t_probe_until_next",
            "name": "Probe Until Next",
            "mana_cost": "{R}",
            "types": ["Instant"],
            "spell_effects": [effect],
        }

    def compile(self, effect):
        return compile_card(CardModel.model_validate(self.spell(effect)))

    def test_exile_accepts_it(self):
        self.compile({"op": "exile", "objects": {"zone": "graveyard", "count": 1},
                      "playable": "until_next_exile_by_source"})

    def test_grant_playable_over_exile_accepts_it(self):
        self.compile({"op": "grant_playable",
                      "objects": {"zone": "exile", "controller": "any", "count": "all"},
                      "playable": "until_next_exile_by_source"})

    def test_look_at_top_into_a_hand_refuses_it(self):
        with pytest.raises(DslError, match="until_next_exile_by_source"):
            self.compile({"op": "look_at_top", "player": "you", "amount": {"const": 1},
                          "objects": {"count": 1}, "destination": "hand",
                          "playable": "until_next_exile_by_source"})
