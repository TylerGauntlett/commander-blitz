"""An Aura whose host is a **player**, and the lock that names no defender.

    Overencumbered — "Enchant opponent / When this Aura enters, enchanted
    opponent creates a Clue token, a Food token, and a Junk token. / At the
    beginning of combat on enchanted opponent's turn, that player may pay {1}
    for each artifact they control. If they don't, creatures can't attack this
    combat."

Rule 303.4a is the rule: "an Aura spell requires a target, which is defined by
its enchant ability" and that ability may name **a player**. 702.5b makes the
enchant line a restriction on what the Aura may ever be attached to, and 704.5n
is the state-based action that follows from both: an Aura attached to an
illegal object *or player*, or to nothing at all, is put into its owner's
graveyard.

The engine had the last of those three and neither of the first two, and the
result was not a card that played approximately right. `GameObject.attached_to`
is an oid, `stack._attach_aura` attached only on a `kind: "object"` target ref,
so Overencumbered resolved, enchanted nobody, and `sba` moved it to the
graveyard with cause `aura_unattached` before its own enters trigger could
resolve. The only assertion that passed about the shipped card was
``zone == "graveyard"``: three printed sentences, a mana cost, and no game
effect whatsoever.

`attached_to_player` is a second field rather than a second meaning for the
first, and that is forced. A player id and an oid are both `int`, so one field
holding either could not be read without a discriminator at every reader --
and there are seven of them, each meaning "the permanent I am on": the
characteristics layer, the `attached` selector, trigger filters, `_detach_all`,
phasing, bestow and the state-based action itself. A seat number arriving in
that field is an oid pointing at an unrelated object, silently and differently
in every game.

Four claims are worth pinning, and each is a way this could be quietly wrong:

1. The Aura **stays on the battlefield**, and the state-based action that bins a
   genuinely unattached Aura still bins one. Those are two different boards, and
   the second is the counterfactual asserted against below.
2. Its abilities can **name that player**. `enchanted_player` is read off the
   ability's own source -- the argument `attached`, `haunted_by` and cipher's
   `encoded_by` all make. Every other spelling is a different card:
   `{"target": …}` is refused at compile (an ability's targets are scoped to
   that ability) and would resolve to `[]`, which `op_may` reads as "nobody" and
   bills `ctx.controller` -- so the Aura's *controller* would pay the enchanted
   player's toll, which is the documented Rhystic Study failure; `each_opponent`
   is the near miss and taxes the whole table at a pod.
3. "At the beginning of combat on **enchanted opponent's** turn" needs no new
   trigger clause: `is_active_player` already takes a player spec, so the
   composition is `controller: "any"` plus that condition. `controller:
   "opponent"` is the near miss and fires on *every* opponent's combat.
4. "**Creatures can't attack this combat**" names no defender at all, so it
   reaches all three of 506.2's attack targets. `cant_attack_player` with
   `each_player` on both sides installs the right cross-product and deliberately
   exempts planeswalkers -- correctly, for the sentence it was built for -- so
   without `planeswalkers: true` a line printed "creatures can't attack" leaves
   every creature free to swing at a walker. That divergence follows the printed
   sentence, exactly as `cant_attack_you`'s and goad's do, and never a house
   rule about walkers.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import combat as combat_mod
from automtg.engine import sba
from automtg.engine.characteristics import _condition_met
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import attach, attach_to_player, restrict_attack
from tests.conftest import _default_answer, oids_of, only_oid

AURA = "t_encumber"  # the Overencumbered prototype -- all three sentences
ROBE = "t_seat_robe"  # "Enchant player / enchanted player loses 1 life…"
ON_CREATURE = "t_creature_aura"  # the counterfactual: the same clause, on a creature Aura
BEAR = "t_bear"
WALKER = "t_walker"  # loyalty 4
ARTIFACT = "t_flying_artifact"  # {2} artifact, no abilities
CLUE = "clue_token"
SWAMP = "swamp"


def position(builder, *, mine=(AURA,), theirs=(BEAR,), third=(), players=2, active=1):
    """``mine`` under player 0, ``theirs`` under player 1, ``third`` under player 2.

    Player 1 is the active player by default, because the two sentences worth
    testing are both about *their* turn: the combat trigger and the toll.

    Built from the untap step and advanced, so the position starts with the
    turn's own machinery having run. Any Aura in ``mine`` is attached to player 1
    before the advance -- `GameBuilder.battlefield` places permanents rather than
    playing them, exactly as it fires no enters trigger, so the attaching is the
    caller's job here just as it is for Equipment.
    """
    b = builder(players=players)
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    if third and players > 2:
        b.battlefield(2, list(third))
    for pid in range(players):
        # A land in hand is what makes the position *stop* inside turn one: with
        # no legal action anywhere the engine auto-passes whole turns, and a
        # trigger asserted after that has already had several upkeeps to fire
        # on. Nothing plays it -- `_default_answer` passes priority.
        b.library(pid, [SWAMP] * 30).hand(pid, [SWAMP])
    game = b.active(active).step(Step.UNTAP).build(advance=False)
    for def_id in (AURA, ROBE):
        for oid in oids_of(game, def_id):
            attach_to_player(game.state, oid, 1)
    game._advance()
    return game


def cast_position(builder, *, players=2, mine=(), theirs=()):
    """Player 0 with the Aura in hand and the mana to cast it -- the real path.

    The only way to exercise `stack._attach_aura`, which is where an Aura
    learns what it enchants: a permanent *placed* on the battlefield was never
    a spell and has no targets to read.
    """
    b = builder(players=players)
    b.battlefield(0, [SWAMP] * 4).hand(0, [AURA])
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    for pid in range(players):
        b.library(pid, [SWAMP] * 30)
    return b.build()


def cast_the_aura(game, *, at: int | None = None) -> int:
    """Cast the Aura, enchanting ``at`` (or whichever seat is offered). Its oid."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and (at is None or any(ref.kind == "player" and ref.id == at for ref in a.targets))
    )
    oid = action.source
    game.apply(action)
    settle(game)
    return oid


def settle(game, limit: int = 60) -> None:
    """Let the stack and the pending triggers empty out."""
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def attacks_offered(game, *, toll=ActionKind.NO, limit: int = 80):
    """Every ADD_ATTACKER offered during this turn's declare-attackers step.

    Collected across the whole turn rather than asserted at one decision,
    because a combat in which no creature can attack has **no declare-attackers
    decision at all** -- `can_attack` is false for everything, so the step is
    skipped and there is no moment at which to look at an empty list. "Nothing
    was ever offered" is the observation the printed sentence makes.

    ``toll`` answers the enchanted player's "you may pay" with yes or no. Runs
    to the end of the current turn, so calling it twice reads two combats --
    which is how the ``this_combat`` clock is asserted.
    """
    seen: list[tuple[int, tuple[str, int]]] = []
    turn = game.state.turn
    for _ in range(limit):
        decision = game.pending()
        if decision is None or game.state.turn != turn:
            break
        if game.state.step is Step.DECLARE_ATTACKERS:
            seen += [
                (a.source, (t.kind, t.id))
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                for t in a.targets
            ]
        if decision.kind is DecisionKind.MAY:
            paid = next((a for a in game.legal_actions() if a.kind is toll), None)
            game.apply(paid or _default_answer(game, decision))
            continue
        game.apply(_default_answer(game, decision))
    return seen


def toll_offered(game, limit: int = 60):
    """The "you may pay" decision this turn's combat trigger produced, if any.

    ``None`` means the trigger resolved without asking -- which `op_may` does
    when the price cannot be met, and is therefore also how "the toll was
    counted wrongly and came out unaffordable" shows up.
    """
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return None
        if decision.kind is DecisionKind.MAY:
            return decision
        if game.state.step is Step.POSTCOMBAT_MAIN:
            return None
        game.apply(_default_answer(game, decision))
    return None


# ----------------------------------------------------------------------
# 303.4a / 704.5n -- the Aura lives on a seat
# ----------------------------------------------------------------------


class TestTheAuraSurvivesEnchantingAPlayer:
    def test_it_arrives_attached_to_the_seat_it_targeted(self, builder):
        game = cast_position(builder)
        aura = cast_the_aura(game, at=1)

        obj = game.state.objects[aura]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.attached_to_player == 1

    def test_it_is_not_binned_by_the_unattached_state_based_action(self, builder):
        """The regression this capability exists for: it used to die on arrival."""
        game = cast_position(builder)
        aura = cast_the_aura(game, at=1)

        sba.check(game.state)

        assert game.state.objects[aura].zone is not Zone.GRAVEYARD
        assert aura in game.state.battlefield

    def test_the_object_link_stays_empty(self, builder):
        """A seat is not an oid. Reading one as the other is the whole hazard."""
        game = cast_position(builder)
        aura = cast_the_aura(game, at=1)

        assert game.state.objects[aura].attached_to is None

    def test_an_aura_attached_to_nothing_is_still_binned(self, builder):
        """The counterfactual. 704.5n did not stop applying."""
        game = position(builder, mine=(), theirs=())
        game.state.battlefield.append(
            oid := _place(game, AURA, controller=0),
        )

        sba.check(game.state)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_it_goes_to_the_graveyard_when_that_player_leaves_the_game(self, builder):
        """704.5n's other half: the host became illegal, so the Aura follows."""
        game = position(builder, players=3, theirs=(BEAR,), third=(BEAR,))
        aura = only_oid(game, AURA)
        game.state.players[1].life = 0

        sba.check(game.state)

        assert not game.state.is_alive(1)
        assert game.state.objects[aura].zone is Zone.GRAVEYARD

    def test_moving_it_onto_a_permanent_clears_the_seat(self, builder):
        """An Aura is attached to exactly one thing (303.4)."""
        game = position(builder, theirs=(BEAR,))
        aura, bear = only_oid(game, AURA), only_oid(game, BEAR)
        assert game.state.objects[aura].attached_to_player == 1

        attach(game.state, aura, bear)

        assert game.state.objects[aura].attached_to == bear
        assert game.state.objects[aura].attached_to_player is None

    def test_it_counts_as_attached_for_the_static_condition_leaf(self, builder):
        """`is_attached` asks a plain question, and both hosts answer it.

        Reading only the object link would say "no" of a permanent the rules and
        the state-based actions both call attached -- and `is_attached` is legal
        in a static precisely because both fields are pipeline *inputs* the
        `attach` primitives write and no layer can change.
        """
        game = position(builder)
        source = game.state.objects[only_oid(game, AURA)]

        assert _condition_met(game.state, source, {"is_attached": True}) is True
        assert _condition_met(game.state, source, {"is_attached": False}) is False

    def test_an_unattached_permanent_still_answers_no(self, builder):
        """The boundary: the leaf did not become a tautology."""
        game = position(builder, mine=(), theirs=())
        source = game.state.objects[_place(game, BEAR, controller=0)]

        assert _condition_met(game.state, source, {"is_attached": True}) is False


def _place(game, def_id: str, *, controller: int) -> int:
    """Put a permanent on the battlefield attached to nothing at all."""
    from automtg.engine.state import new_object

    obj = new_object(game.state, def_id, owner=controller, zone=Zone.BATTLEFIELD)
    obj.controller = controller
    return obj.oid


# ----------------------------------------------------------------------
# the effect side -- "enchanted opponent", "that player"
# ----------------------------------------------------------------------


class TestItsAbilitiesCanNameThatPlayer:
    def test_the_enters_trigger_pays_out_to_the_enchanted_player(self, builder):
        """"Enchanted opponent creates a Clue token" -- their Clue, not yours."""
        game = cast_position(builder)
        cast_the_aura(game, at=1)

        clues = oids_of(game, CLUE)
        assert [game.state.objects[c].controller for c in clues] == [1]

    def test_at_a_pod_only_the_enchanted_opponent_gets_it(self, builder):
        """`each_opponent` is the near miss, and it is wrong by one whole seat."""
        game = cast_position(builder, players=3)
        cast_the_aura(game, at=2)

        clues = oids_of(game, CLUE)
        assert [game.state.objects[c].controller for c in clues] == [2]

    def test_an_aura_on_a_creature_names_nobody(self, builder):
        """`[]` rather than a fallback to the controller: an effect aimed at
        nobody does nothing, where "me" would point the card at its own caster."""
        b = builder(players=2)
        b.battlefield(0, [SWAMP, SWAMP]).hand(0, [ON_CREATURE]).battlefield(1, [BEAR])
        for pid in range(2):
            b.library(pid, [SWAMP] * 30)
        game = b.build()
        bear = only_oid(game, BEAR)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and any(r.id == bear for r in a.targets)
        )
        game.apply(action)
        settle(game)

        assert oids_of(game, CLUE) == []

    def test_the_toll_is_billed_to_the_enchanted_player(self, builder):
        """`op_may` reads an empty player list as `ctx.controller`, so a spec
        that resolved to nobody would hand the bill to the Aura's own side."""
        game = position(builder, theirs=(BEAR,))

        decision = toll_offered(game)

        assert decision is not None
        assert decision.player == 1


class TestTheTollCountsThatPlayersArtifacts:
    def test_it_scales_with_their_own_artifacts(self, builder):
        """Two artifacts is {2}, and one land cannot meet it -- so no question is
        asked at all, which is `op_may`'s reading of an unpayable optional cost."""
        game = position(builder, theirs=(BEAR, ARTIFACT, ARTIFACT, SWAMP))

        assert toll_offered(game) is None

    def test_two_artifacts_and_two_lands_can_pay(self, builder):
        game = position(builder, theirs=(BEAR, ARTIFACT, ARTIFACT, SWAMP, SWAMP))

        assert toll_offered(game) is not None

    def test_another_opponents_artifacts_are_not_counted(self, builder):
        """`controller: "opponent"` is the near miss and reads the whole table.

        The enchanted player controls nothing, so their toll is {0} and the
        question is asked with no mana at all. Counted the near miss's way it
        would be {3} -- unpayable -- and the trigger would silently skip the
        question and lock the board.
        """
        game = position(
            builder, players=3, theirs=(BEAR,), third=(ARTIFACT, ARTIFACT, ARTIFACT)
        )

        assert toll_offered(game) is not None


class TestTheTriggerFiresOnThatPlayersTurn:
    """The Robe's upkeep line, read one turn at a time.

    Every assertion here is made at the position's **first** stop, which is
    inside turn one, and that is the point: the clause is about *whose* upkeep,
    so a test that let the game roll on would see it fire eventually whatever
    the condition said.
    """

    def test_it_fires_on_the_enchanted_players_turn(self, builder):
        game = position(builder, mine=(ROBE,), theirs=(BEAR,), active=1)

        assert game.state.turn == 1
        assert game.state.players[1].life == 39

    def test_it_does_not_fire_on_the_aura_controllers_turn(self, builder):
        """`is_your_turn` is the leaf that cannot say this: a trigger is always
        evaluated with the ability's own controller, which is the other seat."""
        game = position(builder, mine=(ROBE,), theirs=(BEAR,), active=0)

        assert game.state.turn == 1
        assert game.state.players[1].life == 40

    def test_at_a_pod_it_does_not_fire_on_a_third_players_turn(self, builder):
        """`controller: "opponent"` is the near miss: at a pod it means *any*
        opponent's turn, so the Robe would drain on two turns in three."""
        game = position(
            builder, mine=(ROBE,), theirs=(BEAR,), third=(BEAR,), players=3, active=2
        )

        assert game.state.turn == 1
        assert game.state.players[1].life == 40


# ----------------------------------------------------------------------
# "creatures can't attack this combat" -- 506.2's three targets
# ----------------------------------------------------------------------


class TestCreaturesCantAttackThisCombat:
    def test_nothing_is_offered_as_an_attacker_when_the_toll_goes_unpaid(self, builder):
        game = position(builder, mine=(AURA, WALKER), theirs=(BEAR,))

        assert attacks_offered(game, toll=ActionKind.NO) == []

    def test_paying_leaves_combat_untouched(self, builder):
        """The boundary. Nothing controls no artifacts, so the price is {0} --
        and a lock that fired anyway would be a strictly stronger card."""
        game = position(builder, mine=(AURA, WALKER), theirs=(BEAR,))
        bear = only_oid(game, BEAR)
        walker = only_oid(game, WALKER)

        offered = attacks_offered(game, toll=ActionKind.YES)

        assert sorted(offered) == sorted([(bear, ("player", 0)), (bear, ("object", walker))])

    def test_it_reaches_planeswalkers(self, builder):
        """The half `cant_attack_player` alone gets wrong, and the reason the
        flag exists: the sentence names no defender, so a walker is not a way
        round it."""
        game = position(builder, mine=(WALKER,), theirs=(BEAR,))
        state = game.state
        bear = only_oid(game, BEAR)

        restrict_attack(state, 1, 0, "this_combat", planeswalkers=True)

        assert combat_mod.legal_defenders(state, bear) == []
        assert combat_mod.legal_planeswalker_defenders(state, bear) == []
        assert combat_mod.can_attack(state, bear) is False

    def test_the_seat_only_form_still_exempts_them(self, builder):
        """The counterfactual, and the reading every card that names a *player*
        keeps: 506.2 -- attacking somebody's planeswalker is not attacking
        them, which is why Ghostly Prison taxes nothing when it does."""
        game = position(builder, mine=(WALKER,), theirs=(BEAR,))
        state = game.state
        bear, walker = only_oid(game, BEAR), only_oid(game, WALKER)

        restrict_attack(state, 1, 0, "this_combat", planeswalkers=False)

        assert combat_mod.legal_defenders(state, bear) == []
        assert combat_mod.legal_planeswalker_defenders(state, bear) == [walker]
        assert combat_mod.can_attack(state, bear) is True

    def test_the_two_widths_are_separate_entries(self, builder):
        """Not deduplicated together: a narrow entry swallowing a wide one would
        silently be the weaker prohibition."""
        game = position(builder, theirs=(BEAR,))
        state = game.state

        assert restrict_attack(state, 1, 0, "this_combat", planeswalkers=False) is True
        assert restrict_attack(state, 1, 0, "this_combat", planeswalkers=True) is True
        assert restrict_attack(state, 1, 0, "this_combat", planeswalkers=True) is False
        assert len(state.attack_restrictions) == 2

    def test_it_wears_off_with_the_combat(self, builder):
        """`this_combat`, so the **next** combat is free.

        The lock is bought and lost by a payment every combat, which is the
        whole reason it could not be the `cant_attack` static: that one is a
        continuous ability read off the battlefield for as long as its source
        sits there, and this one has to end even though the Aura has not moved.

        Asserted as the next turn's declare-attackers step rather than as an
        empty list, because an empty list is also what "nothing was ever
        installed" looks like.
        """
        game = position(builder, mine=(AURA, WALKER, BEAR), theirs=(BEAR,))
        assert attacks_offered(game, toll=ActionKind.NO) == []

        mine = [oid for oid in oids_of(game, BEAR) if game.state.objects[oid].controller == 0]
        offered = attacks_offered(game, toll=ActionKind.NO)

        assert game.state.attack_restrictions == []
        assert [oid for oid, _ in offered] == mine


# ----------------------------------------------------------------------
# the load-time guards
# ----------------------------------------------------------------------


def _card(**over):
    body = {
        "id": "x",
        "name": "X",
        "mana_cost": "{1}",
        "types": ["Enchantment"],
        "subtypes": ["Aura"],
        "targets": [{"id": "t1", "kind": "player", "count": 1}],
        "abilities": [
            {
                "kind": "triggered",
                "text": "",
                "trigger": {"event": "self_enters", "source": "self"},
                "effects": [
                    {"op": "gain_life", "player": "enchanted_player", "amount": {"const": 1}}
                ],
            }
        ],
    }
    body.update(over)
    return compile_card(CardModel.model_validate(body))


class TestTheLoaderRefusesTheNearMisses:
    def test_the_aura_form_loads(self):
        assert _card() is not None

    def test_enchanted_player_off_an_aura_is_refused(self):
        """It would resolve to nobody for the whole game, and say nothing."""
        with pytest.raises(DslError, match="enchanted_player"):
            _card(types=["Artifact"], subtypes=[], targets=[])

    def test_it_is_refused_inside_a_static_affects_filter_too(self):
        """A static flattens its parameters onto the ability, so the ordinary
        effect walk cannot see them -- and an unknown controller word matches
        every permanent on the table rather than none."""
        with pytest.raises(DslError, match="enchanted_player"):
            _card(
                types=["Artifact"],
                subtypes=[],
                targets=[],
                abilities=[
                    {
                        "kind": "static",
                        "text": "",
                        "effect": "buff",
                        "affects": {"controller": "enchanted_player", "types": ["Creature"]},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                    }
                ],
            )

    def test_a_non_boolean_planeswalkers_flag_is_refused(self):
        """`"false"` is a non-empty string and would read as `true`, turning a
        line that names a seat into one strictly stronger than the printing."""
        with pytest.raises(DslError, match="planeswalkers"):
            _card(
                abilities=[
                    {
                        "kind": "triggered",
                        "text": "",
                        "trigger": {"event": "self_enters", "source": "self"},
                        "effects": [
                            {
                                "op": "cant_attack_player",
                                "attacker": "each_player",
                                "defender": "each_player",
                                "duration": "this_combat",
                                "planeswalkers": "false",
                            }
                        ],
                    }
                ]
            )
