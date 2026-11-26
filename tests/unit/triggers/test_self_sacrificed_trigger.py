""""When you sacrifice this Aura…" -- a `sacrificed` trigger about its own source.

    "Whenever enchanted creature attacks, put a +1/+1 counter on it. Then if it
    has three or more +1/+1 counters on it, sacrifice this Aura.
    When you sacrifice this Aura, search your library for up to two basic land
    cards, put them onto the battlefield tapped, then shuffle."
                                                -- Ordeal of Nylea

A sacrifice is a leaves-the-battlefield event (603.6c), and those look back in
time (603.10a): the Aura is in the graveyard when SACRIFICED goes out, and still
hears it. Every shipped `sacrificed` trigger was a battlefield observer of other
permanents, so the departed-subject walk in `triggers._candidate_abilities`
never offered the sacrificed object its own -- the Ordeal's reward could not
fire. `dies` with `source: "self"` would fire, and is wider than printed: a
destroyed or bounced Ordeal is not sacrificed.

`t_ss_ordeal` is the last line alone, on a plain enchantment, gaining 3 life.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.zones import destroy, move_object, sacrifice
from tests.conftest import only_oid, settle

ORDEAL = "t_ss_ordeal"
BEAR = "t_bear"
SWAMP = "swamp"


def position(builder):
    b = builder(players=2).battlefield(0, [ORDEAL, BEAR])
    for pid in range(2):
        b.library(pid, [SWAMP] * 20)
    game = b.active(0).step(Step.PRECOMBAT_MAIN).build()
    return game, only_oid(game, ORDEAL, 0)


def life(game) -> int:
    return game.state.players[0].life


class TestItsOwnSacrifice:
    def test_sacrificing_it_fires_the_trigger(self, builder):
        game, ordeal = position(builder)
        assert sacrifice(game.state, ordeal, by=0)
        settle(game)
        assert life(game) == 43

    def test_it_fires_once(self, builder):
        game, ordeal = position(builder)
        sacrifice(game.state, ordeal, by=0)
        settle(game)
        settle(game)
        assert life(game) == 43


class TestOtherDeparturesAreNotASacrifice:
    def test_destroyed(self, builder):
        game, ordeal = position(builder)
        destroy(game.state, ordeal)
        settle(game)
        assert life(game) == 40

    def test_bounced(self, builder):
        game, ordeal = position(builder)
        move_object(game.state, ordeal, Zone.HAND)
        settle(game)
        assert life(game) == 40

    def test_another_permanent_sacrificed(self, builder):
        game, _ = position(builder)
        sacrifice(game.state, only_oid(game, BEAR, 0), by=0)
        settle(game)
        assert life(game) == 40
