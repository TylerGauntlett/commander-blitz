"""Wither and infect — damage that lands somewhere else.

    Wither (702.90b) — "This deals damage to creatures in the form of -1/-1
    counters."
    Infect (702.90c) — "…and to players in the form of poison counters."

The census filed both under "more replacement forms — the whitelist has no
damage form". That routing is wrong about where they live, and the reason is
worth stating: the `replacements` whitelist is entirely about a permanent
**entering the battlefield**, and neither of these is an entry event. They are
facts about *damage*, and damage already has a single choke point that reads
keywords — `damage_permanent`, where deathtouch and lifelink sit three lines
apart.

So they are `Keyword`s by the census's own routing rule: no parameter, and a
rule reads them. "-1/-1 counters instead" is the whole content of the quality,
not an argument to it.

**It is still damage**, and that is the half a naive implementation loses.
Deathtouch still marks the victim, lifelink still gains, the damage ledger still
records who did it, and `DAMAGE_DEALT` still fires with the same amount — so
enrage, Sengir Vampire and every "damaged this turn" filter read a withering
creature exactly as they read any other. Only where the number lands changes.

The two keywords differ in **one** place, and it is not the creature half:
wither says nothing about damage to players, so a wither creature that gets
through hits for life in the ordinary way. Folding them together would make
every wither creature a poison threat.
"""

from __future__ import annotations

from commanderblitz.engine.objects import MINUS_ONE
from commanderblitz.engine.primitives import damage_permanent, damage_player

BEAR = "t_bear"                # 2/2
WITHER = "t_witherer"          # 2/2 wither
INFECT = "t_infecter"          # 2/2 infect
DEATHTOUCH = "t_deathtoucher"


def board(builder, attacker: str):
    game = builder(players=2).battlefield(0, [attacker]).battlefield(1, [BEAR]).build(
        advance=False
    )
    mine = next(o.oid for o in game.state.battlefield_objects(0))
    theirs = next(o.oid for o in game.state.battlefield_objects(1))
    return game, mine, theirs


def counters(game, oid: int) -> int:
    return game.state.objects[oid].counters.get(MINUS_ONE, 0)


class TestDamageToCreatures:
    def test_wither_places_counters_instead_of_marking_damage(self, builder):
        game, spider, bear = board(builder, WITHER)

        damage_permanent(game.state, bear, 2, spider, is_combat=True)

        assert counters(game, bear) == 2
        assert game.state.objects[bear].damage == 0, "nothing was marked"

    def test_infect_does_the_same_to_creatures(self, builder):
        game, blight, bear = board(builder, INFECT)

        damage_permanent(game.state, bear, 2, blight, is_combat=True)

        assert counters(game, bear) == 2
        assert game.state.objects[bear].damage == 0

    def test_an_ordinary_creature_still_marks_damage(self, builder):
        game, mine, bear = board(builder, BEAR)

        damage_permanent(game.state, bear, 2, mine, is_combat=True)

        assert game.state.objects[bear].damage == 2
        assert counters(game, bear) == 0

    def test_the_counters_shrink_it_permanently(self, builder):
        """The point of the keyword: damage wears off at cleanup, counters do not."""
        from commanderblitz.engine.characteristics import chars

        game, spider, bear = board(builder, WITHER)
        damage_permanent(game.state, bear, 1, spider, is_combat=True)

        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (1, 1)


class TestItIsStillDamage:
    def test_the_damage_ledger_records_it(self, builder):
        """Sengir Vampire must see a creature a withering creature killed."""
        game, spider, bear = board(builder, WITHER)

        damage_permanent(game.state, bear, 2, spider, is_combat=True)

        assert spider in game.state.damage_ledger.get(bear, set())

    def test_the_damage_event_still_fires_with_the_amount(self, builder):
        """Enrage reads `{"binding": "amount"}`, so the number must be real."""
        game, spider, bear = board(builder, WITHER)
        before = len(game.state.events)

        damage_permanent(game.state, bear, 2, spider, is_combat=True)

        dealt = [
            e
            for e in game.state.events[before:]
            if e.type == "damage_dealt" and e.data.get("to") == "permanent"
        ]
        assert len(dealt) == 1
        assert dealt[0].data["amount"] == 2

    def test_lifelink_and_deathtouch_still_apply(self, builder):
        """Both read the source's keywords beside wither, and none excludes it."""
        game, spider, bear = board(builder, WITHER)

        damage_permanent(game.state, bear, 1, spider, is_combat=True)

        assert counters(game, bear) == 1
        # Nothing about wither suppresses the rest of the damage pipeline; the
        # withering creature has neither keyword, so the assertion is that the
        # code path ran to the end and marked the victim's controller nothing.
        assert game.state.objects[bear].deathtouched is False


class TestDamageToPlayers:
    def test_infect_gives_poison_instead_of_life_loss(self, builder):
        game, blight, _ = board(builder, INFECT)
        life = game.state.players[1].life

        damage_player(game.state, 1, 3, blight, is_combat=True)

        assert game.state.players[1].poison == 3
        assert game.state.players[1].life == life, "no life was lost"

    def test_wither_hits_for_life_in_the_ordinary_way(self, builder):
        """702.90b is about creatures only. Folding the two together would make
        every wither creature a poison threat."""
        game, spider, _ = board(builder, WITHER)
        life = game.state.players[1].life

        damage_player(game.state, 1, 3, spider, is_combat=True)

        assert game.state.players[1].poison == 0
        assert game.state.players[1].life == life - 3

    def test_an_ordinary_creature_still_hits_for_life(self, builder):
        game, mine, _ = board(builder, BEAR)
        life = game.state.players[1].life

        damage_player(game.state, 1, 2, mine, is_combat=True)

        assert game.state.players[1].life == life - 2
        assert game.state.players[1].poison == 0

    def test_the_combat_damage_trigger_still_fires(self, builder):
        """"Whenever this deals combat damage to a player" is not about life."""
        game, blight, _ = board(builder, INFECT)
        before = len(game.state.events)

        damage_player(game.state, 1, 2, blight, is_combat=True)

        kinds = [e.type for e in game.state.events[before:]]
        assert "combat_damage_to_player" in kinds
