"""A keyword action that names its own token travels with the deck.

`empower`, `amass` and `incubate` never write a `create_token`: the op picks the
token itself (`EMPOWER_TOKEN`, `AMASS_TOKENS`, `INCUBATOR_TOKEN`). The deck
bundle asks `token_references` which tokens a card can make, so an op it does
not know about ships a deck whose Plan for All Outcomes creates a Jace the
client has never been sent. Each of the three is checked here on its shipped
card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.linking import token_references
from commanderblitz.cards.registry import default_registry
from commanderblitz.engine.effects.ops_counters import (
    AMASS_TOKENS,
    EMPOWER_TOKEN,
    INCUBATOR_TOKEN,
)


@pytest.fixture(scope="module")
def registry():
    return default_registry().registry


@pytest.mark.parametrize(
    ("card_id", "token_id"),
    [
        ("plan_for_all_outcomes", EMPOWER_TOKEN),
        ("fatehold_charm", EMPOWER_TOKEN),
        ("dreadhorde_invasion", AMASS_TOKENS["Zombie"]),
        ("sunfall", INCUBATOR_TOKEN),
    ],
)
def test_the_card_names_the_token_its_op_creates(registry, card_id, token_id):
    assert token_id in token_references(registry.get(card_id))
