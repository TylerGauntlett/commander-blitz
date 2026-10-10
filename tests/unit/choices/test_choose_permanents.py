"""Tragic Arrogance — marking survivors before a mass sacrifice.

    For each player, you choose from among the permanents that player controls
    an artifact, a creature, an enchantment, and a planeswalker. Then each
    player sacrifices all other nonland permanents they control.

Two things were missing, and the op is only the first.

**Nothing could choose without acting.** Every op that writes a binding through
`as` also does something to what it picked — `sacrifice`, `exile`,
`gain_control`, `reveal`, `create_token`, `copy_permanent`, `search_zones`.
`snapshot` records without acting, but it takes `oids[0]` of its pool with no
`count` and no `chooser`, so it can be neither a choice nor four picks. There
was no way to mark the survivors *before* the sweep. Inverting the card into
"choose the ones to sacrifice" is a different choice, not a workaround: the
printed card names one survivor per type, not an all-but-one selection.

**And `count` is one flat number.** `types`/`any_types` filter a pool
uniformly, so a single choice of four over artifacts-creatures-enchantments-
planeswalkers happily keeps four creatures. That is `t_flat_tragic` below, and
it is the whole reason the binding **accumulates**: four separate per-type
choices share one name, and the one `sacrifice` that follows spares all four
with a single `exclude_binding`.

The board is deliberately symmetrical and deliberately holds *two* creatures per
player, because one is the only case where the flat and per-type readings agree.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import ActionKind, DecisionKind

TRAGIC = "t_tragic"
FLAT = "t_flat_tragic"

#: An artifact, two creatures, an enchantment and a planeswalker, per player.
BOARD = ["accorder_s_shield", "t_bear", "t_bear", "fang_of_shigeki", "t_walker"]


def board(builder, card_id: str):
    return (
        builder(players=2)
        .hand(0, [card_id, "forest"])
        .battlefield(0, ["plains"] * 5)
        .battlefield(0, BOARD)
        .battlefield(1, BOARD)
        .library(0, ["forest"] * 20)
        .build()
    )


def resolve(game, card_id: str):
    """Cast it and take the first offered choice at every prompt."""
    state = game.state
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    for _ in range(60):
        decision = game.pending()
        if decision is None:
            break
        actions = game.legal_actions()
        if not actions:
            break
        if decision.kind is DecisionKind.PRIORITY and not state.stack:
            break
        choices = [a for a in actions if a.kind is ActionKind.CHOOSE]
        game.apply(choices[0] if choices else actions[0])
    return game


def survivors(game, pid: int):
    state = game.state
    return sorted(
        state.card_of(o).id
        for o in state.battlefield_objects(pid)
        if not state.card_of(o).is_land
    )


class TestOneOfEachTypeSurvives:
    def test_the_controller_keeps_one_of_each(self, builder):
        game = resolve(board(builder, TRAGIC), TRAGIC)
        assert survivors(game, 0) == [
            "accorder_s_shield",
            "fang_of_shigeki",
            "t_bear",
            "t_walker",
        ]

    def test_and_so_does_every_other_player(self, builder):
        """"For each player" -- the loop, and the binding surviving it."""
        game = resolve(board(builder, TRAGIC), TRAGIC)
        assert survivors(game, 1) == survivors(game, 0)

    def test_the_second_creature_is_sacrificed(self, builder):
        """One creature, not two: the per-type quota is the point."""
        game = resolve(board(builder, TRAGIC), TRAGIC)
        assert survivors(game, 0).count("t_bear") == 1

    def test_the_lands_are_untouched(self, builder):
        game = resolve(board(builder, TRAGIC), TRAGIC)
        state = game.state
        lands = [
            o for o in state.battlefield_objects(0) if state.card_of(o).is_land
        ]
        assert len(lands) == 5


class TestTheFlatCountIsTheWrongCard:
    """`count: 4` over a merged pool -- what the DSL could already say."""

    def test_it_keeps_two_creatures_and_no_planeswalker(self, builder):
        game = resolve(board(builder, FLAT), FLAT)
        kept = survivors(game, 0)
        assert kept.count("t_bear") == 2
        assert "t_walker" not in kept

    def test_the_two_cards_disagree(self, builder):
        per_type = survivors(resolve(board(builder, TRAGIC), TRAGIC), 0)
        flat = survivors(resolve(board(builder, FLAT), FLAT), 0)
        assert per_type != flat


class TestTheLoaderKeepsItHonest:
    def test_choosing_without_an_as_is_refused(self):
        """It changes nothing, so a choice nobody reads is a pointless prompt."""
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.cards.schema import CardModel
        from commanderblitz.engine.errors import DslError

        card = CardModel.model_validate(
            {
                "id": "t_bad_choose",
                "name": "Test Bad Choose",
                "oracle_text": "Choose a creature.",
                "mana_cost": "{W}",
                "types": ["Sorcery"],
                "spell_effects": [
                    {
                        "op": "choose_permanents",
                        "objects": {"zone": "battlefield", "types": ["Creature"]},
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="'as'"):
            compile_card(card, source="test")
