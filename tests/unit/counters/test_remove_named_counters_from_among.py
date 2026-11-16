"""Removing counters of one **named** kind from among permanents.

    Sage of Fables -- "{2}, Remove a +1/+1 counter from a creature you control:
    Draw a card."
    Duchess, Wayward Tavernkeep -- "{1}, Remove a quest counter from a permanent
    you control: Create a Junk token."
    Overseer of Vault 76 -- "you may remove three quest counters from among
    permanents you control."

The `remove_counters` cost names a kind but reads only the source; the
`remove_counters_from_among` cost chooses among permanents but takes counters
of any kind. These sentences are both at once: the payer picks the permanent,
the card picks the kind. Filtering the pool with `has_counters` is not enough,
because a creature carrying a +1/+1 and a -1/-1 counter would be offered and
could pay with the -1/-1 -- a strictly cheaper card than the printed one.

So `counter` on `remove_counters_from_among` (cost and op) fixes the kind: only
permanents carrying it are offered, only counters of it count toward
payability (602.2b: a cost is paid in full or the ability is not activated),
and the kind is never asked. The witness is Sage of Fables.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card, activations, hand_ids, only_oid, pass_until

SAGE = "t_counter_sage"  # {2}, remove a +1/+1 counter from a creature you control: draw
HARVEST = "t_quest_harvest"  # remove two quest counters from among permanents you control
BEAR = "t_bear"
ENCHANTMENT = "t_proliferate_doubler"


def position(builder, *, sage=None, bear=None, enchantment=None, theirs=None, hand=()):
    """The Sage and three Islands; a Bear and an enchantment of ours, a Bear of theirs."""
    b = builder(players=2).battlefield(0, [SAGE], counters=sage or {})
    b = b.battlefield(0, ["island"] * 3)
    b = b.battlefield(0, ["swamp"]).hand(0, list(hand))
    if bear is not None:
        b = b.battlefield(0, [BEAR], counters=bear)
    if enchantment is not None:
        b = b.battlefield(0, [ENCHANTMENT], counters=enchantment)
    if theirs is not None:
        b = b.battlefield(1, [BEAR], counters=theirs)
    game = (
        b.library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )
    game._advance()
    return game, only_oid(game, SAGE, 0)


def counters(game, oid) -> dict:
    return {k: n for k, n in game.state.objects[oid].counters.items() if n > 0}


def activate(game, sage) -> list:
    """Activate the Sage; every cost question asked, answered with the first option."""
    game.apply(activations(game, sage)[0])
    asked = []
    while (decision := game.pending()) is not None and decision.kind in (
        DecisionKind.CHOOSE_OBJECTS,
        DecisionKind.CHOOSE_MODE,
    ):
        asked.append(decision)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
    return asked


class TestWhatPaysIt:
    def test_a_plus_one_counter_on_a_creature_pays(self, builder):
        game, sage = position(builder, bear={"+1/+1": 1})
        assert activations(game, sage)

    def test_another_kind_does_not(self, builder):
        """The boundary the named kind exists for: counters, but not +1/+1."""
        game, sage = position(builder, bear={"-1/-1": 1, "charge": 3})
        assert not activations(game, sage)

    def test_the_kind_on_a_non_creature_does_not(self, builder):
        game, sage = position(builder, enchantment={"+1/+1": 2})
        assert not activations(game, sage)

    def test_an_opponents_creature_does_not(self, builder):
        game, sage = position(builder, theirs={"+1/+1": 2})
        assert not activations(game, sage)

    def test_the_source_itself_may(self, builder):
        """"A creature you control" -- the Sage is one."""
        game, sage = position(builder, sage={"+1/+1": 1})
        assert activations(game, sage)


class TestPayingIt:
    def test_only_the_named_kind_comes_off_and_the_kind_is_not_asked(self, builder):
        game, sage = position(builder, bear={"+1/+1": 1, "stun": 1})
        bear = only_oid(game, BEAR, 0)
        hand = len(hand_ids(game, 0))
        asked = activate(game, sage)
        assert not [d for d in asked if d.kind is DecisionKind.CHOOSE_MODE]
        assert counters(game, bear) == {"stun": 1}
        pass_until(game, lambda g: not g.state.stack)
        assert len(hand_ids(game, 0)) == hand + 1

    def test_only_permanents_with_the_kind_are_offered(self, builder):
        game, sage = position(builder, sage={"charge": 2}, bear={"+1/+1": 1})
        game.apply(activations(game, sage)[0])
        # One candidate is a forced pick, so nothing is asked and the cost is paid.
        assert game.pending() is None or game.pending().kind is not DecisionKind.CHOOSE_OBJECTS
        assert counters(game, only_oid(game, BEAR, 0)) == {}
        assert counters(game, sage) == {"charge": 2}

    def test_the_payer_chooses_among_them(self, builder):
        game, sage = position(builder, sage={"+1/+1": 1}, bear={"+1/+1": 2})
        game.apply(activations(game, sage)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.context["purpose"] == "remove_counter_cost"
        assert {o.value for o in decision.options} == {sage, only_oid(game, BEAR, 0)}


def cast(game, spell):
    game.apply(action_for_card(game, ActionKind.CAST, spell))
    pass_until(
        game,
        lambda g: (
            (d := g.pending()) is not None and d.context.get("purpose") == "remove_counter"
        )
        or not g.state.stack,
    )


class TestTheOp:
    def test_exactly_that_many_of_that_kind(self, builder):
        game, _ = position(
            builder, bear={"quest": 1, "+1/+1": 3}, enchantment={"quest": 3}, hand=[HARVEST]
        )
        bear, ench = only_oid(game, BEAR, 0), only_oid(game, ENCHANTMENT, 0)
        life = game.state.players[0].life
        cast(game, HARVEST)
        while (d := game.pending()) is not None and d.context.get("purpose") == "remove_counter":
            assert d.kind is DecisionKind.CHOOSE_OBJECTS, "the kind is never asked"
            assert {o.value for o in d.options} <= {bear, ench}
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
        pass_until(game, lambda g: not g.state.stack)
        assert counters(game, bear).get("+1/+1") == 3
        quest = counters(game, bear).get("quest", 0) + counters(game, ench).get("quest", 0)
        assert quest == 2
        assert game.state.players[0].life == life + 2

    def test_as_many_as_there_are(self, builder):
        """609.3: one quest counter among them, so one comes off and is counted."""
        game, _ = position(builder, bear={"quest": 1, "charge": 4}, hand=[HARVEST])
        life = game.state.players[0].life
        cast(game, HARVEST)
        pass_until(game, lambda g: not g.state.stack)
        assert counters(game, only_oid(game, BEAR, 0)) == {"charge": 4}
        assert game.state.players[0].life == life + 1


class TestTheLoaderGuardsIt:
    def _card(self, kind):
        return CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "oracle_text": "Remove a counter from a creature you control: Draw a card.",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "Remove a counter from a creature you control: Draw a card.",
                        "cost": {
                            "remove_counters_from_among": {
                                "count": 1,
                                "counter": kind,
                                "types": ["Creature"],
                            }
                        },
                        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                    }
                ],
            }
        )

    def test_a_kind_that_is_not_a_string_is_refused(self):
        with pytest.raises(DslError, match="a counter kind"):
            compile_card(self._card(3))

    def test_a_near_miss_of_a_keyword_counter_is_refused(self):
        with pytest.raises(DslError):
            compile_card(self._card("Vigilance"))
