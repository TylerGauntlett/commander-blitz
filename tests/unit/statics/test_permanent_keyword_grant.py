"""Riot (702.135), and the duration `grant_keyword` did not have.

The census blamed the wrong half. It routes riot as "`self_enters` +
`choose_mode`, but a `choose_mode` inside a trigger resolves late" — and the
mode *selection* works, which is what this file is about.

**Riot itself is no longer written that way**, and the late resolution turned
out not to be fine: 614.1c says the creature is never on the battlefield at its
printed size, which a trigger cannot promise however it is ordered. Riot is now a
`Keyword` applied during the arrival — see `tests/unit/keywords/test_riot.py`, which makes
that argument, and `zones.offer_riot_choice`, which asks the question. `t_rioter`
stays as it is on purpose: it is this file's witness for the **duration**, and
the trigger shape is the honest way to isolate that from the replacement.

What did not work is the **haste**. `grant_keyword` had exactly one duration:
it appends an `until_eot` `TempEffect`, swept by `clear_until_eot` at cleanup.
Riot's haste is not until end of turn — it is part of what the creature is for
as long as it is on the battlefield.

That difference is invisible on the turn the creature arrives and total
afterwards. An until-end-of-turn haste lets it attack the turn it entered, then
silently evaporates; from the next turn on, a riot creature that chose haste is
indistinguishable from one that chose the counter. Not a smaller version of the
card — the wrong one, half the time, starting one turn later.

So `granted_keywords` is a set on the object rather than a `TempEffect`, for
exactly the reason `hasted_by_suspend` is a field: only one of the two is swept
at cleanup. It resets with the rest of the battlefield state, because a
permanent that leaves and returns makes the choice again.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import grant_keyword
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, action_for_card, only_oid, pass_until

RIOTER = "t_rioter"  # 2/2; enters with a +1/+1 counter or with haste
BEAR = "t_bear"

COUNTER_MODE = 0
HASTE_MODE = 1


def cast_riot(builder, mode: int):
    """Cast the rioter and take `mode` when the choice is offered."""
    game = (
        builder(players=2).hand(0, [RIOTER]).battlefield(0, ["mountain"] * 3).build()
    )
    game.apply(action_for_card(game, ActionKind.CAST, RIOTER))
    for _ in range(20):
        decision = game.pending()
        if decision is not None and decision.kind is not DecisionKind.PRIORITY:
            choices = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
            game.apply(choices[mode] if len(choices) > mode else game.legal_actions()[0])
            continue
        if not game.state.stack and not game.state.pending_triggers:
            break
        if decision is None:
            game._advance()
        else:
            game.apply(_default_answer(game, decision))
    return game, only_oid(game, RIOTER, 0)


class TestBothModes:
    def test_the_counter_mode_grows_it(self, builder):
        game, oid = cast_riot(builder, COUNTER_MODE)
        assert chars(game.state, oid).power == 3
        assert "haste" not in chars(game.state, oid).keywords

    def test_the_haste_mode_grants_haste(self, builder):
        game, oid = cast_riot(builder, HASTE_MODE)
        assert "haste" in chars(game.state, oid).keywords
        assert chars(game.state, oid).power == 2

    def test_it_is_one_or_the_other(self, builder):
        game, oid = cast_riot(builder, COUNTER_MODE)
        c = chars(game.state, oid)
        assert (c.power, "haste" in c.keywords) == (3, False)


class TestTheHasteLasts:
    def test_it_survives_end_of_turn(self, builder):
        """The whole point of the new duration. An `until_eot` haste is gone by
        the next turn, when a riot creature that chose haste would be
        indistinguishable from one that chose the counter."""
        game, oid = cast_riot(builder, HASTE_MODE)
        pass_until(game, lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert "haste" in chars(game.state, oid).keywords

    def test_an_ordinary_grant_does_not(self, builder):
        """The default is unchanged, so no shipped card moved."""
        game = builder(players=2).battlefield(0, [BEAR]).build()
        oid = only_oid(game, BEAR, 0)
        grant_keyword(game.state, oid, "haste")
        assert "haste" in chars(game.state, oid).keywords
        pass_until(game, lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert "haste" not in chars(game.state, oid).keywords

    def test_leaving_the_battlefield_clears_it(self, builder):
        """A permanent that returns makes the choice again (400.7)."""
        game, oid = cast_riot(builder, HASTE_MODE)
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert game.state.objects[oid].granted_keywords == set()


class TestThePrimitive:
    def test_permanent_and_temporary_land_in_different_places(self, builder):
        game = builder(players=2).battlefield(0, [BEAR]).build()
        oid = only_oid(game, BEAR, 0)
        grant_keyword(game.state, oid, "flying", permanent=True)
        grant_keyword(game.state, oid, "trample")
        obj = game.state.objects[oid]
        assert obj.granted_keywords == {"flying"}
        assert [t.keyword for t in obj.until_eot] == ["trample"]
        assert {"flying", "trample"} <= chars(game.state, oid).keywords


class TestTheLoaderGuardsTheDuration:
    def base(self, duration: str) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{R}",
            "types": ["Sorcery"],
            "spell_effects": [
                {
                    "op": "grant_keyword",
                    "keyword": "haste",
                    "duration": duration,
                    "objects": {"controller": "you", "types": ["Creature"]},
                }
            ],
        }

    def test_a_misspelled_duration_is_refused(self):
        """It would fall back to until-end-of-turn, which is the *wrong half*
        of riot rather than a smaller version of it."""
        with pytest.raises(DslError, match="unknown grant_keyword duration"):
            compile_card(CardModel.model_validate(self.base("forever")))

    def test_both_spellings_compile(self):
        for duration in ("permanent", "until_end_of_turn"):
            compile_card(CardModel.model_validate(self.base(duration)))

    def test_the_riot_card_compiles(self, registry):
        card = registry.get(RIOTER)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        (mode_spec,) = ability.effects
        assert mode_spec["op"] == "choose_mode"
        haste = mode_spec["modes"][HASTE_MODE]["effects"][0]
        assert haste["duration"] == "permanent"
