"""Removing counters of **any** kind from a target, as many as the chooser likes.

    Glissa Sunslayer -- "Whenever Glissa Sunslayer deals combat damage to a
    player, choose one -- ... • Remove up to three counters from target
    permanent."

`remove_counters` names one kind, defaulting to +1/+1, and takes exactly
`amount` of it. Glissa names none: 122.1 lets a permanent carry any number of
kinds, and the sentence lets the controller take them in any mix -- a -1/-1 off
their own creature, loyalty off an opponent's planeswalker, two of one and one
of another. Written with a named kind the card would clear loyalty and leave
oil, stun and charge counters untouched, a card that looks implemented and is
quietly smaller than printed.

`any_kind` asks one counter at a time through `effects.counter_removal`, the
question the `remove_counters_from_among` cost already asks: which permanent
(declinable past the floor, purpose ``"remove_counter"``), then which kind when
it carries more than one (harmful kinds offered first). With ``up_to`` the
amount is a ceiling the controller may stop short of, down to none; without it
the removal is exactly `amount`, or as many as there are (609.3).
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, only_oid, pass_until

SCOUR = "t_counter_scour"  # {T}: remove up to three counters from target permanent
STRIP = "t_counter_strip"  # {T}: remove two counters from target permanent
SUNSLAYER = "t_sunslayer"  # Glissa Sunslayer, line for line
BEAR = "t_bear"
WALKER = "t_walker"


def position(builder, rock: str, *, bear=None, walker=None):
    """``rock`` for player 0; a Bear with ``bear`` counters and a walker with ``walker``."""
    b = builder(players=2).battlefield(0, [rock])
    if bear is not None:
        b = b.battlefield(1, [BEAR], counters=bear)
    if walker is not None:
        b = b.battlefield(1, [WALKER], counters=walker)
    game = (
        b.library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game, only_oid(game, rock, 0)


def counters(game, oid) -> dict:
    return {k: n for k, n in game.state.objects[oid].counters.items() if n > 0}


def choose(game, label_prefix: str | None = None, oid: int | None = None):
    """Answer the pending choice by option label prefix or by object."""
    for action in game.legal_actions():
        if action.kind is not ActionKind.CHOOSE:
            continue
        if oid is not None and action.targets and action.targets[0].id == oid:
            return game.apply(action)
        if label_prefix is not None and (action.label or "").startswith(label_prefix):
            return game.apply(action)
    raise AssertionError([a.label for a in game.legal_actions()])


def stop(game):
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


def activate_at(game, rock, target):
    game.apply(
        next(a for a in activations(game, rock) if a.targets and a.targets[0].id == target)
    )
    # Let the ability resolve up to its first question.
    pass_until(
        game,
        lambda g: (
            (d := g.pending()) is not None
            and d.kind in (DecisionKind.CHOOSE_OBJECTS, DecisionKind.CHOOSE_MODE)
        )
        or not g.state.stack,
    )


def removal_pending(game) -> bool:
    d = game.pending()
    return d is not None and d.context.get("purpose") == "remove_counter"


class TestAnyKind:
    def test_a_mix_of_kinds_comes_off(self, builder):
        game, rock = position(builder, SCOUR, bear={"-1/-1": 1, "charge": 2, "stun": 1})
        bear = only_oid(game, BEAR, 1)
        activate_at(game, rock, bear)
        choose(game, oid=bear)
        choose(game, "charge")
        choose(game, oid=bear)
        choose(game, "stun")
        choose(game, oid=bear)
        choose(game, "charge")
        assert counters(game, bear) == {"-1/-1": 1}

    def test_a_kind_the_named_op_could_not_reach(self, builder):
        """Loyalty: the card is as good against a planeswalker as a creature."""
        game, rock = position(builder, SCOUR, walker={"loyalty": 5})
        walker = only_oid(game, WALKER, 1)
        activate_at(game, rock, walker)
        for _ in range(3):
            choose(game, oid=walker)
        assert counters(game, walker) == {"loyalty": 2}

    def test_one_kind_is_not_asked_which(self, builder):
        game, rock = position(builder, SCOUR, walker={"loyalty": 5})
        walker = only_oid(game, WALKER, 1)
        activate_at(game, rock, walker)
        choose(game, oid=walker)
        assert removal_pending(game), "the next question is 'another?', not 'which kind?'"

    def test_harmful_kinds_are_offered_first(self, builder):
        game, rock = position(builder, SCOUR, bear={"charge": 3, "-1/-1": 1})
        bear = only_oid(game, BEAR, 1)
        activate_at(game, rock, bear)
        choose(game, oid=bear)
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert decision.options[0].label.startswith("-1/-1")


class TestUpTo:
    def test_never_more_than_three(self, builder):
        game, rock = position(builder, SCOUR, walker={"loyalty": 9})
        walker = only_oid(game, WALKER, 1)
        activate_at(game, rock, walker)
        for _ in range(3):
            choose(game, oid=walker)
        assert not removal_pending(game)
        assert counters(game, walker) == {"loyalty": 6}

    def test_the_controller_may_stop_short(self, builder):
        game, rock = position(builder, SCOUR, walker={"loyalty": 5})
        walker = only_oid(game, WALKER, 1)
        activate_at(game, rock, walker)
        choose(game, oid=walker)
        stop(game)
        assert counters(game, walker) == {"loyalty": 4}

    def test_down_to_none(self, builder):
        game, rock = position(builder, SCOUR, walker={"loyalty": 5})
        walker = only_oid(game, WALKER, 1)
        activate_at(game, rock, walker)
        assert removal_pending(game), "zero is a legal answer, so it is asked"
        stop(game)
        assert counters(game, walker) == {"loyalty": 5}

    def test_fewer_than_three_there_takes_what_there_is(self, builder):
        game, rock = position(builder, SCOUR, bear={"+1/+1": 1})
        bear = only_oid(game, BEAR, 1)
        activate_at(game, rock, bear)
        choose(game, oid=bear)
        assert not removal_pending(game)
        assert counters(game, bear) == {}


class TestExactly:
    def test_without_up_to_nothing_is_asked_but_the_kind(self, builder):
        """"Remove two counters" is not declinable: the permanent is forced."""
        game, rock = position(builder, STRIP, bear={"+1/+1": 1, "charge": 2})
        bear = only_oid(game, BEAR, 1)
        activate_at(game, rock, bear)
        assert game.pending().kind is DecisionKind.CHOOSE_MODE
        choose(game, "charge")
        choose(game, "charge")
        assert counters(game, bear) == {"+1/+1": 1}

    def test_as_many_as_there_are(self, builder):
        """609.3: "remove two" off a permanent with one removes the one."""
        game, rock = position(builder, STRIP, walker={"loyalty": 1})
        walker = only_oid(game, WALKER, 1)
        activate_at(game, rock, walker)
        pass_until(game, lambda g: not g.state.stack)
        assert not [o for o in game.state.battlefield_objects(1) if o.def_id == WALKER], (
            "a walker at no loyalty is put into the graveyard (704.5i)"
        )


class TestGlissaSunslayer:
    def test_the_whole_card_loads(self, registry):
        card = registry.get(SUNSLAYER)
        assert card is not None

    def test_the_third_mode_removes_counters(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [SUNSLAYER])
            .battlefield(1, [WALKER], counters={"loyalty": 4})
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        glissa = only_oid(game, SUNSLAYER, 0)
        walker = only_oid(game, WALKER, 1)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == glissa
                and any(r.kind == "player" for r in a.targets)
            )
        )
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.CHOOSE_MODE,
        )
        choose(game, "Remove up to three")
        # The mode's own target (601.2c, declared once the mode is chosen).
        assert game.pending().prompt.startswith("Choose targ")
        choose(game, oid=walker)
        pass_until(game, removal_pending)
        for _ in range(3):
            choose(game, oid=walker)
        assert counters(game, walker) == {"loyalty": 1}


class TestTheLoaderGuardsIt:
    CARD = {
        "id": "t_probe",
        "name": "Probe",
        "oracle_text": "Remove up to three counters from target permanent.",
        "types": ["Sorcery"],
        "mana_cost": "{B}",
        "targets": [
            {"id": "t1", "kind": "permanent", "count": 1, "selector": {"zone": "battlefield"}}
        ],
        "spell_effects": [
            {"op": "remove_counters", "objects": {"target": "t1"}, "any_kind": True,
             "amount": {"const": 3}, "up_to": True}
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

    def test_any_number_loads(self):
        compile_card(self._with(amount=None, up_to=None))

    def test_a_named_kind_beside_any_kind_is_refused(self):
        with pytest.raises(DslError, match="contradict"):
            compile_card(self._with(counter="+1/+1"))

    def test_up_to_without_any_kind_is_refused(self):
        with pytest.raises(DslError, match="needs 'any_kind'"):
            compile_card(self._with(any_kind=None))

    def test_up_to_without_an_amount_is_refused(self):
        with pytest.raises(DslError, match="ceiling"):
            compile_card(self._with(amount=None))

    def test_a_zero_amount_is_refused(self):
        with pytest.raises(DslError, match="removes none"):
            compile_card(self._with(amount={"const": 0}))

    def test_any_kind_elsewhere_is_refused(self):
        card = copy.deepcopy(self.CARD)
        card["spell_effects"] = [
            {"op": "add_counters", "objects": {"target": "t1"}, "any_kind": True}
        ]
        with pytest.raises(DslError, match="'any_kind' only means anything"):
            compile_card(CardModel.model_validate(card))

    def test_a_non_boolean_is_refused(self):
        with pytest.raises(DslError, match="boolean"):
            compile_card(self._with(any_kind="yes"))
