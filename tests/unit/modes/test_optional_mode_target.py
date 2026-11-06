"""An "up to one" target owned by one mode -- 601.2b, 601.2c and 115.1.

    Summon: Magus Sisters -- "I, II, III -- Choose one at random --
    * Combine Powers! -- Put three +1/+1 counters on target creature.
    * Defense! -- Put a shield counter on target creature. You gain 3 life.
    * Fight! -- This creature fights **up to one** target creature an opponent
      controls."

"Up to one target" is a target the controller may decline (601.2c lets zero
be chosen), so the Fight bullet is choosable with no opposing creature at all:
601.2b strikes off only a mode *with no legal way to declare its targets*, and
declaring none is a legal way. Each nearer spelling is a different card:

* a fixed ``count: 1`` mode target forces the fight whenever an opponent has a
  creature, and with none it strikes Fight! out of the random pool, so the
  other two bullets come up half the time each instead of a third;
* a card-level ``optional`` target is declared whatever mode is chosen, and
  cannot share the card with the other bullets' mode-owned targets.

The machinery's one hazard is positional: `filter_legal` splits stored refs
spec by spec, and a declined target stores none. So the loader admits an
``optional`` mode-owned spec only where it ends every declaration -- the last
spec of its mode, no later mode owning a target -- and these tests pin both
that boundary and the behaviour it buys.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import stack as stack_module
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.stack import push_triggered_ability, resolve_top
from commanderblitz.engine.structs import TriggerInstance
from tests.conftest import action_for_card

SISTERS = "t_sisters"
RANDOM_SISTERS = "t_random_sisters"
VOLLEY = "t_up_to_one_volley"
COUNTERS = "Put three +1/+1 counters on target creature."
FIGHT = "This creature fights up to one target creature an opponent controls."
DAMAGE = "Test Volley deals 2 damage to up to one target creature an opponent controls."


def board(builder, source: str, *, foes: int = 1, hand: tuple[str, ...] = ()):
    """``source`` on player 0's battlefield beside a bear, ``foes`` bears opposite.

    Returns ``(game, source_oid, foe_oids)``.
    """
    game = (
        builder(players=2)
        .battlefield(0, [source, "t_bear"] + ["forest"] * 4)
        .hand(0, list(hand))
        .battlefield(1, ["t_bear"] * foes)
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .build()
    )
    oid = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == source)
    foe_oids = [o.oid for o in game.state.battlefield_objects(1) if o.def_id == "t_bear"]
    return game, oid, foe_oids


def push(game, source: int, def_id: str, answers: tuple[str, ...] = ()):
    """Put the trigger on the stack, answering by label; ``""`` declines.

    Returns ``(item, decisions)`` -- every decision asked, so a test can claim
    what was offered.
    """
    trig = TriggerInstance(source_oid=source, ability_index=0, controller=0, def_id=def_id)
    generator = push_triggered_ability(game.state, trig)
    remaining = list(answers)
    asked = []
    send: list[int] | None = None
    while True:
        try:
            decision = generator.send(send)
        except StopIteration as stop:
            assert not remaining, f"never asked about {remaining}"
            return stop.value, asked
        asked.append(decision)
        labels = [option.label for option in decision.options]
        assert remaining, f"unexpected question: {labels}"
        want = remaining.pop(0)
        assert want in labels, f"{want!r} not offered; got {labels}"
        send = [labels.index(want)]


def resolve(game) -> None:
    generator = resolve_top(game.state)
    send: list[int] | None = None
    while True:
        try:
            generator.send(send)
        except StopIteration:
            return
        send = [0]


def damage(game, oid: int) -> int:
    return game.state.objects[oid].damage


class TestOnATrigger:
    def test_the_mode_is_offered_with_nothing_to_target(self, builder):
        """601.2b: declaring zero targets is a legal declaration."""
        game, source, _ = board(builder, SISTERS, foes=0)
        item, asked = push(game, source, SISTERS, (FIGHT,))
        assert [o.label for o in asked[0].options] == [COUNTERS, FIGHT]
        assert item.modes == (1,)
        assert item.targets == ()
        resolve(game)  # fights nothing, and resolves rather than fizzling

    def test_the_target_may_be_declined_when_one_exists(self, builder):
        game, source, (foe,) = board(builder, SISTERS)
        item, asked = push(game, source, SISTERS, (FIGHT, "no targets"))
        labels = [o.label for o in asked[1].options]
        assert labels[-1] == "no targets" and len(labels) == 2
        assert item.targets == ()
        resolve(game)
        assert damage(game, foe) == 0
        assert damage(game, source) == 0

    def test_a_declared_target_is_fought(self, builder):
        game, source, (foe,) = board(builder, SISTERS)
        item, _ = push(game, source, SISTERS, (FIGHT, "Test Bear"))
        assert [ref.id for ref in item.targets] == [foe]
        resolve(game)
        assert damage(game, source) == 2  # the bear's power
        assert damage(game, foe) == 3  # this creature's

    def test_the_other_mode_keeps_its_own_fixed_target(self, builder):
        """Mode 0's spec precedes the optional one, so its ref is read back
        into its own bucket."""
        game, source, _ = board(builder, SISTERS)
        bear = next(
            o.oid for o in game.state.battlefield_objects(0) if o.def_id == "t_bear"
        )
        item, _ = push(game, source, SISTERS, (COUNTERS, "Test Bear"))
        assert item.modes == (0,)
        resolve(game)
        assert game.state.objects[bear].counter("+1/+1") == 3


class TestAtRandom:
    @pytest.mark.parametrize("foes", [0, 1])
    def test_the_random_pool_keeps_the_mode(self, builder, monkeypatch, foes):
        """Striking Fight! when no opponent has a creature would skew the odds."""
        seen: list[list[int]] = []
        real = stack_module.pick_at_random

        def spy(state, offered, count):
            seen.append(list(offered))
            return real(state, offered, count)

        monkeypatch.setattr(stack_module, "pick_at_random", spy)
        game, source, _ = board(builder, RANDOM_SISTERS, foes=foes)
        trig = TriggerInstance(
            source_oid=source, ability_index=0, controller=0, def_id=RANDOM_SISTERS
        )
        generator = push_triggered_ability(game.state, trig)
        send: list[int] | None = None
        while True:
            try:
                generator.send(send)
            except StopIteration:
                break
            send = [0]
        assert seen == [[0, 1]]


class TestOnASpell:
    def test_the_target_may_be_declined_inside_the_cast(self, builder):
        game, _, (foe,) = board(builder, "forest", hand=(VOLLEY,))
        game.apply(action_for_card(game, ActionKind.CAST, VOLLEY))
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert [o.label for o in decision.options] == [COUNTERS, DAMAGE]
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 1)
        )
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.min_count == 0
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )
        for _ in range(20):
            if not game.state.stack:
                break
            passes = [a for a in game.legal_actions() if a.kind is ActionKind.PASS]
            game.apply(passes[0])
        assert not game.state.stack
        assert damage(game, foe) == 0
        assert VOLLEY in [game.state.objects[o].def_id for o in game.state.players[0].graveyard]

    def test_the_mode_is_castable_with_nothing_to_target(self, builder):
        game, _, _ = board(builder, "forest", foes=0, hand=(VOLLEY,))
        game.apply(action_for_card(game, ActionKind.CAST, VOLLEY))
        assert [o.label for o in game.pending().options] == [COUNTERS, DAMAGE]


class TestTheLoaderBoundary:
    def base(self):
        return json_card(VOLLEY)

    def compile(self, card):
        compile_card(CardModel.model_validate(card))

    def test_the_last_target_declared_loads(self):
        self.compile(self.base())

    def test_not_last_when_a_later_mode_owns_a_target(self):
        card = self.base()
        card["targets"][0]["optional"] = True
        card["targets"][1]["optional"] = False
        with pytest.raises(DslError, match="must be the last target declared"):
            self.compile(card)

    def test_beside_a_card_level_optional_target(self):
        card = self.base()
        card["targets"].insert(
            0,
            {
                "id": "extra",
                "kind": "player",
                "optional": True,
                "selector": {},
            },
        )
        card["spell_effects"].append({"op": "draw", "player": {"target": "extra"}})
        with pytest.raises(DslError, match="card-level 'optional' target"):
            self.compile(card)


def json_card(card_id: str) -> dict:
    path = Path(__file__).resolve().parents[2] / "data" / "optional_mode_target.cards.json"
    cards = json.loads(path.read_text(encoding="utf-8"))["cards"]
    return next(card for card in cards if card["id"] == card_id)
