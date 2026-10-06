"""Curiosity: "Whenever enchanted creature deals damage to an opponent…".

Rule 120.1 lets damage be dealt to a player, and says nothing about how it got
there; 510.2 makes combat damage one occasion of it rather than a different
kind of thing. So "deals damage to a player" is the broad claim and "deals
*combat* damage to a player" is a narrowing of it, and the engine had only the
narrow one: `primitives.damage_player` fires COMBAT_DAMAGE_TO_PLAYER inside
``if is_combat``, so a pinger, a Fireball, a fight or a triggered burn spell
under Curiosity drew nothing at all.

Substituting the combat trigger is not a weaker card, it is a different one --
Curiosity, Ophidian Eye and Tandem Lookout are all played precisely for the
noncombat half, on a creature that taps to ping rather than one that attacks.
So the noncombat half is what most of this file is about, and
`TestTheCombatOnlyTriggerIsNotASubstitute` asserts the difference rather than
leaving it to the docstring.

The event needed no new type. DAMAGE_DEALT has carried every player hit since
damage existed, with ``to="player"`` telling it apart from the permanent half
that `dealt_damage` already takes. What it lacked was a name, a **subject** --
the dealing permanent, so an Aura's ``filter: {"attached": true}`` and a
granted ability's ``source: "self"`` have something to point at -- and the two
payload keys a ``controller``/``defending`` clause is compared against.

`life_lost` is the near miss on the other side and is refused by
`TestInfectStillFiresIt`: an infect hit deals damage and costs no life, so a
trigger hung on the life total is silent for exactly the creature the card is
best on.

Witnesses: Curiosity and Ophidian Eye (the Aura shape, reached through
`attached`), and Tandem Lookout (the same trigger reached through a static
`grant_ability`, where the subject must resolve against the creature that was
granted the ability rather than the one that granted it).
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.primitives import attach, damage_permanent, damage_player
from automtg.engine.structs import DamageShield, TargetRef
from tests.conftest import _default_answer, find_action, only_oid, pass_until

EYE = "t_curious_eye"  # Aura: "whenever enchanted creature deals damage to an opponent, draw"
COMBAT_EYE = "t_combat_only_eye"  # the same Aura, on `deals_combat_damage_to_player`
LOOKOUT = "t_lookout"  # grants the trigger to itself and its partner
PINGER = "t_pinger"  # "{T}: deals 1 damage to target player"
BEAR = "t_bear"  # 2/2 vanilla
INFECTER = "t_infecter"  # 2/2 with infect


def board(builder, *, aura: str = EYE, host: str = BEAR, players: int = 2, host_pid: int = 0):
    """``aura`` attached to ``host``, frozen in a main phase.

    Attached in place rather than cast: the Aura's own resolution is
    `test_attached`'s subject, and what this file is about is what happens
    *afterwards*, once the link exists.
    """
    b = (
        builder(players=players)
        .battlefield(0, [aura])
        .battlefield(host_pid, [host])
        .library(0, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
    )
    game = b.build(advance=False)
    eye = only_oid(game, aura, 0)
    creature = only_oid(game, host, host_pid)
    # Attached before the game is advanced, and that ordering is not
    # incidental: an Aura attached to nothing is binned by a state-based
    # action the moment the engine looks, so a board built the usual way
    # loses the Aura before the first test line runs.
    attach(game.state, eye, creature)
    game._advance()
    return game, eye, creature


def settle(game, limit: int = 40) -> None:
    """Resolve whatever the trigger put on the stack."""
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the trigger never resolved")


def drawn(game, before: int, pid: int = 0) -> int:
    return len(game.state.players[pid].hand) - before


def hand(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


class TestNoncombatDamageFiresIt:
    """The half of the mechanic that did not exist before."""

    def test_a_ping_at_an_opponent_draws_a_card(self, builder):
        game, _, creature = board(builder)
        before = hand(game)
        damage_player(game.state, 1, 1, creature)
        settle(game)
        assert drawn(game, before) == 1

    def test_it_works_through_a_real_activated_ability(self, builder):
        """The whole path, not the primitive: an opponent-targeting ping from
        the enchanted creature's own printed ability."""
        game, _, pinger = board(builder, host=PINGER)
        before = hand(game)
        game.apply(
            find_action(
                game, ActionKind.ACTIVATE, source=pinger, targets=(TargetRef.player(1),)
            )
        )
        settle(game)
        assert drawn(game, before) == 1
        assert game.state.players[1].life == 39, "the ping landed, too"

    def test_it_fires_once_per_damage_event_not_once_per_point(self, builder):
        """Rule 120.3: damage is dealt in one event, however much of it there
        is. A Fireball for five under Curiosity draws one card."""
        game, _, creature = board(builder)
        before = hand(game)
        damage_player(game.state, 1, 5, creature)
        settle(game)
        assert drawn(game, before) == 1

    def test_two_separate_hits_fire_twice(self, builder):
        game, _, creature = board(builder)
        before = hand(game)
        damage_player(game.state, 1, 1, creature)
        settle(game)
        damage_player(game.state, 1, 1, creature)
        settle(game)
        assert drawn(game, before) == 2

    def test_zero_damage_is_no_damage(self, builder):
        """The boundary: `damage_player` returns early on a non-positive
        amount, so nothing is dealt and nothing may fire."""
        game, _, creature = board(builder)
        before = hand(game)
        damage_player(game.state, 1, 0, creature)
        settle(game)
        assert drawn(game, before) == 0

    def test_prevented_damage_fires_nothing(self, builder):
        """Prevented damage was never dealt (615.1), so there is no event to
        hang the draw on -- the shield is checked above the DAMAGE_DEALT fire."""
        game, _, creature = board(builder)
        game.state.damage_shields.append(DamageShield(player=1))
        before = hand(game)
        assert damage_player(game.state, 1, 3, creature) == 0
        settle(game)
        assert drawn(game, before) == 0


class TestCombatDamageFiresItToo:
    """"Deals damage" is the broad claim, so combat damage is inside it."""

    def test_connecting_in_combat_draws_a_card(self, builder):
        game, _, bear = board(builder)
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        before = hand(game)
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=bear, targets=(TargetRef.player(1),)
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        for _ in range(60):
            if game.over or int(game.state.step) > int(Step.COMBAT_DAMAGE):
                break
            decision = game.pending()
            if decision is None:
                game._advance()
                continue
            game.apply(_default_answer(game, decision))
        settle(game)
        assert drawn(game, before) == 1, "two damage got through; one card"


class TestTheCombatOnlyTriggerIsNotASubstitute:
    """The counterfactual, asserted rather than argued.

    Both Auras are on the board and on the same creature, so the one difference
    between the two runs is which trigger the card is written on.
    """

    def test_the_combat_only_aura_sleeps_through_a_ping(self, builder):
        game, _, creature = board(builder, aura=COMBAT_EYE)
        before = hand(game)
        damage_player(game.state, 1, 1, creature)
        settle(game)
        assert drawn(game, before) == 0, (
            "`deals_combat_damage_to_player` is combat-only by construction"
        )

    def test_and_this_one_does_not(self, builder):
        game, _, creature = board(builder)
        before = hand(game)
        damage_player(game.state, 1, 1, creature)
        settle(game)
        assert drawn(game, before) == 1


class TestInfectStillFiresIt:
    """Why the trigger is hung on the damage and not on the life total.

    An infect hit deals damage (702.90c) and costs no life at all, so
    `life_lost` -- the other near miss the gap records named -- is silent for
    exactly the creature Curiosity is best on.
    """

    def test_poison_counters_still_count_as_damage(self, builder):
        game, _, infecter = board(builder, host=INFECTER)
        before = hand(game)
        damage_player(game.state, 1, 2, infecter)
        settle(game)
        assert game.state.players[1].life == 40, "infect costs no life"
        assert game.state.players[1].poison == 2
        assert drawn(game, before) == 1


class TestWhoDealtItAndWhoTookIt:
    def test_damage_from_an_unenchanted_creature_does_nothing(self, builder):
        """`filter: {"attached": true}` is what "enchanted creature" means."""
        game = (
            builder(players=2)
            .battlefield(0, [EYE, BEAR, PINGER])
            .library(0, ["forest"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        eye = only_oid(game, EYE, 0)
        attach(game.state, eye, only_oid(game, BEAR, 0))
        before = hand(game)
        damage_player(game.state, 1, 1, only_oid(game, PINGER, 0))
        settle(game)
        assert drawn(game, before) == 0

    def test_damage_to_a_permanent_does_nothing(self, builder):
        """The other half of DAMAGE_DEALT, which `dealt_damage` takes.

        Without the scoping, a Shock from the enchanted creature at a Bear would
        draw a card off a trigger whose printed line says "to an opponent".
        """
        game = (
            builder(players=2)
            .battlefield(0, [EYE, BEAR])
            .battlefield(1, [BEAR])
            .library(0, ["forest"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        eye, mine = only_oid(game, EYE, 0), only_oid(game, BEAR, 0)
        attach(game.state, eye, mine)
        before = hand(game)
        damage_permanent(game.state, only_oid(game, BEAR, 1), 2, mine)
        settle(game)
        assert drawn(game, before) == 0

    def test_damage_dealt_to_you_does_not_fire_an_opponent_clause(self, builder):
        """"…to **an opponent**". You are not your own opponent, and a creature
        you control can damage you -- a fight gone wrong, a redirection."""
        game, _, creature = board(builder)
        before = hand(game)
        damage_player(game.state, 0, 1, creature)
        settle(game)
        assert drawn(game, before) == 0

    def test_the_opponent_is_the_auras_controller_s_opponent(self, builder):
        """Curiosity may enchant a creature its controller does not control.

        Three seats, because two hide the difference: the Aura is player 0's,
        the creature is player 1's, and it hits player 2. "An opponent" is asked
        of the player who controls the *ability*, so this draws -- and the same
        creature hitting player 0 does not.
        """
        game, _, creature = board(builder, players=3, host_pid=1)
        before = hand(game)
        damage_player(game.state, 2, 1, creature)
        settle(game)
        assert drawn(game, before) == 1

        damage_player(game.state, 0, 1, creature)
        settle(game)
        assert drawn(game, before) == 1, "player 0 is not player 0's opponent"


class TestTheGrantedCopy:
    """Tandem Lookout: the same trigger reached through `grant_ability`.

    The subject has to resolve against the creature that was **granted** the
    ability, not the one that granted it, or the pair-a-pinger line -- the whole
    reason the card is played -- draws on the wrong creature's damage.
    """

    def pair(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [LOOKOUT, BEAR])
            .library(0, ["forest"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        lookout, bear = only_oid(game, LOOKOUT, 0), only_oid(game, BEAR, 0)
        game.state.objects[lookout].paired_with = bear
        game.state.objects[bear].paired_with = lookout
        game.state.bump_chars()
        return game, lookout, bear

    def test_the_partner_s_damage_draws(self, builder):
        game, _, bear = self.pair(builder)
        before = hand(game)
        damage_player(game.state, 1, 1, bear)
        settle(game)
        assert drawn(game, before) == 1, "the granted ability is the partner's own"

    def test_the_granter_s_own_damage_draws_too(self, builder):
        """"…**each of those creatures** has…" -- both halves of the pair."""
        game, lookout, _ = self.pair(builder)
        before = hand(game)
        damage_player(game.state, 1, 1, lookout)
        settle(game)
        assert drawn(game, before) == 1

    def test_an_unpaired_creature_has_nothing(self, builder):
        """The static's "as long as" gate. Breaking the pair takes the ability
        away, so a Bear that is nobody's partner draws nothing."""
        game, lookout, bear = self.pair(builder)
        game.state.objects[lookout].paired_with = None
        game.state.objects[bear].paired_with = None
        game.state.bump_chars()
        before = hand(game)
        damage_player(game.state, 1, 1, bear)
        settle(game)
        assert drawn(game, before) == 0


class TestTheLoaderKnowsIt:
    def test_the_event_name_is_accepted(self, registry):
        card = registry.get(EYE)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger is not None
        assert ability.trigger.event == "deals_damage_to_player"
        assert ability.trigger.defending == "opponent"

    def test_defending_is_still_refused_where_no_defender_exists(self):
        """The `DEFENDING_TRIGGERS` entry is an addition, not a loosening: an
        event with no defending player on it still rejects the clause, because
        a `defending` clause it cannot answer matches nothing, for ever and
        silently."""
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(_card_with_trigger({
                "event": "dies",
                "source": "self",
                "defending": "opponent",
            })))

    def test_a_near_miss_spelling_is_refused(self):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(_card_with_trigger({
                "event": "deals_damage_to_a_player",
                "source": "self",
            })))


def _card_with_trigger(trigger: dict) -> dict:
    return {
        "id": "bogus",
        "name": "Bogus",
        "oracle_text": "x",
        "mana_cost": "{G}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "triggered",
                "text": "x",
                "trigger": trigger,
                "effects": [{"op": "noop"}],
            }
        ],
    }
