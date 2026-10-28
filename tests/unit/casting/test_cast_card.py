"""A paid cast during a resolution, and the casting lock it may leave behind.

Conduit of Worlds: "{T}: Choose target nonland permanent card in your
graveyard. If you haven't cast a spell this turn, you may cast that card. If you
do, you can't cast additional spells this turn. Activate only as a sorcery."

608.2g and 601.2: the card is cast while the ability resolves -- it goes on the
stack, its cast triggers fire, and it counts toward the turn's spells -- and
nothing waives its price, so the caster pays its mana cost (601.2f-h). Every
"you may cast" the engine had was free (`suspend.cast_for_free`), and a free
Conduit is a strictly better card; `grant_playable` leaves a permission to use
later, which "if you do" could not read as the ability resolves. So
`cast_card` makes the cast at the card's price, with the adjustments the cast
line makes -- targets asked, X announced, cost reductions -- and records what
was actually cast.

"You can't cast additional spells this turn" is a player-wide, total
prohibition with a clock, installed by a resolving ability. The static of that
name lasts as long as its permanent; `cant_cast_spells_from_zones` is
zone-filtered and leaves the cast of a copy (707.12) open. `cant_cast_spells`
the op writes a `CastLock` shutting every zone, which
`player_cant_cast_spells` reads as total (101.2: the "can't" beats every
"may").
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import (
    player_cant_cast_spells,
    player_cant_cast_while_resolving,
)
from tests.conftest import (
    activations,
    declare_targets,
    find_action,
    oids_of,
    only_oid,
    pass_until,
    plus_one_counters,
    settle,
)

CONDUIT = "t_cc_conduit"


def position(builder, *, graveyard=("t_bear",), lands=("forest", "forest"), mine=(), theirs=()):
    """Player 0's Conduit, ``lands`` untapped and ``graveyard``; a Bear and a
    Forest in hand, so a priority window with nothing cast still has a play in
    it and the engine does not pass it on the player's behalf.

    Returns ``(game, conduit)``."""
    game = (
        builder(players=2)
        .battlefield(0, [CONDUIT, *lands, *mine])
        .battlefield(1, list(theirs))
        .graveyard(0, list(graveyard))
        .hand(0, ["t_bear", "forest"])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .build()
    )
    return game, only_oid(game, CONDUIT, 0)


def activate(game, conduit) -> None:
    """Activate the Conduit and pass until its resolution asks something."""
    game.apply(activations(game, conduit)[0])
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().kind is not DecisionKind.PRIORITY,
    )


def resolve_unasked(game, conduit) -> None:
    """Activate the Conduit and resolve it, failing if it ever offers the cast."""
    game.apply(activations(game, conduit)[0])
    for _ in range(20):
        if not game.state.stack:
            return
        assert game.pending().kind is DecisionKind.PRIORITY, game.pending().prompt
        game.apply(find_action(game, ActionKind.PASS))
    raise AssertionError("the Conduit never resolved")


def offered(game) -> bool:
    decision = game.pending()
    return decision is not None and decision.kind is DecisionKind.MAY


def bear_casts(game) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].zone is Zone.HAND
    ]


def graveyard_ids(game, pid: int = 0) -> list[str]:
    return [game.state.objects[oid].def_id for oid in game.state.players[pid].graveyard]


class TestThePaidCast:
    def test_yes_casts_the_card_at_its_mana_cost(self, builder):
        game, conduit = position(builder)
        activate(game, conduit)
        assert offered(game)
        before = len(game.state.events)
        game.apply(find_action(game, ActionKind.YES))
        cast = [e for e in game.state.events[before:] if e.type == "spell_cast"]
        assert len(cast) == 1
        # Not free: a real payment, and no `free` flag on the cast.
        assert not cast[0].data.get("free")
        assert any(e.type == "mana_spent" for e in game.state.events[before:])
        settle(game)
        assert len(oids_of(game, "t_bear", 0)) == 1
        assert "t_bear" not in graveyard_ids(game)
        forests = oids_of(game, "forest", 0)
        assert sum(game.state.objects[oid].tapped for oid in forests) == 2

    def test_it_counts_as_a_spell_cast_this_turn(self, builder):
        game, conduit = position(builder)
        activate(game, conduit)
        game.apply(find_action(game, ActionKind.YES))
        assert game.state.turn_ledger.spells_cast.get(0) == 1

    def test_unpayable_is_not_offered(self, builder):
        game, conduit = position(builder, lands=("forest",))
        resolve_unasked(game, conduit)
        assert graveyard_ids(game) == ["t_bear"]
        assert game.state.cast_locks == []

    def test_declining_casts_nothing_and_locks_nothing(self, builder):
        game, conduit = position(builder)
        activate(game, conduit)
        game.apply(find_action(game, ActionKind.NO))
        settle(game)
        assert graveyard_ids(game) == ["t_bear"]
        assert bear_casts(game), "declined: the hand is still open"


class TestIfYouHaventCastASpell:
    def test_a_spell_already_cast_this_turn_closes_the_offer(self, builder):
        game, conduit = position(builder, lands=("forest",) * 4)
        game.apply(bear_casts(game)[0])
        settle(game)
        resolve_unasked(game, conduit)
        assert graveyard_ids(game) == ["t_bear"]


class TestTheLock:
    def cast_through(self, builder):
        game, conduit = position(builder, lands=("forest",) * 4)
        activate(game, conduit)
        game.apply(find_action(game, ActionKind.YES))
        settle(game)
        return game

    def test_no_additional_spell_this_turn(self, builder):
        game = self.cast_through(builder)
        # Two Forests untapped and a Bear in hand: affordable, and refused.
        assert sum(not game.state.objects[o].tapped for o in oids_of(game, "forest", 0)) == 2
        assert bear_casts(game) == []
        assert player_cant_cast_spells(game.state, 0)

    def test_the_lock_is_total_copies_included(self, builder):
        # 707.12: casting a copy is casting, and a copy has no zone for a zone
        # lock to compare -- the reason the lock is read as total.
        game = self.cast_through(builder)
        assert player_cant_cast_while_resolving(game.state, 0)

    def test_only_the_caster_is_locked(self, builder):
        game = self.cast_through(builder)
        assert not player_cant_cast_spells(game.state, 1)

    def test_it_wears_off_with_the_turn(self, builder):
        game = self.cast_through(builder)
        pass_until(game, lambda g: g.state.active_player == 1)
        assert game.state.cast_locks == []
        assert not player_cant_cast_spells(game.state, 0)


class TestTheCastAsks:
    def test_an_aura_asks_for_its_target(self, builder):
        game, conduit = position(
            builder,
            graveyard=("t_big_aura",),
            lands=("plains",) * 5,
            mine=("t_bear",),
            theirs=("t_bear",),
        )
        theirs = only_oid(game, "t_bear", 1)
        activate(game, conduit)
        game.apply(find_action(game, ActionKind.YES))
        assert game.pending().kind is DecisionKind.CHOOSE_OBJECTS
        assert {o.ref.id for o in game.pending().options} == {
            only_oid(game, "t_bear", 0),
            theirs,
        }
        declare_targets(game, theirs)
        settle(game)
        aura = next(
            oid for oid in game.state.battlefield if game.state.objects[oid].def_id == "t_big_aura"
        )
        assert game.state.objects[aura].attached_to == theirs

    def test_x_is_announced(self, builder):
        game, conduit = position(builder, graveyard=("t_x_hydra",), lands=("forest",) * 4)
        activate(game, conduit)
        game.apply(find_action(game, ActionKind.YES))
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X
        # {X}{G} off four Forests: X runs 0..3.
        assert [o.value for o in decision.options] == [0, 1, 2, 3]
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 2)
        )
        settle(game)
        hydra = only_oid(game, "t_x_hydra", 0)
        assert plus_one_counters(game, hydra) == 2


class TestSilence:
    """The opponents-facing form: "Your opponents can't cast spells this turn"."""

    def test_opponents_locked_caster_free_until_cleanup(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", "forest", "forest"])
            .hand(0, ["t_cc_silence", "t_bear"])
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .build()
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == "t_cc_silence"
            )
        )
        settle(game)
        assert player_cant_cast_spells(game.state, 1)
        assert not player_cant_cast_spells(game.state, 0)
        assert bear_casts(game)
        pass_until(game, lambda g: g.state.active_player == 1 and g.state.step is Step.UPKEEP)
        assert not player_cant_cast_spells(game.state, 1)


class TestTheLoaderGuards:
    def _card(self, effects: list[dict]) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_cc_probe",
                "name": "Test Cast Card Probe",
                "mana_cost": "{2}",
                "types": ["Sorcery"],
                "oracle_text": "Probe.",
                "spell_effects": effects,
            }
        )

    def test_the_printed_forms_load(self):
        compile_card(
            self._card(
                [
                    {"op": "cast_card", "objects": {"binding": "x"}, "as": "cast"},
                    {"op": "cant_cast_spells", "player": "you", "duration": "this_turn"},
                ]
            )
        )

    @pytest.mark.parametrize(
        "effect",
        [
            {"op": "cast_card"},
            {"op": "cast_card", "objects": {"binding": "x"}, "free": True},
            {"op": "cant_cast_spells", "player": "you"},
            {"op": "cant_cast_spells", "duration": "this_turn"},
            {"op": "cant_cast_spells", "player": "you", "duration": "forever"},
            {
                "op": "cant_cast_spells",
                "player": "you",
                "duration": "this_turn",
                "zones": ["hand"],
            },
        ],
    )
    def test_malformed_forms_are_refused(self, effect):
        with pytest.raises(DslError):
            compile_card(self._card([effect]))
