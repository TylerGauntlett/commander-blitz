"""How much the creatures of a combat-damage batch dealt to that player.

    "Whenever one or more creatures you control with trample deal combat damage
    to a player, create an X/X green Dinosaur Beast creature token with trample,
    where X is **the amount of damage those creatures dealt to that player**."
                                                    -- Quartzwood Crasher

`creatures_deal_combat_damage` carried which creatures hit which seat and not
how hard, so X had nothing to read. Each seat's hit now records every damager's
amount (`combat._fire_damage_batch`), and a `per_player` firing binds `amount`
as the sum over the creatures its filter kept: those creatures, that player.
A creature without trample that connected beside them is not "those creatures"
and adds nothing.

The filter's `keywords` reads the damagers as they deal the damage, which is
while they are on the battlefield (the batch fires inside the damage step,
before state-based actions), so a creature **granted** trample counts. Read off
the printed face, as every other filter key still is, an Elf given trample by
a lord would leave the card a narrower one than printed.

`t_cda_crasher` gains that much life, so the life total is the reading.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Step
from tests.conftest import pass_until

CRASHER = "t_cda_crasher"
TRAMPLER = "t_cda_trampler"  # 3/3 trample
PLAIN = "t_cda_plain"  # 2/2
ELF = "t_cda_elf"  # 4/4 Elf
BANNER = "t_cda_banner"  # Elves you control have trample


def life_gained(builder, attackers: list[str], *, extra=()) -> int:
    game = (
        builder(players=2)
        .battlefield(0, [CRASHER, *extra, *attackers])
        .library(0, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    for obj in game.state.battlefield_objects(0):
        obj.entered_turn = 0
    before = game.state.players[0].life
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    for obj in [o for o in game.state.battlefield_objects(0) if o.def_id in attackers]:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER and a.source == obj.oid
            )
        )
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    pass_until(game, lambda g: (g.state.turn, g.state.step) >= mark)
    return game.state.players[0].life - before


class TestThatAmount:
    def test_one_trampler_is_its_damage(self, builder):
        assert life_gained(builder, [TRAMPLER]) == 3

    def test_two_tramplers_are_summed(self, builder):
        assert life_gained(builder, [TRAMPLER, TRAMPLER]) == 6

    def test_a_creature_without_trample_adds_nothing(self, builder):
        assert life_gained(builder, [TRAMPLER, PLAIN]) == 3

    def test_no_trampler_connecting_is_no_trigger(self, builder):
        assert life_gained(builder, [PLAIN]) == 0


class TestGrantedTrampleCounts:
    def test_an_elf_given_trample_is_one_of_those_creatures(self, builder):
        assert life_gained(builder, [ELF], extra=[BANNER]) == 4

    def test_without_the_grant_it_is_not(self, builder):
        assert life_gained(builder, [ELF]) == 0
