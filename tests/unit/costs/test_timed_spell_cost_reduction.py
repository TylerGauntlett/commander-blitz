"""A discount on every matching spell for the rest of the turn, owned by the player.

    "Whenever this creature attacks, instant and sorcery spells you cast this
    turn cost {1} less to cast."                    -- Spellbinding Soprano

Rule 611.2a: a continuous effect from a resolving ability lasts as long as the
ability says -- here "this turn" -- and does not depend on its source staying
on the battlefield. Neither existing shape says it. `next_spell_cost_reduction`
alone is single-use, so the second instant of the turn would pay full price.
The `spell_cost_reduction` static covers every spell but only while a permanent
carries it, so granting it to the Soprano "until end of turn" would end the
discount the moment the attacker dies in combat -- exactly when a player wants
to cast the burn spell the discount was for.

`every_spell: true` writes the same `structs.NextSpellDiscount` row with
``next_spell`` false: read by `cost_reduction.cost_reduction` like the one-shot,
never spent by a cast, and swept at cleanup with the rest of the table.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.cost_reduction import cost_reduction
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import find_action, only_oid, pass_until, settle_to_priority

SOPRANO = "t_soprano"  # whenever it attacks: instants and sorceries cost {1} less this turn
CANCEL = "cancel"  # {1}{U}{U} instant
OPT = "opt"  # {U} instant
DIVINATION = "divination"  # {2}{U} sorcery
BEARS = "grizzly_bears"  # {1}{G} creature


def position(builder, hand=()):
    """Seat 0 in their precombat main with the Soprano, lands, and spells in hand.

    Two Opts so there is always a spell in hand to stop the auto-pass at the
    player's priority, however many are cast.
    """
    game = (
        builder(players=2)
        .battlefield(0, [SOPRANO, "island", "island", "island", "island", "forest", "forest"])
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .hand(0, [*hand, OPT, OPT])
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    return game, only_oid(game, SOPRANO, 0)


def attack(game, oid: int) -> None:
    """Declare the Soprano on seat 1 and let its trigger resolve."""
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(
        find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),))
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers and bool(
        g.state.next_spell_discounts
    ))


def discount_on(game, registry, card_id: str) -> int:
    return cost_reduction(game.state, 0, registry.get(card_id))


def cast(game, card_id: str) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    settle_to_priority(game)


class TestItStartsWithTheAttack:
    def test_nothing_before_the_attack(self, builder, registry):
        """The control: the Soprano standing there discounts nothing."""
        game, _ = position(builder)

        assert discount_on(game, registry, CANCEL) == 0

    def test_the_attack_discounts_instants_and_sorceries(self, builder, registry):
        game, oid = position(builder)
        attack(game, oid)

        assert discount_on(game, registry, CANCEL) == 1
        assert discount_on(game, registry, DIVINATION) == 1

    def test_a_creature_spell_is_not_discounted(self, builder, registry):
        game, oid = position(builder)
        attack(game, oid)

        assert discount_on(game, registry, BEARS) == 0


class TestItCoversEverySpellThisTurn:
    def test_a_cast_does_not_spend_it(self, builder, registry):
        """The boundary with `next_spell_cost_reduction`: after one instant the
        next one is still {1} cheaper."""
        game, oid = position(builder)
        attack(game, oid)
        cast(game, OPT)

        assert discount_on(game, registry, CANCEL) == 1

    def test_a_sorcery_after_combat_is_charged_the_discounted_price(self, builder):
        """{1} off Divination's {2}{U} leaves {1}{U}: two lands tap for it, and
        "this turn" reaches past combat into the second main phase."""
        game, oid = position(builder, hand=[DIVINATION])
        attack(game, oid)
        pass_until(
            game,
            lambda g: g.state.step is Step.POSTCOMBAT_MAIN
            and g.pending() is not None
            and g.pending().kind is DecisionKind.PRIORITY
            and g.pending().player == 0,
        )
        cast(game, DIVINATION)
        lands = [
            o for o in game.state.battlefield
            if game.state.objects[o].def_id in ("island", "forest")
        ]

        assert sum(game.state.objects[o].tapped for o in lands) == 2

    def test_it_persists_after_the_source_leaves(self, builder, registry):
        """611.2a: the Soprano dying in combat does not end the discount."""
        game, oid = position(builder)
        attack(game, oid)
        move_object(game.state, oid, Zone.GRAVEYARD)

        assert discount_on(game, registry, CANCEL) == 1


class TestItWearsOff:
    def test_it_is_gone_next_turn(self, builder, registry):
        game, oid = position(builder)
        attack(game, oid)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)

        assert discount_on(game, registry, CANCEL) == 0
        assert not game.state.next_spell_discounts


class TestTheLoaderPlacesIt:
    def test_a_non_boolean_every_spell_is_refused(self):
        card = CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "{T}: Spells you cast this turn cost {1} less to cast.",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "{T}: Spells you cast this turn cost {1} less to cast.",
                        "cost": {"tap": True},
                        "effects": [
                            {
                                "op": "next_spell_cost_reduction",
                                "amount": {"const": 1},
                                "every_spell": "yes",
                            }
                        ],
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="'every_spell' is true or false"):
            compile_card(card)
