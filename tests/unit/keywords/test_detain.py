"""Detain (701.30a): three restrictions, one word, and an unusual lifetime.

"Until your next turn, that permanent can't attack or block and its activated
abilities can't be activated." The census routes it as "`lock_abilities` and
`cant_attack` exist separately; needs them bundled until a player's next turn",
and the bundling is the smaller half. The lifetime is the interesting one.

**It outlives the turn it was cast in.** `until_eot` is wiped at cleanup, so a
detain built on a `TempEffect` would expire the moment the turn ended —
usually before the detained creature would ever have attacked. That is a
strictly worse card than the printed one, and nothing about it would look
wrong. So detain is a field on the object, for the same reason `must_attack`
is: both have to survive cleanup.

**It records who, not when.** "Your next turn" is not a fixed turn number —
eliminate a player and it moves. The untap step clears the detain belonging to
whoever is untapping, which says that sentence once in the one place it can be
right, exactly as `frozen_by` names a permanent rather than a duration.

One op rather than three, because detain is one printed word and the authoring
verifier asks each *ability* which sentence it implements. Three ops would read
as three claims on one line, and a card that got two of the three would look
implemented.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import _default_answer, only_oid, pass_until

DETAINER = "t_detainer"  # {1}{W} sorcery: detain target creature an opponent controls
BEAR = "t_bear"
DORK = "t_dork"  # 1/1 creature with an activated ability


def position(builder, victim=BEAR):
    game = (
        builder(players=2)
        .hand(0, [DETAINER])
        .battlefield(0, ["plains", "plains"])
        .battlefield(1, [victim])
        .build()
    )
    return game, only_oid(game, victim, 1)


def cast_detain(game, victim: int) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and TargetRef.obj(victim) in a.targets
    )
    game.apply(action)
    for _ in range(30):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the detain never resolved")


class TestItRestrictsAllThree:
    def test_it_cannot_attack(self, builder):
        """Asserted against `can_attack` with the victim's controller made
        active, rather than by driving to their combat: resolving the detain
        already carries the game into that turn, and driving further reaches
        the *next* one — where player 0's untap has correctly ended it. The
        clearing is a separate claim, tested below."""
        game, victim = position(builder)
        cast_detain(game, victim)
        game.state.active_idx = 1
        assert not combat_mod.can_attack(game.state, victim)
        game.state.objects[victim].detained_by = None
        assert combat_mod.can_attack(game.state, victim), (
            "the detain is the only thing stopping it"
        )

    def test_it_cannot_block(self, builder):
        game, victim = position(builder)
        cast_detain(game, victim)
        assert not combat_mod.can_block(game.state, victim, victim, 1), (
            "detained, so it is not a legal blocker of anything"
        )

    def test_its_activated_abilities_are_locked(self, builder):
        game, victim = position(builder, victim=DORK)
        cast_detain(game, victim)
        assert game.state.objects[victim].abilities_locked

    def test_an_undetained_creature_is_unaffected(self, builder):
        game = (
            builder(players=2)
            .battlefield(1, [BEAR])
            .build()
        )
        oid = only_oid(game, BEAR, 1)
        assert not game.state.objects[oid].abilities_locked
        assert game.state.objects[oid].detained_by is None


class TestTheLifetime:
    def test_it_survives_the_turn_it_was_cast_in(self, builder):
        """The failure a `TempEffect` would have: cleanup wipes `until_eot`,
        so the detain would end before the creature would ever have attacked.
        """
        game, victim = position(builder)
        cast_detain(game, victim)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.objects[victim].detained_by == 0

    def test_it_ends_on_the_detaining_players_next_turn(self, builder):
        """Cleared by *that player's* untap step, not by a turn count."""
        game, victim = position(builder)
        cast_detain(game, victim)
        pass_until(
            game,
            lambda g: g.state.turn >= 3
            and g.state.active_player == 0
            and g.state.step >= Step.PRECOMBAT_MAIN,
        )
        assert game.state.objects[victim].detained_by is None

    def test_the_victims_own_turn_does_not_end_it(self, builder):
        """The turn in between is exactly the one the card is bought for."""
        game, victim = position(builder)
        cast_detain(game, victim)
        pass_until(
            game,
            lambda g: g.state.active_player == 1 and g.state.step >= Step.PRECOMBAT_MAIN,
        )
        assert game.state.objects[victim].detained_by == 0


class TestTheLoaderGuardsIt:
    def test_detain_without_objects_is_refused(self):
        with pytest.raises(DslError, match="needs 'objects'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "oracle_text": "x",
                        "mana_cost": "{W}",
                        "types": ["Sorcery"],
                        "spell_effects": [{"op": "detain"}],
                    }
                )
            )

    def test_the_detain_card_compiles(self, registry):
        card = registry.get(DETAINER)
        assert [e["op"] for e in card.spell_effects] == ["detain"]
