"""Anger — a static ability that works from the **graveyard**.

    Haste
    As long as this card is in your graveyard and you control a Mountain,
    creatures you control have haste.

`active_zones` already existed on the ability schema and already accepted
`"graveyard"`, but the loader read it only on the activated and triggered
branches: `_compile_static` built its `Ability` without it, so every static was
pinned to the battlefield default. And `_battlefield_statics` was the only
source of statics in the engine.

Between them that made Anger the **inverse** of the printed card. The static
switched on the moment Anger resolved as a 2/2 — granting the team haste from
play, which the card never does — and switched off the moment it died, which is
exactly when the card is supposed to start working. It would have loaded, shown
its text, and been wrong in the one way that is hardest to notice: it does
grant haste, just never when it should.

`t_wrong_anger` is that card, kept as the counterfactual. It is byte-for-byte
the same static with `active_zones` omitted, and the two are asserted to be
exact opposites of each other.

The zone half of the sentence needs no condition of its own. Being collected
only while the card sits in a graveyard *is* "as long as this card is in your
graveyard", and `characteristics._graveyard_statics` is what enforces it —
which is why `static_condition_keys` gained no zone predicate.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Keyword, Zone

ANGER = "t_anger"
WRONG = "t_wrong_anger"
BEAR = "t_bear"


def board(builder, card: str, *, where: str, mountain: bool = True):
    b = builder(players=2).battlefield(0, [BEAR])
    if mountain:
        b = b.battlefield(0, ["mountain"])
    b = b.graveyard(0, [card]) if where == "graveyard" else b.battlefield(0, [card])
    return b.build(advance=False)


def bear_has_haste(game) -> bool:
    state = game.state
    bear = next(
        o.oid for o in state.battlefield_objects(0) if state.card_of(o).id == BEAR
    )
    return Keyword.HASTE.value in chars(state, bear).keywords


class TestItWorksFromTheGraveyard:
    def test_the_team_gets_haste(self, builder):
        assert bear_has_haste(board(builder, ANGER, where="graveyard"))

    def test_the_condition_still_gates_it(self, builder):
        """"…and you control a **Mountain**" is an ordinary static condition."""
        assert not bear_has_haste(
            board(builder, ANGER, where="graveyard", mountain=False)
        )


class TestItDoesNotWorkFromPlay:
    def test_anger_on_the_battlefield_grants_nothing(self, builder):
        """The half that is easiest to get backwards.

        A 2/2 Anger in play is a creature with haste and nothing else. The
        anthem belongs to the graveyard.
        """
        assert not bear_has_haste(board(builder, ANGER, where="battlefield"))

    def test_anger_still_has_haste_itself(self, builder):
        """Its printed keyword is unaffected -- only the static moved zones."""
        game = board(builder, ANGER, where="battlefield")
        state = game.state
        anger = next(
            o.oid for o in state.battlefield_objects(0) if state.card_of(o).id == ANGER
        )
        assert Keyword.HASTE.value in chars(state, anger).keywords


class TestTheCounterfactualIsTheExactInverse:
    """Byte-for-byte the same static, without `active_zones`."""

    def test_the_old_shape_grants_from_play(self, builder):
        assert bear_has_haste(board(builder, WRONG, where="battlefield"))

    def test_and_grants_nothing_from_the_graveyard(self, builder):
        assert not bear_has_haste(board(builder, WRONG, where="graveyard"))

    def test_the_two_disagree_in_both_zones(self, builder):
        for where in ("battlefield", "graveyard"):
            real = bear_has_haste(board(builder, ANGER, where=where))
            old = bear_has_haste(board(builder, WRONG, where=where))
            assert real is not old, f"they must be opposites in the {where}"


class TestTheZonesAreDeclared:
    def test_anger_declares_the_graveyard(self, registry):
        assert registry.get(ANGER).abilities[0].active_zones == (Zone.GRAVEYARD,)

    def test_the_default_is_still_the_battlefield(self, registry):
        assert registry.get(WRONG).abilities[0].active_zones == (Zone.BATTLEFIELD,)

    def test_a_zone_nothing_collects_is_refused(self):
        """A static in hand would load clean and never once be gathered."""
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.cards.schema import CardModel
        from commanderblitz.engine.errors import DslError

        card = CardModel.model_validate(
            {
                "id": "t_bad_zone_static",
                "name": "Test Bad Zone Static",
                "oracle_text": "Creatures you control have haste.",
                "mana_cost": "{R}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Creatures you control have haste.",
                        "effect": "grant_keyword",
                        "keywords": ["haste"],
                        "active_zones": ["hand"],
                        "affects": {"controller": "you", "types": ["Creature"]},
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="graveyard"):
            compile_card(card, source="test")
