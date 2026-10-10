"""`sacrifice`'s `snapshot`: last-known information about a permanent *somebody
else* chose, taken while it is still on the battlefield.

**Entrapment Maneuver** is the witness. "Target player sacrifices an attacking
creature of their choice. You create X 1/1 white Soldier creature tokens, where
X is **that creature's toughness**." Rule 608.2h and the last-known-information
rule (603.10e / 613.6) both say the same thing about "that creature": the value
is read from the game state *immediately before* the creature left, not from the
card lying in the graveyard afterwards.

The engine's LKI is deliberately explicit rather than global -- a card that needs
a value after its subject has gone declares a `snapshot` (see
`docs/rules-coverage.md`). Every existing road to that declaration reaches the
subject through a **selector or a target**, resolved by the op that runs it:

- a `target`, which Swords to Plowshares and Beast Within take;
- an `objects` selector evaluated when the `snapshot` op runs.

Entrapment Maneuver's creature is neither. It is picked *by the target player*,
inside `op_sacrifice`, and no selector written afterwards names it. `sacrifice`'s
`as` records which oid was picked, but `as` is only readable by the next op --
and by then the oid is a graveyard card, where `chars()` gives the printed line.

That is not a rounding error, it is the whole card. A 5/5 wearing three +1/+1
counters has battlefield toughness 8 and printed toughness 5, and the naive
`as`-then-`snapshot` spelling makes **five** Soldiers for an eight-toughness
attacker -- off by every counter, anthem, Aura, Equipment and combat pump the
trick was cast into, while looking entirely implemented on screen.
`TestPrintedToughnessIsTheWrongAnswer` pins that spelling so the difference is
measured and not merely asserted.

The other two candidates and why they are not this:

- `toughness_had` reads `ctx.bindings["had_toughness"]`, which only the DIES and
  LEAVES_BATTLEFIELD *trigger* events bind. Entrapment Maneuver is an instant
  reading its own resolution, not a trigger.
- `for_each` does bind an object while it is still on the battlefield, but it
  goes through `resolve_pool` alone and ignores `count` and `chooser` -- so it
  would iterate every attacking creature the player controls instead of the one
  they chose.

So the value is taken in the one window `op_sacrifice` already has: after
`pick_from_pool` returns and before `sacrifice()` moves anything -- the same
window that writes `as`, using the same `zones.snapshot` and writing the same
binding shape as the `snapshot` op, so nothing downstream has to know which op
wrote it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

SPELL = "t_entrapment"  # snapshots the victim inside the sacrifice
NAIVE = "t_entrapment_printed"  # `as`, then a snapshot op afterwards
BEAR = "t_bear"  # 2/2
SOLDIER = "human_soldier_1_1_w"


def position(builder, *, spell: str = SPELL, counters: dict[str, int] | None = None):
    """Player 1 attacks with a Bear; player 0 holds ``spell`` and two Plains.

    Returns ``(game, oid)`` with the game sitting on player 0's priority in the
    declare-attackers step and ``oid`` the attacking Bear.
    """
    game = (
        builder(players=2)
        .battlefield(1, [BEAR], counters=counters)
        .battlefield(0, ["plains", "plains"])
        .hand(0, [spell])
        .active(1)
        .step(Step.UNTAP)
        .build()
    )
    oid = game.state.battlefield_objects(1)[0].oid
    for _ in range(200):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            break
        game.apply(_default_answer(game, decision))
    attack = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
    )
    game.apply(attack)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    return game, oid


def cast_at(game, defender: int, def_id: str = SPELL) -> None:
    """Cast the spell targeting player ``defender`` and let it resolve."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == def_id
        and any(t.kind == "player" and t.id == defender for t in a.targets)
    )
    game.apply(action)
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            return
        choose = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None
        )
        game.apply(choose if choose is not None else _default_answer(game, decision))


def soldiers(game, pid: int = 0) -> int:
    return sum(1 for o in game.state.battlefield_objects(pid) if o.def_id == SOLDIER)


class TestTheSnapshotIsTakenOnTheBattlefield:
    def test_counters_are_counted(self, builder):
        """A 2/2 with three +1/+1 counters is a 5/5, so it makes five Soldiers."""
        game, oid = position(builder, counters={"+1/+1": 3})
        assert chars(game.state, oid).toughness == 5
        cast_at(game, 1)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert soldiers(game) == 5

    def test_counters_can_lower_it_too(self, builder):
        """-1/-1 counters move the number down, not merely up.

        The bug is "the printed line", not "too small a number": a snapshot that
        quietly read the card would over-produce here and under-produce above,
        and a test that only ever grew the creature could not tell the two
        apart.
        """
        game, oid = position(builder, counters={"-1/-1": 1})
        assert chars(game.state, oid).toughness == 1
        cast_at(game, 1)
        assert soldiers(game) == 1

    def test_a_plain_creature_is_unchanged(self, builder):
        """With nothing modifying it, the snapshot equals the printed 2/2."""
        game, _ = position(builder)
        cast_at(game, 1)
        assert soldiers(game) == 2


class TestPrintedToughnessIsTheWrongAnswer:
    def test_snapshotting_after_the_sacrifice_reads_the_card(self, builder):
        """The spelling this capability exists to replace, measured.

        Identical card except that it records the choice with `as` and takes the
        snapshot in the *next* op. The Bear is a 5/5 on the battlefield and a
        2/2 in the graveyard, and this route makes two Soldiers.
        """
        game, oid = position(builder, spell=NAIVE, counters={"+1/+1": 3})
        assert chars(game.state, oid).toughness == 5
        cast_at(game, 1, def_id=NAIVE)
        assert soldiers(game) == 2

    def test_the_two_cards_disagree_only_because_of_the_window(self, builder):
        """…and agree when there is nothing for the counters to hide.

        Which is what makes the case above a statement about *when* the value is
        read rather than about two different effects.
        """
        game, _ = position(builder, spell=NAIVE)
        cast_at(game, 1, def_id=NAIVE)
        assert soldiers(game) == 2


class TestNothingWasChosen:
    def test_no_attacking_creature_binds_an_empty_snapshot(self, builder):
        """The boundary: the pool is empty, so the binding is `{}` and X is 0.

        `op_snapshot` binds `{}` rather than leaving the name unwritten when its
        pool is empty, and this must not diverge -- a stale binding from an
        earlier resolution would be read as a live one.
        """
        game = (
            builder(players=2)
            .battlefield(1, [BEAR])
            .battlefield(0, ["plains", "plains"])
            .hand(0, [SPELL])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        bear = game.state.battlefield_objects(1)[0].oid
        cast_at(game, 1)
        # Nothing was attacking, so nothing was sacrificed and nothing was made.
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert soldiers(game) == 0


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
    def test_a_valid_snapshot_loads(self):
        probe(
            {
                "op": "sacrifice",
                "objects": {"controller": "opponent", "count": 1, "chooser": "owner"},
                "snapshot": "victim",
            }
        )

    def test_snapshot_on_another_op_is_refused(self):
        """The silent failure the guard exists for.

        No op reads an unknown key, so `{"op": "destroy", "snapshot": "victim"}`
        would load, resolve, and leave every `{"toughness_of": {"binding":
        "victim"}}` on the card answering 0 -- a card that makes no tokens and
        says nothing about why.
        """
        with pytest.raises(DslError, match="only sacrifice reads it"):
            probe({"op": "destroy", "objects": {"controller": "opponent"}, "snapshot": "v"})

    def test_an_empty_name_is_refused(self):
        with pytest.raises(DslError, match="non-empty binding name"):
            probe({"op": "sacrifice", "objects": {"controller": "you"}, "snapshot": ""})

    def test_a_non_string_name_is_refused(self):
        with pytest.raises(DslError, match="non-empty binding name"):
            probe({"op": "sacrifice", "objects": {"controller": "you"}, "snapshot": 3})

    def test_the_snapshot_op_itself_still_loads(self):
        """`{"op": "snapshot"}` names its binding `as`, so the guard is about the
        *key* and must not catch the op that shares its name."""
        probe({"op": "snapshot", "objects": {"controller": "you"}, "as": "victim"})
