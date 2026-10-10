""""As this artifact enters, choose a creature type."

Vanquisher's Banner is the shipped witness, and it asks the question twice:
"Creatures you control **of the chosen type** get +1/+1" is a static filter, and
"whenever you cast a creature spell **of the chosen type**" is a trigger filter.
Both are lists of literal subtype names everywhere else in the DSL, so the
choice needs somewhere to live and one substitution wherever a filter is matched.

**No new `DecisionKind`.** The gap record asked for a `CHOOSE_TYPE` kind and the
whole Tier C chain behind it — `actions.GENERATOR_DECISIONS`,
`legality._choice_actions`, `game.apply`, the authoring verifier's auto-answer
table. None of it was needed: `ask_mode` already asks "pick one of these labels"
and returns the index, which is exactly this question. That is the Fact-or-
Fiction lesson the skill opens with, and it turned a Tier C run into a Tier A
one.

The choice lives on the *object* (`GameObject.chosen_type`), not on the card:
two Banners choose independently, and a Banner that leaves and returns is a new
object that chooses again — which is why it resets with the rest of the
battlefield state.

Two things worth pinning because both look right on a board:

- Before a type is chosen, the anthem must pump **nobody**. A filter that fell
  back to "match everything" would make the Banner a global anthem for a moment,
  and matching everything is the failure mode an empty filter always has —
  see `test_spell_cost_reduction.py` for the same bug caught the hard way.
- The two filters must agree. A card whose anthem tracked the choice and whose
  trigger did not would draw off the wrong spells and nothing would say so.

*Divergence, recorded in `rules-coverage.md`*: the printed line is "**as** this
artifact enters", a replacement effect that cannot be responded to.
`zones._enter_battlefield` applies enter-replacements synchronously and cannot
stop to ask a question, so this is a `self_enters` trigger and the type is
chosen a moment after the permanent arrives rather than as it does. The window
is observable only by another trigger ordered between the two.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind

BANNER = "vanquishers_banner"
FLIER = "t_flier"  # {2}{U} Bird
BEAR = "t_bear"  # Bear


def board(builder, extra=()):
    return (
        builder(players=2)
        .battlefield(0, [BANNER, *extra])
        .build()
    )


def only(game, def_id: str) -> int:
    return next(
        o for o in game.state.battlefield if game.state.objects[o].def_id == def_id
    )


def choose(game, type_name: str) -> None:
    """Answer the Banner's enters-trigger with a named creature type."""
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_MODE
    labels = [o.label for o in decision.options]
    index = labels.index(type_name)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and a.choice == index
        )
    )


def cast_the_banner(builder, *, hand=(), lands=9):
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * lands)
        .hand(0, [BANNER, *hand])
        .library(0, ["forest"] * 10)
        .active(0)
        .max_turns(1)
        .build()
    )
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == BANNER
        )
    )
    return game


def play(game, def_id: str) -> int:
    """Cast a creature and let everything resolve. Returns the hand delta."""
    before = len(game.state.players[0].hand)
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
    )
    game.apply(action)
    for _ in range(20):
        decision = game.pending()
        if (
            decision is None
            or decision.kind is not DecisionKind.PRIORITY
            or not game.state.stack
        ):
            break
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    return len(game.state.players[0].hand) - before


class TestTheChoice:
    def test_it_is_asked_as_the_banner_arrives(self, builder):
        game = cast_the_banner(builder)
        decision = game.pending()
        assert decision is not None
        assert decision.prompt == "Choose a creature type"

    def test_it_offers_the_pool_s_creature_types(self, builder):
        game = cast_the_banner(builder)
        labels = [o.label for o in game.pending().options]
        assert "Bird" in labels
        assert "Zombie" in labels
        assert len(labels) > 50, "the whole pool, not a handful"
        assert labels == sorted(labels), "stable order, so a replay picks the same type"

    def test_it_is_recorded_on_the_permanent(self, builder):
        game = cast_the_banner(builder)
        choose(game, "Bird")
        assert game.state.objects[only(game, BANNER)].chosen_type == "Bird"


class TestTheAnthem:
    def test_it_pumps_the_chosen_type(self, builder):
        game = board(builder, extra=[BEAR])
        game.state.objects[only(game, BANNER)].chosen_type = "Bear"
        game.state.bump_chars()
        c = chars(game.state, only(game, BEAR))
        assert (c.power, c.toughness) == (3, 3)

    def test_it_leaves_other_types_alone(self, builder):
        game = board(builder, extra=[BEAR])
        game.state.objects[only(game, BANNER)].chosen_type = "Vampire"
        game.state.bump_chars()
        c = chars(game.state, only(game, BEAR))
        assert (c.power, c.toughness) == (2, 2)

    def test_before_a_choice_it_pumps_nobody(self, builder):
        """An unresolved filter must match nothing, never everything."""
        game = board(builder, extra=[BEAR])
        assert game.state.objects[only(game, BANNER)].chosen_type is None
        c = chars(game.state, only(game, BEAR))
        assert (c.power, c.toughness) == (2, 2)


class TestTheDrawTrigger:
    def test_casting_the_chosen_type_draws(self, builder):
        game = cast_the_banner(builder, hand=[FLIER])
        choose(game, "Bird")
        assert play(game, FLIER) == 0, "one card cast, one card drawn"

    def test_casting_another_type_does_not(self, builder):
        game = cast_the_banner(builder, hand=[FLIER])
        choose(game, "Zombie")
        assert play(game, FLIER) == -1, "cast it and drew nothing"

    def test_the_two_filters_agree(self, builder):
        """The anthem and the trigger read the same choice."""
        game = cast_the_banner(builder, hand=[FLIER])
        choose(game, "Bird")
        play(game, FLIER)
        c = chars(game.state, only(game, FLIER))
        assert (c.power, c.toughness) == (3, 3), "drew off it *and* pumped it"


class TestItIsPerObject:
    def test_the_choice_is_cleared_when_it_leaves(self, builder):
        from commanderblitz.engine.zones import destroy

        game = board(builder, extra=[BEAR])
        banner = only(game, BANNER)
        game.state.objects[banner].chosen_type = "Bear"
        destroy(game.state, banner)
        assert game.state.objects[banner].chosen_type is None, (
            "a permanent that comes back is a new object and chooses again"
        )

DISCOUNTER = "t_chosen_discount"  # {3} artifact; chosen-type creatures cost {1} less


class TestTheChoiceReachesTheOtherTwoReaders:
    """Herald's Horn — the two paths `resolve_chosen_subtypes` was never called from.

    The substitution was done wherever a filter was about to be matched *and* the
    source permanent happened to be in scope: static `affects`, via
    `characteristics._matches`, and trigger filters, via `triggers`. Two readers
    were left out, and both are on Herald's Horn.

    `spell_cost_reduction` prices a card that is still in hand, through
    `_matches_printed`, whose signature is a printed card and no object — which
    made it look as though the source was unavailable. It was not: the loop
    already walks `(source_obj, static)` pairs and had the permanent all along.

    The effect-side selector is the genuinely new one. "If it's a creature card
    of the chosen type" is asked about the top card of a *library*, where no
    trigger has bound anything and no static is being computed, so the marker
    dict reached `set(want) & subtypes` unresolved and matched nothing.
    """

    def board_with_discounter(self, builder, hand):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 9)
            .hand(0, [DISCOUNTER, *hand])
            .library(0, ["forest"] * 10)
            .active(0)
            .max_turns(1)
            .build()
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == DISCOUNTER
            )
        )
        return game

    def cost_of(self, game, def_id: str) -> int:
        """What legality is actually charging for this card right now."""
        from commanderblitz.engine.cost_reduction import cost_reduction

        card = game.state.card_of(
            next(
                game.state.objects[o]
                for o in game.state.players[0].hand
                if game.state.objects[o].def_id == def_id
            )
        )
        return card.mana_cost.mana_value() - cost_reduction(game.state, 0, card)

    def test_the_chosen_type_is_discounted(self, builder):
        game = self.board_with_discounter(builder, [BEAR])
        choose(game, "Bear")
        assert self.cost_of(game, BEAR) == 1, "a 2-drop Bear for {1}"

    def test_another_type_is_not(self, builder):
        game = self.board_with_discounter(builder, [FLIER])
        choose(game, "Bear")
        assert self.cost_of(game, FLIER) == 3, "the Bird pays full price"

    def test_nothing_is_discounted_before_a_type_is_chosen(self, builder):
        """`resolve_chosen_subtypes` matches nothing rather than everything.

        The opposite default would discount the entire game while the trigger
        was still on the stack.
        """
        game = self.board_with_discounter(builder, [BEAR])
        discounter = only(game, DISCOUNTER)
        assert game.state.objects[discounter].chosen_type is None, (
            "the trigger has not been answered yet"
        )
        assert self.cost_of(game, BEAR) == 2, "full price, not free"

