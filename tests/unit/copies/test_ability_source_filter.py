"""Targeting an ability on the stack by what its **source** is.

    The Peregrine Dynamo -- "{1}, {T}: Copy target activated or triggered
    ability you control from another legendary source that's not a commander.
    You may choose new targets for the copy."

An ability on the stack has no characteristics of its own (113.7a), so "from
another legendary source that's not a commander" is a question about a
different object: the permanent the ability came from. Without a way to ask
it, the only spelling was Peter Parker's Camera's "target activated or
triggered ability you control" -- a strictly wider card that copies the
abilities of every nonlegendary permanent and of the commander itself.

The ``ability_source`` clause on an ``ability_on_stack`` selector is that
question: an ordinary object selector asked of the source through
`selectors.matches`. 113.7a also makes the ability independent of its source,
so a source that has left the battlefield while its ability waited on the
stack -- destroyed in response, or a token that ceased to exist -- is asked as
it last existed there, from the record `zones.move_object` files on the stack item as
it leaves (`StackItem.source_last_known`). Both `candidates` and `still_legal`
read it, so a target that is offered is one the 608.2b re-check accepts.

Witness: The Peregrine Dynamo (`the_peregrine_dynamo` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.sba import run as run_sba
from commanderblitz.engine.stack import push_activated_ability
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.targeting import candidates, still_legal
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

DYNAMO = "t_dynamo"
LEGEND = "t_legend_gainer"  # Legendary: {T}: you gain 2 life
PLAIN = "t_gainer"  # nonlegendary: {T}: you gain 2 life


def board(builder, *extra: str):
    """``(game, dynamo)`` with a legendary and a nonlegendary source beside it."""
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 4 + [DYNAMO, LEGEND, PLAIN, *extra])
        .build(advance=False)
    )
    return game, only_oid(game, DYNAMO, 0)


def activate(game, card_id: str, index: int = 0):
    return push_activated_ability(game.state, only_oid(game, card_id, 0), index, 0)


def spec(game):
    return game.state.registry.get(DYNAMO).abilities[0].targets[0]


def offered(game, dynamo: int) -> list[int]:
    return [ref.id for ref in candidates(game.state, 0, spec(game), dynamo)]


def legal(game, dynamo: int, item) -> bool:
    return still_legal(game.state, 0, spec(game), TargetRef.stack(item.sid), dynamo)


class TestTheSourceIsAsked:
    def test_a_legendary_sources_ability_is_offered(self, builder):
        game, dynamo = board(builder)
        item = activate(game, LEGEND)
        assert offered(game, dynamo) == [item.sid]

    def test_a_nonlegendary_sources_is_not(self, builder):
        game, dynamo = board(builder)
        activate(game, PLAIN)
        assert offered(game, dynamo) == []

    def test_its_own_ability_is_not_another_source(self, builder):
        """The Dynamo is legendary and no commander; only "another" refuses it."""
        game, dynamo = board(builder)
        activate(game, DYNAMO, index=1)
        assert offered(game, dynamo) == []

    def test_a_commanders_is_not(self, builder):
        game, dynamo = board(builder)
        game.state.objects[only_oid(game, LEGEND, 0)].is_commander = True
        activate(game, LEGEND)
        assert offered(game, dynamo) == []

    def test_still_legal_agrees(self, builder):
        game, dynamo = board(builder)
        legendary, plain = activate(game, LEGEND), activate(game, PLAIN)
        assert offered(game, dynamo) == [legendary.sid]
        assert legal(game, dynamo, legendary)
        assert not legal(game, dynamo, plain)


class TestADepartedSourceIsAskedAsItLastWas:
    def test_nothing_is_recorded_while_it_stays(self, builder):
        game, _ = board(builder)
        assert activate(game, LEGEND).source_last_known is None

    def test_a_sacrificed_source_is_still_legendary(self, builder):
        game, dynamo = board(builder)
        item = activate(game, LEGEND)
        move_object(game.state, only_oid(game, LEGEND, 0), Zone.GRAVEYARD)

        assert item.source_last_known is not None
        assert "Legendary" in item.source_last_known.chars.supertypes
        assert offered(game, dynamo) == [item.sid]
        assert legal(game, dynamo, item)

    def test_a_token_that_ceased_to_exist_is_still_asked(self, builder):
        """Read live, a token source is no object at all once 704.5d removes it."""
        game, dynamo = board(builder)
        legend = only_oid(game, LEGEND, 0)
        game.state.objects[legend].is_token = True
        item = activate(game, LEGEND)
        move_object(game.state, legend, Zone.GRAVEYARD)
        run_sba(game.state)

        assert legend not in game.state.objects
        assert offered(game, dynamo) == [item.sid]

    def test_a_departed_commander_is_still_refused(self, builder):
        game, dynamo = board(builder)
        legend = only_oid(game, LEGEND, 0)
        game.state.objects[legend].is_commander = True
        activate(game, LEGEND)
        move_object(game.state, legend, Zone.GRAVEYARD)
        assert offered(game, dynamo) == []

    def test_a_copy_keeps_the_record(self, builder):
        """706.10: the copy has the same source, so the same last-known one."""
        game, _ = board(builder)
        item = activate(game, LEGEND)
        move_object(game.state, only_oid(game, LEGEND, 0), Zone.GRAVEYARD)
        ctx = EffectContext(
            state=game.state, controller=0, targets={"t1": [TargetRef.stack(item.sid)]}
        )
        for _ in OPS["copy_ability"](ctx, {"target": "t1"}):
            raise AssertionError("a copy without new targets asks nothing")

        copy = game.state.stack[-1]
        assert copy.sid != item.sid
        assert copy.source_last_known is item.source_last_known


class TestTheLoader:
    def _card(self, selector) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_dynamo_probe",
                "name": "Dynamo Probe",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "{T}: Copy target ability you control from a legendary source.",
                        "cost": {"tap": True},
                        "targets": [{"id": "t1", "kind": "ability_on_stack", "selector": selector}],
                        "effects": [{"op": "copy_ability", "target": "t1"}],
                    }
                ],
            }
        )

    def test_it_loads(self):
        compile_card(
            self._card(
                {
                    "controller": "you",
                    "ability_source": {
                        "supertypes": ["Legendary"],
                        "exclude_self": True,
                        "is_commander": False,
                    },
                }
            )
        )

    @pytest.mark.parametrize(
        "source",
        [
            {},
            {"zone": "battlefield"},
            {"tapped": True},
            {"attached_to": {"types": ["Creature"]}},
            {"supertypes": ["Legendery"]},
        ],
        ids=["empty", "zone", "live_board_state", "attachment", "unknown_supertype"],
    )
    def test_a_clause_it_cannot_answer_is_refused(self, source):
        with pytest.raises(DslError, match="ability_source"):
            compile_card(self._card({"ability_source": source}))

    def test_a_face_clause_still_belongs_inside_it(self):
        with pytest.raises(DslError, match="ability_source"):
            compile_card(self._card({"supertypes": ["Legendary"]}))

    def test_it_means_nothing_on_a_permanent(self):
        card = CardModel.model_validate(
            {
                "id": "t_dynamo_probe",
                "name": "Dynamo Probe",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "{T}: Tap target creature.",
                        "cost": {"tap": True},
                        "targets": [
                            {
                                "id": "t1",
                                "kind": "permanent",
                                "selector": {"ability_source": {"supertypes": ["Legendary"]}},
                            }
                        ],
                        "effects": [{"op": "tap", "target": "t1"}],
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="ability_source"):
            compile_card(card)
