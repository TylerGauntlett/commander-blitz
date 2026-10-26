""""Destroy all creatures that **aren't** of the chosen type."

Kindred Judgment is the witness. `{"chosen_type_of": "self"}` was a read on
`subtypes` alone -- "is that object of the chosen type" -- and `not_subtypes`
compared its entries as literal names. The same entry under `not_subtypes`
therefore matched no subtype at all, so "aren't of the chosen type" read
"every creature", and the spell killed the creatures it exists to spare.

Rule 205.3m makes a creature type a subtype like any other, so the
complement is the same substitution with the test turned over: resolved
wherever the filter is matched (`characteristics.resolve_chosen_subtypes`),
against the object that made the choice -- here the spell itself, which chose
as it resolved.

Two claims are pinned beside the happy path:

- **Both sides of the table are swept and both are spared.** The filter
  carries ``controller: any``; a filter that quietly kept only the caster's
  creatures, or only the opponent's, would look right on a one-sided board.
- **No choice made, nothing matched.** The failure an unresolved negation
  has is the opposite of the one `subtypes` has: dropping the entry makes the
  filter "every creature". The sentinel `subtypes` already uses closes it.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import resolve_chosen_subtypes
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.objects import GameObject

JUDGMENT = "kindred_judgment"
BEAR = "t_bear"  # Bear
FLIER = "t_flier"  # Bird


def cast_judgment(builder, type_name: str):
    """Player 0 casts Kindred Judgment over a Bear and a Bird on each side."""
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 7 + [BEAR, FLIER])
        .battlefield(1, [BEAR, FLIER])
        .hand(0, [JUDGMENT])
        .library(0, ["plains"] * 10)
        .active(0)
        .max_turns(1)
        .build()
    )
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == JUDGMENT
        )
    )
    for _ in range(40):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.CHOOSE_MODE:
            labels = [o.label for o in decision.options]
            index = labels.index(type_name)
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
            continue
        if decision.kind is DecisionKind.PRIORITY and game.state.stack:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
            continue
        break
    return game


def creatures(game, pid: int) -> list[str]:
    return sorted(
        game.state.objects[o].def_id
        for o in game.state.battlefield
        if game.state.objects[o].controller == pid
        and game.state.objects[o].def_id in (BEAR, FLIER)
    )


class TestTheSweep:
    def test_creatures_of_the_chosen_type_survive(self, builder):
        game = cast_judgment(builder, "Bear")
        assert creatures(game, 0) == [BEAR]
        assert creatures(game, 1) == [BEAR], "controller: any spares the opponent's too"

    def test_every_other_creature_is_destroyed(self, builder):
        game = cast_judgment(builder, "Bird")
        assert creatures(game, 0) == [FLIER]
        assert creatures(game, 1) == [FLIER]

    def test_a_type_nobody_has_destroys_them_all(self, builder):
        game = cast_judgment(builder, "Dragon")
        assert creatures(game, 0) == []
        assert creatures(game, 1) == []

    def test_lands_are_not_creatures_and_stay(self, builder):
        game = cast_judgment(builder, "Dragon")
        plains = [o for o in game.state.battlefield if game.state.objects[o].def_id == "plains"]
        assert len(plains) == 7


class TestTheSubstitution:
    FILTER = {"types": ["Creature"], "not_subtypes": [{"chosen_type_of": "self"}]}

    def test_the_choice_becomes_a_literal_name(self):
        source = GameObject(oid=1, def_id=JUDGMENT, owner=0, controller=0, zone=Zone.STACK)
        source.chosen_type = "Elf"
        resolved = resolve_chosen_subtypes(self.FILTER, source)
        assert resolved["not_subtypes"] == ["Elf"]
        assert "subtypes" not in resolved

    def test_no_choice_matches_nothing_rather_than_everything(self):
        source = GameObject(oid=1, def_id=JUDGMENT, owner=0, controller=0, zone=Zone.STACK)
        resolved = resolve_chosen_subtypes(self.FILTER, source)
        assert resolved["subtypes"] == ["\0none"], (
            "dropping the entry would make 'aren't of the chosen type' every creature"
        )

    def test_a_literal_negation_is_left_alone(self):
        literal = {"types": ["Creature"], "not_subtypes": ["Human"]}
        assert resolve_chosen_subtypes(literal, None) is literal
