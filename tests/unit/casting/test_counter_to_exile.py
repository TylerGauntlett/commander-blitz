"""``counter``'s ``exiles`` -- "If that spell is countered this way, exile it
instead of putting it into its owner's graveyard."

Force of Negation and Transcendent Dragon are the witnesses.

**The rules argument.** Countering (701.6a) removes a spell from the stack and
puts it into its owner's graveyard. The second sentence is a replacement on
*that* move (614.1a): the card goes to exile instead, so it never touches the
graveyard -- nothing that watches a graveyard sees it, and the owner cannot
flash it back or regrow it. Without the key the card is a plain Counterspell,
a strictly weaker card. Written as an `exile` op after the counter it would be
wrong in the other direction: the card would hit the graveyard first, and it
would then be a new object (400.7) no selector names as "that spell".

"Countered **this way**" is the condition. A spell that can't be countered
stays on the stack and resolves, and nothing is exiled.

Transcendent Dragon then casts the exiled card: `as` binds the cards the
counter actually put in exile, and `play_exiled` over that binding is the free
cast, made by the Dragon's controller whoever owns the card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card, find_action, pass_until, settle

NEGATION = "t_cte_negation"
DRAGON = "t_cte_dragon"
UNSTOPPABLE = "t_cte_unstoppable"
DIVINATION = "t_draw_spell"
COUNTERSPELL = "t_counterspell"
BEAR = "t_bear"


def position(builder, *, theirs=(DIVINATION,), ours=(NEGATION,), lands=("island",) * 3):
    """Player 0 holds ``theirs`` and ``lands`` in their main phase; player 1
    holds ``ours`` and three Islands. Returns ``game``."""
    return (
        builder(players=2)
        .battlefield(0, list(lands))
        .battlefield(1, ["island"] * 3)
        .hand(0, list(theirs))
        .hand(1, list(ours))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def card_in_hand(game, pid: int, card_id: str) -> int:
    return next(
        oid for oid in game.state.players[pid].hand if game.state.objects[oid].def_id == card_id
    )


def cast_and_respond(game, spell: str, response: str) -> int:
    """Player 0 casts ``spell``; player 1 answers with ``response``. Returns the
    spell's oid."""
    oid = card_in_hand(game, 0, spell)
    game.apply(action_for_card(game, ActionKind.CAST, spell))
    pass_until(game, lambda g: g.pending().player == 1)
    game.apply(action_for_card(game, ActionKind.CAST, response))
    return oid


def zone_of(game, oid) -> Zone:
    return game.state.objects[oid].zone


def resolved_for(game, card_id: str, pid: int) -> bool:
    """Whether ``card_id`` resolved as a spell ``pid`` controlled."""
    return any(
        e.type == "spell_resolved" and e.data.get("card") == card_id and e.player == pid
        for e in game.state.events
    )


def countered(game) -> list:
    return [e for e in game.state.events if e.type == "spell_countered"]


class TestCounteredThisWayIsExiled:
    def test_the_countered_spell_goes_to_exile(self, builder):
        game = position(builder)
        divination = cast_and_respond(game, DIVINATION, NEGATION)
        settle(game)
        assert countered(game) and "failed" not in countered(game)[0].data
        assert zone_of(game, divination) is Zone.EXILE
        assert divination not in game.state.players[0].graveyard

    def test_it_never_touches_the_graveyard(self, builder):
        game = position(builder)
        divination = cast_and_respond(game, DIVINATION, NEGATION)
        settle(game)
        moves = [
            e
            for e in game.state.events
            if e.type == "zone_change" and e.data.get("oid") == divination
        ]
        assert [e.data.get("to") for e in moves][-1] in (Zone.EXILE, Zone.EXILE.value)
        assert all(e.data.get("to") not in (Zone.GRAVEYARD, Zone.GRAVEYARD.value) for e in moves)

    def test_a_plain_counter_still_uses_the_graveyard(self, builder):
        game = position(builder, ours=(COUNTERSPELL,))
        divination = cast_and_respond(game, DIVINATION, COUNTERSPELL)
        settle(game)
        assert zone_of(game, divination) is Zone.GRAVEYARD


class TestOnlyIfCountered:
    def test_an_uncounterable_spell_resolves_and_stays_out_of_exile(self, builder):
        game = position(builder, theirs=(UNSTOPPABLE,))
        spell = cast_and_respond(game, UNSTOPPABLE, NEGATION)
        settle(game)
        assert countered(game)[0].data.get("failed") == "cannot be countered"
        assert resolved_for(game, UNSTOPPABLE, 0)
        assert zone_of(game, spell) is Zone.GRAVEYARD

    def test_a_creature_spell_is_no_target_for_the_noncreature_counter(self, builder):
        game = position(builder, theirs=(BEAR,), lands=("island", "forest"))
        game.apply(action_for_card(game, ActionKind.CAST, BEAR))
        pass_until(game, lambda g: g.pending().player == 1)
        assert not any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == NEGATION
            for a in game.legal_actions()
        )


def dragon_trigger_resolving(game) -> int:
    """Player 0 casts Divination, player 1 flashes the Dragon in, and the table
    passes until the enters trigger's "may" asks. Returns Divination's oid."""
    divination = cast_and_respond(game, DIVINATION, DRAGON)
    pass_until(game, lambda g: g.pending().kind is DecisionKind.MAY)
    assert game.pending().player == 1
    assert zone_of(game, divination) is Zone.EXILE
    return divination


class TestTheDragonCastsWhatItExiled:
    def test_yes_casts_the_card_for_its_controller(self, builder):
        game = position(builder, ours=(DRAGON,))
        divination = dragon_trigger_resolving(game)
        game.apply(find_action(game, ActionKind.YES))
        settle(game)
        # Player 1 cast and resolved player 0's Divination, for free: the three
        # Islands they had went on the Dragon and nothing else.
        assert resolved_for(game, DIVINATION, 1)
        assert not resolved_for(game, DIVINATION, 0)
        # It is still player 0's card, so it resolves into their graveyard.
        assert zone_of(game, divination) is Zone.GRAVEYARD
        assert divination in game.state.players[0].graveyard

    def test_no_leaves_it_in_exile(self, builder):
        game = position(builder, ours=(DRAGON,))
        divination = dragon_trigger_resolving(game)
        game.apply(find_action(game, ActionKind.NO))
        settle(game)
        assert zone_of(game, divination) is Zone.EXILE

    def test_an_uncounterable_spell_is_not_offered(self, builder):
        game = position(builder, theirs=(UNSTOPPABLE,), ours=(DRAGON,))
        spell = cast_and_respond(game, UNSTOPPABLE, DRAGON)
        # The "may" may still ask -- with nothing bound, a yes casts nothing.
        for _ in range(50):
            decision = game.pending()
            if decision is not None and decision.kind is DecisionKind.MAY:
                game.apply(find_action(game, ActionKind.YES))
            elif not game.state.stack and not game.state.pending_triggers:
                break
            else:
                pass_until(
                    game,
                    lambda g: (g.pending() is not None and g.pending().kind is DecisionKind.MAY)
                    or (not g.state.stack and not g.state.pending_triggers),
                )
        assert resolved_for(game, UNSTOPPABLE, 0)
        assert not resolved_for(game, UNSTOPPABLE, 1)
        assert zone_of(game, spell) is Zone.GRAVEYARD


class TestTheLoaderGuard:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_cte_probe",
                "name": "Test Counter To Exile Probe",
                "mana_cost": "{U}",
                "types": ["Instant"],
                "oracle_text": "Probe.",
                "targets": [{"id": "t1", "kind": "spell", "count": 1, "selector": {}}],
                "spell_effects": [effect],
            }
        )

    def test_the_printed_form_loads(self):
        compile_card(
            self._card({"op": "counter", "target": "t1", "exiles": True, "as": "countered"})
        )

    @pytest.mark.parametrize("value", ["true", 1, None])
    def test_a_non_boolean_exiles_is_refused(self, value):
        with pytest.raises(DslError):
            compile_card(self._card({"op": "counter", "target": "t1", "exiles": value}))

    @pytest.mark.parametrize("value", ["", 3, None])
    def test_a_non_name_as_is_refused(self, value):
        with pytest.raises(DslError):
            compile_card(self._card({"op": "counter", "target": "t1", "as": value}))
