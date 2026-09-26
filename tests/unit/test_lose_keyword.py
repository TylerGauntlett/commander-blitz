"""``lose_keyword`` — "lose first strike **and can't have or gain** first strike".

    Archetype of Courage — "Creatures you control have first strike. Creatures
    your opponents control lose first strike and can't have or gain first
    strike."

The keyword pipeline in `characteristics._compute` was additive from end to end:
every step does `keywords.update(...)` — the `grant_keyword` statics at layer 2,
keyword counters at 2b (122.1c), until-end-of-turn grants at 6, suspend's haste
at 7 and `granted_keywords` at 8 — and no step ever discarded one. The single
subtractive thing in the whole language was `lose_all_abilities`.

**Where this layer sits is the whole design, and it is the opposite end of the
file from the near miss.** `lose_all_abilities` is deliberately *early*, at
layer 1, because 613.1b keeps whatever is added after a removal: an Imprisoned
in the Moon plus a Levitation leaves the permanent flying, and that is correct.
Archetype's sentence is the other kind. "Can't have or gain" is a standing
prohibition rather than a one-time subtraction, so it has to outrank every adder
above it — which makes it the **last** step, after even `granted_keywords`.
Placed anywhere earlier, an opponent's own anthem or a first-strike counter
hands the keyword straight back, and the card reads as working while doing
nothing on the only boards where it matters. `TestItBeatsALaterGrant` and
`TestItBeatsAKeywordCounter` are that claim.

`lose_all_abilities` is also wrong on breadth, not only on position: it would
take the opponents' flying, their triggered abilities and their activated
abilities too, turning a first-strike hoser into half a Humility.
`TestItTakesOnlyWhatItNames` is that one.

Witness: Archetype of Courage
(`data/authoring/answers/archetype_of_courage.json`).
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import Keyword
from automtg.engine.errors import DslError
from automtg.engine.primitives import add_counters
from tests.conftest import only_oid

ARCHETYPE = "t_archetype"  # the grant half and the lose half, as printed
LOSE_ONLY = "t_archetype_lose_only"  # the lose half alone
FS_ANTHEM = "t_first_strike_anthem"  # an opponent-side grant it has to beat
FLY_ANTHEM = "t_flying_anthem"  # a keyword it must leave alone
STRIKER = "t_striker"  # a creature with first strike printed
BEAR = "t_bear"  # 2/2 vanilla
FIRST_STRIKE = Keyword.FIRST_STRIKE.value


def board(builder, mine=(LOSE_ONLY,), theirs=(STRIKER,)):
    """Player 0 holds the Archetype; player 1 is the opponent it names."""
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 3 + list(mine))
        .battlefield(1, ["plains"] * 3 + list(theirs))
        .hand(0, ["plains"])
        .hand(1, ["plains"])
        .build()
    )


def keywords(game, oid) -> frozenset[str]:
    return chars(game.state, oid).keywords


class TestItTakesThePrintedKeyword:
    def test_the_opponents_creature_loses_it(self, builder):
        game = board(builder)
        assert FIRST_STRIKE not in keywords(game, only_oid(game, STRIKER, 1))

    def test_without_the_static_it_keeps_it(self, builder):
        """Pins that the removal is the static's and not the position's."""
        game = board(builder, mine=())
        assert FIRST_STRIKE in keywords(game, only_oid(game, STRIKER, 1))

    def test_its_own_side_is_untouched(self, builder):
        """"Creatures your **opponents** control" -- the filter is not
        decoration, and the whole printed card is a one-sided hoser."""
        game = board(builder, mine=(LOSE_ONLY, STRIKER))
        assert FIRST_STRIKE in keywords(game, only_oid(game, STRIKER, 0))

    def test_the_printed_card_does_both_halves_at_once(self, builder):
        """Archetype of Courage as printed: its own creatures gain it while the
        opponents' cannot have it."""
        game = board(builder, mine=(ARCHETYPE, BEAR), theirs=(STRIKER,))
        assert FIRST_STRIKE in keywords(game, only_oid(game, BEAR, 0))
        assert FIRST_STRIKE not in keywords(game, only_oid(game, STRIKER, 1))


class TestItBeatsALaterGrant:
    """"…and can't have or gain first strike" -- the clause that decides the
    layer position.

    An opponent's own anthem is a `grant_keyword` at layer 2. If the removal ran
    anywhere before layer 8 this would hand the keyword back, and the card would
    look correct in every test above while failing on the one board it exists
    for.
    """

    def test_the_opponents_own_anthem_cannot_give_it_back(self, builder):
        game = board(builder, theirs=(BEAR, FS_ANTHEM))
        assert FIRST_STRIKE not in keywords(game, only_oid(game, BEAR, 1))

    def test_that_anthem_works_when_the_archetype_is_gone(self, builder):
        """Pins that the anthem is real and the position is not rigged."""
        game = board(builder, mine=(), theirs=(BEAR, FS_ANTHEM))
        assert FIRST_STRIKE in keywords(game, only_oid(game, BEAR, 1))


class TestItBeatsAKeywordCounter:
    """122.1c -- "a permanent with a keyword counter on it has that keyword
    ability". Layer 2b, and another adder the prohibition has to outrank."""

    def test_a_first_strike_counter_cannot_give_it_back(self, builder):
        game = board(builder, theirs=(BEAR,))
        oid = only_oid(game, BEAR, 1)
        add_counters(game.state, oid, FIRST_STRIKE, 1)
        assert FIRST_STRIKE not in keywords(game, oid)

    def test_the_counter_works_when_the_archetype_is_gone(self, builder):
        game = board(builder, mine=(), theirs=(BEAR,))
        oid = only_oid(game, BEAR, 1)
        add_counters(game.state, oid, FIRST_STRIKE, 1)
        assert FIRST_STRIKE in keywords(game, oid)


class TestItTakesOnlyWhatItNames:
    """The breadth half of why `lose_all_abilities` is not this.

    That static would also take the opponents' flying -- and their triggered and
    activated abilities -- which is half a Humility rather than a first-strike
    hoser.
    """

    def test_another_keyword_survives(self, builder):
        game = board(builder, theirs=(BEAR, FLY_ANTHEM))
        assert Keyword.FLYING.value in keywords(game, only_oid(game, BEAR, 1))

    def test_and_the_named_one_still_goes(self, builder):
        """Both on the same board, so the difference is measured rather than
        described."""
        game = board(builder, theirs=(STRIKER, FLY_ANTHEM))
        oid = only_oid(game, STRIKER, 1)
        assert Keyword.FLYING.value in keywords(game, oid)
        assert FIRST_STRIKE not in keywords(game, oid)


class TestTheLoaderRefusesTheSilentFailures:
    def _card(self, **extra) -> CardModel:
        static = {
            "kind": "static",
            "text": "Creatures your opponents control lose first strike and "
            "can't have or gain first strike.",
            "effect": "lose_keyword",
            "keywords": ["first_strike"],
            "affects": {"controller": "opponent", "types": ["Creature"]},
        }
        static.update(extra)
        return CardModel.model_validate(
            {
                "id": "t_lose_probe",
                "name": "Lose Probe",
                "mana_cost": "{1}{W}{W}",
                "oracle_text": "Creatures your opponents control lose first "
                "strike and can't have or gain first strike.",
                "types": ["Creature"],
                "power": 2,
                "toughness": 2,
                "abilities": [static],
            }
        )

    def test_the_printed_shape_loads(self):
        assert compile_card(self._card()) is not None

    def test_no_keywords_is_refused(self):
        """An empty list subtracts nothing and would load clean, printing a
        prohibition over an inert static."""
        with pytest.raises(DslError, match="needs the keywords it removes"):
            compile_card(self._card(keywords=[]))

    def test_no_affects_is_refused(self):
        """The filter defaults to your own side, so an absent one is a card that
        reads as a hoser and hoses its controller instead."""
        with pytest.raises(DslError, match="needs 'affects'"):
            compile_card(self._card(affects=None))
