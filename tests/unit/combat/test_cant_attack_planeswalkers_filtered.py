""""Creatures they control can't attack Jaces you control this turn."

Rule 506.2 gives an attack three kinds of target -- a player, a planeswalker, a
battle -- and 508.1c makes a declaration illegal if any restriction is not
obeyed. `cant_attack_player` already spoke to two shapes of that: a **seat**
("you can't attack that player", walkers exempt) and **everything**
("creatures can't attack this combat", `planeswalkers: true`). Jace,
Multiverse Architect prints the third: some of the defender's planeswalkers,
picked out by subtype, and *not* the seat. Neither existing reading is that
card. The seat form leaves every Jace attackable and closes the player instead
-- a different card pointed at the wrong target; the whole-table form closes
the player and every walker, which is strictly stronger than the printing.

`planeswalkers_matching: {"subtypes": [...]}` is that sentence, and four
properties are pinned because each could be wrong without anything breaking:

1. **The seat stays open.** The player and their other planeswalkers are still
   legal targets; only the matching walkers drop out.
2. **The subtype is read live.** 611.2c locks the affected set only for effects
   that change characteristics; a prohibition is not one, so a Jace that
   arrives after the trigger resolved is covered for the rest of the turn.
3. **It lasts the turn,** extra combats included, and wears off at cleanup.
4. The loader refuses the shapes that would load as another card.

The witness is Jace, Multiverse Architect, whose first line is reproduced on
`t_jace_gate` so the trigger stands alone.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.temp_effects import restrict_attack
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, only_oid, pass_until

BEAR = "t_bear"
JACE = "t_jace_walker"  # a Jace, loyalty 4
SORIN = "t_walker"  # a Sorin, loyalty 4 -- the walker the filter does not name
GATE = "t_jace_gate"  # Jace, Multiverse Architect's first line on an artifact


def position(builder, *, players=2, mine=(BEAR,), theirs=(JACE, SORIN), third=(), active=0):
    """``mine`` under player 0, ``theirs`` under player 1, ``third`` under player 2."""
    b = builder(players=players)
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    if third:
        b.battlefield(2, list(third))
    return b.active(active).step(Step.UNTAP).build()


def to_declare_attackers(game, limit: int = 60):
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def offered(game, oid: int) -> tuple[list[int], list[int]]:
    """(players, permanents) this creature is offered as attack targets."""
    actions = [
        a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
    ]
    players = sorted(t.id for a in actions for t in a.targets if t.kind == "player")
    objects = sorted(t.id for a in actions for t in a.targets if t.kind == "object")
    return players, objects


def jaces(game, pid: int = 1, *, jace=JACE) -> int:
    return only_oid(game, jace, pid)


class TestOnlyTheMatchingWalkersAreClosed:
    def test_the_seat_and_the_other_walker_stay_open(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 0)
        jace, sorin = jaces(game), only_oid(game, SORIN, 1)
        restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Jace",))
        to_declare_attackers(game)
        assert offered(game, bear) == ([1], [sorin]), (
            "the player and their Sorin are attackable; only the Jace is not"
        )
        assert jace not in offered(game, bear)[1]

    def test_add_attacker_agrees_with_legality(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 0)
        jace, sorin = jaces(game), only_oid(game, SORIN, 1)
        restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Jace",))
        to_declare_attackers(game)
        assert not combat_mod.add_attacker(game.state, bear, 1, permanent=jace)
        assert combat_mod.add_attacker(game.state, bear, 1, permanent=sorin)

    def test_the_seat_form_is_the_wrong_card(self, builder):
        """The near miss, pinned: the seat restriction closes the player and
        leaves the Jace open -- the exact opposite of the printed line."""
        game = position(builder)
        bear = only_oid(game, BEAR, 0)
        jace, sorin = jaces(game), only_oid(game, SORIN, 1)
        restrict_attack(game.state, 0, 1, "this_turn")
        to_declare_attackers(game)
        assert offered(game, bear) == ([], sorted([jace, sorin]))

    def test_it_protects_only_the_defenders_jaces(self, builder):
        """"Jaces *you* control": another player's Jace is still a target."""
        game = position(builder, players=3, theirs=(JACE,), third=(JACE,))
        bear = only_oid(game, BEAR, 0)
        mine, theirs = jaces(game, 1), jaces(game, 2)
        restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Jace",))
        to_declare_attackers(game)
        assert offered(game, bear) == ([1, 2], [theirs])
        assert mine not in offered(game, bear)[1]

    def test_it_points_one_way(self, builder):
        game = position(builder, mine=(BEAR, JACE), theirs=(BEAR,), active=1)
        bear = only_oid(game, BEAR, 1)
        restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Jace",))
        to_declare_attackers(game)
        assert offered(game, bear) == ([0], [jaces(game, 0)])

    def test_a_creature_with_only_jaces_to_attack_still_attacks_the_player(self, builder):
        game = position(builder, theirs=(JACE,))
        bear = only_oid(game, BEAR, 0)
        restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Jace",))
        assert combat_mod.can_attack(game.state, bear)


class TestTheSubtypeIsReadLive:
    def test_a_jace_that_arrives_later_is_covered(self, builder):
        """611.2c: a prohibition is not locked to the objects present when it
        resolved. "Jaces you control" means every Jace at declaration."""
        b = builder(players=2)
        b.battlefield(0, [BEAR]).battlefield(1, [SORIN]).hand(1, [JACE])
        game = b.active(0).step(Step.UNTAP).build()
        bear = only_oid(game, BEAR, 0)
        restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Jace",))
        jace = next(
            oid
            for oid, obj in game.state.objects.items()
            if obj.def_id == JACE and obj.zone is Zone.HAND
        )
        move_object(game.state, jace, Zone.BATTLEFIELD)
        to_declare_attackers(game)
        assert offered(game, bear) == ([1], [only_oid(game, SORIN, 1)])

    def test_a_walker_that_stops_being_a_jace_is_open_again(self, builder):
        """The other half of reading it live: the test is the walker's subtypes
        now, not the ones it had when the trigger resolved."""
        game = position(builder, theirs=(JACE,))
        bear = only_oid(game, BEAR, 0)
        jace = jaces(game)
        restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Jace",))
        assert combat_mod.attack_target_forbidden(game.state, bear, 1, permanent=jace)
        restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Sorin",))
        assert combat_mod.attack_target_forbidden(game.state, bear, 1, permanent=jace), (
            "an unrelated subtype does not lift the Jace restriction"
        )
        game.state.attack_restrictions.pop(0)
        assert not combat_mod.attack_target_forbidden(game.state, bear, 1, permanent=jace)


class TestTheDuration:
    def test_it_survives_the_combat(self, builder):
        game = position(builder)
        restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Jace",))
        to_declare_attackers(game)
        combat_mod.end_combat(game.state)
        assert [r.walker_subtypes for r in game.state.attack_restrictions] == [("Jace",)]

    def test_it_ends_at_cleanup(self, builder):
        game = position(builder)
        restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Jace",))
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.attack_restrictions == []

    def test_it_is_a_different_entry_from_the_seat_restriction(self, builder):
        game = position(builder)
        assert restrict_attack(game.state, 0, 1, "this_turn")
        assert restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Jace",))
        assert not restrict_attack(game.state, 0, 1, "this_turn", walker_subtypes=("Jace",))
        assert len(game.state.attack_restrictions) == 2


class TestTheTrigger:
    """Jace, Multiverse Architect's first line: a may-pay at the beginning of
    each opponent's combat, and the restriction is the unpaid branch."""

    def test_declining_closes_the_jace_and_not_the_player(self, builder):
        game = position(builder, mine=(GATE, JACE, SORIN), theirs=(BEAR,), active=1)
        bear = only_oid(game, BEAR, 1)
        to_declare_attackers(game)
        assert [
            (r.attacker, r.defender, r.duration, r.walker_subtypes)
            for r in game.state.attack_restrictions
        ] == [(1, 0, "this_turn", ("Jace",))]
        assert offered(game, bear) == ([0], [only_oid(game, SORIN, 0)])

    def test_it_does_not_fire_on_its_controllers_own_turn(self, builder):
        game = position(builder, mine=(GATE, BEAR), theirs=(JACE,))
        to_declare_attackers(game)
        assert game.state.attack_restrictions == []


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


def restriction(**extra) -> dict:
    return {
        "op": "cant_attack_player",
        "attacker": "each_opponent",
        "defender": "you",
        "duration": "this_turn",
        **extra,
    }


class TestTheLoaderGuardsIt:
    def test_the_printed_shape_loads(self):
        probe(restriction(planeswalkers_matching={"subtypes": ["Jace"]}))

    @pytest.mark.parametrize(
        "matching",
        [{}, {"subtypes": []}, {"subtypes": "Jace"}, ["Jace"], {"subtypes": ["Jace"], "controller": "you"}],
    )
    def test_a_malformed_filter_is_refused(self, matching):
        with pytest.raises(DslError, match="planeswalkers_matching: must be"):
            probe(restriction(planeswalkers_matching=matching))

    def test_a_creature_subtype_is_refused(self):
        """A filter that can match no planeswalker would prohibit nothing."""
        with pytest.raises(DslError, match="not a planeswalker subtype"):
            probe(restriction(planeswalkers_matching={"subtypes": ["Wizard"]}))

    def test_it_is_refused_beside_the_whole_table_flag(self):
        with pytest.raises(DslError, match="not both"):
            probe(
                restriction(planeswalkers=True, planeswalkers_matching={"subtypes": ["Jace"]})
            )
