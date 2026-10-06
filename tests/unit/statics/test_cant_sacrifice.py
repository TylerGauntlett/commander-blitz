""""You can't sacrifice those creatures this turn" -- the engine's first
sacrifice prohibition, and the last blocker on **Call for Aid**.

Rule 701.17b: a player can't sacrifice a permanent an effect says they can't.
A sacrifice is not damage and not destruction, so nothing already in the engine
could refuse one:

- `lock_abilities` is the near miss the gap record names. It stops a permanent's
  *own* activated abilities being activated, so it says nothing about an Altar
  standing three permanents away whose activation cost eats this one, and
  nothing at all about the `sacrifice` op or an edict.
- `replace_deaths` redirects a permanent's death *after* the sacrifice. The
  creature still leaves the battlefield and the outlet still got paid, which is
  not what "can't" means -- and it would leave Call for Aid's borrowed creatures
  gone from the board when control was due to revert.
- `indestructible` explicitly does not stop a sacrifice (701.17a), and no
  prevention or protection is aimed at one either.

Without this, Call for Aid gains control of an opponent's whole board and the
caster is free to feed it to a sacrifice outlet before control reverts -- a
strictly better card than the printed one, which is why the gap record refused
to write a partial answer.

A sacrifice is demanded on **two roads** and the printed rule does not
distinguish between them, so both are pinned below:

1. As a **cost** -- an outlet's activation cost, an additional cost to cast,
   emerge's fodder. The cost becomes *unpayable*: `costs._sacrifice_pool` and
   `legality._emerge_fodder` drop the protected permanents, so `can_pay` refuses
   and `legality` never offers the action at all. A cost that could be paid and
   then quietly not sacrifice would be a free outlet.
2. As an **effect** -- the `sacrifice` op, "each opponent sacrifices a
   creature". The pool narrows, so an edict takes something *else* if there is
   anything else and does nothing only when there is not. Filtering after the
   choice instead would let a protected creature answer the edict and fizzle it,
   which is a better answer than the rule allows.

The rest is the shape the three restrictions before it already have -- a frozen
record on `GameState`, a required `duration`, one predicate, and a clearing hook
in `turn._cleanup_step`. What is deliberately *not* shared: there is no
`until_your_next_turn` (no printed one-shot says it), hence no `player` field,
hence no `sba._eliminate` prune -- an entry with only a turn-long clock is
cleared by the cleanup step whoever has left the game. See
`structs.SACRIFICE_RESTRICTION_DURATIONS`.

And the guard is deliberately *not* in `zones.sacrifice`, tempting though the
single funnel is: that function is also how 704.5s sacrifices a finished Saga
with no player choosing, and `sba._finished_sagas` sets its "something changed"
flag on the call -- so a `sacrifice` that quietly returned False would spin the
state-based-action loop for ever. `TestTheGameStillSacrificesForItself` pins it.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import combat as combat_mod
from automtg.engine import sagas, sba
from automtg.engine.carddef import Cost
from automtg.engine.costs import can_pay
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.legality import _emerge_fodder
from automtg.engine.primitives import (
    clear_sacrifice_restrictions,
    forbid_sacrifice,
    sacrifice_forbidden,
)
from automtg.engine.zones import destroy
from tests.conftest import _default_answer, oids_of, only_oid, pass_until

BEAR = "t_bear"
WALL = "t_wall"
GOBLIN = "t_offering"  # {4}{R} Goblin, emerge {4}{R} by sacrificing a Goblin
OUTLET = "t_sac_outlet"  # Sacrifice a creature: you gain 1 life.
EDICT = "t_edict"  # {B} sorcery: each opponent sacrifices a creature
ADDITIONAL = "t_mandatory_sac"  # additional cost: sacrifice a creature; draw two
BODYGUARD = "t_bodyguard"  # {W} sorcery: you can't sacrifice target creature this turn


def position(builder, *, mine=(BEAR,), theirs=(), hand=(), lands=("swamp",) * 4):
    """Player 0 has ``mine`` and an outlet; ``lands`` pays for whatever is cast."""
    b = builder(players=2)
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    if hand:
        b.hand(0, list(hand))
    if lands:
        b.battlefield(0, list(lands))
    return b.active(0).step(Step.PRECOMBAT_MAIN).build()


def activations(game, def_id: str = OUTLET) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and a.source is not None
        and game.state.objects[a.source].def_id == def_id
    ]


def casts(game, def_id: str) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == def_id
    ]


def settle(game, limit: int = 60) -> None:
    """Let the stack empty, answering every decision the most passive way."""
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def cast(game, def_id: str) -> None:
    game.apply(casts(game, def_id)[0])
    settle(game)


def on_battlefield(game, pid: int) -> list[str]:
    return sorted(obj.def_id for obj in game.state.battlefield_objects(pid))


class TestTheCostRoadBecomesUnpayable:
    """701.17b makes the *cost* unpayable, so the action is never offered. Any
    reading where the outlet activates and then eats nothing is a free outlet."""

    def test_the_unrestricted_baseline(self, builder):
        game = position(builder, mine=(BEAR, OUTLET))
        assert len(activations(game)) == 1, "the outlet is normally activatable"

    def test_the_only_fodder_being_protected_removes_the_activation(self, builder):
        game = position(builder, mine=(BEAR, OUTLET))
        bear = only_oid(game, BEAR, 0)
        forbid_sacrifice(game.state, [bear], "this_turn")
        assert activations(game) == [], (
            "an outlet with nothing legal to eat is an unpayable cost, "
            "not a payable one that sacrifices nobody"
        )

    def test_another_creature_keeps_the_outlet_live(self, builder):
        game = position(builder, mine=(BEAR, WALL, OUTLET))
        bear = only_oid(game, BEAR, 0)
        forbid_sacrifice(game.state, [bear], "this_turn")
        assert len(activations(game)) == 1

    def test_paying_takes_the_unprotected_one(self, builder):
        """`can_pay` and `pay` build the pool through the same helper, so they
        cannot disagree about which creature is legal fodder."""
        game = position(builder, mine=(BEAR, WALL, OUTLET))
        bear = only_oid(game, BEAR, 0)
        forbid_sacrifice(game.state, [bear], "this_turn")
        game.apply(activations(game)[0])
        settle(game)
        assert on_battlefield(game, 0).count(BEAR) == 1, "the protected Bear survived"
        assert on_battlefield(game, 0).count(WALL) == 0, "the Wall was eaten instead"

    def test_a_two_creature_cost_needs_two_legal_creatures(self, builder):
        """The pool is compared against the cost's ``count``, so protecting one
        of two candidates makes a "sacrifice two creatures" cost unpayable even
        though one creature is still perfectly legal fodder."""
        game = position(builder, mine=(BEAR, WALL))
        cost = Cost(
            sacrifice={
                "zone": "battlefield",
                "controller": "you",
                "types": ["Creature"],
                "count": 2,
            }
        )
        assert can_pay(game.state, 0, cost, None)
        forbid_sacrifice(game.state, [only_oid(game, BEAR, 0)], "this_turn")
        assert not can_pay(game.state, 0, cost, None)


class TestTheAdditionalCostToCast:
    """"As an additional cost to cast this spell, sacrifice a creature."
    `carddef.additional_cost` is a `Cost` and goes through `can_pay`, so the one
    filter in `_sacrifice_pool` closes this road too."""

    def test_the_unrestricted_baseline(self, builder):
        game = position(builder, mine=(BEAR,), hand=(ADDITIONAL,))
        assert len(casts(game, ADDITIONAL)) == 1

    def test_protecting_the_only_creature_makes_the_spell_uncastable(self, builder):
        game = position(builder, mine=(BEAR,), hand=(ADDITIONAL,))
        forbid_sacrifice(game.state, [only_oid(game, BEAR, 0)], "this_turn")
        assert casts(game, ADDITIONAL) == [], (
            "the additional cost cannot be paid, so the spell cannot be cast"
        )

    def test_a_second_creature_keeps_it_castable(self, builder):
        game = position(builder, mine=(BEAR, WALL), hand=(ADDITIONAL,))
        forbid_sacrifice(game.state, [only_oid(game, BEAR, 0)], "this_turn")
        assert len(casts(game, ADDITIONAL)) == 1


class TestEmergeFodder:
    """Emerge and offering are the one sacrifice cost that is not a `Cost`: the
    creature is chosen as part of the cast action, because how much the spell
    costs depends on which one it is. `_sacrifice_pool` cannot see it, so
    `legality._emerge_fodder` asks the same question again."""

    def test_the_unrestricted_baseline(self, builder):
        game = position(builder, mine=(GOBLIN,), hand=(GOBLIN,), lands=("mountain",) * 8)
        goblin = only_oid(game, GOBLIN, 0)
        caster = game.state.players[0].hand[0]
        assert _emerge_fodder(game.state, 0, caster) == [goblin]

    def test_a_protected_goblin_is_not_fodder(self, builder):
        game = position(builder, mine=(GOBLIN,), hand=(GOBLIN,), lands=("mountain",) * 8)
        goblin = only_oid(game, GOBLIN, 0)
        caster = game.state.players[0].hand[0]
        forbid_sacrifice(game.state, [goblin], "this_turn")
        assert _emerge_fodder(game.state, 0, caster) == []
        assert not any(a.emerge_oid is not None for a in game.legal_actions()), (
            "with no legal fodder there is no emerge line at all"
        )


class TestTheEffectRoadPicksSomethingElse:
    """The `sacrifice` op narrows its *pool*, so an edict must take a legal
    creature when there is one. Skipping the protected creature after the choice
    would let it answer the edict and fizzle, which is a better answer than
    701.17b allows."""

    def test_the_unrestricted_baseline(self, builder):
        game = position(builder, mine=(), theirs=(BEAR,), hand=(EDICT,))
        cast(game, EDICT)
        assert on_battlefield(game, 1) == []

    def test_the_edict_takes_the_other_creature(self, builder):
        game = position(builder, mine=(), theirs=(BEAR, WALL), hand=(EDICT,))
        bear = only_oid(game, BEAR, 1)
        forbid_sacrifice(game.state, [bear], "this_turn")
        cast(game, EDICT)
        assert on_battlefield(game, 1) == [BEAR], "the Wall was the only legal choice"

    def test_with_nothing_else_the_edict_does_nothing(self, builder):
        game = position(builder, mine=(), theirs=(BEAR,), hand=(EDICT,))
        bear = only_oid(game, BEAR, 1)
        forbid_sacrifice(game.state, [bear], "this_turn")
        cast(game, EDICT)
        assert on_battlefield(game, 1) == [BEAR]

    def test_the_protected_creature_is_never_offered_as_a_choice(self, builder):
        """The pool is narrowed before the question is asked, so the player is
        never shown a choice they are not allowed to make."""
        game = position(builder, mine=(), theirs=(BEAR, BEAR, WALL), hand=(EDICT,))
        bears = oids_of(game, BEAR, 1)
        forbid_sacrifice(game.state, bears, "this_turn")
        game.apply(casts(game, EDICT)[0])
        for _ in range(40):
            decision = game.pending()
            if decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS:
                offered = {o.value for o in decision.options}
                assert offered.isdisjoint(bears), "protected creatures were offered"
                return
            if decision is None:
                game._advance()
                continue
            game.apply(_default_answer(game, decision))
        # A single legal candidate is taken without asking, which is also correct.


class TestItIsNotIndestructibleAndNotAReplacement:
    """The three near misses, each pinned as a thing this does *not* do. A
    prohibition that also stopped destruction would be a strictly better card."""

    def test_a_protected_creature_can_still_be_destroyed(self, builder):
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        forbid_sacrifice(game.state, [bear], "this_turn")
        assert destroy(game.state, bear)
        assert on_battlefield(game, 0).count(BEAR) == 0

    def test_it_says_nothing_about_a_creature_it_does_not_name(self, builder):
        game = position(builder, mine=(BEAR, WALL))
        forbid_sacrifice(game.state, [only_oid(game, BEAR, 0)], "this_turn")
        assert sacrifice_forbidden(game.state, only_oid(game, BEAR, 0))
        assert not sacrifice_forbidden(game.state, only_oid(game, WALL, 0))

    def test_an_empty_table_costs_nothing_and_forbids_nothing(self, builder):
        game = position(builder, mine=(BEAR,))
        assert game.state.sacrifice_restrictions == []
        assert not sacrifice_forbidden(game.state, only_oid(game, BEAR, 0))


class TestTheGameStillSacrificesForItself:
    """Why the guard is at the two choice points and not in `zones.sacrifice`.

    704.5s sacrifices a finished Saga with no player choosing, and
    `sba._finished_sagas` sets `changed = True` on the call -- so a `sacrifice`
    that returned False under a restriction would make `sba.check` report a
    change for ever and the loop would never settle."""

    def test_a_finished_saga_under_a_restriction_still_leaves(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["t_saga"], counters={sagas.LORE: 3})
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        saga = only_oid(game, "t_saga", 0)
        forbid_sacrifice(game.state, [saga], "this_turn")
        sba.run(game.state)
        assert game.state.objects[saga].zone is Zone.GRAVEYARD
        assert not sba.check(game.state), (
            "a `sacrifice` that returned False here would report a change for "
            "ever and the state-based-action loop would never settle"
        )


class TestTheClock:
    def test_this_turn_ends_at_cleanup(self, builder):
        game = position(builder, mine=(BEAR, OUTLET))
        forbid_sacrifice(game.state, [only_oid(game, BEAR, 0)], "this_turn")
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.sacrifice_restrictions == []

    def test_it_survives_the_combat_it_was_cast_before(self, builder):
        """Call for Aid is cast in a precombat main phase and the sentence means
        the *whole* turn -- the outlet the borrowed creatures have to survive is
        the one an opponent reaches for in the second main phase."""
        game = position(builder, mine=(BEAR, OUTLET))
        forbid_sacrifice(game.state, [only_oid(game, BEAR, 0)], "this_turn")
        combat_mod.end_combat(game.state)
        assert [r.duration for r in game.state.sacrifice_restrictions] == ["this_turn"]
        assert activations(game) == [], "still unpayable after the combat ended"

    def test_clearing_another_duration_leaves_it_alone(self, builder):
        game = position(builder, mine=(BEAR,))
        forbid_sacrifice(game.state, [only_oid(game, BEAR, 0)], "this_turn")
        clear_sacrifice_restrictions(game.state, "until_your_next_turn")
        assert len(game.state.sacrifice_restrictions) == 1
        clear_sacrifice_restrictions(game.state, "this_turn")
        assert game.state.sacrifice_restrictions == []


class TestItOutlivesItsSource:
    def test_destroying_the_source_does_not_lift_it(self, builder):
        """The first of the three things a static could not do. Call for Aid is
        a sorcery and is in a graveyard before the outlet is ever activated."""
        game = position(builder, mine=(BEAR, OUTLET))
        bear = only_oid(game, BEAR, 0)
        land = oids_of(game, "swamp", 0)[0]
        forbid_sacrifice(game.state, [bear], "this_turn", source=land)
        destroy(game.state, land)
        assert sacrifice_forbidden(game.state, bear)
        assert activations(game) == []


class TestAnEliminatedPlayerNeedsNoPrune:
    """Unlike `block_prohibitions` and `unblockables` there is no
    ``until_your_next_turn`` here, so there is no clock keyed to a seat that can
    stop coming -- which is why `sba._eliminate` has nothing to do."""

    def test_a_turn_scoped_entry_is_left_alone_and_wears_off_normally(self, builder):
        game = position(builder, mine=(BEAR,), theirs=(BEAR,))
        forbid_sacrifice(game.state, [only_oid(game, BEAR, 0)], "this_turn")
        game.state.players[1].life = 0
        sba.run(game.state)
        assert len(game.state.sacrifice_restrictions) == 1
        clear_sacrifice_restrictions(game.state, "this_turn")
        assert game.state.sacrifice_restrictions == []


class TestThePrimitiveRefusesWhatCannotBite:
    def test_an_empty_set_protects_nobody(self, builder):
        game = position(builder)
        assert not forbid_sacrifice(game.state, [], "this_turn")
        assert game.state.sacrifice_restrictions == []

    def test_the_same_entry_is_recorded_once(self, builder):
        game = position(builder)
        assert forbid_sacrifice(game.state, [7], "this_turn")
        assert not forbid_sacrifice(game.state, [7], "this_turn")
        assert len(game.state.sacrifice_restrictions) == 1

    def test_duplicate_oids_within_one_call_collapse(self, builder):
        game = position(builder)
        forbid_sacrifice(game.state, [7, 7, 8], "this_turn")
        assert game.state.sacrifice_restrictions[0].objects == (7, 8)

    def test_two_effects_protecting_the_same_creature_are_two_entries(self, builder):
        """Different sources are different effects, and one being lifted must
        not lift the other."""
        game = position(builder)
        assert forbid_sacrifice(game.state, [7], "this_turn", source=1)
        assert forbid_sacrifice(game.state, [7], "this_turn", source=2)
        assert len(game.state.sacrifice_restrictions) == 2

    def test_an_unknown_duration_is_a_value_error(self, builder):
        game = position(builder)
        with pytest.raises(ValueError, match="unknown sacrifice restriction duration"):
            forbid_sacrifice(game.state, [7], "until_your_next_turn")


def probe(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{W}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )
    )


class TestTheLoaderGuardsIt:
    def test_a_missing_objects_is_refused(self):
        """Neither reading of an absent `objects` is safe: "everything" is a
        one-sided Sigarda for the turn and "nothing" is a card that silently
        protects nobody."""
        with pytest.raises(DslError, match="cant_sacrifice needs 'objects'"):
            probe({"op": "cant_sacrifice", "duration": "this_turn"})

    def test_a_missing_duration_is_refused(self):
        with pytest.raises(DslError, match="cant_sacrifice needs a 'duration'"):
            probe({"op": "cant_sacrifice", "objects": {"types": ["Creature"]}})

    def test_an_unknown_duration_is_refused(self):
        with pytest.raises(DslError, match="unknown cant_sacrifice duration"):
            probe(
                {
                    "op": "cant_sacrifice",
                    "objects": {"types": ["Creature"]},
                    "duration": "until_your_next_turn",
                }
            )


class TestTheSpellForm:
    """A resolving spell installing the restriction, which is the only shape any
    printed card has -- and the shape the authoring verifier cannot observe,
    because it never activates an activated ability."""

    def test_casting_it_records_the_target(self, builder):
        game = position(builder, mine=(BEAR, OUTLET), hand=(BODYGUARD,), lands=("plains",) * 4)
        bear = only_oid(game, BEAR, 0)
        cast(game, BODYGUARD)
        entry = game.state.sacrifice_restrictions[0]
        assert (entry.objects, entry.duration) == ((bear,), "this_turn")

    def test_the_outlet_goes_away_when_it_resolves(self, builder):
        game = position(builder, mine=(BEAR, OUTLET), hand=(BODYGUARD,), lands=("plains",) * 4)
        assert len(activations(game)) == 1
        cast(game, BODYGUARD)
        assert activations(game) == []

    def test_the_source_is_recorded_and_is_not_the_target(self, builder):
        game = position(builder, mine=(BEAR, OUTLET), hand=(BODYGUARD,), lands=("plains",) * 4)
        bear = only_oid(game, BEAR, 0)
        spell = game.state.players[0].hand[0]
        cast(game, BODYGUARD)
        entry = game.state.sacrifice_restrictions[0]
        assert entry.source == spell
        assert entry.objects == (bear,), "the spell's target, not the spell"


class TestTheShippedCard:
    def test_call_for_aid_is_playable_and_says_every_line(self, real_registry):
        """The card this capability was built for. Its other four clauses were
        already expressible -- `cant_sacrifice` was the last blocker."""
        card = real_registry.get("call_for_aid")
        assert card is not None
        assert [e["op"] for e in card.spell_effects] == [
            "gain_control",
            "untap",
            "grant_keyword",
            "cant_attack_player",
            "cant_sacrifice",
        ]
        restriction = card.spell_effects[-1]
        assert restriction["duration"] == "this_turn"
