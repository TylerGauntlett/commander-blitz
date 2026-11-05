"""'Can't be blocked by creatures your opponents control' -- `unblockable` with
``by_opponents``, keyed on the player who granted it.

Rule 509.1b: a blocker may be declared only if no restriction forbids it. Rikku,
Resourceful Guardian's first line forbids some blockers of the creature it
marks: those controlled by an opponent *of Rikku's controller*. Two near misses
would load clean and be a different card.

- Plain `unblockable` refuses every blocker. On a creature you control that is
  the same answer, since every blocker it meets is an opponent's -- but Rikku
  also marks an opponent's creature you put a counter on, and plain
  `unblockable` would stop *your* creatures blocking it when it attacks you, a
  strictly worse card for you and better for them.
- ``except_blockers`` with a ``controller`` key is refused by the loader, and
  would be wrong anyway: a static filter's ``controller`` is read relative to
  the attacker, and an opponent's attacker has several opponents of its own.

What is pinned below:

1. On your own attacker it refuses every blocker, as the plain op does, and
   asked with no blocker it is total evasion.
2. On an opponent's creature, the granting player's blockers are exempt and
   every other player's are refused; asked with no blocker it is *not* total
   evasion.
3. The primitive refuses an entry with no granting player.
4. It wears off at cleanup.
5. Rikku's own trigger records it on the creature you put counters on, an
   opponent's included, and not on one an opponent put counters on.
6. The loader accepts ``true`` and refuses anything else.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters
from commanderblitz.engine.temp_effects import make_unblockable
from tests.conftest import activations, only_oid, pass_until, settle

BEAR = "t_bear"
RIKKU = "rikku_resourceful_guardian"


def position(builder):
    """Three seats, a bear each; player 0 is the granting player."""
    b = builder(players=3)
    for pid in range(3):
        b.battlefield(pid, [BEAR])
    return b.active(0).step(Step.PRECOMBAT_MAIN).build()


class TestOnYourOwnCreature:
    def test_every_opponent_is_refused(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=0, opponents_only=True)
        for pid in (1, 2):
            assert combat_mod.unblockable(game.state, mine, only_oid(game, BEAR, pid))
        assert combat_mod.unblockable(game.state, mine)


class TestOnAnOpponentsCreature:
    def test_your_blockers_are_exempt_and_the_others_are_not(self, builder):
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        make_unblockable(game.state, [theirs], "this_turn", player=0, opponents_only=True)
        assert not combat_mod.unblockable(game.state, theirs, only_oid(game, BEAR, 0))
        assert combat_mod.unblockable(game.state, theirs, only_oid(game, BEAR, 2))

    def test_asked_without_a_blocker_it_is_blockable(self, builder):
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        make_unblockable(game.state, [theirs], "this_turn", player=0, opponents_only=True)
        assert not combat_mod.unblockable(game.state, theirs)

    def test_the_plain_op_is_the_contrast(self, builder):
        """Without the flag, your own bear could not block it either."""
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        make_unblockable(game.state, [theirs], "this_turn", player=0)
        assert combat_mod.unblockable(game.state, theirs, only_oid(game, BEAR, 0))


class TestThePrimitive:
    def test_no_granting_player_records_nothing(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        assert not make_unblockable(game.state, [mine], "this_turn", opponents_only=True)
        assert game.state.unblockables == []

    def test_it_wears_off_at_cleanup(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=0, opponents_only=True)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.unblockables == []


class TestRikku:
    def board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [RIKKU, BEAR, "island", "island"])
            .battlefield(1, [BEAR])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        return game

    def test_your_counter_on_their_creature_marks_it_for_your_opponents_only(self, builder):
        game = self.board(builder)
        rikku, theirs = only_oid(game, RIKKU, 0), only_oid(game, BEAR, 1)
        add_counters(game.state, theirs, "+1/+1", 1, source=rikku)
        settle(game)
        [entry] = game.state.unblockables
        assert entry.objects == (theirs,)
        assert entry.opponents_only and entry.player == 0
        assert not combat_mod.unblockable(game.state, theirs, only_oid(game, BEAR, 0))

    def test_stealing_a_counter_marks_the_creature_it_lands_on(self, builder):
        """Steal moves the counter onto your creature, which puts it there (122.5)."""
        game = self.board(builder)
        rikku, mine = only_oid(game, RIKKU, 0), only_oid(game, BEAR, 0)
        theirs = only_oid(game, BEAR, 1)
        game.state.objects[theirs].add_counter("+1/+1", 1)
        [steal] = [a for a in activations(game, rikku) if mine in {t.id for t in a.targets}]
        game.apply(steal)
        settle(game)
        assert game.state.objects[mine].counters.get("+1/+1") == 1
        assert combat_mod.unblockable(game.state, mine, theirs)
        assert combat_mod.unblockable(game.state, mine)

    def test_an_opponents_counter_does_not_trigger(self, builder):
        game = self.board(builder)
        mine = only_oid(game, BEAR, 0)
        add_counters(game.state, mine, "+1/+1", 1, by=1)
        settle(game)
        assert game.state.unblockables == []


def probe(flag) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{U}",
                "types": ["Sorcery"],
                "spell_effects": [
                    {
                        "op": "unblockable",
                        "objects": {"types": ["Creature"]},
                        "duration": "this_turn",
                        "by_opponents": flag,
                    }
                ],
            }
        )
    )


class TestTheLoaderGuardsIt:
    def test_true_compiles(self):
        probe(True)

    @pytest.mark.parametrize("flag", [False, "yes", 1])
    def test_anything_else_is_refused(self, flag):
        with pytest.raises(DslError, match="by_opponents"):
            probe(flag)
