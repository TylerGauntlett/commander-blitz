"""Extort (702.101) -- a keyword that is a triggered ability and nothing else.

    "Extort (Whenever you cast a spell, you may pay {W/B}. If you do, each
    opponent loses 1 life and you gain that much life.)"

Nothing here is new engine: a `spell_cast` trigger, a `may` with a hybrid `pay`,
`lose_life` on each opponent and `gain_life`. What was missing was **"that
much life"**. It is the life the opponents actually lost, which is one per
opponent only while nothing replaces the loss; the gap record for Crypt Ghast
filed extort as blocked because the only spelling available counted opponents.
`lose_life`'s ``as`` binding (test_life_lost_this_way.py) is the read.

The witness is `templates.extort_ability`, which the template tier writes onto
every bare "Extort" line (Syndic of Tithes, Basilica Guards, Crypt Ghast's first
line), and `t_extortioner` carries that exact ability -- pinned below, so the
card these tests play cannot drift from the one the pipeline writes.

The rules points, each with a test:

- 702.101a -- *any* spell you cast, creature spells included; not an opponent's.
- The payment is optional and {W/B} is hybrid: either colour pays it, and a
  player who can pay neither is not asked (a yes that could not be honoured).
- 702.101b -- each instance triggers separately, so two extorters ask twice.
- "That much" is the loss after replacement: a doubled drain gains double.
"""

from __future__ import annotations

import json
from pathlib import Path

from automtg.cards.authoring.templates import extort_ability
from automtg.engine.enums import ActionKind, DecisionKind
from tests.conftest import _default_answer, action_for_card, find_action

EXTORTER = "t_extortioner"
BEAR = "t_bear"  # {1}{G}, a creature spell -- extort does not care what is cast
DOUBLER = "t_always_bloodletter"
DATA = Path(__file__).resolve().parents[2] / "data" / "extort.cards.json"


def position(builder, *, players: int = 2, extorters: int = 1, payers=("swamp",), board=()):
    """Player 0 with ``extorters`` on the battlefield, two Forests for the Bear,
    and ``payers`` as the lands left for extort. Every seat at 20."""
    b = (
        builder(players=players)
        .hand(0, [BEAR])
        .battlefield(0, [EXTORTER] * extorters)
        .battlefield(0, ["forest", "forest", *payers])
        .battlefield(0, list(board))
        .active(0)
    )
    for pid in range(players):
        b = b.life(pid, 20)
    return b.build()


def cast_and_settle(game, *, say_yes: bool, limit: int = 60) -> int:
    """Cast the Bear, answer every extort prompt, resolve. Returns prompts seen."""
    game.apply(action_for_card(game, ActionKind.CAST, BEAR))
    asked = 0
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.MAY:
            asked += 1
            game.apply(find_action(game, ActionKind.YES if say_yes else ActionKind.NO))
            continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    return asked


def life(game) -> list[int]:
    return [p.life for p in game.state.players]


class TestTheTestCardIsTheTemplate:
    def test_t_extortioner_carries_exactly_the_template_ability(self):
        card = json.loads(DATA.read_text(encoding="utf-8"))["cards"][0]
        (ability,) = card["abilities"]
        assert ability == extort_ability(ability["text"])


class TestPaying:
    def test_paying_drains_each_opponent_and_gains_that_much(self, builder):
        game = position(builder)
        assert cast_and_settle(game, say_yes=True) == 1
        assert life(game) == [21, 19]

    def test_with_two_opponents_it_gains_two(self, builder):
        game = position(builder, players=3)
        cast_and_settle(game, say_yes=True)
        assert life(game) == [22, 19, 19]

    def test_white_mana_pays_the_hybrid_pip(self, builder):
        game = position(builder, payers=("plains",))
        assert cast_and_settle(game, say_yes=True) == 1
        assert life(game) == [21, 19]

    def test_the_payment_is_actually_taken(self, builder):
        game = position(builder)
        cast_and_settle(game, say_yes=True)
        swamps = [o for o in game.state.battlefield_objects(0) if o.def_id == "swamp"]
        assert all(o.tapped for o in swamps)


class TestNotPaying:
    def test_declining_changes_no_life_total(self, builder):
        game = position(builder)
        assert cast_and_settle(game, say_yes=False) == 1
        assert life(game) == [20, 20]

    def test_a_player_who_cannot_pay_is_not_asked(self, builder):
        """Only Islands left after the Bear: neither W nor B is available."""
        game = position(builder, payers=("island",))
        assert cast_and_settle(game, say_yes=True) == 0
        assert life(game) == [20, 20]


class TestWhatTriggersIt:
    def test_each_instance_triggers_separately(self, builder):
        """702.101b: two extorters, two prompts, two drains -- given the mana."""
        game = position(builder, extorters=2, payers=("swamp", "plains"))
        assert cast_and_settle(game, say_yes=True) == 2
        assert life(game) == [22, 18]

    def test_an_opponents_spell_does_not_trigger_it(self, builder):
        game = (
            builder(players=2)
            .hand(1, [BEAR])
            .battlefield(0, [EXTORTER, "swamp"])
            .battlefield(1, ["forest", "forest"])
            .life(0, 20)
            .life(1, 20)
            .active(1)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, BEAR))
        for _ in range(40):
            decision = game.pending()
            assert decision is None or decision.kind is not DecisionKind.MAY
            if decision is None or not game.state.stack:
                break
            game.apply(_default_answer(game, decision))
        assert life(game) == [20, 20]


class TestThatMuchLife:
    def test_a_doubled_loss_gains_the_doubled_amount(self, builder):
        """The reason extort waited on the binding: counting opponents gains 1."""
        game = position(builder, board=(DOUBLER,))
        cast_and_settle(game, say_yes=True)
        assert life(game) == [22, 18]
