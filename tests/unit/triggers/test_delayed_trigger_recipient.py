"""A delayed trigger scoped to the permanent being **hit**.

    "+1: Until your next turn, whenever a creature deals combat damage to
    Vraska the Unseen, destroy that creature."      -- Vraska the Unseen

`subject` scopes a delayed trigger to the **dealer** -- Hunter's Insight's "that
creature". Vraska's +1 is the other end of the same hit: any creature, but only
when it hits *her*. Without the scope, `deals_combat_damage_to_planeswalker`
with `controller: "any"` fires on every planeswalker hit on the table, and
destroying whatever hit a different planeswalker is a strictly different card.

`recipient` is resolved as the ability is created, like `subject`, and compared
against the event's recipient key (`triggers.RECIPIENT_KEYS` -- ``planeswalker``
on this event). The subject stays the dealer, so "destroy that creature" is
``{"binding": "subject"}``. A recipient that leaves the battlefield is released
the way a subject is (400.7): a Vraska recast later is a new object.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_permanent
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of, only_oid, pass_until

WALKER = "t_walker"  # a 4-loyalty planeswalker -- Vraska
OTHER = "t_emblem_walker"  # a second, differently named planeswalker
BEAR = "t_bear"  # 2/2

PLUS_ONE = {
    "op": "delayed_trigger",
    "duration": "until_your_next_turn",
    "text": "Until your next turn, whenever a creature deals combat damage to Vraska the "
    "Unseen, destroy that creature.",
    "trigger": {
        "event": "deals_combat_damage_to_planeswalker",
        "controller": "any",
        "recipient": {"self_only": True},
    },
    "effects": [{"op": "destroy", "objects": {"binding": "subject"}}],
}


def board(builder):
    """Player 0 has two planeswalkers; player 1 has two Bears.

    Returns ``(game, vraska, other_walker, bears)``.
    """
    game = (
        builder(players=2)
        .battlefield(0, [WALKER, OTHER])
        .battlefield(1, [BEAR, BEAR])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return (
        game,
        only_oid(game, WALKER, 0),
        only_oid(game, OTHER, 0),
        sorted(oids_of(game, BEAR, 1)),
    )


def plus_one(game, vraska: int) -> None:
    ctx = EffectContext(state=game.state, controller=0, source_oid=vraska)
    list(execute(ctx, [PLUS_ONE]))


def hit(game, dealer: int, walker: int, *, combat: bool = True) -> None:
    damage_permanent(game.state, walker, 1, dealer, is_combat=combat)
    pass_until(
        game,
        lambda g: not g.state.armed_delays
        and not g.state.stack
        and not g.state.pending_triggers,
    )


def alive(game, oid: int) -> bool:
    return game.state.objects[oid].zone is Zone.BATTLEFIELD


class TestTheScope:
    def test_a_creature_that_hits_vraska_is_destroyed(self, builder):
        game, vraska, _, bears = board(builder)
        plus_one(game, vraska)
        hit(game, bears[0], vraska)
        assert not alive(game, bears[0])
        assert alive(game, bears[1])

    def test_it_fires_for_every_creature(self, builder):
        game, vraska, _, bears = board(builder)
        plus_one(game, vraska)
        hit(game, bears[0], vraska)
        hit(game, bears[1], vraska)
        assert not alive(game, bears[0]) and not alive(game, bears[1])

    def test_a_hit_on_another_planeswalker_is_not_hers(self, builder):
        """The whole of the scope: unscoped, this destroys the Bear."""
        game, vraska, other, bears = board(builder)
        plus_one(game, vraska)
        hit(game, bears[0], other)
        assert alive(game, bears[0])

    def test_noncombat_damage_is_not_combat_damage(self, builder):
        game, vraska, _, bears = board(builder)
        plus_one(game, vraska)
        hit(game, bears[0], vraska, combat=False)
        assert alive(game, bears[0])


class TestWhenVraskaLeaves:
    def test_the_subscription_goes_with_her(self, builder):
        """A Vraska that returns is a new object (400.7), and her old +1 is not hers."""
        game, vraska, _, bears = board(builder)
        plus_one(game, vraska)
        move_object(game.state, vraska, Zone.GRAVEYARD)
        assert game.state.delayed_triggers == []
        move_object(game.state, vraska, Zone.BATTLEFIELD)
        hit(game, bears[0], vraska)
        assert alive(game, bears[0])


class TestTheLoader:
    @staticmethod
    def _card(trigger: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_rcp_walker",
                "name": "Test Recipient Walker",
                "mana_cost": "{2}{B}",
                "types": ["Sorcery"],
                "oracle_text": PLUS_ONE["text"],
                "spell_effects": [{**PLUS_ONE, "trigger": trigger}],
            }
        )

    def test_the_recipient_scope_loads(self):
        compile_card(self._card(PLUS_ONE["trigger"]))

    def test_an_event_with_no_recipient_is_refused(self):
        with pytest.raises(DslError, match="no recipient"):
            compile_card(
                self._card(
                    {"event": "deals_combat_damage_to_player", "recipient": {"self_only": True}}
                )
            )

    def test_a_recipient_naming_nothing_is_refused(self):
        with pytest.raises(DslError, match="permanent being hit"):
            compile_card(
                self._card(
                    {
                        "event": "deals_combat_damage_to_planeswalker",
                        "recipient": {"types": ["Planeswalker"]},
                    }
                )
            )

