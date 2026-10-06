"""A continuous sacrifice prohibition: "equipped creature can't be sacrificed".

Assault Suit. `cant_sacrifice` already existed as a **one-shot op** -- Call for
Aid's "you can't sacrifice those creatures this turn" -- and that mechanism
cannot be reused here, for the reason `cant_attack_you` is not the
`cant_attack_player` op either.

The op records a *set of permanents*, chosen when a spell resolved. An
Equipment's prohibition is a *filter*, recomputed every time it is asked, and
that difference is the whole card: the protection has to **end** when the Suit
is unequipped or leaves the battlefield, and it has to **move** when the Suit is
equipped to something else. A recorded set does neither.

Both mechanisms are read at one seam, `temp_effects.sacrifice_forbidden`, which
is asked at the two places a player *chooses* what to sacrifice rather than at
`zones.sacrifice`. That placement is 701.17b -- the cost becomes unpayable --
and it is also what stops the state-based-action loop spinning on a `sacrifice`
that silently returned False.

Both roads to a sacrifice are asserted below, because the printed rule does not
distinguish them: a **cost** (an outlet's activation) and an **effect** (an
edict). A fix that closed only one would leave the card readable and wrong.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.primitives import attach
from automtg.engine.temp_effects import sacrifice_forbidden
from automtg.engine.zones import destroy
from tests.conftest import oids_of

SUIT = "t_suit"  # protects the creature it is attached to
OPEN = "t_open_suit"  # protects every creature you control
ALTAR = "t_altar"  # "Sacrifice a creature: you gain 1 life"
BEAR = "t_cs_bear"
DORK = "t_cs_dork"


def board(builder, mine=(), theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def altar_offered(game) -> bool:
    """Is the sacrifice outlet's activation legal right now?

    The cost road: 701.17b says the cost becomes unpayable, so legality must not
    offer the activation at all rather than offering it and doing nothing.
    """
    return any(
        act.kind is ActionKind.ACTIVATE
        and game.state.objects[act.source].def_id == ALTAR
        for act in game.legal_actions()
    )


class TestTheProtectionFollowsTheEquipment:
    def test_an_equipped_creature_cannot_be_sacrificed(self, builder):
        game = board(builder, [SUIT, BEAR])
        suit, bear = oids_of(game, SUIT, 0)[0], oids_of(game, BEAR, 0)[0]
        attach(game.state, suit, bear)
        assert sacrifice_forbidden(game.state, bear)

    def test_an_unattached_suit_protects_nobody(self, builder):
        """`attached` matches nothing while `attached_to` is None, which is the
        answer that leaves the creature sacrificeable rather than the one that
        protects the whole board."""
        game = board(builder, [SUIT, BEAR])
        assert not sacrifice_forbidden(game.state, oids_of(game, BEAR, 0)[0])

    def test_another_creature_is_not_protected(self, builder):
        game = board(builder, [SUIT, BEAR, DORK])
        attach(game.state, oids_of(game, SUIT, 0)[0], oids_of(game, BEAR, 0)[0])
        assert not sacrifice_forbidden(game.state, oids_of(game, DORK, 0)[0])

    def test_moving_the_suit_moves_the_protection(self, builder):
        """The claim a recorded set cannot make."""
        game = board(builder, [SUIT, BEAR, DORK])
        suit = oids_of(game, SUIT, 0)[0]
        bear, dork = oids_of(game, BEAR, 0)[0], oids_of(game, DORK, 0)[0]
        attach(game.state, suit, bear)
        attach(game.state, suit, dork)
        assert sacrifice_forbidden(game.state, dork)
        assert not sacrifice_forbidden(game.state, bear)

    def test_destroying_the_suit_ends_the_protection(self, builder):
        """The wearing-off, and the other thing a recorded set cannot do."""
        game = board(builder, [SUIT, BEAR])
        suit, bear = oids_of(game, SUIT, 0)[0], oids_of(game, BEAR, 0)[0]
        attach(game.state, suit, bear)
        assert sacrifice_forbidden(game.state, bear)
        destroy(game.state, suit, cause="test")
        assert not sacrifice_forbidden(game.state, bear)


class TestTheCostRoad:
    """An outlet whose cost it would pay is simply not offered (701.17b)."""

    def test_the_outlet_is_offered_with_legal_fodder(self, builder):
        game = board(builder, [ALTAR, BEAR])
        assert altar_offered(game)

    def test_the_outlet_is_not_offered_when_the_only_creature_is_protected(self, builder):
        game = board(builder, [ALTAR, SUIT, BEAR])
        attach(game.state, oids_of(game, SUIT, 0)[0], oids_of(game, BEAR, 0)[0])
        assert not altar_offered(game)

    def test_a_second_unprotected_creature_keeps_it_payable(self, builder):
        """The cost is unpayable only when nothing legal is left -- the
        prohibition narrows the pool, it does not lock the outlet."""
        game = board(builder, [ALTAR, SUIT, BEAR, DORK])
        attach(game.state, oids_of(game, SUIT, 0)[0], oids_of(game, BEAR, 0)[0])
        assert altar_offered(game)


class TestTheEffectRoad:
    def test_a_protected_creature_is_not_in_the_edict_pool(self, builder):
        """"Each player sacrifices a creature" takes something else.

        Asked through `sacrifice_forbidden` directly, which is the predicate
        `op_sacrifice` filters its pool with -- the same seam the cost road
        reads, which is the point of there being one.
        """
        game = board(builder, [OPEN, BEAR, DORK])
        assert sacrifice_forbidden(game.state, oids_of(game, BEAR, 0)[0])
        assert sacrifice_forbidden(game.state, oids_of(game, DORK, 0)[0])

    def test_it_does_not_reach_across_the_table(self, builder):
        """`controller: "you"` is the filter, so the opponent's creature is
        still fodder -- an edict resolves against them normally."""
        game = board(builder, [OPEN], [BEAR])
        assert not sacrifice_forbidden(game.state, oids_of(game, BEAR, 1)[0])


class TestTheLoaderRefusesAFilterlessProhibition:
    def test_a_static_without_affects_is_refused(self):
        """A missing filter matches nothing, so the card would load, print
        "can't be sacrificed" and not do it. Read as a wildcard instead it would
        be worse: a one-permanent clause locking every outlet in the game."""
        card = CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Equipped creature can't be sacrificed.",
                "mana_cost": "{3}",
                "types": ["Artifact"],
                "subtypes": ["Equipment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Equipped creature can't be sacrificed.",
                        "effect": "cant_sacrifice",
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="cant_sacrifice"):
            compile_card(card)
