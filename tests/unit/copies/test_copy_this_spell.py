""""You may copy this spell" said by the resolving spell itself.

    Sevinne's Reclamation — "Return target permanent card with mana value 3 or
    less from your graveyard to the battlefield. If this spell was cast from a
    graveyard, you may copy this spell and may choose a new target for the
    copy. Flashback {4}{W}"

Rule 707.10: a copy of a spell is put on the stack, copying the original's
characteristics and the choices made for it -- targets, X, modes, additional
costs -- and 707.10c's "may choose new targets" lets its controller re-aim it.
The copy here is an instruction *in the spell's own text*, so it is made as the
spell resolves: a countered original makes no copy, which is what separates
the card from a storm-shaped cast trigger that copies on cast.

Without `this_spell` the clause was unsayable. `copy_spell` finds its original
on the stack, and `stack.resolve_top` has already taken the resolving spell off
it, so a `copy_spell` in `spell_effects` copied nothing. `this_spell` names the
resolving item itself (`EffectContext.resolving_spell`), its last-known
targets and choices. The copy was never cast, so it was not cast from a
graveyard and does not offer to copy itself again; it is a token, so the
flashback card is the only card exiled. `t_self_reclaim` is the witness at a
one-mana price.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

RECLAIM = "t_self_reclaim"
BEARS = "grizzly_bears"
ELVES = "llanowar_elves"
COUNTER = "t_counterspell"


def board(builder, *, from_graveyard: bool = True, counter: bool = False):
    """You hold or bin the reclaim spell; two small creatures wait in your graveyard."""
    b = builder(players=2).battlefield(0, ["plains"] * 2).graveyard(0, [BEARS, ELVES])
    b = b.graveyard(0, [RECLAIM]) if from_graveyard else b.hand(0, [RECLAIM])
    if counter:
        b = b.battlefield(1, ["island"] * 2).hand(1, [COUNTER])
    return b.build()


def oid_in_graveyard(game, card_id: str) -> int:
    return next(
        oid for oid in game.state.players[0].graveyard if game.state.objects[oid].def_id == card_id
    )


def cast_at(game, card_id: str) -> None:
    """Cast the reclaim spell (from hand or by flashback) targeting one card."""
    target = oid_in_graveyard(game, card_id)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == RECLAIM
            and a.targets
            and a.targets[0].id == target
        )
    )


def run(game, *, copy: bool, retarget_to: str | None = None, counter: bool = False):
    """Resolve everything, recording the prompts the table was asked."""
    asked: list[str] = []
    for _ in range(300):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.MAY:
            asked.append("may")
            kind = ActionKind.YES if copy else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is kind))
            continue
        if decision.kind is DecisionKind.CHOOSE_MODE and "New targets" in (decision.prompt or ""):
            asked.append("new_targets")
            want = next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE
                and retarget_to is not None
                and retarget_to in (decision.options[a.choice].label or "")
            )
            game.apply(want)
            continue
        if counter and decision.kind is DecisionKind.PRIORITY and decision.player == 1:
            cast = [
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == COUNTER
            ]
            if cast:
                game.apply(cast[0])
                continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    return asked


def on_battlefield(game) -> list[str]:
    return sorted(o.def_id for o in game.state.battlefield_objects(0) if o.def_id in (BEARS, ELVES))


class TestTheCopy:
    def test_flashback_copy_returns_a_second_card(self, builder):
        game = board(builder)
        cast_at(game, BEARS)
        asked = run(game, copy=True, retarget_to="Llanowar")
        assert asked == ["may", "new_targets"]
        assert on_battlefield(game) == [BEARS, ELVES]

    def test_the_card_alone_is_exiled_and_the_copy_is_gone(self, builder):
        """Flashback exiles the card; the copy is a token that ceases to exist."""
        game = board(builder)
        cast_at(game, BEARS)
        run(game, copy=True, retarget_to="Llanowar")
        exiled = [game.state.objects[oid].def_id for oid in game.state.players[0].exile]
        assert exiled == [RECLAIM]
        assert RECLAIM not in [game.state.objects[o].def_id for o in game.state.players[0].graveyard]
        assert not any(
            o.def_id == RECLAIM and o.zone is not Zone.EXILE for o in game.state.objects.values()
        )

    def test_the_copy_is_not_cast_from_a_graveyard(self, builder):
        """It is asked once: the copy resolving does not offer another copy."""
        game = board(builder)
        cast_at(game, BEARS)
        assert run(game, copy=True, retarget_to="Llanowar").count("may") == 1

    def test_keeping_the_old_target_returns_nothing_more(self, builder):
        """The copy keeps the original's target, now on the battlefield: 608.2b."""
        game = board(builder)
        cast_at(game, BEARS)
        run(game, copy=True, retarget_to="Grizzly")
        assert on_battlefield(game) == [BEARS]
        assert game.state.objects[oid_in_graveyard(game, ELVES)].zone is Zone.GRAVEYARD


class TestWhenTheCopyIsNotMade:
    def test_declining_makes_no_copy(self, builder):
        game = board(builder)
        cast_at(game, BEARS)
        assert run(game, copy=False) == ["may"]
        assert on_battlefield(game) == [BEARS]

    def test_cast_from_hand_is_not_asked(self, builder):
        game = board(builder, from_graveyard=False)
        cast_at(game, BEARS)
        assert run(game, copy=True) == []
        assert on_battlefield(game) == [BEARS]

    def test_nothing_is_copied_as_it_is_cast(self, builder):
        """The copy is made on resolution, so only the spell is on the stack.

        An opponent holding a counterspell, so priority stops with it there.
        """
        game = board(builder, counter=True)
        cast_at(game, BEARS)
        assert [item.def_id for item in game.state.stack] == [RECLAIM]

    def test_a_countered_original_makes_no_copy(self, builder):
        game = board(builder, counter=True)
        cast_at(game, BEARS)
        assert run(game, copy=True, retarget_to="Llanowar", counter=True) == []
        assert on_battlefield(game) == []


class TestLoaderRefusals:
    def _card(self, effect, **extra) -> CardModel:
        return CardModel(
            id="t_this_spell_probe",
            name="This Spell Probe",
            mana_cost="{U}",
            types=["Instant"],
            spell_effects=[effect],
            **extra,
        )

    def test_this_spell_on_another_op(self):
        with pytest.raises(DslError, match="this_spell"):
            compile_card(self._card({"op": "draw", "amount": {"const": 1}, "this_spell": True}))

    def test_this_spell_beside_sid(self):
        with pytest.raises(DslError, match="replaces"):
            compile_card(
                self._card({"op": "copy_spell", "this_spell": True, "sid": {"binding": "sid"}})
            )

    def test_this_spell_must_be_true(self):
        with pytest.raises(DslError, match="this_spell"):
            compile_card(self._card({"op": "copy_spell", "this_spell": "yes"}))

    def test_this_spell_outside_spell_effects(self):
        ability = {
            "kind": "activated",
            "cost": {"mana": "{1}"},
            "effects": [{"op": "copy_spell", "this_spell": True}],
        }
        model = CardModel(
            id="t_this_spell_probe",
            name="This Spell Probe",
            mana_cost="{U}",
            types=["Artifact"],
            abilities=[ability],
        )
        with pytest.raises(DslError, match="spell_effects"):
            compile_card(model)

    def test_the_witness_loads(self):
        compile_card(self._card({"op": "copy_spell", "this_spell": True, "new_targets": True}))
