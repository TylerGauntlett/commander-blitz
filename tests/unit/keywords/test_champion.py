"""Champion — the O-Ring family, wearing a different word.

    "Champion an Elf (When this creature enters, sacrifice it unless you exile
    another Elf you control. When this creature leaves the battlefield, that
    card returns to the battlefield.)"

The census filed this as blocked: "exile-and-return tied to the championing
permanent leaving". That is exactly what `exile` with `until_leaves` does, and
it has shipped since Oblivion Ring — the link is written on the **exiled card**
naming the permanent that exiled it, precisely so the exiler can be the thing
that goes away.

Everything else is vocabulary already in the pool: an `exists` guard, a `may`
with an `else` that sacrifices, and a `leaves_battlefield` trigger reading the
link back with `{"exiled_with": "self"}`.

Two things this pins that would otherwise be silent:

- **The `exists` guard is not bookkeeping.** Without it the "may" can be
  accepted with no other Elf to exile, and a champion creature that costs
  nothing is a strictly better card than the one printed — the same failure the
  Karoo lands' guard exists to refuse.
- **The championed card comes back under its owner's control**, and it comes
  back on *any* way of leaving, not only dying. Blinking a champion creature
  returns what it was holding, which is the interaction the whole mechanic is
  played for.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Zone
from tests.conftest import action_for_card, find_action, oids_of, only_oid, pass_until

FOREST = "forest"
CHAMPION = "t_champion"     # {2}{G} 4/4, champion an Elf
ELF = "t_elf"               # a plain 1/1 Elf, so the two are told apart by id
BEAR = "t_bear"


def position(builder, others: list[str]):
    return (
        builder(players=2)
        .battlefield(0, [FOREST] * 4)
        .battlefield(0, others)
        .hand(0, [CHAMPION])
        .library(0, [FOREST] * 20)
        .library(1, [FOREST] * 20)
        .build()
    )


def cast_champion(game):
    game.apply(action_for_card(game, ActionKind.CAST, CHAMPION))


class TestWithNothingToChampion:
    def test_it_sacrifices_itself(self, builder):
        """The `exists` guard: no other Elf, so the "may" is never offered."""
        game = position(builder, [BEAR])
        cast_champion(game)
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        assert not oids_of(game, CHAMPION), "it went straight to the graveyard"


class TestWithAnElfToChampion:
    def _play(self, builder, *, accept: bool):
        game = position(builder, [ELF])
        elf = only_oid(game, ELF)
        cast_champion(game)
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.kind.value == "may"
        )
        game.apply(
            find_action(game, ActionKind.YES if accept else ActionKind.NO)
        )
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)
        return game, elf

    def test_accepting_exiles_the_elf(self, builder):
        game, elf = self._play(builder, accept=True)

        assert game.state.objects[elf].zone is Zone.EXILE
        assert len(oids_of(game, CHAMPION)) == 1, "the new one stayed"

    def test_declining_sacrifices_the_new_creature(self, builder):
        game, elf = self._play(builder, accept=False)

        assert game.state.objects[elf].zone is Zone.BATTLEFIELD
        assert not oids_of(game, CHAMPION), "the champion sacrificed itself"

    def test_the_elf_comes_back_when_the_champion_leaves(self, builder):
        from automtg.engine.zones import destroy

        game, elf = self._play(builder, accept=True)
        newcomer = only_oid(game, CHAMPION)

        destroy(game.state, newcomer)
        pass_until(
            game, lambda g: game.state.objects[elf].zone is Zone.BATTLEFIELD
        )

        assert game.state.objects[elf].zone is Zone.BATTLEFIELD
        assert game.state.objects[elf].controller == 0
