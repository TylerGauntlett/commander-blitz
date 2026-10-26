""""Reselect which player or permanent target attacking creature is attacking."

Misleading Signpost and Portal Mage move an attack that has already been
declared. Nothing in the engine could: `cant_attack_player` and
`must_attack_planeswalker` constrain a declaration that has not happened yet, and
`attacking` on `create_token` / `put_onto_battlefield` chooses a defender only for
a permanent arriving in combat. `redirect_attack` rewrites
`combat.attackers[oid]` (the defending player) and `attacking_permanent[oid]`
(the planeswalker or battle, 506.2) for a creature that is attacking now.

What the rules make of it, each pinned below:

- **Who chooses.** "*You* may reselect" -- the effect's controller, here the
  defending player who flashed the Signpost in, not the attacker's controller.
- **What may be chosen.** 506.2's three attack targets, minus the reminder
  text's exception: "It can't attack its controller or their permanents."
- **Nothing is declared** (the reading 508.4 gives a creature put onto the
  battlefield attacking). Restrictions on declaring (508.1c) are not consulted,
  so a "can't attack that player" restriction does not stop the reselection, and
  no attack trigger fires again.
- **Blocks follow the attack.** The new defending player declares blockers for
  it, and the old one, attacked by nothing any more, is not asked to (509.1).
  Combat damage lands on the new target.

The witness is Misleading Signpost.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.temp_effects import restrict_attack
from tests.conftest import _default_answer, action_for_card, attack_with, find_action, pass_until

SIGNPOST = "t_redirect_signpost"
BEAR = "t_bear"
WALKER = "t_walker"


def position(builder, *, players=3, mine=(BEAR,), lend=()):
    """Player 0 attacks player 1 with a bear; player 1 holds the Signpost.

    ``lend`` goes on player 2's battlefield. Returns ``(game, bear)``.
    """
    b = builder(players=players).battlefield(0, list(mine)).hand(1, [SIGNPOST])
    if lend:
        b.battlefield(2, list(lend))
    game = b.active(0).step(Step.UNTAP).build()
    bear = next(o for o in game.state.battlefield if game.state.objects[o].def_id == BEAR)
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    attack_with(game, bear, defender=1)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    return game, bear


def offered(decision) -> list[tuple[str, int]]:
    return [(o.ref.kind, o.ref.id) for o in decision.options if o.ref is not None]


def flash_signpost(game, *, accept=True, pick=None, seen=None):
    """Player 1 flashes the Signpost in and answers its trigger.

    ``pick`` is the ``(kind, id)`` to send the attacker at; ``seen`` collects
    the reselection decision, so a test can read who was asked and what was
    offered.
    """

    def can_flash(g):
        d = g.pending()
        return (
            g.state.step is Step.DECLARE_ATTACKERS
            and d is not None
            and d.kind is DecisionKind.PRIORITY
            and d.player == 1
            and any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == SIGNPOST
                for a in g.legal_actions()
            )
        )

    pass_until(game, can_flash)
    game.apply(action_for_card(game, ActionKind.CAST, SIGNPOST))
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            return
        # The trigger has left the stack by the time it asks, so the stack being
        # empty is not the end; the end is the first decision that is not the
        # Signpost's own.
        mine = decision.kind is DecisionKind.MAY or decision.context.get("purpose") == "attack"
        if not mine and not game.state.stack and not game.state.pending_triggers:
            return
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if accept else ActionKind.NO
            game.apply(find_action(game, want))
            continue
        if (
            decision.kind is DecisionKind.CHOOSE_OBJECTS
            and decision.context.get("purpose") == "attack"
        ):
            if seen is not None:
                seen.append(decision)
            index = offered(decision).index(pick)
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the Signpost never finished resolving")


class TestTheAttackMoves:
    def test_to_another_player(self, builder):
        game, bear = position(builder)
        flash_signpost(game, pick=("player", 2))
        combat = game.state.combat
        assert combat.attackers[bear] == 2
        assert bear not in combat.attacking_permanent

    def test_to_a_planeswalker(self, builder):
        game, bear = position(builder, lend=(WALKER,))
        walker = next(o for o in game.state.battlefield if game.state.objects[o].def_id == WALKER)
        flash_signpost(game, pick=("object", walker))
        combat = game.state.combat
        assert combat.attacking_permanent[bear] == walker
        assert combat.attackers[bear] == 2, "the walker's controller is the defending player"

    def test_declining_leaves_it_where_it_was(self, builder):
        game, bear = position(builder)
        flash_signpost(game, accept=False)
        assert game.state.combat.attackers[bear] == 1


class TestWhatIsOffered:
    def test_the_effects_controller_chooses(self, builder):
        game, _ = position(builder)
        seen = []
        flash_signpost(game, pick=("player", 2), seen=seen)
        assert seen[0].player == 1, "the Signpost's controller, not the attacker's"

    def test_never_its_controller_or_their_permanents(self, builder):
        game, _ = position(builder, mine=(BEAR, WALKER), lend=(WALKER,))
        mine = next(
            o
            for o in game.state.battlefield
            if game.state.objects[o].def_id == WALKER and game.state.objects[o].controller == 0
        )
        theirs = next(
            o
            for o in game.state.battlefield
            if game.state.objects[o].def_id == WALKER and game.state.objects[o].controller == 2
        )
        seen = []
        flash_signpost(game, pick=("player", 2), seen=seen)
        options = offered(seen[0])
        assert ("player", 0) not in options
        assert ("object", mine) not in options
        assert {("player", 1), ("player", 2), ("object", theirs)} <= set(options)

    def test_a_declaration_restriction_does_not_apply(self, builder):
        """508.1c governs declaring; nothing is declared here (508.4's reading)."""
        game, bear = position(builder)
        restrict_attack(game.state, 0, 2, "this_turn")
        flash_signpost(game, pick=("player", 2))
        assert game.state.combat.attackers[bear] == 2


class TestNothingIsDeclared:
    def test_no_attack_trigger_fires_again(self, builder):
        game, _ = position(builder)
        attacks_before = sum(1 for e in game.state.events if e.type == "attacks")
        flash_signpost(game, pick=("player", 2))
        assert sum(1 for e in game.state.events if e.type == "attacks") == attacks_before


class TestBlocksAndDamageFollow:
    def test_the_new_defender_blocks_and_the_old_one_does_not(self, builder):
        game, _ = position(builder)
        flash_signpost(game, pick=("player", 2))
        assert game.state.combat.pending_blockers == [2]

    def test_combat_damage_lands_on_the_new_target(self, builder):
        game, _ = position(builder)
        flash_signpost(game, pick=("player", 2))
        pass_until(game, lambda g: g.state.step >= Step.END_OF_COMBAT)
        assert game.state.players[1].life == 40
        assert game.state.players[2].life == 38


def probe(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{U}",
                "types": ["Instant"],
                "spell_effects": [effect],
            }
        )
    )


class TestLoadTime:
    def test_it_needs_objects(self):
        with pytest.raises(DslError, match="redirect_attack"):
            probe({"op": "redirect_attack"})
