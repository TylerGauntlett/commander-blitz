"""The four predefined artifact tokens, each proved to do what it prints.

A token definition never goes through the card-authoring gates. `verify.py`
casts a card and reads the board, and a token is not cast -- it is created by
somebody else's effect -- so gate 4 and gate 5 cannot reach one. `fidelity.py`
skips them explicitly too (`if card.is_token`), because a token has no printing
to be measured against.

That leaves these with exactly the coverage written here, which matters more
than usual: every one of them is an activated ability, and an activated ability
that silently does nothing is the failure the whole pipeline exists to prevent.
Clue and Treasure were already in the pool; Food, Junk, Lander and Map arrived
for the Fallout and Bloomburrow removal suites, which hand a token to the
*opponent* as the cost of killing something -- so a Lander that fetched nothing
would quietly make Emergency Eject a strictly better card than the printed one.
"""

from __future__ import annotations

from commanderblitz.engine.enums import COLORLESS, ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.mana import SYMBOL_INDEX
from commanderblitz.engine.primitives import create_token
from tests.conftest import _default_answer, oids_of, pass_until

BEAR = "t_bear"


def board(builder, token: str, *, library=("forest",) * 10):
    """A token on your battlefield, with lands enough to pay for anything."""
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 6 + ["island"] * 2)
        .battlefield(1, [BEAR])
        .library(0, list(library))
        .build()
    )
    create_token(game.state, token, 0, 1)
    your_main(game)
    return game, oids_of(game, token)[0]


def your_main(game):
    """Hand priority to player 0 in their own main phase.

    `GameBuilder.build` auto-passes forward until somebody has a real decision,
    and an empty board gives nobody one -- so it lands on the *opponent's* turn.
    A token created after that is on the battlefield but its controller never
    gets priority to use it. Passing round to player 0's main phase is the
    public way there, and it untaps them on the way.
    """
    pass_until(
        game,
        lambda g: g.state.active_player == 0 and g.state.step is Step.PRECOMBAT_MAIN,
    )


def activate(game, oid: int):
    """Activate the token's only ability and resolve it, taking every choice.

    `_default_answer` is the *most passive* legal answer, which for a search is
    "find nothing" -- so it would have proved a Lander that fetches no land.
    Preferring `CHOOSE` and `YES` is the same rule the authoring verifier's
    auto-answer table follows, and for the same reason: an optional effect
    nobody accepts demonstrates nothing.
    """
    action = next(
        a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
    )
    game.apply(action)
    for _ in range(200):
        decision = game.pending()
        if decision is None or game.over:
            return
        if not game.state.stack and decision.kind is DecisionKind.PRIORITY:
            return
        actions = game.legal_actions()
        take = next(
            (a for a in actions if a.kind in (ActionKind.CHOOSE, ActionKind.YES)),
            None,
        )
        game.apply(take or _default_answer(game, decision))


def gone(game, oid: int) -> bool:
    """A sacrificed token ceases to exist (111.7) -- it is not merely elsewhere.

    The state-based action removes the object outright, so looking up its zone
    raises. That disappearance *is* the assertion: an artifact token written as
    a non-token would sit in the graveyard instead.
    """
    return oid not in game.state.objects


class TestFood:
    """"{2}, {T}, Sacrifice this artifact: You gain 3 life." """

    def test_it_gains_three_life_and_sacrifices_itself(self, builder):
        game, oid = board(builder, "food_token")
        life = game.state.players[0].life

        activate(game, oid)

        assert game.state.players[0].life == life + 3
        assert gone(game, oid)


class TestJunk:
    """Exile the top card, and you may *play* it -- not cast it free.

    The distinction is the whole card. `play_exiled` is hideaway's permission and
    costs nothing; `playable_this_turn` grants permission at the printed price.
    Writing Junk with the former would hand every opponent of an Emergency Eject
    a free card off the top of a 100-card deck.
    """

    def test_it_exiles_the_top_card_of_your_library(self, builder):
        game, oid = board(builder, "junk_token", library=["forest"] * 10)
        top = game.state.players[0].library[0]
        before = len(game.state.players[0].library)

        activate(game, oid)

        assert len(game.state.players[0].library) == before - 1
        assert game.state.objects[top].zone is Zone.EXILE

    def test_the_exiled_card_is_playable_this_turn(self, builder):
        game, oid = board(builder, "junk_token", library=["forest"] * 10)
        top = game.state.players[0].library[0]

        activate(game, oid)

        exiled = game.state.objects[top]
        assert exiled.playable_by == 0
        assert exiled.playable_turn == game.state.turn


class TestLander:
    """A basic land onto the battlefield **tapped** -- never untapped.

    A generated card is never better than the printed one, and an untapped
    Rampant Growth is a different card.
    """

    def test_it_fetches_a_basic_onto_the_battlefield_tapped(self, builder):
        game, oid = board(builder, "lander_token", library=["forest"] * 10)
        lands = len(game.state.battlefield_objects(0))

        activate(game, oid)

        assert len(game.state.battlefield_objects(0)) == lands  # +forest, -token
        fetched = [o for o in game.state.battlefield_objects(0) if o.def_id == "forest"]
        assert len(fetched) == 1
        assert fetched[0].tapped

    def test_it_finds_nothing_in_a_library_with_no_basics(self, builder):
        """Searching a library that cannot answer is legal and simply whiffs."""
        game, oid = board(builder, "lander_token", library=["t_bear"] * 5)

        activate(game, oid)

        assert not [o for o in game.state.battlefield_objects(0) if o.def_id == "t_bear"]
        assert gone(game, oid)


class TestMap:
    """"Target creature you control explores."

    The target is declared on the *ability*, not on the card: a token has no
    casting, so a card-level target would never be chosen.
    """

    def test_it_explores_with_a_creature_you_control(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 6 + [BEAR])
            .battlefield(1, [BEAR])
            .library(0, ["forest"] * 10)
            .build()
        )
        create_token(game.state, "map_token", 0, 1)
        your_main(game)
        oid = oids_of(game, "map_token")[0]
        bear = oids_of(game, BEAR, 0)[0]
        before = len(game.state.players[0].library)

        activate(game, oid)

        # Explore reveals the top card; a land goes to hand, a nonland stays on
        # top with a +1/+1 counter. Either way the token is spent and the top of
        # the library was looked at.
        assert gone(game, oid)
        moved = len(game.state.players[0].library) != before
        assert moved or game.state.objects[bear].counter("+1/+1") == 1

    def test_it_offers_no_activation_with_no_creature_to_target(self, builder):
        """No legal target, no ability -- 601.2c, and the mana is not wasted."""
        game, oid = board(builder, "map_token")

        assert not [
            a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
        ]


class TestTreasure:
    """"{T}, Sacrifice this artifact: Add one mana of any color."

    It shipped as `{T}: Add {C}` -- no sacrifice, and colourless. Both halves
    were wrong in the direction that matters: a Treasure you never have to
    sacrifice is a Sol Ring that taps for one, and thirty-odd cards in the pool
    make Treasures. The colour is not cosmetic either -- Treasure is played to
    *fix*, and one that only made {C} could not cast the spell it was made for.
    """

    def test_it_makes_a_colored_mana_and_is_spent_doing_it(self, builder):
        game, oid = board(builder, "treasure_token")

        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid
        )
        game.apply(action)
        # A mana ability does not use the stack; the mode is the only question.
        for _ in range(20):
            decision = game.pending()
            if decision is None or decision.kind is DecisionKind.PRIORITY:
                break
            choice = next(
                (a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None
            )
            if choice is None:
                break
            game.apply(choice)

        assert gone(game, oid), "a Treasure that survives being tapped is a mana rock"
        pool = game.state.players[0].mana_pool
        assert pool.total() == 1
        # SYMBOLS is W U B R G C, so the last slot is colourless -- which is
        # what it used to produce and what a fixer must not.
        assert pool.amounts[SYMBOL_INDEX[COLORLESS]] == 0

    def test_every_color_is_on_offer(self, registry):
        """Five modes, not one. "Any color" is what a Treasure is played for."""
        ability = registry.get("treasure_token").abilities[0]
        assert ability.is_mana_ability
        modes = ability.effects[0]["modes"]
        assert [m["label"] for m in modes] == ["White", "Blue", "Black", "Red", "Green"]
