"""Removing counters from among other permanents, as a cost.

    Tekuthal, Inquiry Dominus — "{1}{U/P}{U/P}, Remove three counters from among
    other artifacts, creatures, and planeswalkers you control: Put an
    indestructible counter on Tekuthal."

The `remove_counters` cost takes one **named** kind off the **source**. This
sentence is the other shape on both axes: counters of *any* kinds, off *other*
permanents a selector names, split among them however the payer likes -- three
off one creature, or one each off a planeswalker, an artifact and a creature.

It is a cost (602.2b), so it is paid in full as the ability is activated or not
at all: the ability is not offered while the matching permanents carry fewer
than three counters between them, and the counters are gone before the ability
can be responded to. Paying it with a `remove_counters` **op** would take them
on resolution, after the ability had been activated with nothing to pay.

Asked one counter at a time -- which permanent (`ask_objects`, purpose
``"remove_counter_cost"``), then which kind when it carries more than one
(`ask_mode`, harmful kinds offered first) -- because that one question can say
every split, and a cost cannot fail halfway. The witness is Tekuthal.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.carddef import Cost
from commanderblitz.engine.costs import can_pay
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, only_oid, pass_until

EATER = "t_counter_eater"
BEAR = "t_bear"
WALKER = "t_walker"
ENCHANTMENT = "t_proliferate_doubler"

COST = {
    "remove_counters_from_among": {
        "count": 3,
        "any_types": ["Artifact", "Creature", "Planeswalker"],
        "exclude_self": True,
    }
}


def board(builder, *, bear=None, walker=None, eater=None, enchantment=None):
    """The Eater, islands to pay {1}, and whichever countered permanents are named."""
    b = builder(players=2).battlefield(0, [EATER], counters=eater or {})
    b = b.battlefield(0, ["island"] * 2)
    if bear is not None:
        b = b.battlefield(0, [BEAR], counters=bear)
    if walker is not None:
        b = b.battlefield(0, [WALKER], counters=walker)
    if enchantment is not None:
        b = b.battlefield(0, [ENCHANTMENT], counters=enchantment)
    game = b.build()
    return game, only_oid(game, EATER, 0)


def payable(game, source) -> bool:
    return can_pay(game.state, 0, Cost.from_spec(COST), source)


def activation(game, source):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == source
        ),
        None,
    )


def counters(game, card_id: str) -> dict:
    return dict(game.state.objects[only_oid(game, card_id, 0)].counters)


def pay(game, source, answer) -> list:
    """Activate, answering each cost question with ``answer(decision, actions)``."""
    game.apply(activation(game, source))
    asked = []
    while (decision := game.pending()) is not None and decision.kind in (
        DecisionKind.CHOOSE_OBJECTS,
        DecisionKind.CHOOSE_MODE,
    ):
        asked.append(decision)
        game.apply(answer(decision, game.legal_actions()))
    return asked


def first(decision, actions):
    return next(a for a in actions if a.kind is ActionKind.CHOOSE)


class TestWhatItCosts:
    def test_three_counters_on_one_permanent_pay(self, builder):
        game, source = board(builder, bear={"+1/+1": 3})
        assert payable(game, source)

    def test_three_split_among_permanents_pay(self, builder):
        game, source = board(builder, bear={"+1/+1": 1}, walker={"loyalty": 2})
        assert payable(game, source)

    def test_two_is_one_short(self, builder):
        """The boundary, asserted beside the case above."""
        game, source = board(builder, bear={"+1/+1": 2})
        assert not payable(game, source)
        assert activation(game, source) is None

    def test_any_kinds_count(self, builder):
        game, source = board(builder, bear={"+1/+1": 1, "charge": 1, "stun": 1})
        assert payable(game, source)

    def test_its_own_counters_do_not(self, builder):
        """"From among **other** ..." -- `exclude_self`."""
        game, source = board(builder, bear={"+1/+1": 1}, eater={"+1/+1": 5})
        assert not payable(game, source)

    def test_an_enchantment_does_not(self, builder):
        """The selector names artifacts, creatures and planeswalkers."""
        game, source = board(builder, bear={"+1/+1": 1}, enchantment={"charge": 5})
        assert not payable(game, source)


class TestPayingIt:
    def test_the_counters_come_off_and_the_ability_resolves(self, builder):
        game, source = board(builder, bear={"+1/+1": 3})
        pay(game, source, first)
        pass_until(game, lambda g: not g.state.stack)
        assert counters(game, BEAR) == {}
        assert counters(game, EATER) == {"indestructible": 1}

    def test_it_is_paid_before_the_ability_is_on_the_stack(self, builder):
        """A cost (602.2b): with a choice pending, nothing is on the stack yet,
        and once the ability is there the counters are already gone."""
        game, source = board(builder, bear={"+1/+1": 2}, walker={"loyalty": 4})
        game.apply(activation(game, source))
        assert game.pending().context["purpose"] == "remove_counter_cost"
        assert not game.state.stack

    def test_the_payer_splits_it(self, builder):
        game, source = board(builder, bear={"+1/+1": 2}, walker={"loyalty": 4})
        walker = only_oid(game, WALKER, 0)
        picks = iter([walker, walker, None])

        def answer(decision, actions):
            want = next(picks)
            if want is None:
                return first(decision, actions)
            return next(a for a in actions if a.targets and a.targets[0].id == want)

        pay(game, source, answer)
        assert counters(game, WALKER) == {"loyalty": 2}
        assert counters(game, BEAR) == {"+1/+1": 1}

    def test_a_permanent_with_two_kinds_asks_which(self, builder):
        game, source = board(builder, bear={"+1/+1": 2, "stun": 2})
        asked = pay(game, source, first)
        modes = [d for d in asked if d.kind is DecisionKind.CHOOSE_MODE]
        assert modes, "which kind is the payer's choice"
        assert modes[0].options[0].label.startswith("stun"), "harmful first"

    def test_one_at_a_time_it_only_asks_what_is_left(self, builder):
        game, source = board(builder, bear={"+1/+1": 1}, walker={"loyalty": 2})
        asked = pay(game, source, first)
        objects = [d for d in asked if d.kind is DecisionKind.CHOOSE_OBJECTS]
        # The bear's only counter goes first; after that only the walker is left,
        # a forced choice that is not asked -- and a walker at no loyalty dies.
        assert len(objects) == 1
        assert oids_of(game, WALKER, 0) == []


class TestTheHeuristicAgent:
    def test_it_takes_the_harmful_counter_first(self, builder):
        from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent

        game, source = board(
            builder, bear={"-1/-1": 1}, walker={"loyalty": 5}
        )
        agent = HeuristicAgent(seed=0)
        game.apply(activation(game, source))
        decision = game.pending()
        assert decision.context["purpose"] == "remove_counter_cost"
        chosen = agent.act(game, 0, game.legal_actions())
        assert chosen.targets[0].id == only_oid(game, BEAR, 0)


class TestTheLoaderGuardsIt:
    CARD = {
        "id": "t_probe",
        "name": "Probe",
        "oracle_text": "Remove three counters from among creatures you control: Draw a card.",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "activated",
                "text": "Remove three counters from among creatures you control: Draw a card.",
                "cost": {"remove_counters_from_among": {"count": 3, "types": ["Creature"]}},
                "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            }
        ],
    }

    def _with(self, among):
        card = copy.deepcopy(self.CARD)
        card["abilities"][0]["cost"]["remove_counters_from_among"] = among
        return CardModel.model_validate(card)

    def test_the_card_loads_and_describes_itself(self):
        card = compile_card(CardModel.model_validate(self.CARD))
        assert "Remove 3 counters" in card.abilities[0].cost.describe()

    def test_a_missing_count_is_refused(self):
        with pytest.raises(DslError, match="positive integer 'count'"):
            compile_card(self._with({"types": ["Creature"]}))

    def test_a_named_kind_is_refused(self):
        with pytest.raises(DslError, match="any kind"):
            compile_card(self._with({"count": 1, "counter": "+1/+1"}))

    def test_a_bad_selector_key_is_refused(self):
        with pytest.raises(DslError, match="unknown selector keys"):
            compile_card(self._with({"count": 1, "typs": ["Creature"]}))

    def test_it_is_not_a_tap_only_cost(self):
        assert not Cost.from_spec({"tap": True, **COST}).is_tap_only()
