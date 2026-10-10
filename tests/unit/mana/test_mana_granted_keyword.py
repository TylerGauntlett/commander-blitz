"""A rider on mana that outlives the spell it paid for.

    "Add {R}{R}. **If that mana is spent on a creature spell, it gains haste
    until end of turn.**"                             -- Arena of Glory

`mana_uncounterable` (see `test_uncounterable_mana.py`) is the same shape with
the easy lifetime: "that spell can't be countered" is read while the spell is
still on the stack and then thrown away. This one is owed to the **permanent**,
and the spell and the permanent are the same object moving zones.

**That is the trap, and it is the reason this file exists.** Every reachable
spelling of the sentence writes haste onto the spell:

* a `spell_cast` trigger with `filter: {"paid_by": "self"}` -- Path of
  Ancestry's shape -- resolves while the creature is still on the stack;
* `grant_keyword` writes `granted_keywords`, and `grant_keyword` with no
  `permanent` writes `until_eot`.

`reset_permanent_state` clears **both** as the spell moves to the battlefield.
So the creature arrives with nothing, and a test that asserts on the spell, or
on the permanent without ever attacking, passes anyway. The assertion that
catches it is the one the card is bought for: the creature is on the
battlefield, it has haste, and it can be declared as an attacker **this turn**.

The mechanism, mirroring the uncounterable rider one field over: `mana.Pip`
carries a `ManaKeywordGrant`, `ManaPool.spend` reports the ones a payment
consumed, `costs.pay_mana` asks the printed "**creature** spell" question at the
one instant the spell still exists to be asked, `zones.move_object` carries the
answer across the reset -- and only when the destination is the battlefield --
and `_enter_battlefield` hands it over in the slot riot occupies, so the
creature is never on the battlefield without it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.costs import activate_mana_ability
from commanderblitz.engine.enums import ActionKind, Keyword, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaKeywordGrant, ManaPool, Pip, Requirement
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, find_action, only_oid, pass_until

ARENA = "t_glory_arena"  # ability 0 is the plain {R}; ability 1 carries the rider
SPRINTER = "t_glory_sprinter"  # vanilla 2/2 Creature for {2}
RELIC = "t_glory_relic"  # vanilla Artifact for {2}
#: On the board only so there *is* a declare-attackers step: a turn in which
#: nobody can attack skips it, and a test that walked on to the next one would
#: be asking about a creature whose summoning sickness had since worn off.
BEAR = "t_bear"

PLAIN_MANA = 0
RIDER_MANA = 1

HASTE = ManaKeywordGrant(keywords=("haste",), spell_types=("Creature",))


def red(n: int = 1) -> Requirement:
    colored = [0] * 6
    colored[SYMBOL_INDEX["R"]] = n
    return Requirement(colored=tuple(colored))


class TestThePipCarriesIt:
    def test_a_pip_defaults_to_no_grant(self):
        assert Pip().grant is None
        assert Pip(source=7).grant is None

    def test_spending_a_plain_pool_reports_nothing(self):
        pool = ManaPool()
        pool.add("R", 1, source=1)
        assert pool.spend(red()).grants == ()

    def test_spending_a_rider_pip_reports_it(self):
        pool = ManaPool()
        pool.add("R", 1, source=1, grant=HASTE)
        assert pool.spend(red()).grants == (HASTE,)

    def test_two_pips_of_one_grant_report_it_once(self):
        """Arena makes `{R}{R}` and the creature gains haste, not haste twice."""
        pool = ManaPool()
        pool.add("R", 2, source=1, grant=HASTE)
        assert pool.spend(red(2)).grants == (HASTE,)

    def test_it_does_not_leak_to_the_next_payment(self):
        """The wearing-off: each payment reports only the pips it consumed."""
        pool = ManaPool()
        pool.add("R", 1, source=1, grant=HASTE)
        pool.add("R", 1, source=2)
        assert pool.spend(red()).grants == (), "newest first: the plain pip"
        assert pool.spend(red()).grants == (HASTE,), "then the Arena's"


class TestOneCardTwoAbilities:
    """The case that makes a per-permanent flag wrong, as Cavern's does."""

    def board(self, builder):
        game = builder(players=2).battlefield(0, [ARENA]).build(advance=False)
        return game, only_oid(game, ARENA, 0)

    def test_the_rider_ability_makes_granting_mana(self, builder):
        game, arena = self.board(builder)
        activate_mana_ability(game.state, arena, RIDER_MANA, 0)
        pool = game.state.players[0].mana_pool
        assert all(pip.grant == HASTE for row in pool.tags for pip in row)

    def test_the_plain_ability_on_the_same_permanent_does_not(self, builder):
        """Same card, same permanent, other ability -- and ordinary mana.

        Recorded against the permanent instead, Arena's printed first line would
        hand out haste for free, which is a strictly better land.
        """
        game, arena = self.board(builder)
        activate_mana_ability(game.state, arena, PLAIN_MANA, 0)
        pool = game.state.players[0].mana_pool
        assert not any(pip.grant for row in pool.tags for pip in row)


def cast_with(builder, card_id: str, *, rider: bool):
    """Exert the Arena (or not) and cast ``card_id`` with the mana.

    One Mountain and no more, so the payment has exactly one shape: the Mountain
    pays the Arena's `{R}`, which leaves the pool holding the Arena's two and the
    board holding nothing untapped for the solver to reach for.
    """
    game = (
        builder(players=2)
        .hand(0, [card_id])
        .battlefield(0, [ARENA, "mountain", BEAR])
        .build()
    )
    arena = only_oid(game, ARENA, 0)
    if rider:
        game.apply(
            find_action(game, ActionKind.ACTIVATE, source=arena, ability_index=RIDER_MANA)
        )
    else:
        # The plain line, fired the way the payment solver fires it: it is
        # `is_tap_only`, so legality never offers it as a row.
        activate_mana_ability(game.state, arena, PLAIN_MANA, 0)
        activate_mana_ability(game.state, only_oid(game, "mountain", 0), 0, 0)
    spell = action_for_card(game, ActionKind.CAST, card_id).source
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    return game, spell


def to_combat(game) -> None:
    """Walk to **this** turn's declare-attackers step and no further.

    Not a `pass_until` on the step alone: the creature's controller is the
    active player here, so the next such step would be theirs again two turns
    later, with the summoning sickness gone and both halves of the test looking
    alike.
    """
    turn = game.state.turn
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    assert game.state.turn == turn, "walked past the turn the creature entered"


class TestTheGrantSurvivesTheArrival:
    def test_the_creature_is_on_the_battlefield_with_haste(self, builder):
        game, oid = cast_with(builder, SPRINTER, rider=True)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert Keyword.HASTE.value in chars(game.state, oid).keywords

    def test_it_can_attack_this_turn(self, builder):
        """The assertion the card is bought for, and the one every wrong
        implementation fails: haste written onto the *spell* is wiped by
        `reset_permanent_state` on the way in, and nothing says so."""
        game, oid = cast_with(builder, SPRINTER, rider=True)
        to_combat(game)
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),)
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert oid in game.state.combat.attackers

    def test_without_the_rider_it_cannot(self, builder):
        """The control. Same creature, same turn, mana from Arena's other line
        -- and summoning sickness stands."""
        game, oid = cast_with(builder, SPRINTER, rider=False)
        assert Keyword.HASTE.value not in chars(game.state, oid).keywords
        to_combat(game)
        assert not any(
            a.kind is ActionKind.ADD_ATTACKER and a.source == oid
            for a in game.legal_actions()
        )

    def test_the_grant_wears_off(self, builder):
        """"Until end of turn" -- `until_eot` and not riot's `granted_keywords`,
        which has no duration and is never swept."""
        game, oid = cast_with(builder, SPRINTER, rider=True)
        pass_until(game, lambda g: g.state.turn >= 2 and g.state.step >= Step.UPKEEP)
        assert Keyword.HASTE.value not in chars(game.state, oid).keywords

    def test_a_noncreature_spell_is_given_nothing(self, builder):
        """ "If that mana is spent on a **creature** spell". The artifact is paid
        for with the same two pips and gains nothing."""
        game, oid = cast_with(builder, RELIC, rider=True)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert not chars(game.state, oid).keywords
        assert not game.state.objects[oid].mana_granted_keywords


class TestTheStagingFieldIsNotAKeepsake:
    def test_it_is_emptied_by_the_arrival(self, builder):
        """The promise belongs to one arrival. A permanent that leaves and comes
        back is a new object and nobody paid Arena of Glory for that one."""
        game, oid = cast_with(builder, SPRINTER, rider=True)
        assert game.state.objects[oid].mana_granted_keywords == set()

    def test_a_spell_that_never_arrives_does_not_keep_it(self, builder):
        """The reason `move_object` restores it for one destination only. A
        countered creature spell that kept the promise in its graveyard would
        cash it on a later cast, off mana nobody spent.
        """
        game = builder(players=2).hand(0, [SPRINTER]).build(advance=False)
        oid = next(o.oid for o in game.state.objects.values() if o.def_id == SPRINTER)
        game.state.objects[oid].mana_granted_keywords = {Keyword.HASTE.value}
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert game.state.objects[oid].mana_granted_keywords == set()


class TestTheLoaderPlacesTheRider:
    def _card(self, **extra) -> CardModel:
        ability = {
            "kind": "activated",
            "text": "{T}: Add {R}.",
            "cost": {"tap": True},
            "effects": [{"op": "add_mana", "mana": "{R}"}],
            **extra,
        }
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "{T}: Add {R}.",
                "types": ["Land"],
                "abilities": [ability],
            }
        )

    def test_it_loads_on_a_mana_ability(self):
        card = compile_card(
            self._card(
                is_mana_ability=True,
                mana_grant={"keywords": ["haste"], "spell_types": ["Creature"]},
            )
        )
        assert card.abilities[0].mana_grant == HASTE

    def test_the_spell_filter_is_optional(self):
        card = compile_card(self._card(is_mana_ability=True, mana_grant={"keywords": ["haste"]}))
        assert card.abilities[0].mana_grant == ManaKeywordGrant(keywords=("haste",))

    def test_it_is_refused_on_anything_else(self):
        """It rides the mana, so on an ability that makes none it would load and
        never be read."""
        with pytest.raises(DslError, match="mana_grant"):
            compile_card(self._card(mana_grant={"keywords": ["haste"]}))

    def test_a_misspelt_keyword_is_refused(self):
        """A rider that matches nothing reads on the board as a land whose
        second ability is strictly worse than its first -- silent, and the
        reason the names are checked at load time."""
        with pytest.raises(DslError, match="unknown keyword"):
            compile_card(self._card(is_mana_ability=True, mana_grant={"keywords": ["hast"]}))

    def test_a_misspelt_type_is_refused(self):
        with pytest.raises(DslError, match="unknown card type"):
            compile_card(
                self._card(
                    is_mana_ability=True,
                    mana_grant={"keywords": ["haste"], "spell_types": ["creature"]},
                )
            )

    def test_a_grant_of_nothing_is_refused(self):
        with pytest.raises(DslError, match="keywords"):
            compile_card(self._card(is_mana_ability=True, mana_grant={"keywords": []}))
