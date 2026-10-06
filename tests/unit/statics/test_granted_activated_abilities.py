"""A one-shot effect that gives a permanent an activated ability, stack or not.

    Urza's Saga — "I — This Saga gains "{T}: Add {C}."
    II — This Saga gains "{2}, {T}: Create a 0/0 colorless Construct artifact
    creature token with 'This token gets +1/+1 for each artifact you control.'"
    III — Search your library for an artifact card with mana cost {0} or {1}, put
    it onto the battlefield, then shuffle."

A chapter resolves once and what it grants outlives it: the Saga *has* the
ability for as long as it is that object (613.1f's "gains", no duration), and
400.7 ends it when the Saga leaves. `t_granting_saga` in
`tests/data/granted_activated.cards.json` is Urza's Saga written the way the
card will be, so it is the witness until the card itself is authored.

Two things were missing, and each alone ships a card that looks right:

**The op's grant was never offered.** `grant_ability` wrote a record onto the
permanent, and only `triggers.collect` read that record. Legality, the payment
solver and `game._activate` read `characteristics.abilities_of`, which knew only
the *static* grants -- so chapter I "loaded today" and the Saga still could not
tap for {C}. `abilities_of` now appends the op's activated grants too.

**A granted ability that uses the stack resolved as something else.**
`stack.ability_of` looked an activated ability up by index in its source's
*printed* list. Chapter II's ability sits at position 4 on the Saga; resolved
there it is nothing, and at the granter-pool index 1 it is **chapter II** --
which also tells 704.5s a chapter is still on the stack, so the Saga would never
be sacrificed after III while a Construct was on its way. 608.2 is the rule that
makes it matter: the ability resolves independently of its source, so the pair
(granter, index into ``grantable_abilities``) is recorded as it is activated,
the pair a granted trigger already carried.
"""

from __future__ import annotations

import dataclasses

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import sagas
from automtg.engine.characteristics import abilities_of, chars
from automtg.engine.costs import mana_sources
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import add_counters, clear_until_eot
from automtg.engine.stack import ability_of
from automtg.engine.zones import move_object
from tests.conftest import _default_answer, only_oid

SAGA = "t_granting_saga"
CONSTRUCT = "construct_0_0_c_artifact_buff"
ANCHOR = "lightning_bolt"  # keeps player 0 holding priority in the main phase
PRINTED = 3  # three chapters, so the first granted ability is at position 3
CONSTRUCT_TEXT = (
    "{2}, {T}: Create a 0/0 colorless Construct artifact creature token with "
    "'This token gets +1/+1 for each artifact you control.'"
)


def resolve(game, limit: int = 80) -> None:
    """Pass priority, answering anything else passively, until nothing waits."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.PRIORITY and not (
            game.state.stack or game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def saga_in_hand(builder):
    """Player 0 in their main phase holding the Saga, with {2} to spare after.

    The Bolt is an anchor, not a card under test: holding an instant they can
    cast keeps the engine from auto-passing player 0 out of the phase the
    moment the stack empties.
    """
    return (
        builder(players=2)
        .hand(0, [SAGA, ANCHOR])
        .battlefield(0, ["plains"] * 3 + ["mountain"])
        .library(0, ["sol_ring"] + ["plains"] * 10)
        .build()
    )


def play_saga(builder):
    """The Saga played as a land drop and chapter I resolved: ``(game, oid)``."""
    game = saga_in_hand(builder)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND)
    )
    saga = only_oid(game, SAGA)
    resolve(game)
    return game, saga


def reach_chapter_two(builder):
    """Chapter II resolved on top of chapter I: ``(game, oid)``."""
    game, saga = play_saga(builder)
    add_counters(game.state, saga, sagas.LORE, 1)
    resolve(game)
    return game, saga


def make_construct(game, saga: int):
    """The granted Construct ability, if it is being offered at all."""
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == saga
        ),
        None,
    )


def constructs(game) -> list[int]:
    return [
        oid for oid in game.state.battlefield if game.state.objects[oid].def_id == CONSTRUCT
    ]


def taps_for_colorless(game, saga: int) -> bool:
    return any(s.oid == saga for s in mana_sources(game.state, 0))


class TestChapterOneGrantsAManaAbility:
    def test_the_land_drop_enters_with_its_first_lore_counter(self, builder):
        """714.2b is part of entering however the Saga got there -- played as a
        land it was never cast, and it still starts its story."""
        game, saga = play_saga(builder)
        assert game.state.objects[saga].counter(sagas.LORE) == 1

    def test_nothing_is_granted_before_chapter_one_resolves(self, builder):
        game = saga_in_hand(builder)
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND)
        )
        saga = only_oid(game, SAGA)

        assert len(abilities_of(game.state, saga)) == PRINTED
        assert not taps_for_colorless(game, saga)

    def test_the_saga_has_the_mana_ability_afterwards(self, builder):
        game, saga = play_saga(builder)

        granted = abilities_of(game.state, saga)[PRINTED:]
        assert [a.text for a in granted] == ["{T}: Add {C}."]
        assert granted[0].is_mana_ability
        assert granted[0].index == PRINTED, "appended, so printed indices never move"

    def test_the_payment_solver_can_tap_it(self, builder):
        """A granted mana ability the solver cannot see is not a mana source."""
        game, saga = play_saga(builder)

        source = next(s for s in mana_sources(game.state, 0) if s.oid == saga)
        assert source.options == ((0, 0, 0, 0, 0, 1),)

    def test_the_grant_is_not_swept_at_cleanup(self, builder):
        """No printed duration: the Saga keeps it past the turn it was made."""
        game, saga = play_saga(builder)
        clear_until_eot(game.state)
        game.state.bump_chars()

        assert taps_for_colorless(game, saga)


class TestChapterTwoGrantsAStackAbility:
    def test_it_is_not_there_after_chapter_one_alone(self, builder):
        game, saga = play_saga(builder)
        assert make_construct(game, saga) is None

    def test_it_is_offered_at_its_derived_position(self, builder):
        """After the printed three and chapter I's grant -- the list legality,
        `game._activate` and `push_activated_ability` all index into."""
        game, saga = reach_chapter_two(builder)

        action = make_construct(game, saga)
        assert action is not None
        assert action.ability_index == PRINTED + 1
        assert abilities_of(game.state, saga)[action.ability_index].text == CONSTRUCT_TEXT

    def test_it_goes_on_the_stack_carrying_its_granter(self, builder):
        """Not a mana ability, so it uses the stack (605.3a) -- and the item
        says where its definition lives, not where it sat on the Saga."""
        game, saga = reach_chapter_two(builder)
        game.apply(make_construct(game, saga))

        item = game.state.stack[-1]
        assert item.kind == "ability"
        assert item.granted_by == saga
        assert item.ability_index == 1, "the granter's pool, not the Saga's list"
        assert ability_of(game.state, item).text == CONSTRUCT_TEXT
        assert game.state.objects[saga].tapped
        assert not constructs(game), "nothing happens until it resolves"

    def test_it_resolves_into_a_construct(self, builder):
        game, saga = reach_chapter_two(builder)
        game.apply(make_construct(game, saga))
        resolve(game)

        [token] = constructs(game)
        # The Saga is no artifact, so the Construct counts only itself.
        assert (chars(game.state, token).power, chars(game.state, token).toughness) == (1, 1)

    def test_it_resolves_after_the_saga_has_left(self, builder):
        """608.2: once activated, the ability is independent of its source.
        The grant went with the Saga (400.7); the ability on the stack did not."""
        game, saga = reach_chapter_two(builder)
        game.apply(make_construct(game, saga))
        move_object(game.state, saga, Zone.GRAVEYARD, to_player=0)
        resolve(game)

        assert len(constructs(game)) == 1

    def test_it_resolves_when_the_granter_object_no_longer_exists(self, builder):
        """A token granter is popped out of `state.objects` when it leaves, so
        the granter's card id travels with the item as well."""
        game, saga = reach_chapter_two(builder)
        game.apply(make_construct(game, saga))
        item = game.state.stack[-1]
        orphan = dataclasses.replace(item, granted_by=max(game.state.objects) + 1000)

        assert ability_of(game.state, orphan).text == CONSTRUCT_TEXT


class TestTheFinalChapter:
    """714.4 / 704.5s, on a Saga that is also a land."""

    def test_a_granted_ability_on_the_stack_is_not_a_chapter(self, builder):
        """Looked up at its old printed index, the Construct ability *was*
        chapter II -- and a chapter on the stack holds off the sacrifice."""
        game, saga = reach_chapter_two(builder)
        game.apply(make_construct(game, saga))

        assert not sagas.chapter_on_stack(game.state, saga)

    def test_three_sacrifices_the_saga_and_the_construct_still_arrives(self, builder):
        """Activate in response to chapter III: III resolves first, the Saga is
        sacrificed by the state-based action with the Construct ability still
        beneath, and that ability then resolves on its own."""
        game, saga = reach_chapter_two(builder)
        add_counters(game.state, saga, sagas.LORE, 1)
        game.apply(make_construct(game, saga))
        resolve(game)

        assert game.state.objects[saga].zone is Zone.GRAVEYARD
        assert len(constructs(game)) == 1


class TestTheGrantEndsWithTheObject:
    def test_it_is_gone_once_the_saga_leaves(self, builder):
        game, saga = reach_chapter_two(builder)
        move_object(game.state, saga, Zone.GRAVEYARD, to_player=0)

        assert game.state.objects[saga].granted_abilities_permanent == []
        assert len(abilities_of(game.state, saga)) == PRINTED

    def test_a_saga_that_returns_is_a_new_object(self, builder):
        """400.7. It starts again from chapter I, which grants the mana ability
        back -- and nothing brings the Construct ability with it."""
        game, saga = reach_chapter_two(builder)
        move_object(game.state, saga, Zone.GRAVEYARD, to_player=0)
        move_object(game.state, saga, Zone.BATTLEFIELD, to_player=0)
        game.state.objects[saga].tapped = False

        assert len(abilities_of(game.state, saga)) == PRINTED
        assert not taps_for_colorless(game, saga)

        resolve(game)
        assert [a.text for a in abilities_of(game.state, saga)[PRINTED:]] == ["{T}: Add {C}."]
        assert make_construct(game, saga) is None


class TestTheLoader:
    base = {
        "id": "probe",
        "name": "Probe",
        "types": ["Artifact"],
        "abilities": [
            {
                "kind": "activated",
                "text": "{T}: It gains the thing.",
                "cost": {"tap": True},
                "effects": [
                    {
                        "op": "grant_ability",
                        "ability": 0,
                        "duration": "permanent",
                        "objects": {"self_only": True},
                    }
                ],
            }
        ],
    }

    def compile(self, grantable: dict) -> None:
        compile_card(CardModel.model_validate({**self.base, "grantable_abilities": [grantable]}))

    def test_a_stack_using_activated_ability_may_be_granted(self):
        self.compile(
            {
                "kind": "activated",
                "text": "{2}, {T}: Draw a card.",
                "cost": {"mana": "{2}", "tap": True},
                "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            }
        )

    def test_one_that_works_from_another_zone_is_refused(self):
        """A grant lives on a permanent; granted cycling would never be offered
        from the hand it is printed to work in."""
        with pytest.raises(DslError, match="battlefield only"):
            self.compile(
                {
                    "kind": "activated",
                    "text": "{2}: Draw a card.",
                    "cost": {"mana": "{2}", "discard_self": True},
                    "active_zones": ["hand"],
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            )
