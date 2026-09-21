"""Riot -- 702.113, and the first keyword whose whole content is a replacement.

    "Nontoken creatures you control have riot.
     (They enter with your choice of a +1/+1 counter or haste.)"
                                                -- Rhythm of the Wild

Two claims, and this file is here because each one has a cheaper spelling that
looks identical until the moment it matters.

**It is a replacement, not a trigger (614.1c).** The creature is *never* on the
battlefield at its printed size. The approximation -- a `self_enters` trigger
running `choose_mode` over `add_counters` and `grant_keyword` -- puts it there
first and decorates it afterwards, and three separate things go wrong in that
gap: a printed 0/0 is binned by state-based actions before the trigger ever
resolves, every other enters trigger reads a size riot says was never on the
board, and an opponent holds priority with a creature that should not have been
seen without its counter. `TestTheCounterIsPartOfTheArrival` is that argument:
the 0/0 lives, and a watcher on the other side of the table reads 1 rather than
0. Neither is reachable from a trigger, in any ordering.

**It is a `Keyword`, not a `ReplacementModel` entry.** Every `self_enters*`
event is printed on the permanent it modifies, and riot's commonest printing is
one permanent handing the replacement to *other* creatures. A replacement is not
grantable; a keyword is, through the `grant_keyword` static that already exists.
So the same machinery has to answer both `t_riot_brute` -- the word printed on
the creature -- and `t_riot_drum`, which is Rhythm of the Wild's second line, and
`TestGrantedRiot` pins that half.

The choice is the **controller's**, made as the creature enters, and it is per
creature: two arrivals are two questions, because the choice belongs to each
arrival rather than to whatever put them there. Both branches are covered, and
so is the thing the haste half exists for -- attacking the turn it arrived.

A token is asked nothing, which is the printed card: Rhythm of the Wild says
nontoken, its `affects` says `is_token: false`, and `create_token` is not a
generator and could not stop to ask anyway.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Keyword, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import action_for_card, pass_until

BRUTE = "t_riot_brute"  # 2/2 with riot printed on it
PLAIN = "t_riot_plain"  # the same 2/2 without it -- the control
SAPLING = "t_riot_sapling"  # a printed 0/0 with riot: alive only with the counter
DRUM = "t_riot_drum"  # "Nontoken creatures you control have riot"
SCRIBE = "t_riot_scribe"  # gains life equal to the entering creature's power
RAISE = "t_riot_raise"  # returns a creature card from your graveyard
SPAWN = "t_riot_spawn"  # makes a 1/1 token

COUNTER, HASTE = 0, 1


def position(builder, hand, *, board=(), graveyard=(), opponent=()):
    """Eight Forests and a main phase, which is every position in this file.

    ``opponent`` seats the other player with the same eight lands and a hand of
    their own -- the one shape `TestGrantedRiot` needs, because "creatures
    **you** control" is only a claim if somebody else's creature is watched
    entering under the same Drum.
    """
    builder_ = (
        builder(players=2)
        .battlefield(0, ["forest"] * 8)
        .battlefield(0, list(board))
        .hand(0, list(hand))
        .graveyard(0, list(graveyard))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
    )
    if opponent:
        builder_ = builder_.battlefield(1, ["forest"] * 8).hand(1, list(opponent))
    game = builder_.build(advance=False)
    game._advance()
    return game


def riot_question(game):
    """The pending riot decision, or None.

    A `CHOOSE_MODE` is what `ask_mode` yields, and riot is the only thing in
    these positions that asks one -- no card here is modal.
    """
    pending = game.pending()
    if pending is None or pending.kind is not DecisionKind.CHOOSE_MODE:
        return None
    return pending


def answer_riot(game, half: int) -> bool:
    """Take ``half`` of the riot choice if it is on the table. True if it was."""
    if riot_question(game) is None:
        return False
    choices = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
    game.apply(choices[half])
    return True


def cast(game, card_id: str, half: int = COUNTER):
    """Cast ``card_id``, answering every riot question it raises with ``half``."""
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    for _ in range(40):
        if not answer_riot(game, half):
            break
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def to_combat(game) -> None:
    """Walk to this turn's declare-attackers step, and no further.

    Not a `pass_until` on the step alone: the creature's controller is the
    active player in every position here, so the *next* such step would be
    theirs again two turns later, with the summoning sickness gone and both
    halves of riot looking alike.
    """
    turn = game.state.turn
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    assert game.state.turn == turn, "walked past the turn the creature entered"


def find(game, def_id: str):
    return next(o for o in game.state.objects.values() if o.def_id == def_id)


def counters(game, def_id: str) -> int:
    return find(game, def_id).counters.get("+1/+1", 0)


class TestTheChoiceIsOffered:
    def test_a_printed_riot_creature_is_asked(self, builder):
        game = position(builder, [BRUTE])
        game.apply(action_for_card(game, ActionKind.CAST, BRUTE))
        assert riot_question(game) is not None

    def test_the_question_names_both_halves(self, builder):
        """"…with your choice of a +1/+1 counter **or** haste." Exactly two
        options, so `ask_mode` cannot short-circuit them the way it does a
        "choose one" with one mode left."""
        game = position(builder, [BRUTE])
        game.apply(action_for_card(game, ActionKind.CAST, BRUTE))
        pending = riot_question(game)
        assert [option.label for option in pending.options] == [
            "A +1/+1 counter",
            "Haste",
        ]

    def test_a_creature_without_riot_is_asked_nothing(self, builder):
        """The control. Without it every test here would pass on a version
        that asked the question of every creature in the game."""
        game = position(builder, [PLAIN])
        game.apply(action_for_card(game, ActionKind.CAST, PLAIN))
        assert riot_question(game) is None

    def test_the_controller_is_the_one_asked(self, builder):
        """"**your** choice" -- the arriving creature's controller, not the
        active player by coincidence and not the spell's target."""
        game = position(builder, [BRUTE])
        game.apply(action_for_card(game, ActionKind.CAST, BRUTE))
        assert riot_question(game).player == 0


class TestTheCounterBranch:
    def test_it_arrives_with_a_counter(self, builder):
        game = position(builder, [BRUTE])
        cast(game, BRUTE, COUNTER)
        assert counters(game, BRUTE) == 1

    def test_it_is_bigger_for_it(self, builder):
        """A +1/+1 counter is read by the layer pipeline like any other, so
        the 2/2 is a 3/3 -- not a pump effect that wears off."""
        game = position(builder, [BRUTE])
        cast(game, BRUTE, COUNTER)
        seen = chars(game.state, find(game, BRUTE).oid)
        assert (seen.power, seen.toughness) == (3, 3)

    def test_it_has_no_haste(self, builder):
        """The two halves are exclusive: taking the counter buys nothing else."""
        game = position(builder, [BRUTE])
        cast(game, BRUTE, COUNTER)
        assert Keyword.HASTE.value not in chars(game.state, find(game, BRUTE).oid).keywords

    def test_it_cannot_attack_the_turn_it_arrived(self, builder):
        """302.6, unchanged. The counter is not a consolation prize with a
        hidden upside.

        The Scribe is on the board only so there *is* a combat phase: a turn in
        which nobody can attack skips it, and a test that walked to the next
        declare-attackers step would be asking about a creature that has since
        stopped being summoning sick."""
        game = position(builder, [BRUTE], board=[SCRIBE])
        cast(game, BRUTE, COUNTER)
        oid = find(game, BRUTE).oid
        to_combat(game)
        assert not any(
            a.kind is ActionKind.ADD_ATTACKER and a.source == oid
            for a in game.legal_actions()
        )


class TestTheHasteBranch:
    def test_it_arrives_with_haste(self, builder):
        game = position(builder, [BRUTE])
        cast(game, BRUTE, HASTE)
        assert Keyword.HASTE.value in chars(game.state, find(game, BRUTE).oid).keywords

    def test_it_arrives_with_no_counter(self, builder):
        game = position(builder, [BRUTE])
        cast(game, BRUTE, HASTE)
        assert counters(game, BRUTE) == 0

    def test_it_can_attack_the_turn_it_arrived(self, builder):
        """The whole of the haste half. Without this the branch is a keyword
        that shows on a card and changes nothing a player can do."""
        game = position(builder, [BRUTE])
        cast(game, BRUTE, HASTE)
        oid = find(game, BRUTE).oid
        to_combat(game)
        assert any(
            a.kind is ActionKind.ADD_ATTACKER and a.source == oid
            for a in game.legal_actions()
        )

    def test_the_haste_outlives_the_turn(self, builder):
        """`granted_keywords`, not an `until_eot` `TempEffect`: riot's haste is
        part of what the creature is for as long as it is on the battlefield.
        An until-end-of-turn grant does the same thing today and nothing ever
        after, so the two branches would become indistinguishable one turn
        later -- see `tests/unit/test_permanent_keyword_grant.py`, which is
        where that duration was built."""
        game = position(builder, [BRUTE])
        cast(game, BRUTE, HASTE)
        oid = find(game, BRUTE).oid
        pass_until(game, lambda g: g.state.turn >= 3)
        assert Keyword.HASTE.value in chars(game.state, oid).keywords


class TestTheCounterIsPartOfTheArrival:
    """614.1c, and the reason riot is not a `self_enters` trigger.

    Both tests here fail on the trigger spelling no matter how the triggers are
    ordered, because the trigger cannot run before the creature is on the
    battlefield and these are questions about that instant.
    """

    def test_a_printed_zero_zero_survives(self, builder):
        """A 0/0 with riot that took the counter is a 1/1 the whole time it is
        on the battlefield. Written as a trigger it arrives as a 0/0 and
        state-based actions bin it before anything can grow it (704.5f)."""
        game = position(builder, [SAPLING])
        cast(game, SAPLING, COUNTER)
        assert find(game, SAPLING).zone is Zone.BATTLEFIELD
        seen = chars(game.state, find(game, SAPLING).oid)
        assert (seen.power, seen.toughness) == (1, 1)

    def test_the_haste_half_does_not_save_it(self, builder):
        """The boundary of the test above: the choice is real, and taking the
        other half of it really does leave a 0/0 to die. Riot is not "a counter,
        plus haste if you ask nicely"."""
        game = position(builder, [SAPLING])
        cast(game, SAPLING, HASTE)
        assert find(game, SAPLING).zone is Zone.GRAVEYARD

    def test_another_enters_trigger_reads_the_bigger_creature(self, builder):
        """"…gain life equal to **its power**", asked about a 2/2 that entered
        with a +1/+1 counter. Three, not two: the counter was on before the
        ENTERS_BATTLEFIELD event went out, so nothing watching the battlefield
        ever saw the printed size."""
        game = position(builder, [BRUTE], board=[SCRIBE])
        life = game.state.players[0].life
        cast(game, BRUTE, COUNTER)
        assert game.state.players[0].life == life + 3

    def test_the_watcher_reads_the_printed_size_on_the_haste_branch(self, builder):
        """The same watcher, the other branch, and the control for the test
        above: two is what it should read when no counter was placed."""
        game = position(builder, [BRUTE], board=[SCRIBE])
        life = game.state.players[0].life
        cast(game, BRUTE, HASTE)
        assert game.state.players[0].life == life + 2


class TestGrantedRiot:
    """Rhythm of the Wild's second line -- the printing riot is a keyword for.

    A `ReplacementModel` could not say this at all: every `self_enters*` event
    is printed on the permanent it modifies, and nothing in the DSL lets one
    permanent hand a replacement to other creatures. A keyword is grantable, so
    `grant_keyword` -- which already existed -- is the whole mechanism.
    """

    def test_a_creature_with_no_riot_of_its_own_is_asked(self, builder):
        game = position(builder, [PLAIN], board=[DRUM])
        game.apply(action_for_card(game, ActionKind.CAST, PLAIN))
        assert riot_question(game) is not None

    def test_the_counter_lands(self, builder):
        game = position(builder, [PLAIN], board=[DRUM])
        cast(game, PLAIN, COUNTER)
        assert counters(game, PLAIN) == 1

    def test_the_haste_lands(self, builder):
        game = position(builder, [PLAIN], board=[DRUM])
        cast(game, PLAIN, HASTE)
        assert Keyword.HASTE.value in chars(game.state, find(game, PLAIN).oid).keywords

    def test_an_opponents_creature_is_not_asked(self, builder):
        """"…creatures **you** control." The granting static's `affects` is
        matched against the arriving object exactly as it would be against a
        permanent, so the filter stays the printed one rather than widening
        because the object is still in transit."""
        game = position(builder, [], board=[DRUM], opponent=[PLAIN])
        pass_until(
            game,
            lambda g: g.state.active_player == 1 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        game.apply(action_for_card(game, ActionKind.CAST, PLAIN))
        assert riot_question(game) is None

    def test_a_token_is_asked_nothing(self, builder):
        """"**Nontoken** creatures you control." The static's `is_token: false`
        says so, and `create_token` is not a generator and could not have
        stopped to ask in any case -- so the token arrives as its printed 1/1
        with neither half."""
        game = position(builder, [SPAWN], board=[DRUM])
        cast(game, SPAWN)
        token = next(
            game.state.objects[oid]
            for oid in game.state.battlefield
            if game.state.objects[oid].is_token
        )
        assert token.counters.get("+1/+1", 0) == 0
        assert Keyword.HASTE.value not in chars(game.state, token.oid).keywords

    def test_the_grant_goes_away_with_the_granter(self, builder):
        """The control for the whole class: no Drum, no question. Riot is not
        quietly on every creature because the keyword now exists."""
        game = position(builder, [PLAIN])
        game.apply(action_for_card(game, ActionKind.CAST, PLAIN))
        assert riot_question(game) is None


class TestEveryArrivalIsAsked:
    """"Nontoken creatures you control **have riot**" is a fact about the
    creatures, not about the cast line -- so any arrival from any zone carries
    it, exactly as Mox Diamond's replacement does."""

    def test_a_reanimated_creature_is_asked(self, builder):
        game = position(builder, [RAISE], board=[DRUM], graveyard=[PLAIN])
        cast(game, RAISE, COUNTER)
        assert find(game, PLAIN).zone is Zone.BATTLEFIELD
        assert counters(game, PLAIN) == 1

    def test_a_reanimated_creature_can_take_the_haste(self, builder):
        game = position(builder, [RAISE], board=[DRUM], graveyard=[PLAIN])
        cast(game, RAISE, HASTE)
        oid = find(game, PLAIN).oid
        assert Keyword.HASTE.value in chars(game.state, oid).keywords
        assert counters(game, PLAIN) == 0


class TestTheChoiceIsPerCreature:
    def test_two_arrivals_are_two_questions(self, builder):
        """The choice belongs to each arrival, so a second riot creature is
        asked again rather than inheriting the first answer -- and the two may
        differ."""
        game = position(builder, [BRUTE, PLAIN], board=[DRUM])
        cast(game, BRUTE, HASTE)
        cast(game, PLAIN, COUNTER)
        assert Keyword.HASTE.value in chars(game.state, find(game, BRUTE).oid).keywords
        assert counters(game, BRUTE) == 0
        assert counters(game, PLAIN) == 1
        assert Keyword.HASTE.value not in chars(game.state, find(game, PLAIN).oid).keywords


class TestItIsStillAKeyword:
    def test_the_creature_reads_as_having_riot(self, builder):
        """Once the permanent is there the keyword is spent, but it is still a
        characteristic -- `chars` reports it, so anything that filters on
        keywords sees the word the card prints."""
        game = position(builder, [BRUTE])
        cast(game, BRUTE, COUNTER)
        assert Keyword.RIOT.value in chars(game.state, find(game, BRUTE).oid).keywords

    def test_the_granted_form_reads_the_same_way(self, builder):
        game = position(builder, [PLAIN], board=[DRUM])
        cast(game, PLAIN, COUNTER)
        assert Keyword.RIOT.value in chars(game.state, find(game, PLAIN).oid).keywords


class TestTheOtherLine:
    """"Creature spells you control can't be countered", which the gap record
    recorded as already expressible and which was not.

    `spells_cant_be_countered` has read an optional `affects_spells` since it
    was written, and the loader refused to let any card carry one -- so every
    narrowed printing of the sentence was unsayable and the whole family could
    only be said as Lier's symmetrical line.
    """

    def _card(self, ability):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "types": ["Enchantment"],
                "mana_cost": "{1}",
                "abilities": [ability],
            }
        )

    def test_a_narrowed_filter_loads(self):
        card = compile_card(
            self._card(
                {
                    "kind": "static",
                    "text": "Creature spells you control can't be countered.",
                    "effect": "spells_cant_be_countered",
                    "affects_spells": {"types": ["Creature"], "controller": "you"},
                }
            )
        )
        assert card.abilities[0].static["affects_spells"] == {
            "types": ["Creature"],
            "controller": "you",
        }

    def test_no_filter_still_loads(self):
        """Lier prints none -- "spells can't be countered", everyone's. An
        omitted filter is *wider* than any written one, not a defaulted narrow
        one, which is why `controller` defaults to any seat here and to "you"
        on a cost reduction."""
        card = compile_card(
            self._card(
                {
                    "kind": "static",
                    "text": "Spells can't be countered.",
                    "effect": "spells_cant_be_countered",
                }
            )
        )
        assert card.abilities[0].static.get("affects_spells") is None

    def test_board_state_is_refused_in_the_filter(self):
        """A spell has a printed face and a caster and no board state, so the
        filter is checked against `SPELL_FILTER_KEYS` rather than the wider
        permanent list -- the same refusal `spell_cost_reduction` makes."""
        with pytest.raises(DslError, match="affects_spells"):
            compile_card(
                self._card(
                    {
                        "kind": "static",
                        "text": "Creature spells you control can't be countered.",
                        "effect": "spells_cant_be_countered",
                        "affects_spells": {"types": ["Creature"], "tapped": True},
                    }
                )
            )

    def test_affects_is_refused(self):
        """`affects` picks out permanents and this static describes spells, so
        the near-miss spelling fails at load rather than loading clean and
        protecting nothing."""
        with pytest.raises(DslError, match="affects_spells"):
            compile_card(
                self._card(
                    {
                        "kind": "static",
                        "text": "Creature spells you control can't be countered.",
                        "effect": "spells_cant_be_countered",
                        "affects": {"types": ["Creature"], "controller": "you"},
                    }
                )
            )
