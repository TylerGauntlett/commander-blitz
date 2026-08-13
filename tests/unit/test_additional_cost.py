"""Casualty and replicate — an additional cost that is not mana.

    Casualty 2 — "As an additional cost to cast this spell, you may sacrifice a
    creature with power 2 or greater. When you do, copy this spell."
    Replicate {1} — "…you may pay an additional {1} any number of times. When
    you cast this spell, copy it for each time you paid."

`kicker` is the only additional cost a hand-cast spell could carry, and it is
wrong twice over for both of these: it is **mana-only** — `_cast_variant`
computes `mana_cost.plus(kicker)`, a `ManaCost`, which cannot sacrifice
anything — and it is paid **once**.

So `additional_cost` is a full `Cost`, and legality offers **one cast line per
number of times paid**, which is convoke's shape rather than kicker's: the count
changes the price, and it is the player's to choose.

Three things the modifiers decide, and each is a different printed card:

| | |
|---|---|
| neither | Deadly Dispute — "sacrifice an artifact or creature", mandatory |
| `additional_optional` | casualty — "you **may** sacrifice" |
| both | replicate — "any number of times", which includes none |

Moving the payment into `spell_effects` is the approximation the DSL notes
forbid, and it fails in a way nothing on screen would show: the spell could be
cast with no creature to sacrifice and would still draw the card.

**The copy needs no new machinery.** "When you cast this spell" is a
`spell_cast` trigger with `active_zones: ["stack"]`, which already ships — so
the trigger goes on the stack *above* the spell and its copy resolves first,
which is what rule 706.10 wants and what a `copy_spell` inside `spell_effects`
would get backwards.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Zone
from tests.conftest import pass_until

SWAMP = "swamp"
MOUNTAIN = "mountain"
CASUALTY = "t_casualty"     # {1}{B} sorcery, casualty 2, draws a card
REPLICATE = "t_replicate"   # {R} instant, replicate {1}, 1 damage
BEAR = "t_bear"             # 2/2 -- power 2, so legal casualty fodder
DORK = "t_dork"             # 1/1 -- power 1, so not


def casualty_board(builder, *creatures: str):
    return (
        builder(players=2)
        .battlefield(0, [SWAMP] * 3)
        .battlefield(0, list(creatures))
        .hand(0, [CASUALTY])
        .library(0, [SWAMP] * 20)
        .library(1, [SWAMP] * 20)
        .build()
    )


def replicate_board(builder, lands: int):
    return (
        builder(players=2)
        .battlefield(0, [MOUNTAIN] * lands)
        .hand(0, [REPLICATE])
        .library(0, [MOUNTAIN] * 20)
        .library(1, [MOUNTAIN] * 20)
        .build()
    )


def lines(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
    ]


class TestCasualty:
    def test_both_lines_are_offered_with_legal_fodder(self, builder):
        game = casualty_board(builder, BEAR)
        counts = sorted({a.additional_times for a in lines(game, CASUALTY)})
        assert counts == [0, 1], "pay it, or do not"

    def test_only_the_free_line_is_offered_with_no_fodder(self, builder):
        game = casualty_board(builder)
        counts = sorted({a.additional_times for a in lines(game, CASUALTY)})
        assert counts == [0]

    def test_a_creature_too_small_is_not_fodder(self, builder):
        """The selector's own `power` clause -- casualty 2 needs power 2."""
        game = casualty_board(builder, DORK)
        counts = sorted({a.additional_times for a in lines(game, CASUALTY)})
        assert counts == [0]

    def test_paying_it_sacrifices_the_creature(self, builder):
        game = casualty_board(builder, BEAR)
        bear = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
        game.apply(next(a for a in lines(game, CASUALTY) if a.additional_times == 1))
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_paying_it_copies_the_spell(self, builder):
        game = casualty_board(builder, BEAR)
        hand = len(game.state.players[0].hand)
        game.apply(next(a for a in lines(game, CASUALTY) if a.additional_times == 1))
        pass_until(game, lambda g: not g.state.stack)

        # Cast one, drew two: the copy and the original.
        assert len(game.state.players[0].hand) == hand - 1 + 2

    def test_declining_copies_nothing(self, builder):
        game = casualty_board(builder, BEAR)
        hand = len(game.state.players[0].hand)
        bear = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
        game.apply(next(a for a in lines(game, CASUALTY) if a.additional_times == 0))
        pass_until(game, lambda g: not g.state.stack)

        assert len(game.state.players[0].hand) == hand - 1 + 1
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD


class TestReplicate:
    def test_one_line_per_number_of_times_paid(self, builder):
        """Convoke's shape: the count changes the price and is the player's."""
        game = replicate_board(builder, lands=3)
        counts = sorted({a.additional_times for a in lines(game, REPLICATE)})
        assert counts == [0, 1, 2], "{R}, {R}{1}, {R}{1}{1}"

    def test_the_mana_is_really_charged(self, builder):
        game = replicate_board(builder, lands=1)
        counts = sorted({a.additional_times for a in lines(game, REPLICATE)})
        assert counts == [0], "one Mountain pays {R} and nothing more"

    def test_the_number_of_copies_is_the_number_paid(self, builder):
        game = replicate_board(builder, lands=3)
        life = game.state.players[1].life
        action = next(
            a
            for a in lines(game, REPLICATE)
            if a.additional_times == 2
            and any(t.kind == "player" and t.id == 1 for t in a.targets)
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.players[1].life == life - 3, "the original and two copies"

    def test_paying_none_copies_nothing(self, builder):
        game = replicate_board(builder, lands=3)
        life = game.state.players[1].life
        action = next(
            a
            for a in lines(game, REPLICATE)
            if a.additional_times == 0
            and any(t.kind == "player" and t.id == 1 for t in a.targets)
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.players[1].life == life - 1


class TestAMandatoryCost:
    """Deadly Dispute's shape: neither modifier, so the free line is withdrawn."""

    def _card(self, **extra) -> CardModel:
        base = {
            "id": "t_mandatory_probe",
            "name": "Mandatory Probe",
            "mana_cost": "{1}{B}",
            "types": ["Sorcery"],
            "additional_cost": {"sacrifice": {"controller": "you", "types": ["Creature"]}},
            "spell_effects": [{"op": "draw", "player": "you"}],
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def test_it_loads_with_nothing_reading_it(self):
        """Unlike kicker: "sacrifice an artifact" is the whole cost, read by nobody."""
        compile_card(self._card())

    def test_the_modifiers_need_a_cost(self):
        with pytest.raises(DslError, match="need an 'additional_cost'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_probe2",
                        "name": "Probe 2",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "additional_optional": True,
                        "spell_effects": [{"op": "draw", "player": "you"}],
                    }
                )
            )

    def test_repeatable_needs_optional(self):
        """"Any number of times" includes none."""
        with pytest.raises(DslError, match="includes none"):
            compile_card(self._card(additional_repeatable=True))

    def test_reading_the_count_without_a_cost_is_refused(self):
        with pytest.raises(DslError, match="reads 'additional_paid'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_probe3",
                        "name": "Probe 3",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "spell_effects": [
                            {
                                "op": "if",
                                "condition": {
                                    "cmp": ">=",
                                    "left": {"additional_paid": True},
                                    "right": {"const": 1},
                                },
                                "then": [{"op": "draw", "player": "you"}],
                            }
                        ],
                    }
                )
            )
