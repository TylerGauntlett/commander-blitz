"""Who moved this card, and how.

``ZONE_CHANGE`` has carried a ``cause`` since the beginning; what it never
carried was the *culprit*, because ``source`` on a zone change is the object
that moved and not the thing that moved it.  Without ``by`` no consumer can
build a sentence of the form "X destroys Y", which is why the client's log said
only "Grizzly Bears dies" and its board animated nothing at all.

These tests pin the payload, not the prose -- the words live in the client's
``logic/labels.ts``, which is the one place allowed to have them.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.primitives import damage_permanent
from commanderblitz.engine.sba import run as run_sba
from commanderblitz.engine.zones import bounce, destroy, exile, move_object, sacrifice
from tests.conftest import action_for_card, only_oid, pass_until


def zone_changes(game, *, to: str | None = None, card: str | None = None):
    """Every zone-change event, optionally narrowed to a destination or card."""
    return [
        event
        for event in game.state.events
        if event.type == "zone_change"
        and (to is None or event.data.get("to") == to)
        and (card is None or event.data.get("card") == card)
    ]


class TestTheEventPayload:
    def test_a_move_with_no_culprit_reports_none(self, builder):
        game = builder().battlefield(0, ["t_bear"]).build(advance=False)
        move_object(game.state, only_oid(game, "t_bear", 0), Zone.GRAVEYARD)
        (event,) = zone_changes(game, card="t_bear")
        assert event.data["by"] is None
        assert event.data["by_card"] is None

    def test_a_culprit_is_reported_by_oid_and_by_card_id(self, builder):
        game = builder().battlefield(0, ["t_bear", "t_sac_outlet"]).build(advance=False)
        bear = only_oid(game, "t_bear", 0)
        outlet = only_oid(game, "t_sac_outlet", 0)
        destroy(game.state, bear, by=outlet)
        (event,) = zone_changes(game, card="t_bear")
        assert event.data["cause"] == "destroyed"
        assert event.data["by"] == outlet
        # The id, not the oid: by the time the client draws this the culprit may
        # be in no zone it can see, so an oid alone would not resolve to a name.
        assert event.data["by_card"] == "t_sac_outlet"

    def test_the_culprit_is_named_even_when_it_leaves_in_the_same_pass(self, builder):
        """A creature that trades in combat is gone before the event goes out.

        `move_object` resolves `by_card` before it touches any zone list, which
        is the whole reason it is captured up front rather than at emit time.
        """
        game = builder().battlefield(0, ["t_bear"]).battlefield(1, ["t_bear"]).build(advance=False)
        mine = only_oid(game, "t_bear", 0)
        theirs = only_oid(game, "t_bear", 1)
        # Kill the culprit first, then move the victim naming it.
        move_object(game.state, theirs, Zone.GRAVEYARD)
        game.state.objects.pop(theirs, None)
        destroy(game.state, mine, by=theirs)
        (event,) = zone_changes(game, card="t_bear")[1:]
        assert event.data["by"] == theirs
        assert event.data["by_card"] is None  # gone, and honest about it

    def test_dies_and_leaves_battlefield_stay_untouched(self, builder):
        """Deliberately payload-free.

        Nothing reads a cause there, and a new key in a *fired* event's data can
        collide with a card's trigger bindings.  The client correlates with the
        `zone_change` that `move_object` always emits alongside.
        """
        game = builder().battlefield(0, ["t_bear"]).build(advance=False)
        destroy(game.state, only_oid(game, "t_bear", 0), by=99)
        for event in game.state.events:
            if event.type in ("dies", "leaves_battlefield"):
                assert "by" not in event.data
                assert "cause" not in event.data


class TestTheWrappers:
    def test_sacrifice(self, builder):
        game = builder().battlefield(0, ["t_bear", "t_sac_outlet"]).build(advance=False)
        outlet = only_oid(game, "t_sac_outlet", 0)
        sacrifice(game.state, only_oid(game, "t_bear", 0), by=outlet)
        (event,) = zone_changes(game, card="t_bear")
        assert (event.data["cause"], event.data["by"]) == ("sacrificed", outlet)

    def test_exile(self, builder):
        game = builder().battlefield(0, ["t_bear", "t_sac_outlet"]).build(advance=False)
        outlet = only_oid(game, "t_sac_outlet", 0)
        exile(game.state, only_oid(game, "t_bear", 0), by=outlet)
        (event,) = zone_changes(game, card="t_bear")
        assert (event.data["cause"], event.data["to"]) == ("exiled", "exile")
        assert event.data["by"] == outlet

    def test_bounce(self, builder):
        game = builder().battlefield(0, ["t_bear", "t_sac_outlet"]).build(advance=False)
        outlet = only_oid(game, "t_sac_outlet", 0)
        bounce(game.state, only_oid(game, "t_bear", 0), by=outlet)
        (event,) = zone_changes(game, card="t_bear")
        assert (event.data["cause"], event.data["to"]) == ("returned", "hand")
        assert event.data["by"] == outlet


class TestTheEffectOps:
    """The end of the wire: an op that removes something names its own source.

    `EffectContext` has always carried `source_oid`; `op_destroy` and friends
    simply threw it away, which is why a resolved removal spell could not be
    told apart from a legend-rule death once the card had left the board.
    """

    def test_a_removal_spell_names_itself(self, builder):
        game = (
            builder()
            .hand(0, ["t_removal"])
            .battlefield(0, ["plains"])
            .battlefield(1, ["t_bear"])
            .build()
        )
        spell = action_for_card(game, ActionKind.CAST, "t_removal")
        game.apply(spell)
        pass_until(game, lambda g: not g.state.stack)

        (event,) = zone_changes(game, card="t_bear")
        assert event.data["cause"] == "exiled"
        assert event.data["by_card"] == "t_removal"

    def test_a_sacrifice_cost_names_what_it_paid_for(self, builder):
        game = builder().battlefield(0, ["t_sac_outlet", "t_bear"]).build()
        outlet = only_oid(game, "t_sac_outlet", 0)
        activate = next(
            a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == outlet
        )
        game.apply(activate)
        pass_until(game, lambda g: not g.state.stack)

        (event,) = zone_changes(game, card="t_bear")
        assert event.data["cause"] == "sacrificed"
        assert event.data["by"] == outlet


class TestLethalDamage:
    def test_a_single_damage_source_is_named(self, builder):
        game = builder().battlefield(0, ["t_bear"]).battlefield(1, ["t_big"]).build(advance=False)
        bear = only_oid(game, "t_bear", 0)
        giant = only_oid(game, "t_big", 1)
        damage_permanent(game.state, bear, 2, giant)
        run_sba(game.state)
        (event,) = zone_changes(game, card="t_bear")
        assert event.data["cause"] == "lethal_damage"
        assert event.data["by"] == giant
        assert event.data["by_card"] == "t_big"

    def test_a_gang_block_declines_to_blame_anybody(self, builder):
        """Three blockers, no accusation.

        `last_damager` holds whichever source wrote last, which in a multi-block
        is an arbitrary one of them.  Naming it would be a lie the caption then
        repeats, so the cause degrades to a plain "lethal_damage".
        """
        game = (
            builder()
            .battlefield(0, ["t_bear"])
            .battlefield(1, ["t_bear", "t_bear"])
            .build(advance=False)
        )
        victim = only_oid(game, "t_bear", 0)
        first, second = (obj for obj in game.state.battlefield_objects(1))
        damage_permanent(game.state, victim, 1, first.oid)
        damage_permanent(game.state, victim, 1, second.oid)
        run_sba(game.state)
        (event,) = zone_changes(game, card="t_bear")[:1]
        assert event.data["cause"] == "lethal_damage"
        assert event.data["by"] is None

    def test_an_unattributed_source_stays_unattributed(self, builder):
        game = builder().battlefield(0, ["t_bear"]).build(advance=False)
        damage_permanent(game.state, only_oid(game, "t_bear", 0), 2, None)
        run_sba(game.state)
        (event,) = zone_changes(game, card="t_bear")
        assert event.data["by"] is None


class TestTheOtherStateBasedActions:
    def test_zero_toughness_and_the_legend_rule_name_nobody(self, builder):
        """Neither has a meaningful killer, so neither invents one."""
        game = builder().battlefield(0, ["t_legend", "t_legend"]).build(advance=False)
        run_sba(game.state)
        (event,) = zone_changes(game, card="t_legend")
        assert (event.data["cause"], event.data["by"]) == ("legend_rule", None)


class TestTheCommanderReplacement:
    def test_a_destroyed_commander_keeps_its_cause_and_changes_its_destination(self, builder):
        """`to` and `cause` answer different questions and must not be conflated.

        Rule 903.9a redirects the commander to the command zone while leaving
        the cause alone, so this event reads `to=command, cause=destroyed`.  The
        client's exit animation flies to the pile named by `to` for exactly this
        reason -- deriving the destination from the cause would send a destroyed
        commander to the graveyard, where it is not.
        """
        game = builder().commander(0, ["t_commander"]).build(advance=False)
        commander = game.state.players[0].command[0]
        move_object(game.state, commander, Zone.BATTLEFIELD)
        destroy(game.state, commander)

        event = zone_changes(game, card="t_commander")[-1]
        assert event.data["to"] == "command"
        assert event.data["cause"] == "destroyed"


class TestCleanup:
    def test_last_damager_is_cleared_with_the_ledger(self, builder):
        """Rule 514.2 wipes damage; the memory of who dealt it goes with it.

        Kept in lockstep with `damage_ledger` on purpose -- `sba` reads the two
        together, and a `last_damager` that outlived the ledger would attribute
        this turn's death to last turn's attacker.
        """
        game = builder().battlefield(0, ["t_big"]).battlefield(1, ["t_bear"]).build()
        damage_permanent(game.state, only_oid(game, "t_big", 0), 1, only_oid(game, "t_bear", 1))
        assert game.state.last_damager

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        assert not game.state.last_damager
        assert not game.state.damage_ledger
