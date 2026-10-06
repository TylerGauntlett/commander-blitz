"""Disturb — a graveyard cast that arrives on the other face.

    "Disturb {1}{W} (You may cast this card transformed from your graveyard for
    its disturb cost.)"

Both halves shipped years apart and had never met. `graveyard_cost` is the cast,
generalised for flashback, jump-start and escape; `transformed` is the face,
built for Bloodline Keeper. Disturb is one word joining them —
`graveyard_cast_transformed` — and everything interesting is *when* the face is
turned.

**At cast time, not on resolution.** The card is the back face from the moment
it goes on the stack, so its name, types and effects are the back face's. A
spell that showed its front face on the stack and its back face on the
battlefield would be two different cards to everyone watching, and for the
disturb cards that matters most — a Creature front and an Enchantment back —
even `is_permanent` would be answered off the wrong face.

**And again after the move.** `reset_permanent_state` clears `transformed` on
the way onto the battlefield, which is rule 712.13a ("enters front face up") and
right for every permanent except this one. So `cast_transformed` is kept beside
the other `cast_*` flags and re-applied, exactly as `cast_x` outlives its spell.

*Divergence*: legality enumerates the cast's targets off the **front** face,
because it decides what is castable before anything is turned over. No disturb
card in the pool targets, and the front and back faces of one would have to
differ in what they point at for it to show.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from tests.conftest import pass_until

PLAINS = "plains"
FRONT = "t_disturb_front"     # {2}{W} 2/2 Spirit, disturb {1}{W}
BACK = "t_disturb_back"       # the Enchantment it comes back as
BEAR = "t_bear"


def position(builder, lands: int = 3):
    game = (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands)
        .battlefield(0, [BEAR])
        .graveyard(0, [FRONT])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build()
    )
    spirit = game.state.players[0].graveyard[0]
    return game, spirit


def disturb_line(game, spirit: int):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.source == spirit
        ),
        None,
    )


class TestTheCast:
    def test_it_is_offered_from_the_graveyard(self, builder):
        game, spirit = position(builder)
        assert disturb_line(game, spirit) is not None

    def test_it_is_not_offered_without_the_mana(self, builder):
        game, spirit = position(builder, lands=1)
        assert disturb_line(game, spirit) is None


class TestTheFace:
    def test_the_spell_is_cast_as_the_back_face(self, builder):
        """The `spell_cast` event names the card, and it must be the back one.

        Asserted off the log rather than off the stack because with nothing to
        respond with the spell resolves inside the same `apply` -- and the claim
        is about what was *cast*, which the log is the record of.
        """
        game, spirit = position(builder)
        events = game.apply(disturb_line(game, spirit))

        cast = next(e for e in events if e.type == "spell_cast")
        assert cast.data["card"] == BACK, "name, types and effects are the back face's"

    def test_it_arrives_on_the_battlefield_transformed(self, builder):
        game, spirit = position(builder)
        game.apply(disturb_line(game, spirit))
        pass_until(game, lambda g: not g.state.stack)

        obj = game.state.objects[spirit]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.transformed, "reset_permanent_state cleared it; disturb re-applies it"
        assert game.state.card_of(obj).id == BACK

    def test_the_back_face_ability_works(self, builder):
        """The whole point: an Enchantment back, not a 2/2 Spirit."""
        game, spirit = position(builder)
        bear = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
        assert chars(game.state, bear).power == 2

        game.apply(disturb_line(game, spirit))
        pass_until(game, lambda g: not g.state.stack)

        assert chars(game.state, bear).power == 3, "the anthem on the back face"

    def test_it_is_not_a_creature(self, builder):
        game, spirit = position(builder)
        game.apply(disturb_line(game, spirit))
        pass_until(game, lambda g: not g.state.stack)

        assert "Creature" not in chars(game.state, spirit).types
        assert "Enchantment" in chars(game.state, spirit).types


class TestTheLoaderGuards:
    def _card(self, **extra) -> CardModel:
        base = {
            "id": "t_disturb_probe",
            "name": "Disturb Probe",
            "mana_cost": "{2}{W}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "graveyard_cast_transformed": True,
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def test_both_halves_together_load(self):
        compile_card(
            self._card(back_face="t_disturb_back", graveyard_cost={"mana": "{1}{W}"})
        )

    def test_no_graveyard_cost_is_refused(self):
        """There is no cast for it to transform."""
        with pytest.raises(DslError, match="needs a 'graveyard_cost'"):
            compile_card(self._card(back_face="t_disturb_back"))

    def test_no_back_face_is_refused(self):
        """Flashback wearing the wrong word: it would arrive as its front face."""
        with pytest.raises(DslError, match="needs a 'back_face'"):
            compile_card(self._card(graveyard_cost={"mana": "{1}{W}"}))
