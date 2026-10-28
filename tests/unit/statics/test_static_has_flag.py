"""A static's "as long as" can read a flag on its own source -- a Siege's mode.

    Windcrag Siege -- "As this enchantment enters, choose Mardu or Jeskai.
    * Mardu -- If a creature attacking causes a triggered ability of a
      permanent you control to trigger, that ability triggers an additional
      time.
    * Jeskai -- At the beginning of your upkeep, create a 1/1 red Goblin ..."

The choice is made once, as the permanent enters, and it switches one bullet on
for the rest of the permanent's life. Outpost Siege's two bullets are both
triggers, so `has_flag` in a trigger's condition was enough for it. Windcrag's
Mardu bullet is a **static** (a `double_triggers` over attack causes), and
without `has_flag` in the static condition language the bullet is on whichever
mode was chosen: a Jeskai Siege doubles every attack trigger as well as making
Goblins, which is both halves of the card at once.

Reading the flag keeps ADR 0001's pipeline acyclic: `GameObject.flags` is
object state that `set_flag` alone writes and a zone change alone clears (400.7),
and no layer reads or writes it, so it is a pipeline input as a counter is. A
counter is the near miss and is wrong: proliferate would add a second "Mardu",
and anything that removes counters would undo a choice the rules say is fixed.

The claims, each of which is one of those wrong cards if it breaks:

* the Mardu static is on after Mardu is chosen, and attack triggers resolve
  twice;
* the static is off after Jeskai is chosen, so the trigger resolves once;
* `set_flag` invalidates the characteristics cache, so a flag-gated buff is
  seen the moment the word is written rather than at the next unrelated change;
* the flag is lost with a zone change, so the static is off on the new object;
* the loader refuses a flag that is not a non-empty string.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import (
    action_for_card,
    advance_to_step,
    attack_with,
    only_oid,
    pass_until,
    pt,
    settle_completely,
    static_probe,
)

SIEGE = "t_flag_siege"
ANTHEM = "t_flag_anthem"
LIFEGAINER = "t_attack_lifegainer"


def cast_choosing(builder, card_id: str, mode: str, board=(LIFEGAINER,)):
    """Cast ``card_id`` from hand and answer its "as this enters" with ``mode``.

    Returns ``(game, oid)`` with the stack empty in the precombat main phase.
    """
    game = (
        builder(players=2)
        .battlefield(0, [*board, "mountain"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [card_id])
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_MODE,
    )
    decision = game.pending()
    index = next(o.value for o in decision.options if o.label == mode)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )
    if game.pending() is decision:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    settle_completely(game)
    return game, only_oid(game, card_id)


def life_from_one_attack(game) -> int:
    """Life player 0 gains from the lifegainer attacking once."""
    attacker = only_oid(game, LIFEGAINER)
    advance_to_step(game, Step.DECLARE_ATTACKERS)
    before = game.state.players[0].life
    attack_with(game, attacker)
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    settle_completely(game)
    return game.state.players[0].life - before


class TestTheChosenModeSwitchesTheStatic:
    def test_mardu_doubles_an_attack_trigger(self, builder):
        game, oid = cast_choosing(builder, SIEGE, "Mardu")
        assert "mardu" in game.state.objects[oid].flags
        assert life_from_one_attack(game) == 2

    def test_jeskai_leaves_the_attack_trigger_single(self, builder):
        """The bullet that was not chosen is not on."""
        game, oid = cast_choosing(builder, SIEGE, "Jeskai")
        assert "mardu" not in game.state.objects[oid].flags
        assert life_from_one_attack(game) == 1


class TestTheCacheSeesTheWord:
    def test_a_flag_gated_buff_applies_once_the_choice_is_made(self, builder):
        game, oid = cast_choosing(builder, ANTHEM, "Mardu", board=())
        assert pt(game, oid) == (3, 3)

    def test_set_flag_alone_invalidates_a_warm_cache(self, builder):
        """No stack, no trigger: only the op's own bump can make `chars` re-read."""
        game = builder(players=2).battlefield(0, [ANTHEM]).build()
        oid = only_oid(game, ANTHEM)
        assert pt(game, oid) == (1, 1)  # warms the cache
        ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
        gen = execute(ctx, [{"op": "set_flag", "flag": "mardu"}])
        with contextlib.suppress(StopIteration):
            while True:
                next(gen)
        assert pt(game, oid) == (3, 3)

    def test_and_not_for_the_other_choice(self, builder):
        game, oid = cast_choosing(builder, ANTHEM, "Jeskai", board=())
        assert pt(game, oid) == (1, 1)


class TestAZoneChangeForgetsTheChoice:
    def test_the_new_object_has_chosen_nothing(self, builder):
        """400.7: flags are reset with the object, so the static goes off."""
        game, oid = cast_choosing(builder, ANTHEM, "Mardu", board=())
        assert pt(game, oid) == (3, 3)
        move_object(game.state, oid, Zone.HAND)
        new = game.state.players[0].hand[-1]
        assert "mardu" not in game.state.objects[new].flags


class TestTheLoaderRefusesAMalformedFlag:
    @pytest.mark.parametrize("flag", ["", 1, True, ["mardu"]])
    def test_a_flag_must_be_a_non_empty_string(self, flag):
        card = static_probe(
            {
                "effect": "double_triggers",
                "affects": {"controller": "you"},
                "condition": {"has_flag": flag},
            }
        )
        with pytest.raises(DslError, match="has_flag"):
            compile_card(CardModel.model_validate(card))

    def test_a_named_flag_loads(self):
        card = static_probe(
            {
                "effect": "double_triggers",
                "affects": {"controller": "you"},
                "condition": {"not": {"has_flag": "mardu"}},
            }
        )
        compile_card(CardModel.model_validate(card))
