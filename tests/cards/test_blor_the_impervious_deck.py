"""The Blor the Impervious deck, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card **once**, in one
fixed sandbox, and reads the board. Three of its documented limits bite most of
this deck:

- **It never activates an ability.** The Mycosynth Gardens' copy ability,
  Excalibur's equip and The Irencrag's mana ability are the whole point of those
  cards, and the harness stops before any of them.
- **A trigger that never fires cannot be asserted.** Nothing in that position
  attacks, mutates, or plays a second permanent, so Tanuki Transplanter, Gemrazer
  and The Irencrag all have honest expectations of "nothing happened".
- **A static that changes a later spell's price is invisible.** The sandbox casts
  one card and stops, so Excalibur's and Strong Back's discounts are measured
  against a board that never pays them.

So the authoring expectations are floors, and these are the observations. Each
class is one card and asserts the printed sentence the gate could not reach --
including, in each case, the **near miss**: the reading that would be wrong if
the card were mis-written.
"""

from __future__ import annotations

import pytest

from automtg.cards.registry import default_registry
from automtg.engine.characteristics import abilities_of, chars, protection_from
from automtg.engine.costs import (
    ability_mana,
    activate_mana_ability,
    available_mana,
    cost_reduction,
)
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.mana import SYMBOL_INDEX
from automtg.engine.player_statics import player_cant_cast_spells
from automtg.engine.primitives import attach, damage_permanent, damage_player
from tests.conftest import (
    _default_answer,
    count_on_battlefield,
    oids_of,
    only_oid,
    pass_until,
)

GREEN = SYMBOL_INDEX["G"]


def board(builder, mine=(), theirs=(), lands=6, hand=(), attachments=()):
    """A board, with ``attachments`` hooked up before the first advance.

    An Aura attached to nothing is put into its owner's graveyard by the
    state-based actions, and `build(advance=True)` runs them -- so an Aura this
    file wants on the battlefield has to find its host first. `attach` is the
    same primitive the Aura's own resolution calls.

    Both seats hold a spare Forest, and it is load bearing rather than scenery.
    With no play available to anybody the engine's auto-pass runs straight out
    of the main phase inside one `_advance`, and a position built to activate an
    ability then opens on the declare-attackers decision instead of on priority
    -- so the ability is either missing from `legal_actions` or resolves in a
    window it would never really resolve in, and passing afterwards rolls the
    turn far enough to draw a card that the test then blames on the card. A land
    in hand is the cheapest thing that makes a seat stop.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * lands)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, [*hand, "forest"])
        .hand(1, ["forest"])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    for aura, host in attachments:
        assert attach(game.state, only_oid(game, aura), only_oid(game, host))
    game.state.bump_chars()
    game._advance()
    return game


def cast(game, card_id: str, *, accept: bool = False):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    settle(game, accept=accept)


def settle(game, *, accept: bool = False, limit: int = 400) -> None:
    """Let the stack empty. ``accept`` says yes to the "you may" halves.

    `pass_until`'s default answer is the passive one, which declines every
    `MAY` -- correct for a test that only wants the board to settle, and the
    wrong answer for a card whose whole printed sentence is behind the prompt.
    """
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if accept and decision.kind is DecisionKind.MAY:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
            continue
        # Priority with nothing waiting is the end. The emptiness of the stack
        # is *not* on its own: a triggered ability that asks its question
        # before resolving leaves the stack and the trigger queue both empty
        # while its decision is still pending, and a loop that stopped there
        # would answer nothing and report that the card did nothing.
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def equip(game, equipment: str, creature: str, pid: int = 0) -> None:
    """Attach an Equipment where its own equip ability would put it."""
    assert attach(game.state, only_oid(game, equipment), only_oid(game, creature, pid=pid))
    game.state.bump_chars()


def swing(game, attacker: str, defender: int = 1, *, accept: bool = False) -> None:
    """Declare ``attacker`` as an attacker and close the declaration."""
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
    )
    oid = only_oid(game, attacker)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER
            and a.source == oid
            and any(t.kind == "player" and t.id == defender for t in a.targets)
        )
    )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    settle(game, accept=accept)


def connect(game, dealer: str, amount: int = 3, defender: int = 1, *, accept: bool = False):
    """``dealer`` deals combat damage to a player -- the saboteur trigger.

    `damage_player` rather than a real swing, for the reason
    `test_combat_damage_to_planeswalker.py` gives: the event is what the card
    listens to, and driving it directly keeps the position to the two permanents
    the sentence is about.
    """
    damage_player(game.state, defender, amount, only_oid(game, dealer, pid=0), is_combat=True)
    settle(game, accept=accept)


def activations(game, oid: int, index: int | None = None) -> list:
    """The activations of ``oid`` currently legal, optionally one ability of it."""
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and a.source == oid
        and (index is None or a.ability_index == index)
    ]


def tap_for_mana(game, card_id: str, pid: int = 0, index: int | None = None) -> list[int]:
    """Tap ``card_id`` for mana and return the pool it filled.

    A mana ability uses no stack and answers no question (605.3a), so it is
    driven directly rather than through `legal_actions` -- the same shape
    `test_add_mana_on_tap.py` uses, and the only shape available: an ability
    whose cost is only {T} belongs to the payment solver and legality never
    offers it as a row.

    ``index`` defaults to the first mana ability rather than to zero, because
    an ability list counts triggered abilities too -- Talon Gates of Madara
    prints its enters trigger first, so its {T} is ability 1.
    """
    oid = oids_of(game, card_id, pid)[0]
    if index is None:
        index = next(
            a.index for a in abilities_of(game.state, oid) if getattr(a, "is_mana_ability", False)
        )
    activate_mana_ability(game.state, oid, index, pid)
    return list(game.state.players[pid].mana_pool.amounts)


def settle_choosing(game, oid: int, *, limit: int = 400) -> None:
    """Settle, taking any answer that names ``oid`` when one is offered.

    "Up to one target creature" is declinable, and `_default_answer` declines
    everything it can -- so a test that wants the target chosen has to say so.
    """
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        aimed = [a for a in game.legal_actions() if any(t.id == oid for t in a.targets)]
        if aimed:
            game.apply(aimed[0])
            continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def settle_taking(game, def_id: str, *, limit: int = 400) -> None:
    """Settle, taking ``def_id`` whenever a choice offers it.

    A search is a `CHOOSE_OBJECTS` whose last option is the decline, and
    `_default_answer` prefers exactly that -- so a test that wants the card
    found has to name it. The zone is not checked: the card being offered at
    all is the search having reached it.
    """
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        wanted = [
            a
            for a in game.legal_actions()
            if any(
                game.state.objects[t.id].def_id == def_id
                for t in a.targets
                if t.id in game.state.objects
            )
        ]
        if wanted:
            game.apply(wanted[0])
            continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def hand_ids(game, pid: int = 0) -> list[str]:
    return [game.state.objects[o].def_id for o in game.state.players[pid].hand]


def library_size(game, pid: int = 0) -> int:
    return len(game.state.players[pid].library)


class TestInquisitorsFlail:
    """"If equipped creature would deal combat damage, it deals double that
    damage instead." Gate 5 never reaches combat, so the doubling is unobserved
    there -- the card enters and the board looks identical either way."""

    def position(self, builder):
        game = board(
            builder, mine=["inquisitor_s_flail", "grizzly_bears"], theirs=["grizzly_bears"]
        )
        assert attach(
            game.state,
            only_oid(game, "inquisitor_s_flail"),
            only_oid(game, "grizzly_bears", pid=0),
        )
        game.state.bump_chars()
        return game

    def test_the_equipped_creature_hits_for_double(self, builder):
        game = self.position(builder)
        dealt = damage_permanent(
            game.state,
            only_oid(game, "grizzly_bears", pid=1),
            2,
            only_oid(game, "grizzly_bears", pid=0),
            is_combat=True,
        )
        assert dealt == 4

    def test_but_not_outside_combat(self, builder):
        """The near miss. The card says "combat damage" and a Flail that
        doubled a burn spell would be a different card."""
        game = self.position(builder)
        dealt = damage_permanent(
            game.state,
            only_oid(game, "grizzly_bears", pid=1),
            2,
            only_oid(game, "grizzly_bears", pid=0),
            is_combat=False,
        )
        assert dealt == 2


class TestExcaliburSwordOfEden:
    """"This spell costs {X} less to cast, where X is the total mana value of
    historic permanents you control." A price, which the behaviour gate cannot
    see: it casts the card and reads the board."""

    def test_an_empty_board_pays_the_printed_twelve(self, builder):
        game = board(builder, lands=0)
        card = default_registry().registry.get("excalibur_sword_of_eden")
        assert cost_reduction(game.state, 0, card) == 0

    def test_historic_permanents_pay_for_it(self, builder):
        """A Sol Ring is an artifact (2), Urza's Saga a Saga land (0), and the
        commander a legendary creature -- three different halves of "historic",
        which is the disjunction the card needed."""
        game = board(builder, mine=["sol_ring", "urza_s_saga", "blor_the_impervious"], lands=0)
        card = default_registry().registry.get("excalibur_sword_of_eden")
        assert cost_reduction(game.state, 0, card) > 0

    def test_a_forest_pays_nothing(self, builder):
        """The near miss: a Forest is a permanent you control and is not
        historic, so a reduction counting permanents rather than historic ones
        would discount here."""
        game = board(builder, lands=5)
        card = default_registry().registry.get("excalibur_sword_of_eden")
        assert cost_reduction(game.state, 0, card) == 0


class TestStrongBack:
    """"Equip abilities you activate that target enchanted creature cost {3}
    less to activate." Two prices and an aim, none of which gate 5 reaches."""

    def position(self, builder):
        return board(
            builder,
            mine=["strong_back", "commander_s_plate", "grizzly_bears", "llanowar_elves"],
            attachments=[("strong_back", "grizzly_bears")],
        )

    def equip_price(self, game, at: str) -> int:
        oid = only_oid(game, "commander_s_plate")
        ability = next(
            a for a in abilities_of(game.state, oid) if getattr(a, "is_equip", False)
        )
        wanted = only_oid(game, at)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and a.source == oid
            and any(r.id == wanted for r in a.targets)
        )
        return ability_mana(
            game.state, 0, ability.cost, 0, oid, ability=ability, targets=action.targets
        ).generic

    def test_equipping_the_enchanted_creature_is_cheaper(self, builder):
        game = self.position(builder)
        assert self.equip_price(game, "grizzly_bears") < self.equip_price(
            game, "llanowar_elves"
        )

    def test_the_enchanted_creature_grows_with_what_is_on_it(self, builder):
        """"Enchanted creature gets +2/+2 for each Aura and Equipment attached
        to it." Strong Back counts itself, so a 2/2 bear is already a 4/4."""
        game = self.position(builder)
        assert chars(game.state, only_oid(game, "grizzly_bears")).power == 4


class TestNaturalize:
    """A bug this deck's work found in a card it does not contain.

    "Destroy target artifact **or enchantment**" shipped able to target only
    artifacts: the selector said `types: ["Artifact"]`, which is an AND over one
    type rather than the printed or. The card loaded, played, and quietly did
    half of what it says -- the failure mode no gate can see, because targeting
    fewer things is never an error.

    `any_types` is the spelling the disjunction needs, and Loran of the Third
    Path has used it for the same printed words all along.
    """

    def test_it_can_target_an_enchantment(self, builder):
        game = board(builder, theirs=["sylvan_library"], hand=["naturalize"])
        wanted = only_oid(game, "sylvan_library")
        aims = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "naturalize"
            and any(r.id == wanted for r in a.targets)
        ]
        assert aims, "an enchantment is half of what the card says it destroys"

    def test_it_still_targets_an_artifact(self, builder):
        """The control: widening the filter must not have swapped one half of
        the sentence for the other."""
        game = board(builder, theirs=["sol_ring"], hand=["naturalize"])
        wanted = only_oid(game, "sol_ring")
        aims = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "naturalize"
            and any(r.id == wanted for r in a.targets)
        ]
        assert aims

    def test_it_does_not_target_a_creature(self, builder):
        """The near miss. `any_types` is an or over the two named types and not
        a licence to hit anything."""
        game = board(builder, theirs=["grizzly_bears"], hand=["naturalize"])
        wanted = only_oid(game, "grizzly_bears")
        aims = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "naturalize"
            and any(r.id == wanted for r in a.targets)
        ]
        assert not aims


class TestAdaptiveOmnitool:
    """"Equipped creature gets +1/+1 for each artifact you control" and
    "whenever equipped creature attacks, look at the top six." A count and an
    attack trigger: the gate casts the Omnitool onto an empty board and nothing
    it could count is there, and nothing attacks afterwards."""

    def position(self, builder, theirs=()):
        game = board(
            builder, mine=["adaptive_omnitool", "sol_ring", "grizzly_bears"], theirs=list(theirs)
        )
        equip(game, "adaptive_omnitool", "grizzly_bears")
        return game

    def test_the_bonus_counts_every_artifact_you_control(self, builder):
        """The Omnitool counts itself and the Sol Ring, so a 2/2 bear is a 4/4."""
        game = self.position(builder)
        assert chars(game.state, only_oid(game, "grizzly_bears", pid=0)).power == 4

    def test_an_opponents_artifact_is_not_yours(self, builder):
        """The near miss: "you control" is half the sentence, and a count that
        read the whole battlefield would make this bear a 5/5."""
        game = board(
            builder, mine=["adaptive_omnitool", "sol_ring", "grizzly_bears"], theirs=["sol_ring"]
        )
        equip(game, "adaptive_omnitool", "grizzly_bears")
        assert chars(game.state, only_oid(game, "grizzly_bears", pid=0)).power == 4


class TestBloodforgedBattleAxe:
    """"Whenever equipped creature deals combat damage to a player, create a
    token that's a copy of this Equipment." The gate never reaches combat, so
    the copy is unobserved there."""

    def position(self, builder):
        game = board(builder, mine=["bloodforged_battle_axe", "grizzly_bears"])
        equip(game, "bloodforged_battle_axe", "grizzly_bears")
        return game

    def test_a_connecting_hit_copies_the_axe(self, builder):
        game = self.position(builder)
        connect(game, "grizzly_bears")
        assert count_on_battlefield(game, "bloodforged_battle_axe", 0) == 2

    def test_noncombat_damage_does_not(self, builder):
        """The near miss. The card says *combat* damage, and an Axe that copied
        itself off a drain spell would be a different card."""
        game = self.position(builder)
        damage_player(game.state, 1, 3, only_oid(game, "grizzly_bears", pid=0), is_combat=False)
        settle(game)
        assert count_on_battlefield(game, "bloodforged_battle_axe", 0) == 1


class TestBoneSabres:
    """"Whenever equipped creature attacks, put four +1/+1 counters on it." An
    attack trigger, and nothing in the gate's sandbox attacks."""

    def test_attacking_puts_four_counters_on_the_equipped_creature(self, builder):
        game = board(builder, mine=["bone_sabres", "grizzly_bears"])
        equip(game, "bone_sabres", "grizzly_bears")
        swing(game, "grizzly_bears")
        bear = only_oid(game, "grizzly_bears", pid=0)
        assert game.state.objects[bear].counters.get("+1/+1") == 4
        assert chars(game.state, bear).power == 6

    def test_an_unequipped_attacker_gets_nothing(self, builder):
        """The near miss: the trigger is scoped to the creature the Sabres are
        on, not to every creature you attack with."""
        game = board(builder, mine=["bone_sabres", "grizzly_bears", "llanowar_elves"])
        equip(game, "bone_sabres", "grizzly_bears")
        swing(game, "llanowar_elves")
        elves = only_oid(game, "llanowar_elves", pid=0)
        assert not game.state.objects[elves].counters.get("+1/+1")


class TestBusterSword:
    """"Whenever equipped creature deals combat damage to a player, draw a
    card, then you may cast a spell from your hand with mana value less than or
    equal to that damage." A saboteur trigger with a bound read off the damage,
    and the gate reaches neither half."""

    def position(self, builder, hand=()):
        game = board(builder, mine=["buster_sword", "grizzly_bears"], hand=list(hand))
        equip(game, "buster_sword", "grizzly_bears")
        return game

    def test_the_equipped_creature_gets_plus_three_two(self, builder):
        game = self.position(builder)
        stats = chars(game.state, only_oid(game, "grizzly_bears", pid=0))
        assert (stats.power, stats.toughness) == (5, 4)

    def test_a_connecting_hit_draws(self, builder):
        game = self.position(builder)
        before = library_size(game)
        connect(game, "grizzly_bears")
        assert library_size(game) == before - 1

    def test_noncombat_damage_draws_nothing(self, builder):
        """The near miss: the trigger reads "combat damage"."""
        game = self.position(builder)
        before = library_size(game)
        damage_player(game.state, 1, 3, only_oid(game, "grizzly_bears", pid=0), is_combat=False)
        settle(game)
        assert library_size(game) == before


class TestMaskOfMemory:
    """"Whenever equipped creature deals combat damage to a player, you may
    draw two cards. If you do, discard a card." Optional, so the passive answer
    the gate would give is "no" -- the printed sentence is behind the yes."""

    def position(self, builder):
        game = board(builder, mine=["mask_of_memory", "grizzly_bears"], hand=["forest"])
        equip(game, "mask_of_memory", "grizzly_bears")
        return game

    def test_saying_yes_draws_two_and_discards_one(self, builder):
        game = self.position(builder)
        before_library = library_size(game)
        before_hand = len(game.state.players[0].hand)
        connect(game, "grizzly_bears", accept=True)
        assert library_size(game) == before_library - 2
        assert len(game.state.players[0].hand) == before_hand + 1

    def test_saying_no_draws_nothing(self, builder):
        """The near miss. "You may" is the whole first clause, and a Mask that
        drew regardless would be a strictly better card."""
        game = self.position(builder)
        before = library_size(game)
        connect(game, "grizzly_bears")
        assert library_size(game) == before


class TestSwordOfFireAndIce:
    """"+2/+2 and protection from red and from blue", and a saboteur trigger
    that deals 2 and draws. The statics the gate can see; the trigger it
    cannot."""

    def position(self, builder):
        game = board(
            builder,
            mine=["sword_of_fire_and_ice", "grizzly_bears"],
            theirs=["grizzly_bears"],
        )
        equip(game, "sword_of_fire_and_ice", "grizzly_bears")
        return game

    def test_the_equipped_creature_is_protected_from_red_and_blue(self, builder):
        game = self.position(builder)
        assert protection_from(game.state, only_oid(game, "grizzly_bears", pid=0)) >= {"R", "U"}

    def test_it_is_not_protected_from_green(self, builder):
        """The near miss: two named colours, not all of them -- and this is a
        mono-green deck, where a Sword that blanked green would read as working."""
        game = self.position(builder)
        assert "G" not in protection_from(game.state, only_oid(game, "grizzly_bears", pid=0))

    def test_a_connecting_hit_draws_a_card(self, builder):
        game = self.position(builder)
        before = library_size(game)
        connect(game, "grizzly_bears", accept=True)
        assert library_size(game) == before - 1


class TestHammerOfNazahn:
    """"Whenever this or another Equipment you control enters, you may attach
    that Equipment to target creature you control." An enters trigger about a
    *later* permanent, which the gate's one-card sandbox cannot produce."""

    def test_the_equipped_creature_is_indestructible(self, builder):
        game = board(builder, mine=["hammer_of_nazahn", "grizzly_bears"])
        equip(game, "hammer_of_nazahn", "grizzly_bears")
        bear = only_oid(game, "grizzly_bears", pid=0)
        assert "indestructible" in chars(game.state, bear).keywords
        assert chars(game.state, bear).power == 4

    def test_a_later_equipment_attaches_itself_for_free(self, builder):
        """The sentence the gate cannot reach: the Hammer is already out, and a
        second Equipment entering finds the creature without its equip cost."""
        game = board(
            builder, mine=["hammer_of_nazahn", "grizzly_bears"], hand=["basilisk_collar"]
        )
        cast(game, "basilisk_collar", accept=True)
        collar = only_oid(game, "basilisk_collar", pid=0)
        assert game.state.objects[collar].attached_to == only_oid(game, "grizzly_bears", pid=0)


class TestNettlecyst:
    """Living weapon, and a count over two types. The germ the gate does see;
    the "and/or" in the count is the part that could be half-written."""

    def test_living_weapon_brings_its_own_creature(self, builder):
        game = board(builder, mine=[], hand=["nettlecyst"])
        cast(game, "nettlecyst")
        germ = only_oid(game, "germ_0_0_b", pid=0)
        cyst = only_oid(game, "nettlecyst", pid=0)
        assert game.state.objects[cyst].attached_to == germ
        # A 0/0 that lives only because the Equipment that made it is on it:
        # the count is at least the Nettlecyst itself.
        assert chars(game.state, germ).power >= 1

    def test_the_count_takes_artifacts_and_enchantments_both(self, builder):
        """"For each artifact **and/or** enchantment" is a disjunction. A
        Nettlecyst counting only artifacts is the near miss, and in this deck --
        full of both -- it would still look like it worked."""
        game = board(
            builder,
            mine=["nettlecyst", "grizzly_bears", "sol_ring", "keen_sense"],
            attachments=[("keen_sense", "grizzly_bears")],
        )
        equip(game, "nettlecyst", "grizzly_bears")
        # Nettlecyst, Sol Ring, Keen Sense -- two artifacts and one enchantment.
        assert chars(game.state, only_oid(game, "grizzly_bears", pid=0)).power == 5


class TestStaffOfTitania:
    """"+X/+X where X is the number of Forests you control", and a token on
    attack. The deck runs 36 lands, so the count is the card."""

    def position(self, builder):
        game = board(builder, mine=["staff_of_titania", "grizzly_bears"], lands=4)
        equip(game, "staff_of_titania", "grizzly_bears")
        return game

    def test_the_bonus_counts_forests(self, builder):
        game = self.position(builder)
        assert chars(game.state, only_oid(game, "grizzly_bears", pid=0)).power == 6

    def test_attacking_makes_a_forest_dryad(self, builder):
        game = self.position(builder)
        before = count_on_battlefield(game, "forest_dryad_1_1_g_land", 0)
        swing(game, "grizzly_bears")
        assert count_on_battlefield(game, "forest_dryad_1_1_g_land", 0) == before + 1


class TestPowerFist:
    """"Equipped creature has trample and 'whenever this creature deals combat
    damage to a player, put that many +1/+1 counters on it.'" A granted
    ability, so the trigger has to survive being handed to another permanent."""

    def position(self, builder):
        game = board(builder, mine=["power_fist", "grizzly_bears"])
        equip(game, "power_fist", "grizzly_bears")
        return game

    def test_the_equipped_creature_tramples(self, builder):
        game = self.position(builder)
        assert "trample" in chars(game.state, only_oid(game, "grizzly_bears", pid=0)).keywords

    def test_a_connecting_hit_puts_that_many_counters_on_it(self, builder):
        game = self.position(builder)
        connect(game, "grizzly_bears", amount=3)
        bear = only_oid(game, "grizzly_bears", pid=0)
        assert game.state.objects[bear].counters.get("+1/+1") == 3

    def test_an_unequipped_creature_gets_none(self, builder):
        """The near miss: the ability is granted to the equipped creature, not
        printed on the Fist for everything you control."""
        game = board(builder, mine=["power_fist", "grizzly_bears", "llanowar_elves"])
        equip(game, "power_fist", "grizzly_bears")
        connect(game, "llanowar_elves", amount=3)
        elves = only_oid(game, "llanowar_elves", pid=0)
        assert not game.state.objects[elves].counters.get("+1/+1")


class TestBasiliskCollar:
    """"Equipped creature has deathtouch and lifelink." Two keywords, and the
    Collar is the deck's combo piece with every damage trigger in it."""

    def test_it_grants_both_halves(self, builder):
        game = board(builder, mine=["basilisk_collar", "grizzly_bears"])
        equip(game, "basilisk_collar", "grizzly_bears")
        granted = chars(game.state, only_oid(game, "grizzly_bears", pid=0)).keywords
        assert {"deathtouch", "lifelink"} <= set(granted)

    def test_an_unequipped_creature_has_neither(self, builder):
        """The near miss: `affects: {attached: true}` is the whole scope, and a
        Collar that granted them to everything would read as working here."""
        game = board(builder, mine=["basilisk_collar", "grizzly_bears", "llanowar_elves"])
        equip(game, "basilisk_collar", "grizzly_bears")
        granted = chars(game.state, only_oid(game, "llanowar_elves", pid=0)).keywords
        assert not {"deathtouch", "lifelink"} & set(granted)


class TestConquerorsFlail:
    """"+1/+1 for each color among permanents you control", and "your opponents
    can't cast spells during your turn". A count over colours and a lock, and
    the gate casts the Flail onto a board with neither."""

    def test_mono_green_pays_exactly_one(self, builder):
        """The deck is mono-green: one colour among permanents, so +1/+1. A
        Flail that counted permanents rather than colours would be enormous."""
        game = board(
            builder, mine=["conqueror_s_flail", "grizzly_bears", "llanowar_elves"], lands=6
        )
        equip(game, "conqueror_s_flail", "grizzly_bears")
        assert chars(game.state, only_oid(game, "grizzly_bears", pid=0)).power == 3

    def test_attached_it_locks_the_opponent_out_of_your_turn(self, builder):
        game = board(builder, mine=["conqueror_s_flail", "grizzly_bears"])
        equip(game, "conqueror_s_flail", "grizzly_bears")
        assert player_cant_cast_spells(game.state, 1)

    def test_unattached_it_locks_nobody(self, builder):
        """The near miss: "as long as this Equipment is attached to a creature"
        is a condition, not scenery."""
        game = board(builder, mine=["conqueror_s_flail", "grizzly_bears"])
        assert not player_cant_cast_spells(game.state, 1)

    def test_it_never_locks_you(self, builder):
        game = board(builder, mine=["conqueror_s_flail", "grizzly_bears"])
        equip(game, "conqueror_s_flail", "grizzly_bears")
        assert not player_cant_cast_spells(game.state, 0)


class TestTheManaDorks:
    """"{T}: Add {G}." Three copies of one sentence -- Elvish Mystic, Fyndhorn
    Elves, Llanowar Elves -- and gate 5 never activates an ability, so the
    deck's whole first turn was unobserved."""

    @pytest.mark.parametrize(
        "dork", ["elvish_mystic", "fyndhorn_elves", "llanowar_elves"]
    )
    def test_it_taps_for_one_green(self, builder, dork):
        game = board(builder, mine=[dork], lands=0)
        pool = tap_for_mana(game, dork)
        assert pool[GREEN] == 1
        assert sum(pool) == 1


class TestArborElf:
    """"{T}: Untap target Forest." Not a mana ability and not a Llanowar Elves:
    it untaps a land, which is why the deck runs Utopia Sprawl."""

    def position(self, builder):
        game = board(builder, mine=["arbor_elf"], lands=2)
        forest = oids_of(game, "forest", 0)[0]
        game.state.objects[forest].tapped = True
        return game, forest

    def test_it_untaps_a_tapped_forest(self, builder):
        game, forest = self.position(builder)
        elf = only_oid(game, "arbor_elf", pid=0)
        action = next(
            a
            for a in activations(game, elf)
            if any(t.id == forest for t in a.targets)
        )
        game.apply(action)
        settle(game)
        assert not game.state.objects[forest].tapped

    def test_it_will_not_untap_a_land_that_is_not_a_forest(self, builder):
        """The near miss. "Target Forest" is a subtype, and an Arbor Elf that
        untapped any land would be a different, much better card -- and in a
        deck of 36 lands it would look like it worked."""
        game = board(builder, mine=["arbor_elf", "strip_mine"], lands=1)
        mine = only_oid(game, "strip_mine", pid=0)
        game.state.objects[mine].tapped = True
        elf = only_oid(game, "arbor_elf", pid=0)
        assert not [a for a in activations(game, elf) if any(t.id == mine for t in a.targets)]


class TestSakuraTribeElder:
    """"Sacrifice this creature: Search your library for a basic land card, put
    that card onto the battlefield tapped, then shuffle." A sacrifice cost, so
    the gate -- which casts and stops -- never sees the ramp."""

    def test_sacrificing_it_fetches_a_basic_tapped(self, builder):
        game = board(builder, mine=["sakura_tribe_elder"], lands=0)
        elder = only_oid(game, "sakura_tribe_elder", pid=0)
        before = count_on_battlefield(game, "forest", 0)
        game.apply(activations(game, elder)[0])
        settle_taking(game, "forest")
        assert count_on_battlefield(game, "forest", 0) == before + 1
        assert not oids_of(game, "sakura_tribe_elder", 0), "it sacrifices itself to pay"

    def test_the_land_arrives_tapped(self, builder):
        """The near miss, and the whole reason the card is a fog rather than a
        ritual: an Elder that fetched untapped would ramp the turn it died."""
        game = board(builder, mine=["sakura_tribe_elder"], lands=0)
        elder = only_oid(game, "sakura_tribe_elder", pid=0)
        game.apply(activations(game, elder)[0])
        settle_taking(game, "forest")
        assert oids_of(game, "forest", 0), "nothing was fetched to look at"
        assert all(game.state.objects[o].tapped for o in oids_of(game, "forest", 0))


class TestBuriedRuin:
    """"{2}, {T}, Sacrifice this land: Return target artifact card from your
    graveyard to your hand." Three cost pieces and a graveyard target, none of
    which the behaviour gate reaches."""

    def position(self, builder, graveyard=("sol_ring",)):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["buried_ruin"])
            .graveyard(0, list(graveyard))
            .library(0, ["forest"] * 30)
            .library(1, ["forest"] * 30)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game

    def test_it_buys_an_artifact_back(self, builder):
        game = self.position(builder)
        ruin = only_oid(game, "buried_ruin", pid=0)
        game.apply(activations(game, ruin, index=1)[0])
        settle(game)
        assert "sol_ring" in hand_ids(game)

    def test_it_will_not_target_a_nonartifact(self, builder):
        """The near miss: "artifact card" is the filter, and this deck's
        graveyard is mostly lands and creatures."""
        game = self.position(builder, graveyard=("grizzly_bears",))
        ruin = only_oid(game, "buried_ruin", pid=0)
        assert not activations(game, ruin, index=1)


class TestStripMine:
    """"{T}, Sacrifice this land: Destroy target land." The gate puts it on the
    battlefield and stops; the ability is the card."""

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["strip_mine"])
            .battlefield(1, ["forest", "urza_s_saga"])
            .library(0, ["forest"] * 30)
            .library(1, ["forest"] * 30)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_it_destroys_a_land(self, builder):
        game = self.position(builder)
        mine = only_oid(game, "strip_mine", pid=0)
        saga = only_oid(game, "urza_s_saga", pid=1)
        action = next(
            a for a in activations(game, mine, index=1) if any(t.id == saga for t in a.targets)
        )
        game.apply(action)
        settle(game)
        assert not oids_of(game, "urza_s_saga", 1)
        assert not oids_of(game, "strip_mine", 0), "it sacrifices itself to pay"

    def test_it_is_not_restricted_to_nonbasics(self, builder):
        """The near miss, and it points the other way from the usual one:
        Wasteland says "nonbasic" and Strip Mine does not. A Strip Mine that
        spared basics would be the weaker card."""
        game = self.position(builder)
        mine = only_oid(game, "strip_mine", pid=0)
        basic = only_oid(game, "forest", pid=1)
        assert [a for a in activations(game, mine, index=1) if any(t.id == basic for t in a.targets)]


class TestFanaticOfRhonas:
    """"Ferocious -- {T}: Add {G}{G}{G}{G}. Activate only if you control a
    creature with power 4 or greater." A condition on an activation, which is
    legality rather than resolution and so invisible to the gate."""

    def test_without_a_four_power_creature_it_makes_one_mana(self, builder):
        """Read through `available_mana` rather than `legal_actions`: a mana
        ability whose cost is only {T} belongs to the payment solver and is
        never offered as a row, so the condition has to be asked where the
        solver asks it."""
        game = board(builder, mine=["fanatic_of_rhonas"], lands=0)
        assert available_mana(game.state, 0) == 1

    def test_with_one_it_makes_four(self, builder):
        game = board(builder, mine=["fanatic_of_rhonas", "t_five_five"], lands=0)
        assert available_mana(game.state, 0) == 4

    def test_the_four_power_creature_must_be_yours(self, builder):
        """The near miss: "you control a creature with power 4 or greater",
        and an opponent's fatty is the reading that would be wrong."""
        game = board(builder, mine=["fanatic_of_rhonas"], theirs=["t_five_five"], lands=0)
        assert available_mana(game.state, 0) == 1


class TestInventorsFair:
    """"Activate only if you control three or more artifacts", and an upkeep
    trigger with the same condition. Both counts, and the gate casts one card
    onto a board with nothing on it."""

    def position(self, builder, artifacts=()):
        return (
            builder(players=2)
            .battlefield(0, ["forest"] * 5 + ["inventors_fair", *artifacts])
            .library(0, ["forest"] * 30)
            .library(1, ["forest"] * 30)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_with_three_artifacts_the_tutor_is_offered(self, builder):
        game = self.position(builder, ["sol_ring", "basilisk_collar", "power_fist"])
        fair = only_oid(game, "inventors_fair", pid=0)
        assert activations(game, fair, index=2)

    def test_with_two_it_is_not(self, builder):
        """The near miss: "three or more" is a threshold, and the Fair itself
        is a land rather than an artifact, so it does not count toward it."""
        game = self.position(builder, ["sol_ring", "basilisk_collar"])
        fair = only_oid(game, "inventors_fair", pid=0)
        assert not activations(game, fair, index=2)


class TestTalonGatesOfMadara:
    """"When this land enters, up to one target creature phases out." An enters
    trigger with an optional target -- and the gate puts lands onto the
    battlefield rather than playing them, so nothing fired."""

    def play(self, builder, aim: bool):
        game = board(
            builder, mine=[], theirs=["grizzly_bears"], lands=0,
            hand=["talon_gates_of_madara"],
        )
        bear = only_oid(game, "grizzly_bears", pid=1)
        mark = len(game.state.events)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND
            and game.state.objects[a.source].def_id == "talon_gates_of_madara"
        )
        game.apply(action)
        if aim:
            settle_choosing(game, bear)
        else:
            # The decline is the option with no target on it, and it is not
            # what `_default_answer` reaches for: with no FINISH_DECLARATION
            # among the choices it takes the first, which is the creature.
            game.apply(next(a for a in game.legal_actions() if not a.targets))
            settle(game)
        return game, bear, mark

    def phasings(self, game, mark: int, bear: int, kind: str) -> list:
        return [
            e
            for e in game.state.events[mark:]
            if e.type == kind and e.data.get("oid") == bear
        ]

    def test_playing_it_phases_a_creature_out(self, builder):
        """Asserted on the event rather than the flag, and that is the rule
        rather than a convenience: the land drop uses up the turn's only play,
        so nothing anchors priority afterwards and the turn runs on to the
        opponent's untap step -- where a phased-out permanent correctly comes
        back. The flag is false by then; that the creature phased out at all is
        what the card says."""
        game, bear, mark = self.play(builder, aim=True)
        assert self.phasings(game, mark, bear, "phased_out")

    def test_it_comes_back_by_its_controllers_untap_step(self, builder):
        """702.26: a permanent phased out by a printed one-shot has no phasing
        keyword of its own, so it phases in and stays. Removal it is not."""
        game, bear, mark = self.play(builder, aim=True)
        assert self.phasings(game, mark, bear, "phased_in")
        assert bear in game.state.battlefield

    def test_up_to_one_may_be_none(self, builder):
        """The near miss: "up to one target" is declinable, and a Talon Gates
        that had to phase something out would be a liability in a deck whose
        own creatures are the only ones on the board half the time."""
        game, bear, mark = self.play(builder, aim=False)
        assert not self.phasings(game, mark, bear, "phased_out")

    def test_it_taps_for_colorless(self, builder):
        """The control: it is still a land, and its first ability is the one
        the mana base counts on."""
        game = board(builder, mine=["talon_gates_of_madara"], lands=0)
        pool = tap_for_mana(game, "talon_gates_of_madara")
        assert sum(pool) == 1


class TestEternalWitness:
    """"When this creature enters, you may return target card from your
    graveyard to your hand." An enters trigger reaching a zone the gate's
    sandbox leaves empty."""

    def test_it_buys_a_card_back(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 6)
            .graveyard(0, ["naturalize"])
            .hand(0, ["eternal_witness"])
            .library(0, ["forest"] * 30)
            .library(1, ["forest"] * 30)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast(game, "eternal_witness", accept=True)
        assert "naturalize" in hand_ids(game)

    def test_an_empty_graveyard_is_not_an_error(self, builder):
        """The near miss in the other direction: the card is still castable
        with nothing to return, and this deck casts it for the body often."""
        game = board(builder, mine=[], hand=["eternal_witness"], lands=6)
        cast(game, "eternal_witness", accept=True)
        assert count_on_battlefield(game, "eternal_witness", 0) == 1


class TestKeenSense:
    """"Whenever enchanted creature deals damage to an opponent, you may draw a
    card." Damage of any kind, not combat damage -- the one word separating this
    from every saboteur Equipment in the deck."""

    def position(self, builder):
        return board(
            builder,
            mine=["keen_sense", "grizzly_bears"],
            attachments=[("keen_sense", "grizzly_bears")],
        )

    def test_a_combat_hit_draws(self, builder):
        game = self.position(builder)
        before = library_size(game)
        connect(game, "grizzly_bears", accept=True)
        assert library_size(game) == before - 1

    def test_noncombat_damage_draws_too(self, builder):
        """The near miss, and it is the opposite of the Equipment's: Keen Sense
        says "deals damage", so an implementation that copied the saboteur
        trigger next to it would be too narrow."""
        game = self.position(builder)
        before = library_size(game)
        damage_player(game.state, 1, 2, only_oid(game, "grizzly_bears", pid=0), is_combat=False)
        settle(game, accept=True)
        assert library_size(game) == before - 1


class TestToskiBearerOfSecrets:
    """"Toski attacks each combat if able", and "whenever a creature you
    control deals combat damage to a player, draw a card". A compulsion and a
    team-wide trigger, neither reachable by casting one card and stopping."""

    def test_any_of_your_creatures_connecting_draws(self, builder):
        game = board(builder, mine=["toski_bearer_of_secrets", "grizzly_bears"])
        before = library_size(game)
        connect(game, "grizzly_bears")
        assert library_size(game) == before - 1

    def test_an_opponents_creature_connecting_does_not(self, builder):
        """The near miss: "a creature **you control**", and Toski is famous
        enough that a version drawing off everybody would look generous rather
        than wrong."""
        game = board(builder, mine=["toski_bearer_of_secrets"], theirs=["grizzly_bears"])
        before = library_size(game)
        damage_player(game.state, 0, 2, only_oid(game, "grizzly_bears", pid=1), is_combat=True)
        settle(game)
        assert library_size(game) == before


class TestBoseijuWhoEndures:
    """Channel: "{1}{G}, Discard this card: Destroy target artifact,
    enchantment, or nonbasic land an opponent controls. This ability costs {1}
    less for each legendary creature you control." An ability activated from
    *hand*, which is a zone the behaviour gate never activates from, plus a
    three-way disjunction and a scaling cost."""

    def position(self, builder, theirs=("urza_s_saga",), mine=()):
        return (
            builder(players=2)
            .battlefield(0, ["forest"] * 5 + list(mine))
            .battlefield(1, list(theirs))
            .hand(0, ["boseiju_who_endures", "forest"])
            .hand(1, ["forest"])
            .library(0, ["forest"] * 30)
            .library(1, ["forest"] * 30)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def channel(self, game, want: str, pid: int = 1):
        target = only_oid(game, want, pid=pid)
        return [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and any(t.id == target for t in a.targets)
        ]

    def test_it_destroys_an_opponents_nonbasic_land(self, builder):
        game = self.position(builder)
        game.apply(self.channel(game, "urza_s_saga")[0])
        settle(game)
        assert not oids_of(game, "urza_s_saga", 1)

    def test_it_reaches_an_artifact_and_an_enchantment_too(self, builder):
        """Three printed halves, and a selector written as an AND over the
        three types would match nothing at all."""
        game = self.position(builder, theirs=("sol_ring", "sylvan_library"))
        assert self.channel(game, "sol_ring")
        assert self.channel(game, "sylvan_library")

    def test_it_will_not_take_a_basic_land(self, builder):
        """The near miss: "nonbasic" is the word, and in a format of Forests a
        Boseiju that took basics would be a Strip Mine on every land."""
        game = self.position(builder, theirs=("forest",))
        assert not self.channel(game, "forest")

    def test_it_will_not_take_your_own_permanent(self, builder):
        """The other near miss: "an opponent controls"."""
        game = self.position(builder, mine=("sol_ring",))
        assert not self.channel(game, "sol_ring", pid=0)


class TestMosswortBridge:
    """Hideaway 4, and "{G}, {T}: You may play the exiled card without paying
    its mana cost if creatures you control have total power 10 or greater." The
    gate places lands rather than playing them, so the hideaway never fired."""

    def position(self, builder, mine=()):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 5 + list(mine))
            .hand(0, ["mosswort_bridge", "forest"])
            .hand(1, ["forest"])
            .library(0, ["forest"] * 30)
            .library(1, ["forest"] * 30)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND
            and game.state.objects[a.source].def_id == "mosswort_bridge"
        )
        game.apply(action)
        settle(game)
        return game

    def test_it_hides_a_card_away_as_it_enters(self, builder):
        game = self.position(builder)
        hidden = [
            o
            for o in game.state.objects.values()
            if o.zone is Zone.EXILE and o.owner == 0
        ]
        assert hidden, "hideaway 4 looks at four and exiles one"

    def test_the_payoff_waits_for_ten_power(self, builder):
        """The near miss: the condition is on the *ability*, and a Bridge that
        handed the card over for {G} would be one of the best lands ever
        printed."""
        game = self.position(builder)
        bridge = only_oid(game, "mosswort_bridge", pid=0)
        before = len(game.state.players[0].library)
        for action in activations(game, bridge):
            game.apply(action)
            settle(game)
            break
        assert len(game.state.players[0].library) == before


class TestSelvalaHeartOfTheWilds:
    """"Whenever another creature enters, its controller may draw a card if its
    power is greater than each other creature's power." A trigger about a later
    permanent, and a comparison the gate's one-card board cannot set up."""

    def test_a_bigger_creature_draws_for_its_controller(self, builder):
        game = board(
            builder,
            mine=["selvala_heart_of_the_wilds", "grizzly_bears"],
            hand=["t_five_five"],
        )
        before = library_size(game)
        cast(game, "t_five_five", accept=True)
        assert library_size(game) == before - 1

    def test_a_smaller_one_does_not(self, builder):
        """The near miss: "greater than **each other** creature's power" is a
        maximum, not a comparison with Selvala herself."""
        game = board(
            builder,
            mine=["selvala_heart_of_the_wilds", "t_five_five"],
            hand=["grizzly_bears"],
        )
        before = library_size(game)
        cast(game, "grizzly_bears", accept=True)
        assert library_size(game) == before

    def big_mana(self, builder, mine) -> int:
        """Activate Selvala's mana ability and return what reached the pool.

        Offered as a row rather than taken by the payment solver, because its
        cost is {G} and {T} rather than {T} alone -- so unlike the deck's
        Forests it is reachable through `legal_actions`.
        """
        game = board(builder, mine=["selvala_heart_of_the_wilds", *mine], lands=2)
        selvala = only_oid(game, "selvala_heart_of_the_wilds", pid=0)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == selvala
        )
        game.apply(action)
        settle(game)
        return game.state.players[0].mana_pool.total()

    def test_her_mana_scales_with_the_biggest_creature(self, builder):
        """"Add X mana ... where X is the greatest power among creatures you
        control." A 5/5 next to her makes five."""
        assert self.big_mana(builder, ["t_five_five"]) == 5

    def test_alone_she_makes_her_own_power(self, builder):
        """The near miss: "greatest power among creatures you control" includes
        her, so the floor is 2 rather than 0 -- and an X read off some other
        creature would make nothing at all here."""
        assert self.big_mana(builder, []) == 2


class TestLevelUp:
    """An Aura: "+1/+1 counter as it enters", and it grants the creature
    "whenever this creature attacks, double the number of +1/+1 counters on
    it." A granted attack trigger, two layers from anything the gate sees."""

    def position(self, builder):
        return board(
            builder,
            mine=["level_up", "grizzly_bears"],
            attachments=[("level_up", "grizzly_bears")],
        )

    def test_attacking_doubles_the_counters(self, builder):
        game = self.position(builder)
        bear = only_oid(game, "grizzly_bears", pid=0)
        game.state.objects[bear].counters["+1/+1"] = 3
        game.state.bump_chars()
        swing(game, "grizzly_bears")
        assert game.state.objects[bear].counters.get("+1/+1") == 6

    def test_a_creature_without_the_aura_keeps_its_counters(self, builder):
        """The near miss: the doubling is granted to the enchanted creature,
        not printed on the Aura for the team."""
        game = board(
            builder,
            mine=["level_up", "grizzly_bears", "llanowar_elves"],
            attachments=[("level_up", "grizzly_bears")],
        )
        elves = only_oid(game, "llanowar_elves", pid=0)
        game.state.objects[elves].counters["+1/+1"] = 3
        game.state.bump_chars()
        swing(game, "llanowar_elves")
        assert game.state.objects[elves].counters.get("+1/+1") == 3


class TestHuntersTalent:
    """A Class enchantment: an enters trigger that fights in all but name, and
    two levels bought later. Gate 5 casts it and reads the board, so neither
    the damage nor either level is observed."""

    def position(self, builder):
        return board(
            builder,
            mine=["grizzly_bears"],
            theirs=["grizzly_bears"],
            hand=["hunter_s_talent"],
        )

    def test_it_shoots_a_creature_for_your_creatures_power(self, builder):
        game = self.position(builder)
        theirs = only_oid(game, "grizzly_bears", pid=1)
        cast(game, "hunter_s_talent", accept=True)
        assert theirs not in game.state.battlefield, "a 2/2 dealt 2 is dead"

    def test_level_two_is_bought_not_given(self, builder):
        """The near miss: a Class enters at level 1, and its later abilities
        are behind a cost. A Talent that arrived at level 2 would be a
        different card."""
        game = self.position(builder)
        cast(game, "hunter_s_talent", accept=True)
        talent = only_oid(game, "hunter_s_talent", pid=0)
        assert game.state.objects[talent].class_level == 1
