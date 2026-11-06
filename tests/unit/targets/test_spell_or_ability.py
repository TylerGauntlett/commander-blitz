""""Counter target **spell, activated ability, or triggered ability**."

Disallow. One instance of the word "target" whose pool is every object on the
stack, so it is one spec of kind `spell_or_ability`: the `spell` pool and the
`ability_on_stack` pool together. Two specs would be a card that targets twice
and could be cast only with a spell *and* an ability on the stack; a
`choose_mode` between them is a modal card choosing at a different moment.

The rules this rests on:

* 605.3b -- a mana ability does not use the stack, so it is never a candidate:
  there is nothing on the stack to point at.
* 701.6b -- countering an ability removes it from the stack; its effect never
  happens. `counter` already did this for any stack ref; what was missing was a
  target able to reach a spell and an ability alike.
* 608.2b -- the target is re-checked on resolution by the half it is in:
  `still_legal` sends an ability ref to `_ability_matches` and a spell ref to
  `_spell_matches`, the same matchers `candidates` offered them through.

Witness: Disallow (`disallow` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.stack import push_activated_ability, push_triggered_ability
from commanderblitz.engine.structs import TargetRef, TriggerInstance
from commanderblitz.engine.targeting import candidates, still_legal
from tests.conftest import (
    action_for_card,
    activations,
    only_oid,
    pass_until,
    settle_to_priority,
)

DISALLOW = "t_disallow"
THEIRS = "t_disallow_theirs"  # "...an opponent controls"
TRIGGERER = "t_upkeep_gainer"  # at the beginning of your upkeep, gain 2
ACTIVATED = "t_gainer"  # {T}: you gain 2 life
BAIT = "t_plain_instant"  # {W}: you gain 1 life


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 3 + [TRIGGERER, ACTIVATED])
        .battlefield(1, ["plains"] * 2 + [ACTIVATED])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [DISALLOW, THEIRS])
        .build(advance=False)
    )


def spec(game, def_id=DISALLOW):
    return game.state.registry.get(def_id).targets[0]


def trigger(game, seat=0):
    trig = TriggerInstance(
        source_oid=only_oid(game, TRIGGERER, 0), ability_index=0, controller=seat
    )
    for _ in push_triggered_ability(game.state, trig):
        raise AssertionError("this trigger chooses nothing")
    return game.state.stack[-1]


def activate(game, seat=0):
    return push_activated_ability(game.state, only_oid(game, ACTIVATED, seat), 0, seat)


def offered(game, def_id=DISALLOW) -> list[int]:
    return [ref.id for ref in candidates(game.state, 0, spec(game, def_id), None)]


class TestThePoolIsEveryStackObject:
    def test_an_activated_ability_is_offered(self, builder):
        game = board(builder)
        item = activate(game)
        assert offered(game) == [item.sid]

    def test_a_triggered_ability_is_offered(self, builder):
        game = board(builder)
        item = trigger(game)
        assert offered(game) == [item.sid]

    def test_both_kinds_together(self, builder):
        game = board(builder)
        triggered, activated = trigger(game), activate(game)
        assert sorted(offered(game)) == sorted([triggered.sid, activated.sid])

    def test_with_an_empty_stack_nothing_is(self, builder):
        game = board(builder)
        assert offered(game) == []


class TestAManaAbilityIsNeverACandidate:
    def test_tapping_for_mana_leaves_nothing_to_target(self, builder):
        """605.3b: the mana ability resolves at once, off the stack."""
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 3 + ["dimir_signet"])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            # A land drop keeps the main-phase window open: "pass, or add some
            # mana" is no decision, and the engine would skip it.
            .hand(0, [DISALLOW, "mountain"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        mana = activations(game, only_oid(game, "dimir_signet", 0))
        assert mana, "a Signet's mana ability is activated by hand"
        game.apply(mana[0])
        assert game.state.stack == []
        assert offered(game) == []
        assert not any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == DISALLOW
            for a in game.legal_actions()
        )


class TestItCountersAnAbility:
    def test_the_ability_leaves_the_stack_and_does_nothing(self, builder):
        """701.6b: a countered ability is removed and its effect never happens."""
        game = board(builder)
        game._advance()
        life = game.state.players[0].life
        gainer = only_oid(game, ACTIVATED, 0)
        game.apply(activations(game, gainer)[0])
        ability = game.state.stack[-1]
        assert not ability.is_spell

        cast = action_for_card(game, ActionKind.CAST, DISALLOW)
        assert [(r.kind, r.id) for r in cast.targets] == [("stack", ability.sid)]
        game.apply(cast)
        settle_to_priority(game)

        assert game.state.stack == []
        assert game.state.players[0].life == life
        assert game.state.objects[gainer].tapped  # the cost stays paid


class TestItCountersASpell:
    def test_the_spell_goes_to_its_owners_graveyard(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 3)
            .battlefield(1, ["plains"] * 2)
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .hand(0, [DISALLOW])
            .hand(1, [BAIT])
            .build(advance=False)
        )
        game._advance()

        def bait_casts(g):
            return [
                a
                for a in g.legal_actions()
                if a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == BAIT
            ]

        pass_until(game, lambda g: bool(bait_casts(g)))
        bait = bait_casts(game)[0]
        game.apply(bait)
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == DISALLOW
                for a in g.legal_actions()
            ),
        )
        life = game.state.players[1].life
        game.apply(action_for_card(game, ActionKind.CAST, DISALLOW))
        settle_to_priority(game)

        assert game.state.objects[bait.source].zone is Zone.GRAVEYARD
        assert game.state.players[1].life == life


class TestTheControllerClause:
    def test_only_an_opponents_ability_is_offered(self, builder):
        game = board(builder)
        mine, theirs = activate(game, 0), activate(game, 1)
        assert offered(game, THEIRS) == [theirs.sid]
        assert mine.sid in offered(game)

    def test_still_legal_agrees(self, builder):
        game = board(builder)
        mine, theirs = activate(game, 0), activate(game, 1)
        narrow = spec(game, THEIRS)
        assert still_legal(game.state, 0, narrow, TargetRef.stack(theirs.sid), None)
        assert not still_legal(game.state, 0, narrow, TargetRef.stack(mine.sid), None)


class TestTheRecheck:
    def test_an_ability_still_on_the_stack_is_legal(self, builder):
        game = board(builder)
        item = trigger(game)
        assert still_legal(game.state, 0, spec(game), TargetRef.stack(item.sid), None)

    def test_an_ability_that_has_left_is_not(self, builder):
        game = board(builder)
        item = trigger(game)
        game.state.stack = [it for it in game.state.stack if it.sid != item.sid]
        assert not still_legal(game.state, 0, spec(game), TargetRef.stack(item.sid), None)

    def test_a_permanent_is_never_legal(self, builder):
        game = board(builder)
        gainer = only_oid(game, ACTIVATED, 0)
        assert not still_legal(game.state, 0, spec(game), TargetRef.obj(gainer), None)


class TestTheLoader:
    def _card(self, target) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_disallow_probe",
                "name": "Disallow Probe",
                "oracle_text": "Counter target spell, activated ability, or triggered ability.",
                "mana_cost": "{1}{U}{U}",
                "types": ["Instant"],
                "targets": [target],
                "spell_effects": [{"op": "counter", "target": "t1"}],
            }
        )

    def test_it_loads(self):
        compile_card(self._card({"id": "t1", "kind": "spell_or_ability"}))

    def test_a_face_clause_is_refused(self):
        """"Creature spell or ability" would narrow only the spell half."""
        with pytest.raises(DslError, match="spell_or_ability"):
            compile_card(
                self._card(
                    {"id": "t1", "kind": "spell_or_ability", "selector": {"types": ["Creature"]}}
                )
            )

    def test_ability_kind_is_refused(self):
        with pytest.raises(DslError, match="spell_or_ability"):
            compile_card(
                self._card(
                    {
                        "id": "t1",
                        "kind": "spell_or_ability",
                        "selector": {"ability_kind": "triggered"},
                    }
                )
            )

    def test_a_mapping_controller_is_refused(self):
        """`_ability_matches` answers only "you" and "opponent"."""
        with pytest.raises(DslError, match="controller"):
            compile_card(
                self._card(
                    {
                        "id": "t1",
                        "kind": "spell_or_ability",
                        "selector": {"controller": {"target": "t0"}},
                    }
                )
            )

    def test_total_mana_value_is_refused(self):
        with pytest.raises(DslError, match="total_mana_value"):
            compile_card(
                self._card({"id": "t1", "kind": "spell_or_ability", "total_mana_value": 3})
            )
