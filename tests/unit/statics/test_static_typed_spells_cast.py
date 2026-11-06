""""Two or more **noncreature** spells this turn": the typed cast count in a static.

    "As long as you've cast two or more noncreature spells this turn, Lyse
    Hext has double strike."                                  -- Lyse Hext

Rule 604.3: a static ability with a condition exists whenever the condition is
met and not otherwise. The condition counts spells *of a type*, so the flat
`TurnLedger.spells_cast` total the bare `spells_cast_this_turn` leaf reads is
the wrong input: it knows only how many, and would switch double strike on
after two creature spells -- a strictly stronger card, and a silent one. The
typed form, ``{"player": …, "filter": …}``, counts the ids the same cast fold
records in `TurnLedger.spells_cast_ids`, matched on each cast face's printed
characteristics with `characteristics._matches_printed`, exactly as the
effect side's leaf in `effects/values.py` matches them.

It is admissible in a static under ADR 0001 for the bare leaf's reason: the
ids list is a pipeline **input**, written only by `GameState._tally` folding
SPELL_CAST and emptied only by the cleanup step, both of which bump
`char_version`; and a printed face is no layer's output.

What each reading rests on, and each has a test class:

- **The threshold** -- one noncreature spell is not enough, two are.
- **"Noncreature"** -- creature spells are not counted, however many.
- **"You've cast"** -- an opponent's noncreature spells do not count.
- **"This turn"** -- the grant ends with the turn the spells were cast in.
- **The loader** -- the typed form loads, and a filter that would silently
  match nothing (a board-state key, a misspelled type, no filter at all) is
  refused.

`t_stsc_hexer` in `tests/data/static_typed_spells_cast.cards.json` is Lyse
Hext's double-strike line on a vanilla 2/2.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import keywords, only_oid, pass_until, static_probe

HEXER = "t_stsc_hexer"  # 2/2, double strike after two noncreature spells you cast
SORCERY = "t_sorcery"  # {R} sorcery
BOLT = "t_bolt"  # {R} instant
BEAR = "t_bear"  # {1}{G} creature


def position(builder, *, active: int = 0):
    """Player 0 controls the Hexer, frozen in a main phase of ``active``'s turn.

    Casts are written straight to the ledger with SPELL_CAST, the one funnel
    every cast path passes through, so each test says exactly what was cast by
    whom and nothing else moves the characteristics cache.
    """
    game = (
        builder(players=2)
        .battlefield(0, [HEXER])
        .battlefield(1, ["mountain"])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
        .build(advance=False)
    )
    return game, only_oid(game, HEXER, 0)


def cast(game, *card_ids: str, player: int = 0) -> None:
    for card_id in card_ids:
        game.state.emit(EventType.SPELL_CAST, player=player, card=card_id)


def double_strike(game, oid: int) -> bool:
    return "double_strike" in keywords(game, oid)


class TestTheThreshold:
    def test_nothing_cast_no_double_strike(self, builder):
        game, hexer = position(builder)
        assert not double_strike(game, hexer)

    def test_one_noncreature_spell_is_not_enough(self, builder):
        game, hexer = position(builder)
        cast(game, SORCERY)
        assert not double_strike(game, hexer)

    def test_the_second_turns_it_on(self, builder):
        """An instant and a sorcery: "noncreature" is any type but Creature."""
        game, hexer = position(builder)
        cast(game, SORCERY)
        assert not double_strike(game, hexer)
        cast(game, BOLT)
        assert double_strike(game, hexer), "the cast fold itself must invalidate the cache"

    def test_a_third_keeps_it(self, builder):
        game, hexer = position(builder)
        cast(game, SORCERY, BOLT, SORCERY)
        assert double_strike(game, hexer)


class TestOnlyNoncreatureSpellsCount:
    def test_two_creature_spells_do_not_turn_it_on(self, builder):
        """The claim the capability rests on: the flat count reaches two."""
        game, hexer = position(builder)
        cast(game, BEAR, BEAR)
        assert game.state.turn_ledger.spells_cast == {0: 2}
        assert not double_strike(game, hexer)

    def test_a_mixed_turn_counts_only_the_noncreature_half(self, builder):
        game, hexer = position(builder)
        cast(game, BEAR, SORCERY, BEAR)
        assert not double_strike(game, hexer)
        cast(game, BOLT)
        assert double_strike(game, hexer)


class TestOnlyYourSpellsCount:
    def test_an_opponents_noncreature_spells_do_not(self, builder):
        game, hexer = position(builder, active=1)
        cast(game, SORCERY, BOLT, player=1)
        assert not double_strike(game, hexer)

    def test_yours_on_their_turn_do(self, builder):
        """"This turn", not "your turn": two instants in response work."""
        game, hexer = position(builder, active=1)
        cast(game, BOLT, BOLT)
        assert double_strike(game, hexer)


class TestItEndsWithTheTurn:
    def test_the_next_turn_starts_without_it(self, builder):
        game, hexer = position(builder)
        cast(game, SORCERY, BOLT)
        assert double_strike(game, hexer)
        turn = game.state.turn
        game._advance()
        pass_until(game, lambda g: g.state.turn != turn)
        assert game.state.turn != turn
        assert not game.state.turn_ledger.spells_cast_ids
        assert not double_strike(game, hexer)


class TestTheLoader:
    def compile(self, left):
        static = {
            "effect": "grant_keyword",
            "keywords": ["double_strike"],
            "affects": {"self_only": True},
            "condition": {"cmp": ">=", "left": left, "right": {"const": 2}},
        }
        return compile_card(CardModel.model_validate(static_probe(static)))

    @pytest.mark.parametrize(
        "spec",
        [
            {"player": "you", "filter": {"not_types": ["Creature"]}},
            {"filter": {"any_types": ["Instant", "Sorcery"]}},
            {"player": "opponent", "filter": {"colors": ["R"], "types": ["Instant"]}},
        ],
    )
    def test_the_typed_form_loads(self, spec):
        self.compile({"spells_cast_this_turn": spec})

    def test_the_bare_form_still_loads(self):
        self.compile({"spells_cast_this_turn": "you"})

    @pytest.mark.parametrize(
        ("spec", "match"),
        [
            ({"player": "you", "filter": {"not_types": ["Creature"]}, "x": 1}, "unknown keys"),
            ({"player": "active_player", "filter": {"types": ["Instant"]}}, r"\.player"),
            ({"player": "you"}, r"\.filter"),
            ({"player": "you", "filter": {}}, r"\.filter"),
            ({"player": "you", "filter": {"tapped": True}}, "printed face"),
            ({"player": "you", "filter": {"controller": "you"}}, "printed face"),
            ({"player": "you", "filter": {"not_types": ["Creture"]}}, "unknown type"),
            ({"player": "you", "filter": {"supertypes": ["Legend"]}}, "unknown supertype"),
            ({"player": "you", "filter": {"mana_cost": "{1}"}}, "mana_cost|list"),
        ],
    )
    def test_a_filter_that_would_match_nothing_is_refused(self, spec, match):
        with pytest.raises(DslError, match=match):
            self.compile({"spells_cast_this_turn": spec})
