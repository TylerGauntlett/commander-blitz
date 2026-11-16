"""Zara, Renegade Recruiter -- "You may put a creature card from it onto the
battlefield under your control tapped and attacking that player... **Return that
creature** to its owner's hand at the beginning of the next end step."

"That creature" is the one object this resolution put down, and the delayed
return has to name exactly it (603.7c: a delayed trigger refers to the object
the effect that created it affected). `put_onto_battlefield` recorded nothing,
so the nearest spelling was a selector over the board at end step --
`{"controller": "you", "owner": {"binding": "defender"}}` -- which also bounces
every other creature borrowed from that player this turn, and none at all once
it has changed controller back.

So `as` on the op binds the oids that **actually arrived**, the way
`create_token`'s and `copy_permanent`'s `as` let Flamerush Rider exile "the
token", and `delay` carries the binding to the end step. Written even when
nothing arrived, so a declined "you may" returns nothing.

`t_recruiter` is the witness: Zara's two sentences over the attack trigger.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, attack_with, only_oid, pass_until

RECRUITER = "t_recruiter"
BEAR = "t_bear"


def position(builder, *, borrowed: bool = False):
    """Player 0's recruiter ready to attack; player 1 holds a bear.

    ``borrowed`` puts a second bear of player 1's under player 0's control --
    the creature an end-step selector would bounce along with the recruit.
    """
    b = builder(players=2).battlefield(0, [RECRUITER]).hand(1, [BEAR])
    if borrowed:
        b = b.battlefield(1, [BEAR])
    game = b.build()
    other = None
    if borrowed:
        other = next(oid for oid in game.state.battlefield if game.state.card(oid).id == BEAR)
        game.state.objects[other].controller = 0
        game.state.bump_chars()
    return game, only_oid(game, RECRUITER), other


def recruit(game, recruiter: int, *, accept: bool = True) -> int:
    """Attack with the recruiter and answer its trigger; the bear's oid."""
    bear = next(oid for oid in game.state.players[1].hand if game.state.card(oid).id == BEAR)
    pass_until(game, lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.DECLARE_ATTACKERS)
    attack_with(game, recruiter)
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    for _ in range(100):
        decision = game.pending()
        if decision is None or game.state.objects[bear].zone is Zone.BATTLEFIELD:
            break
        if decision.kind is DecisionKind.MAY:
            wanted = ActionKind.YES if accept else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is wanted))
            if not accept:
                break
            continue
        if decision.kind is DecisionKind.CHOOSE_OBJECTS and decision.context.get("purpose") != "attack":
            index = next(i for i, o in enumerate(decision.options) if o.ref and o.ref.id == bear)
            game.apply(
                next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
            )
            continue
        game.apply(_default_answer(game, decision))
    return bear


def to_end_step_passed(game) -> None:
    pass_until(game, lambda g: g.state.step is Step.CLEANUP or g.state.active_player != 0)


class TestTheRecruitArrives:
    def test_it_is_on_the_battlefield_under_your_control_attacking(self, builder):
        game, recruiter, _ = position(builder)
        bear = recruit(game, recruiter)
        obj = game.state.objects[bear]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.controller == 0 and obj.tapped
        assert game.state.combat.attackers.get(bear) == 1


class TestThatCreatureGoesBack:
    def test_it_returns_to_its_owners_hand_at_the_end_step(self, builder):
        game, recruiter, _ = position(builder)
        bear = recruit(game, recruiter)
        to_end_step_passed(game)
        assert bear in game.state.players[1].hand

    def test_another_borrowed_creature_of_the_same_owner_stays(self, builder):
        """The selector spelling would have bounced this one too."""
        game, recruiter, other = position(builder, borrowed=True)
        recruit(game, recruiter)
        to_end_step_passed(game)
        assert game.state.objects[other].zone is Zone.BATTLEFIELD

    def test_declining_returns_nothing(self, builder):
        game, recruiter, other = position(builder, borrowed=True)
        bear = recruit(game, recruiter, accept=False)
        to_end_step_passed(game)
        assert bear in game.state.players[1].hand
        assert game.state.objects[other].zone is Zone.BATTLEFIELD


def _probe(effects: list) -> CardModel:
    text = "When this creature enters, put a creature card from your hand onto the battlefield."
    return CardModel.model_validate(
        {
            "id": "t_put_as_probe",
            "name": "Test Put As Probe",
            "oracle_text": text,
            "mana_cost": "{1}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {"kind": "triggered", "text": text, "trigger": {"event": "self_enters", "source": "self"},
                 "effects": effects}
            ],
        }
    )


class TestTheLoader:
    def test_as_is_accepted(self):
        compile_card(
            _probe([{"op": "put_onto_battlefield", "as": "put",
                     "objects": {"zone": "hand", "types": ["Creature"], "count": 1, "chooser": "controller"}}]),
            source="test",
        )

    def test_a_non_string_as_is_refused(self):
        with pytest.raises(DslError, match="'as'"):
            compile_card(
                _probe([{"op": "put_onto_battlefield", "as": 3,
                         "objects": {"zone": "hand", "types": ["Creature"], "count": 1}}]),
                source="test",
            )
