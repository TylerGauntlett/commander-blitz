"""A cast made during a resolution, priced in life rather than mana.

Anrakyr the Traveller: "Whenever Anrakyr the Traveller attacks, you may cast an
artifact spell from your hand or graveyard by paying life equal to its mana
value rather than paying its mana cost."

The cast happens while the attack trigger resolves (608.2g), so timing is
ignored: a non-flash artifact is cast in the declare-attackers step. The price
is an alternative cost (118.9). `cast_from_hand` already cast at resolution but
only for free, which would make the card strictly better; `grant_playable`'s
`playable_pay_life_instead` has the right price but leaves a permission for a
later priority window, which a sorcery-speed artifact cannot use in combat. So
`cast_from_hand` takes `pay_life_instead`:

- the life is the mana value with X at 0 (107.3b);
- a card whose life the player cannot pay is not offered (119.4);
- a tax is still owed on top of the life (601.2f), as generic mana;
- the cast is real: the spell goes on the stack and resolves.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from tests.conftest import pass_until

ANRAKYR = {
    "op": "cast_from_hand",
    "zones": ["hand", "graveyard"],
    "selector": {"types": ["Artifact"]},
    "pay_life_instead": True,
}


def a_table(builder, *, hand=(), graveyard=(), lands=0, theirs=(), life=None):
    """Player 0 with ``lands`` Plains and the given cards; player 1 with ``theirs``."""
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * lands)
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .graveyard(0, list(graveyard))
        .build()
    )
    if life is not None:
        game.state.players[0].life = life
    return game


def offer(game, spec=ANRAKYR, *, take: str | None = None) -> list[int]:
    """Resolve the op for player 0; return the oids offered, taking ``take`` if named."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = OPS[spec["op"]](ctx, spec)
    offered: list[int] = []
    answer = None
    first = True
    while True:
        try:
            decision = gen.send(answer)
        except StopIteration:
            break
        options = [option.value for option in decision.options]
        if first:
            offered = options
            first = False
            wanted = [
                i
                for i, oid in enumerate(options)
                if take is not None and game.state.objects[oid].def_id == take
            ]
            answer = wanted[:1]
        else:
            # Anything after the pick (a mana payment) takes its first option.
            answer = [0]
    return offered


def ids(game, oids) -> set[str]:
    return {game.state.objects[oid].def_id for oid in oids}


def on_battlefield(game, card_id: str) -> bool:
    return any(game.state.objects[oid].def_id == card_id for oid in game.state.battlefield)


class TestWhatIsOffered:
    def test_artifacts_from_hand_and_graveyard(self, builder):
        game = a_table(builder, hand=["t_bobblehead", "t_bear"], graveyard=["t_sundial"])
        assert ids(game, offer(game)) == {"t_bobblehead", "t_sundial"}

    def test_not_one_whose_life_cannot_be_paid(self, builder):
        # 119.4: four life cannot be paid from three.
        game = a_table(builder, hand=["t_bobblehead", "t_sundial"], life=3)
        assert ids(game, offer(game)) == {"t_bobblehead"}

    def test_exactly_the_life_total_is_payable(self, builder):
        game = a_table(builder, hand=["t_sundial"], life=4)
        assert ids(game, offer(game)) == {"t_sundial"}

    def test_a_tax_needs_mana_on_top(self, builder):
        # 601.2f: "spells your opponents cast cost {1} more" still applies to
        # the alternative cost, and with no land the {1} cannot be paid.
        game = a_table(builder, hand=["t_bobblehead"], theirs=["t_mana_toll_all"])
        assert offer(game) == []


class TestThePrice:
    def test_life_equal_to_mana_value_and_no_mana(self, builder):
        game = a_table(builder, hand=["t_sundial"], lands=4)
        before = game.state.players[0].life
        offer(game, take="t_sundial")
        assert game.state.players[0].life == before - 4
        assert not any(game.state.objects[oid].tapped for oid in game.state.battlefield)
        pass_until(game, lambda g: not g.state.stack)
        assert on_battlefield(game, "t_sundial")

    def test_cast_out_of_the_graveyard(self, builder):
        game = a_table(builder, graveyard=["t_bobblehead"])
        before = game.state.players[0].life
        offer(game, take="t_bobblehead")
        assert game.state.players[0].life == before - 1
        pass_until(game, lambda g: not g.state.stack)
        assert on_battlefield(game, "t_bobblehead")

    def test_the_tax_is_paid_in_mana_beside_the_life(self, builder):
        game = a_table(builder, hand=["t_bobblehead"], lands=1, theirs=["t_mana_toll_all"])
        before = game.state.players[0].life
        offer(game, take="t_bobblehead")
        assert game.state.players[0].life == before - 1
        plains = [
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].def_id == "plains"
        ]
        assert all(game.state.objects[oid].tapped for oid in plains)

    def test_declining_costs_nothing(self, builder):
        game = a_table(builder, hand=["t_sundial"])
        before = game.state.players[0].life
        offer(game, take=None)
        assert game.state.players[0].life == before
        assert not game.state.stack

    def test_without_the_key_the_cast_is_still_free(self, builder):
        game = a_table(builder, hand=["t_sundial"])
        before = game.state.players[0].life
        offer(game, {k: v for k, v in ANRAKYR.items() if k != "pay_life_instead"}, take="t_sundial")
        assert game.state.players[0].life == before
        assert game.state.stack


class TestTheLoaderGuards:
    def _card(self, effect: dict, op_text: str = "cast_from_hand") -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_life_caster",
                "name": "Test Life Caster",
                "mana_cost": "{2}",
                "types": ["Sorcery"],
                "oracle_text": "You may cast an artifact spell from your hand or graveyard "
                "by paying life equal to its mana value rather than paying its mana cost.",
                "spell_effects": [effect],
            }
        )

    def test_the_form_loads(self):
        compile_card(self._card(ANRAKYR))

    def test_a_non_boolean_is_refused(self):
        with pytest.raises(DslError, match="pay_life_instead"):
            compile_card(self._card({**ANRAKYR, "pay_life_instead": "false"}))

    def test_cast_card_refuses_the_key(self):
        with pytest.raises(DslError, match="pay_life_instead"):
            compile_card(
                self._card(
                    {"op": "cast_card", "objects": {"zone": "hand"}, "pay_life_instead": True}
                )
            )
