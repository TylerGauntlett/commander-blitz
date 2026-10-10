"""Investigate: a keyword action that is entirely a token.

"Whenever you cast a creature spell with mana value 3 or less, investigate."
Bygone Bishop is the shipped witness, and the parenthetical on it is the whole
specification: *(Create a Clue token. It's an artifact with "{2}, Sacrifice this
token: Draw a card.")*

So there is no `investigate` op and there should not be one. `create_token`
already names any token in the pool, `Cost` already carries mana and a
`self_only` sacrifice together (Mind Stone pays exactly that shape), and `draw`
is an op -- the only thing missing was a Clue for `create_token` to point at.
`validate_token_references` makes that a load-time failure rather than a silent
no-op, which is why the card could not be written half.

What is worth pinning, then, is not that a token appears but that it is the
*right* token, because every way of getting it wrong is invisible on screen:

- A Clue that could be cashed for free, or for one mana, is a strictly better
  card than the one printed. The cost is the card.
- A Clue that lingers after being sacrificed would let one token draw twice.
  A token that has left the battlefield ceases to exist, as a state-based
  action, and nothing about the Clue's own text says so -- the engine does.
- "Mana value 3 or less" is a boundary, and a filter that read `<` instead of
  `<=`, or dropped the creature clause, would still look like it worked.

Note the behaviour gate cannot cover any of this: nothing casts a spell after
the card under test in the verification sandbox, so Bygone Bishop's trigger
never fires there. This file is the only coverage the Clue has.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, CardType, DecisionKind

# A creature spell on each side of "mana value 3 or less", both with
# generic-only costs so the boundary under test is the mana *value* and never
# a colour the board happens not to make.
UNDER_THE_LINE = "darksteel_myr"  # {3}
OVER_THE_LINE = "h_e_r_b_i_e_scout_unit"  # {4}


def bishop(builder, *, hand=(), lands=7):
    """Bygone Bishop on the battlefield with enough mana to cast and to cash in."""
    return (
        builder(players=2)
        .battlefield(0, ["bygone_bishop"] + ["island"] * lands)
        .hand(0, list(hand))
        .library(0, ["forest"] * 20)
        .build()
    )


def resolve(game) -> None:
    """Pass priority until the stack is empty, so triggers and abilities finish."""
    for _ in range(60):
        decision = game.pending()
        if decision is None or decision.kind is not DecisionKind.PRIORITY:
            return
        if not game.state.stack:
            return
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))


def cast(game, def_id: str) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
    )
    game.apply(action)
    resolve(game)


def clues(game) -> list[int]:
    return [
        oid
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == "clue_token"
    ]


def cash_in(game, oid: int):
    """The Clue's own ability, if it is being offered at all."""
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid
        ),
        None,
    )


class TestInvestigateMakesAClue:
    def test_a_creature_spell_at_the_boundary_investigates(self, builder):
        game = bishop(builder, hand=[UNDER_THE_LINE])
        cast(game, UNDER_THE_LINE)
        assert len(clues(game)) == 1, "mana value 3 is '3 or less'"

    def test_it_is_a_real_token(self, builder):
        game = bishop(builder, hand=[UNDER_THE_LINE])
        cast(game, UNDER_THE_LINE)
        oid = clues(game)[0]
        assert game.state.objects[oid].is_token, (
            "a Clue made by create_token must be a token, or it will not cease "
            "to exist when it is sacrificed"
        )

    def test_it_is_an_artifact_and_not_a_creature(self, builder):
        game = bishop(builder, hand=[UNDER_THE_LINE])
        cast(game, UNDER_THE_LINE)
        c = chars(game.state, clues(game)[0])
        assert CardType.ARTIFACT.value in c.types
        assert CardType.CREATURE.value not in c.types, "a Clue cannot attack"
        assert "Clue" in c.subtypes


class TestTheBoundary:
    def test_one_over_the_line_does_not_investigate(self, builder):
        game = bishop(builder, hand=[OVER_THE_LINE])
        cast(game, OVER_THE_LINE)
        assert clues(game) == [], "mana value 4 is not '3 or less'"

    def test_a_noncreature_spell_does_not_investigate(self, builder):
        game = bishop(builder, hand=["divination"])
        cast(game, "divination")
        assert clues(game) == [], (
            "Divination is mana value 3 and still not a creature spell"
        )


class TestCashingItIn:
    def test_it_draws_a_card(self, builder):
        game = bishop(builder, hand=[UNDER_THE_LINE])
        cast(game, UNDER_THE_LINE)
        oid = clues(game)[0]
        before = len(game.state.players[0].hand)

        game.apply(cash_in(game, oid))
        resolve(game)

        assert len(game.state.players[0].hand) == before + 1

    def test_the_clue_ceases_to_exist(self, builder):
        game = bishop(builder, hand=[UNDER_THE_LINE])
        cast(game, UNDER_THE_LINE)
        oid = clues(game)[0]

        game.apply(cash_in(game, oid))
        resolve(game)

        assert clues(game) == [], "it was sacrificed"
        assert oid not in game.state.players[0].graveyard, (
            "a token that has left the battlefield ceases to exist; a Clue "
            "sitting in the graveyard could be brought back and cashed twice"
        )

    def test_it_costs_two_and_not_one(self, builder):
        # One land, and the Clue's ability wants {2}. `legality` must not offer
        # a cost the player cannot pay -- otherwise the mana row is a lie.
        game = bishop(builder, hand=[UNDER_THE_LINE], lands=4)
        cast(game, UNDER_THE_LINE)
        oid = clues(game)[0]
        for land in [o for o in game.state.battlefield][:]:
            obj = game.state.objects[land]
            if obj.def_id == "island":
                obj.tapped = True
        game.state.bump_chars()

        assert cash_in(game, oid) is None, "no mana, no draw"
