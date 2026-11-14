"""A spell that costs less for what it aims at.

    Ephara's Dispersal — "This spell costs {2} less to cast if it targets an
    attacking creature. Return target creature to its owner's hand."

    Price of Fame — "This spell costs {2} less to cast if it targets a
    legendary creature. Destroy target creature."

Rule 601.2f: the total cost is determined *after* the targets are announced
(601.2c), so a reduction may ask which targets this cast chose. The card-level
`cost_reduction` takes a ``targeting`` clause beside its ``amount`` for that: a
reduction filter matched against the object targets of the cast, true when any
of them matches.

**The near miss is a stronger card.** `cost_reduction`'s ``condition`` with
``exists: attacking creature`` loads clean and discounts the spell whenever
*anything* is attacking — so Ephara's Dispersal bounces a blocker for {1}{U}.
The `spell_cost_reduction` static has a ``targeting`` clause already, but it
discounts other spells from a permanent, not the card carrying it.

**The offer and the charge are one number.** Legality prices each offered
tuple with its own targets (`casting._priced_tuples`), and `Game._cast` charges
the tuple the action carries, both through `cost_reduction.cost_reduction`. A
gate asked before any tuple exists reads the clause generously; the tuples a
discount does not reach are dropped where they are priced.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.cost_reduction import cost_reduction
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import attack_with, find_action, only_oid, pass_until, settle

RECALL = "t_ambush_recall"  # {3}{U}: bounce target creature, {2} less at an attacker
TOLL = "t_fame_toll"  # {3}{B}: destroy target creature, {2} less at a legend
BEAR = "t_bear"
LEGEND = "t_legend"


def casts(game, def_id: str = RECALL) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
    ]


def aimed_at(game, def_id: str = RECALL) -> set[int]:
    """The creatures ``def_id`` is offered against right now."""
    return {r.id for a in casts(game, def_id) for r in a.targets}


def in_combat(builder, *, islands: int):
    """P1 attacks P0 with a Bear; P0 holds Ambush Recall and a Bear of its own.

    Returns the game at P0's first priority after attackers are declared, the
    attacking Bear and the one at home.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * islands + [BEAR])
        .battlefield(1, [BEAR])
        .hand(0, [RECALL])
        .library(0, ["island"] * 10)
        .library(1, ["island"] * 10)
        .active(1)
        .build()
    )
    attacker, home = only_oid(game, BEAR, 1), only_oid(game, BEAR, 0)
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
    )
    attack_with(game, attacker, defender=0)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(game, lambda g: g.pending() is not None and g.pending().player == 0)
    return game, attacker, home


def priced(game, card_id: str, *oids: int, pid: int = 0) -> int:
    card = game.state.registry.get(card_id)
    return cost_reduction(
        game.state, pid, card, tuple(TargetRef.obj(o) for o in oids), zone=Zone.HAND, owner=pid
    )


class TestWhatItDiscounts:
    def test_aimed_at_an_attacker(self, builder):
        game, attacker, _home = in_combat(builder, islands=4)
        assert priced(game, RECALL, attacker) == 2

    def test_aimed_at_a_creature_that_is_not_attacking(self, builder):
        """"…if it targets **an attacking** creature". The clause is the card."""
        game, _attacker, home = in_combat(builder, islands=4)
        assert priced(game, RECALL, home) == 0

    def test_whose_attacker_does_not_matter(self, builder):
        """``controller`` defaults to ``any``: the attacker is the opponent's."""
        game, attacker, _home = in_combat(builder, islands=4)
        assert game.state.objects[attacker].controller == 1
        assert priced(game, RECALL, attacker) == 2

    def test_a_legend_and_an_ordinary_creature(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["swamp"] * 4)
            .battlefield(1, [LEGEND, BEAR])
            .hand(0, [TOLL])
            .build()
        )
        assert priced(game, TOLL, only_oid(game, LEGEND, 1)) == 2
        assert priced(game, TOLL, only_oid(game, BEAR, 1)) == 0

    def test_the_gate_reads_it_generously(self, builder):
        """No tuple yet: legality asks whether the card is castable at all."""
        game, _attacker, _home = in_combat(builder, islands=2)
        card = game.state.registry.get(RECALL)
        assert cost_reduction(game.state, 0, card, None, zone=Zone.HAND, owner=0) == 2


class TestTheOfferAndTheCharge:
    def test_two_mana_offers_only_the_attacker(self, builder):
        game, attacker, home = in_combat(builder, islands=2)
        assert aimed_at(game) == {attacker}, f"{home} costs {{3}}{{U}} and there are two lands"

    def test_four_mana_offers_both(self, builder):
        game, attacker, home = in_combat(builder, islands=4)
        assert aimed_at(game) == {attacker, home}

    def test_the_cheap_cast_is_charged_cheap_and_resolves(self, builder):
        game, attacker, _home = in_combat(builder, islands=2)
        game.apply(next(a for a in casts(game) if a.targets[0].id == attacker))
        settle(game)
        assert attacker in game.state.players[1].hand
        assert all(
            game.state.objects[o].tapped
            for o in game.state.battlefield
            if game.state.objects[o].def_id == "island"
        )

    def test_the_full_price_at_a_non_attacker(self, builder):
        game, _attacker, home = in_combat(builder, islands=4)
        game.apply(next(a for a in casts(game) if a.targets[0].id == home))
        settle(game)
        assert home in game.state.players[0].hand
        islands = [o for o in game.state.battlefield if game.state.objects[o].def_id == "island"]
        assert all(game.state.objects[o].tapped for o in islands), "all four paid"

    def test_nothing_attacking_is_the_printed_cost(self, builder):
        """Outside combat the spell is a four-drop: two lands cast nothing."""
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 2)
            .battlefield(1, [BEAR])
            .hand(0, [RECALL])
            .build()
        )
        assert not casts(game)


def _card(**fields) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "This spell costs {2} less to cast if it targets an attacking creature.",
        "mana_cost": "{3}{U}",
        "types": ["Instant"],
        "targets": [{"id": "t1", "kind": "permanent", "count": 1,
                     "selector": {"types": ["Creature"], "controller": "any"}}],
        "spell_effects": [{"op": "return_to_hand", "objects": {"target": "t1"}}],
        **fields,
    }


def _compile(raw: dict):
    return compile_card(CardModel.model_validate(raw))


class TestTheLoader:
    def test_the_printed_shape_loads(self):
        card = _compile(_card(cost_reduction={
            "amount": 2, "targeting": {"types": ["Creature"], "attacking": True}}))
        assert card.cost_reduction["targeting"] == {"types": ["Creature"], "attacking": True}

    def test_targeting_is_a_gate_for_a_flat_amount(self):
        """A flat ``amount`` needs *a* gate, and ``targeting`` is one."""
        with pytest.raises(DslError, match="needs a 'condition' or a 'targeting'"):
            _compile(_card(cost_reduction={"amount": 2}))

    def test_a_card_with_no_targets(self):
        raw = _card(cost_reduction={"amount": 2, "targeting": {"attacking": True}})
        raw["targets"] = []
        raw["spell_effects"] = [{"op": "draw", "amount": {"const": 1}}]
        with pytest.raises(DslError, match="declares no targets"):
            _compile(raw)

    @pytest.mark.parametrize("key", ["zone", "self_only", "exclude_self"])
    def test_keys_a_target_cannot_answer(self, key):
        value = "battlefield" if key == "zone" else True
        with pytest.raises(DslError, match="cannot be asked of a target"):
            _compile(_card(cost_reduction={"amount": 2, "targeting": {key: value}}))

    def test_a_misspelled_supertype(self):
        with pytest.raises(DslError, match="unknown supertype"):
            _compile(_card(cost_reduction={
                "amount": 2, "targeting": {"supertypes": ["Legendery"]}}))

    def test_an_empty_clause(self):
        with pytest.raises(DslError, match="non-empty filter"):
            _compile(_card(cost_reduction={"amount": 2, "targeting": {}}))

    def test_not_on_an_activated_ability(self):
        """An ability's `mana_reduction` is priced where no tuple is handed in."""
        raw = {
            "id": "probe", "name": "Probe", "oracle_text": "{3}: Draw a card.",
            "mana_cost": "{1}", "types": ["Artifact"],
            "abilities": [{
                "kind": "activated", "text": "{3}: Draw a card.",
                "cost": {"mana": "{3}", "mana_reduction": {
                    "amount": 2, "targeting": {"attacking": True}}},
                "effects": [{"op": "draw", "amount": {"const": 1}}],
            }],
        }
        with pytest.raises(DslError, match="only a card's own"):
            _compile(raw)
