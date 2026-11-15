""""Loses all abilities … **until end of turn**" -- the timed loss, and its return.

Warkite Marauder: "Whenever this creature attacks, target creature defending
player controls loses all abilities and has base power and toughness 0/1 until
end of turn." The `lose_all_abilities` op was permanent only (The Irencrag), and
the permanent op *deletes* every ability grant older than itself
(`_drop_earlier_grants`) because they are gone for good. A timed loss cannot:
riot's haste or a one-shot "gains flying for as long as …" must be back when it
wears off, and a version that deleted them would be a permanent strip of the
grants dressed as a temporary one.

So the timed loss is a `TempEffect(kind="lose_all_abilities")` whose timestamp
is the resolution's start, and the readers -- `chars`, `abilities_of`,
`protection_from` -- read past every grant older than it while it stands
(613.7). A grant made after it survives. Cleanup (514.2) ends it, and with
``until_your_next_turn`` that seat's next untap step does.

The witness is Warkite Marauder; the targets here are `t_flier` (printed
flying) and `t_anthem` (a printed static anthem, which stops applying).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import abilities_of, chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import (
    clear_until_eot,
    clear_until_next_turn,
    grant_keyword,
)
from tests.conftest import only_oid

FLIER = "t_flier"  # 2/2 flying
BEAR = "t_bear"  # 2/2
ANTHEM = "t_anthem"  # "Creatures you control get +1/+1."


def strip(game, name: str, duration: str = "until_end_of_turn") -> None:
    """Resolve the Marauder's effect list against the one permanent named ``name``."""
    target = {"zone": "battlefield", "controller": "any", "name": name, "count": "all"}
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    effects = [
        {"op": "lose_all_abilities", "objects": target, "duration": duration},
        {"op": "animate", "power": {"const": 0}, "toughness": {"const": 1},
         "objects": target, "duration": duration},
    ]
    for _ in execute(ctx, effects):
        raise AssertionError("the strip asks nothing")


def board(builder):
    game = builder(players=2).battlefield(1, [FLIER, BEAR, ANTHEM]).build()
    return game, only_oid(game, FLIER, 1), only_oid(game, BEAR, 1), only_oid(game, ANTHEM, 1)


class TestUntilEndOfTurn:
    def test_the_printed_keyword_goes(self, builder):
        game, flier, _, _ = board(builder)
        strip(game, "Test Flier")
        assert "flying" not in chars(game.state, flier).keywords

    def test_the_base_size_is_zero_one(self, builder):
        """The anthem still pumps the 0/1: layer 7c after the 7b base."""
        game, flier, _, _ = board(builder)
        strip(game, "Test Flier")
        c = chars(game.state, flier)
        assert (c.power, c.toughness) == (1, 2)

    def test_a_stripped_static_stops_applying(self, builder):
        game, _, bear, _ = board(builder)
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (3, 3)
        strip(game, "Test Anthem")
        assert abilities_of(game.state, only_oid(game, ANTHEM, 1)) == ()
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (2, 2)

    def test_everything_is_back_after_cleanup(self, builder):
        game, flier, bear, anthem = board(builder)
        strip(game, "Test Flier")
        strip(game, "Test Anthem")
        clear_until_eot(game.state)
        assert "flying" in chars(game.state, flier).keywords
        assert abilities_of(game.state, anthem)
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (3, 3)
        assert not game.state.objects[flier].lost_all_abilities


class TestGrantsByTimestamp:
    def test_a_lasting_grant_made_earlier_is_hidden_then_returns(self, builder):
        """The case a destructive strip gets wrong: the grant outlives the turn."""
        game, _, bear, _ = board(builder)
        grant_keyword(game.state, bear, "haste", permanent=True)
        strip(game, "Test Bear")
        assert "haste" not in chars(game.state, bear).keywords
        clear_until_eot(game.state)
        assert "haste" in chars(game.state, bear).keywords

    def test_a_grant_made_later_survives(self, builder):
        game, _, bear, _ = board(builder)
        strip(game, "Test Bear")
        grant_keyword(game.state, bear, "trample")
        assert "trample" in chars(game.state, bear).keywords

    def test_an_earlier_timed_grant_is_hidden(self, builder):
        game, _, bear, _ = board(builder)
        grant_keyword(game.state, bear, "trample")
        strip(game, "Test Bear")
        assert "trample" not in chars(game.state, bear).keywords


class TestTheOtherClock:
    def test_until_your_next_turn_outlasts_cleanup(self, builder):
        game, flier, _, _ = board(builder)
        strip(game, "Test Flier", duration="until_your_next_turn")
        clear_until_eot(game.state)
        assert "flying" not in chars(game.state, flier).keywords
        clear_until_next_turn(game.state, 0)
        assert "flying" in chars(game.state, flier).keywords


class TestThePermanentOpIsUnchanged:
    def test_no_duration_never_wears_off(self, builder):
        game, flier, _, _ = board(builder)
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        target = {"zone": "battlefield", "controller": "any", "name": "Test Flier", "count": "all"}
        list(execute(ctx, [{"op": "lose_all_abilities", "objects": target}]))
        clear_until_eot(game.state)
        assert "flying" not in chars(game.state, flier).keywords


class TestLoading:
    def _card(self, duration):
        return CardModel.model_validate({
            "id": "x", "name": "X", "oracle_text": "X.", "mana_cost": "{1}",
            "types": ["Sorcery"],
            "spell_effects": [{"op": "lose_all_abilities", "duration": duration,
                               "objects": {"zone": "battlefield", "count": "all"}}],
        })

    def test_a_misspelt_clock_is_refused(self):
        with pytest.raises(DslError, match="unknown lose_all_abilities duration"):
            compile_card(self._card("until_eot"))

    def test_the_timed_clock_loads(self):
        compile_card(self._card("until_end_of_turn"))
