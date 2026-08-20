"""Jin-Gitaxias: "You may choose new targets for the copy."

Rule 706.10 puts a copy on the stack with the original's choices, and 115.7b
lets the copy's controller change any number of them. The engine did the first
half and deliberately skipped the second — `op_copy_spell`'s own docstring says
why, and it is a good reason: the choice is a decision **per copy**, and a storm
count of nine would ask nine times. It also said when to revisit it — "worth
doing when a card in the pool needs it" — and Jin-Gitaxias is that card.

So the capability is opt-in. `new_targets: true` is written on the one op that
wants it; storm, replicate, conspire, casualty, gravestorm and epic all go
through the same `put_copy_on_stack` and none of them gained a prompt. The
objection was to asking unconditionally, not to the ability to ask.

Retargeting is not a detail of this card, which is why it could not simply be
dropped: copying a removal spell onto the creature it already killed is a
strictly worse card than the one printed, and it would look entirely normal.

No new `DecisionKind` — `ask_mode` already asks "pick one of these labels" and
returns an index, which is exactly this question. The same argument
`choose_type` makes.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind
from tests.conftest import _default_answer, only_oid

ZAP = "t_zap"  # {R} instant, 3 damage to target creature
COPYCAT = "t_copycat"  # copies your instants, MAY choose new targets
STORMCAT = "t_stormcat"  # copies your instants, keeps the original's targets
BEAR = "grizzly_bears"  # 2/2, mine
THEIRS = "t_goblin"  # 1/1, the opponent's -- a distinct name, so the
#: "new targets" options are told apart by their labels the way a player does


def board(builder, engine: str):
    """You control the copier and two bears; the opponent controls one."""
    return (
        builder(players=2)
        .battlefield(0, [engine, BEAR, BEAR])
        .battlefield(0, ["mountain"] * 4)
        .battlefield(1, [THEIRS])
        .hand(0, [ZAP])
        .build()
    )


def cast_zap(game, target: int):
    """Cast Zap at one exact creature. The cast action carries the target."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == ZAP
        and a.targets
        and a.targets[0].id == target
    )
    game.apply(action)


def opponent_creature(game):
    return only_oid(game, THEIRS, 1)


def my_bears(game):
    return [
        oid
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == BEAR
        and game.state.objects[oid].controller == 0
    ]


def run(game, *, retarget_to=None, limit: int = 300):
    """Resolve everything. If asked for new targets, pick the tuple naming `retarget_to`."""
    asked = False
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.CHOOSE_MODE and "New targets" in (
            decision.prompt or ""
        ):
            asked = True
            if retarget_to is None:
                game.apply(_default_answer(game, decision))
                continue
            want = next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE
                and retarget_to in (decision.options[a.choice].label or "")
            )
            game.apply(want)
            continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    return asked


class TestTheChoiceIsOffered:
    def test_it_asks_when_the_op_opts_in(self, builder):
        game = board(builder, COPYCAT)
        cast_zap(game, my_bears(game)[0])
        assert run(game), "the copy should have offered new targets"

    def test_it_does_not_ask_without_the_flag(self, builder):
        """Storm's whole objection: the same op, and no prompt."""
        game = board(builder, STORMCAT)
        cast_zap(game, my_bears(game)[0])
        assert not run(game), "a plain copy must never ask"


class TestTheCopyCanBeMoved:
    def test_the_copy_hits_a_different_creature(self, builder):
        """The point of the card, and what dropping the clause would cost.

        The spell is aimed at one of my own bears; the copy is moved onto the
        opponent's. Without retargeting both would hit mine and the opponent
        would lose nothing -- a strictly worse card that looks entirely normal.
        """
        game = board(builder, COPYCAT)
        theirs = opponent_creature(game)
        mine = my_bears(game)
        cast_zap(game, mine[0])
        run(game, retarget_to="Test Goblin")
        assert game.state.objects[theirs].zone.name == "GRAVEYARD", (
            "the copy was pointed at the opponent's creature and killed it"
        )
        assert game.state.objects[mine[0]].zone.name == "GRAVEYARD", (
            "and the original still resolved where it was aimed"
        )

    def test_a_plain_copy_stays_where_the_original_pointed(self, builder):
        """The 706.10 default, unchanged: both hits land on the same creature."""
        game = board(builder, STORMCAT)
        theirs = opponent_creature(game)
        mine = my_bears(game)
        cast_zap(game, mine[0])
        run(game)
        assert game.state.objects[mine[0]].zone.name == "GRAVEYARD"
        assert game.state.objects[theirs].zone.name == "BATTLEFIELD", (
            "nothing moved the copy, so the opponent's creature was never touched"
        )


class TestTheLoaderRefusesItElsewhere:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_bad_copy",
                "name": "Bad Copy",
                "oracle_text": "Bad.",
                "mana_cost": "{U}",
                "types": ["Instant"],
                "colors": ["U"],
                "color_identity": ["U"],
                "spell_effects": [effect],
            }
        )

    def test_new_targets_on_another_op_is_a_load_error(self):
        with pytest.raises(DslError, match="new_targets"):
            compile_card(
                self._card({"op": "draw", "amount": {"const": 1}, "new_targets": True})
            )

    def test_a_non_boolean_is_a_load_error(self):
        with pytest.raises(DslError, match="boolean"):
            compile_card(self._card({"op": "copy_spell", "new_targets": "yes"}))
