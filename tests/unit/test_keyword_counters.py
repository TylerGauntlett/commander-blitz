"""Keyword counters (122.1c): a counter named for a keyword **is** that keyword.

"A keyword counter is a counter with a keyword ability's name. A permanent with
a keyword counter on it has that keyword ability." Nothing about the counter is
bookkeeping *about* a keyword — the counter is where the keyword comes from.

What was wrong without this, and it was wrong silently: `add_counters` has always
accepted any `counter` string, and the characteristics pipeline read exactly two
kinds — `+1/+1` and `-1/-1`, for power and toughness. Nothing consulted counters
when computing **keywords**. So a card printing "return that card to the
battlefield with a vigilance counter and a lifelink counter on it" loaded, cast,
resolved, wrote two tallies, and handed back a creature that tapped when it
attacked and gained nobody any life. That is the one outcome
`cards/authoring/verify.py` exists to prevent, arriving through a clause that
every gate passed.

`grant_keyword` is the near miss and is the wrong shape three times over: there
is no counter object, so `counters_on`, `remove_counters`, `move_counters` and
`proliferate` cannot see it; its grant is bound to a duration or to a live
source; and a static one cannot be pointed at a single creature chosen when an
ability resolved. Hence a layer that reads the counters, not a new kind of grant.

**The witnesses are both still blocked**, which is why this file carries the
whole mechanic. Gilraen, Dúnedain Protector ("…with a vigilance counter and a
lifelink counter on it") also needs a delayed trigger able to name the card it
exiled; Oath of Eorl ("Put an indestructible counter on up to one target Human")
is a Saga, which is a rules subsystem the engine does not have. Neither is
authored, so there is no re-verified card standing behind any of this — only
what is asserted here.

Where the layer sits is the design question, and the answer is *with the keyword
grants* rather than beside the +1/+1 counters four layers later. That is what the
real layer system does for the same reason — 613.1f applies keyword counters with
the ability-adding effects, 613.1d applies +1/+1 counters — and it is what the
two counters do that separates them: one is an ability, one is a size. The
position cannot be observed by an outcome, because keywords only accumulate into
a set and no layer removes one, so it is asserted here as what it is: both halves
of "read the counters" work, and neither leaks into the other.
"""

from __future__ import annotations

import contextlib

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars, has_keyword
from automtg.engine.combat import can_block
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.primitives import add_counters, grant_keyword, remove_counters
from automtg.engine.structs import TargetRef
from automtg.engine.zones import destroy, move_object
from tests.conftest import action_for_card, find_action, only_oid, pass_until

BEAR = "t_bear"
VIGILANT = "t_vigilant"
INDESTRUCTIBLE = "t_indestructible"
FLIER = "t_flier"


def a_bear(builder, counters: dict[str, int] | None = None):
    """One 2/2 with no printed keywords, and its oid.

    A vanilla creature is the whole point of the fixture: every keyword these
    tests see has to have come from a counter, so the printed face must have
    none to lend.
    """
    game = builder(players=2).battlefield(0, [BEAR], counters=counters).build()
    return game, only_oid(game, BEAR, 0)


def run(game, controller: int = 0, **effect) -> None:
    """Drive one op to completion outside the stack, as `test_proliferate` does."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [effect])
    with contextlib.suppress(StopIteration):
        decision = next(gen)
        while True:
            # Proliferate's "any number" is answered with everything offered.
            decision = gen.send(list(range(len(decision.options))))


def counters_of(game, oid: int) -> dict[str, int]:
    return dict(game.state.objects[oid].counters)


class TestTheCounterIsTheKeyword:
    @pytest.mark.parametrize(
        "keyword",
        ["vigilance", "lifelink", "indestructible", "flying", "first_strike", "menace"],
    )
    def test_any_implemented_keyword_can_arrive_as_a_counter(self, builder, keyword):
        """122.1c names no subset, so the set is derived from `Keyword` itself.

        Parametrised rather than asserted once because the failure this guards
        against is a hand-maintained list: the next card to print a *menace*
        counter must not need an engine change.
        """
        game, bear = a_bear(builder, {keyword: 1})
        assert has_keyword(game.state, bear, keyword)

    def test_it_is_the_same_creature_the_printed_keyword_makes(self, builder):
        """Parity is the claim. A vigilance counter is not "nearly" vigilance."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR], counters={"vigilance": 1})
            .battlefield(0, [VIGILANT])
            .build()
        )
        countered = chars(game.state, only_oid(game, BEAR, 0))
        printed = chars(game.state, only_oid(game, VIGILANT, 0))
        assert countered.keywords == printed.keywords
        assert (countered.power, countered.toughness) == (printed.power, printed.toughness)

    def test_several_counters_grant_several_keywords(self, builder):
        """Gilraen's clause is two counters at once, so it must not be one slot."""
        game, bear = a_bear(builder, {"vigilance": 1, "lifelink": 1})
        assert {"vigilance", "lifelink"} <= chars(game.state, bear).keywords

    def test_a_counter_that_is_not_a_keyword_grants_nothing(self, builder):
        """The shipped pool is full of charge, quest and slumber counters."""
        game, bear = a_bear(builder, {"charge": 3, "quest": 2, "slumber": 1})
        assert chars(game.state, bear).keywords == frozenset()

    def test_a_plus_one_counter_is_still_only_a_size(self, builder):
        """The other half of reading the counters, unchanged. A layer that mixed
        the two would give every growing creature a `+1/+1` "keyword"."""
        game, bear = a_bear(builder, {"+1/+1": 2})
        c = chars(game.state, bear)
        assert (c.power, c.toughness) == (4, 4)
        assert c.keywords == frozenset()

    def test_a_keyword_counter_is_not_a_size(self, builder):
        """And the mirror: the keyword layer must not reach the P/T layer."""
        game, bear = a_bear(builder, {"vigilance": 4})
        c = chars(game.state, bear)
        assert (c.power, c.toughness) == (2, 2)

    def test_partner_is_excluded(self, builder):
        """`INERT_KEYWORDS` is excluded for the reason it exists: partner is a
        deck-construction word, and the engine is handed a finished deck. A
        counter that grants nothing is the inert tally in a costume."""
        game, bear = a_bear(builder, {"partner": 1})
        assert chars(game.state, bear).keywords == frozenset()


class TestARuleActuallyReadsIt:
    """A keyword in a set is not a keyword. Three rules, three modules."""

    def to_attackers(self, game):
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )

    def attack_with(self, game, oid: int, defender: int = 1):
        game.apply(
            find_action(
                game,
                ActionKind.ADD_ATTACKER,
                source=oid,
                targets=(TargetRef.player(defender),),
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))

    def test_a_vigilance_counter_attacks_untapped(self, builder):
        game, bear = a_bear(builder, {"vigilance": 1})
        self.to_attackers(game)
        self.attack_with(game, bear)
        assert not game.state.objects[bear].tapped

    def test_the_same_creature_without_it_taps(self, builder):
        """The control. Without it the test would pass on a bear that never
        tapped for a reason of its own."""
        game, bear = a_bear(builder)
        self.to_attackers(game)
        self.attack_with(game, bear)
        assert game.state.objects[bear].tapped

    def test_an_indestructible_counter_survives_destruction(self, builder):
        game, bear = a_bear(builder, {"indestructible": 1})
        assert destroy(game.state, bear) is False
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_the_same_creature_without_it_dies(self, builder):
        game, bear = a_bear(builder)
        assert destroy(game.state, bear) is True
        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_a_flying_counter_cannot_be_blocked_from_the_ground(self, builder):
        """`combat.can_block` reads derived characteristics on both sides, so
        this is the evasion asking the keyword layer directly."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR], counters={"flying": 1})
            .battlefield(1, [BEAR])
            .build()
        )
        attacker = only_oid(game, BEAR, 0)
        blocker = only_oid(game, BEAR, 1)
        self.to_attackers(game)
        self.attack_with(game, attacker)
        assert not can_block(game.state, blocker, attacker, 1)

    def test_a_reach_counter_blocks_it_again(self, builder):
        """Two counters answering each other, which is what makes it a real
        keyword rather than a flag one rule happens to consult."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR], counters={"flying": 1})
            .battlefield(1, [BEAR], counters={"reach": 1})
            .build()
        )
        attacker = only_oid(game, BEAR, 0)
        blocker = only_oid(game, BEAR, 1)
        self.to_attackers(game)
        self.attack_with(game, attacker)
        assert can_block(game.state, blocker, attacker, 1)


class TestItOutlastsWhatPlacedIt:
    """The whole reason a counter rather than a `grant_keyword`."""

    def test_it_survives_the_cleanup_step(self, builder):
        game, bear = a_bear(builder)
        add_counters(game.state, bear, "vigilance", 1)
        turn = game.state.turn

        pass_until(game, lambda g: g.state.turn > turn)

        assert has_keyword(game.state, bear, "vigilance")

    def test_an_until_end_of_turn_grant_does_not(self, builder):
        """The contrast that makes the previous test mean something. This is
        `grant_keyword`'s default duration, and it is the whole of why the
        counter could not be written as one."""
        game, bear = a_bear(builder)
        grant_keyword(game.state, bear, "vigilance")
        assert has_keyword(game.state, bear, "vigilance")
        turn = game.state.turn

        pass_until(game, lambda g: g.state.turn > turn)

        assert not has_keyword(game.state, bear, "vigilance")

    def test_it_survives_the_permanent_that_placed_it_leaving(self, builder):
        """Gilraen dies the turn after; the creature she returned keeps both
        counters. A counter has no link back to its source, and this pins that
        it is not quietly acquiring one."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(0, [INDESTRUCTIBLE])
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        source = only_oid(game, INDESTRUCTIBLE, 0)
        add_counters(game.state, bear, "vigilance", 1, source=source)

        move_object(game.state, source, Zone.GRAVEYARD)

        assert has_keyword(game.state, bear, "vigilance")


class TestTakingItOff:
    def test_removing_the_last_counter_takes_the_keyword(self, builder):
        game, bear = a_bear(builder, {"vigilance": 1})
        remove_counters(game.state, bear, "vigilance", 1)
        assert not has_keyword(game.state, bear, "vigilance")
        assert counters_of(game, bear) == {}

    def test_one_of_two_leaves_the_keyword(self, builder):
        """The boundary. A keyword is not a count — two vigilance counters are
        not double vigilance, and one of them coming off changes nothing."""
        game, bear = a_bear(builder, {"vigilance": 2})
        remove_counters(game.state, bear, "vigilance", 1)
        assert has_keyword(game.state, bear, "vigilance")
        assert counters_of(game, bear) == {"vigilance": 1}

    def test_removing_more_than_are_there_is_clamped_and_still_ends_it(self, builder):
        game, bear = a_bear(builder, {"vigilance": 1})
        assert remove_counters(game.state, bear, "vigilance", 5) == 1
        assert not has_keyword(game.state, bear, "vigilance")

    def test_removing_a_different_kind_leaves_it_alone(self, builder):
        game, bear = a_bear(builder, {"vigilance": 1, "+1/+1": 1})
        remove_counters(game.state, bear, "+1/+1", 1)
        assert has_keyword(game.state, bear, "vigilance")

    def test_the_remove_counters_op_reaches_it(self, builder):
        """The DSL half of the same claim: `remove_counters` was written for
        `+1/+1` and takes a keyword kind with no change."""
        game, bear = a_bear(builder, {"lifelink": 1})
        run(
            game,
            op="remove_counters",
            counter="lifelink",
            amount={"const": 1},
            objects={"controller": "you", "types": ["Creature"]},
        )
        assert not has_keyword(game.state, bear, "lifelink")


class TestTheOtherCounterOps:
    """What `grant_keyword` could not be seen by, and this is."""

    def test_counters_on_reads_it(self, builder):
        game, bear = a_bear(builder, {"vigilance": 2})
        ctx = EffectContext(state=game.state, controller=0, source_oid=bear)
        value = evaluate_value(ctx, {"counters_on": {"counter": "vigilance"}})
        assert value == 2

    def test_proliferate_gives_a_second_one_and_the_keyword_is_unchanged(self, builder):
        """"Another counter of each kind already there" — a keyword counter is a
        kind, so it grows; having two of them is not two vigilances."""
        game, bear = a_bear(builder, {"vigilance": 1})
        run(game, op="proliferate")
        assert counters_of(game, bear) == {"vigilance": 2}
        assert has_keyword(game.state, bear, "vigilance")

    def test_proliferate_still_starts_nothing(self, builder):
        """It must not hand out keywords. Proliferate adds to a kind already
        there and never begins one, and a creature with no counters is the case
        where a keyword appearing would be most invisible."""
        game, bear = a_bear(builder)
        run(game, op="proliferate")
        assert counters_of(game, bear) == {}
        assert chars(game.state, bear).keywords == frozenset()

    def test_move_counters_carries_the_keyword_across(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR], counters={"vigilance": 1})
            .battlefield(0, [FLIER])
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        flier = only_oid(game, FLIER, 0)
        run(
            game,
            op="move_counters",
            counter="vigilance",
            **{"from": {"controller": "you", "subtypes": ["Bear"]}},
            objects={"controller": "you", "subtypes": ["Bird"]},
        )
        assert not has_keyword(game.state, bear, "vigilance")
        assert has_keyword(game.state, flier, "vigilance")

    def test_the_add_counters_op_places_one_from_a_card(self, builder):
        """End to end from JSON: the only route a real card takes."""
        game = (
            builder(players=2)
            .battlefield(0, ["plains"])
            .battlefield(0, [BEAR])
            .hand(0, ["t_vigilance_counter"])
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        game.apply(action_for_card(game, ActionKind.CAST, "t_vigilance_counter"))
        pass_until(game, lambda g: not g.state.stack)

        assert counters_of(game, bear) == {"vigilance": 1}
        assert has_keyword(game.state, bear, "vigilance")


class TestChangingZones:
    def test_it_arrives_live_when_a_permanent_enters_with_one(self, builder):
        """Gilraen's clause is "*return* that card … with a lifelink counter on
        it", so the counter is placed as part of entering. It must be readable
        by the time anything looks at the permanent."""
        game = builder(players=2).battlefield(0, ["plains", "plains"]).hand(
            0, ["t_arrives_with_lifelink"]
        ).build()
        game.apply(action_for_card(game, ActionKind.CAST, "t_arrives_with_lifelink"))
        pass_until(game, lambda g: not g.state.stack)

        oid = only_oid(game, "t_arrives_with_lifelink", 0)
        assert counters_of(game, oid) == {"lifelink": 1}
        assert has_keyword(game.state, oid, "lifelink")

    def test_leaving_the_battlefield_takes_the_counters_and_the_keyword(self, builder):
        """121.2: counters on a permanent cease to exist when it leaves. So the
        keyword goes with them, and a creature that comes back is the printed
        one again — which is *why* Gilraen's card says to return it with the
        counters rather than trusting them to travel."""
        game, bear = a_bear(builder, {"vigilance": 1})

        destroy(game.state, bear)
        assert counters_of(game, bear) == {}

        move_object(game.state, bear, Zone.BATTLEFIELD)

        assert counters_of(game, bear) == {}
        assert not has_keyword(game.state, bear, "vigilance")


class TestTheLoaderRefusesANearMiss:
    """The lookup is exact, so a near miss is an inert clause that loads clean.

    This is the one silent failure in an open vocabulary that is *detectable*:
    the misspelling normalises onto a keyword the engine implements. A kind that
    normalises onto nothing is somebody's charge counter and is left alone.
    """

    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_counter_giver",
                "name": "Test Counter Giver",
                "mana_cost": "{W}",
                "types": ["Sorcery"],
                "oracle_text": "Put a vigilance counter on target creature.",
                "targets": [
                    {"id": "t1", "kind": "permanent", "selector": {"types": ["Creature"]}}
                ],
                "spell_effects": [effect],
            }
        )

    def _add(self, counter: str) -> dict:
        return {
            "op": "add_counters",
            "counter": counter,
            "amount": {"const": 1},
            "objects": {"target": "t1"},
        }

    def test_the_exact_keyword_name_is_the_form(self):
        compile_card(self._card(self._add("vigilance")))

    def test_an_ordinary_counter_kind_is_untouched(self):
        compile_card(self._card(self._add("charge")))

    @pytest.mark.parametrize(
        "counter", ["Vigilance", "vigilance counter", "VIGILANCE", " vigilance "]
    )
    def test_a_near_miss_spelling_is_refused(self, counter):
        with pytest.raises(DslError, match="exact keyword name"):
            compile_card(self._card(self._add(counter)))

    def test_a_keyword_written_with_a_space_is_refused(self):
        """`first_strike`, not "first strike" — and the engine's spelling is the
        underscored one, so the printed English is the near miss."""
        with pytest.raises(DslError, match="'first_strike'"):
            compile_card(self._card(self._add("first strike")))

    def test_remove_counters_is_guarded_too(self):
        """A card that removes a counter nothing ever placed reads as printed
        and does nothing, which is the same failure pointed the other way."""
        with pytest.raises(DslError, match="exact keyword name"):
            compile_card(
                self._card(
                    {
                        "op": "remove_counters",
                        "counter": "Lifelink",
                        "amount": {"const": 1},
                        "objects": {"target": "t1"},
                    }
                )
            )

    def test_an_enters_with_counters_replacement_is_guarded(self):
        """The shape Gilraen's clause needs, and the one where a near miss is
        least visible: it is only read as a permanent enters."""
        with pytest.raises(DslError, match="exact keyword name"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_arrives_wrong",
                        "name": "Test Arrives Wrong",
                        "mana_cost": "{1}{W}",
                        "types": ["Creature"],
                        "subtypes": ["Soldier"],
                        "power": 2,
                        "toughness": 2,
                        "oracle_text": "This creature enters with a lifelink counter on it.",
                        "replacements": [
                            {
                                "event": "self_enters_with_counters",
                                "counter": "lifelink counter",
                                "amount": 1,
                            }
                        ],
                    }
                )
            )

    def test_a_static_condition_reading_one_is_guarded(self):
        """"As long as it has an indestructible counter on it" — read off the
        source's own dict by exact key, so a near miss switches the static off
        for ever rather than failing to load."""
        with pytest.raises(DslError, match="exact keyword name"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_static_reader",
                        "name": "Test Static Reader",
                        "mana_cost": "{1}{W}",
                        "types": ["Creature"],
                        "subtypes": ["Soldier"],
                        "power": 2,
                        "toughness": 2,
                        "oracle_text": "As long as this creature has an indestructible "
                        "counter on it, it gets +1/+1.",
                        "abilities": [
                            {
                                "kind": "static",
                                "text": "As long as this creature has an indestructible "
                                "counter on it, it gets +1/+1.",
                                "effect": "buff",
                                "affects": {"self_only": True},
                                "power": {"const": 1},
                                "toughness": {"const": 1},
                                "condition": {
                                    "counters": {"counter": "Indestructible", "amount": 1}
                                },
                            }
                        ],
                    }
                )
            )

    def test_a_counter_placed_trigger_filter_is_guarded(self):
        with pytest.raises(DslError, match="exact keyword name"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_trigger_reader",
                        "name": "Test Trigger Reader",
                        "mana_cost": "{1}{W}",
                        "types": ["Creature"],
                        "subtypes": ["Soldier"],
                        "power": 2,
                        "toughness": 2,
                        "oracle_text": "Whenever a vigilance counter is put on this "
                        "creature, you gain 1 life.",
                        "abilities": [
                            {
                                "kind": "triggered",
                                "text": "Whenever a vigilance counter is put on this "
                                "creature, you gain 1 life.",
                                "trigger": {
                                    "event": "counter_placed",
                                    "counter": "vigilance counter",
                                },
                                "effects": [
                                    {
                                        "op": "gain_life",
                                        "player": "you",
                                        "amount": {"const": 1},
                                    }
                                ],
                            }
                        ],
                    }
                )
            )
