""""Any number of target opponents" owned by a mode that is **not** the last
one owning a target -- 601.2b, 601.2c, 608.2b.

    Will of the Abzan -- "Choose one. If you control a commander as you cast
    this spell, you may choose both instead.
    * Any number of target opponents each sacrifice a creature with the
      greatest power among creatures that player controls and lose 3 life.
    * Return target creature card from your graveyard to the battlefield."

The first bullet's target is caster-sized and the second bullet owns a target
of its own. The stored refs are one flat tuple that `targeting.filter_legal`
splits spec by spec, and a caster-sized spec stores as many refs as were
picked -- so laid out in printed mode order, the opponents would swallow the
graveyard card's ref and the second bullet would read nothing back.

`carddef._specs_for_modes` therefore stores a declaration's fixed-size specs
first, in printed mode order, and the one `optional` or caster-sized mode-owned
spec a card may carry **last**, whichever mode owns it. The question is still
asked in the printed order; only the storage moves, and every reader of the
stored refs -- the cast, a trigger's enumeration, 608.2b's re-check, the
division of damage -- walks the same list. The loader admits one such spec per
card (two would need a split no position can give) and refuses one a sibling's
selector names, which would be enumerated before what it reads.

Each nearer spelling is a different card: a fixed ``count`` on the opponents
turns "any number" into an exact number, and lifting the graveyard target to
the card level forces it to be declared when only the first bullet is chosen.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import stack
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card

WILL = "t_abzan_will"
BEAR = "t_bear"  # 2/2
BIG = "t_big"  # 6/6
DORK = "t_dork"  # 1/1
SAC = 0
RETURN = 1


def board(builder, *, commander: bool = True, buried=(DORK,)):
    """Three seats: player 0 casts, players 1 and 2 each control a bear and a
    six-drop. Player 0's commander (a bear) is on the battlefield when
    ``commander`` holds."""
    game = (
        builder(players=3)
        .battlefield(0, ["swamp"] * 2 + [BEAR])
        .hand(0, [WILL])
        .graveyard(0, list(buried))
        .battlefield(1, [BEAR, BIG])
        .battlefield(2, [BEAR, BIG])
    )
    for pid in range(3):
        game = game.library(pid, ["swamp"] * 10)
    game = game.build()
    if commander:
        mine = next(
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].controller == 0
            and game.state.objects[oid].def_id == BEAR
        )
        game.state.objects[mine].is_commander = True
    return game


def cast(game, modes: list[int]) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, WILL))
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_MODE
    for mode in modes:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == mode
            )
        )
    if game.pending() is decision:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


def pick(game, ids: list[int]) -> None:
    """Answer one target question with ``ids`` (player seats or object ids)."""
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_OBJECTS, decision
    for wanted in ids:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.targets and a.targets[0].id == wanted
            )
        )
    if game.pending() is decision:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


def resolve(game) -> None:
    for _ in range(40):
        if not game.state.stack:
            return
        decision = game.pending()
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.PASS)
            if decision.kind is DecisionKind.PRIORITY
            else game.legal_actions()[0]
        )
    raise AssertionError("the spell never resolved")


def creatures_of(game, pid: int) -> list[str]:
    return sorted(
        game.state.objects[oid].def_id
        for oid in game.state.battlefield
        if game.state.objects[oid].controller == pid
        and "Creature" in game.state.card(oid).types
    )


def buried(game) -> int:
    """The one creature card in player 0's graveyard, before the cast."""
    (dork,) = game.state.players[0].graveyard
    return dork


def life(game, pid: int) -> int:
    return game.state.players[pid].life


class TestBothModes:
    def test_each_bucket_gets_its_own_refs(self, builder):
        """Two opponents in the first bullet, the dork in the second: each
        opponent loses its six-drop and 3 life, and the dork comes back."""
        game = board(builder)
        dork = buried(game)
        before = [life(game, pid) for pid in range(3)]
        cast(game, [SAC, RETURN])
        pick(game, [1, 2])
        resolve(game)
        assert creatures_of(game, 1) == [BEAR]
        assert creatures_of(game, 2) == [BEAR]
        assert life(game, 1) == before[1] - 3
        assert life(game, 2) == before[2] - 3
        assert dork in game.state.battlefield

    @pytest.mark.parametrize("foes", [[], [2]])
    def test_any_number_includes_fewer(self, builder, foes):
        """Zero or one opponent: the graveyard card's ref still lands in its
        own bucket rather than in the opponents'."""
        game = board(builder)
        dork = buried(game)
        before = life(game, 1)
        cast(game, [SAC, RETURN])
        pick(game, foes)
        resolve(game)
        assert dork in game.state.battlefield
        assert creatures_of(game, 1) == [BEAR, BIG]
        assert life(game, 1) == before
        if foes:
            assert creatures_of(game, 2) == [BEAR]

    def test_the_refs_are_stored_fixed_first(self, builder, monkeypatch):
        """The storage order every reader shares: the graveyard card, then the
        opponents, though the opponents were asked about first."""
        seen = []
        real = stack.filter_legal

        def spy(state, controller, specs, refs, *args, **kwargs):
            seen.append(([spec.id for spec in specs], [ref.id for ref in refs]))
            return real(state, controller, specs, refs, *args, **kwargs)

        monkeypatch.setattr(stack, "filter_legal", spy)
        game = board(builder)
        dork = buried(game)
        cast(game, [SAC, RETURN])
        pick(game, [1, 2])
        resolve(game)
        assert seen == [(["back", "foes"], [dork, 1, 2])]


class TestOneMode:
    def test_without_a_commander_the_first_bullet_alone(self, builder):
        game = board(builder, commander=False)
        before = life(game, 2)
        cast(game, [SAC])
        pick(game, [2])
        resolve(game)
        assert creatures_of(game, 2) == [BEAR]
        assert life(game, 2) == before - 3
        assert creatures_of(game, 1) == [BEAR, BIG]

    def test_the_second_bullet_alone(self, builder):
        game = board(builder, commander=False)
        dork = buried(game)
        cast(game, [RETURN])
        resolve(game)
        assert dork in game.state.battlefield
        assert creatures_of(game, 1) == [BEAR, BIG]


def json_card() -> dict:
    path = Path(__file__).resolve().parents[2] / "data" / "modal_variable_size_targets.cards.json"
    cards = json.loads(path.read_text(encoding="utf-8"))["cards"]
    return copy.deepcopy(next(card for card in cards if card["id"] == WILL))


def compile_(card) -> None:
    compile_card(CardModel.model_validate(card))


class TestTheLoaderBoundary:
    def test_the_card_loads(self):
        compile_(json_card())

    def test_two_sizeless_mode_targets_are_refused(self):
        """Choose both, and two caster-picked sizes share one flat tuple with
        nothing to say where the first ends."""
        card = json_card()
        card["targets"][1]["optional"] = True
        with pytest.raises(DslError, match="one 'optional' or caster-sized"):
            compile_(card)

    def test_a_sibling_naming_it_is_refused(self):
        """Stored last, it would be enumerated after the spec that reads it."""
        card = json_card()
        card["targets"][1]["selector"]["owner"] = {"target": "foes"}
        with pytest.raises(DslError, match="its selector names 'foes'"):
            compile_(card)
