"""``choose_blockers`` — the defender's declaration, made by somebody else.

    Odric, Master Tactician — "Whenever Odric and at least three other creatures
    attack, you choose which creatures block this combat and how those creatures
    block."

Nothing in the combat-flag family can say this, and the reason is not breadth but
*kind*. `must_block` and `cant_block` each constrain **one** creature and leave
the defender free everywhere else: the defender could still add blockers the
effect never named, and "and **how** those creatures block" — which attacker each
blocker is assigned to — has no spelling at all in a per-creature requirement.
`block_restriction`'s filter says only what may not block a given attacker.

So what moves is the **decision**, not the creatures. Underneath,
`turn._next_blocker_decision` unconditionally issued
`PendingDecision(kind=DECLARE_BLOCKERS, player=pid)` to each seat in
`combat.pending_blockers`, with no way to reassign it.

The design that makes this safe is the split between *who is asked* and *whose
declaration it is*. `PendingDecision.on_behalf_of` names the second, and
`decision.subject` resolves it, so every legality check goes on reading the
defender exactly as it did when the defender answered for themselves:
`legal_blocks` offers the defender's creatures, `add_blocker` validates against
them, and `blocks_valid` / `unmet_block_requirements` still hold the defender to
their own menace and lures. **A stolen declaration is exactly as legal as the
defender's own would have been** — Odric may choose badly but not illegally,
which is the printed card. `TestTheRulesStillBind` is that claim.

Recorded on `CombatState` rather than on a player, because "this combat" is the
printed duration: it dies with `state.combat`, needs no clock of its own, and a
second combat granted the same turn correctly begins free of it.

Witness: Odric, Master Tactician
(`odric_master_tactician` in `data/cards/auto/`).
"""

from __future__ import annotations

from automtg.engine.combat import add_attacker, add_blocker, legal_blocks, start_combat
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import _default_answer, only_oid

TACTICIAN = "t_tactician"  # the battalion-conditioned printed card
NOW = "t_tactician_now"  # the same takeover on a bare attacks trigger
MENACER = "t_menacer"  # menace, so the defender's requirements can be tested
BEAR = "t_bear"  # 2/2 vanilla
SQUIRE = "t_small"  # 1/1 vanilla
PLAINS = "plains"


def board(builder, mine, theirs):
    game = (
        builder(players=2)
        .battlefield(0, [PLAINS] * 4 + list(mine))
        .battlefield(1, list(theirs))
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build(advance=False)
    )
    start_combat(game.state)
    return game


def take_over(game, controller=0):
    """Resolve the op as the attack trigger would."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    list(execute(ctx, [{"op": "choose_blockers", "player": "you"}]))


class TestTheDecisionMoves:
    def test_the_attacker_is_asked_instead_of_the_defender(self, builder):
        game = board(builder, [BEAR], [SQUIRE])
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        take_over(game)
        from automtg.engine.turn import _next_blocker_decision

        game.state.combat.pending_blockers = [1]
        _next_blocker_decision(game.state)
        decision = game.state.pending_decision

        assert decision.kind is DecisionKind.DECLARE_BLOCKERS
        assert decision.player == 0, "the attacker holds the prompt"
        assert decision.on_behalf_of == 1, "the declaration is still the defender's"
        assert decision.subject == 1

    def test_without_the_op_the_defender_is_asked(self, builder):
        """Pins that the reassignment is the op's and not the harness's."""
        game = board(builder, [BEAR], [SQUIRE])
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        from automtg.engine.turn import _next_blocker_decision

        game.state.combat.pending_blockers = [1]
        _next_blocker_decision(game.state)
        decision = game.state.pending_decision

        assert decision.player == 1
        assert decision.on_behalf_of is None
        assert decision.subject == 1

    def test_the_blocks_offered_are_still_the_defenders_creatures(self, builder):
        """The whole safety of the design. The attacker holds the prompt and is
        offered the *defender's* blockers, not their own."""
        game = board(builder, [BEAR, SQUIRE], [MENACER])
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        take_over(game)
        from automtg.engine.legality import _blocker_actions
        from automtg.engine.turn import _next_blocker_decision

        game.state.combat.pending_blockers = [1]
        _next_blocker_decision(game.state)
        offered = _blocker_actions(game.state, game.state.pending_decision.subject)
        sources = {a.source for a in offered if a.kind is ActionKind.ADD_BLOCKER}

        assert sources == {only_oid(game, MENACER, 1)}
        assert only_oid(game, SQUIRE, 0) not in sources


class TestTheRulesStillBind:
    """A stolen declaration is exactly as legal as the defender's own.

    Odric may choose badly; he may not choose illegally. Every check reads the
    defender through `decision.subject`, so none of them can tell the difference.
    """

    def test_menace_still_needs_two_blockers(self, builder):
        game = board(builder, [MENACER], [BEAR, SQUIRE])
        attacker = only_oid(game, MENACER, 0)
        add_attacker(game.state, attacker, 1)
        take_over(game)
        from automtg.engine.combat import blocks_valid

        add_blocker(game.state, only_oid(game, BEAR, 1), attacker, 1)
        assert blocks_valid(game.state, 1) is False, "one blocker cannot block menace"
        add_blocker(game.state, only_oid(game, SQUIRE, 1), attacker, 1)
        assert blocks_valid(game.state, 1) is True

    def test_legal_blocks_is_computed_for_the_defender(self, builder):
        game = board(builder, [BEAR], [SQUIRE])
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        take_over(game)

        pairs = list(legal_blocks(game.state, 1))
        assert {b for b, _ in pairs} == {only_oid(game, SQUIRE, 1)}


class TestItLastsExactlyOneCombat:
    def test_it_is_recorded_on_the_combat(self, builder):
        game = board(builder, [BEAR], [SQUIRE])
        take_over(game)
        assert game.state.combat.blocker_chooser == 0

    def test_a_fresh_combat_starts_free_of_it(self, builder):
        """"This combat" -- the record dies with `state.combat`, so an extra
        combat granted the same turn is the defender's own again."""
        game = board(builder, [BEAR], [SQUIRE])
        take_over(game)
        start_combat(game.state)
        assert game.state.combat.blocker_chooser is None

    def test_with_no_combat_the_op_is_inert(self, builder):
        """A trigger resolving outside combat must not crash or leave a record
        for the next one to inherit."""
        game = board(builder, [BEAR], [SQUIRE])
        game.state.combat = None
        take_over(game)
        assert game.state.combat is None


class TestThroughARealTurn:
    """The printed card, driven rather than poked: four attackers, and the
    defender is never asked to declare their own blocks."""

    def position(self, builder, tactician: str):
        return (
            builder(players=2)
            .battlefield(0, [PLAINS] * 4 + [tactician, BEAR, BEAR, BEAR])
            .battlefield(1, [SQUIRE])
            .library(0, [PLAINS] * 20)
            .library(1, [PLAINS] * 20)
            .active(0)
            .step(Step.UNTAP)
            .max_turns(2)
            .build()
        )

    def attack_with_everything(self, game, limit: int = 200):
        for _ in range(limit):
            decision = game.pending()
            if decision is None:
                break
            if decision.kind is DecisionKind.DECLARE_ATTACKERS:
                while True:
                    adds = [
                        a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER
                    ]
                    if not adds:
                        break
                    game.apply(adds[0])
                game.apply(
                    next(
                        a
                        for a in game.legal_actions()
                        if a.kind is ActionKind.FINISH_DECLARATION
                    )
                )
                return
            game.apply(_default_answer(game, decision))
        raise AssertionError("never reached declare attackers")

    def blockers_asked(self, game, limit: int = 200) -> set[int]:
        asked: set[int] = set()
        for _ in range(limit):
            decision = game.pending()
            if decision is None or game.state.step is Step.END_OF_COMBAT:
                break
            if decision.kind is DecisionKind.DECLARE_BLOCKERS:
                asked.add(decision.player)
            game.apply(_default_answer(game, decision))
        return asked

    def test_the_defender_is_never_asked(self, builder):
        game = self.position(builder, NOW)
        self.attack_with_everything(game)
        assert self.blockers_asked(game) == {0}

    def test_without_the_card_the_defender_is_asked(self, builder):
        game = self.position(builder, BEAR)
        self.attack_with_everything(game)
        assert self.blockers_asked(game) == {1}

    def test_the_battalion_condition_gates_it(self, builder):
        """The printed trigger needs Odric plus three others. With four
        attackers it fires, so the attacker declares."""
        game = self.position(builder, TACTICIAN)
        self.attack_with_everything(game)
        assert len(game.state.combat.attackers) >= 4
        assert self.blockers_asked(game) == {0}
