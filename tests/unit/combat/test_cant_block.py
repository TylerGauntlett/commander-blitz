"""Unleash (702.86), and the `cant_block` static it was waiting on.

The census had unleash as `routed` with the gap named exactly: "enters with a
counter is whitelisted, but there is no `cant_block` static to pair with it".
Half the keyword had been expressible since the enters-with-counters
replacement shipped, and the other half had nowhere to live.

`cant_block` is the mirror of `cant_attack`, down to reusing `_matches` for its
filter, and it is a **static** rather than a `Keyword` for the reason
`block_restriction` and `lock_abilities` are: a keyword is a characteristic, and
this is a permission. Nothing reads it through `chars`, and putting it in a
creature's keyword list would be a lie about what the card says.

It is checked in `can_block` rather than in `blocks_valid`, which is the
difference between it and menace: this is a fact about one creature, not about
the shape of the whole declaration, so a creature under it is never offered as a
blocker in the first place.

The conditional half -- "as long as it has a +1/+1 counter on it" -- needed
nothing new. Static abilities have taken a `counters` condition leaf since
Arixmethes, and that is exactly the shape unleash wants.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import block_forbidden
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until

UNLEASHED = "t_unleashed"  # 2/2, can't block while it has a +1/+1 counter
BEAR = "t_bear"


def position(builder, *, counters: dict | None = None):
    """The unleashed creature on player 1's side, facing an attacker."""
    game = (
        builder(players=2)
        .battlefield(0, [BEAR])
        .battlefield(1, [UNLEASHED], counters=counters or {})
        .build()
    )
    return game, only_oid(game, UNLEASHED, 1)


def block_options(game) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.ADD_BLOCKER]


def to_blockers(game, attacker: int) -> None:
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    game.apply(
        find_action(game, ActionKind.ADD_ATTACKER, source=attacker, targets=(TargetRef.player(1),))
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS)


class TestTheStatic:
    def test_with_the_counter_it_cannot_block(self, builder):
        game, oid = position(builder, counters={"+1/+1": 1})
        assert block_forbidden(game.state, oid)

    def test_without_the_counter_it_can(self, builder):
        """The boundary the whole keyword turns on: unleash is a choice, and
        declining it leaves an ordinary creature."""
        game, oid = position(builder)
        assert not block_forbidden(game.state, oid)

    def test_a_creature_with_no_such_static_is_unaffected(self, builder):
        game, _ = position(builder, counters={"+1/+1": 1})
        assert not block_forbidden(game.state, only_oid(game, BEAR, 0))

    def test_removing_the_counter_gives_the_block_back(self, builder):
        """It is a static read live, not a flag written once."""
        game, oid = position(builder, counters={"+1/+1": 1})
        assert block_forbidden(game.state, oid)
        game.state.objects[oid].counters = {}
        game.state.bump_chars()
        assert not block_forbidden(game.state, oid)


class TestItIsEnforcedInCombat:
    def test_it_is_not_offered_as_a_blocker(self, builder):
        game, _ = position(builder, counters={"+1/+1": 1})
        to_blockers(game, only_oid(game, BEAR, 0))
        assert block_options(game) == [], (
            "checked in `can_block`, so it is never offered -- unlike menace, "
            "which is a fact about the whole declaration"
        )

    def test_without_the_counter_it_is_offered(self, builder):
        game, oid = position(builder)
        to_blockers(game, only_oid(game, BEAR, 0))
        assert [a for a in block_options(game) if a.source == oid]


class TestTheLoaderKnowsIt:
    def test_the_unleash_card_compiles(self, registry):
        card = registry.get(UNLEASHED)
        (static,) = [a for a in card.abilities if a.is_static]
        assert (static.static or {}).get("effect") == "cant_block"

    def test_an_unknown_static_is_still_refused(self):
        with pytest.raises(DslError, match="unknown static effect"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "oracle_text": "x",
                        "mana_cost": "{B}",
                        "types": ["Creature"],
                        "power": 1,
                        "toughness": 1,
                        "abilities": [
                            {
                                "kind": "static",
                                "text": "x",
                                "effect": "cant_block_ever",
                                "affects": {"self_only": True},
                            }
                        ],
                    }
                )
            )
