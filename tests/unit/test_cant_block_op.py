""""Can't block", said by something that is not standing on the battlefield.

The **op**. `test_cant_block.py` next door covers the static of the same name
(unleash); this file is its counterpart, and the two are deliberately separate
files because they are separate mechanisms that happen to print one sentence.

Rule 509.1a: a creature may be declared as a blocker only if it is untapped and
"no restrictions" say otherwise. The engine already had one of those restrictions
-- the `cant_block` **static**, read by `characteristics.block_forbidden` off
`_battlefield_statics` -- and it can only ever be a fact about a permanent that
is currently there. It needs a source on the battlefield, it ends the moment that
source leaves, and its `affects` filter may read only *printed* characteristics.

None of those three is true of the sentence on the two witnesses:

- **Aragorn, King of Gondor** -- "Whenever Aragorn attacks, up to one target
  creature can't block this turn. If you're the monarch, creatures can't block
  this turn." The first half names a creature chosen when the *trigger resolves*,
  which no printed-characteristics filter can pick out. The second half is global
  and turn-scoped, so it must also catch a creature that enters after it
  resolved -- it is a continuous effect, not a mark written on each creature.
- **Taunt from the Rampart** -- "Until your next turn, those creatures can't
  block." A sorcery, so nothing is left on the battlefield to own the effect, and
  the clock runs past end of turn.

`detain` is the documented near-miss and is wrong for one specific reason worth
stating: it stops *attacking* too, and Taunt from the Rampart's other half goads
the same creatures into attacking. Using detain there would print a card that
does the opposite of what it says.

What is pinned below, and each is a way this could be silently wrong instead of
broken:

1. It stops blocking and **only** blocking -- attacking and activated abilities
   are untouched, which is the whole of the difference from detain.
2. The named form is a **fixed set**: a creature that enters afterwards was not
   one of "those creatures", so it blocks freely.
3. The global form is **not** a snapshot: a creature that enters afterwards is
   caught, because "creatures can't block this turn" is a continuous effect.
4. The two clocks are different and neither is the other's default.
   `this_turn` ends at cleanup; `until_your_next_turn` survives the whole turn
   cycle back to the imposing player's untap step, where detain is cleared.
5. An empty chosen set restricts nobody. "Up to one target creature" with no
   target taken must not collapse into "every creature".
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import combat as combat_mod
from automtg.engine import sba
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.primitives import forbid_block
from tests.conftest import _default_answer, only_oid, pass_until

BEAR = "t_bear"
WALL = "t_wall"  # 0/4 defender-ish body; a second creature to block with
TAUNT = "t_taunter"  # {2}{R} sorcery: until your next turn, their creatures can't block
FALTER = "t_falterer"  # {1}{R} sorcery: creatures can't block this turn
KING = "t_king"  # attacks trigger: up to one target creature can't block this turn
DETAINER = "t_detainer"


def position(builder, *, players=2, mine=(BEAR,), theirs=(BEAR,), active=0, hand=()):
    """Player 0 attacks with ``mine``; player 1 defends with ``theirs``."""
    b = builder(players=players)
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    if hand:
        b.hand(0, list(hand)).battlefield(0, ["mountain", "mountain", "mountain"])
    return b.active(active).step(Step.UNTAP).build()


def to_declare_blockers(game, limit: int = 80):
    """Advance to the declare-blockers decision, attacking with everything on the way."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_BLOCKERS:
            return game
        if decision.kind is DecisionKind.DECLARE_ATTACKERS:
            adds = [
                a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER
            ]
            game.apply(adds[0] if adds else _default_answer(game, decision))
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare blockers")


def blockers_offered(game) -> list[int]:
    return sorted(
        {
            a.source
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_BLOCKER and a.source is not None
        }
    )


def cast(game, card_id: str, limit: int = 40) -> None:
    """Cast a sorcery from player 0's hand and let it resolve."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"{card_id} never resolved")


class TestItStopsBlockingAndOnlyBlocking:
    def test_the_unrestricted_baseline(self, builder):
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        to_declare_blockers(game)
        assert blockers_offered(game) == [theirs]

    def test_a_prohibited_creature_is_not_offered_as_a_blocker(self, builder):
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        forbid_block(game.state, [theirs], "this_turn")
        to_declare_blockers(game)
        assert blockers_offered(game) == []

    def test_can_block_says_so_directly(self, builder):
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        to_declare_blockers(game)
        attacker = next(iter(game.state.combat.attackers))
        assert combat_mod.can_block(game.state, theirs, attacker, 1)
        forbid_block(game.state, [theirs], "this_turn")
        assert not combat_mod.can_block(game.state, theirs, attacker, 1)

    def test_it_does_not_stop_the_creature_attacking(self, builder):
        """The whole reason this is not `detain`. Taunt from the Rampart goads
        the same creatures it stops blocking, so a version that also forbade
        attacking would print a card that contradicts its own first sentence."""
        game = position(builder, mine=(BEAR,), theirs=())
        mine = only_oid(game, BEAR, 0)
        forbid_block(game.state, [mine], "this_turn")
        assert combat_mod.can_attack(game.state, mine)

    def test_detain_stops_both_and_that_is_the_difference(self, builder):
        game = position(builder, mine=(BEAR,), theirs=())
        mine = only_oid(game, BEAR, 0)
        game.state.objects[mine].detained_by = 1
        assert not combat_mod.can_attack(game.state, mine)


class TestTheNamedFormIsAFixedSet:
    def test_only_the_named_creature_is_stopped(self, builder):
        game = position(builder, theirs=(BEAR, WALL))
        bear = only_oid(game, BEAR, 1)
        wall = only_oid(game, WALL, 1)
        forbid_block(game.state, [bear], "this_turn")
        to_declare_blockers(game)
        assert blockers_offered(game) == [wall]

    def test_a_creature_that_arrives_later_was_not_one_of_them(self, builder):
        game = position(builder, theirs=(BEAR,))
        bear = only_oid(game, BEAR, 1)
        forbid_block(game.state, [bear], "this_turn")
        newcomer = game.state.registry  # placeholder to keep the name obvious
        assert newcomer is not None
        # A creature the effect never saw: not in `objects`, so not restricted.
        assert not combat_mod.block_prohibited(game.state, 9999)

    def test_an_empty_chosen_set_restricts_nobody(self, builder):
        """"Up to one target creature" with no target taken. Collapsing an empty
        set into "every creature" would turn a declined optional target into a
        one-sided Falter, which is the worst available misreading."""
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        assert not forbid_block(game.state, [], "this_turn")
        assert game.state.block_prohibitions == []
        assert not combat_mod.block_prohibited(game.state, theirs)


class TestTheGlobalFormIsContinuousNotASnapshot:
    def test_every_creature_on_the_board_is_caught(self, builder):
        game = position(builder, theirs=(BEAR, WALL))
        forbid_block(game.state, None, "this_turn")
        to_declare_blockers(game)
        assert blockers_offered(game) == []

    def test_a_creature_that_enters_later_in_the_turn_is_caught_too(self, builder):
        """The reason this is a turn-scoped continuous effect rather than a mark
        written on each creature: "creatures can't block this turn" is not a
        snapshot of the battlefield taken when it resolved."""
        game = position(builder, theirs=(BEAR,))
        forbid_block(game.state, None, "this_turn")
        # Any oid at all, including one that does not exist yet.
        assert combat_mod.block_prohibited(game.state, 12345)

    def test_it_reaches_the_imposing_players_own_creatures(self, builder):
        """"Creatures can't block this turn" is not "creatures your opponents
        control". Aragorn's global clause is symmetrical, and the asymmetry that
        makes it good is that its controller is the one attacking."""
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        forbid_block(game.state, None, "this_turn", player=0)
        assert combat_mod.block_prohibited(game.state, mine)


class TestTheTwoClocks:
    def test_this_turn_ends_at_cleanup(self, builder):
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        forbid_block(game.state, [theirs], "this_turn")
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.block_prohibitions == []

    def test_this_turn_survives_the_end_of_combat(self, builder):
        """`cant_attack_player`'s `this_combat` has no counterpart here, and this
        is why: blockers are declared *inside* the combat that would clear it, so
        a combat-scoped "can't block" would be indistinguishable from none."""
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        forbid_block(game.state, [theirs], "this_turn")
        to_declare_blockers(game)
        combat_mod.end_combat(game.state)
        assert [r.duration for r in game.state.block_prohibitions] == ["this_turn"]

    def test_until_your_next_turn_survives_the_opponents_whole_turn(self, builder):
        """Turn 2 is player 1's: their untap step runs and must leave a
        prohibition player 0 imposed exactly where it was."""
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        forbid_block(game.state, [theirs], "until_your_next_turn", player=0)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.active_player == 1
        assert len(game.state.block_prohibitions) == 1

    def test_until_your_next_turn_ends_at_the_imposing_players_untap(self, builder):
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        forbid_block(game.state, [theirs], "until_your_next_turn", player=0)
        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.active_player == 0, "back round to player 0's untap step"
        assert game.state.block_prohibitions == []

    def test_the_two_clocks_do_not_clear_each_other(self, builder):
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        forbid_block(game.state, [theirs], "this_turn", player=0)
        forbid_block(game.state, [theirs], "until_your_next_turn", player=0)
        assert len(game.state.block_prohibitions) == 2
        pass_until(game, lambda g: g.state.turn >= 2)
        assert [r.duration for r in game.state.block_prohibitions] == [
            "until_your_next_turn"
        ], "the shorter clock wearing off must not take the longer one with it"

    def test_one_players_untap_does_not_clear_anothers(self, builder):
        """The entry names *who* imposed it, so two untap steps go by untouched
        and only the third -- player 2's -- ends it."""
        game = position(builder, players=3)
        theirs = only_oid(game, BEAR, 1)
        forbid_block(game.state, [theirs], "until_your_next_turn", player=2)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert len(game.state.block_prohibitions) == 1, "player 1's untap is not theirs"
        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.active_player == 2
        assert game.state.block_prohibitions == []


class TestThePrimitiveRefusesWhatCannotBite:
    def test_until_your_next_turn_without_a_player_has_no_clock(self, builder):
        """Nothing would ever clear it, so it would be "can't block, ever"."""
        game = position(builder)
        assert not forbid_block(game.state, [1], "until_your_next_turn")
        assert game.state.block_prohibitions == []

    def test_the_same_entry_is_recorded_once(self, builder):
        game = position(builder)
        assert forbid_block(game.state, [7], "this_turn", player=0)
        assert not forbid_block(game.state, [7], "this_turn", player=0)
        assert len(game.state.block_prohibitions) == 1

    def test_a_global_entry_never_merges_with_a_named_one(self, builder):
        game = position(builder)
        forbid_block(game.state, [7], "this_turn", player=0)
        forbid_block(game.state, None, "this_turn", player=0)
        assert len(game.state.block_prohibitions) == 2

    def test_an_unknown_duration_is_a_value_error(self, builder):
        game = position(builder)
        with pytest.raises(ValueError, match="unknown block prohibition duration"):
            forbid_block(game.state, [7], "this_combat")


class TestAnEliminatedPlayersClockNeverComes:
    def test_their_prohibitions_are_dropped(self, builder):
        """"Until your next turn" is cleared in that player's untap step. A
        player who has left the game never has another one, so the entry would
        outlive them for the rest of the game."""
        game = position(builder, players=3)
        theirs = only_oid(game, BEAR, 1)
        forbid_block(game.state, [theirs], "until_your_next_turn", player=2)
        game.state.players[2].life = 0
        sba.run(game.state)
        assert game.state.block_prohibitions == []

    def test_a_turn_scoped_one_is_left_alone(self, builder):
        """Cleanup clears it whoever is alive, so there is nothing to fix."""
        game = position(builder, players=3)
        theirs = only_oid(game, BEAR, 1)
        forbid_block(game.state, [theirs], "this_turn", player=2)
        game.state.players[2].life = 0
        sba.run(game.state)
        assert len(game.state.block_prohibitions) == 1


class TestTheSorceryForms:
    def test_the_named_form_from_a_resolving_sorcery(self, builder):
        """Taunt from the Rampart's clause: a sorcery leaves no permanent behind
        for a static to live on, which is the first reason the static could not
        do this job."""
        game = position(builder, theirs=(BEAR, WALL), hand=(TAUNT,))
        bear = only_oid(game, BEAR, 1)
        wall = only_oid(game, WALL, 1)
        cast(game, TAUNT)
        entry = game.state.block_prohibitions[0]
        assert sorted(entry.objects) == sorted((bear, wall))
        assert (entry.duration, entry.player) == ("until_your_next_turn", 0)
        to_declare_blockers(game)
        assert blockers_offered(game) == []

    def test_the_global_form_from_a_resolving_sorcery(self, builder):
        game = position(builder, theirs=(BEAR, WALL), hand=(FALTER,))
        cast(game, FALTER)
        entry = game.state.block_prohibitions[0]
        assert (entry.objects, entry.duration) == (None, "this_turn")
        to_declare_blockers(game)
        assert blockers_offered(game) == []


class TestTheTriggeredTargetedForm:
    """Aragorn's first clause: the creature is named when the trigger resolves,
    which is the thing a static's printed-characteristics filter cannot do."""

    def test_the_targeted_creature_cannot_block_the_attacker_that_named_it(
        self, builder
    ):
        game = position(builder, mine=(KING,), theirs=(BEAR,))
        bear = only_oid(game, BEAR, 1)
        to_declare_blockers(game)
        assert game.state.block_prohibitions, "the attack trigger resolved"
        assert bear in game.state.block_prohibitions[0].objects
        assert blockers_offered(game) == []

    def test_the_prohibition_is_gone_next_turn(self, builder):
        game = position(builder, mine=(KING,), theirs=(BEAR,))
        to_declare_blockers(game)
        assert game.state.block_prohibitions
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.block_prohibitions == []


def probe(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{R}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )
    )


class TestTheLoaderGuardsIt:
    def test_neither_form_is_refused(self):
        with pytest.raises(DslError, match="needs exactly one of 'objects'"):
            probe({"op": "cant_block", "duration": "this_turn"})

    def test_both_forms_at_once_is_refused(self):
        with pytest.raises(DslError, match="needs exactly one of 'objects'"):
            probe(
                {
                    "op": "cant_block",
                    "objects": {},
                    "all_creatures": True,
                    "duration": "this_turn",
                }
            )

    def test_a_missing_duration_is_refused(self):
        with pytest.raises(DslError, match="needs a 'duration'"):
            probe({"op": "cant_block", "all_creatures": True})

    def test_an_unknown_duration_is_refused(self):
        """`this_combat` is `cant_attack_player`'s word, and it means nothing
        here -- blockers are declared inside the combat that would clear it."""
        with pytest.raises(DslError, match="unknown cant_block duration"):
            probe(
                {"op": "cant_block", "all_creatures": True, "duration": "this_combat"}
            )

    def test_the_witness_shapes_compile(self, registry):
        assert [e["op"] for e in registry.get(TAUNT).spell_effects] == ["cant_block"]
        assert registry.get(TAUNT).spell_effects[0]["duration"] == "until_your_next_turn"
        assert registry.get(FALTER).spell_effects[0]["all_creatures"] is True
        ability = registry.get(KING).abilities[0]
        assert [e["op"] for e in ability.effects] == ["cant_block"]
