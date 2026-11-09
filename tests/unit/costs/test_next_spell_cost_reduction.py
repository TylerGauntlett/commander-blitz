"""A one-shot discount on the next matching spell.

    "{T}: The next instant or sorcery spell you cast this turn costs {X} less
    to cast, where X is the number of Wizards you control as this ability
    resolves."                                        -- Kaza, Roil Chaser

Neither half of the reduction language said it. A card's `cost_reduction` and
the `spell_cost_reduction` static are **continuous**: they recount the board
every time the spell is priced, and they discount every matching spell for as
long as their source stands. This one is fixed as the ability resolves, owned
by the player (Kaza may be gone by the time the spell is cast), used up by one
spell, and over at cleanup -- `grant_flash_permission`'s ``next_spell`` shape
with a price instead of a timing.

The witnesses are Kaza and Mutated Cultist ("the next spell you cast this turn
costs {1} less … for each counter removed this way"), which is why ``types`` is
optional and ``amount`` is any value.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.cost_reduction import cost_reduction
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, settle_to_priority

KAZA = "t_kaza"  # {T}: next instant or sorcery costs {X} less, X = Wizards you control
WIZARD = "t_wizard"  # a vanilla 1/1 Wizard
CULTIST = "t_next_discount_any"  # {T}: the next spell costs {2} less
CANCEL = "cancel"  # {1}{U}{U} instant
OPT = "opt"  # {U} instant
BEARS = "grizzly_bears"  # {1}{G} creature


def position(builder, board, hand=()):
    return (
        builder(players=2)
        .battlefield(0, [*board, "island", "island", "island", "forest", "forest"])
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        # A spell always in hand, so the auto-pass stops at the player's
        # priority instead of running the turn out to cleanup.
        .hand(0, [*hand, OPT])
        .build()
    )


def oid_of(game, card_id: str) -> int:
    return next(o for o in game.state.battlefield if game.state.objects[o].def_id == card_id)


def activate(game, card_id: str) -> None:
    (action,) = activations(game, oid_of(game, card_id))
    game.apply(action)
    settle_to_priority(game)


def discount_on(game, registry, card_id: str) -> int:
    return cost_reduction(game.state, 0, registry.get(card_id))


def cast(game, card_id: str) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    settle_to_priority(game)


class TestItIsFixedAsItResolves:
    def test_it_counts_the_wizards(self, builder, registry):
        """Kaza and two more Wizards: {3} less."""
        game = position(builder, [KAZA, WIZARD, WIZARD])
        activate(game, KAZA)

        assert discount_on(game, registry, CANCEL) == 3

    def test_a_wizard_leaving_afterwards_changes_nothing(self, builder, registry):
        """"as this ability resolves" -- read once, not at pricing time."""
        game = position(builder, [KAZA, WIZARD, WIZARD])
        activate(game, KAZA)
        from commanderblitz.engine.zones import move_object

        move_object(game.state, oid_of(game, WIZARD), Zone.GRAVEYARD)

        assert discount_on(game, registry, CANCEL) == 3

    def test_nothing_before_the_activation(self, builder, registry):
        """The control: Kaza standing there discounts nothing."""
        game = position(builder, [KAZA, WIZARD, WIZARD])

        assert discount_on(game, registry, CANCEL) == 0


class TestItIsTheNextMatchingSpell:
    def test_a_creature_spell_is_not_discounted(self, builder, registry):
        game = position(builder, [KAZA])
        activate(game, KAZA)

        assert discount_on(game, registry, BEARS) == 0

    def test_the_cast_spends_it(self, builder, registry):
        game = position(builder, [KAZA])
        activate(game, KAZA)
        cast(game, OPT)

        assert discount_on(game, registry, CANCEL) == 0

    def test_a_creature_cast_in_between_leaves_it_waiting(self, builder, registry):
        game = position(builder, [KAZA], hand=[BEARS])
        activate(game, KAZA)
        cast(game, BEARS)

        assert discount_on(game, registry, CANCEL) == 1

    def test_the_spell_is_charged_the_discounted_price(self, builder):
        """{2} off Grizzly Bears' {1}{G} leaves {G}: one Forest pays it and the
        other stays untapped. Generic only, so the {G} is still owed."""
        game = position(builder, [CULTIST], hand=[BEARS])
        activate(game, CULTIST)
        cast(game, BEARS)
        lands = [
            o for o in game.state.battlefield
            if game.state.objects[o].def_id in ("island", "forest")
        ]

        assert sum(game.state.objects[o].tapped for o in lands) == 1

    def test_an_untyped_discount_takes_any_spell(self, builder, registry):
        """Mutated Cultist: "the next spell you cast this turn"."""
        game = position(builder, [CULTIST])
        activate(game, CULTIST)

        assert discount_on(game, registry, BEARS) == 2


class TestItWearsOff:
    def test_it_is_gone_next_turn(self, builder, registry):
        from tests.conftest import pass_until

        game = position(builder, [KAZA, WIZARD])
        activate(game, KAZA)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)

        assert discount_on(game, registry, CANCEL) == 0

    def test_two_activations_both_apply(self, builder, registry):
        """Each is its own effect about the same next spell."""
        game = position(builder, [CULTIST, CULTIST])
        for oid in [o for o in game.state.battlefield if game.state.objects[o].def_id == CULTIST]:
            (action,) = activations(game, oid)
            game.apply(action)
            settle_to_priority(game)

        assert discount_on(game, registry, BEARS) == 4


class TestTheLoaderPlacesIt:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "{T}: The next spell you cast this turn costs {1} less to cast.",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "{T}: The next spell you cast this turn costs {1} less to cast.",
                        "cost": {"tap": True},
                        "effects": [effect],
                    }
                ],
            }
        )

    def test_it_needs_an_amount(self):
        with pytest.raises(DslError, match="needs an 'amount'"):
            compile_card(self._card({"op": "next_spell_cost_reduction"}))

    def test_a_misspelt_type_is_refused(self):
        with pytest.raises(DslError, match="unknown card type"):
            compile_card(
                self._card(
                    {"op": "next_spell_cost_reduction", "amount": {"const": 1}, "types": ["Instnat"]}
                )
            )
