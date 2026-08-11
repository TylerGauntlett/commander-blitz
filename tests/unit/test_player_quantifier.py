""""An opponent has 10 or less life" -- a question about *one* player.

Vampire Lacerator and Guul Draz Vampire are the shipped witnesses, and they ask
the same question from the two different condition languages: Lacerator from an
`if` inside a triggered ability, Guul Draz from a static's "as long as" clause.

The engine could already read a life total, and reading it was the trap.
`life_of` **sums** over its player spec, and `"opponent"` and `"each_opponent"`
are the same set, so `{"life_of": "opponent"} <= 10` means "my opponents'
COMBINED life is 10 or less". In a duel that is the printed card exactly. At a
Commander table it is a different card and the wrong way round: three opponents
at 4 life each sum to 12, so a summing Lacerator would drain its controller
against a table that is nearly dead, and a summing Guul Draz would stay a 1/1
while every opponent was in burn range.

This repo is multiplayer and Commander-first, so that is a divergence rather
than a rounding error -- which is why the fix is a leaf that asks about one
player at a time rather than a bigger `life_of`:

    {"min_life_of": "each_opponent"}   the existential, "an opponent has…"
    {"max_life_of": "each_opponent"}   the universal, "each opponent has…"

`min`/`max` already existed as value expressions, and could not help: they take
a literal list of value expressions written into the card, and no player spec
enumerates opponents one at a time to feed them.

Two things the tests below pin that are easy to get wrong and invisible on
screen:

- The **boundary**. "10 or less" includes 10 and excludes 11, in both languages.
- The **empty set**. With no opponents left, "an opponent has 10 or less life"
  must be false. A minimum over nothing that returned 0 would make it vacuously
  true and switch Lacerator's drawback off at the moment the last opponent
  died, so `NO_PLAYERS_LIFE` is a life total nothing reaches. `max_life_of` has
  the opposite bias on purpose: "each opponent has…" over nobody is vacuously
  true, and that reading is correct.

A static may ask this for the same reason it may count a zone: a life total is a
pipeline *input*. Nothing in the fixed-order characteristics pipeline can change
one, so no static can come to depend on another static's output through it --
the invariant `test_static_condition.py::TestItStaysAcyclic` exists to protect.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import NO_PLAYERS_LIFE, chars, min_life
from automtg.engine.enums import ActionKind, Keyword, Step
from automtg.engine.errors import DslError


def vampire(builder, lives: list[int]):
    """Guul Draz Vampire on the battlefield, with the table at these life totals."""
    game = builder(players=len(lives)).battlefield(0, ["guul_draz_vampire"]).build()
    for pid, life in enumerate(lives):
        game.state.players[pid].life = life
    game.state.bump_chars()
    oid = next(
        o
        for o in game.state.battlefield
        if game.state.objects[o].def_id == "guul_draz_vampire"
    )
    return game, oid


def lacerator_upkeep(builder, lives: list[int]) -> int:
    """Life lost by player 0 over one upkeep. Starts at UNTAP so it is not skipped."""
    game = (
        builder(players=len(lives))
        .battlefield(0, ["vampire_lacerator"])
        .library(0, ["forest"] * 10)
        .active(0)
        .step(Step.UNTAP)
        .build(advance=False)
    )
    for pid, life in enumerate(lives):
        game.state.players[pid].life = life
    game.state.bump_chars()
    before = game.state.players[0].life

    game._advance()
    for _ in range(80):
        if game.state.step is Step.DRAW:
            break
        if game.pending() is None:
            break
        passing = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.PASS), None
        )
        if passing is None:
            break
        game.apply(passing)
    return before - game.state.players[0].life


class TestTheStaticLanguage:
    def test_it_applies_when_one_opponent_is_low(self, builder):
        game, oid = vampire(builder, [40, 10])
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (3, 2)
        assert Keyword.INTIMIDATE.value in c.keywords

    def test_it_does_not_apply_when_nobody_is(self, builder):
        game, oid = vampire(builder, [40, 40])
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (1, 1)
        assert Keyword.INTIMIDATE.value not in c.keywords

    def test_the_boundary_is_ten_not_eleven(self, builder):
        game, oid = vampire(builder, [40, 11])
        assert chars(game.state, oid).power == 1, "11 is not '10 or less'"
        game, oid = vampire(builder, [40, 10])
        assert chars(game.state, oid).power == 3, "10 is"

    def test_it_asks_about_one_opponent_not_the_table(self, builder):
        # Three opponents at 4: any one of them satisfies the card, and their
        # sum (12) does not. This is the case a summing read gets backwards.
        game, oid = vampire(builder, [40, 4, 4, 4])
        assert chars(game.state, oid).power == 3, (
            "an opponent at 4 life is 'an opponent with 10 or less', whatever "
            "the rest of the table adds up to"
        )

    def test_one_low_opponent_among_healthy_ones_is_enough(self, builder):
        game, oid = vampire(builder, [40, 40, 40, 9])
        assert chars(game.state, oid).power == 3

    def test_a_healthy_table_still_does_not_trigger_it(self, builder):
        game, oid = vampire(builder, [40, 40, 40, 40])
        assert chars(game.state, oid).power == 1


class TestTheEffectLanguage:
    def test_it_drains_when_no_opponent_is_low(self, builder):
        assert lacerator_upkeep(builder, [40, 40]) == 1

    def test_it_does_not_drain_when_one_is(self, builder):
        assert lacerator_upkeep(builder, [40, 10]) == 0

    def test_the_boundary_is_ten_not_eleven(self, builder):
        assert lacerator_upkeep(builder, [40, 11]) == 1, "11 is not '10 or less'"
        assert lacerator_upkeep(builder, [40, 10]) == 0, "10 is"

    def test_a_nearly_dead_pod_stops_the_drain(self, builder):
        # Summing would read 4+4+4 = 12, decide nobody is low, and drain.
        assert lacerator_upkeep(builder, [40, 4, 4, 4]) == 0

    def test_a_healthy_pod_still_drains(self, builder):
        assert lacerator_upkeep(builder, [40, 40, 40, 40]) == 1


class TestTheEmptySet:
    def test_a_minimum_over_nobody_is_not_zero(self):
        assert min_life([]) == NO_PLAYERS_LIFE
        assert min_life([]) > 10, (
            "'an opponent has 10 or less life' must be FALSE with no opponents; "
            "a minimum of 0 would make it vacuously true"
        )

    def test_it_is_still_a_minimum_when_there_is_somebody(self):
        assert min_life([40, 4, 12]) == 4


class TestTheLoaderMirrors:
    """Both languages, or a card loads and lies.

    The static condition language is validated separately from the effect one,
    so a leaf added to only one of them would load in a card that then read 0.
    """

    def probe(self, left: dict) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "As long as an opponent has 10 or less life, this creature gets +1/+0.",
            "mana_cost": "{B}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "static",
                    "text": "As long as an opponent has 10 or less life, this creature gets +1/+0.",
                    "effect": "buff",
                    "affects": {"self_only": True},
                    "power": {"const": 1},
                    "toughness": {"const": 0},
                    "condition": {"cmp": "<=", "left": left, "right": {"const": 10}},
                }
            ],
        }

    def test_a_static_may_ask_it(self):
        compile_card(CardModel.model_validate(self.probe({"min_life_of": "each_opponent"})))

    def test_a_static_may_not_name_an_unknown_player_spec(self):
        with pytest.raises(DslError, match="min_life_of"):
            compile_card(CardModel.model_validate(self.probe({"min_life_of": "the_monarch"})))

    def test_a_static_still_may_not_use_the_summing_leaf(self):
        # `life_of` is deliberately absent from the static language: it would
        # read the whole table as one number and there is no card that wants it.
        with pytest.raises(DslError, match="static values"):
            compile_card(CardModel.model_validate(self.probe({"life_of": "opponent"})))
