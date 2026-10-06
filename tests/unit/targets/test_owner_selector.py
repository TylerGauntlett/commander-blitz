"""``owner`` — the effect-side selector key that asks who *owns* an object.

    Majestic Genesis — "Reveal the top X cards of your library, where X is the
    greatest mana value of a commander **you own** on the battlefield or in the
    command zone."

Rule 903.3 defines a commander by **ownership**, and that is not a synonym for
control in a game this engine can actually reach: `gain_control` is implemented,
so a commander can sit on the battlefield under somebody who does not own it.
`controller: "you"` — the only ownership-shaped word the effect-side selector
language had — is then wrong in both directions at once. It misses your own
commander while an opponent holds it, and it counts an opponent's commander you
have taken. Either way X comes out a different number from the printed one, and
nothing on screen says so: a look-at-top that looked four deep instead of five
reads exactly like a look-at-top.

The word already existed twice over, in the same sense: `STATIC_FILTER_KEYS` has
it, and `costs._reduction_matches` has read it since Visions of Glory, which
spells this identical printed clause in a `mana_reduction`. So the asymmetry
this closes is that the same sentence on two cards in the same deck could only be
said on the cost side.

One difference from the static side, and it is the defaults rather than the
meaning: a static's filter defaults `controller: "you"`, so `owner` there has to
*switch that default off*; an effect-side selector defaults nothing, so `owner`
is an ordinary filter that composes with a `controller` written beside it.

What is pinned below, and each is a way this could be silently wrong:

1. A commander you own that an opponent controls still counts — the card.
2. The mirror: a commander you have stolen is **not** one you own.
3. `controller` is genuinely a different set on that board, in both directions.
4. Written together the two keys are a conjunction, not a replacement.
5. `owner: "opponent"` is the complement, `"any"` filters nobody out, and the
   mapping player spec names one seat.
6. The number the card actually reads — `extreme_value` over the union of the
   battlefield and the command zone — is 5 and not 0 when the commander is
   stolen.
7. In a zone somebody owns, `owner` says whose list to walk, so `owner: "any"`
   on a graveyard reads the table's and not only yours.
8. The loader knows the key, and refuses a word it cannot answer.
"""

from __future__ import annotations

import pytest

from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import matches, resolve_pool, validate_selector
from automtg.engine.errors import DslError
from automtg.engine.primitives import change_control
from tests.conftest import only_oid

#: "A commander you own on the battlefield or in the command zone" -- the pool
#: Majestic Genesis reads X off, written exactly as the card writes it.
COMMANDERS_YOU_OWN = {
    "union": [
        {"zone": "battlefield", "is_commander": True, "owner": "you"},
        {"zone": "command", "player": "you", "is_commander": True},
    ]
}

#: The same line with the only word that existed before. It is what the card
#: would have had to say, and it is a different pool.
COMMANDERS_YOU_CONTROL = {
    "union": [
        {"zone": "battlefield", "is_commander": True, "controller": "you"},
        {"zone": "command", "player": "you", "is_commander": True},
    ]
}

GREATEST_MANA_VALUE = {"of": "mana_value", "pick": "greatest"}


def board(builder, *, stolen: bool = False):
    """Player 0's commander stands on the battlefield; ``stolen`` hands it over.

    ``t_commander_five`` is ``{3}{W}{W}`` -- mana value 5, and the only
    commander in the position, so every count below is 5 or 0 and never
    ambiguous about which object it found.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 3 + ["t_bear"])
        .battlefield(0, ["t_commander_five"])
        .build()
    )
    commander = only_oid(game, "t_commander_five")
    game.state.objects[commander].is_commander = True
    game.state.players[0].commanders.append(commander)
    if stolen:
        change_control(game.state, commander, 1)
    return game, commander


def ctx_for(game, controller: int = 0) -> EffectContext:
    return EffectContext(state=game.state, controller=controller)


def x_from(game, selector, controller: int = 0) -> int:
    """The number Majestic Genesis looks that deep on."""
    from automtg.engine.effects.values import evaluate_value

    return evaluate_value(
        ctx_for(game, controller),
        {"extreme_value": {**GREATEST_MANA_VALUE, "objects": selector}},
    )


class TestOwnershipSurvivesAControlChange:
    def test_a_commander_an_opponent_stole_is_still_one_you_own(self, builder):
        """The card. 903.3 makes ownership the relation, and `change_control`
        deliberately leaves `owner` alone, so the answer has to be yes."""
        game, commander = board(builder, stolen=True)
        assert game.state.objects[commander].controller == 1
        assert matches(ctx_for(game), commander, {"owner": "you"})

    def test_control_says_the_opposite_on_the_same_board(self, builder):
        """Why the key exists. The near miss is not merely narrower here, it is
        false -- so X would be read off an empty pool."""
        game, commander = board(builder, stolen=True)
        assert not matches(ctx_for(game), commander, {"controller": "you"})

    def test_a_commander_you_stole_is_not_one_you_own(self, builder):
        """The other direction, which matters just as much: `controller` would
        count somebody else's commander towards your own X."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3)
            .battlefield(1, ["t_commander_five"])
            .build()
        )
        theirs = only_oid(game, "t_commander_five")
        game.state.objects[theirs].is_commander = True
        game.state.players[1].commanders.append(theirs)
        change_control(game.state, theirs, 0)

        ctx = ctx_for(game)
        assert matches(ctx, theirs, {"controller": "you"})
        assert not matches(ctx, theirs, {"owner": "you"})
        assert matches(ctx, theirs, {"owner": "opponent"})


class TestItIsAFilterAndNotADefault:
    def test_owner_and_controller_together_are_a_conjunction(self, builder):
        """"A permanent you own that an opponent controls" -- sayable only
        because the effect side defaults neither word. On the static side
        `owner` has to suppress a defaulted `controller: "you"`; here there is
        no default to suppress, so both clauses simply apply."""
        game, commander = board(builder, stolen=True)
        ctx = ctx_for(game)
        assert matches(ctx, commander, {"owner": "you", "controller": "opponent"})
        assert not matches(ctx, commander, {"owner": "you", "controller": "you"})

    def test_an_unstolen_permanent_fails_that_same_conjunction(self, builder):
        """The boundary of the clause above: with nobody having taken it, the
        permanent you own is one you also control."""
        game, commander = board(builder)
        ctx = ctx_for(game)
        assert not matches(ctx, commander, {"owner": "you", "controller": "opponent"})
        assert matches(ctx, commander, {"owner": "you", "controller": "you"})

    def test_any_filters_nobody_out(self, builder):
        """`"any"` is the third word, and it has to be inert rather than
        unrecognised -- an unknown word would also match everything, which is
        exactly why `validate_selector` refuses one."""
        game, commander = board(builder, stolen=True)
        bear = only_oid(game, "t_bear")
        ctx = ctx_for(game)
        assert matches(ctx, commander, {"owner": "any"})
        assert matches(ctx, bear, {"owner": "any"})

    def test_a_player_spec_names_one_seat(self, builder):
        """The mapping form, which `controller` already took and which no
        combination of the three words can say. `{"not": "you"}` is "a
        permanent you don't own" -- and at a pod it would be the difference
        between one seat and the table."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .battlefield(1, ["forest"])
            .build()
        )
        mine, theirs = game.state.battlefield[0], game.state.battlefield[1]
        ctx = ctx_for(game)
        validate_selector({"owner": {"not": "you"}}, "card.effects[0]")
        assert not matches(ctx, mine, {"owner": {"not": "you"}})
        assert matches(ctx, theirs, {"owner": {"not": "you"}})

    def test_it_composes_with_the_rest_of_the_selector(self, builder):
        """A bear you own is not a commander you own."""
        game, _ = board(builder)
        bear = only_oid(game, "t_bear")
        ctx = ctx_for(game)
        assert matches(ctx, bear, {"owner": "you"})
        assert not matches(ctx, bear, {"owner": "you", "is_commander": True})


class TestTheNumberTheCardReads:
    def test_x_is_five_while_the_commander_is_stolen(self, builder):
        """The whole point, end to end: `extreme_value` over the union the card
        writes still reads 5 when an opponent is holding the commander."""
        game, _ = board(builder, stolen=True)
        assert x_from(game, COMMANDERS_YOU_OWN) == 5

    def test_the_control_spelling_reads_zero_there(self, builder):
        """And what the card would have had to do without the key. An empty
        pool is 0 by `extreme_value`'s own rule, so Majestic Genesis would look
        at nothing at all and say nothing about why."""
        game, _ = board(builder, stolen=True)
        assert x_from(game, COMMANDERS_YOU_CONTROL) == 0

    def test_both_spellings_agree_when_nothing_was_stolen(self, builder):
        """The key is not a different reading of an ordinary board -- it only
        parts company from `controller` where control has actually moved."""
        game, _ = board(builder)
        assert x_from(game, COMMANDERS_YOU_OWN) == 5
        assert x_from(game, COMMANDERS_YOU_CONTROL) == 5

    def test_the_command_zone_half_is_unaffected(self, builder):
        """The other branch of the union. A commander nobody has cast is in the
        command zone, where `player: "you"` already scoped it correctly -- so
        the union has to find it with the battlefield branch empty."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3)
            .commander(0, ["t_commander_five"])
            .build()
        )
        assert x_from(game, COMMANDERS_YOU_OWN) == 5

    def test_an_opponents_commander_is_not_counted(self, builder):
        """X is read off *your* commanders. `owner: "any"` would be a bigger
        card, and so would the `controller` spelling on a board where you have
        stolen theirs."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3)
            .battlefield(1, ["t_commander_five"])
            .build()
        )
        theirs = only_oid(game, "t_commander_five")
        game.state.objects[theirs].is_commander = True
        game.state.players[1].commanders.append(theirs)
        change_control(game.state, theirs, 0)
        assert x_from(game, COMMANDERS_YOU_OWN) == 0
        assert x_from(game, COMMANDERS_YOU_CONTROL) == 5


class TestZonesSomebodyOwns:
    def test_owner_says_whose_graveyard_to_walk(self, builder):
        """In an owned zone the two words name the same seat -- 400.3 sends a
        card to its *owner's* graveyard -- so `owner` has to stand in for the
        defaulted `controller: "you"` there. Without that, a selector that
        deliberately said `owner: "any"` would read only your own graveyard:
        the silent narrowing `player` is validated to prevent, arriving through
        the other door."""
        game = (
            builder(players=2)
            .graveyard(0, ["t_bear"])
            .graveyard(1, ["t_bear", "t_bear"])
            .build()
        )
        ctx = ctx_for(game)
        every = resolve_pool(ctx, {"zone": "graveyard", "owner": "any"})
        assert len(every) == 3

    def test_owner_you_still_reads_only_yours(self, builder):
        game = (
            builder(players=2)
            .graveyard(0, ["t_bear"])
            .graveyard(1, ["t_bear", "t_bear"])
            .build()
        )
        ctx = ctx_for(game)
        mine = resolve_pool(ctx, {"zone": "graveyard", "owner": "you"})
        assert len(mine) == 1
        assert game.state.objects[mine[0]].owner == 0

    def test_controller_still_wins_when_both_are_written(self, builder):
        """`controller` is the word every shipped card in an owned zone uses,
        and adding `owner` must not change what any of them mean."""
        game = (
            builder(players=2)
            .graveyard(0, ["t_bear"])
            .graveyard(1, ["t_bear", "t_bear"])
            .build()
        )
        ctx = ctx_for(game)
        pool = resolve_pool(
            ctx, {"zone": "graveyard", "controller": "opponent", "owner": "any"}
        )
        assert len(pool) == 2


class TestTheLoaderKnowsTheWord:
    def test_owner_is_a_known_selector_key(self):
        validate_selector({"owner": "you", "is_commander": True}, "card.effects[0]")

    @pytest.mark.parametrize("word", ["mine", "controller", "owned", True])
    def test_an_unanswerable_word_is_refused_at_load_time(self, word):
        """An unrecognised word matches *everything*, so "a commander you own"
        would quietly become "a commander" and X would be an opponent's
        number. Refused for the reason `controller`'s typos are."""
        with pytest.raises(DslError, match="unknown owner clause"):
            validate_selector({"owner": word}, "card.effects[0]")
