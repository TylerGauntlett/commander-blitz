"""Which *creatures* attacked this turn -- rule 508.1, read after combat is over.

Declaring attackers (508.1) is an event, and like every other event in
`TurnLedger` the board keeps no record that it happened. The engine already
recorded the *seat*: `attacked` was a `set[int]` of player ids, which is the
whole of raid. Two printed cards ask the other half of the same question and
neither can be answered from it:

**Relentless Assault** -- "Untap all creatures that attacked this turn." A
sorcery, so it resolves in a **main phase**, after the combat it is talking
about. `attacking` is the near miss and is strictly live combat state:
`combat.end_combat` sets `state.combat = None`, so by the time this spell
resolves `attacking` is false for every creature on the board and the untap
would hit nothing at all. `tapped` is the other near miss and is wrong in *both*
directions -- it catches a creature tapped for mana and misses a vigilant
attacker, which is the one this card most wants to untap.

**Windbrisk Heights** -- "if you attacked with three or more creatures this
turn." `{"attacked_this_turn": "you"}` counts players, so it is 1 whether you
swung with one creature or ten: compared against 3 it can never be true, and
relaxing the comparison to 1 quietly demotes a hideaway land to a raid land.
And a board count cannot stand in either, because **an attacker that died in
combat still attacked** -- three attackers, one of which traded, has to leave
the land unlocked in the postcombat main phase.

So `TurnLedger.creatures_attacked` holds player id -> the *oids* they declared,
`attacked` is derived from its keys so raid and this cannot disagree, and the two
readers are an ordinary selector key (`attacked_this_turn`) and an ordinary value
(`attackers_this_turn`). Nothing new was needed in the condition language.

One boundary carries the design: **removal from combat does not undo a
declaration** (506.4). A creature that attacked and then died, was bounced, or
was removed from combat still attacked this turn, so nothing is ever taken out of
the record -- it is cleared only with the rest of the ledger at cleanup.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.conditions import evaluate_condition
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import (
    _default_answer,
    action_for_card,
    find_action,
    oids_of,
    only_oid,
    pass_until,
)

BEAR = "t_bear"  # {1}{G} 2/2
DORK = "t_dork"  # {G} 1/1, "{T}: Add {G}."
VIGILANT = "t_vigilant"  # {1}{W} 2/2 vigilance
BOLT = "t_bolt"  # {R} instant, so priority genuinely stops each step
RELENTLESS = "t_relentless"  # {2}{R} sorcery, "Untap all creatures that attacked…"
VAULT = "t_raid_vault"  # {2} artifact, "{T}: Draw a card if you attacked with 3+…"

#: Selectors that read the record, and the two near misses they replace.
ATTACKED = {"zone": "battlefield", "types": ["Creature"], "attacked_this_turn": True}
ATTACKING = {"zone": "battlefield", "types": ["Creature"], "attacking": True}
TAPPED = {"zone": "battlefield", "types": ["Creature"], "tapped": True}


# ----------------------------------------------------------------------
# the position, and the combat idiom of `test_turn_ledger.py`
# ----------------------------------------------------------------------


def board(builder, mine=(BEAR, BEAR, BEAR), hand=(), theirs=()):
    """A turn about to declare attackers, with an instant so the steps are visible.

    The bolt and the mountains are not decoration: with nothing castable the
    engine auto-passes from combat damage straight into the next turn, where
    cleanup has correctly emptied the ledger -- so a test reaching for the
    postcombat main phase would measure the clearing and report it as a failure to
    count. `test_turn_ledger.within_this_turn` documents the same trap.
    """
    b = builder(players=2).battlefield(0, ["mountain"] * 4).hand(0, [BOLT, *hand])
    b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    return b.build()


def to_attackers(game):
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )


def attack_with(game, *oids: int, defender: int = 1):
    from commanderblitz.engine.structs import TargetRef

    for oid in oids:
        game.apply(
            find_action(
                game,
                ActionKind.ADD_ATTACKER,
                source=oid,
                targets=(TargetRef.player(defender),),
            )
        )


def done(game):
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def within_this_turn(game, predicate, limit: int = 200):
    turn = game.state.turn
    for _ in range(limit):
        if predicate(game):
            return
        assert not game.over, "the game ended before the assertion"
        assert game.state.turn == turn, "the turn rolled over before the assertion"
        decision = game.pending()
        assert decision is not None, "nothing left to pass with"
        game.apply(_default_answer(game, decision))
    raise AssertionError("did not reach the condition inside one turn")


def swing(game, *oids: int):
    """Declare these creatures as attackers and lock the declaration in."""
    to_attackers(game)
    attack_with(game, *oids)
    done(game)


def to_postcombat_main(game):
    within_this_turn(game, lambda g: g.state.step >= Step.POSTCOMBAT_MAIN)


def ctx(game, controller: int = 0) -> EffectContext:
    return EffectContext(state=game.state, controller=controller)


def matching(game, selector) -> set[int]:
    return set(resolve_pool(ctx(game), selector))


# ----------------------------------------------------------------------
# the record itself
# ----------------------------------------------------------------------


class TestTheLedgerRecordsWhichCreaturesAttacked:
    def test_three_attackers_are_recorded_by_oid(self, builder):
        game = board(builder)
        bears = oids_of(game, BEAR, 0)
        swing(game, *bears)
        assert game.state.turn_ledger.creatures_attacked == {0: set(bears)}

    def test_declining_to_attack_records_nothing(self, builder):
        """The boundary raid is read against, and the reason the event fires
        only when there is at least one attacker."""
        game = board(builder)
        to_attackers(game)
        done(game)
        to_postcombat_main(game)
        assert game.state.turn_ledger.creatures_attacked == {}

    def test_only_the_creatures_declared_are_recorded(self, builder):
        game = board(builder, mine=(BEAR, BEAR, BEAR))
        first, *rest = oids_of(game, BEAR, 0)
        swing(game, first)
        ledger = game.state.turn_ledger
        assert ledger.has_attacked(first)
        assert not any(ledger.has_attacked(oid) for oid in rest)

    def test_a_vigilant_attacker_is_recorded_though_it_never_tapped(self, builder):
        """Half of why `tapped` cannot stand in: it misses this creature."""
        game = board(builder, mine=(VIGILANT,))
        oid = only_oid(game, VIGILANT, 0)
        swing(game, oid)
        assert game.state.turn_ledger.has_attacked(oid)
        assert not game.state.objects[oid].tapped, "vigilance -- it attacked untapped"

    def test_a_creature_tapped_for_mana_is_not_recorded(self, builder):
        """The other half: `tapped` catches this creature, which never attacked."""
        from commanderblitz.engine.primitives import tap_permanent

        game = board(builder, mine=(BEAR, DORK))
        dork = only_oid(game, DORK, 0)
        tap_permanent(game.state, dork)
        swing(game, only_oid(game, BEAR, 0))
        assert game.state.objects[dork].tapped
        assert not game.state.turn_ledger.has_attacked(dork)

    def test_it_survives_the_end_of_combat(self, builder):
        """The whole point: both cards that read it are used after combat."""
        game = board(builder)
        bears = oids_of(game, BEAR, 0)
        swing(game, *bears)
        to_postcombat_main(game)
        assert not (game.state.combat and game.state.combat.attackers), (
            "combat is over, so the board no longer says anybody attacked"
        )
        assert game.state.turn_ledger.creatures_attacked == {0: set(bears)}

    def test_it_survives_the_attacker_dying(self, builder):
        """Rule 506.4 -- leaving combat does not undo the declaration."""
        game = board(builder)
        bears = oids_of(game, BEAR, 0)
        swing(game, *bears)
        move_object(game.state, bears[0], Zone.GRAVEYARD)
        assert game.state.turn_ledger.has_attacked(bears[0]), (
            "it died in combat; it still attacked"
        )

    def test_it_clears_at_the_turn_boundary(self, builder):
        game = board(builder)
        swing(game, *oids_of(game, BEAR, 0))
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        assert game.state.turn_ledger.creatures_attacked == {}


class TestRaidReadsTheSameRecord:
    """`attacked` is derived from the keys, so the two cannot disagree."""

    def test_the_player_set_still_answers_raid(self, builder):
        game = board(builder)
        assert game.state.turn_ledger.attacked == set()
        swing(game, *oids_of(game, BEAR, 0))
        assert game.state.turn_ledger.attacked == {0}
        assert evaluate_value(ctx(game), {"attacked_this_turn": "you"}) == 1

    def test_declining_leaves_raid_false(self, builder):
        game = board(builder)
        to_attackers(game)
        done(game)
        to_postcombat_main(game)
        assert game.state.turn_ledger.attacked == set()
        assert evaluate_value(ctx(game), {"attacked_this_turn": "you"}) == 0


# ----------------------------------------------------------------------
# the selector -- Relentless Assault
# ----------------------------------------------------------------------


class TestTheSelectorFindsThemAfterCombat:
    def test_the_selector_matches_the_attackers_in_the_postcombat_main(self, builder):
        game = board(builder)
        bears = oids_of(game, BEAR, 0)
        swing(game, *bears)
        to_postcombat_main(game)
        assert matching(game, ATTACKED) == set(bears)

    def test_attacking_matches_nothing_in_the_same_position(self, builder):
        """The near miss, measured. This is the bug the key exists to fix."""
        game = board(builder)
        swing(game, *oids_of(game, BEAR, 0))
        to_postcombat_main(game)
        assert matching(game, ATTACKING) == set(), (
            "`end_combat` set state.combat to None, so live combat state is empty"
        )

    def test_it_is_false_for_a_creature_that_stayed_home(self, builder):
        game = board(builder, mine=(BEAR, BEAR, DORK))
        bears = oids_of(game, BEAR, 0)
        swing(game, *bears)
        to_postcombat_main(game)
        assert matching(game, ATTACKED) == set(bears)
        assert only_oid(game, DORK, 0) not in matching(game, ATTACKED)

    def test_the_negation_matches_everything_that_stayed_home(self, builder):
        game = board(builder, mine=(BEAR, DORK))
        swing(game, only_oid(game, BEAR, 0))
        to_postcombat_main(game)
        stayed = {**ATTACKED, "attacked_this_turn": False}
        assert matching(game, stayed) == {only_oid(game, DORK, 0)}

    def test_untap_all_creatures_that_attacked_untaps_exactly_those(self, builder):
        """Relentless Assault's first sentence, cast in a real game."""
        from commanderblitz.engine.primitives import tap_permanent

        game = board(builder, mine=(BEAR, BEAR, DORK), hand=(RELENTLESS,))
        bears = oids_of(game, BEAR, 0)
        dork = only_oid(game, DORK, 0)
        swing(game, *bears)
        tap_permanent(game.state, dork)  # tapped for mana, not for an attack
        to_postcombat_main(game)
        assert all(game.state.objects[oid].tapped for oid in bears), "attacking taps"

        game.apply(action_for_card(game, ActionKind.CAST, RELENTLESS))
        pass_until(game, lambda g: not g.state.stack)

        assert not any(game.state.objects[oid].tapped for oid in bears), (
            "both attackers untapped, in a phase where `attacking` reads false"
        )
        assert game.state.objects[dork].tapped, (
            "the mana dork never attacked, so it stays tapped -- what `tapped` "
            "as the filter would have got wrong"
        )


# ----------------------------------------------------------------------
# the value -- Windbrisk Heights
# ----------------------------------------------------------------------


class TestTheValueCountsCreaturesRatherThanSeats:
    def test_three_attackers_is_three(self, builder):
        game = board(builder)
        swing(game, *oids_of(game, BEAR, 0))
        to_postcombat_main(game)
        assert evaluate_value(ctx(game), {"attackers_this_turn": "you"}) == 3
        assert evaluate_value(ctx(game), {"attacked_this_turn": "you"}) == 1, (
            "the player tally is 1 on the same board, which is why it cannot "
            "answer 'three or more creatures'"
        )

    def test_one_attacker_is_one(self, builder):
        game = board(builder)
        swing(game, oids_of(game, BEAR, 0)[0])
        assert evaluate_value(ctx(game), {"attackers_this_turn": "you"}) == 1

    def test_nobody_attacked_is_zero(self, builder):
        game = board(builder)
        to_attackers(game)
        done(game)
        assert evaluate_value(ctx(game), {"attackers_this_turn": "you"}) == 0

    def test_an_opponents_attackers_are_not_yours(self, builder):
        game = board(builder)
        swing(game, *oids_of(game, BEAR, 0))
        assert evaluate_value(ctx(game, controller=1), {"attackers_this_turn": "you"}) == 0
        assert (
            evaluate_value(ctx(game, controller=1), {"attackers_this_turn": "each_opponent"})
            == 3
        )

    def test_the_count_survives_an_attacker_dying(self, builder):
        """The reason the ledger holds oids instead of the board being recounted."""
        game = board(builder)
        bears = oids_of(game, BEAR, 0)
        swing(game, *bears)
        move_object(game.state, bears[0], Zone.GRAVEYARD)
        to_postcombat_main(game)

        assert evaluate_value(ctx(game), {"attackers_this_turn": "you"}) == 3, (
            "you attacked with three creatures; one of them traded"
        )
        assert evaluate_value(ctx(game), {"count": ATTACKED}) == 2, (
            "and a board count reads 2 -- the approximation this value refuses"
        )

    def test_the_windbrisk_condition_is_an_ordinary_comparison(self, builder):
        """No new condition vocabulary: the whole unlock is a `cmp`."""
        game = board(builder)
        unlocked = {
            "cmp": ">=",
            "left": {"attackers_this_turn": "you"},
            "right": {"const": 3},
        }
        bears = oids_of(game, BEAR, 0)
        assert not evaluate_condition(game.state, unlocked, controller=0)
        swing(game, *bears[:2])
        assert not evaluate_condition(game.state, unlocked, controller=0), (
            "two attackers is not three"
        )
        game.state.turn_ledger.creatures_attacked[0].add(bears[2])
        assert evaluate_condition(game.state, unlocked, controller=0)


class TestTheUnlockInARealGame:
    """Windbrisk Heights' shape: an activated ability gated on the count."""

    def activate_the_vault(self, game):
        game.apply(find_action(game, ActionKind.ACTIVATE, source=only_oid(game, VAULT, 0)))
        pass_until(game, lambda g: not g.state.stack)

    def test_two_attackers_do_not_unlock_it(self, builder):
        game = board(builder, mine=(BEAR, BEAR, BEAR, VAULT))
        swing(game, *oids_of(game, BEAR, 0)[:2])
        to_postcombat_main(game)
        before = len(game.state.players[0].hand)
        self.activate_the_vault(game)
        assert len(game.state.players[0].hand) == before, "two is not three"

    def test_three_attackers_unlock_it(self, builder):
        game = board(builder, mine=(BEAR, BEAR, BEAR, VAULT))
        swing(game, *oids_of(game, BEAR, 0))
        to_postcombat_main(game)
        before = len(game.state.players[0].hand)
        self.activate_the_vault(game)
        assert len(game.state.players[0].hand) == before + 1

    def test_three_attackers_one_of_which_died_still_unlock_it(self, builder):
        """The case a board count gets wrong, played out."""
        game = board(builder, mine=(BEAR, BEAR, BEAR, VAULT))
        bears = oids_of(game, BEAR, 0)
        swing(game, *bears)
        move_object(game.state, bears[0], Zone.GRAVEYARD)
        to_postcombat_main(game)
        before = len(game.state.players[0].hand)
        self.activate_the_vault(game)
        assert len(game.state.players[0].hand) == before + 1

    def test_it_relocks_next_turn(self, builder):
        """The wearing-off. `creatures_attacked` clears with the rest of the ledger."""
        game = board(builder, mine=(BEAR, BEAR, BEAR, VAULT))
        swing(game, *oids_of(game, BEAR, 0))
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn + 1 and g.state.active_idx == 0)
        pass_until(
            game,
            lambda g: g.state.step >= Step.PRECOMBAT_MAIN and not game.state.objects[
                only_oid(game, VAULT, 0)
            ].tapped,
        )
        before = len(game.state.players[0].hand)
        self.activate_the_vault(game)
        assert len(game.state.players[0].hand) == before, (
            "a new turn, and nobody has attacked in it yet"
        )


# ----------------------------------------------------------------------
# load time
# ----------------------------------------------------------------------


class TestBothSpellingsAreCheckedAtLoadTime:
    """A misspelled filter that loads and matches nothing is the failure the
    key registries exist to refuse."""

    def test_the_selector_key_is_known(self):
        from commanderblitz.engine.effects.selectors import validate_selector

        validate_selector(ATTACKED, "test")
        with pytest.raises(DslError):
            validate_selector({"attacked_this_turn_objects": True}, "test")

    def test_the_value_key_is_known(self):
        from commanderblitz.engine.effects.values import validate_value

        validate_value({"attackers_this_turn": "you"}, "test")
        with pytest.raises(DslError):
            validate_value({"attackers_last_turn": "you"}, "test")

    def test_both_test_cards_compile(self, registry):
        for card_id in (RELENTLESS, VAULT):
            assert registry.get(card_id) is not None
