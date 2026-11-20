""""You may cast Zombie spells from your graveyard this turn."

Liliana, Untouched by Death's third ability. Rule 601.2 lets a card be cast from
wherever an effect permits, and this permission names a filter and a duration
and nothing else: no count, and no "exile it instead". So it is
`grant_graveyard_cast` with ``unmetered: true`` -- a standing grant on the table
that the turn ends, read beside the battlefield statics.

The two spellings the loader used to insist on are both wrong here.
``max_per_turn`` caps a sentence that has no cap, and ``grants_flashback`` exiles
a Zombie the card lets go back to the graveyard -- the creature that dies is the
whole loop, cast again the same turn. `grant_playable` is the near miss on the
other side: it snapshots the graveyard as it resolves, and the Zombie that died
afterwards is invisible to it. `TestTheLoop` is that difference.

The loader still refuses a grant that neither meters, exiles nor says
``unmetered``, because the cap a card prints is the easiest clause to drop. The
static never takes the flag: it has no end, and the turn is what bounds this.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until, settle_to_priority

WILL = "t_zombie_will"  # sorcery: grant_graveyard_cast, Zombie, unmetered
ZOMBIE = "t_gy_zombie"  # {B} 2/2 Zombie
IMP = "t_gy_imp"  # {B} 2/2 Imp -- the same body without the subtype


def position(builder, *, graveyard=(), battlefield=(), hand=(WILL,)):
    # An Imp kept in hand holds priority open after each cast: with nothing
    # left to do, the table passes the turn on its own.
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 6 + ["mountain"] * 4 + list(battlefield))
        .battlefield(1, ["plains"])
        .graveyard(0, list(graveyard))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [*hand, IMP])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast(game, oid: int) -> None:
    action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid)
    game.apply(action)
    settle_to_priority(game)


def cast_the_grant(game, grant: str = WILL) -> None:
    game._advance()
    oid = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == grant)
    cast(game, oid)


def castable(game, oid: int) -> bool:
    return any(a.kind is ActionKind.CAST and a.source == oid for a in game.legal_actions())


def in_graveyard(game, card_id: str) -> list[int]:
    return [o for o in game.state.players[0].graveyard if game.state.objects[o].def_id == card_id]


class TestTheFilter:
    def test_nothing_before_the_grant(self, builder):
        """The control."""
        game = position(builder, graveyard=[ZOMBIE])
        game._advance()
        assert not castable(game, in_graveyard(game, ZOMBIE)[0])

    def test_a_zombie_becomes_castable(self, builder):
        game = position(builder, graveyard=[ZOMBIE])
        oid = in_graveyard(game, ZOMBIE)[0]
        cast_the_grant(game)
        assert castable(game, oid)

    def test_a_non_zombie_does_not(self, builder):
        game = position(builder, graveyard=[IMP])
        oid = in_graveyard(game, IMP)[0]
        cast_the_grant(game)
        assert not castable(game, oid)


class TestNoCap:
    def test_every_zombie_can_go(self, builder):
        """No ``max_per_turn``: the third is as castable as the first."""
        game = position(builder, graveyard=[ZOMBIE, ZOMBIE, ZOMBIE])
        oids = in_graveyard(game, ZOMBIE)
        cast_the_grant(game)
        for oid in oids:
            cast(game, oid)
        assert all(game.state.objects[o].zone is Zone.BATTLEFIELD for o in oids)


class TestNoExile:
    def test_the_zombie_resolves_onto_the_battlefield(self, builder):
        """It goes where it normally would -- no flashback rider."""
        game = position(builder, graveyard=[ZOMBIE])
        oid = in_graveyard(game, ZOMBIE)[0]
        cast_the_grant(game)
        cast(game, oid)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD


class TestTheLoop:
    """A standing permission, not a snapshot of the graveyard."""

    def test_a_zombie_that_dies_later_is_castable_again(self, builder):
        game = position(builder, graveyard=[ZOMBIE])
        oid = in_graveyard(game, ZOMBIE)[0]
        cast_the_grant(game)
        cast(game, oid)
        move_object(game.state, oid, Zone.GRAVEYARD, cause="test")
        (again,) = in_graveyard(game, ZOMBIE)
        game._advance()

        assert castable(game, again), "the card that arrived after the grant is covered"
        cast(game, again)
        assert game.state.objects[again].zone is Zone.BATTLEFIELD


class TestItEndsWithTheTurn:
    def test_the_permission_is_gone_next_turn(self, builder):
        game = position(builder, graveyard=[ZOMBIE])
        oid = in_graveyard(game, ZOMBIE)[0]
        cast_the_grant(game)
        turn = game.state.turn
        pass_until(
            game,
            lambda g: g.state.turn > turn
            and g.state.active_player == 0
            and g.state.step is Step.PRECOMBAT_MAIN,
        )
        assert not castable(game, oid)


class TestTheLoader:
    def spell(self, **extra):
        return CardModel.model_validate(
            {
                "id": "t_probe_unmetered",
                "name": "Probe Unmetered",
                "mana_cost": "{B}",
                "types": ["Sorcery"],
                "spell_effects": [
                    {
                        "op": "grant_graveyard_cast",
                        "affects_spells": {"subtypes": ["Zombie"]},
                        **extra,
                    }
                ],
            }
        )

    def test_unmetered_alone_is_enough(self):
        compile_card(self.spell(unmetered=True))

    def test_silence_is_still_refused(self):
        """A grant that leaves the cap out has to say it meant to."""
        with pytest.raises(DslError, match="unmetered"):
            compile_card(self.spell())

    @pytest.mark.parametrize(
        "extra",
        [
            {"max_per_turn": 1},
            {"grants_flashback": True},
            {"escape": {"exile_from_graveyard": 3}},
        ],
    )
    def test_beside_another_brake_is_refused(self, extra):
        with pytest.raises(DslError, match="'unmetered' beside"):
            compile_card(self.spell(unmetered=True, **extra))

    def test_it_is_a_flag(self):
        with pytest.raises(DslError, match="is a flag"):
            compile_card(self.spell(unmetered=1))
