"""Provoke (702.38): a block *requirement*, the mirror of `must_attack`.

`docs/keywords.md` routes provoke this way and says why it was outstanding:
"`must_attack` exists for requirements; this is the block-requirement mirror,
which does not". The engine had exactly one shape for compelling a player in
combat, and it compelled the attacking one.

**It is a mirror, not the same op with a flag.** A block requirement always
names *what* to block -- "blocks this creature this combat if able" -- where an
attack requirement names nothing at all. So `must_block` records an oid on the
blocker rather than a duration, and the two expire on different clocks:
`must_attack` can outlive a turn (Trench Behemoth binds an opponent's *next*
combat), while a block requirement is scoped to the combat that placed it and
is spent when blockers lock in.

**"…if able" is the whole second half**, exactly as it is for attacking. A
requirement never makes an illegal block legal, so a creature that is tapped, or
that simply cannot block the attacker, owes nothing. That is not a footnote:
provoke *untaps* its victim first, and it does so precisely because a tapped
creature would otherwise be excused. The untap and the requirement are two
clauses and two ops here, which is also what leaves room for the lure family --
requirements without an untap.

**Enforced by withholding "Done blocking"**, the way menace and Tromokratis
already are, rather than by refusing to offer blocks. A declaration is legal or
not as a whole, and a player part-way through building one has not broken a
rule; they have not finished.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import combat as combat_mod
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until

PROVOKER = "t_provoker"  # 3/3, provoke
BEAR = "t_bear"  # 2/2
WALL = "t_wall"  # 0/4 defender


def to_attackers(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)


def to_blockers(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS)


def done(game):
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def can_finish(game) -> bool:
    return any(a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions())


def attack_and_provoke(game, attacker: int, victim: int | None):
    """Attack, then answer the provoke trigger's optional target."""
    to_attackers(game)
    game.apply(
        find_action(game, ActionKind.ADD_ATTACKER, source=attacker, targets=(TargetRef.player(1),))
    )
    done(game)
    # The trigger targets optionally; drive to the block declaration, choosing
    # the victim if one was asked for.
    for _ in range(40):
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        if decision.kind is DecisionKind.DECLARE_BLOCKERS:
            return
        actions = game.legal_actions()
        if victim is not None:
            wanted = [
                a
                for a in actions
                if a.kind is ActionKind.CHOOSE and TargetRef.obj(victim) in (a.targets or ())
            ]
            if wanted:
                game.apply(wanted[0])
                continue
        game.apply(actions[0])
    raise AssertionError("never reached the block declaration")


class TestTheRequirementIsRecorded:
    def test_the_provoked_creature_carries_the_attacker(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [PROVOKER])
            .battlefield(1, [BEAR])
            .build()
        )
        attacker = only_oid(game, PROVOKER, 0)
        victim = only_oid(game, BEAR, 1)
        attack_and_provoke(game, attacker, victim)
        assert game.state.objects[victim].must_block == attacker

    def test_it_untaps_the_victim_first(self, builder):
        """Why provoke untaps: "if able" would otherwise excuse a tapped
        creature, and the creature you most want to provoke just attacked."""
        game = (
            builder(players=2)
            .battlefield(0, [PROVOKER])
            .battlefield(1, [BEAR], tapped=True)
            .build()
        )
        attacker = only_oid(game, PROVOKER, 0)
        victim = only_oid(game, BEAR, 1)
        attack_and_provoke(game, attacker, victim)
        assert not game.state.objects[victim].tapped


class TestTheRequirementIsEnforced:
    def test_done_blocking_is_withheld_until_it_blocks(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [PROVOKER])
            .battlefield(1, [BEAR])
            .build()
        )
        attacker = only_oid(game, PROVOKER, 0)
        victim = only_oid(game, BEAR, 1)
        attack_and_provoke(game, attacker, victim)
        assert not can_finish(game), (
            "the provoked creature can block and is not blocking, so the "
            "declaration is not finishable"
        )
        game.apply(
            find_action(
                game, ActionKind.ADD_BLOCKER, source=victim, targets=(TargetRef.obj(attacker),)
            )
        )
        assert can_finish(game)

    def test_blocking_somebody_else_is_not_offered(self, builder):
        """Rule 509.1c, and where the mirror stops being a mirror.

        Attacking is not exclusive, so an attack requirement can be enforced by
        withholding "Done attacking" alone -- the creature can always be added.
        Blocking is exclusive. A provoked creature that blocks something else
        first cannot be retracted, `legal_blocks` then offers nothing, and the
        deadlock escape in `legality._blocker_actions` hands out "Done
        blocking" regardless. So the requirement narrows what is *offered*:
        while it is able to block the creature that provoked it, that is the
        only block it is offered.
        """
        game = (
            builder(players=2)
            .battlefield(0, [PROVOKER, BEAR])
            .battlefield(1, [BEAR])
            .build()
        )
        provoker = only_oid(game, PROVOKER, 0)
        other = only_oid(game, BEAR, 0)
        victim = only_oid(game, BEAR, 1)
        to_attackers(game)
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=provoker, targets=(TargetRef.player(1),)
            )
        )
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=other, targets=(TargetRef.player(1),)
            )
        )
        done(game)
        for _ in range(40):
            decision = game.pending()
            if decision is None:
                game._advance()
                continue
            if decision.kind is DecisionKind.DECLARE_BLOCKERS:
                break
            actions = game.legal_actions()
            wanted = [
                a
                for a in actions
                if a.kind is ActionKind.CHOOSE and TargetRef.obj(victim) in (a.targets or ())
            ]
            game.apply(wanted[0] if wanted else actions[0])
        offered = {
            (a.source, a.targets[0].id)
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_BLOCKER
        }
        assert (victim, provoker) in offered
        assert (victim, other) not in offered, (
            "the provoked creature may only be offered the block it owes"
        )
        assert not can_finish(game), "and it has not made that block yet"

    def test_a_creature_that_cannot_block_owes_nothing(self, builder):
        """"…if able". The requirement never makes an illegal block legal."""
        game = (
            builder(players=2)
            .battlefield(0, [PROVOKER])
            .battlefield(1, [BEAR])
            .build()
        )
        attacker = only_oid(game, PROVOKER, 0)
        victim = only_oid(game, BEAR, 1)
        attack_and_provoke(game, attacker, victim)
        # Tap it after the untap, so it is under the requirement and unable.
        game.state.objects[victim].tapped = True
        assert can_finish(game)
        assert combat_mod.unmet_block_requirements(game.state, 1) == []

    def test_no_provoke_target_leaves_blocking_free(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [PROVOKER])
            .battlefield(1, [BEAR])
            .build()
        )
        attacker = only_oid(game, PROVOKER, 0)
        attack_and_provoke(game, attacker, None)
        # Whichever way the optional target was answered, a declaration that
        # meets it is reachable; what must not happen is a deadlock.
        assert can_finish(game) or combat_mod.unmet_block_requirements(game.state, 1)


class TestItIsSpent:
    def test_the_requirement_does_not_survive_the_combat(self, builder):
        """Spent whether or not it was met -- otherwise the next combat is
        compelled too, which no printed provoke says."""
        game = (
            builder(players=2)
            .battlefield(0, [PROVOKER])
            .battlefield(1, [BEAR])
            .build()
        )
        attacker = only_oid(game, PROVOKER, 0)
        victim = only_oid(game, BEAR, 1)
        attack_and_provoke(game, attacker, victim)
        game.apply(
            find_action(
                game, ActionKind.ADD_BLOCKER, source=victim, targets=(TargetRef.obj(attacker),)
            )
        )
        done(game)
        assert game.state.objects[victim].must_block is None


class TestTheLoaderGuardsIt:
    def test_must_block_without_objects_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "oracle_text": "x",
                        "mana_cost": "{G}",
                        "types": ["Creature"],
                        "power": 1,
                        "toughness": 1,
                        "abilities": [
                            {
                                "kind": "triggered",
                                "text": "x",
                                "trigger": {"event": "attacks", "source": "self"},
                                "effects": [{"op": "must_block"}],
                            }
                        ],
                    }
                )
            )

    def test_the_provoke_card_compiles(self, registry):
        card = registry.get(PROVOKER)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert [e["op"] for e in ability.effects] == ["untap", "must_block"]
