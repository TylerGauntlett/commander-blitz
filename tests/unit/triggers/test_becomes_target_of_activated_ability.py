""""Whenever one or more creatures you control become the target of an
**activated ability**, draw a card. This ability triggers only once each turn."

Professor Hojo's second line. `targeted_by` could already say "a spell" (Goldspan
Dragon) and "an ability", but rule 113.3 names three kinds of ability on the
stack -- activated, triggered and the mana abilities that never reach it -- and
the ``ability`` arm reads only `is_spell`, so it answers "activated or
triggered". Written with it, Hojo draws off an opponent's enters trigger that
taps its creature, which is a wider card than the printed one.

**The kind was already on the item.** `StackItem.ability_kind` is recorded as
`push_activated_ability` and `push_triggered_ability` put the ability on the
stack (Strionic Resonator reads it), and a copy keeps it through
`dataclasses.replace` (707.10). `stack.announce_targets` now copies it onto
every BECAME_TARGET, and ``targeted_by: "activated_ability"`` compares against
it -- as a presence, like the spell arm, so an event that does not say
``"activated"`` never fires it.

**"One or more … only once each turn" is ``max_per_turn: 1``.** The batch is the
one ability's targets; the per-turn cap already folds every later event of the
turn, the rest of that batch included, so a ``batched`` flag would add no
firing the cap does not already refuse.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import TargetRef
from tests.conftest import oids_of, only_oid, settle

HOJO = "t_hojo_drawer"  # targeted_by: "activated_ability", max_per_turn 1
WIDE = "t_hojo_wide_drawer"  # the near miss: targeted_by: "ability"
TAPPER = "t_enter_tapper"  # {U}, enters: tap target creature an opponent controls
PASSAGE = "t_passage"  # {4}, {T}: target creature can't be blocked this turn
PUMP = "t_pump_spell"  # {G} instant, targets a creature
BEAR = "t_bear"


def draws(game, drawer: str = HOJO) -> int:
    """How many times the drawer's ability resolved.

    Counted off the log rather than the hand: a seat with nothing to do is
    auto-passed, so the turn can roll on into its owner's draw step before the
    test looks.
    """
    return sum(
        1
        for e in game.state.events
        if e.type is EventType.ABILITY_RESOLVED and e.data.get("card") == drawer
    )


def activate_at(game, source_oid: int, target_oid: int) -> None:
    for action in game.legal_actions():
        if (
            action.kind is ActionKind.ACTIVATE
            and action.source == source_oid
            and TargetRef.obj(target_oid) in action.targets
        ):
            game.apply(action)
            return
    raise AssertionError(
        f"no activation of {source_oid} at {target_oid}; "
        f"legal: {[(a.kind.value, a.label) for a in game.legal_actions()]}"
    )


def cast(game, card_id: str, target_oid: int | None = None) -> None:
    for action in game.legal_actions():
        if action.kind is not ActionKind.CAST or action.source is None:
            continue
        if game.state.objects[action.source].def_id != card_id:
            continue
        if target_oid is not None and TargetRef.obj(target_oid) not in action.targets:
            continue
        game.apply(action)
        return
    raise AssertionError(f"no cast of {card_id}")


def passage_position(builder, drawer: str = HOJO, *, theirs=()):
    """The drawer and a Bear beside two Passages and mana for both."""
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * 8 + [PASSAGE, PASSAGE, BEAR, drawer])
        .battlefield(1, list(theirs))
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def tapper_position(builder, drawer: str):
    """The opponent, active, about to cast a creature whose enters trigger taps
    the drawer -- the only creature its controller has."""
    return (
        builder(players=2)
        .battlefield(0, [drawer])
        .battlefield(1, ["island"])
        .hand(1, [TAPPER])
        .step(Step.PRECOMBAT_MAIN)
        .active(1)
        .build()
    )


class TestAnActivatedAbilityFiresIt:
    def test_your_own_activation_at_another_creature_you_control(self, builder):
        game = passage_position(builder)
        passage = oids_of(game, PASSAGE, 0)[0]
        activate_at(game, passage, only_oid(game, BEAR, 0))
        settle(game)
        assert draws(game) == 1

    def test_an_opponents_activation(self, builder):
        """No controller is printed: an opponent's ability aimed at your
        creature draws too."""
        game = (
            builder(players=2)
            .battlefield(0, [HOJO])
            .battlefield(1, ["mountain"] * 4 + [PASSAGE])
            .step(Step.PRECOMBAT_MAIN)
            .active(1)
            .build()
        )
        activate_at(game, only_oid(game, PASSAGE, 1), only_oid(game, HOJO, 0))
        settle(game)
        assert draws(game) == 1

    def test_a_creature_you_do_not_control_does_not(self, builder):
        game = passage_position(builder, theirs=(BEAR,))
        passage = oids_of(game, PASSAGE, 0)[0]
        activate_at(game, passage, only_oid(game, BEAR, 1))
        settle(game)
        assert draws(game) == 0


class TestOnlyOnceEachTurn:
    def test_a_second_activation_the_same_turn_does_not_draw(self, builder):
        game = passage_position(builder)
        first, second = oids_of(game, PASSAGE, 0)
        activate_at(game, first, only_oid(game, BEAR, 0))
        settle(game)
        activate_at(game, second, only_oid(game, HOJO, 0))
        settle(game)
        assert draws(game) == 1


class TestATriggeredAbilityDoesNot:
    def test_an_opponents_enters_trigger(self, builder):
        """The whole of the restriction: the tapper's trigger is an ability,
        but not an activated one."""
        game = tapper_position(builder, HOJO)
        cast(game, TAPPER)
        settle(game)
        assert any(
            e.type is EventType.TAPPED and e.data.get("oid") == only_oid(game, HOJO, 0)
            for e in game.state.events
        )
        assert draws(game) == 0

    def test_the_ability_arm_is_the_wider_card(self, builder):
        """The near miss, kept live and measured: `"ability"` still means both
        kinds, so no shipped card's reading moved."""
        game = tapper_position(builder, WIDE)
        cast(game, TAPPER)
        settle(game)
        assert draws(game, WIDE) == 1


class TestASpellDoesNot:
    def test_a_spell_at_a_creature_you_control(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest", BEAR, HOJO])
            .hand(0, [PUMP])
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        cast(game, PUMP, only_oid(game, BEAR, 0))
        settle(game)
        assert draws(game) == 0


class TestTheKindIsOnTheEvent:
    """Read straight off the payload, so the clause and what it compares against
    cannot drift apart."""

    def became_target(self, game):
        (fired,) = [e for e in game.state.events if e.type is EventType.BECAME_TARGET]
        return fired

    def test_an_activated_ability_says_so(self, builder):
        game = passage_position(builder)
        activate_at(game, oids_of(game, PASSAGE, 0)[0], only_oid(game, BEAR, 0))
        assert self.became_target(game).data["ability_kind"] == "activated"

    def test_a_triggered_ability_says_so(self, builder):
        game = tapper_position(builder, HOJO)
        cast(game, TAPPER)
        settle(game)
        assert self.became_target(game).data["ability_kind"] == "triggered"

    def test_a_spell_names_no_ability_kind(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest", BEAR])
            .hand(0, [PUMP])
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        cast(game, PUMP, only_oid(game, BEAR, 0))
        assert self.became_target(game).data.get("ability_kind") is None


class TestTheClauseCompiles:
    def test_it_reaches_the_trigger_spec(self, registry):
        card = registry.get(HOJO)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger is not None
        assert ability.trigger.targeted_by == "activated_ability"
        assert ability.trigger.max_per_turn == 1
