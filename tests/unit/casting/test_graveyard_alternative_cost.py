"""A graveyard alternative cost with no keyword: "by paying {2}{W} rather than paying its mana cost".

    Enchant creature
    Enchanted creature gets +1/+1.
    You may cast this card from your graveyard by paying {2}{W} rather than
    paying its mana cost.

118.9: the sentence is an alternative cost, and 601.2b-f make it the price
of a cast from the zone it names. It is escape's slot exactly (the
`graveyard_cost` field, with `"graveyard_cast": "graveyard"`) less the exile:
the card goes where it normally would, so an Aura cast this way that later
dies is back in the graveyard to be cast again. Flashback's destination would
be wrong twice over, exiling a card the printed text never exiles. And the
price is the printed one only from the graveyard: from the hand the card
costs its {W}, and a graveyard with only {W} to spend offers nothing.

Gate 3 had no claimant for the unkeyworded line, so the card loaded and
played and was still rejected as half-implemented. The claimant reads the
field, strictly: the printed mana must be the declared mana, the destination
the plain graveyard one, and any other payment fails closed.

Witness: Raffine's Guidance, whose test twin is `t_raffines_guidance`.
"""

from __future__ import annotations

from commanderblitz.cards.authoring.verify import residual_text
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.zones import destroy
from tests.conftest import only_oid, pass_until, pt

GUIDANCE = "t_raffines_guidance"  # {W} Aura, +1/+1; {2}{W} from the graveyard
LINE = (
    "You may cast this card from your graveyard by paying {2}{W} rather than paying its mana cost."
)


def board(builder, *, where: str, plains: int = 3):
    """Player 0 with the Guidance in ``where``, a bear to enchant and ``plains``."""
    b = builder(players=2)
    b = b.graveyard(0, [GUIDANCE]) if where == "graveyard" else b.hand(0, [GUIDANCE])
    game = (
        b.battlefield(0, ["t_bear"] + ["plains"] * plains)
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .build()
    )
    (oid,) = [o.oid for o in game.state.objects.values() if o.def_id == GUIDANCE]
    return game, oid


def casts(game, oid: int):
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def cast(game, oid: int) -> None:
    """Cast the Guidance by its one offered line and resolve it onto the bear."""
    (action,) = casts(game, oid)
    game.apply(action)
    pass_until(game, lambda g: g.state.objects[oid].zone is Zone.BATTLEFIELD and not g.state.stack)


def untapped_plains(game) -> int:
    return sum(
        1
        for o in game.state.objects.values()
        if o.def_id == "plains" and o.zone is Zone.BATTLEFIELD and not o.tapped
    )


class TestItIsCastFromTheGraveyard:
    def test_it_is_offered_once_from_the_graveyard(self, builder):
        game, oid = board(builder, where="graveyard")
        (action,) = casts(game, oid)
        assert action.flashback

    def test_it_pays_the_printed_two_and_white(self, builder):
        game, oid = board(builder, where="graveyard")
        cast(game, oid)
        assert untapped_plains(game) == 0

    def test_it_enchants_and_buffs(self, builder):
        game, oid = board(builder, where="graveyard")
        bear = only_oid(game, "t_bear")
        before = pt(game, bear)
        cast(game, oid)
        assert game.state.objects[oid].attached_to == bear
        assert pt(game, bear) == (before[0] + 1, before[1] + 1)

    def test_with_only_its_mana_cost_available_it_is_not_offered(self, builder):
        # The boundary: {W} is the hand price, not the graveyard one.
        game, oid = board(builder, where="graveyard", plains=1)
        assert casts(game, oid) == []


class TestItIsNotExiled:
    def test_when_it_dies_it_returns_to_the_graveyard(self, builder):
        game, oid = board(builder, where="graveyard")
        cast(game, oid)
        destroy(game.state, oid)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD, (
            "no exile rider is printed; exiling it here would make it flashback"
        )
        assert game.state.players[0].exile == []


class TestTheHandCastIsUnchanged:
    def test_from_the_hand_it_costs_its_mana_cost(self, builder):
        game, oid = board(builder, where="hand", plains=1)
        (action,) = casts(game, oid)
        assert not action.flashback
        cast(game, oid)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert untapped_plains(game) == 0


class TestThePrintedLineIsClaimed:
    """Gate 3's bookkeeping, where a correct card used to die."""

    def _residual(self, **extra) -> str:
        base = {
            "id": "t_graveyard_alternative_residual",
            "name": "Graveyard Alternative Residual",
            "mana_cost": "{W}",
            "oracle_text": f"Enchant creature\nEnchanted creature gets +1/+1.\n{LINE}",
            "types": ["Enchantment"],
            "subtypes": ["Aura"],
            "targets": [
                {
                    "id": "enchanted",
                    "kind": "permanent",
                    "selector": {"types": ["Creature"], "zone": "battlefield"},
                }
            ],
            "graveyard_cost": {"mana": "{2}{W}"},
            "graveyard_cast": "graveyard",
            "abilities": [
                {
                    "kind": "static",
                    "effect": "buff",
                    "affects": {"attached": True},
                    "power": {"const": 1},
                    "toughness": {"const": 1},
                    "text": "Enchanted creature gets +1/+1",
                }
            ],
        }
        base.update(extra)
        card = compile_card(CardModel.model_validate(base))
        return residual_text(card, card.oracle_text)

    def test_the_exact_card_is_claimed(self):
        assert self._residual() == ""

    def test_the_cards_own_name_is_claimed_like_this_card(self):
        line = LINE.replace("this card", "Graveyard Alternative Residual")
        assert self._residual(oracle_text=line) == ""

    def test_a_cheaper_price_cannot_claim_the_printed_one(self):
        assert "graveyard" in self._residual(graveyard_cost={"mana": "{W}"})

    def test_a_different_colour_cannot_claim_the_printed_one(self):
        assert "graveyard" in self._residual(graveyard_cost={"mana": "{2}{B}"})

    def test_a_flashback_shaped_card_cannot_claim_it(self):
        # The same price with the exile destination is a card that is gone
        # after one use, which the printed line does not say.
        base_exile = {"graveyard_cost": {"mana": "{2}{W}"}, "graveyard_cast": "exile"}
        assert "graveyard" in self._residual(**base_exile)

    def test_a_flashback_spelled_card_cannot_claim_it(self):
        residual = self._residual(
            graveyard_cost=None, graveyard_cast="exile", flashback={"mana": "{2}{W}"}
        )
        assert "graveyard" in residual

    def test_another_payment_fails_closed(self):
        dearer = {"mana": "{2}{W}", "pay_life": 2}
        assert "graveyard" in self._residual(graveyard_cost=dearer)

    def test_a_printed_extra_payment_is_not_this_line(self):
        # Scourge of Nel Toth's shape: the mana is only part of the price.
        line = (
            "You may cast this card from your graveyard by paying {2}{W} and "
            "sacrificing two creatures rather than paying its mana cost."
        )
        assert "graveyard" in self._residual(oracle_text=line)

    def test_a_printed_rider_is_not_this_line(self):
        # Glimpse the Cosmos' shape: a condition in front.
        line = f"As long as you control a Giant, {LINE[0].lower()}{LINE[1:]}"
        assert "graveyard" in self._residual(oracle_text=line)
