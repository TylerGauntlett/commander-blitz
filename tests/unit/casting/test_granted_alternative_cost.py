""""You may pay eight {E} rather than pay the mana cost for permanent spells
you cast." -- Nissa, Worldsoul Speaker.

An alternative cost (118.9) that a permanent hands to a whole class of spell.
Three neighbours come close and each is wrong:

- `alternative_cost` is card-level -- Force of Will prints its own pitch, and
  a creature in Nissa's controller's hand prints nothing.
- `free_cast_permission` (Dracogenesis) waives the cost. This replaces it with
  a different one, and the difference is the card: with seven energy there is
  no line at all.
- `spell_cost_reduction` discounts generic mana and cannot swap the payment to
  another resource at any amount.

So it is a player-wide static, `granted_alternative_cost`, read afresh every
time the cast lines are built (`player_statics.granted_alternative_cost`), and
offering a second line beside the printed one. The claims pinned here:

- **It is a choice.** The printed line stays; "you may" takes nothing away.
- **It is offered only while payable**, and paying it spends exactly the price
  and no mana.
- **Only the filtered spells.** "Permanent spells" leaves instants out.
- **Additional costs still apply** (118.9d): a commander's tax is mana on top.
- **X is 0** (107.3b), because the replacing price has no X in it.
- **The price rides on the action**, and survives a session tape's JSON
  round trip as the same action.
- The loader refuses a grant with no filter, no price, or a price in mana.
"""

from __future__ import annotations

import json

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.actions import Action
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy
from tests.conftest import only_oid

GRANT = "t_energy_grant"  # "pay three {E} rather than pay the mana cost for permanent spells"
LIFE_GRANT = "t_life_grant"  # "pay 5 life rather than … creature spells"
WYRM = "t_cinder_wyrm"  # {4}{R}{R} Dragon 4/4
X_WYRM = "t_swelling_wyrmling"  # {X}{R} Dragon, enters with X +1/+1 counters
INSTANT = "t_plain_instant"  # {W} You gain 1 life.


def board(builder, *, hand=(), energy=0, grant=GRANT, lands=(), commander=()):
    b = (
        builder(players=2)
        .hand(0, list(hand))
        .battlefield(0, [grant, *lands])
        .library(0, ["forest"] * 10)
        .active(0)
    )
    if commander:
        b = b.commander(0, list(commander))
    # Before the build advances: set afterwards, the auto-pass has already
    # rolled past a position in which player 0 had nothing to do.
    b.state.players[0].energy = energy
    return b.build()


def casts(game, card_id, zone="hand"):
    pool = getattr(game.state.players[0], zone)
    oid = next(o for o in pool if game.state.objects[o].def_id == card_id)
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def granted(game, card_id, zone="hand"):
    return [a for a in casts(game, card_id, zone) if a.granted_cost]


def resolve(game, action) -> None:
    game.apply(action)
    for _ in range(20):
        decision = game.pending()
        if decision is None or decision.kind is not DecisionKind.PRIORITY or not game.state.stack:
            break
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))


class TestTheLine:
    def test_it_is_offered_beside_the_printed_line(self, builder):
        game = board(builder, hand=[WYRM], energy=3, lands=["mountain"] * 6)
        lines = casts(game, WYRM)
        assert [a for a in lines if not a.granted_cost], "'you may' keeps the printed line"
        (line,) = granted(game, WYRM)
        assert line.granted_cost == (("pay_energy", 3),)
        assert "{E}{E}{E}" in line.label

    def test_one_short_is_not_offered(self, builder):
        game = board(builder, hand=[WYRM], energy=2)
        assert not granted(game, WYRM)

    def test_with_no_mana_on_the_board_it_is_the_only_line(self, builder):
        game = board(builder, hand=[WYRM], energy=3)
        assert [bool(a.granted_cost) for a in casts(game, WYRM)] == [True]

    def test_an_instant_is_not_a_permanent_spell(self, builder):
        game = board(builder, hand=[INSTANT], energy=3, lands=["plains"])
        assert casts(game, INSTANT)
        assert not granted(game, INSTANT)

    def test_an_opponents_grant_reaches_nobody_else(self, builder):
        b = builder(players=2).hand(0, [WYRM]).battlefield(1, [GRANT]).active(0)
        b = b.library(0, ["forest"] * 10)
        b.state.players[0].energy = 9
        game = b.build()
        assert not granted(game, WYRM)

    def test_the_grant_leaving_takes_the_line_with_it(self, builder):
        game = board(builder, hand=[WYRM], energy=3, lands=["mountain"] * 6)
        destroy(game.state, only_oid(game, GRANT))
        assert not granted(game, WYRM)


class TestPaying:
    def test_it_spends_the_energy_and_no_mana(self, builder):
        game = board(builder, hand=[WYRM], energy=5, lands=["mountain"] * 6)
        resolve(game, granted(game, WYRM)[0])
        assert game.state.players[0].energy == 2
        assert count(game, WYRM) == 1
        assert not any(game.state.objects[o].tapped for o in game.state.battlefield)

    def test_x_is_zero(self, builder):
        """No X is announced, so the 0/0 enters with no counters and dies.

        Five untapped Mountains stand by, so a line that had asked for X would
        have had something to spend.
        """
        game = board(builder, hand=[X_WYRM], energy=3, lands=["mountain"] * 5)
        resolve(game, granted(game, X_WYRM)[0])
        assert count(game, X_WYRM) == 0
        graveyard = [game.state.objects[o].def_id for o in game.state.players[0].graveyard]
        assert X_WYRM in graveyard
        assert not any(game.state.objects[o].tapped for o in game.state.battlefield)

    def test_life_is_the_other_currency(self, builder):
        game = board(builder, hand=[WYRM], grant=LIFE_GRANT)
        before = game.state.players[0].life
        resolve(game, granted(game, WYRM)[0])
        assert game.state.players[0].life == before - 5
        assert count(game, WYRM) == 1


class TestAdditionalCosts:
    def test_a_commander_still_owes_its_tax(self, builder):
        game = board(builder, commander=[WYRM], energy=3, lands=["mountain"] * 2)
        oid = game.state.players[0].command[0]
        game.state.players[0].commander_tax[oid] = 1
        lines = granted(game, WYRM, zone="command")
        assert lines, "the grant names no zone, so the command zone is covered"
        resolve(game, lines[0])
        assert game.state.players[0].energy == 0
        tapped = sum(1 for o in game.state.battlefield if game.state.objects[o].tapped)
        assert tapped == 2, "118.9d: the {2} tax is paid in mana on top"

    def test_a_tax_nobody_can_pay_takes_the_line_away(self, builder):
        game = board(builder, commander=[WYRM], energy=3)
        oid = game.state.players[0].command[0]
        game.state.players[0].commander_tax[oid] = 1
        assert not granted(game, WYRM, zone="command")


class TestTheTape:
    def test_the_price_survives_a_round_trip(self, builder):
        game = board(builder, hand=[WYRM], energy=3)
        line = granted(game, WYRM)[0]
        again = Action.from_record(json.loads(json.dumps(line.to_record())))
        assert again.granted_cost == line.granted_cost
        assert again.key() == line.key()


def count(game, card_id: str) -> int:
    return sum(1 for o in game.state.battlefield if game.state.objects[o].def_id == card_id)


def grant_card(**static):
    body = {
        "kind": "static",
        "text": "You may pay three {E} rather than pay the mana cost for permanent spells you cast.",
        "effect": "granted_alternative_cost",
        "affects_player": "you",
        "affects_spells": {"controller": "you", "not_types": ["Instant", "Sorcery"]},
        "cost": {"pay_energy": 3},
    }
    body.update(static)
    body = {k: v for k, v in body.items() if v is not None}
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": body["text"],
            "mana_cost": "{3}{G}",
            "types": ["Enchantment"],
            "abilities": [body],
        }
    )


class TestTheLoader:
    def test_the_printed_shape_loads(self):
        compile_card(grant_card())

    @pytest.mark.parametrize(
        "static, message",
        [
            ({"affects_spells": None}, "affects_spells"),
            ({"cost": None}, "needs a 'cost'"),
            ({"cost": {"mana": "{2}"}}, "energy or life"),
            ({"cost": {"pay_energy": 2, "discard": 1}}, "energy or life"),
            ({"affects_spells": {"tapped": True}}, "unsupported keys"),
        ],
    )
    def test_it_refuses(self, static, message):
        with pytest.raises(DslError, match=message):
            compile_card(grant_card(**static))
