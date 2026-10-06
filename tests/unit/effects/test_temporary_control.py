""""Gain control of target permanent **until end of turn**." Act of Treason.

`gain_control` was permanent-only *by decision*, not by omission: the loader
refused a `duration` key outright rather than ignoring one, because a card that
asked for "until end of turn" and got a permanent steal is a **strictly better**
card than the printed one — Zealous Conscripts that keeps the creature, on a
board where nothing looks wrong. The refusal was the right shape for a missing
feature. This is the feature.

The interesting half is not the steal, which is the call that already existed.
It is the **handback**, and specifically that it is the same call pointed the
other way rather than an assignment to `controller`, because a control change is
three rules and none of them is symmetric with itself:

* **302.6 — summoning sickness for the player getting it back.** The creature
  has not been under its original controller continuously since their turn
  began either; somebody else had it in between. The plausible wrong
  implementation is the tidy one — save `entered_turn` alongside the controller
  and restore both, "putting it back as it was" — which hands back a creature
  that is *not* newly under its controller's control and can tap for mana in the
  514.3a priority window that a cleanup trigger opens.
* **506.4 — removal from combat.** Structural here rather than observable:
  `state.combat` is `None` by the time the cleanup step runs, so no turn
  structure this engine has reaches a handback mid-combat. It costs one branch
  inside a call that is being made anyway, and the alternative is a rule that is
  correct only for as long as nobody adds a combat phase.
* **The characteristics cache.** Fully observable and the one a hand-rolled
  handback silently loses: every static filtered on `controller` reads
  differently in both directions, so a creature stolen under an anthem is 3/3
  going out and has to be 2/2 coming back.

Three more things the store has to get right, all of them about *which* handback:

* a permanent that left the battlefield during the turn is not resurrected —
  free, because `reset_permanent_state` empties `until_eot` on the way out, and
  the Act-of-Treason-plus-sacrifice line depends on it;
* two steals in one turn unwind newest-first, or the first handback finds the
  wrong controller and stops;
* a *permanent* control change made afterwards outlives this one, so the stored
  seat is validated against the current controller rather than trusted. Mind
  Control cast on a creature somebody already Act of Treason'd does not evaporate
  at end of turn.

Witness: Zealous Conscripts, and behind it Act of Treason, Threaten, Harness by
Force, Mark of Mutiny, Kari Zev's Expertise and Insurrection.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import change_control, clear_until_eot
from automtg.engine.structs import CombatState, TargetRef
from automtg.engine.zones import move_object
from tests.conftest import _default_answer, only_oid, pass_until

TREASON = "t_treason"  # {2}{R} sorcery: steal, untap, haste — all until end of turn
STEAL = "t_permanent_steal"  # {3}{U} sorcery: gain control, no duration
BEAR = "t_bear"
ANTHEM = "t_anthem"  # creatures *you* control get +1/+1


def position(builder):
    """Player 0 holds the Treason; player 1's Bear is the victim.

    The anthem is not scenery: it is the only thing on this board that can tell
    a control change from a field assignment, because it is the one
    characteristic that reads differently depending on whose side the Bear is
    standing on.
    """
    game = (
        builder(players=2)
        .hand(0, [TREASON])
        .battlefield(0, ["mountain", "mountain", "mountain", ANTHEM])
        .battlefield(1, [BEAR])
        .build()
    )
    return game, only_oid(game, BEAR, 1)


def resolve(game) -> None:
    """Let the stack empty, declining every optional choice."""
    for _ in range(30):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the spell never resolved")


def cast_at(game, card_id: str, victim: int) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and TargetRef.obj(victim) in a.targets
        and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    resolve(game)


class TestTheSteal:
    def test_the_thief_controls_it(self, builder):
        game, victim = position(builder)
        cast_at(game, TREASON, victim)
        assert game.state.objects[victim].controller == 0

    def test_the_thiefs_anthem_now_reaches_it(self, builder):
        """The characteristics cache dropped on the way *out* — a 2/2 belonging
        to the other player is a 3/3 the moment it changes sides."""
        game, victim = position(builder)
        assert chars(game.state, victim).power == 2
        cast_at(game, TREASON, victim)
        assert chars(game.state, victim).power == 3

    def test_the_other_two_clauses_come_with_it(self, builder):
        """Untap and haste were already expressible; the point of asserting them
        is that the printed line is one sentence and now works end to end."""
        game, victim = position(builder)
        game.state.objects[victim].tapped = True
        cast_at(game, TREASON, victim)
        assert not game.state.objects[victim].tapped
        assert "haste" in chars(game.state, victim).keywords

    def test_the_owner_is_untouched(self, builder):
        """400.3: control moves, ownership does not, so the card still goes home
        when it dies."""
        game, victim = position(builder)
        cast_at(game, TREASON, victim)
        assert game.state.objects[victim].owner == 1


class TestTheHandback:
    def test_it_goes_back_at_cleanup(self, builder):
        game, victim = position(builder)
        cast_at(game, TREASON, victim)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.objects[victim].controller == 1

    def test_the_anthem_stops_reaching_it(self, builder):
        """`bump_chars` on the way back. Without it the returned creature keeps
        the thief's anthem until something unrelated invalidates the cache."""
        game, victim = position(builder)
        cast_at(game, TREASON, victim)
        assert chars(game.state, victim).power == 3
        pass_until(game, lambda g: g.state.turn >= 2)
        assert chars(game.state, victim).power == 2

    def test_the_haste_goes_with_it(self, builder):
        game, victim = position(builder)
        cast_at(game, TREASON, victim)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert "haste" not in chars(game.state, victim).keywords

    def test_a_permanent_steal_does_not_come_back(self, builder):
        """The default is unchanged, so no shipped card moved: Captivating
        Vampire keeps what it takes."""
        game = (
            builder(players=2)
            .hand(0, [STEAL])
            .battlefield(0, ["island"] * 4)
            .battlefield(1, [BEAR])
            .build()
        )
        victim = only_oid(game, BEAR, 1)
        cast_at(game, STEAL, victim)
        assert game.state.objects[victim].until_eot == []
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.objects[victim].controller == 0


class TestTheThreeRulesOnTheWayBack:
    def test_it_is_summoning_sick_for_the_player_getting_it_back(self, builder):
        """302.6. `entered_turn` is stamped with the turn the handback happened
        in, *not* restored to what it was before the steal — the creature has
        not been under its original controller continuously since their turn
        began, because the thief had it in between."""
        game, victim = position(builder)
        obj = game.state.objects[victim]
        obj.entered_turn = 0  # been there all game, not sick for anybody
        change_control(game.state, victim, 0, duration="until_end_of_turn")
        clear_until_eot(game.state)
        assert obj.controller == 1
        assert obj.entered_turn == game.state.turn
        assert obj.summoning_sick(game.state.turn), (
            "restoring the pre-steal entered_turn would make it 0 and unsick"
        )

    def test_it_is_removed_from_combat(self, builder):
        """506.4, asserted against the primitive: the cleanup step runs with
        `state.combat` already `None`, so this is the branch that keeps the rule
        true for any turn structure that ever changes that."""
        game, victim = position(builder)
        change_control(game.state, victim, 0, duration="until_end_of_turn")
        game.state.combat = CombatState(declaring_player=0)
        game.state.combat.attackers[victim] = TargetRef.player(1)
        clear_until_eot(game.state)
        assert victim in game.state.combat.removed

    def test_the_characteristics_cache_is_dropped(self, builder):
        """The one a bare `obj.controller = previous` loses outright."""
        game, victim = position(builder)
        change_control(game.state, victim, 0, duration="until_end_of_turn")
        assert chars(game.state, victim).power == 3
        clear_until_eot(game.state)
        assert chars(game.state, victim).power == 2

    def test_the_handback_is_announced(self, builder):
        """`control_changed` exists because no zone change happens; a log built
        from zone changes alone would show the creature swapping sides twice in
        silence."""
        game, victim = position(builder)
        change_control(game.state, victim, 0, duration="until_end_of_turn")
        before = len(game.state.events)
        clear_until_eot(game.state)
        moves = [e for e in game.state.events[before:] if e.type == "control_changed"]
        assert [(e.data["from"], e.data["to"]) for e in moves] == [(0, 1)]


class TestWhichHandback:
    def test_a_permanent_that_left_is_not_resurrected(self, builder):
        """`reset_permanent_state` empties `until_eot` on the way out, so the
        entry is gone before cleanup ever looks. Act of Treason plus a sacrifice
        outlet is a real line and the creature does not come home."""
        game, victim = position(builder)
        cast_at(game, TREASON, victim)
        move_object(game.state, victim, Zone.GRAVEYARD)
        assert game.state.objects[victim].until_eot == []
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.objects[victim].zone is Zone.GRAVEYARD

    def test_two_steals_unwind_newest_first(self, builder):
        """Both effects end in the same step. Undone oldest-first the first
        handback would find the wrong controller and give up, leaving the
        permanent one seat away from home."""
        game = (
            builder(players=3)
            .battlefield(0, [BEAR])
            .build()
        )
        victim = only_oid(game, BEAR, 0)
        change_control(game.state, victim, 1, duration="until_end_of_turn")
        change_control(game.state, victim, 2, duration="until_end_of_turn")
        clear_until_eot(game.state)
        assert game.state.objects[victim].controller == 0

    def test_a_later_permanent_steal_outlives_it(self, builder):
        """The stored seat is validated, not trusted: a permanent control
        change made afterwards is a continuous effect that has not ended, and
        handing the permanent to the original controller would end somebody
        else's card for them."""
        game = (
            builder(players=3)
            .battlefield(0, [BEAR])
            .build()
        )
        victim = only_oid(game, BEAR, 0)
        change_control(game.state, victim, 1, duration="until_end_of_turn")
        change_control(game.state, victim, 2)
        clear_until_eot(game.state)
        assert game.state.objects[victim].controller == 2

    def test_stealing_what_you_already_control_records_nothing(self, builder):
        """A no-op steal is not a control change, so there is nothing to end.
        Recorded, it would invent a handback at cleanup that no card asked for."""
        game, victim = position(builder)
        assert not change_control(game.state, victim, 1, duration="until_end_of_turn")
        assert game.state.objects[victim].until_eot == []

    def test_a_seat_that_left_the_game_gets_nothing_back(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, [BEAR])
            .build()
        )
        victim = only_oid(game, BEAR, 0)
        change_control(game.state, victim, 1, duration="until_end_of_turn")
        game.state.players[0].has_lost = True
        clear_until_eot(game.state)
        assert game.state.objects[victim].controller == 1


class TestTheLoaderGuardsTheDuration:
    def base(self, duration) -> dict:
        effect: dict = {"op": "gain_control", "objects": {"target": "t1"}}
        if duration is not None:
            effect["duration"] = duration
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{R}",
            "types": ["Sorcery"],
            "targets": [
                {
                    "id": "t1",
                    "kind": "permanent",
                    "count": 1,
                    "selector": {"types": ["Creature"], "zone": "battlefield"},
                }
            ],
            "spell_effects": [effect],
        }

    def test_a_misspelled_duration_is_still_refused(self):
        """The old guard's reason survives the feature: a `duration` the engine
        does not read is a permanent steal wearing Act of Treason's text."""
        with pytest.raises(DslError, match="unknown gain_control duration"):
            compile_card(CardModel.model_validate(self.base("eot")))

    def test_both_spellings_compile(self):
        for duration in (None, "permanent", "until_end_of_turn"):
            compile_card(CardModel.model_validate(self.base(duration)))

    def test_gain_control_still_needs_objects(self):
        card = self.base("until_end_of_turn")
        del card["spell_effects"][0]["objects"]
        with pytest.raises(DslError, match="gain_control needs 'objects'"):
            compile_card(CardModel.model_validate(card))

    def test_the_treason_card_compiles(self, registry):
        card = registry.get(TREASON)
        assert [e["op"] for e in card.spell_effects] == [
            "gain_control",
            "untap",
            "grant_keyword",
        ]
        assert card.spell_effects[0]["duration"] == "until_end_of_turn"


class TestTheShippedCard:
    def test_zealous_conscripts_steals_and_gives_back(self, real_registry):
        """The card the gap record named, played through the real registry."""
        from automtg.engine.sandbox import GameBuilder

        game = (
            GameBuilder(real_registry, players=2, seed=0)
            .hand(0, ["zealous_conscripts"])
            .battlefield(0, ["mountain"] * 5)
            .battlefield(1, ["zealous_conscripts"])
            .build()
        )
        victim = only_oid(game, "zealous_conscripts", 1)
        game.state.objects[victim].tapped = True
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == "zealous_conscripts"
            )
        )
        # The ETB targets *any* permanent, so the choice has to be made rather
        # than defaulted: "target permanent" includes your own Mountains, which
        # is the Kiki-Jiki half of the card and not the half under test.
        for _ in range(30):
            if not game.state.stack and not game.state.pending_triggers:
                break
            decision = game.pending()
            if decision is None:
                game._advance()
                continue
            aimed = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and TargetRef.obj(victim) in a.targets
                ),
                None,
            )
            game.apply(aimed if aimed is not None else _default_answer(game, decision))
        assert game.state.objects[victim].controller == 0
        assert not game.state.objects[victim].tapped
        assert "haste" in chars(game.state, victim).keywords
        pass_until(
            game,
            lambda g: g.state.turn >= 2 and g.state.step >= Step.PRECOMBAT_MAIN,
        )
        assert game.state.objects[victim].controller == 1
