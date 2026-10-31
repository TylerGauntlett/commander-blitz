"""Annihilator N (702.86) -- a numbered keyword that is granted with its number.

    "Annihilator 2 (Whenever this creature attacks, defending player
    sacrifices two permanents of their choice.)"        -- It That Betrays

    "Enchanted creature gets +10/+10 and has trample and annihilator 2."
                                                        -- Eldrazi Conscription

702.86a makes annihilator a triggered ability, and the sentence is the rules':
`carddef.annihilator_ability(n)` supplies it for every instance, exalted's
shape with ward's interning. It is a `Keyword` and not a printed trigger
because Eldrazi Conscription *grants* it, and a granted printed trigger would be
an unnamed ability rather than the keyword -- so the word goes in `keywords`
and N beside it, on the card (`CardDef.annihilator`, toxic's pairing) or on the
`grant_keyword` static that hands it out (its ``annihilator`` key).

The substance is who sacrifices and who chooses. "Defending player" is the seat
the creature attacks, or the controller of the planeswalker it attacks
(506.2, 508.5), and they pick their own permanents. An annihilator whose
*controller* picked would be strictly better than the printed one, and at a pod
`controller: "opponent"` -- the near miss -- would pool the whole table's
permanents. A test that only counted the dead would pass either way.

The rules points, each with a test:

- the defending player chooses, among only their own permanents, and N go --
  or as many as there are;
- at a pod only the attacked seat sacrifices, and attacking a planeswalker
  makes its controller the defending player;
- each instance triggers separately (702.86b): printed plus granted is two
  triggers and twice the sacrifices;
- a granted annihilator works on a creature that prints none, and stops when
  the Aura leaves;
- the keyword is read on derived characteristics: losing the word, or every
  ability, stops the printed one;
- the loader requires the word and the number together, on a card and on a
  grant, and refuses every grant spelling that cannot carry N.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.authoring.verify import claimed_lines
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import annihilator_instances
from commanderblitz.engine.enums import KEYWORD_COUNTERS, ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.structs import TargetRef
from tests.conftest import _default_answer, find_action, keywords, only_oid, pass_until

ANNIHILATOR = "t_annihilator"  # 5/5 Eldrazi, annihilator 2
CONSCRIPTION = "t_conscription"  # Aura: +10/+10, trample and annihilator 2
SUPPRESSOR = "t_annihilator_suppressor"  # creatures lose annihilator
BEAR = "t_bear"
WALL = "t_wall"
WALKER = "t_walker"


def settle(game, limit: int = 60) -> None:
    for _ in range(limit):
        decision = game.pending()
        if decision is not None and decision.kind is not DecisionKind.PRIORITY:
            game.apply(_default_answer(game, decision))
            continue
        if not game.state.stack and not game.state.pending_triggers:
            return
        if decision is None:
            game._advance()
        else:
            game.apply(_default_answer(game, decision))
    raise AssertionError("nothing settled")


def position(builder, mine=(ANNIHILATOR,), theirs=(BEAR, BEAR, WALL), *, players=2, third=()):
    """Player 0's ``mine`` facing player 1's ``theirs`` (and player 2's ``third``)."""
    b = builder(players=players).battlefield(0, list(mine)).battlefield(1, list(theirs))
    if players > 2:
        b = b.battlefield(2, list(third))
    # Frozen, so an Aura can be attached before the state-based pass would bin
    # it as unattached (704.5m).
    return b.build(advance=False)


def enchant(game, aura_card: str, creature: int) -> int:
    aura = only_oid(game, aura_card, 0)
    attach(game.state, aura, creature)
    game.state.bump_chars()
    return aura


def attack(game, oid: int, target: TargetRef | None = None) -> None:
    if game.pending() is None:
        game._advance()  # the frozen position, thawed
    pass_until(
        game,
        lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
    )
    game.apply(
        find_action(
            game, ActionKind.ADD_ATTACKER, source=oid, targets=(target or TargetRef.player(1),)
        )
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def board(game, pid: int) -> int:
    return len(list(game.state.battlefield_objects(pid)))


class TestTheDefendingPlayerChooses:
    def test_the_defending_player_chooses(self, builder):
        """The whole card. An annihilator whose controller picked would be
        strictly better than the printed one."""
        game = position(builder)
        attack(game, only_oid(game, ANNIHILATOR, 0))
        decision = game.pending()
        assert decision is not None
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.player == 1, "the defending player, not the attacker"

    def test_it_offers_only_the_defenders_permanents(self, builder):
        game = position(builder)
        attack(game, only_oid(game, ANNIHILATOR, 0))
        assert len(game.pending().options) == 3, "their three, and not the attacker"

    def test_n_permanents_go(self, builder):
        game = position(builder)
        before = board(game, 1)
        attack(game, only_oid(game, ANNIHILATOR, 0))
        settle(game)
        assert board(game, 1) == before - 2
        assert board(game, 0) == 1, "the attacker keeps its own"

    def test_it_takes_what_is_there_when_that_is_less(self, builder):
        game = position(builder, theirs=(BEAR,))
        attack(game, only_oid(game, ANNIHILATOR, 0))
        settle(game)
        assert board(game, 1) == 0

    def test_an_empty_board_is_not_a_crash(self, builder):
        game = position(builder, theirs=())
        attack(game, only_oid(game, ANNIHILATOR, 0))
        settle(game)
        assert board(game, 1) == 0

    def test_not_attacking_annihilates_nothing(self, builder):
        game = position(builder)
        settle(game)
        assert board(game, 1) == 3


class TestWhoIsDefending:
    def test_at_a_pod_only_the_attacked_seat_sacrifices(self, builder):
        """`controller: "opponent"` is the near miss: it would pool both
        opponents' boards and let one of them choose for the table."""
        game = position(builder, players=3, third=(BEAR, BEAR, WALL))
        attack(game, only_oid(game, ANNIHILATOR, 0), TargetRef.player(2))
        decision = game.pending()
        assert decision.player == 2
        assert {game.state.objects[o.value].controller for o in decision.options} == {2}
        settle(game)
        assert board(game, 2) == 1
        assert board(game, 1) == 3

    def test_attacking_a_planeswalker_its_controller_sacrifices(self, builder):
        """506.2: the walker's controller is the defending player."""
        game = position(builder, theirs=(WALKER, BEAR, BEAR))
        walker = only_oid(game, WALKER, 1)
        attack(game, only_oid(game, ANNIHILATOR, 0), TargetRef.obj(walker))
        assert game.pending().player == 1
        settle(game)
        assert board(game, 1) == 1


class TestEachInstanceTriggers:
    def test_printed_plus_granted_is_two_triggers(self, builder):
        """702.86b: an annihilator 2 wearing a Conscription has two instances."""
        game = position(builder, mine=(ANNIHILATOR, CONSCRIPTION), theirs=(BEAR,) * 5)
        eldrazi = only_oid(game, ANNIHILATOR, 0)
        enchant(game, CONSCRIPTION, eldrazi)
        assert annihilator_instances(game.state, eldrazi) == (2, 2)
        attack(game, eldrazi)
        settle(game)
        assert board(game, 1) == 1


class TestGranted:
    def test_the_aura_grants_the_keyword_and_its_trigger(self, builder):
        game = position(builder, mine=(BEAR, CONSCRIPTION))
        bear = only_oid(game, BEAR, 0)
        enchant(game, CONSCRIPTION, bear)
        assert {"annihilator", "trample"} <= keywords(game, bear)
        assert annihilator_instances(game.state, bear) == (2,)
        attack(game, bear)
        assert game.pending().player == 1
        settle(game)
        assert board(game, 1) == 1

    def test_without_the_aura_attached_there_is_none(self, builder):
        game = position(builder, mine=(BEAR, CONSCRIPTION))
        bear = only_oid(game, BEAR, 0)
        assert annihilator_instances(game.state, bear) == ()
        attack(game, bear)
        settle(game)
        assert board(game, 1) == 3


class TestTheKeywordIsDerived:
    def test_losing_the_word_stops_it(self, builder):
        game = position(builder, mine=(ANNIHILATOR, SUPPRESSOR))
        eldrazi = only_oid(game, ANNIHILATOR, 0)
        assert annihilator_instances(game.state, eldrazi) == ()
        attack(game, eldrazi)
        settle(game)
        assert board(game, 1) == 3

    def test_losing_every_ability_stops_the_printed_one(self, builder):
        game = position(builder)
        eldrazi = only_oid(game, ANNIHILATOR, 0)
        game.state.objects[eldrazi].lost_all_abilities = True
        game.state.bump_chars()
        assert annihilator_instances(game.state, eldrazi) == ()
        attack(game, eldrazi)
        settle(game)
        assert board(game, 1) == 3

    def test_a_grant_after_the_removal_survives_it(self, builder):
        """613.1b: what is added after a removal survives it -- the printed
        instance is gone, the Aura's is not."""
        game = position(builder, mine=(ANNIHILATOR, CONSCRIPTION))
        eldrazi = only_oid(game, ANNIHILATOR, 0)
        game.state.objects[eldrazi].lost_all_abilities = True
        enchant(game, CONSCRIPTION, eldrazi)
        assert annihilator_instances(game.state, eldrazi) == (2,)


def _creature(**fields) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe_eldrazi",
            "name": "Probe Eldrazi",
            "oracle_text": "Annihilator 1",
            "mana_cost": "{5}",
            "types": ["Creature"],
            "power": 5,
            "toughness": 5,
            **fields,
        }
    )


def _granter(ability: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe_granter",
            "name": "Probe Granter",
            "oracle_text": "Probe.",
            "mana_cost": "{B}",
            "types": ["Enchantment"],
            "abilities": [{"text": "Probe.", **ability}],
        }
    )


def _grant(**fields) -> dict:
    return {
        "kind": "static",
        "effect": "grant_keyword",
        "affects": {"attached": True},
        **fields,
    }


class TestTheLoaderGuard:
    def test_the_word_and_the_number_load(self):
        assert compile_card(_creature(keywords=["annihilator"], annihilator=1)).annihilator == 1

    def test_the_word_without_a_number_is_refused(self):
        with pytest.raises(DslError, match="write both or neither"):
            compile_card(_creature(keywords=["annihilator"]))

    def test_a_number_without_the_word_is_refused(self):
        with pytest.raises(DslError, match="write both or neither"):
            compile_card(_creature(annihilator=1))

    def test_a_negative_number_is_refused(self):
        with pytest.raises(DslError, match="cannot be negative"):
            compile_card(_creature(keywords=["annihilator"], annihilator=-1))

    def test_a_grant_with_its_number_loads(self):
        card = compile_card(_granter(_grant(keywords=["trample", "annihilator"], annihilator=2)))
        assert card.abilities[0].static["annihilator"] == 2

    def test_a_grant_without_its_number_is_refused(self):
        """It would grant a keyword that annihilates nothing."""
        with pytest.raises(DslError, match="needs its N"):
            compile_card(_granter(_grant(keywords=["annihilator"])))

    @pytest.mark.parametrize("n", [0, -1])
    def test_a_grant_with_a_bad_number_is_refused(self, n):
        with pytest.raises(DslError, match="needs its N"):
            compile_card(_granter(_grant(keywords=["annihilator"], annihilator=n)))

    def test_a_number_on_a_grant_of_something_else_is_refused(self):
        with pytest.raises(DslError, match="whose 'keywords' name it"):
            compile_card(_granter(_grant(keywords=["trample"], annihilator=2)))

    def test_a_number_on_another_static_is_refused(self):
        with pytest.raises(DslError, match="whose 'keywords' name it"):
            compile_card(
                _granter(
                    {
                        "kind": "static",
                        "effect": "lose_keyword",
                        "affects": {"types": ["Creature"]},
                        "keywords": ["annihilator"],
                        "annihilator": 2,
                    }
                )
            )

    def test_a_granting_op_is_refused(self):
        """Hideous Taskmaster's "they gain ... annihilator 1 until end of turn"
        is an op grant, and an op grant is a bare word with no N."""
        with pytest.raises(DslError, match="granted only by a grant_keyword static"):
            compile_card(
                _granter(
                    {
                        "kind": "activated",
                        "cost": {"mana": "{B}"},
                        "effects": [
                            {
                                "op": "grant_keyword",
                                "keywords": ["annihilator"],
                                "objects": {"self_only": True},
                            }
                        ],
                    }
                )
            )

    def test_losing_annihilator_is_allowed(self):
        compile_card(
            _granter(
                {
                    "kind": "static",
                    "effect": "lose_keyword",
                    "affects": {"types": ["Creature"]},
                    "keywords": ["annihilator"],
                }
            )
        )

    def test_there_is_no_annihilator_counter(self):
        assert "annihilator" not in KEYWORD_COUNTERS


class TestTheResidualClaim:
    def test_the_printed_line_with_the_cards_own_n_is_claimed(self):
        card = compile_card(_creature(keywords=["annihilator"], annihilator=2))
        line = (
            "Annihilator 2 (Whenever this creature attacks, defending player "
            "sacrifices two permanents of their choice.)"
        )
        assert line in claimed_lines(card, line)

    def test_a_keyword_line_with_another_keyword_is_claimed(self):
        card = compile_card(_creature(keywords=["flying", "annihilator"], annihilator=1))
        assert "Flying, annihilator 1" in claimed_lines(card, "Flying, annihilator 1")

    def test_a_different_n_is_not_claimed(self):
        """An annihilator 1 card wearing "Annihilator 2" is a weaker card."""
        card = compile_card(_creature(keywords=["annihilator"], annihilator=1))
        assert "Annihilator 2" not in claimed_lines(card, "Annihilator 2")
