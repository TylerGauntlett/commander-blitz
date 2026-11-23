""""…if life was paid to activate it, you may pay that much life again."

Verrak, Warped Sengir is the witness: "Whenever you activate an ability that
isn't a mana ability, if life was paid to activate it, you may pay that much
life again. If you do, copy that ability. You may choose new targets for the
copy." Rule 602.2b applies 601.2h to abilities, so the life is part of the
activation's own cost: a printed "Pay N life" and, by 107.4f, a Phyrexian pip
paid with 2 life. 118.4 makes paying life a loss of life, but life lost any other
way -- a painland's damage, an opponent's drain -- was not paid to activate
anything, so `life_lost_this_turn` is the near miss and the wrong number.

Without the intervening clause the trigger fires on every activation and its
`may` asks for 0 life, which is a free copy of every equip and pump. Without
the amount the second payment is a guess.

`TriggerSpec.life_paid_to_activate` reads the event's ``life_paid``, which
`Game._activate` takes from `costs.cost_life_paid`; the trigger binds the same
number as ``life_paid``. The Phyrexian choice is asked before the event fires
(`costs.choose_life_for_mana`) and handed to `pay`, so the event knows it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import _default_answer, activations, only_oid

COPIER = "t_lpa_copier"
WATCHER = "t_lpa_watcher"
#: Pay 2 life: each opponent loses 3 life.
DRAINER = "t_lpa_drainer"
#: {G/P}: each opponent loses 1 life.
FONT = "t_lpa_font"
#: {G}: +1/+1 -- no life anywhere in the cost.
MUTATOR = "t_mutator"


def position(builder, mine, *, watcher=COPIER, life=40):
    """The watcher and ``mine`` under player 0, in their main phase."""
    return (
        builder(players=2)
        .battlefield(0, [watcher, *mine])
        .library(0, ["swamp"] * 20)
        .life(0, life)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def activate(game, card_id, *, phyrexian_life=None):
    """Activate ``card_id``'s first ability, answering the Phyrexian question."""
    game.apply(activations(game, only_oid(game, card_id, 0))[0])
    decision = game.pending()
    if decision is not None and decision.kind is DecisionKind.CHOOSE_MODE:
        assert phyrexian_life is not None, decision.prompt
        want = "Pay with mana" if not phyrexian_life else "Pay 2 life"
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE
                and (decision.options[a.choice].label or "").startswith(want)
            )
        )


def resolve(game, *, copy=True, limit=300):
    """Resolve everything, answering the copier's "may"; whether it was asked."""
    asked = False
    for _ in range(limit):
        decision = game.pending()
        if decision is None or game.over:
            break
        if decision.kind is DecisionKind.MAY:
            asked = True
            want = ActionKind.YES if copy else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            break
        game.apply(_default_answer(game, decision))
    return asked


def lives(game) -> tuple[int, int]:
    return game.state.players[0].life, game.state.players[1].life


def last_activation(game):
    return next(
        e for e in reversed(game.state.events) if e.type == EventType.ABILITY_ACTIVATED
    )


class TestNoLifePaid:
    def test_an_ability_without_life_in_its_cost_does_not_trigger(self, builder):
        game = position(builder, [MUTATOR, "forest"])
        activate(game, MUTATOR)
        assert last_activation(game).data["life_paid"] == 0
        assert not game.state.pending_triggers
        assert not resolve(game)

    def test_a_phyrexian_pip_paid_with_mana_is_no_life(self, builder):
        game = position(builder, [FONT, "forest"])
        activate(game, FONT, phyrexian_life=False)
        assert last_activation(game).data["life_paid"] == 0
        assert not game.state.pending_triggers
        assert not resolve(game)
        assert lives(game) == (40, 39)


class TestPayingItAgainCopies:
    def test_pay_life_is_paid_again_and_the_ability_copied(self, builder):
        game = position(builder, [DRAINER])
        activate(game, DRAINER)
        assert last_activation(game).data["life_paid"] == 2
        assert resolve(game, copy=True)
        # 2 for the cost, 2 again for the copy; the drain twice.
        assert lives(game) == (36, 34)

    def test_declining_leaves_the_original_alone(self, builder):
        game = position(builder, [DRAINER])
        activate(game, DRAINER)
        assert resolve(game, copy=False)
        assert lives(game) == (38, 37)

    def test_a_phyrexian_pip_paid_with_life_counts(self, builder):
        """107.4f: the pip paid with 2 life is 2 life paid to activate it."""
        game = position(builder, [FONT, "forest"])
        activate(game, FONT, phyrexian_life=True)
        assert last_activation(game).data["life_paid"] == 2
        assert game.state.players[0].life == 38, "the pip was paid with life"
        assert resolve(game, copy=True)
        assert lives(game) == (36, 38)

    def test_a_forced_phyrexian_payment_counts_without_a_question(self, builder):
        """No Forest: the pip can only go the life way, and nothing is asked."""
        game = position(builder, [FONT])
        game.apply(activations(game, only_oid(game, FONT, 0))[0])
        assert last_activation(game).data["life_paid"] == 2
        assert resolve(game, copy=True)
        assert lives(game) == (36, 38)

    def test_that_much_life_must_be_affordable(self, builder):
        """119.4: at 3 life the cost leaves 1, and 2 more is not paid."""
        game = position(builder, [DRAINER], life=3)
        activate(game, DRAINER)
        resolve(game, copy=True)
        assert lives(game) == (1, 37)


class TestTheOtherReading:
    def test_false_fires_only_without_life(self, builder):
        game = position(builder, [MUTATOR, DRAINER, "forest"], watcher=WATCHER)
        activate(game, MUTATOR)
        resolve(game)
        assert lives(game) == (40, 39)
        activate(game, DRAINER)
        resolve(game)
        assert lives(game) == (38, 36)


def probe(**trigger) -> dict:
    spec = {"event": "ability_activated", "controller": "you"}
    spec.update(trigger)
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Whenever you activate an ability, ...",
        "mana_cost": "{3}",
        "types": ["Artifact"],
        "abilities": [
            {
                "kind": "triggered",
                "text": "Whenever you activate an ability, ...",
                "trigger": spec,
                "effects": [
                    {"op": "lose_life", "player": "each_opponent", "amount": {"const": 1}}
                ],
            }
        ],
    }


class TestTheLoader:
    def test_it_compiles_beside_mana_ability_false(self):
        card = compile_card(
            CardModel.model_validate(probe(mana_ability=False, life_paid_to_activate=True))
        )
        assert card.abilities[0].trigger.life_paid_to_activate is True

    def test_omitted_is_either_way(self):
        card = compile_card(CardModel.model_validate(probe(mana_ability=False)))
        assert card.abilities[0].trigger.life_paid_to_activate is None

    def test_refused_without_mana_ability_false(self):
        with pytest.raises(DslError, match="life_paid_to_activate"):
            compile_card(CardModel.model_validate(probe(life_paid_to_activate=True)))

    def test_refused_on_another_event(self):
        payload = probe()
        payload["abilities"][0]["trigger"] = {
            "event": "spell_cast",
            "controller": "you",
            "mana_ability": False,
            "life_paid_to_activate": True,
        }
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(payload))
