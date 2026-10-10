"""A filtered batch combat-damage trigger, and the creatures it names.

    Zurgo and Ojutai — "Whenever one or more Dragons you control deal combat
    damage to a player or battle, … You may return one of those Dragons to its
    owner's hand."

`EventType.CREATURES_DEALT_COMBAT_DAMAGE` has existed since Forth Eorlingas! and
already fired once per damaging player per damage step. Three things it could
not do, all of them silent:

**A `filter` on it matched nothing, for ever.** This event's subject is
deliberately a *player* — that is what makes `controller: "you"` read "creatures
**you control**" — so it is absent from `OBJECT_SUBJECT_TRIGGERS`, `_subject_oid`
returns `None`, and the generic filter branch in `_matches` short-circuits to
`False`. "One or more **Dragons** you control" written against it was an ability
that never fired and said nothing about it. So the filter is answered by its own
branch, read over the **damagers** and satisfied by any one of them, because the
printed line is "one or more".

**"Those Dragons" had no name to be reached by.** `_fire_damage_batch` has put
`damagers` on the event since the event existed and `EVENT_BINDING_KEYS` dropped
it. On a filtered trigger the binding is the *matching* subset, not the whole
batch: the Elf that got through beside the Dragons is on the payload and is not
what the card points at. `{"zone": "battlefield", "subtypes": ["Dragon"]}` is the
near miss and is larger still — it includes the Dragons that stayed home.

**"…or battle" could not be said.** `or_battle` widens the event to 506.2's
battle half. A widening, so it is off by default and checked as a presence: the
event now also fires for a swing that connected only with a battle, and every
card already written against it still means "to one or more players".

The near miss kept live as a contrast is `deals_combat_damage_to_player`, which
is per *connection*: three Wyrms through means three firings. That is the right
reading of "whenever **a** Wyrm you control deals combat damage" and the wrong
one of "whenever **one or more** Wyrms do", and both are exercised here side by
side so the difference cannot be argued away.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid, pass_until

WYRM = "t_bcd_wyrm"  # 2/2 Wyrm
ELF = "t_bcd_elf"  # 1/1 Elf, the creature the filter must not name
FLOCK = "t_bcd_flock"  # "one or more Wyrms … deal combat damage to a player"
PER_CONNECTION = "t_bcd_perconnection"  # the same words, per-connection event
PLAYERS_ONLY = "t_bcd_players_only"  # the unwidened batch trigger
OR_BATTLE = "t_bcd_or_battle"  # the same line with "or battle"
BOUNCE = "t_bcd_bounce"  # points return_to_hand at `damagers`
BATTLE = "t_battle_wall"  # Siege, defense 3 (tests/data/battles.cards.json)


def board(builder, *, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 5 + list(mine))
        .battlefield(1, list(theirs))
        .hand(0, [])
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def swing(game, attackers, *, at=None):
    """Declare every attacker, at ``at`` (an oid) or at the defending seat.

    Settled by running **past** this turn's postcombat main, compared as a
    ``(turn, step)`` pair. Neither `END_OF_COMBAT` nor `POSTCOMBAT_MAIN` is a
    state anybody is reliably asked about: a swing that triggers nothing holds
    priority nowhere between the block declaration and the next player's turn,
    so waiting for either step by name walks the game on for forty turns and
    the assertion is then about a board nobody built. The pair stops at the
    first decision at or after this turn's postcombat main, which is the
    opponent's precombat main at the latest -- after combat damage and after
    every trigger it queued, and before this player's next draw.
    """
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    for oid in attackers:
        _declare(game, oid, at)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    _settle(game)


class TestOneFiringForTheWholeSwing:
    def test_three_wyrms_draw_one_card(self, builder):
        """"One or more", which is one ability whatever the numbers are."""
        game = board(builder, mine=[FLOCK, WYRM, WYRM, WYRM])
        before = len(game.state.players[0].hand)
        swing(game, [oid for oid in game.state.battlefield if _is(game, oid, WYRM)])
        assert len(game.state.players[0].hand) - before == 1

    def test_the_per_connection_near_miss_draws_three(self, builder):
        """Kept live as the contrast. `deals_combat_damage_to_player` is the
        right event for "whenever **a** Wyrm you control deals combat damage"
        and the wrong one for "one or more"; the difference is three cards."""
        game = board(builder, mine=[PER_CONNECTION, WYRM, WYRM, WYRM])
        before = len(game.state.players[0].hand)
        swing(game, [oid for oid in game.state.battlefield if _is(game, oid, WYRM)])
        assert len(game.state.players[0].hand) - before == 3

    def test_one_wyrm_still_fires_it(self, builder):
        game = board(builder, mine=[FLOCK, WYRM])
        before = len(game.state.players[0].hand)
        swing(game, [only_oid(game, WYRM, 0)])
        assert len(game.state.players[0].hand) - before == 1

    def test_a_swing_with_no_wyrm_in_it_fires_nothing(self, builder):
        """The whole of the filter: before this branch existed the trigger
        matched nothing at all, so this passing alone would prove nothing --
        the two tests above are what make it a filter rather than a mute."""
        game = board(builder, mine=[FLOCK, ELF])
        before = len(game.state.players[0].hand)
        swing(game, [only_oid(game, ELF, 0)])
        assert len(game.state.players[0].hand) == before

    def test_one_wyrm_among_others_is_enough(self, builder):
        game = board(builder, mine=[FLOCK, WYRM, ELF])
        before = len(game.state.players[0].hand)
        swing(game, [only_oid(game, WYRM, 0), only_oid(game, ELF, 0)])
        assert len(game.state.players[0].hand) - before == 1


class TestThoseDragons:
    """The `damagers` binding, and the reason it is narrowed."""

    def test_the_binding_names_only_the_matching_creatures(self, builder):
        """"…return one of **those Wyrms**". With the Elf in the swing and no
        narrowing, the only creature the op could pick might be the Elf."""
        game = board(builder, mine=[BOUNCE, WYRM, ELF])
        wyrm, elf = only_oid(game, WYRM, 0), only_oid(game, ELF, 0)
        swing(game, [wyrm, elf])

        assert game.state.objects[wyrm].zone is Zone.HAND
        assert game.state.objects[elf].zone is Zone.BATTLEFIELD

    def test_it_is_the_creatures_that_connected(self, builder):
        """Not "every Wyrm you control" -- the near miss the gap record named.
        The Wyrm that stayed home is still on the battlefield."""
        game = board(builder, mine=[BOUNCE, WYRM, WYRM])
        wyrms = [oid for oid in game.state.battlefield if _is(game, oid, WYRM)]
        swing(game, wyrms[:1])

        returned = [o for o in wyrms if game.state.objects[o].zone is Zone.HAND]
        assert returned == wyrms[:1]


class TestOrBattle:
    def test_a_battle_only_swing_fires_the_widened_trigger(self, builder):
        game = board(builder, mine=[OR_BATTLE, WYRM], theirs=[BATTLE])
        life = game.state.players[0].life
        swing(game, [only_oid(game, WYRM, 0)], at=only_oid(game, BATTLE, 1))
        assert game.state.players[0].life - life == 1

    def test_it_does_not_fire_the_unwidened_one(self, builder):
        """The control, and the reason `or_battle` is off by default: "to one or
        more players" is printed on cards that say nothing about battles, and
        `_fire_damage_batch` now fires for a battle-only swing where it used to
        fire for nothing at all."""
        game = board(builder, mine=[PLAYERS_ONLY, WYRM], theirs=[BATTLE])
        life = game.state.players[0].life
        swing(game, [only_oid(game, WYRM, 0)], at=only_oid(game, BATTLE, 1))
        assert game.state.players[0].life == life

    def test_the_unwidened_one_still_fires_on_a_seat(self, builder):
        game = board(builder, mine=[PLAYERS_ONLY, WYRM], theirs=[BATTLE])
        life = game.state.players[0].life
        swing(game, [only_oid(game, WYRM, 0)])
        assert game.state.players[0].life - life == 1

    def test_a_mixed_swing_is_still_one_firing(self, builder):
        """510.2 makes the whole of combat damage one event, so a seat and a
        battle hit in the same step are one batch and one trigger -- which is
        why `or_battle` is a flag on this event and not a second event."""
        game = board(builder, mine=[OR_BATTLE, WYRM, WYRM], theirs=[BATTLE])
        wyrms = [oid for oid in game.state.battlefield if _is(game, oid, WYRM)]
        life = game.state.players[0].life
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
        battle = only_oid(game, BATTLE, 1)
        _declare(game, wyrms[0], battle)
        _declare(game, wyrms[1], None)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.FINISH_DECLARATION
            )
        )
        _settle(game)
        assert game.state.players[0].life - life == 1


class TestTheLoaderRefusesOrBattleElsewhere:
    def compile(self, event: str):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "x",
                    "name": "X",
                    "types": ["Enchantment"],
                    "abilities": [
                        {
                            "kind": "triggered",
                            "text": "…",
                            "trigger": {"event": event, "or_battle": True},
                            "effects": [
                                {"op": "draw", "player": "you", "amount": {"const": 1}}
                            ],
                        }
                    ],
                }
            )
        )

    def test_on_the_per_connection_event_it_is_refused(self):
        """It would load and do nothing: `_matches` reads the flag only on the
        batch event, so the printed half about battles would be missing and the
        card would look complete."""
        with pytest.raises(DslError, match="or_battle"):
            self.compile("deals_combat_damage_to_player")

    def test_on_the_batch_event_it_is_accepted(self):
        assert self.compile("creatures_deal_combat_damage")


def _settle(game) -> None:
    """Run to the first decision at or after this turn's postcombat main."""
    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    pass_until(game, lambda g: (g.state.turn, g.state.step) >= mark)


def _is(game, oid: int, card_id: str) -> bool:
    obj = game.state.objects.get(oid)
    return obj is not None and obj.def_id == card_id


def _declare(game, attacker: int, at: int | None) -> None:
    options = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == attacker
    ]
    game.apply(
        next(
            a
            for a in options
            if any(
                (ref.kind == "object" and ref.id == at)
                if at is not None
                else ref.kind == "player"
                for ref in a.targets
            )
        )
    )
