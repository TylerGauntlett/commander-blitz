""""Whenever this creature attacks or **becomes the target of a spell**, create a
Treasure token."

Goldspan Dragon's second line, and the half of `becomes_target` that could not be
written. The event shipped with heroic and ward, whose printed text is "a spell
**or ability** an opponent controls" -- so the unrestricted event is exactly right
there and exactly wrong here, and nothing on `TriggerSpec` could tell the two
apart:

- `filter` is matched against the trigger's **subject**, which for this event is
  the permanent being targeted (`OBJECT_SUBJECT_TRIGGERS`). It can only ask what
  the Dragon is, never what aimed at it.
- `controller` asks *whose* spell or ability it was -- the axis that separates
  heroic from ward, and not this one.
- `condition` reads `event_bindings`, which copies only `EVENT_BINDING_KEYS`. That
  carries the `sid` and not the kind.

So the trigger a card could write was the wide one, and a Dragon written with it
mints a Treasure off an opponent's tapper, off a fight ability, and off its own
controller's equip. `TestTheUnclausedSpellingIsWider` keeps that card alive and
measures it.

**The payload was already there.** `stack.announce_targets` has put `is_spell` on
every BECAME_TARGET it fires since the event existed -- for the object and the
player half, and at all four push sites. Nothing read it. `targeted_by` is one
spec field and one comparison, and it is a restriction on the trigger rather than
a new event for the reason `mana_ability` is: the distinction is a property of the
thing that caused the event, which no condition key can reach, and a second event
type would duplicate four fire sites and a frontend narration to say what the
existing event already says.

**Why the near miss is not equivalent.** The other way to spell this line is a
`spell_cast` trigger with an intervening-if of `{"exists": {"binding":
"spell_targets", "self_only": true, ...}}` -- the Orvar, the All-Form shape, kept
live here as `t_orvar_dragon`. It is wrong twice, and both are ordinary lines of
play rather than corner cases:

1. **It misses a copy.** Rule 706.10 puts a copy on the stack without casting it,
   so `put_copy_on_stack` fires BECAME_TARGET and no SPELL_CAST -- and
   `spell_targets` is written by `Game._cast`, which never ran.
2. **Rule 603.4 re-asks an intervening-if on resolution.** Kill the Dragon in
   response and the condition finds nothing on the battlefield, so the Treasure is
   silently skipped -- which is the exact interaction the printed card exists for.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import TargetRef
from tests.conftest import _default_answer, only_oid

SPELL_DRAGON = "t_spell_dragon"  # "…becomes the target of a spell"
ABILITY_DRAGON = "t_ability_dragon"  # the other arm of the same clause
WIDE_DRAGON = "t_wide_dragon"  # ward's "a spell or ability" -- the control
ORVAR_DRAGON = "t_orvar_dragon"  # the near miss: spell_cast + intervening-if

PUMP = "t_pump_spell"  # {G} instant, targets a creature
BOLT = "t_bolt"  # {R} instant, 3 damage to any target
BEAR = "t_bear"
COPIER = "t_plain_copier"  # copies your instants, keeping their targets
SWEEP = "t_instant_sweep"  # {2}{B} instant, destroy all creatures -- targets nothing
PASSAGE = "t_passage"  # {4}, {T}: target creature can't be blocked this turn
TREASURE = "treasure_token"


def settle(game, limit: int = 80) -> None:
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def treasures(game, pid: int = 0) -> int:
    return sum(
        1
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == TREASURE
        and game.state.objects[oid].controller == pid
    )


def _act(game, kind: ActionKind, card_id: str, target_oid: int | None = None):
    for action in game.legal_actions():
        if action.kind is not kind or action.source is None:
            continue
        obj = game.state.objects.get(action.source)
        if obj is None or obj.def_id != card_id:
            continue
        if target_oid is not None and TargetRef.obj(target_oid) not in action.targets:
            continue
        game.apply(action)
        return
    raise AssertionError(
        f"no {kind.value} of {card_id} at {target_oid}; "
        f"legal: {[(a.kind.value, a.label) for a in game.legal_actions()]}"
    )


def cast_at(game, card_id: str, target_oid: int | None = None) -> None:
    _act(game, ActionKind.CAST, card_id, target_oid)


def activate_at(game, card_id: str, target_oid: int) -> None:
    _act(game, ActionKind.ACTIVATE, card_id, target_oid)


def spell_position(builder, dragon: str, *, board=(), hand=(PUMP,)):
    """The Dragon out, with mana for anything in hand."""
    return (
        builder(players=2)
        .battlefield(0, ["forest", "island", "island", "island", *board, dragon])
        .hand(0, list(hand))
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def ability_position(builder, dragon: str):
    """The Dragon out beside a land whose activated ability targets a creature."""
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * 4 + [PASSAGE, dragon])
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


class TestASpellFiresIt:
    def test_your_own_spell(self, builder):
        game = spell_position(builder, SPELL_DRAGON)
        cast_at(game, PUMP, only_oid(game, SPELL_DRAGON, 0))
        settle(game)
        assert treasures(game) == 1

    def test_an_opponents_spell(self, builder):
        """`controller` is not this clause. Goldspan Dragon names no caster, so
        the removal spell aimed at killing it pays for the Treasure too."""
        game = (
            builder(players=2)
            .battlefield(0, [SPELL_DRAGON])
            .battlefield(1, ["mountain"])
            .hand(1, [BOLT])
            .step(Step.PRECOMBAT_MAIN)
            .active(1)
            .build()
        )
        cast_at(game, BOLT, only_oid(game, SPELL_DRAGON, 0))
        settle(game)
        assert treasures(game) == 1

    def test_a_spell_aimed_at_something_else_does_not(self, builder):
        game = spell_position(builder, SPELL_DRAGON, board=(BEAR,))
        cast_at(game, PUMP, only_oid(game, BEAR, 0))
        settle(game)
        assert treasures(game) == 0

    def test_a_copy_of_a_spell_fires_it_again(self, builder):
        """706.10 -- a copy is *put on the stack*, never cast, and
        `put_copy_on_stack` announces its targets for exactly this reason."""
        game = spell_position(builder, SPELL_DRAGON, board=(COPIER,))
        cast_at(game, PUMP, only_oid(game, SPELL_DRAGON, 0))
        settle(game)
        assert treasures(game) == 2


class TestAnAbilityDoesNot:
    def test_your_own_activated_ability(self, builder):
        """The whole of the restriction: without it the Dragon pays its
        controller for equipping it."""
        game = ability_position(builder, SPELL_DRAGON)
        activate_at(game, PASSAGE, only_oid(game, SPELL_DRAGON, 0))
        settle(game)
        assert treasures(game) == 0

    def test_the_other_arm_fires_on_the_ability(self, builder):
        game = ability_position(builder, ABILITY_DRAGON)
        activate_at(game, PASSAGE, only_oid(game, ABILITY_DRAGON, 0))
        settle(game)
        assert treasures(game) == 1

    def test_the_other_arm_does_not_fire_on_a_spell(self, builder):
        game = spell_position(builder, ABILITY_DRAGON)
        cast_at(game, PUMP, only_oid(game, ABILITY_DRAGON, 0))
        settle(game)
        assert treasures(game) == 0


class TestTheUnclausedSpellingIsWider:
    """Ward's printed "a spell or ability", kept live and measured.

    It is not a degenerate case to be removed: `carddef.ward_ability` writes
    exactly this trigger, so the unclaused form has to keep firing on both.
    """

    def test_it_fires_on_a_spell(self, builder):
        game = spell_position(builder, WIDE_DRAGON)
        cast_at(game, PUMP, only_oid(game, WIDE_DRAGON, 0))
        settle(game)
        assert treasures(game) == 1

    def test_it_also_fires_on_an_ability(self, builder):
        game = ability_position(builder, WIDE_DRAGON)
        activate_at(game, PASSAGE, only_oid(game, WIDE_DRAGON, 0))
        settle(game)
        assert treasures(game) == 1, (
            "the wide card is the strictly larger one the gap record refused to "
            "write -- a Dragon that mints a Treasure off its own equip"
        )

    def test_ward_still_asks_about_both(self, registry):
        """The shipped users of this event are all ward, and none of them wants
        the clause. `None` has to stay the unrestricted reading."""
        card = registry.get("t_warded")
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger is not None
        assert ability.trigger.event == "becomes_target"
        assert ability.trigger.targeted_by is None


class TestTheNearMissIsNotEquivalent:
    """`spell_cast` with an intervening-if on `spell_targets` -- the Orvar shape.

    Both failures are silent: the card simply makes one fewer Treasure than the
    printed one, in a line of play nobody would think to check.
    """

    def test_it_misses_a_copy(self, builder):
        game = spell_position(builder, ORVAR_DRAGON, board=(COPIER,))
        cast_at(game, PUMP, only_oid(game, ORVAR_DRAGON, 0))
        settle(game)
        assert treasures(game) == 1, (
            "the copy was put on the stack, not cast, so SPELL_CAST never fired "
            "and `spell_targets` -- which `Game._cast` writes -- was never there"
        )

    def test_removing_the_dragon_in_response_skips_the_treasure(self, builder):
        """603.4: an intervening-if is re-checked as the ability resolves."""
        game, _ = self.removal_position(builder, ORVAR_DRAGON)
        settle(game)
        assert treasures(game) == 0, (
            "the condition was re-asked on resolution and found no Dragon on the "
            "battlefield -- the Treasure the printed card had already earned"
        )

    def test_the_trigger_keeps_the_treasure(self, builder):
        """The same position, the same removal, the restricted trigger."""
        game, dragon = self.removal_position(builder, SPELL_DRAGON)
        settle(game)
        assert game.state.objects[dragon].zone is not Zone.BATTLEFIELD
        assert treasures(game) == 1

    def removal_position(self, builder, dragon: str):
        """Pump the Dragon, then sweep it away before the trigger resolves.

        The sweeper targets nothing, so it cannot fire the trigger itself and
        muddy the count -- which any removal *spell* aimed at the Dragon would.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["forest", dragon])
            .hand(0, [PUMP])
            .battlefield(1, ["swamp"] * 3)
            .hand(1, [SWEEP])
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        oid = only_oid(game, dragon, 0)
        cast_at(game, PUMP, oid)
        for _ in range(20):
            decision = game.pending()
            if decision is None:
                game._advance()
                continue
            if decision.kind is DecisionKind.PRIORITY and decision.player == 1:
                break
            game.apply(_default_answer(game, decision))
        assert len(game.state.stack) == 2, (
            "the spell and the trigger it queued, with the opponent holding "
            f"priority: {[i.description for i in game.state.stack]}"
        )
        cast_at(game, SWEEP)
        return game, oid


class TestTheFlagIsOnTheEvent:
    """Read straight off the payload, so the clause and what it compares against
    cannot drift apart. `is_spell` sat there unread for the whole life of the
    event, which is the failure this pins."""

    def test_a_spell_says_so(self, builder):
        game = spell_position(builder, WIDE_DRAGON)
        cast_at(game, PUMP, only_oid(game, WIDE_DRAGON, 0))
        (fired,) = [e for e in game.state.events if e.type is EventType.BECAME_TARGET]
        assert fired.data["is_spell"] == 1

    def test_an_ability_says_so(self, builder):
        game = ability_position(builder, WIDE_DRAGON)
        activate_at(game, PASSAGE, only_oid(game, WIDE_DRAGON, 0))
        (fired,) = [e for e in game.state.events if e.type is EventType.BECAME_TARGET]
        assert fired.data["is_spell"] == 0


class TestTheLoaderGuardsTheClause:
    def base(self, trigger: dict) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{U}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "x",
                    "trigger": trigger,
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }

    def test_it_is_refused_on_another_event(self):
        """The inert-card failure: on `spell_cast` it reads as "of a spell" and
        is a restriction that never applies, so the ability never fires."""
        with pytest.raises(DslError, match="targeted_by"):
            compile_card(
                CardModel.model_validate(
                    self.base({"event": "spell_cast", "targeted_by": "spell"})
                )
            )

    def test_an_unknown_value_is_refused(self):
        with pytest.raises(ValidationError):
            CardModel.model_validate(
                self.base({"event": "becomes_target", "targeted_by": "sorcery"})
            )

    def test_the_clause_compiles(self, registry):
        card = registry.get(SPELL_DRAGON)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger is not None
        assert ability.trigger.targeted_by == "spell"
