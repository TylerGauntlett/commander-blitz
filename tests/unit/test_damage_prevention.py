"""Prevention over a **player** (rule 615), and the trigger that reads it back.

    "When this creature enters, prevent all damage that would be dealt to you
    this turn.
     Whenever damage that would be dealt to you is prevented, put that many
     +1/+1 counters on this creature."

Selfless Squire is the shipped witness and it needs both halves, which is why
they are one capability: the shield prevents, the event carries the amount, the
trigger reads it. Either half alone is a card that does nothing — a shield
nothing announces pays no counters, and a trigger with nothing to listen to
never fires.

**The shield is not the engine's existing prevention.** `prevent_damage` the
*static* is absorb N (702.63a) and is wrong on all three axes this needs:
`characteristics.prevented_damage(state, oid)` is keyed to an **object** and
matches each static's `affects` filter against a permanent, so there is no
player-facing form and `static_filter_keys` cannot name a seat; it is per source
and per instance by design rather than "all damage this turn"; and the loader
refuses it without an `amount`, so "all" cannot even be spelled. Worst of all it
is a *static*, continuous while its source stands on the battlefield — a Squire
carrying one would fog its controller on every future turn, which is a Worship.
`protection` is the other prevention and is likewise per-permanent, and also
stops blocking, targeting and enchanting.

So the shield is a turn-scoped record on the table (`GameState.damage_shields`)
beside `block_prohibitions` and `unblockables`, owned by no permanent — the
Squire may die to the very combat it was flashed into and the shield still
covers the turn.

**The hook did not exist.** `damage_player` went straight from the infect branch
to `life -= amount`: there was no point in the player-damage path where a
prevention could be consulted at all. The check goes in at the very top, because
prevented damage was *never dealt* — no life lost, no poison, no lifelink for
the attacker, no commander-damage tally and no `DAMAGE_DEALT` for the turn ledger
to count. Every one of those is a separate way the shield leaks if the check sits
lower, and the infect branch is the sharpest: a shielded player who still took
the poison would lose to a fog.

**The event was emitted at nobody.** `EventType.DAMAGE_PREVENTED` has existed
since absorb and was emitted at two sites, both through `state.emit` — which only
writes the log — and with no name in `TRIGGER_EVENTS` for a card to subscribe by.
Adding the mapping alone yields a trigger that silently never fires, which is the
same no-op the cycling trigger's "`fire`, not `emit`" comment was written for. All
three sites now `fire`.

The near misses are wrong rather than merely absent. `dealt_damage` is exactly
inverted — prevented damage is damage that was never dealt, so `DAMAGE_DEALT`
does not fire for it and a Squire built on it gets counters only on the turns its
own shield is *down*. `life_lost` fails the same way and is doubly wrong, since
prevented damage costs no life. And the `damage_taken_this_turn` value key reads
zero underneath a working shield by construction.

The authoring verifier declines combat, so the Squire's shield is never tested by
anything in the fixed sandbox and its expectation is the weak
`{"zone": "battlefield"}`. This file is where the behaviour is proved.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import (
    clear_damage_shields,
    damage_permanent,
    damage_player,
    shield_player,
    shielded,
)
from automtg.engine.zones import move_object
from tests.conftest import _default_answer, advance_to_step, only_oid

SQUIRE = "selfless_squire"  # 1/1 flash; shield on ETB, counters on prevention
BEAR = "t_bear"  # 2/2
LIFELINKER = "t_lifelinker"  # 2/2 lifelink
INFECTER = "t_infecter"  # 2/2 infect
ABSORBER = "t_absorber"  # 1/4, absorb 2 -- the *permanent*-side prevention


def position(builder, *, mine=(), theirs=(), players=2):
    """A frozen main phase with ``mine`` under player 0 and ``theirs`` under 1."""
    b = builder(players=players).step(Step.PRECOMBAT_MAIN)
    if mine:
        b = b.battlefield(0, list(mine))
    if theirs:
        b = b.battlefield(1, list(theirs))
    return b.build(advance=False)


def settle(game, limit: int = 60) -> None:
    """Resolve whatever a trigger put on the stack."""
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the trigger never resolved")


def counters(game, oid: int) -> int:
    return game.state.objects[oid].counter("+1/+1")


def events_of(game, kind: str, since: int = 0) -> list:
    return [e for e in game.state.events[since:] if e.type == kind]


class TestTheShieldPrevents:
    def test_damage_to_a_shielded_player_costs_no_life(self, builder):
        game = position(builder)
        shield_player(game.state, 0)
        before = game.state.players[0].life

        assert damage_player(game.state, 0, 5, None) == 0
        assert game.state.players[0].life == before

    def test_without_a_shield_the_damage_lands(self, builder):
        """The control. Everything below is a difference against this line."""
        game = position(builder)
        before = game.state.players[0].life

        assert damage_player(game.state, 0, 5, None) == 5
        assert game.state.players[0].life == before - 5

    def test_the_shield_is_visible_on_the_state(self, builder):
        game = position(builder)
        assert shielded(game.state, 0) is False
        shield_player(game.state, 0)
        assert shielded(game.state, 0) is True

    def test_a_second_identical_shield_is_not_recorded_twice(self, builder):
        """No pool to add to -- the shield is not consumed by use -- so a second
        copy says nothing the first does not and would only double the clean-up."""
        game = position(builder)
        assert shield_player(game.state, 0) is True
        assert shield_player(game.state, 0) is False
        assert len(game.state.damage_shields) == 1

    def test_a_shield_over_a_player_who_has_lost_is_refused(self, builder):
        game = position(builder)
        game.state.players[1].has_lost = True

        assert shield_player(game.state, 1) is False
        assert game.state.damage_shields == []


class TestItIsPerSeat:
    def test_an_unshielded_player_still_takes_damage(self, builder):
        """The shield is keyed to a seat, which is the whole thing the absorb
        static cannot do -- `static_filter_keys` has no way to name a player."""
        game = position(builder)
        shield_player(game.state, 0)
        before = game.state.players[1].life

        assert damage_player(game.state, 1, 3, None) == 3
        assert game.state.players[1].life == before - 3


class TestItIsNotConsumedByUse:
    def test_three_separate_hits_are_each_prevented(self, builder):
        """"Prevent **all** damage… this turn" is a fact about the turn, not a
        pool. Three attackers get through and all three are prevented."""
        game = position(builder)
        shield_player(game.state, 0)
        before = game.state.players[0].life

        for _ in range(3):
            damage_player(game.state, 0, 4, None)

        assert game.state.players[0].life == before

    def test_each_instance_fires_its_own_event(self, builder):
        """Which is what makes the Squire's "that many" add up to the whole swing
        rather than to one attacker's worth."""
        game = position(builder)
        shield_player(game.state, 0)
        before = len(game.state.events)

        damage_player(game.state, 0, 2, None)
        damage_player(game.state, 0, 3, None)

        prevented = events_of(game, "damage_prevented", before)
        assert [e.data["amount"] for e in prevented] == [2, 3]


class TestWhatPreventedDamageDoesNotDo:
    """Prevented damage was never dealt, so nothing downstream may see it.

    Each of these is a separate leak, and each would be a wrong *number* rather
    than an error -- which is why the check sits above every one of them.
    """

    def test_it_fires_no_life_lost(self, builder):
        game = position(builder)
        shield_player(game.state, 0)
        before = len(game.state.events)

        damage_player(game.state, 0, 5, None)

        assert events_of(game, "life_lost", before) == []

    def test_it_fires_no_damage_dealt(self, builder):
        game = position(builder)
        shield_player(game.state, 0)
        before = len(game.state.events)

        damage_player(game.state, 0, 5, None)

        assert events_of(game, "damage_dealt", before) == []

    def test_it_adds_no_poison(self, builder):
        """The sharpest one: a shielded player who still took the poison would
        lose to a fog. This is why the check is above the infect branch."""
        game = position(builder, theirs=[INFECTER])
        infecter = only_oid(game, INFECTER, 1)
        shield_player(game.state, 0)

        damage_player(game.state, 0, 5, infecter)

        assert game.state.players[0].poison == 0

    def test_it_gains_the_attacker_no_life(self, builder):
        game = position(builder, theirs=[LIFELINKER])
        linker = only_oid(game, LIFELINKER, 1)
        shield_player(game.state, 0)
        before = game.state.players[1].life

        damage_player(game.state, 0, 4, linker, is_combat=True)

        assert game.state.players[1].life == before

    def test_it_tallies_no_commander_damage(self, builder):
        game = position(builder, theirs=[BEAR])
        commander = only_oid(game, BEAR, 1)
        game.state.objects[commander].is_commander = True
        shield_player(game.state, 0)

        damage_player(game.state, 0, 7, commander, is_combat=True)

        assert game.state.players[0].commander_damage_taken.get(1, 0) == 0

    def test_it_is_not_counted_as_damage_taken_this_turn(self, builder):
        """`damage_taken_this_turn` is folded from `DAMAGE_DEALT`, so it reads
        zero underneath a working shield -- which is exactly why that value key
        could not have carried "that many" for the Squire."""
        game = position(builder)
        shield_player(game.state, 0)

        damage_player(game.state, 0, 5, None)

        assert game.state.turn_ledger.damage_taken.get(0, 0) == 0


class TestTheBoundary:
    def test_zero_damage_prevents_nothing_and_announces_nothing(self, builder):
        """`damage_player` returns on a non-positive amount before the shield is
        ever consulted, so a shield does not manufacture a prevention event out
        of a hit that was never going to land."""
        game = position(builder)
        shield_player(game.state, 0)
        before = len(game.state.events)

        assert damage_player(game.state, 0, 0, None) == 0
        assert events_of(game, "damage_prevented", before) == []

    def test_negative_damage_likewise(self, builder):
        game = position(builder)
        shield_player(game.state, 0)
        before = len(game.state.events)

        assert damage_player(game.state, 0, -3, None) == 0
        assert events_of(game, "damage_prevented", before) == []


class TestItWearsOff:
    def test_the_cleanup_step_drops_it(self, builder):
        game = position(builder)
        shield_player(game.state, 0)

        clear_damage_shields(game.state, "this_turn")

        assert shielded(game.state, 0) is False
        assert game.state.damage_shields == []

    def test_damage_lands_again_after_the_turn_ends(self, builder):
        """Played through the real turn structure, because this is the whole
        difference from the `prevent_damage` static: a static would still be
        preventing next turn, and every turn after that."""
        game = builder(players=2).step(Step.PRECOMBAT_MAIN).max_turns(4).build()
        shield_player(game.state, 0)
        assert shielded(game.state, 0) is True

        advance_to_step(game, Step.CLEANUP)
        settle(game)

        assert shielded(game.state, 0) is False
        before = game.state.players[0].life
        assert damage_player(game.state, 0, 3, None) == 3
        assert game.state.players[0].life == before - 3


class TestTheSourceIsNotTheLifetime:
    def test_the_shield_outlives_the_permanent_that_installed_it(self, builder):
        """A resolved one-shot does not care what happens to the card that made
        it. The Squire is flashed in as a blocker and dies to the very combat its
        shield was for; Fog leaves no permanent behind at all."""
        game = position(builder, mine=[SQUIRE])
        squire = only_oid(game, SQUIRE, 0)
        shield_player(game.state, 0, source=squire)

        move_object(game.state, squire, Zone.GRAVEYARD)

        assert shielded(game.state, 0) is True
        assert damage_player(game.state, 0, 4, None) == 0


class TestTheTriggerFires:
    """The second half, through the real card and the real trigger bus.

    Every one of these fails if the emission is `state.emit` rather than `fire`:
    the event lands in the log, the assertion reads the log and passes, and the
    counters are never placed.
    """

    def test_the_squire_gets_counters_for_the_prevented_damage(self, builder):
        game = position(builder, mine=[SQUIRE])
        squire = only_oid(game, SQUIRE, 0)
        shield_player(game.state, 0, source=squire)

        damage_player(game.state, 0, 4, None)
        settle(game)

        assert counters(game, squire) == 4, "that many -- four, not one"

    def test_two_preventions_add_up(self, builder):
        game = position(builder, mine=[SQUIRE])
        squire = only_oid(game, SQUIRE, 0)
        shield_player(game.state, 0, source=squire)

        damage_player(game.state, 0, 2, None)
        settle(game)
        damage_player(game.state, 0, 3, None)
        settle(game)

        assert counters(game, squire) == 5

    def test_no_damage_means_no_counters(self, builder):
        game = position(builder, mine=[SQUIRE])
        squire = only_oid(game, SQUIRE, 0)
        shield_player(game.state, 0, source=squire)

        damage_player(game.state, 0, 0, None)
        settle(game)

        assert counters(game, squire) == 0

    def test_damage_that_was_not_prevented_gives_nothing(self, builder):
        """The inversion that makes `dealt_damage` the wrong trigger: with no
        shield up the damage lands and the Squire grows by nothing."""
        game = position(builder, mine=[SQUIRE])
        squire = only_oid(game, SQUIRE, 0)

        damage_player(game.state, 0, 4, None)
        settle(game)

        assert counters(game, squire) == 0

    def test_an_opponents_prevented_damage_gives_nothing(self, builder):
        """"…dealt to **you**." `controller: "you"` is compared against the
        player whose damage was prevented, which is why `_actor` returns
        `event.player` for this trigger."""
        game = position(builder, mine=[SQUIRE])
        squire = only_oid(game, SQUIRE, 0)
        shield_player(game.state, 1)

        damage_player(game.state, 1, 4, None)
        settle(game)

        assert counters(game, squire) == 0

    def test_absorb_on_a_permanent_gives_nothing(self, builder):
        """One event, two shapes -- and the mirror of the `dealt_damage` guard.

        Absorb and protection fire `DAMAGE_PREVENTED` too, and now that all three
        sites go through the bus an unguarded subscription would pay the Squire
        every time one of its controller's creatures shrugged off a blocker.
        """
        game = position(builder, mine=[SQUIRE, ABSORBER])
        squire = only_oid(game, SQUIRE, 0)
        absorber = only_oid(game, ABSORBER, 0)

        damage_permanent(game.state, absorber, 2, None)
        settle(game)

        assert counters(game, squire) == 0

    def test_that_absorb_really_did_prevent_something(self, builder):
        """Guarding the test above: it would pass just as well if absorb had
        quietly stopped preventing anything at all."""
        game = position(builder, mine=[ABSORBER])
        absorber = only_oid(game, ABSORBER, 0)
        before = len(game.state.events)

        damage_permanent(game.state, absorber, 2, None)

        prevented = events_of(game, "damage_prevented", before)
        assert [e.data["to"] for e in prevented] == ["permanent"]


class TestTheEventReachesTheBus:
    def test_the_prevention_queues_a_trigger(self, builder):
        """`fire`, not `emit`. `state.emit` records the event and leaves the
        trigger bus to the caller, so the mapping in `TRIGGER_EVENTS` alone would
        have produced a trigger that silently never fires."""
        game = position(builder, mine=[SQUIRE])
        shield_player(game.state, 0)

        damage_player(game.state, 0, 3, None)

        assert game.state.pending_triggers, "the event never reached the trigger bus"

    def test_the_player_half_says_which_shape_it_is(self, builder):
        game = position(builder)
        shield_player(game.state, 0)
        before = len(game.state.events)

        damage_player(game.state, 0, 3, None)

        (event,) = events_of(game, "damage_prevented", before)
        assert event.data["to"] == "player"
        assert event.data["oid"] is None
        assert event.player == 0
        assert event.data["amount"] == 3


class TestTheShippedCard:
    def test_the_squire_declares_both_halves(self, registry):
        card = registry.get(SQUIRE)
        triggers = [a.trigger.event for a in card.abilities if a.is_triggered]
        assert triggers == ["self_enters", "damage_prevented"]

    def test_entering_the_battlefield_puts_the_shield_up(self, builder):
        """The two halves composing, from the printed side: the ETB installs the
        shield and the shield's own prevention pays the counters."""
        game = position(builder, mine=[SQUIRE])
        squire = only_oid(game, SQUIRE, 0)
        # The builder places permanents rather than entering them, so the ETB is
        # driven here -- the ability is the card's, not the test's.
        from automtg.engine.events import EventType
        from automtg.engine.triggers import fire

        fire(game.state, EventType.ENTERS_BATTLEFIELD, player=0, oid=squire)
        settle(game)

        assert shielded(game.state, 0) is True
        assert damage_player(game.state, 0, 3, None) == 0
        settle(game)
        assert counters(game, squire) == 3


class TestTheLoaderGuards:
    def _card(self, effect) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_shield_probe",
                "name": "Shield Probe",
                "oracle_text": "x",
                "mana_cost": "{W}",
                "types": ["Instant"],
                "spell_effects": [effect],
            }
        )

    def test_a_well_formed_shield_loads(self):
        compile_card(
            self._card({"op": "prevent_damage", "player": "you", "duration": "this_turn"})
        )

    def test_an_amount_is_refused(self):
        """The guard that matters. A Healing Salve written as this op would load
        clean and prevent *everything* -- a strictly better card, silently."""
        with pytest.raises(DslError, match="takes no 'amount'"):
            compile_card(
                self._card(
                    {
                        "op": "prevent_damage",
                        "player": "you",
                        "amount": {"const": 3},
                        "duration": "this_turn",
                    }
                )
            )

    def test_objects_are_refused(self):
        """Accepted and ignored it would be a card that shields nothing it says
        it shields; prevention over permanents is the static, or protection."""
        with pytest.raises(DslError, match="takes no 'objects'"):
            compile_card(
                self._card(
                    {
                        "op": "prevent_damage",
                        "objects": {"controller": "you", "types": ["Creature"]},
                        "duration": "this_turn",
                    }
                )
            )

    def test_a_missing_duration_is_refused(self):
        """A prevention read as lasting longer than it does is a fog that never
        ends, and there is no safe guess for an omitted one."""
        with pytest.raises(DslError, match="prevent_damage needs a 'duration'"):
            compile_card(self._card({"op": "prevent_damage", "player": "you"}))

    def test_an_unknown_duration_is_refused(self):
        with pytest.raises(DslError, match="unknown prevent_damage duration"):
            compile_card(
                self._card(
                    {"op": "prevent_damage", "player": "you", "duration": "forever"}
                )
            )

    def test_the_absorb_static_still_needs_its_amount(self):
        """The two `prevent_damage` names coexist and pull in opposite
        directions: the op refuses an `amount` and the static requires one."""
        with pytest.raises(DslError, match="prevent_damage' needs an 'amount'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_absorb_probe_2",
                        "name": "Absorb Probe",
                        "oracle_text": "x",
                        "mana_cost": "{2}",
                        "types": ["Creature"],
                        "power": 1,
                        "toughness": 1,
                        "abilities": [
                            {
                                "kind": "static",
                                "effect": "prevent_damage",
                                "affects": {"self_only": True},
                            }
                        ],
                    }
                )
            )

    def test_the_trigger_event_name_is_accepted(self):
        compile_card(
            CardModel.model_validate(
                {
                    "id": "t_prevention_watcher",
                    "name": "Prevention Watcher",
                    "oracle_text": "x",
                    "mana_cost": "{W}",
                    "types": ["Creature"],
                    "power": 1,
                    "toughness": 1,
                    "abilities": [
                        {
                            "kind": "triggered",
                            "text": "x",
                            "trigger": {"event": "damage_prevented", "controller": "you"},
                            "effects": [{"op": "noop"}],
                        }
                    ],
                }
            )
        )
