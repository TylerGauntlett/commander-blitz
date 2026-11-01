"""Moving **a counter** of whichever kind the controller picks.

    Nesting Grounds -- "{1}, {T}: Move a counter from target permanent you
    control onto a second target permanent. Activate only as a sorcery."

`move_counters` moved one named kind (default +1/+1) or, with `all_kinds`,
the whole multiset. Nesting Grounds is neither: one counter, of any kind on the
source (122.1) -- a charge, oil, loyalty or -1/-1 counter as readily as a
+1/+1. Naming +1/+1 would make the land useless with every other kind, and
`all_kinds` moves every counter instead of one.

`any_kind` asks, on resolution, which kind moves (`ask_mode`, only when the
source carries more than one, harmful kinds offered first), takes it off the
source and puts the same kind on the destination -- a placement, so counter
replacements and "whenever a counter is put on" see it. With either target
gone (608.2b) nothing moves.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy
from tests.conftest import activations, only_oid, pass_until

GROUNDS = "t_nesting_grounds"
BEAR = "t_bear"
WALKER = "t_walker"


def position(builder, *, mine=None, theirs=None):
    """The Grounds and a Swamp for {1}; our Bear with ``mine``, their walker with ``theirs``.

    The opponent's Bolt and Mountain are an anchor, not a card under test: an
    instant they could cast keeps the engine from auto-passing the stack away
    before a test can respond to the activation.
    """
    game = (
        builder(players=2)
        .battlefield(0, [GROUNDS, "swamp"])
        .battlefield(0, [BEAR], counters=mine or {})
        .battlefield(1, [WALKER, "mountain"], counters=theirs or {"loyalty": 3})
        .hand(1, ["lightning_bolt"])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )
    game._advance()
    return game, only_oid(game, GROUNDS, 0), only_oid(game, BEAR, 0), only_oid(game, WALKER, 1)


def move_line(game, grounds, source, dest):
    return next(
        (
            a
            for a in activations(game, grounds)
            if [r.id for r in a.targets] == [source, dest]
        ),
        None,
    )


def activate(game, grounds, source, dest):
    game.apply(move_line(game, grounds, source, dest))
    pass_until(
        game,
        lambda g: (
            (d := g.pending()) is not None and d.kind is DecisionKind.CHOOSE_MODE
        )
        or not g.state.stack,
    )


def counters(game, oid) -> dict:
    return {k: n for k, n in game.state.objects[oid].counters.items() if n > 0}


def choose_label(game, prefix):
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and (a.label or "").startswith(prefix)
        )
    )
    pass_until(game, lambda g: not g.state.stack)


class TestOneCounterOfAnyKind:
    def test_a_kind_other_than_plus_one_moves(self, builder):
        game, grounds, bear, walker = position(builder, mine={"charge": 2})
        activate(game, grounds, bear, walker)
        assert counters(game, bear) == {"charge": 1}
        assert counters(game, walker) == {"loyalty": 3, "charge": 1}

    def test_only_one_moves(self, builder):
        game, grounds, bear, walker = position(builder, mine={"+1/+1": 3})
        activate(game, grounds, bear, walker)
        assert counters(game, bear) == {"+1/+1": 2}
        assert counters(game, walker) == {"loyalty": 3, "+1/+1": 1}

    def test_the_controller_picks_the_kind(self, builder):
        game, grounds, bear, walker = position(builder, mine={"+1/+1": 2, "stun": 1})
        activate(game, grounds, bear, walker)
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert decision.options[0].label.startswith("stun"), "harmful first"
        choose_label(game, "+1/+1")
        assert counters(game, bear) == {"+1/+1": 1, "stun": 1}
        assert counters(game, walker) == {"loyalty": 3, "+1/+1": 1}

    def test_a_harmful_counter_can_be_handed_over(self, builder):
        game, grounds, bear, walker = position(builder, mine={"-1/-1": 1})
        activate(game, grounds, bear, walker)
        assert counters(game, bear) == {}
        assert counters(game, walker) == {"loyalty": 3, "-1/-1": 1}


class TestTheTargets:
    def test_the_source_must_be_ours(self, builder):
        """"From target permanent **you control**": their walker is no source."""
        game, grounds, bear, walker = position(builder, mine={"charge": 1})
        assert move_line(game, grounds, walker, bear) is None

    def test_the_two_targets_differ(self, builder):
        """"A **second** target permanent" -- one object cannot fill both."""
        game, grounds, bear, _ = position(builder, mine={"charge": 1})
        assert move_line(game, grounds, bear, bear) is None

    def test_a_vanished_destination_moves_nothing(self, builder):
        game, grounds, bear, walker = position(builder, mine={"charge": 1})
        game.apply(move_line(game, grounds, bear, walker))
        assert game.state.stack, "the ability is waiting to resolve"
        destroy(game.state, walker)
        pass_until(game, lambda g: not g.state.stack)
        assert counters(game, bear) == {"charge": 1}, "the counter stays put"

    def test_nothing_on_the_source_moves_nothing(self, builder):
        game, grounds, bear, walker = position(builder, mine={})
        activate(game, grounds, bear, walker)
        assert counters(game, walker) == {"loyalty": 3}

    def test_only_as_a_sorcery(self, builder):
        """"Activate only as a sorcery" compiles onto the ability itself."""
        game, grounds, _, _ = position(builder, mine={"charge": 1})
        assert registry_ability(game, grounds).sorcery_speed_only


def registry_ability(game, grounds):
    return game.state.card(grounds).abilities[1]


class TestTheLoaderGuardsIt:
    CARD = {
        "id": "t_probe",
        "name": "Probe",
        "oracle_text": "Move a counter from target permanent you control onto a second target permanent.",
        "types": ["Sorcery"],
        "mana_cost": "{1}",
        "targets": [
            {"id": "from", "kind": "permanent", "count": 1,
             "selector": {"zone": "battlefield", "controller": "you"}},
            {"id": "onto", "kind": "permanent", "count": 1,
             "selector": {"zone": "battlefield", "controller": "any"}},
        ],
        "spell_effects": [
            {"op": "move_counters", "from": {"target": "from"}, "objects": {"target": "onto"},
             "any_kind": True, "amount": {"const": 1}}
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

    def test_a_named_kind_is_refused(self):
        with pytest.raises(DslError, match="contradict"):
            compile_card(self._with(counter="+1/+1"))

    def test_all_kinds_beside_it_is_refused(self):
        with pytest.raises(DslError, match="all_kinds"):
            compile_card(self._with(all_kinds=True))

    def test_a_missing_amount_is_refused(self):
        with pytest.raises(DslError, match="'amount'"):
            compile_card(self._with(amount=None))

    def test_up_to_is_refused(self):
        with pytest.raises(DslError, match="'up_to' only means anything"):
            compile_card(self._with(up_to=True))
