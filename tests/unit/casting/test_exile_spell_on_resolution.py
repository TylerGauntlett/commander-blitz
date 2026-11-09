""""When you spend this mana to cast an instant or sorcery spell with mana value
3 or less, you may exile that spell instead of putting it into its owner's
graveyard as it resolves."                            -- Forger's Foundry

The Foundry's second ability casts "from among cards exiled with this
artifact", so the exile has to leave a link (`exiled_by`, 607.2a) and not just a
card in exile. It is `grant_plot`'s rider with a link where plot leaves a
permission: the spell's object is marked while it is on the stack, and
`_place_after_resolution` exiles it and links it **after** the move, because
`reset_permanent_state` runs on the way and wipes anything set first.

The spell is named by the spent-mana trigger's ``subject`` binding, an object
id, which is why the op reaches past `_spell_named_by`'s stack id.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import _default_answer, settle_to_priority

FOUNDRY = "t_foundry"  # {T}: Add {U}, and the rider
OPT = "opt"  # {U} instant


def position(builder, source: str):
    return (
        builder(players=2)
        .battlefield(0, [source])
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        # Two Opts: the second keeps the seat from auto-passing the turn away.
        .hand(0, [OPT, OPT])
        .build()
    )


def cast_opt(game, *, accept: bool) -> int:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == OPT
    )
    oid = action.source
    game.apply(action)
    for _ in range(100):
        if not game.state.stack and not game.state.pending_triggers:
            break
        decision = game.pending()
        if decision.kind is DecisionKind.MAY and decision.player == 0:
            kind = ActionKind.YES if accept else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is kind))
        else:
            game.apply(_default_answer(game, decision))
    settle_to_priority(game)
    return oid


def foundry(game) -> int:
    return next(o for o in game.state.battlefield if game.state.objects[o].def_id == FOUNDRY)


class TestTheSpellIsExiledWithTheFoundry:
    def test_it_goes_to_exile(self, builder):
        game = position(builder, FOUNDRY)
        oid = cast_opt(game, accept=True)

        assert game.state.objects[oid].zone is Zone.EXILE

    def test_it_still_resolves(self, builder):
        """"as it resolves" -- Opt draws its card on the way."""
        game = position(builder, FOUNDRY)
        cast_opt(game, accept=True)

        assert len(game.state.players[0].hand) == 2

    def test_the_exile_is_linked_to_the_foundry(self, builder):
        """What "cards exiled with this artifact" reads."""
        game = position(builder, FOUNDRY)
        oid = cast_opt(game, accept=True)

        assert game.state.objects[oid].exiled_by == foundry(game)
        assert oid in game.state.objects[foundry(game)].exiled_cards


class TestOnlyWhenItSays:
    def test_declining_bins_it(self, builder):
        """"you **may** exile"."""
        game = position(builder, FOUNDRY)
        oid = cast_opt(game, accept=False)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_other_mana_bins_it(self, builder):
        """The control: an Island's blue carries no rider."""
        game = position(builder, "island")
        oid = cast_opt(game, accept=True)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert game.state.objects[oid].exiled_by is None
