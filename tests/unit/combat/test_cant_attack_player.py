""""That player can't attack you": the first attack prohibition with two sides.

Rule 508.1c is the one that makes this real -- as a player declares attackers,
"the declaration is illegal if any restrictions aren't obeyed". Every restriction
the engine had was a fact about a single creature: `cant_attack` (Stormtide
Leviathan), `defender`, being tapped, being detained. `attack_forbidden` matches
its filter against the **attacking creature** and takes no defending player at
all, so the sentence on these two cards was not a weaker version of any of them.

The witnesses, and they point in opposite directions, which is the whole reason
one op carries three parameters instead of two near-duplicate ops being built:

- **Call for Aid** -- "You can't attack that player this turn." Installed by a
  resolving *sorcery*, restricting the spell's own controller, scoped to the turn.
  A static could not do it three ways over: there is no permanent left on the
  battlefield to hang it off, no op installs a static, and a static's `affects`
  filter may read only printed characteristics so it could never name a player
  chosen on resolution.
- **Champions of Minas Tirith** -- "…they can't attack you this combat."
  Installed by a *triggered ability*, restricting a third party (the triggering
  opponent) from attacking the ability's controller, scoped to the combat.

Four properties are worth pinning, and each one is a way this could be silently
wrong rather than broken:

1. It narrows the choice instead of removing it. A creature under it still
   attacks anybody else -- a restriction that blanked the attack step would be a
   strictly stronger card than either of these, and nothing would say so.
2. It points one way. Stopping A attacking B says nothing about B attacking A.
3. **Planeswalkers are exempt.** "Creatures can't attack you" restricts attacking
   the *player*; attacking a planeswalker that player controls is not that, which
   is why Ghostly Prison taxes nothing when the attack goes at a planeswalker
   (506.2 makes the walker the thing attacked and its controller merely the
   defending player).
4. The two durations are not interchangeable. `this_combat` has to end with the
   combat, or a Relentless Assault's extra combat would be taxed by a toll that
   was already paid; `this_turn` has to survive the combat it was cast before,
   because Call for Aid is a sorcery cast in a main phase and means the turn.

The legality seam this needed -- `legal_defenders`/`legal_permanent_defenders`
/`add_attacker` taking the attacking oid, funnelled through one
`attack_target_forbidden` predicate -- is the same seam `goad` was recorded
needing, which is why it is per-attacker rather than per-attacking-player.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.temp_effects import restrict_attack
from commanderblitz.engine.turn import grant_extra_phases
from tests.conftest import _default_answer, only_oid, pass_until

BEAR = "t_bear"
WALKER = "t_walker"
TRUCE = "t_truce_caller"  # {W} sorcery: you can't attack target player this turn
TOLL = "t_toll_gate"  # artifact: each opponent can't attack you on their own combat


def position(builder, *, players=2, mine=(BEAR,), theirs=(), lends=(), active=0, hand=()):
    """A board with ``mine`` under player 0 and ``theirs`` under player 1."""
    b = builder(players=players)
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    if lends:
        b.battlefield(2, list(lends))
    if hand:
        b.hand(0, list(hand)).battlefield(0, ["plains", "plains"])
    # Built from the untap step and advanced, so the position starts at the
    # active player's first priority with the turn's own machinery having run --
    # a restriction installed after this is one a resolving spell could have
    # installed.
    return b.active(active).step(Step.UNTAP).build()


def to_declare_attackers(game, limit: int = 60):
    """Advance to the declare-attackers decision, resolving whatever is on the way."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def attack_actions(game, oid: int | None = None):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and (oid is None or a.source == oid)
    ]


def defenders_offered(game, oid: int) -> list[int]:
    """Which *players* this creature is offered as able to attack."""
    return sorted(
        t.id for a in attack_actions(game, oid) for t in a.targets if t.kind == "player"
    )


def walkers_offered(game, oid: int) -> list[int]:
    """Which *planeswalkers* this creature is offered as able to attack."""
    return sorted(
        t.id for a in attack_actions(game, oid) for t in a.targets if t.kind == "object"
    )


class TestItNarrowsTheChoiceRatherThanRemovingIt:
    def test_without_it_every_opponent_is_offered(self, builder):
        game = position(builder, players=3)
        bear = only_oid(game, BEAR, 0)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [1, 2], "the unrestricted baseline"

    def test_the_named_defender_drops_out_and_the_others_do_not(self, builder):
        game = position(builder, players=3)
        bear = only_oid(game, BEAR, 0)
        restrict_attack(game.state, 0, 1, "this_turn")
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [2], (
            "player 1 is protected; the creature is still free to attack player 2"
        )

    def test_it_covers_the_whole_team(self, builder):
        """The restriction names a *player*, so every creature they control is
        under it -- not just the one that happened to be on the board when the
        spell resolved."""
        game = position(builder, players=3, mine=(BEAR, BEAR))
        restrict_attack(game.state, 0, 1, "this_turn")
        to_declare_attackers(game)
        for bear in (o for o in game.state.battlefield if game.state.objects[o].def_id == BEAR):
            assert defenders_offered(game, bear) == [2]

    def test_it_points_one_way(self, builder):
        """Champions of Minas Tirith stops *them* attacking *you*, and says
        nothing at all about your own attacks. A symmetrical implementation
        would be a different card in both directions."""
        game = position(builder, players=3)
        bear = only_oid(game, BEAR, 0)
        restrict_attack(game.state, 1, 0, "this_turn")
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [1, 2]


class TestLegalityAndAddAttackerAgree:
    """An action legality offers and `add_attacker` then refuses is a
    declaration that cannot be completed, so the two read one predicate."""

    def test_add_attacker_refuses_the_forbidden_defender(self, builder):
        game = position(builder, players=3)
        bear = only_oid(game, BEAR, 0)
        restrict_attack(game.state, 0, 1, "this_turn")
        to_declare_attackers(game)
        assert not combat_mod.add_attacker(game.state, bear, 1)
        assert combat_mod.add_attacker(game.state, bear, 2)

    def test_the_predicate_is_asked_per_pair(self, builder):
        game = position(builder, players=3)
        bear = only_oid(game, BEAR, 0)
        restrict_attack(game.state, 0, 1, "this_turn")
        assert combat_mod.attack_target_forbidden(game.state, bear, 1)
        assert not combat_mod.attack_target_forbidden(game.state, bear, 2)


class TestPlaneswalkersAreExempt:
    """"Creatures can't attack you" is about the player. Attacking a
    planeswalker they control is a different thing being attacked (506.2), which
    is why a Ghostly Prison charges nothing for it."""

    def test_the_protected_players_walker_is_still_attackable(self, builder):
        game = position(builder, players=3, theirs=(WALKER,))
        bear = only_oid(game, BEAR, 0)
        walker = only_oid(game, WALKER, 1)
        restrict_attack(game.state, 0, 1, "this_turn")
        to_declare_attackers(game)
        assert 1 not in defenders_offered(game, bear)
        assert walker in walkers_offered(game, bear)
        assert combat_mod.add_attacker(game.state, bear, 1, permanent=walker)
        assert game.state.combat.attackers[bear] == 1, (
            "the walker's controller is still the defending player (506.2)"
        )

    def test_the_walker_keeps_the_creature_a_legal_attacker(self, builder):
        """Two players, and the only thing left to attack is a planeswalker.
        The creature must still be able to attack it."""
        game = position(builder, theirs=(WALKER,))
        bear = only_oid(game, BEAR, 0)
        restrict_attack(game.state, 0, 1, "this_turn")
        assert combat_mod.can_attack(game.state, bear)


class TestACreatureWithNobodyLeftToAttack:
    def test_it_is_not_a_legal_attacker(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 0)
        restrict_attack(game.state, 0, 1, "this_turn")
        assert not combat_mod.can_attack(game.state, bear)
        assert combat_mod.legal_attackers(game.state) == []

    def test_a_compelled_creature_does_not_deadlock_the_step(self, builder):
        """"…if able" is the whole second half. A creature required to attack
        with every defender forbidden owes nothing -- and if `can_attack` said
        otherwise, legality would withhold "Done attacking" with no
        ADD_ATTACKER left to offer, which is a step with no legal action in it.
        """
        game = position(builder)
        bear = only_oid(game, BEAR, 0)
        game.state.objects[bear].must_attack = "this_turn"
        game.state.objects[bear].must_attack_turn = game.state.turn
        restrict_attack(game.state, 0, 1, "this_turn")
        assert combat_mod.unmet_attack_requirements(game.state) == []
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.turn >= 2, "the turn ran to completion"

    def test_the_requirement_is_live_again_once_the_restriction_lifts(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 0)
        game.state.objects[bear].must_attack = "this_turn"
        game.state.objects[bear].must_attack_turn = game.state.turn
        restrict_attack(game.state, 0, 1, "this_turn")
        assert combat_mod.unmet_attack_requirements(game.state) == []
        game.state.attack_restrictions.clear()
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]


class TestTheDurations:
    def test_this_combat_ends_with_the_combat(self, builder):
        game = position(builder, players=3)
        restrict_attack(game.state, 0, 1, "this_combat")
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)
        assert game.state.attack_restrictions == [], (
            "the toll was paid for one combat, not for the turn"
        )

    def test_this_turn_survives_the_combat_it_was_cast_before(self, builder):
        """Call for Aid is a sorcery: it resolves in a main phase and means the
        whole turn. Cleared at end of combat it would restrict nothing at all in
        a turn with one combat phase, which is every turn."""
        game = position(builder, players=3)
        restrict_attack(game.state, 0, 1, "this_turn")
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)
        assert [r.duration for r in game.state.attack_restrictions] == ["this_turn"]

    def test_this_turn_ends_at_cleanup(self, builder):
        game = position(builder, players=3)
        restrict_attack(game.state, 0, 1, "this_turn")
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.attack_restrictions == []


class TestThePrimitiveRefusesWhatCannotBite:
    def test_a_player_cannot_be_stopped_from_attacking_themselves(self, builder):
        game = position(builder)
        assert not restrict_attack(game.state, 0, 0, "this_turn")
        assert game.state.attack_restrictions == []

    def test_the_same_pair_is_recorded_once(self, builder):
        game = position(builder)
        assert restrict_attack(game.state, 0, 1, "this_turn")
        assert not restrict_attack(game.state, 0, 1, "this_turn")
        assert len(game.state.attack_restrictions) == 1

    def test_two_durations_on_one_pair_are_two_entries(self, builder):
        """The shorter one wearing off must not take the longer one with it."""
        game = position(builder, players=3)
        restrict_attack(game.state, 0, 1, "this_turn")
        restrict_attack(game.state, 0, 1, "this_combat")
        assert len(game.state.attack_restrictions) == 2
        combat_mod.end_combat(game.state)
        assert [r.duration for r in game.state.attack_restrictions] == ["this_turn"]

    def test_an_eliminated_player_is_not_restricted(self, builder):
        game = position(builder, players=3)
        game.state.players[1].has_lost = True
        assert not restrict_attack(game.state, 0, 1, "this_turn")


class TestTheSorceryForm:
    """Call for Aid's clause: self-directed and turn-scoped."""

    def cast_truce(self, game, victim: int) -> None:
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and TargetRef.player(victim) in a.targets
        )
        game.apply(action)
        for _ in range(30):
            if not game.state.stack and not game.state.pending_triggers:
                return
            decision = game.pending()
            if decision is None:
                game._advance()
                continue
            game.apply(_default_answer(game, decision))
        raise AssertionError("the truce never resolved")

    def test_it_restricts_its_own_controller(self, builder):
        game = position(builder, players=3, hand=(TRUCE,))
        self.cast_truce(game, 1)
        assert [
            (r.attacker, r.defender, r.duration) for r in game.state.attack_restrictions
        ] == [(0, 1, "this_turn")]

    def test_the_caster_then_cannot_attack_that_player(self, builder):
        game = position(builder, players=3, hand=(TRUCE,))
        bear = only_oid(game, BEAR, 0)
        self.cast_truce(game, 1)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [2]


class TestTheTriggeredThirdPartyForm:
    """Champions of Minas Tirith's clause: the ability's controller is the
    protected player and somebody else is the one restricted."""

    def test_the_triggering_opponent_cannot_attack_the_controller(self, builder):
        game = position(builder, players=3, mine=(TOLL,), theirs=(BEAR,), active=1)
        bear = only_oid(game, BEAR, 1)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [2], (
            "player 0 is protected by their own toll gate; player 2 is not"
        )

    def test_an_extra_combat_re_asks_the_toll(self, builder):
        """The reason the duration is `this_combat` and not `this_turn`: the
        trigger fires at the beginning of *each* combat, so the restriction has
        to have gone with the combat that bought it or the second combat would
        be taxed by a toll already paid -- and, the other way round, must be
        re-imposed rather than left expired."""
        game = position(builder, players=3, mine=(TOLL,), theirs=(BEAR,), active=1)
        bear = only_oid(game, BEAR, 1)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [2]
        assert grant_extra_phases(game.state, ["combat"]) == ["combat"]
        pass_until(
            game,
            lambda g: g.state.extra_phases_taken >= 1
            and g.state.step is Step.DECLARE_ATTACKERS,
        )
        assert game.state.step is Step.DECLARE_ATTACKERS, "reached the second combat"
        assert [
            (r.attacker, r.defender, r.duration) for r in game.state.attack_restrictions
        ] == [(1, 0, "this_combat")], "re-imposed for the new combat, not left over"


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
    def test_a_missing_attacker_is_refused(self):
        with pytest.raises(DslError, match="needs 'attacker'"):
            probe({"op": "cant_attack_player", "defender": "you", "duration": "this_turn"})

    def test_a_missing_defender_is_refused(self):
        with pytest.raises(DslError, match="needs 'defender'"):
            probe({"op": "cant_attack_player", "attacker": "you", "duration": "this_turn"})

    def test_a_missing_duration_is_refused(self):
        """Neither duration is the safe default -- one blanks an extra combat,
        the other gives it away -- so the word is required."""
        with pytest.raises(DslError, match="needs a 'duration'"):
            probe({"op": "cant_attack_player", "attacker": "you", "defender": "opponent"})

    def test_an_unknown_duration_is_refused(self):
        with pytest.raises(DslError, match="unknown cant_attack_player duration"):
            probe(
                {
                    "op": "cant_attack_player",
                    "attacker": "you",
                    "defender": "opponent",
                    "duration": "until_your_next_turn",
                }
            )

    def test_an_unknown_player_spec_is_refused(self):
        with pytest.raises(DslError, match="unknown player spec"):
            probe(
                {
                    "op": "cant_attack_player",
                    "attacker": "the_monarch",
                    "defender": "you",
                    "duration": "this_turn",
                }
            )

    def test_a_target_the_card_never_declared_is_refused(self):
        with pytest.raises(DslError, match="does not declare"):
            probe(
                {
                    "op": "cant_attack_player",
                    "attacker": "you",
                    "defender": {"target": "t1"},
                    "duration": "this_turn",
                }
            )

    def test_both_witness_shapes_compile(self, registry):
        assert [e["op"] for e in registry.get(TRUCE).spell_effects] == [
            "cant_attack_player"
        ]
        ability = registry.get(TOLL).abilities[0]
        assert [e["op"] for e in ability.effects] == ["cant_attack_player"]
        assert ability.effects[0]["duration"] == "this_combat"
