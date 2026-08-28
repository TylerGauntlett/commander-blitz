"""Kefka, Dancing Mad — "each player who owns a spell **you cast this way**".

    At the beginning of your end step, exile a card at random from each
    opponent's graveyard. You may cast any number of spells from among cards
    exiled this way without paying their mana costs. Then each player who owns a
    spell you cast this way loses life equal to its mana value.

`play_exiled` chose its cards, cast them and bound nothing, so no later effect
could name which ones were taken. The nearest thing the DSL could already say is
`exiled_with: "self"`, and it is wrong in **both directions at once**: a card
that was cast has left exile and stops matching, and a card the player declined
still matches. It names "exiled this way" and never "cast this way".

So `play_exiled` grew an `as`, joining `exile`, `sacrifice`, `reveal` and
`discard` in RECORDING_OPS. The binding is built from what `cast_for_free`
actually *did* rather than from the chosen list, because a card with no legal
target is offered and then not cast at all — `cast_for_free` now reports that
instead of returning nothing.

`t_kefka_exiled` is the counterfactual, and it is the whole test: identical card
except that its final loop reads the *exiled* cards. It drains the opponent
whether or not their card was ever cast, which is a strictly better card than
the one printed and would look completely ordinary on the board.

Also fixed here: `op_play_exiled` unconditionally defaulted `exiled_with:
"self"` onto its selector. Only `until_leaves` sets the `exiled_by` link that
key reads, so a plain `exile` followed by `play_exiled` over its own `as` pool
matched no card at all and the whole clause silently did nothing.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind

CAST_WAY = "t_kefka_bolt"
EXILED_WAY = "t_kefka_exiled"


def board(builder, card_id: str):
    return (
        builder(players=2)
        .hand(0, [card_id, "forest"])
        .battlefield(0, ["swamp"] * 6)
        .graveyard(1, ["t_bolt"])
        .library(0, ["forest"] * 20)
        .build()
    )


def resolve(game, card_id: str, *, cast_it: bool):
    """Cast the card, then take or decline the free cast it offers."""
    state = game.state
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    take = 1 if cast_it else 0
    for _ in range(40):
        decision = game.pending()
        if decision is None:
            break
        actions = game.legal_actions()
        if not actions:
            break
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choices = [a for a in actions if a.kind is ActionKind.CHOOSE]
            if take > 0 and choices:
                take -= 1
                game.apply(choices[0])
                continue
            done = [a for a in actions if a.kind is ActionKind.FINISH_DECLARATION]
            game.apply(done[0] if done else actions[0])
            continue
        if decision.kind is DecisionKind.PRIORITY and not state.stack:
            break
        game.apply(actions[0])
    return game


def opponent_life(game) -> int:
    return game.state.players[1].life


class TestTheBindingNamesWhatWasCast:
    def test_casting_the_card_drains_its_owner(self, builder):
        game = resolve(board(builder, CAST_WAY), CAST_WAY, cast_it=True)
        assert opponent_life(game) == 39, "mana value 1, so one life"

    def test_declining_drains_nobody(self, builder):
        """"A spell you cast this way" -- one you declined is not one of them."""
        game = resolve(board(builder, CAST_WAY), CAST_WAY, cast_it=False)
        assert opponent_life(game) == 40


class TestTheNearMissIsWrong:
    """Why `exiled_with` could not stand in, measured rather than argued."""

    def test_reading_the_exiled_set_drains_on_a_cast(self, builder):
        game = resolve(board(builder, EXILED_WAY), EXILED_WAY, cast_it=True)
        assert opponent_life(game) == 39

    def test_and_drains_just_the_same_on_a_decline(self, builder):
        """The bug: it charges for a spell nobody cast."""
        game = resolve(board(builder, EXILED_WAY), EXILED_WAY, cast_it=False)
        assert opponent_life(game) == 39

    def test_the_two_cards_disagree_exactly_where_it_matters(self, builder):
        """One number apart on the decline, identical on the cast."""
        cast_way = opponent_life(
            resolve(board(builder, CAST_WAY), CAST_WAY, cast_it=False)
        )
        exiled_way = opponent_life(
            resolve(board(builder, EXILED_WAY), EXILED_WAY, cast_it=False)
        )
        assert cast_way != exiled_way


class TestTheSelectorDefaultYieldsToABinding:
    """A pool named by a binding has already said which cards it means."""

    def test_a_bound_pool_is_actually_offered(self, builder):
        """Before the fix this matched nothing and the clause was inert."""
        game = board(builder, CAST_WAY)
        state = game.state
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and state.objects[a.source].def_id == CAST_WAY
        )
        game.apply(action)
        decision = game.pending()
        assert decision is not None
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS, (
            "play_exiled must offer the cards its binding names"
        )


class TestTheExileBindingAccumulates:
    """Kefka exiles from **each** opponent, which is a loop around one op.

    `op_exile` assigned its `as` outright, so each iteration clobbered the last
    and only the final opponent's card survived into the binding -- the others
    were exiled and then stranded, because the `play_exiled` that follows could
    no longer name them. `discard` already accumulated across the seats one op
    touches; this is the same fact one loop out.
    """

    def test_both_opponents_cards_are_offered(self, builder):
        game = (
            builder(players=3)
            .hand(0, ["t_kefka_pod", "forest"])
            .battlefield(0, ["swamp"] * 6)
            # Two cards per graveyard, not one. With one, `count: 1` is the
            # whole pool and the random pick short-circuits -- which would hide
            # a `random` written at the op level, where `op_exile` never reads
            # it and the player is asked *which* card to exile instead. The
            # prompt asserted below is `play_exiled`'s, so the exiles must have
            # happened silently.
            .graveyard(1, ["t_bolt", "t_bear"])
            .graveyard(2, ["t_bolt", "t_bear"])
            .library(0, ["forest"] * 20)
            .build()
        )
        state = game.state
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and state.objects[a.source].def_id == "t_kefka_pod"
        )
        game.apply(action)

        decision = game.pending()
        assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.prompt == "Play the exiled card", (
            "the exiles are random, so nothing should have been asked about them"
        )
        assert len(decision.options) == 2, (
            "one card per opponent was exiled, so both must be castable"
        )
