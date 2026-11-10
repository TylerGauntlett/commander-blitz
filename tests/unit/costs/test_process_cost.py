"""The Eldrazi processor cost -- cards an opponent owns, from exile to a graveyard.

"{1}{G}, **Put a card an opponent owns from exile into that player's
graveyard**: Create a 1/1 colorless Eldrazi Scion creature token" (Void
Attendant), and "When this creature enters, **you may put two cards your
opponents own from exile into their owners' graveyards. If you do**, counter
target spell" (Ulamog's Nullifier). One cost key, ``process``, on any cost node:
an activated ability, a ``may``'s ``pay``, an ``additional_cost``.

An effect op is the near miss and the wrong card both times. Moved at
resolution, Void Attendant could be activated with nothing in exile and make a
Scion for {1}{G}, and the Nullifier's "if you do" would counter a spell after
moving one card or none. 118.3 makes the cost a precondition: a player can't pay
a cost without the resources to pay it, so the ability is not offered and the
"may" never asks.

The rules the tests hold:

- **Only cards an opponent owns.** The payer's own exiled cards are never
  fodder, so a payer with only their own cards in exile cannot pay.
- **Every such card counts** -- face down (chosen without being shown, 406.3)
  or exiled by a linked ability (the link is spent and the card stays in the
  graveyard).
- **Each card goes to its owner's graveyard**, two opponents' cards to two
  graveyards, as the cost is paid -- before the ability can be responded to.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import exile, link_exiled
from tests.conftest import activations, only_oid, pass_until, settle

ATTENDANT = "t_process_attendant"  # Void Attendant: "{1}{G}, process one: make a Scion"
NULLIFIER = "t_process_nullifier"  # Ulamog's Nullifier: "you may process two. If you do, counter"
RITUAL = "t_process_ritual"  # "As an additional cost, process one. Draw a card."
BEAR = "t_bear"  # a vanilla 2/2, the cards that end up in exile
BOLT = "t_bolt"  # {R} instant, 3 damage to a creature
SCION = "eldrazi_scion_1_1_c"


def position(builder, *, players=2, mine=(), hand=(), exiled=None):
    """P0 in their main phase with mana; ``exiled`` maps a seat to how many of
    its own Bears are in exile, put there from its graveyard."""
    exiled = exiled or {}
    b = builder(players=players).battlefield(
        0, ["forest"] * 3 + ["island"] * 3 + ["swamp"] * 3 + ["mountain"] * 3 + list(mine)
    )
    for pid in range(players):
        if pid:
            b = b.battlefield(pid, ["mountain"] * 2)
        b = b.graveyard(pid, [BEAR] * exiled.get(pid, 0)).library(pid, ["mountain"] * 20)
    game = b.hand(0, list(hand)).step(Step.PRECOMBAT_MAIN).build(advance=False)
    for player in game.state.players:
        for oid in list(player.graveyard):
            exile(game.state, oid)
    game._advance()
    return game


def exiled_of(game, pid: int) -> list[int]:
    return list(game.state.players[pid].exile)


def graveyard_of(game, pid: int) -> list[int]:
    return list(game.state.players[pid].graveyard)


def scions(game) -> int:
    return sum(1 for obj in game.state.battlefield_objects(0) if obj.def_id == SCION)


def choose_process(game, oid: int) -> None:
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS, decision
    assert decision.context.get("purpose") == "process_cost"
    index = next(i for i, option in enumerate(decision.options) if option.value == oid)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )


class TestAnActivatedAbilityCost:
    """Void Attendant."""

    def test_nothing_in_exile_means_no_activation(self, builder):
        game = position(builder, mine=(ATTENDANT,))
        assert not activations(game, only_oid(game, ATTENDANT, 0))

    def test_your_own_exiled_cards_do_not_pay(self, builder):
        """"A card **an opponent** owns": P0's own exiled Bear is no fodder."""
        game = position(builder, mine=(ATTENDANT,), exiled={0: 2})
        assert not activations(game, only_oid(game, ATTENDANT, 0))

    def test_an_opponents_card_pays_into_its_owners_graveyard(self, builder):
        game = position(builder, mine=(ATTENDANT,), exiled={1: 1})
        (card,) = exiled_of(game, 1)
        game.apply(activations(game, only_oid(game, ATTENDANT, 0))[0])
        assert game.state.objects[card].zone is Zone.GRAVEYARD
        assert graveyard_of(game, 1) == [card] and not graveyard_of(game, 0)
        settle(game)
        assert scions(game) == 1

    def test_it_is_paid_as_the_ability_goes_on_the_stack(self, builder):
        """A cost, not an effect (602.2b): gone from exile while the ability
        waits -- the Bolt in P1's hand keeps the engine from passing it away."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3 + [ATTENDANT])
            .battlefield(1, ["mountain"] * 2)
            .graveyard(1, [BEAR])
            .hand(1, [BOLT])
            .library(0, ["mountain"] * 20)
            .library(1, ["mountain"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        (card,) = graveyard_of(game, 1)
        exile(game.state, card)
        game._advance()
        game.apply(activations(game, only_oid(game, ATTENDANT, 0))[0])
        assert game.state.stack and game.state.objects[card].zone is Zone.GRAVEYARD
        assert scions(game) == 0

    def test_the_payer_chooses_which_card(self, builder):
        game = position(builder, mine=(ATTENDANT,), exiled={1: 2})
        first, second = exiled_of(game, 1)
        game.apply(activations(game, only_oid(game, ATTENDANT, 0))[0])
        choose_process(game, second)
        assert exiled_of(game, 1) == [first] and graveyard_of(game, 1) == [second]

    def test_one_card_pays_once(self, builder):
        """The card that paid is in a graveyard, so the next activation has nothing."""
        game = position(builder, mine=(ATTENDANT,), exiled={1: 1})
        attendant = only_oid(game, ATTENDANT, 0)
        game.apply(activations(game, attendant)[0])
        settle(game)
        assert not activations(game, attendant)

    def test_any_opponents_card_and_it_goes_to_that_players_graveyard(self, builder):
        game = position(builder, players=3, mine=(ATTENDANT,), exiled={2: 1})
        (card,) = exiled_of(game, 2)
        game.apply(activations(game, only_oid(game, ATTENDANT, 0))[0])
        assert graveyard_of(game, 2) == [card] and not graveyard_of(game, 1)


class TestWhichCardsCount:
    def test_a_face_down_card_is_offered_unnamed(self, builder):
        """406.3: the payer picks it without seeing it -- no name, no object
        ref for `player_view` to attach a face to."""
        game = position(builder, mine=(ATTENDANT,), exiled={1: 2})
        hidden, shown = exiled_of(game, 1)
        game.state.objects[hidden].hidden_in_exile = True
        game.apply(activations(game, only_oid(game, ATTENDANT, 0))[0])
        options = {option.value: option for option in game.pending().options}
        assert options[hidden].ref is None and "Bear" not in options[hidden].label
        assert options[shown].ref is not None
        choose_process(game, hidden)
        assert game.state.objects[hidden].zone is Zone.GRAVEYARD
        assert not game.state.objects[hidden].hidden_in_exile

    def test_a_face_down_card_alone_pays(self, builder):
        game = position(builder, mine=(ATTENDANT,), exiled={1: 1})
        (hidden,) = exiled_of(game, 1)
        game.state.objects[hidden].hidden_in_exile = True
        assert activations(game, only_oid(game, ATTENDANT, 0))

    def test_a_card_exiled_with_a_linked_ability_may_be_processed(self, builder):
        """The link is spent with the move: the card is a new object in the
        graveyard and its exiler has nothing left to return."""
        game = position(builder, mine=(ATTENDANT,), exiled={1: 1})
        (card,) = exiled_of(game, 1)
        attendant = only_oid(game, ATTENDANT, 0)
        link_exiled(game.state, card, attendant)
        game.apply(activations(game, attendant)[0])
        obj = game.state.objects[card]
        assert obj.zone is Zone.GRAVEYARD and obj.exiled_by is None


class TestAnOptionalPayment:
    """Ulamog's Nullifier: "you may put two … If you do, counter target spell"."""

    def cast_over_a_bolt(self, game):
        """P0 Bolts its own Attendant, then flashes the Nullifier in over it,
        so the Bolt is the one spell its trigger can target."""
        bolt = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BOLT
        )
        game.apply(bolt)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == NULLIFIER
            )
        )
        pass_until(
            game,
            lambda g: ((d := g.pending()) is not None and d.kind is DecisionKind.MAY)
            or (not g.state.stack and not g.state.pending_triggers),
        )

    def test_two_cards_pay_and_the_spell_is_countered(self, builder):
        game = position(builder, mine=(ATTENDANT,), hand=(BOLT, NULLIFIER), exiled={1: 3})
        attendant = only_oid(game, ATTENDANT, 0)
        self.cast_over_a_bolt(game)
        assert game.pending().kind is DecisionKind.MAY
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
        choices = game.pending()
        assert choices.kind is DecisionKind.CHOOSE_OBJECTS and choices.min_count == 2
        first, second, third = exiled_of(game, 1)
        choose_process(game, first)
        choose_process(game, third)
        assert exiled_of(game, 1) == [second]
        settle(game)
        assert game.state.objects[attendant].damage == 0, "the Bolt was countered"

    def test_declining_moves_nothing_and_counters_nothing(self, builder):
        game = position(builder, mine=(ATTENDANT,), hand=(BOLT, NULLIFIER), exiled={1: 2})
        attendant = only_oid(game, ATTENDANT, 0)
        self.cast_over_a_bolt(game)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.NO))
        settle(game)
        assert len(exiled_of(game, 1)) == 2
        assert game.state.objects[attendant].zone is Zone.GRAVEYARD

    def test_one_card_is_not_two_so_nothing_is_asked(self, builder):
        game = position(builder, mine=(ATTENDANT,), hand=(BOLT, NULLIFIER), exiled={1: 1, 0: 3})
        attendant = only_oid(game, ATTENDANT, 0)
        self.cast_over_a_bolt(game)
        assert game.pending() is None or game.pending().kind is not DecisionKind.MAY
        settle(game)
        assert len(exiled_of(game, 1)) == 1 and len(exiled_of(game, 0)) == 3
        assert game.state.objects[attendant].zone is Zone.GRAVEYARD

    def test_two_opponents_cards_go_to_two_graveyards(self, builder):
        game = position(
            builder, players=3, mine=(ATTENDANT,), hand=(BOLT, NULLIFIER), exiled={1: 1, 2: 1}
        )
        self.cast_over_a_bolt(game)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
        assert len(graveyard_of(game, 1)) == 1 and len(graveyard_of(game, 2)) == 1


def ritual_lines(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == RITUAL
    ]


class TestAnAdditionalCostToCast:
    def test_unpayable_means_uncastable(self, builder):
        game = position(builder, hand=(RITUAL,), exiled={0: 2})
        assert not ritual_lines(game)

    def test_paid_on_casting(self, builder):
        game = position(builder, hand=(RITUAL,), exiled={1: 1})
        (card,) = exiled_of(game, 1)
        game.apply(ritual_lines(game)[0])
        assert game.state.objects[card].zone is Zone.GRAVEYARD
        settle(game)
        assert len(game.state.players[0].hand) == 1


class TestTheLoader:
    def base(self, **cost):
        return {
            "id": "t_process_probe",
            "name": "Probe",
            "oracle_text": "Process: draw.",
            "mana_cost": "{1}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "activated",
                    "text": "Process: draw.",
                    "cost": cost,
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }

    def test_a_count_compiles(self):
        card = compile_card(CardModel.model_validate(self.base(process=2)))
        assert card.abilities[0].cost.process == 2

    def test_a_negative_count_is_refused(self):
        with pytest.raises(DslError, match="process"):
            compile_card(CardModel.model_validate(self.base(process=-1)))

    def test_it_is_not_a_tap_only_mana_shape(self):
        card = compile_card(CardModel.model_validate(self.base(process=1)))
        assert not card.abilities[0].cost.is_tap_only()
