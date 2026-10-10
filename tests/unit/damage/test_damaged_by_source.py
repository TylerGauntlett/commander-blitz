""""Whenever a creature dealt damage by this creature this turn dies…"

Sengir Vampire is the shipped witness, and the clause is a *relationship*
between two objects over a span of time rather than a characteristic of either.
Nothing in the engine recorded one: `damage` applied damage and remembered
nothing about who dealt it.

The awkward part is when the question is asked. It is asked **about a creature
that has already died** — so anything stored on the victim is wrong by
construction, because `reset_permanent_state` wipes it on the way to the
graveyard, which is the exact moment the trigger needs it. Hence a ledger on the
state: victim oid -> the oids of everything that has damaged it this turn.

Cleared during cleanup, next to rule 514.2's "remove all damage from
permanents". A ledger that outlived the turn would let a Sengir Vampire grow off
a creature it hurt yesterday, which is a strictly better card.

Read back through a trigger filter, `{"damaged_by": "self"}`, because
`creature_dies` on its own fires on **every** creature death anywhere — a
strictly stronger card than the one printed, and one that would look right in
almost every game where Sengir is doing the killing.

Two things this file learned the hard way and pins so the next card does not:

- `TriggerModel.controller` defaults to `"you"`, so an unqualified
  `creature_dies` only sees your own creatures dying. Sengir's victims are
  usually an opponent's, so it needs `controller: "any"` — and without it the
  card loads, looks implemented, and never triggers.
- The blocker has to be able to block. Sengir flies; a ground bear never
  blocks it, no creature dies, and a test built that way passes for the wrong
  reason.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.primitives import damage_permanent
from commanderblitz.engine.triggers import matches_card_filter
from tests.conftest import plus_one_counters

SENGIR = "sengir_vampire"  # 4/4 flier
FLIER = "t_flier"  # 2/2 flier -- can block Sengir, and dies to it
BEAR = "t_bear"  # 2/2 ground -- cannot block a flier


def board(builder, defenders=(FLIER,)):
    return (
        builder(players=2)
        .battlefield(0, [SENGIR])
        .battlefield(1, list(defenders))
        .active(0)
        .step(Step.UNTAP)
        .build(advance=False)
    )


def only(game, def_id: str) -> int:
    return next(
        o for o, obj in game.state.objects.items() if obj.def_id == def_id
    )


def fight(game, *, block: bool = True) -> None:
    """Attack with everything, block with everything, run to the end step."""
    game._advance()
    for _ in range(80):
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        if decision.kind in (
            DecisionKind.DECLARE_ATTACKERS,
            DecisionKind.DECLARE_BLOCKERS,
        ):
            wanted = (
                ActionKind.ADD_ATTACKER
                if decision.kind is DecisionKind.DECLARE_ATTACKERS
                else ActionKind.ADD_BLOCKER
            )
            step = next((a for a in actions if a.kind is wanted), None)
            if step is not None and (
                block or decision.kind is DecisionKind.DECLARE_ATTACKERS
            ):
                game.apply(step)
                continue
            done = next(
                (a for a in actions if a.kind is ActionKind.FINISH_DECLARATION), None
            )
            if done is not None:
                game.apply(done)
                continue
        passing = next((a for a in actions if a.kind is ActionKind.PASS), None)
        if passing is None:
            return
        game.apply(passing)
        if game.state.step is Step.END_STEP:
            return


class TestTheLedger:
    def test_damage_records_who_dealt_it(self, builder):
        game = board(builder)
        sengir, flier = only(game, SENGIR), only(game, FLIER)
        damage_permanent(game.state, flier, 1, sengir)
        assert game.state.damage_ledger[flier] == {sengir}

    def test_several_sources_all_land(self, builder):
        game = board(builder, defenders=(FLIER, BEAR))
        sengir, flier, bear = only(game, SENGIR), only(game, FLIER), only(game, BEAR)
        damage_permanent(game.state, flier, 1, sengir)
        damage_permanent(game.state, flier, 1, bear)
        assert game.state.damage_ledger[flier] == {sengir, bear}

    def test_it_is_empty_to_begin_with(self, builder):
        assert board(builder).state.damage_ledger == {}

    def test_cleanup_clears_it(self, builder):
        """"…this turn". Rule 514.2 removes the damage; this goes with it."""
        game = board(builder)
        sengir, flier = only(game, SENGIR), only(game, FLIER)
        damage_permanent(game.state, flier, 1, sengir)
        assert game.state.damage_ledger

        fight(game, block=False)
        assert game.state.damage_ledger == {}, (
            "a ledger that outlived the turn would let Sengir grow off a "
            "creature it hurt yesterday"
        )


class TestTheTrigger:
    def test_killing_a_blocker_grows_it(self, builder):
        game = board(builder)
        sengir = only(game, SENGIR)
        fight(game)

        assert not any(
            game.state.objects[o].def_id == FLIER for o in game.state.battlefield
        ), "the 2/2 blocked a 4/4 and died"
        assert plus_one_counters(game, sengir) == 1

    def test_a_combat_that_kills_nothing_does_not(self, builder):
        game = board(builder)
        sengir = only(game, SENGIR)
        fight(game, block=False)
        assert plus_one_counters(game, sengir) == 0, "nothing died, so nothing triggered"


class TestItIsOnlyItsOwnVictims:
    """The predicate itself, where the negative cases are exact.

    `creature_dies` alone fires on every creature death anywhere, so this
    filter is the entire difference between Sengir Vampire and a strictly
    better card.
    """

    def test_it_matches_a_creature_this_source_damaged(self, builder):
        game = board(builder)
        sengir, flier = only(game, SENGIR), only(game, FLIER)
        damage_permanent(game.state, flier, 1, sengir)
        assert matches_card_filter(
            game.state, flier, {"damaged_by": "self"}, game.state.objects[sengir]
        )

    def test_it_does_not_match_one_somebody_else_damaged(self, builder):
        game = board(builder, defenders=(FLIER, BEAR))
        sengir, flier, bear = only(game, SENGIR), only(game, FLIER), only(game, BEAR)
        damage_permanent(game.state, flier, 1, bear)
        assert not matches_card_filter(
            game.state, flier, {"damaged_by": "self"}, game.state.objects[sengir]
        )

    def test_it_does_not_match_an_undamaged_creature(self, builder):
        game = board(builder)
        sengir, flier = only(game, SENGIR), only(game, FLIER)
        assert not matches_card_filter(
            game.state, flier, {"damaged_by": "self"}, game.state.objects[sengir]
        )

    def test_it_survives_the_victim_dying(self, builder):
        """The whole reason the ledger is on the state and not on the object."""
        from commanderblitz.engine.zones import destroy

        game = board(builder)
        sengir, flier = only(game, SENGIR), only(game, FLIER)
        damage_permanent(game.state, flier, 1, sengir)
        destroy(game.state, flier)

        assert matches_card_filter(
            game.state, flier, {"damaged_by": "self"}, game.state.objects[sengir]
        ), "asked about a creature already in the graveyard, which is the point"
