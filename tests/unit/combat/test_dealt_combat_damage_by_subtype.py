"""How many opponents this creature *or a Dragon* dealt combat damage to -- Estinien Varlineau.

"At the beginning of your second main phase, you draw X cards and lose X life,
where X is **the number of your opponents who were dealt combat damage by
Estinien Varlineau or a Dragon this turn**." A count of *players*, asked after
`state.combat` has gone, about damage from two kinds of source at once:

- `{"dealt_combat_damage_by": "self"}` answers the first half and only that: it
  is keyed by the ability's own source, and knows nothing of other creatures.
- The `combat_damage_by` condition (prowl) knows a Dragon got through but not to
  whom, so it cannot count opponents -- one Dragon hitting one player and three
  Dragons hitting three players read the same.
- The board is the wrong place to look (rule 510.2: the damage is an event that
  happened). A Dragon that connected and then died still dealt the damage; a
  Bear made a Dragon *after* combat dealt it as a Bear.

So `TurnLedger.players_dealt_combat_damage_by_subtype` (subtype -> seats),
folded off COMBAT_DAMAGE_TO_PLAYER from the attacker's **derived** subtypes as
the damage lands, and the `dealt_combat_damage_by` subject widened to
`{"subtypes": [...]}` and `{"any_of": [...]}`. The union is of *seats*, so an
opponent hit by both Estinien and a Dragon is one opponent; `player_count`
counts it and `except: "you"` keeps an opponent's Dragon hitting you out of
"your opponents". It wears off with the rest of the ledger at cleanup.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import select_players
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_player
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import destroy
from tests.conftest import _default_answer, find_action, only_oid, pass_until

ESTINIEN = "t_dcs_estinien"  # 3/3 Human Knight with the second-main line
DRAGON = "t_dcs_dragon"  # vanilla 2/2 Dragon
BEAR = "t_bear"  # vanilla 2/2 Bear
BOLT = "t_bolt"  # an instant, so priority stops in every step
SUBJECT = {"any_of": ["self", {"subtypes": ["Dragon"]}]}
X = {"player_count": {"dealt_combat_damage_by": SUBJECT, "except": "you"}}


def board(builder, *, players: int = 4, theirs: dict[int, list[str]] | None = None):
    b = (
        builder(players=players)
        .battlefield(0, [ESTINIEN, DRAGON, BEAR])
        .hand(0, [BOLT])
        .library(0, ["mountain"] * 10)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid in range(1, players):
        b.battlefield(pid, (theirs or {}).get(pid, []))
        b.library(pid, ["mountain"] * 10)
    game = b.build()
    return game, only_oid(game, ESTINIEN, 0), only_oid(game, DRAGON, 0), only_oid(game, BEAR, 0)


def declare(game, attacks: dict[int, TargetRef]) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    for oid, ref in attacks.items():
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(ref,)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def until(game, predicate, limit: int = 300) -> None:
    """Answer every decision with its default until ``predicate`` holds."""
    for _ in range(limit):
        if predicate(game) or game.over:
            return
        decision = game.pending()
        assert decision is not None, "nothing left to pass with"
        game.apply(_default_answer(game, decision))
    raise AssertionError("did not reach the condition")


def after_the_trigger(game) -> None:
    """The second main phase, with Estinien's trigger resolved."""
    until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN and not g.state.stack
          and g.pending() is not None and g.pending().kind is DecisionKind.PRIORITY
          and g.pending().player == 0)


def ctx(game, oid: int) -> EffectContext:
    return EffectContext(state=game.state, controller=0, source_oid=oid)


def x_for(game, oid: int) -> int:
    return evaluate_value(ctx(game, oid), X)


def make(game, oid: int, *subtypes: str) -> None:
    game.state.objects[oid].added_subtypes = tuple(subtypes)
    game.state.bump_chars()


class TestTheLedger:
    def test_it_records_each_seat_under_the_attackers_subtypes(self, builder):
        game, _, dragon, bear = board(builder)
        declare(game, {dragon: TargetRef.player(1), bear: TargetRef.player(2)})
        after_the_trigger(game)
        ledger = game.state.turn_ledger.players_dealt_combat_damage_by_subtype
        assert ledger["Dragon"] == {1}
        assert ledger["Bear"] == {2}

    def test_the_subtype_is_read_when_the_damage_lands(self, builder):
        # A Bear that was a Dragon as it hit counts after it stops being one.
        game, est, _, bear = board(builder)
        make(game, bear, "Dragon")
        damage_player(game.state, 1, 2, bear, is_combat=True)
        make(game, bear)
        assert x_for(game, est) == 1

    def test_becoming_a_dragon_afterwards_does_not_count(self, builder):
        game, est, _, bear = board(builder)
        damage_player(game.state, 1, 2, bear, is_combat=True)
        make(game, bear, "Dragon")
        assert x_for(game, est) == 0

    def test_the_dragon_dying_afterwards_does_not_undo_it(self, builder):
        game, est, dragon, _ = board(builder)
        damage_player(game.state, 1, 2, dragon, is_combat=True)
        destroy(game.state, dragon)
        assert x_for(game, est) == 1

    def test_noncombat_damage_from_a_dragon_does_not_count(self, builder):
        game, est, dragon, _ = board(builder)
        damage_player(game.state, 1, 2, dragon, is_combat=False)
        assert x_for(game, est) == 0

    def test_it_is_cleared_with_the_ledger(self, builder):
        game, est, dragon, _ = board(builder)
        damage_player(game.state, 1, 2, dragon, is_combat=True)
        damage_player(game.state, 2, 3, est, is_combat=True)
        game.state.turn_ledger.clear()
        assert x_for(game, est) == 0


class TestTheUnion:
    def test_an_opponent_hit_by_both_is_one_opponent(self, builder):
        game, est, dragon, _ = board(builder)
        damage_player(game.state, 1, 3, est, is_combat=True)
        damage_player(game.state, 1, 2, dragon, is_combat=True)
        assert select_players(ctx(game, est), {"dealt_combat_damage_by": SUBJECT}) == [1]
        assert x_for(game, est) == 1

    def test_a_dragon_of_any_controller_counts(self, builder):
        game, est, _, _ = board(builder, theirs={1: [DRAGON]})
        theirs = only_oid(game, DRAGON, 1)
        damage_player(game.state, 2, 2, theirs, is_combat=True)
        assert x_for(game, est) == 1

    def test_an_opponents_dragon_hitting_you_is_not_your_opponent(self, builder):
        game, est, _, _ = board(builder, theirs={1: [DRAGON]})
        theirs = only_oid(game, DRAGON, 1)
        damage_player(game.state, 0, 2, theirs, is_combat=True)
        assert select_players(ctx(game, est), {"dealt_combat_damage_by": SUBJECT}) == [0]
        assert x_for(game, est) == 0

    def test_self_stays_keyed_by_oid(self, builder):
        # Another Human Knight is not "Estinien": only the source's own record.
        game, est, _, bear = board(builder)
        make(game, bear, "Human", "Knight")
        damage_player(game.state, 1, 2, bear, is_combat=True)
        assert x_for(game, est) == 0


class TestTheCard:
    def test_it_draws_and_loses_one_per_opponent_hit(self, builder):
        game, est, dragon, bear = board(builder)
        life, hand = game.state.players[0].life, len(game.state.players[0].hand)
        declare(game, {est: TargetRef.player(1), dragon: TargetRef.player(2),
                       bear: TargetRef.player(3)})
        after_the_trigger(game)
        assert len(game.state.players[0].hand) == hand + 2, "the Bear's opponent is not counted"
        assert game.state.players[0].life == life - 2

    def test_two_sources_into_one_opponent_is_one(self, builder):
        game, est, dragon, _ = board(builder)
        life, hand = game.state.players[0].life, len(game.state.players[0].hand)
        declare(game, {est: TargetRef.player(1), dragon: TargetRef.player(1)})
        after_the_trigger(game)
        assert len(game.state.players[0].hand) == hand + 1
        assert game.state.players[0].life == life - 1

    def test_without_an_attack_it_does_nothing(self, builder):
        game, _, _, _ = board(builder)
        life, hand = game.state.players[0].life, len(game.state.players[0].hand)
        started = game.state.turn
        # With nothing attacking, nobody holds priority again this turn, so the
        # declaration runs straight through the second main phase.
        declare(game, {})
        assert game.state.turn > started
        assert len(game.state.players[0].hand) == hand
        assert game.state.players[0].life == life


class TestTheLoader:
    def probe(self, amount) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "Probe.",
                "mana_cost": "{W}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "Probe.",
                        "cost": {"mana": "{1}"},
                        "effects": [{"op": "draw", "player": "you", "amount": amount}],
                    }
                ],
            }
        )

    @pytest.mark.parametrize(
        "subject", ["self", {"subtypes": ["Dragon"]}, {"subtypes": ["Faerie", "Rogue"]}, SUBJECT]
    )
    def test_the_documented_subjects_load(self, subject):
        compile_card(self.probe({"player_count": {"dealt_combat_damage_by": subject}}))
        compile_card(self.probe(X))

    @pytest.mark.parametrize(
        "subject",
        [
            "subject",
            {"subtypes": []},
            {"subtypes": "Dragon"},
            {"subtypes": [""]},
            {"subtype": ["Dragon"]},
            {"any_of": []},
            {"any_of": ["self", "subject"]},
            {"subtypes": ["Dragon"], "any_of": ["self"]},
        ],
    )
    def test_anything_else_is_refused(self, subject):
        with pytest.raises(DslError, match="dealt_combat_damage_by"):
            compile_card(self.probe({"player_count": {"dealt_combat_damage_by": subject}}))

