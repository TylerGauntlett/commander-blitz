"""Copying a spell with an exception (707.9b, 707.10): `copy_spell`'s ``except_``.

    Donal, Herald of Wings -- "Whenever you cast a nonlegendary creature spell
    with flying, you may copy it, except the copy is a 1/1 Spirit in addition
    to its other types. Do this only once each turn. (The copy becomes a
    token.)"

Rule 707.10 makes a copy of a spell copy the original's copiable values, and
707.9b lets the copying effect change some of them: the exception *becomes*
part of the copy's copiable values. 707.10c and 608.3f then put a copy of a
permanent spell onto the battlefield as a token -- the same object -- so the
token is a 1/1 Spirit too, not the full-sized original. Without ``except_`` the
copy was the original verbatim (`put_copy_on_stack`), so Donal's copy of a 5/5
Dragon was a second 5/5 Dragon: a far stronger card than the printed one.

The exception is `copy_permanent`'s vocabulary, written onto the copy's token
object as its ``copy_overrides``. `t_wing_herald` is Donal's trigger without
the once-each-turn limit, which the authored card writes with a turn flag.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, action_for_card, pt

HERALD = "t_wing_herald"
FLIER = "t_flier"  # {2}{U} 2/2 Bird with flying
JUDGE = "t_judge"  # {2}{W}{U} legendary 3/5 Sphinx with flying
BEARS = "grizzly_bears"  # no flying


def board(builder, hand=(FLIER,)):
    """The herald on your side with mana for one spell; the opponent holds a
    bolt so a cast spell does not resolve inside the `apply` that cast it."""
    return (
        builder(players=2)
        .battlefield(0, [HERALD, "plains", "forest", "island", "island", "island"])
        .hand(0, list(hand))
        .hand(1, ["t_bolt"])
        .battlefield(1, ["mountain"])
        .build()
    )


def answer(game, *, copy: bool, until=None, limit: int = 300) -> list[str]:
    """Resolve, saying `copy` to every "copy that spell?", until `until(game)`
    holds or the stack is empty. Returns the MAY prompts the table saw."""
    asked: list[str] = []
    for _ in range(limit):
        if until is not None and until(game):
            return asked
        decision = game.pending()
        if decision is None:
            return asked
        if decision.kind is DecisionKind.MAY:
            asked.append("may")
            wanted = ActionKind.YES if copy else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is wanted))
            continue
        if not game.state.stack and not game.state.pending_triggers:
            return asked
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def copy_on_stack(game):
    return next(
        (it for it in game.state.stack if it.is_spell and game.state.objects[it.oid].is_token),
        None,
    )


def fliers_on_battlefield(game, card_id: str = FLIER):
    return [o for o in game.state.battlefield_objects(0) if o.def_id == card_id]


class TestTheCopyIsExcepted:
    def test_the_copy_on_the_stack_is_a_1_1_spirit(self, builder):
        """707.10: the exception is part of the copy as a spell, before it resolves."""
        game = board(builder)
        game.apply(action_for_card(game, ActionKind.CAST, FLIER))
        answer(game, copy=True, until=lambda g: copy_on_stack(g) is not None)
        item = copy_on_stack(game)
        assert item is not None
        assert game.state.objects[item.oid].zone is Zone.STACK
        c = chars(game.state, item.oid)
        assert (c.power, c.toughness) == (1, 1)
        assert {"Bird", "Spirit"} <= set(c.subtypes)
        assert "Creature" in c.types

    def test_the_copy_resolves_into_a_1_1_spirit_token(self, builder):
        """707.10c, 608.3f: the token keeps the exception, in addition to its types."""
        game = board(builder)
        game.apply(action_for_card(game, ActionKind.CAST, FLIER))
        answer(game, copy=True)
        tokens = [o for o in fliers_on_battlefield(game) if o.is_token]
        assert len(tokens) == 1
        c = chars(game.state, tokens[0].oid)
        assert (c.power, c.toughness) == (1, 1)
        assert {"Bird", "Spirit"} <= set(c.subtypes)
        assert "Creature" in c.types
        assert "flying" in {str(k) for k in c.keywords}

    def test_the_original_resolves_unchanged(self, builder):
        game = board(builder)
        game.apply(action_for_card(game, ActionKind.CAST, FLIER))
        answer(game, copy=True)
        cards = [o for o in fliers_on_battlefield(game) if not o.is_token]
        assert len(cards) == 1
        c = chars(game.state, cards[0].oid)
        assert (c.power, c.toughness) == (2, 2)
        assert "Spirit" not in set(c.subtypes)

    def test_declining_makes_no_copy(self, builder):
        game = board(builder)
        game.apply(action_for_card(game, ActionKind.CAST, FLIER))
        assert answer(game, copy=False) == ["may"]
        assert [o.is_token for o in fliers_on_battlefield(game)] == [False]

    def test_the_token_leaving_takes_the_exception_with_it(self, builder):
        """The exception is on the token object, not a rule about the card: the
        original card in the graveyard is still a 2/2 Bird."""
        game = board(builder)
        game.apply(action_for_card(game, ActionKind.CAST, FLIER))
        answer(game, copy=True)
        token = next(o for o in fliers_on_battlefield(game) if o.is_token)
        assert token.copy_overrides is not None
        card = next(o for o in fliers_on_battlefield(game) if not o.is_token)
        assert card.copy_overrides is None


class TestTheTriggerFilter:
    def test_a_legendary_flier_does_not_trigger(self, builder):
        game = board(builder, hand=(JUDGE,))
        game.apply(action_for_card(game, ActionKind.CAST, JUDGE))
        assert answer(game, copy=True) == []
        assert [o.is_token for o in fliers_on_battlefield(game, JUDGE)] == [False]

    def test_a_creature_without_flying_does_not_trigger(self, builder):
        game = board(builder, hand=(BEARS,))
        game.apply(action_for_card(game, ActionKind.CAST, BEARS))
        assert answer(game, copy=True) == []
        assert not any(o.is_token for o in game.state.battlefield_objects(0))


class TestTheLoader:
    def _card(self, effect) -> CardModel:
        return CardModel(
            id="t_copy_except_probe",
            name="Copy Except Probe",
            mana_cost="{U}",
            types=["Instant"],
            targets=[{"id": "t1", "kind": "spell"}],
            spell_effects=[effect],
        )

    def test_the_witness_loads(self):
        compile_card(
            self._card(
                {
                    "op": "copy_spell",
                    "target": "t1",
                    "except_": {"power": 1, "toughness": 1, "add_subtypes": ["Spirit"]},
                }
            )
        )

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(
                self._card({"op": "copy_spell", "target": "t1", "except_": {"is_spirit": True}})
            )

    def test_half_a_size_is_refused(self):
        with pytest.raises(DslError, match="pair"):
            compile_card(self._card({"op": "copy_spell", "target": "t1", "except_": {"power": 1}}))

    def test_an_empty_exception_is_refused(self):
        with pytest.raises(DslError, match="empty"):
            compile_card(self._card({"op": "copy_spell", "target": "t1", "except_": {}}))



class TestTheWitness:
    def test_donal_copies_only_once_each_turn(self, builder):
        """The authored card: the second flier this turn is not offered a copy."""
        game = (
            builder(players=2)
            .battlefield(0, ["donal_herald_of_wings"] + ["island"] * 6)
            .hand(0, [FLIER, FLIER])
            .hand(1, ["t_bolt"])
            .battlefield(1, ["mountain"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, FLIER))
        assert answer(game, copy=True) == ["may"]
        game.apply(action_for_card(game, ActionKind.CAST, FLIER))
        assert answer(game, copy=True) == []
        tokens = [o for o in fliers_on_battlefield(game) if o.is_token]
        assert len(tokens) == 1
        assert pt(game, tokens[0].oid) == (1, 1)
