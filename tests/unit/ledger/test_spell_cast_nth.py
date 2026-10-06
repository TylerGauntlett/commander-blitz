"""The *ordinal* of a cast, per caster and per kind, settled where the ability queues.

    Mangara, the Diplomat — "Whenever an opponent casts their second spell each
    turn, draw a card."
    Esper Sentinel — "Whenever an opponent casts their first noncreature spell
    each turn, draw a card unless that player pays {X}…"

Five gap records asked for this (Esper Sentinel, Mangara, The Council of Four,
The Queen of Dale, Trouble in Pairs), and every one of them is the question
`test_draw_nth.py` already answered for draws, asked of SPELL_CAST instead:
*which* cast was this, for the player who made it. Rule 601.2i makes a spell
"cast" at one moment; 603.2 triggers the ability at that moment; and the
ordinal is a fact about that moment, not about the board.

Three near misses were each filed, and each is wrong in ordinary play:

* `max_per_turn: 1` is a cap counted **per permanent** (`triggers._queue` keys it
  by `(oid, ability index)`). "An opponent casts *their* first…" is scoped per
  opponent, so in a pod the first opponent's spell spends the cap and the second
  opponent's first spell taxes nothing. It also cannot say "second" at all.
* The intervening-if `spells_cast_this_turn == 2` reads right when it queues and
  is re-asked on resolution (603.4). An opponent who holds priority and casts a
  third spell in response has moved the tally to 3, and the ability resolves as
  `skipped="condition"`: Mangara draws nothing on exactly the turn it matters.
  That encoding is kept as `t_nth_spell_condition` and its failure is asserted.
* A flat ordinal, unfiltered, cannot say "their first **noncreature** spell". A
  player who casts a creature and then an instant is casting their first
  noncreature spell with the instant, which is their second spell.

So `nth` on a `spell_cast` trigger is scored against the trigger's own `filter`:
the ledger fold writes the flat ordinal onto the event, and a filtered trigger
counts how many of that player's earlier casts this turn matched the filter,
cut at that ordinal so a spell cast in response is not part of the run. The
earlier spells have left the stack, so only their printed faces can be asked,
and the loader refuses a filter key `_matches_printed` does not read.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.triggers import _spell_ordinal
from tests.conftest import action_for_card, pass_until, settle

SECOND = "t_nth_spell_opponent"  # Mangara, Trouble in Pairs: nth 2
NONCREATURE = "t_nth_spell_noncreature"  # Esper Sentinel, The Queen of Dale
ON_THEIR_TURN = "t_nth_spell_active"  # The Council of Four: any player, their turn
CONDITION = "t_nth_spell_condition"  # the `== 2` intervening-if near miss

INSTANT = "t_plain_instant"  # {W} instant: a noncreature spell
BEAR = "t_bear"  # {1}{G} creature spell
TOKEN = "human_soldier_1_1_w"


def position(builder, watcher: str, *, players: int = 2, caster_hand=None):
    """``(game, caster)``: the watcher on seat 0, seat 1 active with spells to cast.

    Seat 1 is the active player so the creature spell is castable at sorcery
    speed; every other seat gets instants and white mana so they can cast on
    seat 1's turn when handed priority.
    """
    lands = ["plains"] * 6 + ["forest"] * 4
    b = (
        builder(players=players)
        .battlefield(0, [watcher, "plains", "plains", "island"])
        .hand(0, [INSTANT, INSTANT])
        .step(Step.PRECOMBAT_MAIN)
        .active(1)
    )
    for pid in range(1, players):
        b = b.battlefield(pid, lands).library(pid, ["plains"] * 20)
        b = b.hand(pid, list(caster_hand or [INSTANT] * 4) if pid == 1 else [INSTANT] * 4)
    b = b.library(0, ["island"] * 20)
    return b.build(), 1


def give_priority(game, pid: int) -> None:
    """Pass until ``pid`` holds priority, without letting the stack resolve."""
    pass_until(
        game,
        lambda g: (
            g.pending() is not None
            and g.pending().kind is DecisionKind.PRIORITY
            and g.pending().player == pid
        ),
    )


def cast(game, pid: int, card_id: str) -> None:
    """``pid`` casts ``card_id`` and keeps priority -- nothing resolves."""
    give_priority(game, pid)
    game.apply(action_for_card(game, ActionKind.CAST, card_id))


def cast_and_resolve(game, pid: int, card_id: str) -> None:
    cast(game, pid, card_id)
    settle(game)


def tokens(game, pid: int = 0) -> int:
    return sum(1 for obj in game.state.battlefield_objects(pid) if obj.def_id == TOKEN)


def skipped_for_condition(game) -> int:
    return sum(
        1
        for event in game.state.events
        if event.type == EventType.ABILITY_RESOLVED and event.data.get("skipped") == "condition"
    )


class TestTheCastCarriesItsOrdinal:
    def test_each_cast_is_numbered_for_its_caster(self, builder):
        """The fold writes the post-bump tally, so the first spell is 1."""
        game, opp = position(builder, SECOND)
        cast_and_resolve(game, opp, INSTANT)
        cast_and_resolve(game, opp, INSTANT)
        casts = [e for e in game.state.events if e.type == EventType.SPELL_CAST]
        assert [e.data["nth"] for e in casts] == [1, 2]

    def test_each_player_counts_from_one(self, builder):
        """ "Their" second spell: seat 2's first cast is 1, whatever seat 1 did."""
        game, opp = position(builder, SECOND, players=3)
        cast_and_resolve(game, opp, INSTANT)
        cast_and_resolve(game, opp, INSTANT)
        cast_and_resolve(game, 2, INSTANT)
        casts = [
            (e.player, e.data["nth"]) for e in game.state.events if e.type == EventType.SPELL_CAST
        ]
        assert casts == [(1, 1), (1, 2), (2, 1)]


class TestOnlyTheSecondSpellFiresIt:
    """Mangara, the Diplomat, and Trouble in Pairs' third clause."""

    def test_the_first_spell_is_silent(self, builder):
        game, opp = position(builder, SECOND)
        cast_and_resolve(game, opp, INSTANT)
        assert tokens(game) == 0

    def test_the_second_spell_fires_it(self, builder):
        game, opp = position(builder, SECOND)
        cast_and_resolve(game, opp, INSTANT)
        cast_and_resolve(game, opp, INSTANT)
        assert tokens(game) == 1

    def test_the_third_and_fourth_spells_are_silent(self, builder):
        """ "Their second spell" is one spell, not "two or more"."""
        game, opp = position(builder, SECOND)
        for _ in range(4):
            cast_and_resolve(game, opp, INSTANT)
        assert tokens(game) == 1

    def test_a_creature_spell_counts(self, builder):
        """Unfiltered means every spell: a bear then an instant is two spells."""
        game, opp = position(builder, SECOND, caster_hand=[BEAR, INSTANT])
        cast_and_resolve(game, opp, BEAR)
        cast_and_resolve(game, opp, INSTANT)
        assert tokens(game) == 1

    def test_your_own_second_spell_is_silent(self, builder):
        game, _ = position(builder, SECOND)
        cast_and_resolve(game, 0, INSTANT)
        cast_and_resolve(game, 0, INSTANT)
        assert tokens(game) == 0


class TestASpellInResponseDoesNotHideIt:
    """The reader's failure, and the reason this is not a `condition`."""

    def test_the_ordinal_form_fires_once(self, builder):
        game, opp = position(builder, SECOND)
        cast_and_resolve(game, opp, INSTANT)
        cast(game, opp, INSTANT)  # the second spell: the trigger queues
        cast(game, opp, INSTANT)  # a third, in response, before it resolves
        settle(game)
        assert game.state.turn_ledger.spells_cast[opp] == 3
        assert tokens(game) == 1
        assert skipped_for_condition(game) == 0

    def test_the_condition_encoding_makes_nothing(self, builder):
        """603.4 re-reads the tally at 3 and skips the ability."""
        game, opp = position(builder, CONDITION)
        cast_and_resolve(game, opp, INSTANT)
        cast(game, opp, INSTANT)
        cast(game, opp, INSTANT)
        settle(game)
        assert skipped_for_condition(game) == 1, "the re-check read a tally of 3"
        assert tokens(game) == 0


class TestTheFirstNoncreatureSpellCountsOnlyNoncreatureSpells:
    """Esper Sentinel and The Queen of Dale: the ordinal is over a filtered run."""

    def test_the_first_noncreature_spell_fires_it(self, builder):
        game, opp = position(builder, NONCREATURE)
        cast_and_resolve(game, opp, INSTANT)
        assert tokens(game) == 1

    def test_a_creature_spell_is_not_the_first_noncreature_spell(self, builder):
        game, opp = position(builder, NONCREATURE, caster_hand=[BEAR])
        cast_and_resolve(game, opp, BEAR)
        assert tokens(game) == 0

    def test_an_instant_after_a_creature_is_still_the_first(self, builder):
        """The flat ordinal says 2 here; the printed card says first."""
        game, opp = position(builder, NONCREATURE, caster_hand=[BEAR, INSTANT])
        cast_and_resolve(game, opp, BEAR)
        cast_and_resolve(game, opp, INSTANT)
        casts = [e for e in game.state.events if e.type == EventType.SPELL_CAST]
        assert casts[-1].data["nth"] == 2
        assert tokens(game) == 1

    def test_the_second_noncreature_spell_is_silent(self, builder):
        game, opp = position(builder, NONCREATURE, caster_hand=[INSTANT, BEAR, INSTANT])
        cast_and_resolve(game, opp, INSTANT)
        cast_and_resolve(game, opp, BEAR)
        cast_and_resolve(game, opp, INSTANT)
        assert tokens(game) == 1

    def test_a_noncreature_spell_in_response_fires_nothing_more(self, builder):
        """Both instants are on the stack before either resolves: one first, one second."""
        game, opp = position(builder, NONCREATURE)
        cast(game, opp, INSTANT)
        cast(game, opp, INSTANT)
        settle(game)
        assert tokens(game) == 1

    def test_the_run_is_cut_at_this_cast(self, builder):
        """A later cast already in the ledger does not move an earlier one's place.

        `collect` matches synchronously today, so no trigger reads the ledger
        after a later cast has landed -- but the ordinal must not depend on that,
        so it is pinned on the function rather than through the bus.
        """
        game, opp = position(builder, NONCREATURE)
        cast(game, opp, INSTANT)
        cast(game, opp, INSTANT)
        state = game.state
        noncreature = {"not_types": ["Creature"]}
        assert len(state.turn_ledger.spells_cast_ids[opp]) == 2
        assert _spell_ordinal(state, noncreature, opp, 1) == 1
        assert _spell_ordinal(state, noncreature, opp, 2) == 2


class TestItIsCountedPerCaster:
    """ "An opponent casts **their** first…" -- the pod `max_per_turn` gets wrong."""

    def test_two_opponents_each_fire_it_once(self, builder):
        game, opp = position(builder, NONCREATURE, players=3)
        cast_and_resolve(game, opp, INSTANT)
        cast_and_resolve(game, 2, INSTANT)
        cast_and_resolve(game, opp, INSTANT)
        assert tokens(game) == 2, "each opponent has a first noncreature spell of their own"

    def test_one_opponents_spells_do_not_advance_anothers(self, builder):
        game, opp = position(builder, SECOND, players=3)
        cast_and_resolve(game, opp, INSTANT)
        cast_and_resolve(game, 2, INSTANT)
        assert tokens(game) == 0, "two spells, but nobody's second"
        cast_and_resolve(game, 2, INSTANT)
        assert tokens(game) == 1


class TestSpellsCastBeforeItArrivedStillCount:
    """The ordinal is the turn's, not the permanent's.

    The Council of Four: "Whenever a player casts their second spell during their
    turn". Seat 0 casts an instant, then the Council itself -- its second spell,
    cast while the Council was not yet on the battlefield -- and then a third.
    The third is not a second spell, however new the Council is.
    """

    def test_the_third_spell_after_it_enters_is_silent(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 6 + ["island"] * 2)
            # A spare instant, so seat 0 still has a decision after the third
            # cast and the engine's auto-pass does not roll the turn over.
            .hand(0, [INSTANT, ON_THEIR_TURN, INSTANT, INSTANT])
            .library(0, ["island"] * 20)
            .library(1, ["plains"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_and_resolve(game, 0, INSTANT)
        cast_and_resolve(game, 0, ON_THEIR_TURN)
        cast_and_resolve(game, 0, INSTANT)
        assert game.state.turn_ledger.spells_cast[0] == 3
        assert tokens(game) == 0


class TestDuringTheirTurn:
    def test_the_active_players_second_spell_fires_it(self, builder):
        game, opp = position(builder, ON_THEIR_TURN)
        cast_and_resolve(game, opp, INSTANT)
        cast_and_resolve(game, opp, INSTANT)
        assert tokens(game) == 1, "'you create' -- the Council's controller gets it"

    def test_a_second_spell_off_turn_is_silent(self, builder):
        game, _ = position(builder, ON_THEIR_TURN)
        cast_and_resolve(game, 0, INSTANT)
        cast_and_resolve(game, 0, INSTANT)
        assert tokens(game) == 0


class TestItIsScopedToTheTurn:
    def test_the_next_turn_counts_from_one_again(self, builder):
        game, opp = position(builder, NONCREATURE)
        cast_and_resolve(game, opp, INSTANT)
        assert tokens(game) == 1
        pass_until(game, lambda g: g.state.turn > 1 and g.state.step is Step.PRECOMBAT_MAIN)
        assert game.state.turn_ledger.spells_cast.get(opp, 0) == 0
        cast_and_resolve(game, opp, INSTANT)
        assert tokens(game) == 2


def watcher(**trigger) -> dict:
    """The card as raw JSON, for the load-time guards below."""
    return {
        "id": "t_nth_spell_probe",
        "name": "Test Nth Spell Probe",
        "oracle_text": "Whenever an opponent casts their first noncreature spell each turn, create a token.",
        "mana_cost": "{W}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "triggered",
                "text": "Whenever an opponent casts their first noncreature spell each turn, create a token.",
                "trigger": {"event": "spell_cast", "controller": "opponent", **trigger},
                "effects": [{"op": "create_token", "token": TOKEN}],
            }
        ],
    }


class TestTheLoaderGuards:
    def test_an_unfiltered_ordinal_loads(self):
        compile_card(CardModel.model_validate(watcher(nth=2)))

    @pytest.mark.parametrize(
        "filt",
        [
            {"not_types": ["Creature"]},
            {"any_types": ["Instant", "Sorcery"]},
            {"colors": ["U"], "min_colors": 2},
        ],
    )
    def test_a_printed_face_filter_loads(self, filt):
        compile_card(CardModel.model_validate(watcher(nth=1, filter=filt)))

    @pytest.mark.parametrize(
        "filt", [{"types": ["Creature"], "mana_value": {"gte": 3}}, {"exclude_self": True}]
    )
    def test_a_board_state_filter_is_refused(self, filt):
        """Earlier spells have left the stack; the key would count only this one."""
        with pytest.raises(DslError, match="counts earlier spells by their printed faces"):
            compile_card(CardModel.model_validate(watcher(nth=1, filter=filt)))

    def test_a_board_state_filter_without_nth_still_loads(self):
        """The restriction is on the ordinal, not on `spell_cast` filters."""
        compile_card(CardModel.model_validate(watcher(filter={"exclude_self": True})))

    @pytest.mark.parametrize("nth", [0, -1])
    def test_a_zeroth_spell_is_refused(self, nth):
        with pytest.raises(DslError, match="'nth' is an ordinal from 1"):
            compile_card(CardModel.model_validate(watcher(nth=nth)))

    def test_it_is_still_refused_on_an_event_with_no_ordinal(self):
        card = watcher(nth=2)
        card["abilities"][0]["trigger"]["event"] = "discard"
        with pytest.raises(DslError, match="only means anything on a draw or spell_cast"):
            compile_card(CardModel.model_validate(card))
