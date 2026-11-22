""""Whenever you activate an ability …, you may copy **that ability**."

Ashnod the Uncaring is the witness: "Whenever you activate an ability of an
artifact or creature that isn't a mana ability, if one or more permanents were
sacrificed to activate it, you may copy that ability. You may choose new
targets for the copy."

707.10 copies an ability on the stack with every choice made for it, and
707.10c lets the copy's controller choose new targets. "That ability" is not a
target: the trigger announces nothing, nothing can make it fizzle, and it
cannot be pointed at some other ability. Written as `copy_ability` over a
declared `ability_on_stack` target it would be Lithoform Engine -- a card that
copies whichever ability you like, and loses the copy when the original's
controller is out of legal targets for it.

So `copy_ability` takes ``sid`` as a value, and the `ability_activated` event
carries the sid of the stack item the activation becomes. The event fires
before the cost is paid (602.2b, and the only moment the source is still where
it was), which is before the item exists -- so `Game._activate` allocates the
sid there and `push_activated_ability` puts the item on the stack under it,
ahead of every trigger the event woke (603.3). An ability that has left the
stack by the time the copy resolves is not there to copy, which is the answer
`copy_spell` gives a `spell_cast` trigger's sid.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import _default_answer, activations, oids_of, only_oid

COPIER = "t_cta_copier"
#: Sacrifice a creature: target player loses 2 life.
STRIKER = "t_cta_striker"
#: {B}, {T}, Sacrifice another creature: create X Zombies, X the sacrificed power.
GISA = "t_gisa_outlet"
#: {G}: +1/+1 -- no sacrifice in the cost.
MUTATOR = "t_mutator"
ZOMBIE = "zombie_2_2_b"


def position(builder, mine, *, players=2):
    """The copier and ``mine`` under player 0, in their main phase."""
    return (
        builder(players=players)
        .battlefield(0, [COPIER, *mine])
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def activate(game, card_id, *, target=None):
    oid = only_oid(game, card_id, 0)
    options = activations(game, oid)
    if target is not None:
        options = [a for a in options if a.targets and a.targets[0].id == target]
    game.apply(options[0])


def resolve(game, *, copy=True, retarget_to=None, limit=300):
    """Resolve everything, answering the copier's "may" and its new targets.

    Returns whether new targets were asked for."""
    asked = False
    for _ in range(limit):
        decision = game.pending()
        if decision is None or game.over:
            break
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if copy else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        if decision.kind is DecisionKind.CHOOSE_MODE and "new targets" in (
            decision.prompt or ""
        ):
            asked = True
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE
                    and (decision.options[a.choice].label or "") == retarget_to
                )
            )
            continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            break
        game.apply(_default_answer(game, decision))
    return asked


def life(game, pid) -> int:
    return game.state.players[pid].life


class TestTheEventNamesTheAbility:
    def test_the_sid_is_the_item_on_the_stack(self, builder):
        game = position(builder, [GISA, "t_bear", "swamp"])
        activate(game, GISA)
        event = next(
            e for e in reversed(game.state.events) if e.type == EventType.ABILITY_ACTIVATED
        )
        item = game.state.stack_item(event.data["sid"])
        assert item is not None and not item.is_spell
        assert item.source_oid == only_oid(game, GISA, 0)


class TestThatAbilityIsCopied:
    def test_the_copy_resolves_with_the_originals_bindings(self, builder):
        """The bear's power is what the cost bound; the copy keeps it, so two
        Zombies become four."""
        game = position(builder, [GISA, "t_bear", "swamp"])
        activate(game, GISA)
        resolve(game)
        assert len(oids_of(game, ZOMBIE, 0)) == 4

    def test_declining_leaves_the_original(self, builder):
        game = position(builder, [GISA, "t_bear", "swamp"])
        activate(game, GISA)
        resolve(game, copy=False)
        assert len(oids_of(game, ZOMBIE, 0)) == 2

    def test_no_sacrifice_no_copy(self, builder):
        """The intervening clause is the previous capability; this is its
        boundary still holding with a copy behind it."""
        game = position(builder, [MUTATOR, "forest"])
        activate(game, MUTATOR)
        assert not game.state.pending_triggers
        resolve(game)
        assert len(game.state.stack) == 0


class TestNewTargets:
    def test_the_copy_may_be_moved(self, builder):
        game = position(builder, [STRIKER, "t_bear"], players=3)
        activate(game, STRIKER, target=1)
        asked = resolve(game, retarget_to=game.state.players[2].name or "p2")
        assert asked
        assert (life(game, 1), life(game, 2)) == (38, 38)

    def test_kept_targets_hit_twice(self, builder):
        game = position(builder, [STRIKER, "t_bear"], players=3)
        activate(game, STRIKER, target=1)
        resolve(game, retarget_to=game.state.players[1].name or "p1")
        assert (life(game, 1), life(game, 2)) == (36, 40)


class TestTheOriginalLeftTheStack:
    def test_nothing_is_copied(self, builder):
        """Stifled in response: the trigger still resolves -- it does not target
        -- but there is no ability left to copy."""
        game = position(builder, [GISA, "t_bear", "swamp"])
        activate(game, GISA)
        event = next(
            e for e in reversed(game.state.events) if e.type == EventType.ABILITY_ACTIVATED
        )
        sid = event.data["sid"]
        game.state.stack = [it for it in game.state.stack if it.sid != sid]
        resolve(game)
        assert not oids_of(game, ZOMBIE, 0)
        assert not game.state.stack


def probe(effect) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Whenever you activate an ability, copy that ability.",
        "mana_cost": "{3}",
        "types": ["Artifact"],
        "abilities": [
            {
                "kind": "triggered",
                "text": "Whenever you activate an ability, copy that ability.",
                "trigger": {
                    "event": "ability_activated",
                    "controller": "you",
                    "mana_ability": False,
                },
                "effects": [effect],
            }
        ],
    }


class TestTheLoader:
    def test_sid_compiles(self):
        compile_card(
            CardModel.model_validate(
                probe({"op": "copy_ability", "sid": {"binding": "sid"}, "new_targets": True})
            )
        )

    def test_sid_beside_target_is_refused(self):
        payload = probe({"op": "copy_ability", "sid": {"binding": "sid"}, "target": "t1"})
        payload["abilities"][0]["targets"] = [
            {"id": "t1", "kind": "ability_on_stack", "count": 1, "selector": {"controller": "you"}}
        ]
        with pytest.raises(DslError, match="'sid' or 'target'"):
            compile_card(CardModel.model_validate(payload))

    def test_a_malformed_sid_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(probe({"op": "copy_ability", "sid": {"bogus": 1}}))
            )
