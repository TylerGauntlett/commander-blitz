"""Emerge, and the trigger that fires while its own card is still a spell.

    Elder Deep-Fiend — "Flash. Emerge {5}{U}{U} (You may cast this spell by
    sacrificing a creature and paying the emerge cost reduced by that creature's
    mana value.) When you cast this spell, tap up to four target permanents."

Two capabilities that arrive together because the card needs both.

**Emerge** is a third alternative cost, and unlike `evoke` its price is not
fixed: it depends on *which* creature is sacrificed. So legality offers one line
per sacrificeable creature rather than one line with a flag — the same reason
kicked and unkicked are two actions, except the choice changes the number.

**The cast trigger** is the harder half. "When you cast this spell" fires while
the card *is* the spell on the stack, so it is never on the battlefield when it
matters, and `_candidate_abilities` scanned the battlefield, the command zone,
the graveyard, the hand and exile — every zone except the one place this card
lives at the moment it speaks. The stack is scanned separately because it is not
a player zone: it is shared, ordered, and holds the spell under its own trigger.

The ordering that makes both work is rule 601.2g: the mana is paid first, then
the sacrifice. A creature that taps for mana can therefore help pay for the
spell that is about to eat it.
"""

from __future__ import annotations

import copy

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from tests.conftest import only_oid, pass_until

EMERGER = {
    "id": "t_emerger_probe",
    "name": "Test Emerger Probe",
    "oracle_text": "Emerge {5}{U}{U} (You may cast this spell by sacrificing a creature and paying the emerge cost reduced by that creature's mana value.)",
    "mana_cost": "{8}",
    "emerge": "{5}{U}{U}",
    "types": ["Creature"],
    "subtypes": ["Eldrazi"],
    "power": 5,
    "toughness": 6,
}


def board(builder, *, islands: int = 8, fodder: list[str] | None = None):
    """`fodder=[]` means *no* creature to eat -- not the default."""
    if fodder is None:
        fodder = ["t_trampler"]
    return (
        builder(players=2)
        .battlefield(0, ["island"] * islands + fodder)
        .battlefield(1, ["t_bear", "t_dork"])
        .hand(0, ["t_emerger"])
        .library(0, ["forest"] * 20)
        .build()
    )


def casts(game) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == "t_emerger"
    ]


class TestThePriceDependsOnWhatGoes:
    def test_one_line_per_sacrificeable_creature(self, builder):
        game = board(builder, fodder=["t_trampler", "t_bear"])
        offered = {a.emerge_oid for a in casts(game) if a.emerge_oid is not None}
        assert len(offered) == 2, "each creature is a different price, so a different line"

    def test_the_label_says_which_one(self, builder):
        game = board(builder)
        line = next(a for a in casts(game) if a.emerge_oid is not None)
        assert "emerge, sacrificing Test Trampler" in line.label

    def test_a_bigger_creature_makes_it_cheaper(self, builder):
        """{5}{U}{U} is seven. Sacrificing a four-drop leaves {1}{U}{U}, which
        three Islands cover; the printed {8} does not."""
        game = board(builder, islands=3)
        lines = casts(game)
        assert lines, "emerge should be affordable off three Islands"
        assert all(a.emerge_oid is not None for a in lines), (
            "the printed {8} cost is not payable here and must not be offered"
        )

    def test_with_no_creature_to_eat_there_is_no_emerge_line(self, builder):
        game = board(builder, islands=3, fodder=[])
        assert not casts(game), "nothing to sacrifice and {8} is unaffordable"


class TestWhatCastingItDoes:
    def test_the_creature_is_sacrificed(self, builder):
        game = board(builder)
        game.apply(next(a for a in casts(game) if a.emerge_oid is not None))
        assert not [
            o for o in game.state.battlefield_objects(0) if o.def_id == "t_trampler"
        ], "the fodder survived"
        assert [
            oid
            for oid in game.state.players[0].graveyard
            if game.state.objects[oid].def_id == "t_trampler"
        ]

    def test_it_arrives_on_the_battlefield(self, builder):
        game = board(builder)
        game.apply(next(a for a in casts(game) if a.emerge_oid is not None))
        # The cast trigger stops to choose its four targets (603.3d), so the
        # spell is still on the stack underneath it until someone answers.
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert only_oid(game, "t_emerger")

    def test_mana_value_is_unchanged(self, builder):
        """Emerge is another way to pay, not a discount on the card. Folding it
        into `mana_cost` would quietly change every mana-value reading."""
        game = board(builder)
        oid = game.state.players[0].hand[0]
        card = game.state.card(oid)
        assert card.mana_cost.mana_value() == 8
        assert card.emerge is not None and card.emerge.mana_value() == 7


class TestTheCastTrigger:
    def test_it_fires_while_the_card_is_still_a_spell(self, builder):
        """The zone nothing scanned.

        Asserted on `ability_triggered` rather than on taps. The trigger asks
        its controller which four permanents, and this test does not answer --
        it only cares that the ability was reached at all. Counting taps would
        measure the answer the test happened to give, not whether the stack was
        scanned.
        """
        game = board(builder)
        before = len(game.state.events)
        game.apply(next(a for a in casts(game) if a.emerge_oid is not None))
        fired = [
            e
            for e in game.state.events[before:]
            if e.type == "ability_triggered" and e.data.get("card") == "t_emerger"
        ]
        assert fired, "the cast trigger never fired; the stack was not scanned"

    def test_the_ability_is_reached_only_because_of_active_zones(self, registry):
        """The guard on the new scan.

        The stack is scanned for *every* spell now, so what stops an ordinary
        ETB from firing there is `active_zones` alone -- which defaults to the
        battlefield and had no `"stack"` to ask for until this card.
        """
        assert [z.value for z in registry.get("t_emerger").abilities[0].active_zones] == [
            "stack"
        ]
        etb = registry.get("t_etb_draw")
        assert [z.value for z in etb.abilities[0].active_zones] == ["battlefield"]


class TestLoadTimeGuards:
    def test_emerge_with_x_is_refused(self):
        card = copy.deepcopy(EMERGER)
        card["emerge"] = "{X}{U}{U}"
        with pytest.raises(DslError, match="emerge cost with X"):
            compile_card(CardModel.model_validate(card))

    def test_a_card_may_not_have_both_alternative_costs(self):
        """No printing does, and legality would have to decide which replaces
        which."""
        card = copy.deepcopy(EMERGER)
        card["evoke"] = "{2}{U}"
        with pytest.raises(DslError, match="both 'evoke' and 'emerge'"):
            compile_card(CardModel.model_validate(card))

    def test_the_card_itself_loads(self):
        card = compile_card(CardModel.model_validate(EMERGER))
        assert card.emerge is not None
