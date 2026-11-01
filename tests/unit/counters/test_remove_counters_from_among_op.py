"""Removing counters from among permanents, as an **effect**, and counting them.

    Eventide's Shadow -- "Remove any number of counters from among permanents
    on the battlefield. You draw cards and lose life equal to the number of
    counters removed this way."

The `remove_counters_from_among` cost (Tekuthal) already asked this question --
one counter at a time, which permanent and then which kind -- but a cost is paid
in full as an ability is activated (602.2b), with a printed count, off
permanents the payer controls. Eventide's Shadow is the same sentence on
resolution: any permanents on the battlefield, any number (zero included), and a
second sentence that reads the number back. `remove_counters` could not say it:
it takes a fixed amount of one named kind and records nothing, and once the
counters are gone the board no longer shows how many there were.

So the op shares the cost's question (`effects.counter_removal`, purpose
``"remove_counter"`` because it may be declined) and binds the number actually
removed under `as`, an int read with ``{"binding": ...}`` the way `lose_life`'s
is. `amount` reads as `remove_counters`' ``any_kind`` does: absent is "any
number", alone is exactly that many or as many as there are (609.3).
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card, hand_ids, only_oid, pass_until

SHADOW = "t_eventide_shadow"  # any number, from among every permanent; draw and lose that many
HARVEST = "t_counter_harvest"  # exactly two, from among creatures you control; gain that much
BEAR = "t_bear"
WALKER = "t_walker"


def position(builder, spell: str, *, mine=None, theirs=None):
    """``spell`` in hand with a Swamp; a Bear of ours and a walker of theirs."""
    b = builder(players=2).battlefield(0, ["swamp"]).hand(0, [spell])
    if mine is not None:
        b = b.battlefield(0, [BEAR], counters=mine)
    if theirs is not None:
        b = b.battlefield(1, [WALKER], counters=theirs)
    game = (
        b.library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )
    game._advance()
    return game


def removal_pending(game) -> bool:
    d = game.pending()
    return d is not None and d.context.get("purpose") == "remove_counter"


def cast(game, spell):
    game.apply(action_for_card(game, ActionKind.CAST, spell))
    pass_until(game, lambda g: removal_pending(g) or not g.state.stack)


def pick(game, oid):
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and a.targets and a.targets[0].id == oid
        )
    )


def stop(game):
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    pass_until(game, lambda g: not g.state.stack)


def counters(game, oid) -> dict:
    return {k: n for k, n in game.state.objects[oid].counters.items() if n > 0}


class TestFromAmong:
    def test_split_among_permanents_and_counted(self, builder):
        game = position(builder, SHADOW, mine={"-1/-1": 1}, theirs={"loyalty": 4})
        bear, walker = only_oid(game, BEAR, 0), only_oid(game, WALKER, 1)
        life, hand = game.state.players[0].life, len(hand_ids(game, 0))
        cast(game, SHADOW)
        pick(game, bear)
        pick(game, walker)
        pick(game, walker)
        stop(game)
        assert counters(game, bear) == {}
        assert counters(game, walker) == {"loyalty": 2}
        assert game.state.players[0].life == life - 3
        assert len(hand_ids(game, 0)) == hand - 1 + 3, "the Shadow left, three were drawn"

    def test_any_permanent_on_the_battlefield(self, builder):
        """"Permanents on the battlefield" -- an opponent's as well as ours."""
        game = position(builder, SHADOW, mine={"charge": 1}, theirs={"loyalty": 4})
        cast(game, SHADOW)
        offered = {o.value for o in game.pending().options}
        assert offered == {only_oid(game, BEAR, 0), only_oid(game, WALKER, 1)}

    def test_a_permanent_without_counters_is_not_offered(self, builder):
        game = position(builder, SHADOW, mine={}, theirs={"loyalty": 4})
        cast(game, SHADOW)
        assert {o.value for o in game.pending().options} == {only_oid(game, WALKER, 1)}

    def test_several_kinds_ask_which(self, builder):
        game = position(builder, SHADOW, mine={"charge": 1, "stun": 1})
        bear = only_oid(game, BEAR, 0)
        cast(game, SHADOW)
        pick(game, bear)
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert decision.options[0].label.startswith("stun"), "harmful first"


class TestAnyNumber:
    def test_zero_removes_nothing_and_draws_nothing(self, builder):
        game = position(builder, SHADOW, theirs={"loyalty": 4})
        life, hand = game.state.players[0].life, len(hand_ids(game, 0))
        cast(game, SHADOW)
        assert removal_pending(game), "zero is a legal answer, so it is asked"
        stop(game)
        assert counters(game, only_oid(game, WALKER, 1)) == {"loyalty": 4}
        assert game.state.players[0].life == life
        assert len(hand_ids(game, 0)) == hand - 1

    def test_it_ends_when_nothing_is_left(self, builder):
        game = position(builder, SHADOW, mine={"charge": 2})
        bear = only_oid(game, BEAR, 0)
        life = game.state.players[0].life
        cast(game, SHADOW)
        pick(game, bear)
        pick(game, bear)
        pass_until(game, lambda g: not g.state.stack)
        assert not removal_pending(game)
        assert game.state.players[0].life == life - 2


class TestExactly:
    def test_two_and_no_more(self, builder):
        game = position(builder, HARVEST, mine={"charge": 5})
        life = game.state.players[0].life
        cast(game, HARVEST)
        pass_until(game, lambda g: not g.state.stack)
        assert counters(game, only_oid(game, BEAR, 0)) == {"charge": 3}
        assert game.state.players[0].life == life + 2

    def test_as_many_as_there_are(self, builder):
        """609.3, and the binding is what was removed, not what was asked for."""
        game = position(builder, HARVEST, mine={"charge": 1})
        life = game.state.players[0].life
        cast(game, HARVEST)
        pass_until(game, lambda g: not g.state.stack)
        assert counters(game, only_oid(game, BEAR, 0)) == {}
        assert game.state.players[0].life == life + 1

    def test_the_selector_bounds_the_pool(self, builder):
        """"Creatures you control" -- the opponent's walker is never offered."""
        game = position(builder, HARVEST, mine={"charge": 1}, theirs={"loyalty": 4})
        cast(game, HARVEST)
        pass_until(game, lambda g: not g.state.stack)
        assert counters(game, only_oid(game, WALKER, 1)) == {"loyalty": 4}


class TestTheLoaderGuardsIt:
    CARD = {
        "id": "t_probe",
        "name": "Probe",
        "oracle_text": "Remove any number of counters from among permanents on the battlefield. You draw cards equal to the number of counters removed this way.",
        "types": ["Sorcery"],
        "mana_cost": "{B}",
        "spell_effects": [
            {"op": "remove_counters_from_among", "objects": {"controller": "any"},
             "as": "removed"},
            {"op": "draw", "player": "you", "amount": {"binding": "removed"}},
        ],
    }

    def _with(self, **changes):
        card = copy.deepcopy(self.CARD)
        effect = card["spell_effects"][0]
        for key, value in changes.items():
            if value is None:
                effect.pop(key, None)
            else:
                effect[key] = value
        return CardModel.model_validate(card)

    def test_the_card_loads(self):
        compile_card(CardModel.model_validate(self.CARD))

    def test_up_to_an_amount_loads(self):
        compile_card(self._with(amount={"const": 3}, up_to=True))

    def test_missing_objects_is_refused(self):
        with pytest.raises(DslError, match="needs 'objects'"):
            compile_card(self._with(objects=None))

    def test_a_named_kind_is_refused(self):
        with pytest.raises(DslError, match="any kind"):
            compile_card(self._with(counter="+1/+1"))

    def test_a_selector_count_is_refused(self):
        with pytest.raises(DslError, match="'amount', not"):
            compile_card(self._with(objects={"controller": "any", "count": 3}))

    def test_any_kind_is_refused_as_redundant(self):
        with pytest.raises(DslError, match="'any_kind' only means anything"):
            compile_card(self._with(any_kind=True))

    def test_up_to_without_an_amount_is_refused(self):
        with pytest.raises(DslError, match="ceiling"):
            compile_card(self._with(up_to=True))
