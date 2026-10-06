""""Target creature can't be blocked this turn" -- evasion with a clock, aimed
at a creature the granting permanent does not control and may not outlive.

Rule 509.1b: a blocker may be declared against an attacker only if no effect
says it can't. The engine already had two of those effects and neither can say
this sentence.

- The `block_restriction` **static** ("this creature can't be blocked by
  Humans", read by `characteristics.block_restrictions` off
  `_battlefield_statics`) is the near miss the gap record for **Rogue's Passage**
  names, and it is the wrong shape three ways over. It must live on a permanent
  standing on the battlefield; it lasts exactly as long as that permanent does;
  and its filters read only *printed* characteristics, so there is no key that
  means "the creature this activated ability targeted". `grant_ability` cannot
  smuggle one onto the target either -- granted abilities are read by
  `triggers.py` alone, and `_battlefield_statics` never consults them, so a
  granted static would load clean and do nothing at all.
- The evasion **keywords** (menace, fear, intimidate, skulk, shadow,
  horsemanship, the landwalks) are every one of them a condition on *which*
  creatures may block. Granting one would be an approximation of "can't be
  blocked", and an approximation of a printed line is a different card.

So this is a one-shot effect on the table, `GameState.unblockables`, and it is
the exact mirror of `cant_block`'s `GameState.block_prohibitions` next door:
that one names a would-be **blocker** and takes it out of every block, this one
names an **attacker** and takes every blocker out of the block against it. They
meet in `combat.can_block` and nowhere else.

What is pinned below, and each is a way this could be silently wrong rather than
broken:

1. Every blocker is refused, not merely the ones some filter matches -- that is
   the difference from `block_restriction`, and from menace and fear.
2. The **direction**. The entry names the attacker; the same creature named
   while it blocks is untouched, and an unblockable creature may still block.
3. It composes with `cant_block` by neither predicate reading the other. Both
   are early-outs in `can_block`, so a prohibited blocker facing an unblockable
   attacker is refused twice, which is one refusal.
4. It wears off. `this_turn` ends at cleanup -- not at end of combat, where a
   combat-scoped evasion would be indistinguishable from none;
   `until_your_next_turn` (Sly Instigator) ends in the granting player's own
   untap step, and never in anybody else's.
5. It **outlives its source**. Rogue's Passage may be destroyed in response to
   its own ability and the creature stays unblockable, which is the first thing
   a static could not do.
6. A block *requirement* excuses a creature that cannot legally block the
   attacker it was provoked by, rather than compelling an illegal block.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import combat as combat_mod
from automtg.engine import sba
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.temp_effects import forbid_block, make_unblockable
from automtg.engine.zones import destroy
from tests.conftest import _default_answer, oids_of, only_oid, pass_until

BEAR = "t_bear"
WALL = "t_wall"
PASSAGE = "t_passage"  # {4}, {T}: target creature can't be blocked this turn
SLIP = "t_slip"  # {U} sorcery: target creature can't be blocked this turn
INSTIGATOR = "t_instigator"  # until your next turn, their creature can't be blocked


def position(builder, *, players=2, mine=(BEAR,), theirs=(BEAR,), hand=(), lands=0):
    """Player 0 attacks with ``mine``; player 1 defends with ``theirs``."""
    b = builder(players=players)
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    if hand:
        b.hand(0, list(hand))
    if hand or lands:
        b.battlefield(0, ["island"] * (lands or 3))
    return b.active(0).step(Step.UNTAP).build()


def to_declare_blockers(game, limit: int = 80):
    """Advance to the declare-blockers decision, attacking with everything on the way."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_BLOCKERS:
            return game
        if decision.kind is DecisionKind.DECLARE_ATTACKERS:
            adds = [
                a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER
            ]
            game.apply(adds[0] if adds else _default_answer(game, decision))
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare blockers")


def blocks_offered(game) -> list[tuple[int, int]]:
    """The (blocker, attacker) pairs the defending player may still declare."""
    return sorted(
        (a.source, a.targets[0].id)
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_BLOCKER and a.source is not None
    )


def blockers_offered(game) -> list[int]:
    return sorted({blocker for blocker, _ in blocks_offered(game)})


def cast(game, card_id: str, limit: int = 40) -> None:
    """Cast a spell from player 0's hand and let it resolve, taking any target."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"{card_id} never resolved")


class TestEveryBlockerIsRefused:
    def test_the_unrestricted_baseline(self, builder):
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        to_declare_blockers(game)
        assert blockers_offered(game) == [theirs]

    def test_no_blocker_is_offered_against_an_unblockable_attacker(self, builder):
        game = position(builder, theirs=(BEAR, WALL))
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=0)
        to_declare_blockers(game)
        assert blockers_offered(game) == [], "both of them, not the ones a filter matched"

    def test_can_block_says_so_directly(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        theirs = only_oid(game, BEAR, 1)
        to_declare_blockers(game)
        assert combat_mod.can_block(game.state, theirs, mine, 1)
        make_unblockable(game.state, [mine], "this_turn", player=0)
        assert not combat_mod.can_block(game.state, theirs, mine, 1)

    def test_a_bigger_blocker_is_refused_too(self, builder):
        """The difference from skulk and menace, which is why neither of them
        could stand in for this: those refuse *some* blockers."""
        game = position(builder, theirs=(WALL,))
        mine = only_oid(game, BEAR, 0)
        wall = only_oid(game, WALL, 1)
        make_unblockable(game.state, [mine], "this_turn", player=0)
        to_declare_blockers(game)
        assert not combat_mod.can_block(game.state, wall, mine, 1)


class TestTheDirectionIsTheAttacker:
    def test_naming_the_blocker_instead_does_nothing(self, builder):
        """The one mistake this op could make that still looks like a working
        card: an entry keyed on the wrong creature."""
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        make_unblockable(game.state, [theirs], "this_turn", player=0)
        to_declare_blockers(game)
        assert blockers_offered(game) == [theirs]

    def test_an_unblockable_creature_may_still_block(self, builder):
        """"Can't be blocked" says nothing about blocking. Player 1's creature is
        made unblockable and then has to block on their opponent's turn anyway."""
        game = position(builder)
        theirs = only_oid(game, BEAR, 1)
        make_unblockable(game.state, [theirs], "this_turn", player=1)
        to_declare_blockers(game)
        assert blockers_offered(game) == [theirs]

    def test_only_the_named_attacker_is_unblockable(self, builder):
        game = position(builder, mine=(BEAR, BEAR), theirs=(BEAR,))
        mine, other = oids_of(game, BEAR, 0)
        theirs = only_oid(game, BEAR, 1)
        make_unblockable(game.state, [mine], "this_turn", player=0)
        to_declare_blockers(game)
        assert blocks_offered(game) == [(theirs, other)], (
            "the other attacker is an ordinary creature and is blockable"
        )

    def test_a_creature_that_arrives_later_was_never_named(self, builder):
        """The set is fixed at resolution -- there is no live global form here,
        unlike `cant_block`'s "creatures can't block this turn"."""
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=0)
        assert not combat_mod.unblockable(game.state, 9999)


class TestItComposesWithCantBlock:
    """The two predicates are independent early-outs in `can_block`, so the
    interesting case is the one where both apply and neither reads the other."""

    def test_a_prohibited_blocker_facing_an_unblockable_attacker(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        theirs = only_oid(game, BEAR, 1)
        forbid_block(game.state, [theirs], "this_turn", player=0)
        make_unblockable(game.state, [mine], "this_turn", player=0)
        assert combat_mod.block_prohibited(game.state, theirs)
        assert combat_mod.unblockable(game.state, mine)
        to_declare_blockers(game)
        assert not combat_mod.can_block(game.state, theirs, mine, 1)
        assert blockers_offered(game) == []

    def test_lifting_one_of_them_leaves_the_other_biting(self, builder):
        """Neither is doing the other's work: drop the prohibition and the
        attacker is still unblockable; drop the evasion and the blocker is still
        prohibited."""
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        theirs = only_oid(game, BEAR, 1)
        to_declare_blockers(game)

        make_unblockable(game.state, [mine], "this_turn", player=0)
        assert not combat_mod.can_block(game.state, theirs, mine, 1)
        game.state.unblockables.clear()
        assert combat_mod.can_block(game.state, theirs, mine, 1)

        forbid_block(game.state, [theirs], "this_turn", player=0)
        assert not combat_mod.can_block(game.state, theirs, mine, 1)
        game.state.block_prohibitions.clear()
        assert combat_mod.can_block(game.state, theirs, mine, 1)

    def test_a_prohibited_creature_still_cannot_block_an_ordinary_attacker(
        self, builder
    ):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        theirs = only_oid(game, BEAR, 1)
        forbid_block(game.state, [theirs], "this_turn", player=0)
        to_declare_blockers(game)
        assert not combat_mod.can_block(game.state, theirs, mine, 1)


class TestABlockRequirementIsExcusedNotBroken:
    def test_a_provoked_creature_owes_nothing_against_an_unblockable_attacker(
        self, builder
    ):
        """`unmet_block_requirements` asks `can_block`, so "blocks if able" is
        satisfied by being unable. Without this the defending player would be
        held at a declaration they have no legal action to complete."""
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        theirs = only_oid(game, BEAR, 1)
        to_declare_blockers(game)
        game.state.objects[theirs].must_block = mine
        assert combat_mod.unmet_block_requirements(game.state, 1) == [theirs]
        make_unblockable(game.state, [mine], "this_turn", player=0)
        assert combat_mod.unmet_block_requirements(game.state, 1) == []
        assert combat_mod.blocks_valid(game.state, 1)


class TestTheClocks:
    def test_this_turn_ends_at_cleanup(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=0)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.unblockables == []

    def test_this_turn_survives_the_end_of_combat(self, builder):
        """A creature that is unblockable only until the combat ends would be
        indistinguishable from one that never was, since blockers are declared
        inside that combat -- and an extra combat this turn is still this turn."""
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=0)
        to_declare_blockers(game)
        combat_mod.end_combat(game.state)
        assert [u.duration for u in game.state.unblockables] == ["this_turn"]

    def test_until_your_next_turn_survives_the_opponents_whole_turn(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "until_your_next_turn", player=0)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.active_player == 1
        assert len(game.state.unblockables) == 1

    def test_until_your_next_turn_ends_at_the_granting_players_untap(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "until_your_next_turn", player=0)
        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.active_player == 0, "back round to player 0's untap step"
        assert game.state.unblockables == []

    def test_the_two_clocks_do_not_clear_each_other(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=0)
        make_unblockable(game.state, [mine], "until_your_next_turn", player=0)
        assert len(game.state.unblockables) == 2
        pass_until(game, lambda g: g.state.turn >= 2)
        assert [u.duration for u in game.state.unblockables] == [
            "until_your_next_turn"
        ], "the shorter clock wearing off must not take the longer one with it"

    def test_one_players_untap_does_not_clear_anothers(self, builder):
        game = position(builder, players=3)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "until_your_next_turn", player=2)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert len(game.state.unblockables) == 1, "player 1's untap is not theirs"
        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.active_player == 2
        assert game.state.unblockables == []

    def test_the_block_prohibition_clock_does_not_clear_this_one(self, builder):
        """Two tables, two clear-ups, one shared helper. A refactor that merged
        them would show up here first."""
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "until_your_next_turn", player=0)
        forbid_block(game.state, [mine], "until_your_next_turn", player=1)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.active_player == 1, "their untap step has run"
        assert game.state.unblockables, "player 1's untap cleared player 0's grant"
        assert game.state.block_prohibitions == [], "and it did clear their own"


class TestItOutlivesItsSource:
    def test_destroying_the_land_does_not_give_the_blockers_back(self, builder):
        """The first of the three things a static could not do: a static is on
        while its source is on the battlefield, so Rogue's Passage sacrificed or
        destroyed in response would undo its own ability."""
        game = position(builder, mine=(BEAR,), theirs=(BEAR,), lands=1)
        mine = only_oid(game, BEAR, 0)
        land = only_oid(game, "island", 0)
        make_unblockable(game.state, [mine], "this_turn", player=0, source=land)
        destroy(game.state, land)
        assert combat_mod.unblockable(game.state, mine)
        to_declare_blockers(game)
        assert blockers_offered(game) == []


class TestThePrimitiveRefusesWhatCannotBite:
    def test_an_empty_set_makes_nobody_unblockable(self, builder):
        game = position(builder)
        assert not make_unblockable(game.state, [], "this_turn", player=0)
        assert game.state.unblockables == []

    def test_until_your_next_turn_without_a_player_has_no_clock(self, builder):
        """Nothing would ever clear it, so a one-turn evasion would be forever."""
        game = position(builder)
        assert not make_unblockable(game.state, [7], "until_your_next_turn")
        assert game.state.unblockables == []

    def test_the_same_entry_is_recorded_once(self, builder):
        game = position(builder)
        assert make_unblockable(game.state, [7], "this_turn", player=0)
        assert not make_unblockable(game.state, [7], "this_turn", player=0)
        assert len(game.state.unblockables) == 1

    def test_an_unknown_duration_is_a_value_error(self, builder):
        game = position(builder)
        with pytest.raises(ValueError, match="unknown unblockable duration"):
            make_unblockable(game.state, [7], "this_combat")


class TestAnEliminatedPlayersClockNeverComes:
    def test_their_grants_are_dropped(self, builder):
        """"Until your next turn" is cleared in that player's untap step, and a
        player who has left never has another one."""
        game = position(builder, players=3)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "until_your_next_turn", player=2)
        game.state.players[2].life = 0
        sba.run(game.state)
        assert game.state.unblockables == []

    def test_a_turn_scoped_one_is_left_alone(self, builder):
        game = position(builder, players=3)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=2)
        game.state.players[2].life = 0
        sba.run(game.state)
        assert len(game.state.unblockables) == 1


class TestTheActivatedAbilityForm:
    """Rogue's Passage's own shape, and the one the authoring verifier cannot
    reach: it never activates an activated ability and never declares a combat,
    so this file is the only place the printed card is actually played."""

    def activate(self, game, target: int) -> None:
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and a.source is not None
            and game.state.objects[a.source].def_id == PASSAGE
            and any(t.id == target for t in a.targets)
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

    def board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [PASSAGE, "island", "island", "island", "island", BEAR])
            .battlefield(1, [BEAR])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_the_targeted_creature_cannot_be_blocked(self, builder):
        game = self.board(builder)
        mine = only_oid(game, BEAR, 0)
        self.activate(game, mine)
        assert [u.objects for u in game.state.unblockables] == [(mine,)]
        to_declare_blockers(game)
        assert blockers_offered(game) == []

    def test_the_source_is_recorded_and_is_not_the_target(self, builder):
        game = self.board(builder)
        mine = only_oid(game, BEAR, 0)
        land = only_oid(game, PASSAGE, 0)
        self.activate(game, mine)
        entry = game.state.unblockables[0]
        assert (entry.source, entry.player) == (land, 0)
        assert entry.objects == (mine,), "the ability's target, not its source"

    def test_it_can_aim_at_the_opponents_creature_too(self, builder):
        """Rogue's Passage says "target creature", not "target creature you
        control" -- a printed-characteristics filter could not tell the
        difference, which is the second reason a static cannot do this job."""
        game = self.board(builder)
        theirs = only_oid(game, BEAR, 1)
        self.activate(game, theirs)
        assert combat_mod.unblockable(game.state, theirs)

    def test_it_is_gone_next_turn(self, builder):
        game = self.board(builder)
        mine = only_oid(game, BEAR, 0)
        self.activate(game, mine)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.unblockables == []


class TestTheSpellForms:
    def test_a_sorcery_leaves_nothing_behind_to_own_it(self, builder):
        game = position(builder, hand=(SLIP,))
        mine = only_oid(game, BEAR, 0)
        cast(game, SLIP)
        entry = game.state.unblockables[0]
        assert (entry.objects, entry.duration) == ((mine,), "this_turn")
        to_declare_blockers(game)
        assert blockers_offered(game) == []

    def test_the_until_your_next_turn_form_records_its_player(self, builder):
        """Sly Instigator's clause, minus the goad it comes with."""
        game = position(builder, hand=(INSTIGATOR,))
        theirs = only_oid(game, BEAR, 1)
        cast(game, INSTIGATOR)
        entry = game.state.unblockables[0]
        assert (entry.objects, entry.duration, entry.player) == (
            (theirs,),
            "until_your_next_turn",
            0,
        )


def probe(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{U}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )
    )


class TestTheLoaderGuardsIt:
    def test_a_missing_objects_is_refused(self):
        """Unlike `cant_block` there is no "everything" reading to fall back on,
        so an absent `objects` is a mistake rather than a shorthand."""
        with pytest.raises(DslError, match="unblockable needs 'objects'"):
            probe({"op": "unblockable", "duration": "this_turn"})

    def test_a_missing_duration_is_refused(self):
        with pytest.raises(DslError, match="unblockable needs a 'duration'"):
            probe({"op": "unblockable", "objects": {"types": ["Creature"]}})

    def test_an_unknown_duration_is_refused(self):
        with pytest.raises(DslError, match="unknown unblockable duration"):
            probe(
                {
                    "op": "unblockable",
                    "objects": {"types": ["Creature"]},
                    "duration": "this_combat",
                }
            )

    def test_the_witness_shapes_compile(self, registry):
        ability = registry.get(PASSAGE).abilities[1]
        assert [e["op"] for e in ability.effects] == ["unblockable"]
        assert ability.effects[0]["duration"] == "this_turn"
        assert registry.get(INSTIGATOR).spell_effects[0]["duration"] == (
            "until_your_next_turn"
        )


class TestTheShippedCard:
    def test_rogues_passage_is_playable_and_says_the_line(self, real_registry):
        card = real_registry.get("rogue_s_passage")
        assert card is not None, "the card this capability was built for"
        ability = card.abilities[-1]
        assert [e["op"] for e in ability.effects] == ["unblockable"]
        assert ability.text == "{4}, {T}: Target creature can't be blocked this turn."
