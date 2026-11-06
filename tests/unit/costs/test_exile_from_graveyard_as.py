"""An exile-from-graveyard cost that names the cards it exiled.

    Coin of Fate: "{3}{W}, {T}, Exile two creature cards from your graveyard,
    Sacrifice this artifact: An opponent chooses one of the exiled cards. You
    put that card on the bottom of your library and return the other to the
    battlefield tapped. You become the monarch."

`exile_from_graveyard` already charged "exile two creature cards from your
graveyard", but it was write-only: the cards went to exile and nothing the
ability did could find them again. A bare `{"zone": "exile"}` selector reaches
every card in exile, which is a different card, and `exiled_with: "self"` reads
a link (607.2a) this cost never writes -- and Coin of Fate's source is
sacrificed as part of the same payment, so nothing would be left to link to.
The capability is `as` on that cost, the graveyard twin of `sacrifice`'s and
`tap_permanents`' `as`.

What the binding holds is the rules argument. The cards are exiled while the
cost is paid (601.2h, via 602.2b), so the ability's effects refer to *those
objects in exile*. That makes the binding a set of oids, not one card and not a
snapshot: "one of the exiled cards" and "the other" are both choices among the
same set, and two cards bound as their first would make "the other" nobody. And
an object that leaves exile in response is a new object (400.7), so a reader
writes `zone: "exile"` beside the binding -- a card that came back to the
graveyard is no longer one of "the exiled cards", and the opponent's choice is
over whatever is still there.

The near miss is the `exile` **op** with `as` in the effects. That exiles on
resolution, so the Coin could be activated with an empty graveyard and
responded to before anything had been exiled -- a different card.

The witness is Coin of Fate (`coin_of_fate` in `data/cards/auto/`);
`t_coin_outlet` is its shape.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until

COIN = "t_coin_outlet"
BEAR = "t_bear"  # 2/2
GIANT = "t_big"  # 6/6


def position(builder, graveyard=(BEAR, GIANT), *, players: int = 2):
    """The Coin, four Plains for {3}{W}, a graveyard, and opponents holding Bolts.

    The Bolts are never cast. They keep each opponent from having a priority
    window with nothing in it but "pass", which would be passed automatically
    and let the ability resolve before a test could look at the stack.
    """
    b = (
        builder(players=players)
        .battlefield(0, [COIN, "plains", "plains", "plains", "plains"])
        .graveyard(0, list(graveyard))
        .library(0, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
    )
    for pid in range(1, players):
        b = b.hand(pid, ["t_bolt"]).battlefield(pid, ["mountain"]).library(pid, ["island"] * 20)
    game = b.build()
    return game, only_oid(game, COIN)


def in_graveyard(game, card_id: str) -> list[int]:
    return [
        oid for oid in game.state.players[0].graveyard if game.state.objects[oid].def_id == card_id
    ]


def card(game, card_id: str) -> int:
    (oid,) = in_graveyard(game, card_id)
    return oid


def coin_action(game, coin: int):
    return next(
        (a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == coin),
        None,
    )


def choose(game, *oids: int) -> None:
    """Answer the pending object choice with exactly ``oids``."""
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS, decision
    wanted = set(oids)
    for index, option in enumerate(decision.options):
        if option.ref is not None and option.ref.id in wanted:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
    if game.pending() is decision:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


def activate(game, coin: int, *exiled: int) -> None:
    """Activate the Coin, exiling ``exiled`` when the engine asks which."""
    action = coin_action(game, coin)
    assert action is not None, "the Coin's ability was not offered"
    game.apply(action)
    decision = game.pending()
    if (
        decision is not None
        and decision.kind is DecisionKind.CHOOSE_OBJECTS
        and decision.context.get("purpose") == "exile_cost"
    ):
        choose(game, *exiled)


def resolve_until_choice(game) -> None:
    """Pass until the ability asks somebody to pick one of the exiled cards."""
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None
        and d.kind is DecisionKind.CHOOSE_OBJECTS
        and d.context.get("purpose") == "choose_permanents",
    )


def resolve(game) -> None:
    pass_until(game, lambda g: not g.state.stack)


def zone(game, oid: int) -> Zone:
    return game.state.objects[oid].zone


class TestWhenItIsOffered:
    def test_two_creature_cards_make_it_offered(self, builder):
        game, coin = position(builder)
        assert coin_action(game, coin) is not None

    def test_one_creature_card_is_not_enough(self, builder):
        """`as` names the cards; it does not loosen the count that gates it."""
        game, coin = position(builder, graveyard=(BEAR, "island"))
        assert coin_action(game, coin) is None


class TestPayingIt:
    def test_the_cards_are_in_exile_before_the_ability_resolves(self, builder):
        game, coin = position(builder)
        bear, giant = card(game, BEAR), card(game, GIANT)

        activate(game, coin, bear, giant)

        assert game.state.stack, "the ability should still be on the stack"
        assert zone(game, bear) is Zone.EXILE
        assert zone(game, giant) is Zone.EXILE

    def test_the_binding_is_every_card_the_cost_exiled(self, builder):
        """Two cards exiled, two cards named -- "the other" needs the second."""
        game, coin = position(builder)
        bear, giant = card(game, BEAR), card(game, GIANT)

        activate(game, coin, bear, giant)

        assert sorted(game.state.stack[-1].bindings["exiled"]) == sorted([bear, giant])

    def test_it_names_only_the_cards_chosen_to_pay(self, builder):
        """A third creature card left in the graveyard is not one of them."""
        game, coin = position(builder, graveyard=(BEAR, BEAR, GIANT))
        first, second = in_graveyard(game, BEAR)
        giant = card(game, GIANT)

        activate(game, coin, first, giant)

        assert sorted(game.state.stack[-1].bindings["exiled"]) == sorted([first, giant])
        assert zone(game, second) is Zone.GRAVEYARD


class TestResolving:
    def test_the_opponent_chooses_among_exactly_the_exiled_cards(self, builder):
        game, coin = position(builder)
        bear, giant = card(game, BEAR), card(game, GIANT)
        activate(game, coin, bear, giant)

        resolve_until_choice(game)

        decision = game.pending()
        assert decision.player == 1
        assert {o.ref.id for o in decision.options} == {bear, giant}

    def test_another_card_in_exile_is_not_offered(self, builder):
        """The near miss a bare `{"zone": "exile"}` would be."""
        game, coin = position(builder, graveyard=(BEAR, GIANT, BEAR))
        bear, stray = in_graveyard(game, BEAR)
        giant = card(game, GIANT)
        move_object(game.state, stray, Zone.EXILE)
        activate(game, coin, bear, giant)

        resolve_until_choice(game)

        assert stray not in {o.ref.id for o in game.pending().options}

    def test_the_chosen_card_goes_to_the_bottom_and_the_other_returns_tapped(self, builder):
        game, coin = position(builder)
        bear, giant = card(game, BEAR), card(game, GIANT)
        activate(game, coin, bear, giant)
        resolve_until_choice(game)

        choose(game, giant)
        resolve(game)

        assert game.state.players[0].library[-1] == giant
        assert game.state.objects[bear].on_battlefield
        assert game.state.objects[bear].tapped
        assert game.state.monarch == 0

    def test_at_a_pod_the_opponent_you_pick_is_the_one_asked(self, builder):
        """"An opponent chooses" -- one seat, the one the controller names."""
        game, coin = position(builder, players=3)
        bear, giant = card(game, BEAR), card(game, GIANT)
        activate(game, coin, bear, giant)
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.CHOOSE_PLAYER,
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and game.pending().options[a.choice].value == 2
            )
        )
        resolve_until_choice(game)

        assert game.pending().player == 2


class TestACardThatLeftExile:
    def test_it_is_no_longer_one_of_the_exiled_cards(self, builder):
        """400.7: back in the graveyard it is a new object. The opponent has
        nothing left to choose between, and the one still in exile is the
        only card the ability can move -- it is "that card", not "the other"."""
        game, coin = position(builder)
        bear, giant = card(game, BEAR), card(game, GIANT)
        activate(game, coin, bear, giant)
        move_object(game.state, giant, Zone.GRAVEYARD)

        resolve(game)

        assert zone(game, giant) is Zone.GRAVEYARD
        assert game.state.players[0].library[-1] == bear
        assert not game.state.objects[bear].on_battlefield


COIN_MODEL = {
    "id": "t_coin_guard",
    "name": "Test Coin Guard",
    "oracle_text": "Exile two creature cards from your graveyard: Return them.",
    "types": ["Artifact"],
    "abilities": [
        {
            "kind": "activated",
            "text": "Exile two creature cards from your graveyard: Return them.",
            "cost": {"exile_from_graveyard": {"types": ["Creature"], "count": 2, "as": "exiled"}},
            "effects": [
                {
                    "op": "put_onto_battlefield",
                    "objects": {"binding": "exiled", "zone": "exile"},
                }
            ],
        }
    ],
}


def _with_exile(selector: dict) -> dict:
    card = copy.deepcopy(COIN_MODEL)
    card["abilities"][0]["cost"]["exile_from_graveyard"] = selector
    return card


class TestLoadTimeGuards:
    def test_the_named_cost_loads(self):
        card = compile_card(CardModel.model_validate(COIN_MODEL))
        assert card.abilities[0].cost.exile_from_graveyard["as"] == "exiled"

    def test_an_empty_name_is_refused(self):
        with pytest.raises(DslError, match="a binding name"):
            compile_card(CardModel.model_validate(_with_exile({"types": ["Creature"], "as": ""})))

    def test_naming_it_on_a_spells_additional_cost_is_refused(self):
        """Only an activated ability's effects receive what its cost named; on
        a spell the name would bind nothing and every read of it would be empty."""
        spell = {
            "id": "t_coin_spell",
            "name": "Test Coin Spell",
            "oracle_text": "As an additional cost, exile a creature card from your graveyard.",
            "mana_cost": "{W}",
            "types": ["Sorcery"],
            "additional_cost": {"exile_from_graveyard": {"types": ["Creature"], "as": "exiled"}},
            "spell_effects": [
                {"op": "put_onto_battlefield", "objects": {"binding": "exiled", "zone": "exile"}}
            ],
        }
        with pytest.raises(DslError, match="only an activated ability"):
            compile_card(CardModel.model_validate(spell))
