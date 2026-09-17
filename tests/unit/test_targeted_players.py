"""Targeted players as a selector — "creatures **those opponents** control".

    "Choose any number of target opponents. Create X 1/1 white Human Soldier
    creature tokens, where X is the number of creatures those opponents
    control." (Call the Coppercoats.)

"Those opponents" is the players the spell targeted, and only them. The near
miss is `controller: "opponent"`, which counts every opponent's creatures at
once: exact when every opponent is targeted, and at a pod a strictly better card
whenever one is not — targeting the opponent with two creatures would still make
tokens for the opponent with four.

No new vocabulary was needed, which is the finding this file records. A
selector's `controller` already accepts a full player spec, and
`{"target": "t1"}` is one: `select_players` resolves it through
`ctx.target_players`, which returns **every** player ref under that id, not the
first. So the spelling Cloak and Dagger uses for one seat reads a set of seats
unchanged, and the gap record that asked for a "targeted-player selector" was
written against a reference that showed the one-seat case only.

What makes it right on resolution is 608.2b: "the spell or ability doesn't
perform any actions on [an illegal target] or make any of that target's
controller perform any actions", and an illegal target is simply not part of the
set. `stack` resolves through `targeting.filter_legal`, which rebuilds the
context's target buckets with only the refs still legal, so an opponent who
gained protection in response drops out of "those opponents" while the rest are
still counted; and if every target has gone, the spell does not resolve at all.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind
from automtg.engine.structs import PROTECTION_EVERYTHING, PlayerProtection

COPPERCOATS = "t_coppercoats"
LOOSE = "t_loose_coppercoats"
SOLDIER = "human_soldier_1_1_w"
BEAR = "grizzly_bears"


def table(builder, card: str = COPPERCOATS):
    """Four seats. Seat 1 has two creatures, seat 2 three, seat 3 four.

    Seat 1 holds an Opt and an untapped Island, so it stops for priority while
    the spell is on the stack -- the window a test needs to respond in.
    """
    return (
        builder(players=4)
        .battlefield(0, ["plains"] * 10)
        .hand(0, [card])
        .battlefield(1, [BEAR] * 2 + ["island"])
        .hand(1, ["opt"])
        .battlefield(2, [BEAR] * 3)
        .battlefield(3, [BEAR] * 4)
        .build()
    )


def cast_at(game, seats: set[int], card: str = COPPERCOATS):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card
        and {r.id for r in a.targets} == seats
    )
    game.apply(action)


def respond(game, protect: set[int] = frozenset()):
    """Give each seat in ``protect`` protection from everything, then let it resolve."""
    for seat in protect:
        game.state.player_protections.append(
            PlayerProtection(player=seat, quality=PROTECTION_EVERYTHING)
        )
    for _ in range(20):
        if not game.state.stack:
            return
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    raise AssertionError("the stack never emptied")


def soldiers(game) -> int:
    return sum(1 for o in game.state.battlefield_objects(0) if o.def_id == SOLDIER)


class TestItCountsOnlyTheTargetedOpponents:
    def test_one_target_counts_that_opponent(self, builder):
        game = table(builder)
        cast_at(game, {1})
        respond(game)
        assert soldiers(game) == 2

    def test_two_targets_count_both_of_them(self, builder):
        game = table(builder)
        cast_at(game, {1, 2})
        respond(game)
        assert soldiers(game) == 2 + 3

    def test_the_untargeted_opponent_is_never_counted(self, builder):
        game = table(builder)
        cast_at(game, {2, 3})
        respond(game)
        assert soldiers(game) == 3 + 4

    def test_every_opponent(self, builder):
        game = table(builder)
        cast_at(game, {1, 2, 3})
        respond(game)
        assert soldiers(game) == 2 + 3 + 4

    def test_no_targets_counts_nobody(self, builder):
        """"Any number" includes none, and nobody controls no creatures."""
        game = table(builder)
        cast_at(game, set())
        respond(game)
        assert soldiers(game) == 0


class TestTheNearMissCountsTheWholeTable:
    """`controller: "opponent"` is a different card, and a better one."""

    def test_one_target_still_counts_every_opponent(self, builder):
        game = table(builder, LOOSE)
        cast_at(game, {1}, LOOSE)
        respond(game)
        assert soldiers(game) == 2 + 3 + 4


class TestIllegalTargetsAreIgnored:
    """608.2b: a target that became illegal is not one of "those opponents"."""

    def test_a_protected_opponent_drops_out_and_the_rest_still_count(self, builder):
        game = table(builder)
        cast_at(game, {1, 2})
        respond(game, protect={2})
        assert soldiers(game) == 2

    def test_when_every_target_is_illegal_the_spell_does_nothing(self, builder):
        game = table(builder)
        cast_at(game, {1})
        respond(game, protect={1})
        assert soldiers(game) == 0


class TestTheLoader:
    """The reference has to name a declared player target, or it counts nobody."""

    def _model(self, controller):
        return CardModel.model_validate(
            {
                "id": "t_those_probe",
                "name": "Those Probe",
                "mana_cost": "{2}{W}",
                "types": ["Sorcery"],
                "targets": [
                    {"id": "t1", "kind": "player", "count": "any",
                     "selector": {"controller": "opponent"}},
                ],
                "spell_effects": [
                    {"op": "create_token", "token": SOLDIER,
                     "amount": {"count": {"types": ["Creature"], "controller": controller}}}
                ],
            }
        )

    def test_the_whole_thing_loads(self):
        compile_card(self._model({"target": "t1"}))

    def test_an_undeclared_target_is_refused(self):
        """It used to load, and count nobody."""
        with pytest.raises(DslError, match="does not declare"):
            compile_card(self._model({"target": "t9"}))

    def test_a_target_that_is_never_a_player_is_refused(self):
        """A permanent target's refs are objects, so "those players" would be nobody."""
        model = self._model({"target": "t1"})
        model.targets[0].kind = "permanent"
        model.targets[0].selector = {"types": ["Creature"]}
        with pytest.raises(DslError, match="never a player"):
            compile_card(model)

    def test_it_is_checked_however_deep_the_selector_sits(self):
        with pytest.raises(DslError, match="does not declare"):
            compile_card(self._model({"not": {"target": "t9"}}))
