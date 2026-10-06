"""Phoenix, Warden of Fire — "any number of target creature cards **with total
mana value 6 or less**".

    III - Flames of Rebirth - Return any number of target creature cards with
    total mana value 6 or less from your graveyard to the battlefield.

A cap on the picks **together**, and no selector clause can say it. Every clause
in `matches` is evaluated against one candidate in isolation, so
`mana_value: {"op": "<=", "value": 6}` says "each of these costs six or less" --
a far wider card, and one that looks right until somebody reanimates six
one-drops for six mana of creatures. `t_each_six` is exactly that card.

So it lives where the *combinations* are built, in the same slot
`one_per_player` occupies and for the same reason: both are facts about a set of
chosen objects rather than about any one of them.

Read off the printed cost, which is all a card in a graveyard has -- nothing is
applying to it, and an X in a mana cost is 0 anywhere but on the stack (202.3b).

**Not re-checked on resolution.** 608.2b asks whether each target is still legal
one at a time; the total was a condition on the *choice*, and a spell whose
targets have partly gone does not have its arithmetic redone.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.errors import DslError
from automtg.engine.targeting import enumerate_target_tuples

REBIRTH = "t_flames_of_rebirth"
EACH = "t_each_six"
DORK = "t_dork"   # {G},     mana value 1
BEAR = "t_bear"   # {1}{G},  mana value 2
BIG = "t_big"     # {5}{G},  mana value 6


def board(builder, buried=(DORK, BEAR, BIG)):
    return (
        builder(players=2)
        .graveyard(0, list(buried))
        .battlefield(0, ["mountain"] * 5)
        .hand(0, ["forest"])
        .library(0, ["forest"] * 10)
        .build(advance=False)
    )


def choices(game, card: str):
    """Every combination offered, as sorted tuples of card ids."""
    state = game.state
    spec = state.registry.get(card).targets
    return sorted(
        tuple(sorted(state.card(ref.id).id for ref in combo))
        for combo in enumerate_target_tuples(state, 0, spec, None)
    )


class TestTheCapIsOnThePicksTogether:
    def test_two_small_creatures_are_offered(self, builder):
        """1 + 2 = 3."""
        assert (BEAR, DORK) in choices(board(builder), REBIRTH)

    def test_the_six_drop_alone_is_offered(self, builder):
        """Exactly at the cap, which "or less" includes."""
        assert (BIG,) in choices(board(builder), REBIRTH)

    def test_the_six_drop_with_anything_else_is_not(self, builder):
        """6 + 1 = 7, and this is the whole clause."""
        offered = choices(board(builder), REBIRTH)
        assert (BIG, DORK) not in offered
        assert (BEAR, BIG) not in offered

    def test_all_three_are_not(self, builder):
        assert (BEAR, BIG, DORK) not in choices(board(builder), REBIRTH)

    def test_declining_is_still_offered(self, builder):
        """"**any number** of target …" includes none."""
        assert () in choices(board(builder), REBIRTH)


class TestTheCounterfactual:
    def test_a_per_card_cap_offers_all_three_at_once(self, builder):
        """`mana_value: {"op": "<=", "value": 6}` -- each of them passes, so
        the whole graveyard comes back."""
        assert (BEAR, BIG, DORK) in choices(board(builder), EACH)

    def test_the_capped_version_offers_strictly_fewer(self, builder):
        game = board(builder)
        assert len(choices(game, REBIRTH)) < len(choices(game, EACH))


def _spec(**overrides):
    target = {
        "id": "t1",
        "kind": "card_in_graveyard",
        "count": "any",
        "total_mana_value": 6,
        "selector": {"zone": "graveyard", "types": ["Creature"]},
    }
    target.update(overrides)
    return CardModel.model_validate(
        {
            "id": "t_bad_total",
            "name": "Test Bad Total",
            "oracle_text": "Return them.",
            "mana_cost": "{1}",
            "types": ["Sorcery"],
            "targets": [target],
            "spell_effects": [
                {
                    "op": "return_from_graveyard",
                    "destination": "battlefield",
                    "controller": "you",
                    "objects": {"target": "t1"},
                }
            ],
        }
    )


class TestTheLoaderChecksIt:
    def test_a_real_cap_loads(self):
        compile_card(_spec(), source="test")

    def test_a_cap_of_zero_is_refused(self):
        """A spec that can only ever choose nothing, printed as though it
        chose something."""
        with pytest.raises(DslError, match="would allow nothing"):
            compile_card(_spec(total_mana_value=0), source="test")

    def test_a_player_target_is_refused(self):
        """A player has no mana value, so the clause would be read against zero
        for every candidate and cap nothing at all."""
        with pytest.raises(DslError, match="does not have"):
            compile_card(
                _spec(kind="player", selector={"controller": "opponent"}), source="test"
            )
