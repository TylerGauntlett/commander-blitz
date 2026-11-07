"""'Other creatures have "…you may have it fight **Grothama, All-Devouring**."'

    Grothama, All-Devouring — Legendary Creature — Wurm
    "Other creatures have "Whenever this creature attacks, you may have it
    fight Grothama, All-Devouring." …"

A granted ability is the **recipient's** ability (113.6, 613.1f), so inside it
``self`` -- `self_only`, ``source_oid`` -- is the creature that attacked. The
card's own name in the quoted text still means the card that granted it, and
before `{"granter": true}` there was no word for that object:

* **``self_only``** is the attacker, and 701.12d makes a creature fighting
  itself a no-op -- the ability would load and never do anything.
* **``{"name": "Grothama, All-Devouring"}``** finds every permanent of that
  name. Two players can each control a Grothama (the legend rule is per
  controller, 704.5j), and each grants the ability; with a name selector both
  triggers fight whichever Grothama comes first, so one takes both blows and
  the other none.

`{"granter": true}` reads `StackItem.granted_by` through
`EffectContext.granted_by`, searched on the battlefield like any selector, so
a Grothama that has left before the trigger resolves is not fought (701.12c:
neither creature deals damage). The loader confines it to a granted trigger's
or activated ability's effects, the only place it has an answer.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import matches
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.zones import move_object
from tests.conftest import find_action, oids_of, only_oid, pass_until

GROTHAMA = "gr_grothama"  # 10/8; other creatures have "attacks: may fight Grothama"
GIANT = "gr_giant"  # 1/30, survives two fights with a 10-power Grothama
BEAR = "gr_bear"  # 3/3

QUOTED = "Whenever this creature attacks, you may have it fight Gr Grothama."


def _grantable(effects_other: dict | None = None, **extra) -> dict:
    return {
        "kind": "triggered",
        "text": QUOTED,
        "trigger": {"event": "attacks", "source": "self"},
        "effects": [
            {
                "op": "may",
                "prompt": "Have it fight Gr Grothama?",
                "effects": [
                    {
                        "op": "fight",
                        "objects": {"self_only": True},
                        "other": effects_other or {"granter": True},
                    }
                ],
            }
        ],
        **extra,
    }


def _grothama(**overrides) -> dict:
    spec = {
        "id": GROTHAMA,
        "name": "Gr Grothama",
        "oracle_text": f'Other creatures have "{QUOTED}"',
        "mana_cost": "{6}{G}",
        "types": ["Creature"],
        "supertypes": ["Legendary"],
        "subtypes": ["Wurm"],
        "power": 10,
        "toughness": 8,
        "grantable_abilities": [_grantable()],
        "abilities": [
            {
                "kind": "static",
                "text": f'Other creatures have "{QUOTED}"',
                "effect": "grant_ability",
                "ability": 0,
                "affects": {"types": ["Creature"], "controller": "any", "exclude_self": True},
            }
        ],
    }
    spec.update(overrides)
    return spec


def _creature(card_id: str, power: int, toughness: int) -> dict:
    return {
        "id": card_id,
        "name": card_id.replace("_", " ").title(),
        "mana_cost": "{G}",
        "types": ["Creature"],
        "subtypes": ["Giant"],
        "power": power,
        "toughness": toughness,
    }


@pytest.fixture(scope="module")
def pool(registry) -> CardRegistry:
    cards = {card.id: card for card in registry}
    for spec in (_grothama(), _creature(GIANT, 1, 30), _creature(BEAR, 3, 3)):
        compiled = compile_card(CardModel.model_validate(spec))
        cards[compiled.id] = compiled
    return CardRegistry(cards)


def position(pool, mine: list[str], theirs: list[str]):
    """``mine`` on seat 0, ``theirs`` on seat 1, seat 0 about to attack."""
    return (
        GameBuilder(pool, players=2, seed=0)
        .battlefield(0, mine)
        .battlefield(1, theirs)
        .build()
    )


def attack(game, oid: int) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def answer_every_may(game, yes: bool) -> None:
    """Resolve the attack triggers, answering each `may` the same way."""
    word = ActionKind.YES if yes else ActionKind.NO
    for _ in range(50):
        decision = game.pending()
        if decision is not None and decision.kind is DecisionKind.MAY:
            game.apply(find_action(game, word))
            continue
        if not game.state.stack and not game.state.pending_triggers:
            return
        pass_until(
            game,
            lambda g: (g.pending() is not None and g.pending().kind is DecisionKind.MAY)
            or (not g.state.stack and not g.state.pending_triggers),
        )
    raise AssertionError("the triggers never finished resolving")


def damage(game, oid: int) -> int:
    return game.state.objects[oid].damage


class TestItFightsTheGranter:
    def test_taking_the_offer_fights_grothama(self, pool):
        game = position(pool, [GIANT], [GROTHAMA])
        giant, wurm = only_oid(game, GIANT, 0), only_oid(game, GROTHAMA, 1)
        attack(game, giant)
        answer_every_may(game, yes=True)

        assert damage(game, wurm) == 1, "the attacker's power, dealt to the granter"
        assert damage(game, giant) == 10, "and Grothama's back, to the attacker"

    def test_declining_fights_nobody(self, pool):
        game = position(pool, [GIANT], [GROTHAMA])
        giant, wurm = only_oid(game, GIANT, 0), only_oid(game, GROTHAMA, 1)
        attack(game, giant)
        answer_every_may(game, yes=False)

        assert damage(game, wurm) == 0
        assert damage(game, giant) == 0

    def test_a_small_attacker_dies_and_still_deals_its_damage(self, pool):
        """The fight is the ordinary one: simultaneous (701.12b)."""
        game = position(pool, [BEAR], [GROTHAMA])
        bear, wurm = only_oid(game, BEAR, 0), only_oid(game, GROTHAMA, 1)
        attack(game, bear)
        answer_every_may(game, yes=True)

        assert damage(game, wurm) == 3
        assert game.state.objects[bear].zone is Zone.GRAVEYARD


class TestEachGranterIsItsOwn:
    def test_two_grothamas_each_take_one_blow(self, pool):
        """Two players' Grothamas each grant the trigger, and each trigger
        fights the Grothama that granted it.

        A name selector would send both fights to the same Grothama: one would
        show 2 damage and the other 0.
        """
        game = position(pool, [GIANT, GROTHAMA], [GROTHAMA])
        giant = only_oid(game, GIANT, 0)
        ours, theirs = only_oid(game, GROTHAMA, 0), only_oid(game, GROTHAMA, 1)
        attack(game, giant)
        answer_every_may(game, yes=True)

        assert damage(game, ours) == 1
        assert damage(game, theirs) == 1
        assert damage(game, giant) == 20


class TestAGranterThatHasLeft:
    def test_grothama_gone_before_the_fight_is_not_fought(self, pool):
        """701.12c: with one of the two off the battlefield, neither deals damage.

        The trigger is resolving -- its `may` is being asked -- when Grothama
        leaves. The ability carries on without its granter (608.2), and the
        selector, searching the battlefield, finds no one to fight.
        """
        game = position(pool, [GIANT], [GROTHAMA])
        giant, wurm = only_oid(game, GIANT, 0), only_oid(game, GROTHAMA, 1)
        attack(game, giant)
        pass_until(game, lambda g: g.pending().kind is DecisionKind.MAY)
        move_object(game.state, wurm, Zone.GRAVEYARD)
        answer_every_may(game, yes=True)

        assert damage(game, giant) == 0
        assert not oids_of(game, GROTHAMA)


class TestTheSelectorOutsideAGrantedAbility:
    def test_an_ungranted_context_matches_nothing(self, pool):
        game = position(pool, [GIANT], [GROTHAMA])
        wurm = only_oid(game, GROTHAMA, 1)
        bare = EffectContext(state=game.state, controller=0, source_oid=wurm)
        granted = EffectContext(state=game.state, controller=0, granted_by=wurm)

        assert not matches(bare, wurm, {"granter": True})
        assert matches(granted, wurm, {"granter": True})


class TestTheLoaderConfinesIt:
    def _compile(self, spec: dict):
        return compile_card(CardModel.model_validate(spec))

    def test_a_printed_ability_has_no_granter(self):
        spec = _grothama(
            abilities=[
                {
                    "kind": "triggered",
                    "text": "Whenever this creature attacks, it fights its granter.",
                    "trigger": {"event": "attacks", "source": "self"},
                    "effects": [
                        {"op": "fight", "objects": {"self_only": True},
                         "other": {"granter": True}}
                    ],
                }
            ],
            grantable_abilities=[],
        )
        with pytest.raises(DslError, match="granter"):
            self._compile(spec)

    def test_a_spell_has_no_granter(self):
        spec = {
            "id": "gr_spell",
            "name": "Gr Spell",
            "oracle_text": "Destroy the granter.",
            "mana_cost": "{B}",
            "types": ["Instant"],
            "spell_effects": [{"op": "destroy", "objects": {"granter": True}}],
        }
        with pytest.raises(DslError, match="granter"):
            self._compile(spec)

    def test_a_granted_target_is_declared_before_the_granter_is_known(self):
        target = {"id": "t1", "kind": "permanent", "count": 1,
                  "selector": {"granter": True, "zone": "battlefield"}}
        spec = _grothama(grantable_abilities=[_grantable(targets=[target])])
        with pytest.raises(DslError, match="grantable_abilities\\[0\\]"):
            self._compile(spec)

    def test_only_true(self):
        spec = _grothama(grantable_abilities=[_grantable({"granter": False})])
        with pytest.raises(DslError, match="granter must be true"):
            self._compile(spec)
