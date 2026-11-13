"""`ungoad`: "each creature you control is no longer goaded" (701.38).

    Serene Sleuth -- "At the beginning of combat on your turn, investigate for
    each goaded creature you control. Then each creature you control is no
    longer goaded."

A goad is two "if able" rules -- attack each combat, and attack a player other
than the goader -- and "no longer goaded" ends both, for every goader and on
every clock. Without it the Sleuth is a Clue engine that leaves its creatures
compelled: they still have "Done attacking" withheld and still may not swing at
the player who goaded them, which is the whole cost the card exists to remove.

Two shapes of goad, two answers:

- **The marks end.** The `goad` op writes the goader into
  `GameObject.goaded_by`, and "for the rest of the game" into
  `goaded_permanently_by` too (Dack Fayden). The sentence names neither goader
  nor clock, so every mark goes, permanent ones included.
- **A `goaded` static stays.** The Impetus Auras' "enchanted creature is
  goaded" is a continuous effect of a static ability, which applies at every
  moment its text matches (611.3a). A one-shot "no longer goaded" ends the goads
  resolving effects created; the static's goad holds again the instant the op is
  done, for as long as the Aura enchants the creature.

The claims: every goader's mark ends, the permanent mark with them; the
compulsion and the target restriction both lift; the creature can be goaded
again afterwards; creatures outside ``objects`` keep theirs; the static goad
survives; the loader refuses a missing ``objects`` and a borrowed ``player`` or
``duration``; and Serene Sleuth's trigger counts the goaded creatures first and
ends their goads second.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import goaders
from commanderblitz.engine.temp_effects import goad_creature
from commanderblitz.engine.zones import destroy
from tests.conftest import oids_of, only_oid
from tests.unit.combat.test_goad import (
    can_finish,
    defenders_offered,
    position,
    to_declare_attackers,
)
from tests.unit.combat.test_static_goad import IMPETUS, enchanted

BEAR = "t_bear"

UNGOAD_THEIRS = {
    "op": "ungoad",
    "objects": {"zone": "battlefield", "controller": "you", "types": ["Creature"]},
}


def ungoad(game, controller: int = 1, spec=UNGOAD_THEIRS) -> None:
    """Resolve ``spec`` for ``controller`` -- by default player 1, whose creatures are goaded."""
    ctx = EffectContext(state=game.state, controller=controller)
    for _ in execute(ctx, [spec]):  # pragma: no cover - the loop body is the failure
        raise AssertionError("ungoad asked a decision; it takes none")


class TestEveryGoadEnds:
    def test_the_goaders_mark_ends(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        assert goaders(game.state, bear) == {0}

        ungoad(game)

        assert goaders(game.state, bear) == set()
        assert game.state.objects[bear].goaded_by == set()

    def test_two_goaders_both_end(self, builder):
        """No goader is named, so none is spared -- unlike `clear_goad`'s untap step."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        goad_creature(game.state, bear, 2)

        ungoad(game)

        assert goaders(game.state, bear) == set()

    def test_a_goad_for_the_rest_of_the_game_ends_too(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0, permanent=True)

        ungoad(game)

        obj = game.state.objects[bear]
        assert obj.goaded_by == set() and obj.goaded_permanently_by == set()

    def test_only_the_named_creatures(self, builder):
        game = position(builder, mine=(BEAR,))
        theirs = only_oid(game, BEAR, 1)
        mine = only_oid(game, BEAR, 0)
        goad_creature(game.state, theirs, 0)
        goad_creature(game.state, mine, 1)

        ungoad(game)

        assert goaders(game.state, theirs) == set()
        assert goaders(game.state, mine) == {1}, "player 0's creature is not player 1's"

    def test_it_can_be_goaded_again(self, builder):
        """It ends what is there and forbids nothing."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        ungoad(game)

        assert goad_creature(game.state, bear, 0)
        assert goaders(game.state, bear) == {0}


class TestBothHalvesLift:
    def test_the_compulsion_lifts(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        ungoad(game)

        assert not combat_mod.attack_required(game.state, bear)
        to_declare_attackers(game)
        assert can_finish(game), '"Done attacking" is offered again'

    def test_the_goader_may_be_attacked_again(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [2], "goaded: away from player 0"

        ungoad(game)

        assert defenders_offered(game, bear) == [0, 2]


class TestAStaticGoadStays:
    def test_the_impetus_goad_survives(self, builder):
        """611.3a: the static applies again the moment the op is done."""
        game, bear = enchanted(builder)
        goad_creature(game.state, bear, 2)
        assert goaders(game.state, bear) == {0, 2}

        ungoad(game)

        assert game.state.objects[bear].goaded_by == set(), "the mark is gone"
        assert goaders(game.state, bear) == {0}, "the Aura's goad is not a mark"
        assert combat_mod.attack_required(game.state, bear)

    def test_the_static_goad_ends_when_the_aura_does(self, builder):
        """What does end it: the static no longer applying, not the op."""
        game, bear = enchanted(builder)
        ungoad(game)
        destroy(game.state, only_oid(game, IMPETUS, 0))
        assert goaders(game.state, bear) == set()


class TestTheLoader:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_ungoad_probe",
                "name": "Ungoad Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_the_shape_loads(self):
        compile_card(self._card(UNGOAD_THEIRS))

    def test_objects_is_required(self):
        with pytest.raises(DslError, match="ungoad needs 'objects'"):
            compile_card(self._card({"op": "ungoad"}))

    @pytest.mark.parametrize(("key", "value"), [("player", "opponent"), ("duration", "permanent")])
    def test_no_goader_and_no_clock(self, key, value):
        with pytest.raises(DslError, match=f"ungoad takes no '{key}'"):
            compile_card(self._card({**UNGOAD_THEIRS, key: value}))


class TestThePrintedCard:
    def test_serene_sleuth_investigates_per_goaded_creature_then_ungoads(self, builder):
        """Counted first, ended second: "then" orders the two sentences."""
        game = position(
            builder, theirs=("serene_sleuth", BEAR, BEAR, "t_sg_cub"), players=3
        )
        sleuth = only_oid(game, "serene_sleuth", 1)
        bears = oids_of(game, BEAR, 1)
        for oid in bears:
            goad_creature(game.state, oid, 0)
        clues = len(oids_of(game, "clue_token", 1))

        to_declare_attackers(game)

        assert len(oids_of(game, "clue_token", 1)) == clues + 2, "two goaded creatures"
        assert all(goaders(game.state, oid) == set() for oid in bears)
        assert goaders(game.state, sleuth) == set()
        assert can_finish(game)
