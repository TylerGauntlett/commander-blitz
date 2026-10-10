"""A zone-filtered casting prohibition that lasts as long as its source.

    Your opponents can't cast spells from anywhere other than their hands.
    -- Drannith Magistrate

Avatar's Wrath prints the same sentence behind "until your next turn", and the
engine already had that: the `cant_cast_spells_from_zones` op writes a timed
`structs.CastLock` row, read back by `primitives.cast_locked_zones` on every road
a cast takes. What it lacked was the clockless form. The nearest pieces both
miss:

* `cant_cast_spells`, the player-wide static, is total or filtered only by the
  printed spell, so it has no "from". Written bare on Magistrate it forbids the
  opponents' **hand** casts too -- a far harsher card, and silently so.
* The op is a one-shot with a clock (`CAST_LOCK_DURATIONS` is ``this_turn`` and
  ``until_your_next_turn``). Fired from an enters trigger it would expire while
  Magistrate is still on the battlefield, and outlive it if it left first.

So the static form is a `cant_cast_spells_from_zones` **static** taking the op's
own `zones` / `except_zones`, and it has no reader of its own: the cast-lock
union unions it in, so the three roads that already ask that question --
`casting._cast_actions` (every priority-window cast, from graveyard, exile,
library top and the command zone alike), `suspend.cast_for_free` and
`replacements._offer_cast` (the resolution-time casts: cascade, suspend,
rebound, madness) -- ask about Magistrate by the same call. 101.2: the "can't"
beats every "may", so flashback, foretell, Bolas's Citadel and cascade all lose
to it.

Commanders are the line that matters most in this format. A commander is cast
from the **command zone** (903.8), which is "anywhere other than their hands",
so Magistrate stops an opponent casting their commander at all for as long as it
stays -- tested explicitly below.

What it does **not** stop, on purpose: the opponents' hand casts, its own
controller's casts, and the special action of foretelling (116.2c), which puts a
card into exile but casts nothing.

Witness: Drannith Magistrate (`drannith_magistrate` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.casting import _cast_actions
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import cast_locked_zones
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

MAGISTRATE = "t_hand_only_magistrate"  # opponents cast from hands only
GRAVE_WARDEN = "t_graveyard_warden"  # opponents can't cast from graveyards
CURFEW = "t_hand_only_curfew"  # Magistrate's lock, during your turn only
RECALL = "t_ember_recall"  # {R} instant, flashback {R} -- hand and graveyard at once
WARDEN = "t_ashen_warden"  # {R} 1/1, the commander
CITADEL = "t_citadel"  # cast from the top of your library, paying life
CASCADER = "t_cascader"  # cascade
FORETELLER = "t_foreteller"  # {2}{R} sorcery, foretell {R}
BEAR = "t_bear"  # {1}{G}, mana value 2


def board(builder, *, lock=MAGISTRATE, locker=0, caster_graveyard=False):
    """``locker`` controls the lock; p1 holds a Recall, has one in the yard and a commander.

    Mountains enough for every line, so each refusal below is the lock's and
    not the mana's.
    """
    b = (
        builder(players=2)
        .battlefield(0, ["mountain"] * 3)
        .hand(1, [RECALL])
        .graveyard(1, [RECALL])
        .commander(1, [WARDEN])
        .battlefield(1, ["mountain"] * 3)
        # Libraries, so the turn-crossing tests cross turns rather than end
        # the game on an empty draw.
        .library(0, ["mountain"] * 20)
        .library(1, ["mountain"] * 20)
        .step(Step.PRECOMBAT_MAIN)
    )
    if lock is not None:
        b = b.battlefield(locker, [lock])
    if caster_graveyard:
        b = b.graveyard(0, [RECALL])
    return b.build()


def lines(game, pid, zone):
    """Every cast line offered to ``pid`` for a card sitting in ``zone``.

    `_cast_actions` with the sorcery window open, as the timed lock's test asks
    it: the claim is about what legality *builds*, and the interesting seat is
    usually the one without priority.
    """
    return [
        a
        for a in _cast_actions(game.state, pid, sorcery_speed=True)
        if game.state.objects[a.source].zone.value == zone
    ]


def oid_of(game, def_id):
    return next(o for o, obj in game.state.objects.items() if obj.def_id == def_id)


class TestTheHandStaysOpenWhileTheOtherZonesShut:
    """"…from anywhere **other than their hands**", which `cant_cast_spells` can't say."""

    def test_the_locked_player_may_still_cast_from_hand(self, builder):
        assert len(lines(board(builder), 1, "hand")) == 1

    def test_the_locked_player_may_not_flash_a_card_back(self, builder):
        # The same card id in the other zone: only where it sits differs.
        assert lines(board(builder), 1, "graveyard") == []

    def test_without_the_magistrate_every_line_exists(self, builder):
        game = board(builder, lock=None)
        assert len(lines(game, 1, "hand")) == 1
        assert len(lines(game, 1, "graveyard")) == 1
        assert len(lines(game, 1, "command")) == 1

    def test_its_controller_is_not_locked(self, builder):
        # "**Your opponents** can't cast."
        game = board(builder, caster_graveyard=True)
        assert len(lines(game, 0, "graveyard")) == 1
        assert lines(game, 1, "graveyard") == []

    def test_the_shut_zones_are_every_castable_zone_but_the_hand(self, builder):
        # Resolved at load time from `except_zones`, by the op's own helper,
        # so the static and Avatar's Wrath shut exactly the same doors.
        game = board(builder)
        assert cast_locked_zones(game.state, 1) == frozenset(
            {"library", "battlefield", "graveyard", "exile", "stack", "command"}
        )
        assert cast_locked_zones(game.state, 0) == frozenset()

    def test_the_positive_spelling_shuts_only_what_it_names(self, builder):
        game = board(builder, lock=GRAVE_WARDEN)
        assert lines(game, 1, "graveyard") == []
        assert len(lines(game, 1, "command")) == 1
        assert len(lines(game, 1, "hand")) == 1


class TestCommandersCannotBeCast:
    """903.8: a commander is cast from the command zone, which is not a hand."""

    def test_the_opponent_cannot_cast_their_commander(self, builder):
        assert lines(board(builder), 1, "command") == []

    def test_the_commander_is_not_offered_through_legal_actions_either(self, builder):
        # The whole priority-window offer, on the locked player's own turn --
        # not just the internal list -- so no other path slips it through.
        game = board(builder)
        pass_until(
            game,
            lambda g: (
                g.state.active_player == 1
                and g.state.step is Step.PRECOMBAT_MAIN
                and (d := g.pending()) is not None
                and d.player == 1
            ),
        )
        warden = oid_of(game, WARDEN)
        assert game.state.objects[warden].zone is Zone.COMMAND
        assert not [
            a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == warden
        ]

    def test_the_controllers_own_commander_is_castable(self, builder):
        game = board(builder, locker=1)
        # p1 controls the Magistrate now, so p1's commander is p1's to cast.
        assert len(lines(game, 1, "command")) == 1


class TestEveryOtherRoadIsShut:
    """The reader is the timed lock's, so every road that asks it asks this."""

    def test_the_top_of_the_library(self, builder):
        def citadel_board(lock):
            b = (
                builder(players=2)
                .battlefield(1, [CITADEL])
                .library(1, [BEAR] + ["forest"] * 5)
                .step(Step.PRECOMBAT_MAIN)
            )
            if lock:
                b = b.battlefield(0, [MAGISTRATE])
            # Not advanced: p0 has no library, and the Bear has to stay on top.
            return b.build(advance=False)

        assert len(lines(citadel_board(False), 1, "library")) == 1
        assert lines(citadel_board(True), 1, "library") == []

    def test_a_foretold_card_in_exile(self, builder):
        """Foretelling is a special action and stays legal; casting it later does not."""

        def foretold(lock):
            b = (
                builder(players=2)
                .battlefield(1, ["mountain"] * 3)
                .hand(1, [FORETELLER])
                .library(0, ["mountain"] * 20)
                .library(1, ["mountain"] * 20)
            )
            if lock:
                b = b.battlefield(0, [MAGISTRATE])
            game = b.build()

            def p1_main(turn):
                return lambda g: (
                    g.state.turn >= turn
                    and g.state.active_player == 1
                    and g.state.step is Step.PRECOMBAT_MAIN
                    and (d := g.pending()) is not None
                    and d.player == 1
                )

            pass_until(game, p1_main(2))
            fore = next(a for a in game.legal_actions() if a.kind is ActionKind.SUSPEND)
            game.apply(fore)
            pass_until(game, p1_main(game.state.turn + 1))
            return game

        # One line per target; the claim is only that some exist.
        assert lines(foretold(False), 1, "exile")
        game = foretold(True)
        bolt = oid_of(game, FORETELLER)
        assert game.state.objects[bolt].zone is Zone.EXILE, "the foretell itself happened"
        assert lines(game, 1, "exile") == []

    def test_a_cascade_out_of_exile(self, builder):
        """`suspend.cast_for_free`: the resolution-time road, which never passes
        through `_cast_actions`. A free cast is still a cast (601.2b)."""

        def cascade(lock):
            b = builder(players=2).battlefield(1, [CASCADER]).library(1, [BEAR, "forest"])
            if lock:
                b = b.battlefield(0, [MAGISTRATE])
            game = b.build(advance=False)
            src = oid_of(game, CASCADER)
            ctx = EffectContext(state=game.state, controller=1, source_oid=src)
            gen = OPS["cascade"](ctx, {"op": "cascade"})
            send = None
            while True:
                try:
                    gen.send(send)
                except StopIteration:
                    break
                send = [0]  # yes, cast it
            return game

        assert [item.def_id for item in cascade(False).state.stack] == [BEAR]
        assert cascade(True).state.stack == []


class TestItLastsExactlyAsLongAsTheSource:
    """No clock: the static is gathered while its source is on the battlefield."""

    def test_the_lock_lifts_when_the_magistrate_leaves(self, builder):
        game = board(builder)
        assert lines(game, 1, "command") == []
        move_object(game.state, oid_of(game, MAGISTRATE), Zone.GRAVEYARD)
        assert len(lines(game, 1, "command")) == 1
        assert len(lines(game, 1, "graveyard")) == 1

    def test_it_holds_across_turns(self, builder):
        # The boundary the timed lock has and this must not: two full turns on,
        # with nothing removed, the lock still stands.
        game = board(builder)
        start = game.state.turn
        pass_until(game, lambda g: g.state.turn == start + 2)
        assert not game.over and game.state.turn == start + 2
        assert lines(game, 1, "graveyard") == []
        assert game.state.cast_locks == [], "no timed row was written to sweep"

    def test_an_as_long_as_condition_is_honoured(self, builder):
        # "During your turn": shut on the locker's turn, open on the other's.
        game = board(builder, lock=CURFEW)
        assert game.state.active_player == 0
        assert lines(game, 1, "graveyard") == []
        pass_until(game, lambda g: g.state.active_player == 1)
        assert len(lines(game, 1, "graveyard")) == 1


class TestTheLoaderRefusesTheWrongCard:
    """Every refusal is a card that would otherwise load as a different lock."""

    def _card(self, **extra):
        static = {
            "kind": "static",
            "text": "Your opponents can't cast spells from anywhere other than their hands.",
            "effect": "cant_cast_spells_from_zones",
            "affects_player": "opponent",
            "except_zones": ["hand"],
        }
        static.update(extra)
        static = {k: v for k, v in static.items() if v is not None}
        return CardModel.model_validate(
            {
                "id": "t_magistrate_probe",
                "name": "Magistrate Probe",
                "mana_cost": "{1}{W}",
                "oracle_text": static["text"],
                "types": ["Creature"],
                "power": 1,
                "toughness": 3,
                "abilities": [static],
            }
        )

    def test_the_printed_shape_loads(self):
        assert compile_card(self._card()) is not None

    def test_neither_zone_list_is_refused(self):
        # Neither would lock nothing while printing a prohibition.
        with pytest.raises(DslError, match="exactly one of"):
            compile_card(self._card(except_zones=None))

    def test_both_zone_lists_are_refused(self):
        with pytest.raises(DslError, match="exactly one of"):
            compile_card(self._card(zones=["graveyard"]))

    def test_an_unknown_zone_is_refused(self):
        # A typo in `except_zones` would lock one more door than printed.
        with pytest.raises(DslError, match="unknown zone"):
            compile_card(self._card(except_zones=["hands"]))

    def test_a_spell_filter_is_refused(self):
        # The reader answers per zone and never sees the spell, so a filter
        # would load as a lock on every spell from those zones.
        with pytest.raises(DslError, match="affects_spells"):
            compile_card(self._card(affects_spells={"types": ["Creature"]}))

    def test_a_missing_affects_player_is_refused(self):
        with pytest.raises(DslError, match="affects_player"):
            compile_card(self._card(affects_player=None))

    def test_zones_on_another_static_are_refused(self):
        # Read by nothing there: a "from" clause silently dropped.
        with pytest.raises(DslError, match="belong to cant_cast_spells_from_zones"):
            compile_card(self._card(effect="cant_cast_spells"))
