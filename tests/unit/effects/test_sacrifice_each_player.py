"""`sacrifice` with `players`: "each player sacrifices", as one action, and the
total last-known power of what it took.

**Reign of the Pit** is the witness. "Each player sacrifices a creature of their
choice. Create an X/X black Demon creature token with flying, where X is the
total power of the creatures sacrificed this way."

Two rules make the card, and the `for_each_player` loop over `sacrifice` that
every other edict is written with gets both wrong:

- **101.4 and 701.21a.** "Each player sacrifices" is one sacrifice. Each player
  chooses in APNAP order, seeing the choices before theirs, and then everything
  chosen is sacrificed at the same time. The loop sacrifices on every pass, so
  the second player's creature is measured after the first player's left -- a
  lord that pumped it has already gone. `TestTheSacrificeIsSimultaneous` is
  that board.
- **608.2h and last-known information.** "The total power of the creatures
  sacrificed this way" is each creature's power as it last existed on the
  battlefield, counters, anthems and pumps included. The loop's `snapshot` is
  rewritten on every pass and holds one creature, and `power_of` over an `as`
  list of oids reads graveyard cards at their printed power.

So `players` gathers every choice first, `snapshot` under it binds one snapshot
per chosen permanent -- all taken before any of them moves -- and `power_of`
over that list sums them.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, action_for_card, settle

SPELL = "t_reign_of_the_pit"
LORD = "t_global_lord"  # 1/1, "All creatures get +1/+1."
BEAR = "t_bear"  # 2/2
PUMP = "t_pump_spell"  # +3/+3 until end of turn
DEMON = "demon_x_x_b_flying"
SWAMPS = ["swamp"] * 6


def position(builder, boards: dict[int, list[str]], *, caster=0, counters=None, extra_hand=()):
    """``caster``, active, holds the spell and six Swamps; ``boards`` per seat.

    ``counters`` maps a seat to counters placed on every creature there.
    Returns ``(game, oids)`` with ``oids[seat]`` that seat's creatures.
    """
    seats = max([1, *boards]) + 1
    lands = SWAMPS + ["forest"] * len(extra_hand)
    b = builder(players=seats).battlefield(caster, lands)
    for pid, cards in boards.items():
        b = b.battlefield(pid, cards, counters=(counters or {}).get(pid))
    game = b.hand(caster, [SPELL, *extra_hand]).active(caster).build()
    oids = {
        pid: [
            o.oid
            for o in game.state.battlefield_objects(pid)
            if "Creature" in chars(game.state, o.oid).types
        ]
        for pid in range(seats)
    }
    return game, oids


def resolve(game, picks: dict[int, int] | None = None) -> list[int]:
    """Cast the spell and let it resolve, each seat picking ``picks[seat]``.

    Returns the seats asked to choose, in the order they were asked.
    """
    game.apply(action_for_card(game, ActionKind.CAST, SPELL))
    asked: list[int] = []
    for _ in range(400):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            asked.append(decision.player)
            want = (picks or {}).get(decision.player)
            choose = next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE
                and (want is None or decision.options[a.choice].ref.id == want)
            )
            game.apply(choose)
            continue
        game.apply(_default_answer(game, decision))
    return asked


def demons(game, pid: int | None = None) -> list[int]:
    return [o.oid for o in game.state.battlefield_objects(pid) if o.def_id == DEMON]


def demon_size(game) -> tuple[int, int]:
    (oid,) = demons(game)
    c = chars(game.state, oid)
    return c.power, c.toughness


class TestTheTotalIsSummed:
    def test_one_demon_the_size_of_every_creature_sacrificed(self, builder):
        """Two 2/2 Bears and the caster's own: one 6/6, not one Demon per player."""
        game, oids = position(builder, {0: [BEAR], 1: [BEAR], 2: [BEAR]})
        resolve(game)
        for pid in range(3):
            assert game.state.objects[oids[pid][0]].zone is Zone.GRAVEYARD
        assert len(demons(game)) == 1
        assert demon_size(game) == (6, 6)

    def test_a_player_with_no_creature_adds_nothing(self, builder):
        game, _ = position(builder, {0: [], 1: [BEAR]})
        resolve(game)
        assert demon_size(game) == (2, 2)

    def test_nothing_sacrificed_makes_a_zero_zero_that_dies(self, builder):
        """X = 0: the token is created and 704.5f puts it in the graveyard."""
        game, _ = position(builder, {0: [], 1: []})
        resolve(game)
        assert demons(game) == []


class TestLastKnownPower:
    def test_counters_are_counted(self, builder):
        """A 2/2 with three +1/+1 counters left as a 5/5 and adds five."""
        game, oids = position(builder, {0: [], 1: [BEAR]}, counters={1: {"+1/+1": 3}})
        assert chars(game.state, oids[1][0]).power == 5
        resolve(game)
        assert demon_size(game) == (5, 5)

    def test_a_pump_before_the_sacrifice_is_counted(self, builder):
        """+3/+3 until end of turn on the Bear: it was a 5/5 when it went.

        The graveyard card is a 2/2, so any reading taken after the move --
        `power_of` over the `as` list of oids -- would make a 2/2.
        """
        game, oids = position(builder, {0: [], 1: [BEAR]}, extra_hand=[PUMP])
        bear = oids[1][0]
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == PUMP
                and [t.id for t in a.targets] == [bear]
            )
        )
        settle(game)
        assert chars(game.state, bear).power == 5
        resolve(game)
        assert chars(game.state, bear).power == 2  # the card, in the graveyard
        assert demon_size(game) == (5, 5)


class TestTheSacrificeIsSimultaneous:
    def test_a_lord_sacrificed_alongside_still_pumped_the_others(self, builder):
        """Player 0 gives up the lord, player 1 a Bear it was pumping.

        Both left at once, so the lord left as a 2/2 and the Bear as a 3/3:
        5. Sacrificed one at a time, the Bear would be measured after the lord
        had gone, at 2, and the Demon would be a 4/4.
        """
        game, oids = position(builder, {0: [LORD], 1: [BEAR]})
        assert chars(game.state, oids[1][0]).power == 3
        resolve(game)
        assert demon_size(game) == (5, 5)

    def test_each_player_chooses_their_own_in_apnap_order(self, builder):
        """The active player first, then the rest in turn order (101.4)."""
        game, oids = position(builder, {0: [BEAR], 1: [BEAR, LORD], 2: [BEAR]})
        lord = oids[1][1]
        asked = resolve(game, picks={1: lord})
        # Player 1 had two creatures to choose between; the others had one, and
        # a mandatory pick of the whole pool asks nobody.
        assert asked == [1]
        assert game.state.objects[lord].zone is Zone.GRAVEYARD
        assert game.state.objects[oids[1][0]].zone is Zone.BATTLEFIELD
        # The lord as a 2/2 and two Bears as 3/3s, all measured together.
        assert demon_size(game) == (8, 8)

    def test_choices_come_in_turn_order_from_the_active_player(self, builder):
        """Seat 1's turn: seats 1, 2, 0 -- not seat order, 0, 1, 2."""
        game, _ = position(
            builder, {0: [BEAR, BEAR], 1: [BEAR, BEAR], 2: [BEAR, BEAR]}, caster=1
        )
        asked = resolve(game)
        assert asked == [1, 2, 0]
        assert demon_size(game) == (6, 6)
        assert demons(game, 1)


def probe(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{B}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )
    )


class TestTheLoaderGuardsIt:
    def test_the_card_shape_loads(self):
        probe(
            {
                "op": "sacrifice",
                "players": "each_player",
                "objects": {"types": ["Creature"], "count": 1},
                "snapshot": "lki",
            }
        )

    @pytest.mark.parametrize("key", ["controller", "chooser"])
    def test_a_selector_naming_whose_or_who_chooses_is_refused(self, key):
        """`players` decides both, so a written one would be silently overridden."""
        with pytest.raises(DslError, match="cannot also name"):
            probe(
                {
                    "op": "sacrifice",
                    "players": "each_opponent",
                    "objects": {"types": ["Creature"], "count": 1, key: "you"},
                }
            )

    def test_an_unknown_player_spec_is_refused(self):
        with pytest.raises(DslError, match="unknown player spec"):
            probe(
                {
                    "op": "sacrifice",
                    "players": "every_player",
                    "objects": {"types": ["Creature"], "count": 1},
                }
            )
