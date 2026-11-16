"""Siren Stormtamer -- "Sacrifice this creature: Counter target spell or ability
**that targets you or a creature you control**."

Rule 115.10 (and the rulings on every card of this family): a spell or ability
"that targets" something is one where that thing is among its chosen targets.
The counter and the `spell_or_ability` target kind existed, but no selector
clause read what a stack object itself targets -- `_ability_matches` answered
`controller` and `ability_kind`, and the spell matcher read printed
characteristics only -- so the only expressible card was a strictly wider
counter-anything ability.

`that_targets` is that clause: `{"player": <player spec>}` and/or
`{"permanent": <selector>}`, met when **any** of the object's targets is such a
player or such a permanent, both read relative to the countering ability's
controller. The candidates and the re-check on resolution (608.2b) both ask it,
so a creature that changed controller in between makes the counter fizzle.

`t_stormtamer` is the witness; `t_nudge` (a spell), `t_hail` (a spell targeting
a player) and `t_nudger` (an activated ability) are what it is pointed at.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import activations, settle

TAMER = "t_stormtamer"
NUDGE = "t_nudge"
HAIL = "t_hail"
NUDGER = "t_nudger"
BEAR = "t_bear"


def position(builder, *, hand=(NUDGE,), mine=(BEAR,)):
    """Player 0's Stormtamer and ``mine``; player 1's bear; ``hand`` free spells.

    A spare Nudge always stays in hand, so player 0 keeps priority with a spell
    on the stack even when the Stormtamer has nothing to point at.
    """
    game = (
        builder(players=2)
        .battlefield(0, [TAMER, *mine, "island"])
        .battlefield(1, [BEAR])
        .hand(0, [*hand, NUDGE])
        .build()
    )
    state = game.state
    tamer = next(o for o in state.battlefield if state.card(o).id == TAMER)
    my_bear = next(o for o in state.battlefield if state.card(o).id == BEAR and state.objects[o].controller == 0)
    their_bear = next(o for o in state.battlefield if state.card(o).id == BEAR and state.objects[o].controller == 1)
    return game, tamer, my_bear, their_bear


def cast_at(game, card_id: str, ref: TargetRef) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.card(a.source).id == card_id
            and a.targets == (ref,)
        )
    )


def offered(game, tamer: int) -> set[TargetRef]:
    return {ref for a in activations(game, tamer) for ref in a.targets}


def top_ref(game) -> TargetRef:
    return TargetRef.stack(game.state.stack[-1].sid)


class TestWhatItMayTarget:
    def test_a_spell_targeting_a_creature_you_control(self, builder):
        game, tamer, mine, _ = position(builder)
        cast_at(game, NUDGE, TargetRef.obj(mine))
        assert top_ref(game) in offered(game, tamer)

    def test_not_a_spell_targeting_an_opponents_creature(self, builder):
        game, tamer, _, theirs = position(builder)
        cast_at(game, NUDGE, TargetRef.obj(theirs))
        assert top_ref(game) not in offered(game, tamer)

    def test_a_spell_targeting_you(self, builder):
        game, tamer, _, _ = position(builder, hand=(HAIL,))
        cast_at(game, HAIL, TargetRef.player(0))
        assert top_ref(game) in offered(game, tamer)

    def test_not_a_spell_targeting_an_opponent(self, builder):
        game, tamer, _, _ = position(builder, hand=(HAIL,))
        cast_at(game, HAIL, TargetRef.player(1))
        assert top_ref(game) not in offered(game, tamer)

    def test_an_ability_targeting_a_creature_you_control(self, builder):
        game, tamer, mine, _ = position(builder, hand=(), mine=(BEAR, NUDGER))
        nudger = next(o for o in game.state.battlefield if game.state.card(o).id == NUDGER)
        game.apply(next(a for a in activations(game, nudger) if a.targets == (TargetRef.obj(mine),)))
        assert top_ref(game) in offered(game, tamer)

    def test_not_an_ability_targeting_an_opponents_creature(self, builder):
        game, tamer, _, theirs = position(builder, hand=(), mine=(BEAR, NUDGER))
        nudger = next(o for o in game.state.battlefield if game.state.card(o).id == NUDGER)
        game.apply(next(a for a in activations(game, nudger) if a.targets == (TargetRef.obj(theirs),)))
        assert top_ref(game) not in offered(game, tamer)


class TestTheCounter:
    def test_it_counters_the_spell(self, builder):
        game, tamer, mine, _ = position(builder)
        cast_at(game, NUDGE, TargetRef.obj(mine))
        spell = game.state.stack[-1].oid
        ref = top_ref(game)
        game.apply(next(a for a in activations(game, tamer) if a.targets == (ref,)))
        settle(game)
        assert game.state.objects[spell].zone is Zone.GRAVEYARD
        assert game.state.objects[tamer].zone is Zone.GRAVEYARD
        assert game.state.objects[mine].counters.get("+1/+1", 0) == 0

    def test_it_fizzles_once_the_creature_is_no_longer_yours(self, builder):
        """608.2b: the target is re-checked against the clause on resolution."""
        game, tamer, mine, _ = position(builder)
        cast_at(game, NUDGE, TargetRef.obj(mine))
        ref = top_ref(game)
        game.apply(next(a for a in activations(game, tamer) if a.targets == (ref,)))
        game.state.objects[mine].controller = 1
        game.state.bump_chars()
        settle(game)
        assert game.state.objects[mine].counters.get("+1/+1", 0) == 1


def _probe(target: dict) -> CardModel:
    text = "Sacrifice this creature: Counter target spell."
    return CardModel.model_validate(
        {
            "id": "t_that_targets_probe",
            "name": "Test That Targets Probe",
            "oracle_text": text,
            "mana_cost": "{1}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "activated",
                    "text": text,
                    "cost": {"sacrifice": {"self_only": True}},
                    "targets": [{"id": "t1", "count": 1, **target}],
                    "effects": [{"op": "counter", "target": "t1"}],
                }
            ],
        }
    )


class TestTheLoader:
    @pytest.mark.parametrize("kind", ["spell", "ability_on_stack", "spell_or_ability"])
    def test_it_is_read_on_every_stack_target_kind(self, kind):
        compile_card(
            _probe({"kind": kind, "selector": {"that_targets": {"player": "you"}}}), source="test"
        )

    def test_it_is_refused_on_a_permanent_target(self):
        with pytest.raises(DslError, match="that_targets"):
            compile_card(
                _probe({"kind": "permanent", "selector": {"that_targets": {"player": "you"}}}),
                source="test",
            )

    def test_an_unknown_clause_is_refused(self):
        with pytest.raises(DslError, match="that_targets"):
            compile_card(
                _probe({"kind": "spell", "selector": {"that_targets": {"card": {}}}}), source="test"
            )

    def test_an_empty_clause_is_refused(self):
        with pytest.raises(DslError, match="that_targets"):
            compile_card(_probe({"kind": "spell", "selector": {"that_targets": {}}}), source="test")
