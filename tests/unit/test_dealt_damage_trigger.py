"""Enrage (702.131): "Whenever this creature is dealt damage, …".

The census lists enrage as needing "a 'this was dealt damage' trigger event",
and that turned out to be half true. The *event* was already there:
`DAMAGE_DEALT` has been fired through the trigger bus by `damage_permanent`
since combat was written, and nothing had ever subscribed to it. What was
missing was the subscription, which is one row in `TRIGGER_EVENTS` — the same
shape `creature_dies` is, sugar over an event that covers more than the trigger
wants.

Two things make it more than a row, and both would be silently wrong rather
than loud:

**One event, two shapes.** `DAMAGE_DEALT` is fired for damage to a *player* as
well as to a permanent, and the two carry different payloads: the player form's
`player` field is the player being hit, where the permanent form's is the
controller of the creature that was hit. An unguarded subscription would fire
every enrage creature on the board whenever anybody took a Lightning Bolt to the
face. The event says which shape it is in `to`, so the guard reads that rather
than inferring it from a missing `oid`.

**`source: "self"` means the victim, not the dealer.** For nearly every other
trigger the subject of the event and its source are the same object, so
`_matches` accepts either. Here they are the creature that was hurt and the
creature that hurt it. Without a stricter check a creature would trigger its own
enrage every time it dealt combat damage, which is both wrong and the exact
opposite of what the keyword is for.

"That much damage" is free: `_queue` has always carried `amount` into the
trigger's bindings, so `{"binding": "amount"}` reads the damage that was dealt.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.primitives import damage_permanent, damage_player
from automtg.engine.structs import TargetRef
from automtg.engine.zones import move_object
from tests.conftest import _default_answer, find_action, only_oid, pass_until, plus_one_counters

ENRAGER = "t_enrager"  # 3/4, "whenever dealt damage, put a +1/+1 counter on it"
AVENGER = "t_avenger"  # 4/4, "whenever dealt damage, it deals that much to target player"
BEAR = "t_bear"  # 2/2


def position(builder, card: str = ENRAGER, *, opposing=()):
    """`card` on player 0's battlefield, frozen in a main phase."""
    b = builder(players=2).battlefield(0, [card]).step(Step.PRECOMBAT_MAIN)
    if opposing:
        b = b.battlefield(1, list(opposing))
    game = b.build(advance=False)
    return game, only_oid(game, card, 0)


def settle(game, limit: int = 40) -> None:
    """Resolve whatever the trigger put on the stack."""
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the trigger never resolved")


class TestItFiresOnDamage:
    def test_damage_triggers_it(self, builder):
        game, oid = position(builder)
        damage_permanent(game.state, oid, 1, None)
        settle(game)
        assert plus_one_counters(game, oid) == 1

    def test_no_damage_no_trigger(self, builder):
        """The boundary: `damage_permanent` returns early on a non-positive
        amount, so nothing is dealt and nothing may fire."""
        game, oid = position(builder)
        damage_permanent(game.state, oid, 0, None)
        settle(game)
        assert plus_one_counters(game, oid) == 0

    def test_it_fires_once_per_source_not_once_per_point(self, builder):
        """Rule 120.3: damage is dealt in one event, however much of it there
        is. An enrage creature hit for three grows by one, not by three."""
        game, oid = position(builder)
        damage_permanent(game.state, oid, 3, None)
        settle(game)
        assert plus_one_counters(game, oid) == 1

    def test_two_separate_sources_fire_twice(self, builder):
        game, oid = position(builder)
        damage_permanent(game.state, oid, 1, None)
        settle(game)
        damage_permanent(game.state, oid, 1, None)
        settle(game)
        assert plus_one_counters(game, oid) == 2


class TestItDoesNotFireOnDamageThatIsNotItsOwn:
    """Every one of these is a wrong *number* rather than an error."""

    def test_damage_to_a_player_does_not_fire_it(self, builder):
        """The two shapes of `DAMAGE_DEALT`, and the reason the guard reads `to`."""
        game, oid = position(builder)
        damage_player(game.state, 1, 3, None)
        settle(game)
        assert plus_one_counters(game, oid) == 0, (
            "a bolt to the face is not damage dealt to this creature"
        )

    def test_damage_to_another_creature_does_not_fire_it(self, builder):
        game, oid = position(builder, opposing=[BEAR])
        damage_permanent(game.state, only_oid(game, BEAR, 1), 2, None)
        settle(game)
        assert plus_one_counters(game, oid) == 0

    def test_dealing_damage_does_not_fire_it(self, builder):
        """`source: "self"` is about being hurt, not about hurting.

        `event.source` on a damage event is the creature *dealing* it, and the
        generic self-check in `_matches` accepts the source as well as the
        subject -- correctly, for every trigger where the two are one object.
        """
        game, oid = position(builder, opposing=[BEAR])
        damage_permanent(game.state, only_oid(game, BEAR, 1), 2, oid)
        settle(game)
        assert plus_one_counters(game, oid) == 0, (
            "the enrager dealt the damage; nothing was dealt to it"
        )


class TestCombatDamageFiresIt:
    """The path enrage is actually printed for, and it needed no combat change."""

    def test_a_blocker_that_survives_grows(self, builder):
        """A 2/2 attacks into the 3/4; the 3/4 blocks, lives, and enrages.

        Player 1 is the active player, so the enrager is blocking rather than
        attacking -- which is how the keyword is nearly always used, and the
        only way to be dealt combat damage without dealing it first in the same
        breath.
        """
        game = (
            builder(players=2)
            .battlefield(0, [ENRAGER])
            .battlefield(1, [BEAR])
            .active(1)
            .build()
        )
        enrager = only_oid(game, ENRAGER, 0)
        attacker = only_oid(game, BEAR, 1)
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=attacker, targets=(TargetRef.player(0),)
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS,
        )
        game.apply(
            find_action(
                game, ActionKind.ADD_BLOCKER, source=enrager, targets=(TargetRef.obj(attacker),)
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        settle(game)
        assert plus_one_counters(game, enrager) == 1, "the 2/2 dealt it two damage and it survived"
        assert chars(game.state, enrager).toughness == 5


class TestTheAmountIsReadable:
    def test_the_binding_carries_the_real_number(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [AVENGER])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        oid = only_oid(game, AVENGER, 0)
        lives = [p.life for p in game.state.players]
        damage_permanent(game.state, oid, 3, None)
        settle(game)
        after = [p.life for p in game.state.players]
        assert sum(lives) - sum(after) == 3, (
            "the avenger deals *that much* damage -- three, not one and not four"
        )


class TestTheTriggerSurvivesItsSource:
    def test_lethal_damage_still_triggers_it(self, builder):
        """Rule 603.10 in spirit: the ability triggered when the damage was
        dealt, and the creature dying to it afterwards does not un-trigger it."""
        game, oid = position(builder, AVENGER)
        lives = [p.life for p in game.state.players]
        damage_permanent(game.state, oid, 4, None)
        move_object(game.state, oid, Zone.GRAVEYARD)
        settle(game)
        after = [p.life for p in game.state.players]
        assert sum(lives) - sum(after) == 4


class TestTheLoaderKnowsIt:
    def test_the_event_name_is_accepted(self, registry):
        card = registry.get(ENRAGER)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger is not None
        assert ability.trigger.event == "dealt_damage"

    def test_an_unknown_event_is_still_refused(self):
        import pytest

        from automtg.cards.loader import compile_card
        from automtg.cards.schema import CardModel
        from automtg.engine.errors import DslError

        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "bogus",
                        "name": "Bogus",
                        "oracle_text": "x",
                        "mana_cost": "{G}",
                        "types": ["Creature"],
                        "power": 1,
                        "toughness": 1,
                        "abilities": [
                            {
                                "kind": "triggered",
                                "text": "x",
                                "trigger": {"event": "dealt_damage_maybe", "source": "self"},
                                "effects": [{"op": "noop"}],
                            }
                        ],
                    }
                )
            )
