"""Battles: defense counters, being attacked, and being defeated (rule 310).

    Zurgo and Ojutai — "…deal combat damage to a player **or battle**".

`CardType.BATTLE` existed and did nothing. A battle entered play as an inert
permanent with no defense, nothing in `combat.py` would let a creature be
declared as attacking one, `_attacker_assignments` had no branch that could put
damage on one, and `or_planeswalker` was the only key in the vocabulary that
widened an attack past a seat. The card that forced the question is Zurgo and
Ojutai, whose printed trigger names battles beside players: written for the
player half alone it is a strictly narrower card in any game with a battle on
the board.

Almost none of this is new machinery, which is the point — 506.2 already had a
third defender kind and the engine already modelled it:

| already there | what it becomes |
|---|---|
| counters are free-form strings | `"defense"` is a counter like any other |
| `self_enters_with_counters` | starting defense, with nothing new at ETB |
| `attacking_planeswalker` | `attacking_permanent`: 506.2's non-seat defenders |
| `_planeswalker_deaths` | a sibling pass for 704.5x |

What had to be decided:

**Defense is counters (310.4).** So printed defense compiles into an
enters-with-counters replacement rather than a field the engine reads, and
proliferate, `counters_on` and the client's badge read a battle for free. A
`defense` the card did not print is refused at load time, because 704.5x would
defeat such a battle the instant it resolved — silently.

**Damage removes defense (310.6)**, read in `damage_permanent` beside the
planeswalker's loyalty branch and for its reason: marking `obj.damage` on a
battle would be invisible, so it would take damage for ever and never die.

**One declaration slot for two permanent types.** `attacking_planeswalker`
became `attacking_permanent`, because 506.2 makes a planeswalker and a battle
the same kind of declaration and the only thing that differs is which counter
the damage comes off. `attackers[oid]` still means the defending player.

**Protectors (310.7, 506.2b) are not modelled**, and the divergence is loud
rather than quiet: a battle here is attackable by the people who could attack
*its controller*, the planeswalker rule applied unchanged, where a real Siege is
attacked by its controller because its protector is an opponent. See
`engine/battles.py` and `docs/rules-coverage.md`.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import sba
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import damage_permanent
from automtg.engine.temp_effects import restrict_attack
from tests.conftest import only_oid, pass_until

BATTLE = "t_battle_wall"  # Siege, defense 3, no text
BIG = "t_battle_big"  # Siege, defense 7
HITTER = "t_battle_hitter"  # 2/2 vanilla


def board(builder, *, battle: str = BATTLE, mine=(HITTER,)):
    """The opponent's battle, and creatures of mine to swing at it with."""
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 5 + list(mine))
        .battlefield(1, [battle])
        .hand(0, [])
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def attacks(game, attacker: int) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == attacker
    ]


def swing_at(game, attackers: dict[int, int]) -> None:
    """Declare each attacker against the permanent it is mapped to, and finish."""
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    for attacker, target in attackers.items():
        game.apply(
            next(
                a
                for a in attacks(game, attacker)
                if any(ref.id == target and ref.kind == "object" for ref in a.targets)
            )
        )
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )


class TestItArrivesWithDefense:
    def test_the_counters_are_there(self, builder):
        """310.3/310.4: the printed number is counters, placed as it enters."""
        game = board(builder)
        battle = only_oid(game, BATTLE, 1)
        assert game.state.objects[battle].counter("defense") == 3

    def test_it_is_a_battle_on_the_board(self, builder):
        game = board(builder)
        assert "Battle" in chars(game.state, only_oid(game, BATTLE, 1)).types

    def test_it_is_not_defeated_on_arrival(self, builder):
        """The state-based action runs before anybody sees the board; a battle
        that entered with its counters has to survive that pass."""
        game = board(builder)
        assert only_oid(game, BATTLE, 1) in game.state.battlefield


class TestDamageComesOffDefense:
    def test_damage_removes_that_many_counters(self, builder):
        """310.6, the loyalty branch's sibling."""
        game = board(builder, battle=BIG)
        battle = only_oid(game, BIG, 1)
        damage_permanent(game.state, battle, 2, None)
        assert game.state.objects[battle].counter("defense") == 5

    def test_it_is_not_marked_as_damage(self, builder):
        """The whole reason the branch exists: `obj.damage` on a battle is
        invisible, because nothing ever compares it to anything."""
        game = board(builder, battle=BIG)
        battle = only_oid(game, BIG, 1)
        damage_permanent(game.state, battle, 2, None)
        assert game.state.objects[battle].damage == 0

    def test_the_last_counter_defeats_it(self, builder):
        """704.5x, checked at the boundary: exactly lethal, not one over."""
        game = board(builder)
        battle = only_oid(game, BATTLE, 1)
        damage_permanent(game.state, battle, 3, None)
        sba.run(game.state)
        assert battle not in game.state.battlefield
        assert game.state.objects[battle].zone is Zone.GRAVEYARD

    def test_one_short_leaves_it_standing(self, builder):
        game = board(builder)
        battle = only_oid(game, BATTLE, 1)
        damage_permanent(game.state, battle, 2, None)
        sba.run(game.state)
        assert battle in game.state.battlefield
        assert game.state.objects[battle].counter("defense") == 1

    def test_it_goes_to_its_owners_graveyard_not_the_exile(self, builder):
        """Not destruction (the shape `_planeswalker_deaths` keeps), so it is
        `move_object` and the owner's graveyard rather than its controller's."""
        game = board(builder)
        battle = only_oid(game, BATTLE, 1)
        damage_permanent(game.state, battle, 9, None)
        sba.run(game.state)
        assert battle in game.state.players[1].graveyard


class TestAttackingOne:
    def test_it_is_offered_as_a_thing_to_attack(self, builder):
        game = board(builder)
        hitter = only_oid(game, HITTER, 0)
        battle = only_oid(game, BATTLE, 1)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)

        targets = {ref.id for a in attacks(game, hitter) for ref in a.targets}
        assert battle in targets, "only the player was offered"

    def test_the_player_is_still_offered_too(self, builder):
        game = board(builder)
        hitter = only_oid(game, HITTER, 0)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)

        kinds = {ref.kind for a in attacks(game, hitter) for ref in a.targets}
        assert kinds == {"player", "object"}

    def test_the_damage_lands_on_the_battle(self, builder):
        game = board(builder)
        hitter, battle = only_oid(game, HITTER, 0), only_oid(game, BATTLE, 1)
        life = game.state.players[1].life
        swing_at(game, {hitter: battle})
        pass_until(game, lambda g: g.state.step is Step.END_OF_COMBAT)

        assert game.state.objects[battle].counter("defense") == 1
        assert game.state.players[1].life == life, "the controller took none of it"

    def test_attacking_a_battle_is_not_attacking_its_controller(self, builder):
        """506.2. `attackers[oid]` still names the defending player -- that is
        what keeps the fifteen existing reads of it true -- but the creature is
        not attacking *them*, and `attacking_permanent` is the record that says
        so."""
        from automtg.engine.effects.selectors import attacking_player_matches

        game = board(builder)
        hitter, battle = only_oid(game, HITTER, 0), only_oid(game, BATTLE, 1)
        swing_at(game, {hitter: battle})
        combat = game.state.combat

        assert combat.attackers[hitter] == 1, "the defending player is its controller"
        assert combat.attacking_permanent[hitter] == battle
        assert not attacking_player_matches(combat, hitter, "opponent", 0), (
            "'attacks an opponent' counted a creature that attacked a battle"
        )

    def test_a_swing_that_defeats_it_leaves_the_seat_untouched(self, builder):
        """The whole risk of the attack, and the whole reward: the battle dies,
        the player it belonged to loses no life at all."""
        game = board(builder)
        hitter, battle = only_oid(game, HITTER, 0), only_oid(game, BATTLE, 1)
        damage_permanent(game.state, battle, 1, None)
        life = game.state.players[1].life
        swing_at(game, {hitter: battle})
        pass_until(game, lambda g: g.state.step is Step.END_OF_COMBAT)

        assert battle not in game.state.battlefield
        assert game.state.players[1].life == life

    def test_your_own_battle_is_not_a_legal_defender(self, builder):
        """The protector divergence, written down as a test so it cannot drift
        silently: with 506.2b unmodelled a battle is attacked by the people who
        could attack its *controller*, exactly as a planeswalker is."""
        game = (
            builder(players=2)
            .battlefield(0, ["swamp"] * 5 + [HITTER, BATTLE])
            .battlefield(1, [])
            .hand(0, [])
            .library(0, ["swamp"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        hitter = only_oid(game, HITTER, 0)
        mine = only_oid(game, BATTLE, 0)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)

        targets = {ref.id for a in attacks(game, hitter) for ref in a.targets}
        assert mine not in targets


class TestGoadSeesABattleAsSomewhereElseToSwing:
    """701.38b, and the one place the rename had to reach past declaration.

    `_has_non_goader_defender` answers goad's "…if able", and it walked the
    battlefield for planeswalkers by name. A goaded creature whose only
    attackable *seat* is the goader's, with a third player's battle on the
    board, has somewhere else to go -- the battle's controller is the defending
    player (506.2), exactly as a walker's is -- and offered only the goader it
    would be forced into an attack the rules do not require.
    """

    def test_a_third_players_battle_discharges_the_requirement(self, builder):
        from automtg.engine import combat as combat_mod

        game = (
            builder(players=3)
            .battlefield(0, ["swamp"] * 5 + [HITTER])
            .battlefield(1, [])
            .battlefield(2, [BATTLE])
            .hand(0, [])
            .library(0, ["swamp"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        hitter = only_oid(game, HITTER, 0)
        # Goaded by player 1, and player 2's seat taken off the table, so the
        # battle is the only defender left that no goader controls.
        game.state.objects[hitter].goaded_by = {1}
        restrict_attack(game.state, 0, 2, "this_turn")

        assert combat_mod._has_non_goader_defender(game.state, hitter, {1})


class TestTheLoaderRefusesAnImpossibleBattle:
    def compile(self, **extra):
        return compile_card(
            CardModel.model_validate(
                {"id": "x", "name": "X", "types": ["Battle"], **extra}
            )
        )

    def test_a_battle_without_defense_is_refused(self):
        """Not a weaker card: 704.5x defeats it as it resolves, so it is a card
        that never reaches the battlefield at all."""
        with pytest.raises(DslError, match="battles need 'defense'"):
            self.compile()

    def test_defense_on_something_else_is_refused(self):
        with pytest.raises(DslError, match="battle's characteristic"):
            compile_card(
                CardModel.model_validate(
                    {"id": "x", "name": "X", "types": ["Artifact"], "defense": 2}
                )
            )

    def test_the_defense_becomes_an_enters_with_counters_replacement(self):
        card = self.compile(defense=4)
        assert any(
            r["event"] == "self_enters_with_counters"
            and r["counter"] == "defense"
            and r["amount"] == 4
            for r in card.replacements
        )


class TestTheActionSpaceCanSayIt:
    """A battle is a defender the RL encoder has to have a slot for, and the
    slots are flat and fixed. Folded in *after* each seat's planeswalkers so no
    walker's slot moves and `DEF_CAP` stays at 8 -- raising it would invalidate
    every trained checkpoint."""

    def test_attacking_a_battle_has_an_index(self, builder):
        from automtg.ai import action_space

        game = board(builder)
        hitter, battle = only_oid(game, HITTER, 0), only_oid(game, BATTLE, 1)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)

        table = action_space.build(game.state)
        swings = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER
            and a.source == hitter
            and any(ref.id == battle and ref.kind == "object" for ref in a.targets)
        ]
        assert swings, "legality never offered the attack"
        assert all(a not in table.dropped for a in swings)
