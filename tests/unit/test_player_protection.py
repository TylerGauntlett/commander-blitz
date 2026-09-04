""""Until your next turn, you gain protection from everything." -- 702.16b/d/i

    Teferi's Protection -- "Until your next turn, your life total can't change
    and you gain protection from everything. All permanents you control phase
    out."
    The One Ring -- "When The One Ring enters, if you cast it, you gain
    protection from everything until your next turn."

Protection existed only as a property of a *permanent*.
`characteristics.protection_from` walks `_battlefield_statics` and matches each
static's `affects` against an object; `static_filter_keys` has no way to name a
seat; and `op_grant_protection` resolved its recipients through `choose_objects`
and then skipped every oid that was not `on_battlefield`. So there was no way in
from either end, and no player-side reader to come in to.

Three claims are pinned here, and the first is the one an implementation shaped
like hexproof would get wrong:

* **It stops anyone, its controller included.** Your own Bolt cannot be pointed
  at you. That is what protection says and what `can_be_targeted` already
  enforces on the object side.
* **"Everything" is answered before the source is read at all.** No set built
  from types, subtypes and colours can contain a colourless source, so the
  sentinel short-circuits rather than joining the intersection.
* **It ends in your untap step, not at cleanup.** "Until your next turn" is a
  seat's clock, not a turn number -- eliminate somebody and it moves -- which is
  the clock detain, block prohibitions and unblockables already share.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import player_protected_from
from automtg.engine.enums import ActionKind
from automtg.engine.primitives import damage_player
from automtg.engine.structs import PROTECTION_EVERYTHING, PlayerProtection
from tests.conftest import _default_answer, action_for_card, oids_of

GRANT = "t_player_protection"  # until your next turn, protection from everything
BOLT = "t_bolt"  # deals 3 damage to any target
BEAR = "t_bear"


def board(builder, *, protected: int = 0):
    """A position with the protection already installed on ``protected``."""
    game = (
        builder(players=2)
        # Mountains, not Plains: a Bolt nobody can pay for is offered as no
        # action at all, and the target set would be empty for the wrong reason.
        .battlefield(0, ["mountain"] * 4)
        .battlefield(1, [BEAR])
        .hand(0, [BOLT])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .active(0)
        .build()
    )
    game.state.player_protections.append(
        PlayerProtection(player=protected, quality=PROTECTION_EVERYTHING)
    )
    game.state.bump_chars()
    return game


def player_targets(game, card_id: str, caster: int) -> set[int]:
    """Which seats ``caster`` is offered as targets for ``card_id``."""
    return {
        ref.id
        for action in game.legal_actions()
        if action.kind is ActionKind.CAST
        and action.source is not None
        and game.state.objects[action.source].def_id == card_id
        and game.state.objects[action.source].controller == caster
        for ref in action.targets
        if ref.kind == "player"
    }


def settle(game, limit: int = 100) -> None:
    """Let the stack empty, answering passively."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None or not game.state.stack:
            return
        game.apply(_default_answer(game, decision))


def run_to_next_turn(game, limit: int = 400) -> None:
    turn = game.state.turn
    for _ in range(limit):
        if game.over or game.state.turn != turn:
            return
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        preferred = (
            [a for a in actions if a.kind is ActionKind.PASS]
            or [a for a in actions if a.kind is ActionKind.FINISH_DECLARATION]
            or [a for a in actions if a.kind is ActionKind.NO]
            or actions
        )
        game.apply(preferred[0])


class TestTargeting:
    def test_the_protected_player_cannot_target_themselves(self, builder):
        """The half a hexproof-shaped implementation gets wrong."""
        game = board(builder)
        assert 0 not in player_targets(game, BOLT, caster=0)

    def test_the_other_seat_is_still_a_legal_target(self, builder):
        game = board(builder)
        assert 1 in player_targets(game, BOLT, caster=0)

    def test_without_the_protection_the_seat_is_offered(self, builder):
        """The control: the seat vanishes because of this and nothing else."""
        game = board(builder)
        game.state.player_protections.clear()
        game.state.bump_chars()
        assert 0 in player_targets(game, BOLT, caster=0)


class TestDamage:
    def test_damage_to_the_protected_player_is_prevented(self, builder):
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        life = game.state.players[0].life

        dealt = damage_player(game.state, 0, 3, bear)

        assert dealt == 0
        assert game.state.players[0].life == life

    def test_it_announces_the_prevention(self, builder):
        """`fire`, not `emit` -- a prevention nothing announces is invisible."""
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        mark = len(game.state.events)

        damage_player(game.state, 0, 3, bear)

        prevented = [e for e in game.state.events[mark:] if e.type == "damage_prevented"]
        assert len(prevented) == 1

    def test_the_unprotected_seat_still_takes_it(self, builder):
        game = board(builder)
        life = game.state.players[1].life
        assert damage_player(game.state, 1, 3, oids_of(game, BEAR)[0]) == 3
        assert game.state.players[1].life == life - 3


class TestEverythingMeansEverything:
    def test_a_source_sharing_no_quality_is_still_stopped(self, builder):
        """A colourless, subtypeless source: no quality set could hold it."""
        game = board(builder)
        mountain = oids_of(game, "mountain")[0]
        assert player_protected_from(game.state, 0, mountain)

    def test_a_missing_source_is_never_protection(self, builder):
        game = board(builder)
        assert not player_protected_from(game.state, 0, None)


class TestTheWearingOff:
    def test_it_survives_the_cleanup_step(self, builder):
        """"Until your next turn" outlasts the turn it was installed in.

        The position starts on the protected player's own turn, which is when
        both printed cards are cast; one turn on is the opponent's, and the
        cleanup step in between sweeps every `this_turn` table there is.
        """
        game = board(builder)
        run_to_next_turn(game)
        assert game.state.active_idx == 1
        assert player_protected_from(game.state, 0, oids_of(game, BEAR)[0])

    def test_it_ends_in_the_protected_players_untap_step(self, builder):
        game = board(builder)
        run_to_next_turn(game)  # the opponent's turn
        run_to_next_turn(game)  # back to ours -- the untap step clears it
        assert game.state.active_idx == 0
        assert not player_protected_from(game.state, 0, oids_of(game, BEAR)[0])


class TestCastingTheSpell:
    def test_resolving_it_installs_the_protection(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 4)
            .battlefield(1, [BEAR])
            .hand(0, [GRANT])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, GRANT))
        settle(game)
        assert player_protected_from(game.state, 0, oids_of(game, BEAR)[0])
        assert not player_protected_from(game.state, 1, oids_of(game, BEAR)[0])


class TestTheLoaderRefusesNonsense:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_bad_protection",
                "name": "Bad Protection",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "types": ["Instant"],
                "colors": ["W"],
                "color_identity": ["W"],
                "spell_effects": [effect],
            }
        )

    def test_a_grant_with_no_recipient(self):
        with pytest.raises(DslError, match="who gains it"):
            compile_card(self._card({"op": "grant_protection", "from_everything": True}))

    def test_a_grant_with_no_quality(self):
        with pytest.raises(DslError, match="needs a quality"):
            compile_card(self._card({"op": "grant_protection", "player": "you"}))

    def test_a_duration_on_an_objects_grant(self):
        """An object's grant lives on `until_eot`; nothing else sweeps it."""
        with pytest.raises(DslError, match="duration"):
            compile_card(
                self._card(
                    {
                        "op": "grant_protection",
                        "objects": {"zone": "battlefield", "controller": "you"},
                        "from_everything": True,
                        "duration": "until_your_next_turn",
                    }
                )
            )

    def test_an_unknown_duration(self):
        with pytest.raises(DslError, match="unknown protection duration"):
            compile_card(
                self._card(
                    {
                        "op": "grant_protection",
                        "player": "you",
                        "from_everything": True,
                        "duration": "forever",
                    }
                )
            )
