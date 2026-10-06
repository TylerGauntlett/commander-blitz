""""Any player may cast spells as though they had flash."

Tidal Barracuda is the witness; Leyline of Anticipation and Vedalken Orrery are
the same permission scoped to one seat. It is the first thing in the engine that
widens a **timing** window, and `casting._timing_ok` is the seam it needed:

    if card.is_instant or Keyword.FLASH.value in card.keywords:
        return True
    return sorcery_speed

Printed characteristics and nothing else. The function took no `state` and no
`pid`, so no permanent on the board could be consulted from it at all — which is
the block three gap records recorded (this card, Borne Upon a Wind and Emergence
Zone). Widening it there rather than at one cast path reaches every zone a spell
can be cast from at once: hand, graveyard (flashback, retrace), exile (foretell,
adventure, plot), a Bolas's Citadel top and a second face all ask this same
question, and a permission written into the hand loop would pass every obvious
test and leave the other six wrong.

Three near misses, and each is a different wrong card:

- **`grant_keyword` with `flash`.** `_timing_ok` reads the *CardDef*'s printed
  keywords and never an object's granted ones, so it does nothing at all. Even
  reaching the object would be wrong twice more: `static_filter_keys` has no
  `zone`, so a static's filter cannot name the cards in a hand, and the printed
  line covers cards **drawn after** the source arrived, which no pool resolved
  once can reach. `TestAGrantedKeywordIsNotThis` pins the first of those.
- **`grant_playable`.** A *zone* permission (`playable_by`/`playable_turn`) —
  where a card may be cast from, at its printed timing. It moves no timing
  restriction, which is the axis this is about.
- **Dropping the sentence** and shipping the Barracuda's second line alone. That
  is a strictly different and strictly worse card, which is why the gap record
  refused to write a partial answer.

It **permits and never compels**. 101.2 still gives a "can't" the last word, so
`player_cant_cast_spells` — the Barracuda's own other half — is unaffected, and
`TestThePermissionDoesNotBeatAProhibition` is that claim on the one card that
prints both sentences at once.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import legality
from automtg.engine.enums import ActionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.player_statics import player_casts_as_though_flash

BARRACUDA = "t_barracuda"  # any player
ORRERY = "t_orrery"  # you
FAIRWEATHER = "t_own_turn_orrery"  # you, during your turn only
SORCERY = "t_sorcery"  # {R} sorcery, no flash of its own
CREATURE = "t_flash_sorcery_target"  # {R} creature, likewise
BOLT = "t_bolt"  # {R} instant -- the control: always castable
VOICE = "t_quiet_voice"  # opponents can't cast spells, on any turn
MOUNTAIN = "mountain"


def position(
    builder,
    *source: str,
    active: int = 0,
    hand0: tuple[str, ...] = (SORCERY,),
    hand1: tuple[str, ...] = (SORCERY,),
    board1: tuple[str, ...] = (),
    step: Step = Step.PRECOMBAT_MAIN,
):
    """Player 0 controls the permission; player 1 is the other seat.

    Both have Mountains, so the only thing that can withhold a cast is the
    timing window. ``active`` is whose turn it is — which decides who is at
    sorcery speed and so which answers are about the permission at all.
    """
    return (
        builder(players=2)
        .battlefield(0, [MOUNTAIN] * 3 + list(source))
        .battlefield(1, [MOUNTAIN] * 3 + list(board1))
        .hand(0, list(hand0))
        .hand(1, list(hand1))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(step)
        .active(active)
        .build(advance=False)
    )


def can_cast(game, pid: int, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in legality._priority_actions(game.state, pid)
    )


class TestTheSorcerySpeedWindowIsTheBaseline:
    """Without the permission, nothing here is castable off-turn.

    The control for every assertion below: if a plain sorcery were castable on
    somebody else's turn anyway, none of the rest would mean anything.
    """

    def test_its_owner_casts_it_on_their_own_turn(self, builder):
        game = position(builder, active=0)
        assert can_cast(game, 0, SORCERY)

    def test_but_not_on_the_opponents_turn(self, builder):
        game = position(builder, active=1)
        assert not can_cast(game, 0, SORCERY)

    def test_an_instant_is_castable_either_way(self, builder):
        """The other control: the window, not the board, is what moves."""
        game = position(builder, active=1, hand0=(BOLT,))
        assert can_cast(game, 0, BOLT)


class TestThePermissionLiftsTheWindow:
    def test_a_sorcery_on_the_opponents_turn(self, builder):
        game = position(builder, ORRERY, active=1)
        assert can_cast(game, 0, SORCERY)

    def test_a_creature_spell_too(self, builder):
        """Not a sorcery-only permission: "spells" is every spell."""
        game = position(builder, ORRERY, active=1, hand0=(CREATURE,))
        assert can_cast(game, 0, CREATURE)

    def test_it_still_works_on_your_own_turn(self, builder):
        """A permission cannot take anything away."""
        game = position(builder, ORRERY, active=0)
        assert can_cast(game, 0, SORCERY)

    def test_in_a_step_that_is_not_a_main_phase(self, builder):
        """Sorcery speed is an empty stack *and* a main phase, and the printed
        line lifts the whole of it — Vedalken Orrery casts during combat."""
        game = position(builder, ORRERY, active=0, step=Step.DECLARE_BLOCKERS)
        assert can_cast(game, 0, SORCERY)

    def test_without_the_source_the_window_returns(self, builder):
        """The wearing-off: it is a static, not a turn flag."""
        game = position(builder, ORRERY, active=1)
        orrery = next(
            o for o in game.state.battlefield if game.state.objects[o].def_id == ORRERY
        )
        game.state.battlefield.remove(orrery)
        game.state.bump_chars()
        assert not can_cast(game, 0, SORCERY)


class TestWhoTheStaticNames:
    """`affects_player` is the difference between the Barracuda and the Orrery."""

    def test_the_orrery_does_not_help_the_opponent(self, builder):
        game = position(builder, ORRERY, active=0)
        assert not can_cast(game, 1, SORCERY), '"You may cast" is one seat'

    def test_the_barracuda_helps_both(self, builder):
        game = position(builder, BARRACUDA, active=0)
        assert can_cast(game, 0, SORCERY)
        assert can_cast(game, 1, SORCERY), '"Any player" includes the other one'

    def test_the_barracudas_owner_is_a_player_too(self, builder):
        """"Any player" is not "each opponent"."""
        game = position(builder, BARRACUDA, active=1)
        assert can_cast(game, 0, SORCERY)

    @pytest.mark.parametrize("pid", [0, 1])
    def test_the_reader_agrees_with_the_offer(self, builder, pid):
        """The drift test: the predicate and the action list are one claim."""
        game = position(builder, BARRACUDA, active=0)
        assert player_casts_as_though_flash(game.state, pid)


class TestTheConditionIsHonoured:
    """An "as long as…" clause on a player-wide static is read, not dropped."""

    def test_it_grants_on_its_own_turn(self, builder):
        game = position(builder, FAIRWEATHER, active=0, step=Step.DECLARE_BLOCKERS)
        assert can_cast(game, 0, SORCERY)

    def test_and_not_on_the_other_one(self, builder):
        game = position(builder, FAIRWEATHER, active=1)
        assert not can_cast(game, 0, SORCERY)
        assert not player_casts_as_though_flash(game.state, 0)


class TestThePermissionDoesNotBeatAProhibition:
    """101.2: when one effect says "may" and another says "can't", "can't" wins.

    The Barracuda prints both sentences, which is what makes this the card that
    has to be right about it: its own second line stops each opponent during its
    controller's turn, and the flash permission must not reopen that door.
    """

    def test_a_locked_opponent_still_cannot_cast(self, builder):
        """Player 0 controls both halves; player 1 holds an instant it may not cast."""
        game = position(builder, BARRACUDA, VOICE, active=0, hand1=(BOLT,))
        assert not can_cast(game, 1, BOLT), "the prohibition outranks the permission"

    def test_and_without_the_lock_that_same_instant_is_castable(self, builder):
        """The control: it is the prohibition doing it, not the board."""
        game = position(builder, BARRACUDA, active=0, hand1=(BOLT,))
        assert can_cast(game, 1, BOLT)

    def test_and_the_permission_still_reaches_its_owner(self, builder):
        """The lock names opponents, so the controller keeps the flash."""
        game = position(builder, BARRACUDA, VOICE, active=1)
        assert can_cast(game, 0, SORCERY)


class TestAGrantedKeywordIsNotThis:
    """The near miss, kept as a claim: `_timing_ok` reads printed keywords.

    A card granted `flash` by a continuous effect is still not castable off-turn,
    which is exactly why this could not have been built as a `grant_keyword`.
    """

    def test_a_sorcery_wearing_granted_flash_is_still_a_sorcery(self, builder):
        from automtg.engine.structs import TempEffect

        game = position(builder, active=1)
        oid = game.state.players[0].hand[0]
        game.state.objects[oid].until_eot.append(TempEffect(kind="keyword", keyword="flash"))
        game.state.bump_chars()
        assert not can_cast(game, 0, SORCERY)


class TestTheLoaderRefusesAFilteredPermission:
    def card(self, **extra):
        return {
            "id": "t_probe_flash",
            "name": "Probe Flash",
            "mana_cost": "{4}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "static",
                    "text": "You may cast spells as though they had flash.",
                    "effect": "cast_as_though_flash",
                    "affects_player": "you",
                    **extra,
                }
            ],
        }

    def test_a_spell_filter_is_refused(self):
        """"You may cast **Spirit** spells as though they had flash" would load
        clean and hand the permission to every spell — a strictly better card."""
        with pytest.raises(DslError, match="cast_as_though_flash"):
            compile_card(CardModel.model_validate(self.card(affects={"types": ["Creature"]})))

    def test_an_amount_is_refused(self):
        with pytest.raises(DslError, match="cast_as_though_flash"):
            compile_card(CardModel.model_validate(self.card(amount={"const": 1})))

    def test_it_needs_a_player(self):
        card = dict(self.card())
        del card["abilities"][0]["affects_player"]
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(card))
