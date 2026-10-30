"""Decayed (702.147) -- a keyword that is two rules, and a word other cards read.

    "Decayed (It can't block. When it attacks, sacrifice it at end of combat.)"
                                        -- the Zombie token `zombie_2_2_b_decayed`

    "At the beginning of your end step, if you control no creatures with
    decayed, create a 2/2 black Zombie creature token with decayed."
                                        -- Jadar, Ghoulcaller of Nephalia

702.147a makes decayed a static ability ("can't block") and a triggered one
("when it attacks, sacrifice it at end of combat"). Without the keyword the
pair could be written as a `cant_block` static and a printed attack trigger,
and that card plays the same -- but it is not a creature *with decayed*, so
Jadar's intervening-if would never see it and Jadar would make a Zombie every
end step instead of one at a time. So the word is a `Keyword`, read on derived
characteristics: `combat.can_block` refuses it as a blocker, and
`carddef.DECAYED_TRIGGER` -- exalted's shape -- schedules the sacrifice with a
`delay` at `end_of_combat`.

Where the sacrifice lands is the substance. "At end of combat" is after combat
damage (511.1), so the Zombie hits first; a substitute timing at the end step
would leave it alive through the postcombat main phase. And it is a real
sacrifice, so a "whenever you sacrifice" watcher hears it.

The rules points, each with a test:

- a decayed creature can't block, and a granted decayed counts too;
- an attacking decayed creature deals its combat damage, then is sacrificed in
  the end of combat step -- not before damage, not at the end step;
- a decayed creature that did not attack stays, and so does one put onto the
  battlefield attacking (508.4: it never attacked);
- the sacrifice fires `sacrificed`, which a watcher triggers on;
- Jadar's condition, written as `exists` over a `keywords` filter, sees it.
"""

from __future__ import annotations

from commanderblitz.engine.effects.conditions import evaluate_condition, validate_condition
from commanderblitz.engine.enums import ActionKind, DecisionKind, Keyword, Step
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import create_token, grant_keyword
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, keywords, oids_of, only_oid, pass_until, settle

ZOMBIE = "zombie_2_2_b_decayed"  # the token: 2/2 black Zombie with decayed
PLAIN_ZOMBIE = "zombie_2_2_b"  # its near miss: the same body, no decayed
BEAR = "t_bear"  # 2/2, no abilities
BATS = "t_bats"  # "Whenever you create or sacrifice a token, each opponent loses 1 life."
BOLT = "t_bolt"  # {R} instant, so priority genuinely stops in each step

#: Jadar's intervening-if, exactly as an author writes it.
NO_DECAYED = {
    "not": {
        "exists": {
            "zone": "battlefield",
            "controller": "you",
            "types": ["Creature"],
            "keywords": ["decayed"],
        }
    }
}


def position(builder, mine=(ZOMBIE,), theirs=()):
    """Player 0's ``mine`` facing player 1's ``theirs``, in a main phase that stops."""
    return (
        builder(players=2)
        .battlefield(0, ["mountain", *mine])
        .hand(0, [BOLT])
        .battlefield(1, ["mountain", *theirs])
        .hand(1, [BOLT])
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def to_declare(game, kind: DecisionKind) -> None:
    pass_until(game, lambda g: g.pending() is not None and g.pending().kind is kind)


def attack(game, *oids: int) -> None:
    to_declare(game, DecisionKind.DECLARE_ATTACKERS)
    for oid in oids:
        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),))
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def blockers_offered(game) -> set[int]:
    return {a.source for a in game.legal_actions() if a.kind is ActionKind.ADD_BLOCKER}


def to_postcombat(game) -> None:
    pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)


def first(game, event_type: EventType, oid: int | None = None):
    for event in game.state.events:
        if event.type == event_type and (oid is None or event.data.get("oid") == oid):
            return event
    return None


class TestItCantBlock:
    def test_a_decayed_creature_is_not_offered_as_a_blocker(self, builder):
        game = position(builder, mine=(BEAR,), theirs=(ZOMBIE,))
        bear, zombie = only_oid(game, BEAR, 0), only_oid(game, ZOMBIE, 1)
        attack(game, bear)
        to_declare(game, DecisionKind.DECLARE_BLOCKERS)
        assert zombie not in blockers_offered(game)

    def test_the_plain_zombie_still_blocks(self, builder):
        """The near miss, and the proof the refusal is the keyword's and not the body's."""
        game = position(builder, mine=(BEAR,), theirs=(PLAIN_ZOMBIE,))
        bear, zombie = only_oid(game, BEAR, 0), only_oid(game, PLAIN_ZOMBIE, 1)
        attack(game, bear)
        to_declare(game, DecisionKind.DECLARE_BLOCKERS)
        assert zombie in blockers_offered(game)

    def test_a_granted_decayed_cant_block_either(self, builder):
        """Read off derived keywords, so a grant is the keyword."""
        game = position(builder, mine=(BEAR,), theirs=(BEAR,))
        attacker, blocker = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        grant_keyword(game.state, blocker, Keyword.DECAYED.value, permanent=True)
        assert "decayed" in keywords(game, blocker)
        attack(game, attacker)
        to_declare(game, DecisionKind.DECLARE_BLOCKERS)
        assert blocker not in blockers_offered(game)

    def test_it_may_still_attack(self, builder):
        game = position(builder)
        zombie = only_oid(game, ZOMBIE, 0)
        to_declare(game, DecisionKind.DECLARE_ATTACKERS)
        assert any(
            a.kind is ActionKind.ADD_ATTACKER and a.source == zombie for a in game.legal_actions()
        )


class TestItIsSacrificedAtEndOfCombat:
    def test_it_is_gone_by_the_postcombat_main_phase(self, builder):
        game = position(builder)
        attack(game, only_oid(game, ZOMBIE, 0))
        to_postcombat(game)
        assert oids_of(game, ZOMBIE, 0) == []

    def test_it_deals_its_combat_damage_first(self, builder):
        """511.1: end of combat comes after the damage step, so the hit is real."""
        game = position(builder)
        life = game.state.players[1].life
        attack(game, only_oid(game, ZOMBIE, 0))
        to_postcombat(game)
        assert game.state.players[1].life == life - 2

    def test_it_is_still_there_in_the_combat_damage_step(self, builder):
        """Not before damage: the trigger schedules the sacrifice, it does not perform it."""
        game = position(builder)
        zombie = only_oid(game, ZOMBIE, 0)
        attack(game, zombie)
        pass_until(game, lambda g: g.state.step is Step.COMBAT_DAMAGE)
        assert oids_of(game, ZOMBIE, 0) == [zombie]

    def test_the_sacrifice_happens_in_the_end_of_combat_step(self, builder):
        game = position(builder)
        zombie = only_oid(game, ZOMBIE, 0)
        attack(game, zombie)
        to_postcombat(game)
        damage = first(game, EventType.COMBAT_DAMAGE_TO_PLAYER)
        sacrifice = first(game, EventType.SACRIFICED, zombie)
        assert damage is not None and sacrifice is not None
        assert sacrifice.step == Step.END_OF_COMBAT
        assert game.state.events.index(damage) < game.state.events.index(sacrifice)

    def test_a_decayed_creature_that_did_not_attack_stays(self, builder):
        game = position(builder, mine=(ZOMBIE, BEAR))
        zombie, bear = only_oid(game, ZOMBIE, 0), only_oid(game, BEAR, 0)
        attack(game, bear)
        to_postcombat(game)
        assert oids_of(game, ZOMBIE, 0) == [zombie]
        assert first(game, EventType.SACRIFICED) is None

    def test_a_creature_without_decayed_is_not_sacrificed(self, builder):
        game = position(builder, mine=(PLAIN_ZOMBIE,))
        zombie = only_oid(game, PLAIN_ZOMBIE, 0)
        attack(game, zombie)
        to_postcombat(game)
        assert oids_of(game, PLAIN_ZOMBIE, 0) == [zombie]

    def test_one_put_onto_the_battlefield_attacking_is_not_sacrificed(self, builder):
        """508.4: it never attacked, so "when it attacks" never triggered."""
        game = position(builder, mine=(BEAR,))
        attack(game, only_oid(game, BEAR, 0))
        zombie = create_token(game.state, ZOMBIE, 0, 1, attacking=1)[0]
        assert game.state.combat is not None and game.state.combat.attacking(zombie)
        to_postcombat(game)
        assert oids_of(game, ZOMBIE, 0) == [zombie]

    def test_a_granted_decayed_is_sacrificed_too(self, builder):
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        grant_keyword(game.state, bear, Keyword.DECAYED.value, permanent=True)
        attack(game, bear)
        to_postcombat(game)
        assert oids_of(game, BEAR, 0) == []


class TestTheSacrificeIsASacrifice:
    def test_a_sacrifice_watcher_triggers(self, builder):
        """The Bats drain on "whenever you sacrifice a token": 2 combat, then 1 more.

        The Zombie is *created* here rather than placed, because the watcher's
        filter is `is_token` and only `create_token` makes a token. Backdated
        the way `GameBuilder.battlefield` backdates what it places, so it may
        attack this turn.
        """
        game = position(builder, mine=(BATS,))
        zombie = create_token(game.state, ZOMBIE, 0, 1)[0]
        game.state.objects[zombie].entered_turn = game.state.turn - 1
        settle(game)
        life = game.state.players[1].life
        attack(game, zombie)
        to_postcombat(game)
        settle(game)
        sacrificed = first(game, EventType.SACRIFICED, zombie)
        assert sacrificed is not None and sacrificed.player == 0
        assert game.state.players[1].life == life - 3


class TestJadarsCondition:
    """ "If you control no creatures with decayed" is `not exists` over `keywords`."""

    def test_the_condition_loads(self):
        validate_condition(NO_DECAYED, "jadar")

    def test_a_decayed_zombie_fails_it(self, builder):
        game = position(builder)
        assert not evaluate_condition(game.state, NO_DECAYED, controller=0)

    def test_the_plain_zombie_does_not(self, builder):
        """Why the near miss would make Jadar a Zombie every end step."""
        game = position(builder, mine=(PLAIN_ZOMBIE,))
        assert evaluate_condition(game.state, NO_DECAYED, controller=0)

    def test_an_opponents_decayed_zombie_does_not(self, builder):
        game = position(builder, mine=(), theirs=(ZOMBIE,))
        assert evaluate_condition(game.state, NO_DECAYED, controller=0)
