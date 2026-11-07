"""``not_subtypes`` in a static filter -- "each other **non-Human** creature".

    "Each other non-Human creature you control enters with an additional +1/+1
     counter on it."  -- Grumgully, the Generous
    "...each non-Equipment artifact and non-Aura enchantment you control..."
     -- Bello, Bard of the Brambles

A subtype the permanent must *lack*. The effect-side selector language always
had the key; the static one did not, and nothing else says it. `not_types` is a
complement over card types, and an `any_of` over every other creature type is
not a finite spelling. Written without it, Grumgully would counter every
creature, Humans included -- a stronger card than the printed one.

Read off the same set `subtypes` reads -- the printed face with text changes
applied, plus the subtypes an effect recorded on the object -- so a creature
something made a Human is spared exactly as a printed Human is (205.3, 613.1d).
Cost-reduction filters, which accept every static key, read it too.
"""

from __future__ import annotations

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.zones import destroy
from tests.conftest import oids_of, pt, static_probe

LORD = "t_ns_lord"
HUMAN = "t_ns_human"
BEAR = "t_bear"  # a green 2/2 Bear


def board(builder, mine=(HUMAN, BEAR)):
    return builder(players=2).battlefield(0, [LORD, *mine]).build()


class TestTheFilter:
    def test_a_non_human_gets_the_bonus(self, builder):
        game = board(builder)
        assert pt(game, oids_of(game, BEAR)[0]) == (3, 3)

    def test_a_human_does_not(self, builder):
        game = board(builder)
        assert pt(game, oids_of(game, HUMAN)[0]) == (2, 2)

    def test_an_opponents_non_human_does_not(self, builder):
        game = builder(players=2).battlefield(0, [LORD]).battlefield(1, [BEAR]).build()
        assert pt(game, oids_of(game, BEAR, 1)[0]) == (2, 2)

    def test_a_recorded_subtype_counts_as_printed(self, builder):
        """A Bear something has made a Human is a Human, and is spared."""
        game = board(builder, mine=(BEAR,))
        bear = game.state.objects[oids_of(game, BEAR)[0]]
        bear.added_subtypes = (*bear.added_subtypes, "Human")
        game.state.bump_chars()
        assert pt(game, bear.oid) == (2, 2)

    def test_it_wears_off_with_the_source(self, builder):
        game = board(builder)
        destroy(game.state, oids_of(game, LORD)[0])
        assert pt(game, oids_of(game, BEAR)[0]) == (2, 2)


class TestTheLoader:
    def test_a_static_may_write_it(self):
        compile_card(
            CardModel.model_validate(
                static_probe(
                    {
                        "effect": "buff",
                        "affects": {"types": ["Creature"], "not_subtypes": ["Human"]},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                    }
                )
            )
        )
