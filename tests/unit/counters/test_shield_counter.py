"""Shield counters — 122.1c, a replacement effect that lives on a counter.

    "This land enters with a shield counter on it. (**If it would be dealt
    damage or destroyed, remove a shield counter from it instead.**)"
    — Diamond City, the witness.

Counter kinds are free strings, so the would-be answer to that card already
loaded: a `self_enters_with_counters` replacement naming `"shield"`, plus the
`move_counters` ability for line three. It placed a counter, showed a counter,
and moved a counter — and **passed all six authoring gates**, because placing
the counter is genuine and only its meaning was missing. The land entered with
an inert tally, died to the first removal spell it is printed to survive, and
spent a tap moving a token of nothing onto a creature. No gate can see that; a
unit test is the only thing that can, which is what this file is.

Nothing in the engine was close enough to bend. `enums.KEYWORD_COUNTERS` is the
`Keyword` values minus the inert ones and "shield" is not a `Keyword`, so the
characteristics pipeline applies nothing for it. `zones.destroy` replaced a
destruction from exactly three places — `indestructible`, the integer
`obj.regeneration_shields`, and totem armor — none counter-driven. And
`prevent_damage` refuses an `objects` clause outright, so it cannot cover a
permanent at all.

Two shipped paths were the right precedents and this is those two, keyed on a
counter kind instead of on a field or a keyword: a regeneration shield is a
spent-once replacement of a **destruction**, and absorb is a per-permanent
prevention of **damage**. Being a counter rather than a card ability is
load-bearing rather than tidy — Diamond City's third ability moves the counter
onto a creature the land never mentions, and it has to keep working there.

Four claims are the whole mechanic, and each is a strictly better or strictly
worse card if it is wrong:

* it replaces **destruction and damage**, one counter per event;
* it is **not indestructible** — with no counters left the permanent dies;
* **lethal damage costs one counter and is prevented entirely**. A replacement,
  not a reduction: nothing is marked, so nothing is left for the state-based
  action to kill it with;
* **sacrifice is not destruction** (701.16b), so a shield does not stop it —
  which is the absence of a rule rather than an extra one, since a sacrifice
  never reaches `zones.destroy`.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Keyword, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import MINUS_ONE, SHIELD
from commanderblitz.engine.primitives import add_counters, damage_permanent, spend_shield_counter
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.zones import destroy, sacrifice
from tests.conftest import only_oid, pass_until

FOREST = "forest"
BEAR = "t_bear"
TROLL = "t_regenerator"
ABSORBER = "t_absorber"
DEATHTOUCHER = "t_deathtoucher"
LIFELINKER = "t_lifelinker"
INDESTRUCTIBLE = "t_indestructible"


def shielded(
    builder,
    card_id: str = BEAR,
    *,
    counters: int = 1,
    extra: tuple = (),
    lands: int = 3,
):
    """One permanent with ``counters`` shield counters on it, and its oid.

    The counters go on with `add_counters` rather than through the builder's
    ``counters=`` keyword on purpose: that keyword writes the dict directly, and
    the claim under test is about a counter that arrived the way every counter
    in a real game arrives.

    ``lands`` drops to zero when the shielded permanent *is* a Forest, so that
    `only_oid` still names exactly one of them.
    """
    game = (
        builder(players=2)
        .battlefield(0, [FOREST] * lands)
        .battlefield(0, [card_id, *extra])
        .build(advance=False)
    )
    oid = only_oid(game, card_id)
    if counters:
        add_counters(game.state, oid, SHIELD, counters)
    return game, oid


def regenerate(game, oid: int, amount: int = 1) -> None:
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    gen = OPS["regenerate"](
        ctx,
        {
            "op": "regenerate",
            "amount": {"const": amount},
            "objects": {"zone": "battlefield", "self_only": True},
        },
    )
    with contextlib.suppress(StopIteration):
        next(gen)


class TestItReplacesDestruction:
    def test_the_permanent_survives_and_one_counter_is_gone(self, builder):
        game, bear = shielded(builder)

        assert destroy(game.state, bear) is False
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].counter(SHIELD) == 0

    def test_it_is_one_counter_per_destruction(self, builder):
        """Two counters is two destructions survived, not a permanent state."""
        game, bear = shielded(builder, counters=2)

        assert destroy(game.state, bear) is False
        assert game.state.objects[bear].counter(SHIELD) == 1
        assert destroy(game.state, bear) is False
        assert game.state.objects[bear].counter(SHIELD) == 0

    def test_with_no_counters_left_it_dies(self, builder):
        """The boundary, and the difference between this and indestructible."""
        game, bear = shielded(builder)
        destroy(game.state, bear)

        assert destroy(game.state, bear) is True
        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_an_unshielded_permanent_is_unaffected(self, builder):
        """The control. Without it this file proves nothing about the counter."""
        game, bear = shielded(builder, counters=0)

        assert destroy(game.state, bear) is True

    def test_it_works_on_a_land(self, builder):
        """Diamond City shields *itself*, and it is not a creature."""
        game, land = shielded(builder, FOREST, lands=0)
        assert destroy(game.state, land) is False
        assert game.state.objects[land].zone is Zone.BATTLEFIELD


class TestItIsNotRegeneration:
    """701.15a's three consequences belong to the regeneration shield. A shield
    counter does none of them, and a permanent that quietly untapped or shed its
    damage would be a strictly better card than the printed one."""

    def test_it_is_not_tapped(self, builder):
        game, bear = shielded(builder)
        destroy(game.state, bear)

        assert not game.state.objects[bear].tapped

    def test_its_marked_damage_stays_marked(self, builder):
        game, bear = shielded(builder)
        game.state.objects[bear].damage = 1
        destroy(game.state, bear)

        assert game.state.objects[bear].damage == 1

    def test_lethal_damage_already_marked_eats_the_counters(self, builder):
        """The consequence of not removing damage, and it is the printed one:
        the state-based action re-checks, so a shielded creature standing in
        lethal damage sheds one counter per check until it has none and dies."""
        game, bear = shielded(builder, counters=2)
        game.state.objects[bear].damage = 2

        assert sba.check(game.state) is True, "one check, one counter"
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].counter(SHIELD) == 1

        sba.run(game.state)
        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_a_shielded_creature_below_lethal_keeps_its_counters(self, builder):
        """The control for the check above: the loop must not spend counters on
        a creature the state-based action was never going to destroy."""
        game, bear = shielded(builder, counters=2)
        game.state.objects[bear].damage = 1
        sba.run(game.state)

        assert game.state.objects[bear].counter(SHIELD) == 2
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_it_survives_the_end_of_the_turn(self, builder):
        """A regeneration shield is wiped at cleanup; a counter is a counter."""
        game, bear = shielded(builder)
        start = game.state.turn
        pass_until(game, lambda g: g.state.turn > start + 1)

        assert game.state.objects[bear].counter(SHIELD) == 1

    def test_cant_be_regenerated_does_not_touch_it(self, builder):
        """701.15c names *regeneration*. A shield counter is a different
        replacement, exactly as indestructible and totem armor are."""
        game, bear = shielded(builder)

        assert destroy(game.state, bear, no_regeneration=True) is False
        assert game.state.objects[bear].counter(SHIELD) == 0


class TestTheLadderInDestroy:
    def test_indestructible_does_not_spend_a_counter(self, builder):
        """Indestructible is not a replacement that consumes anything -- the
        destruction never happens -- so the counter must still be there."""
        game, creature = shielded(builder, INDESTRUCTIBLE)
        assert Keyword.INDESTRUCTIBLE.value in game.state.registry.get(
            INDESTRUCTIBLE
        ).keywords

        assert destroy(game.state, creature) is False
        assert game.state.objects[creature].counter(SHIELD) == 1

    def test_the_counter_is_spent_before_a_regeneration_shield(self, builder):
        """616.1 would let the controller choose between two replacements of the
        same destruction and the engine does not model that choice. The counter
        goes first because it is strictly the cheaper one: no tap, no removal
        from combat, no damage wiped."""
        game, troll = shielded(builder, TROLL)
        regenerate(game, troll)

        assert destroy(game.state, troll) is False
        assert game.state.objects[troll].counter(SHIELD) == 0
        assert game.state.objects[troll].regeneration_shields == 1
        assert not game.state.objects[troll].tapped


class TestItReplacesDamage:
    def test_the_whole_event_is_prevented_for_one_counter(self, builder):
        """A replacement, not a reduction. Five damage costs one counter and
        marks nothing -- so nothing is left for a state-based action to use."""
        game, bear = shielded(builder, extra=(FOREST,))
        source = only_oid(game, BEAR)

        assert damage_permanent(game.state, bear, 5, source) == 0
        assert game.state.objects[bear].damage == 0
        assert game.state.objects[bear].counter(SHIELD) == 0

    def test_lethal_combat_damage_leaves_the_creature_alive(self, builder):
        game, bear = shielded(builder)
        damage_permanent(game.state, bear, 2, bear, is_combat=True)
        sba.run(game.state)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_it_is_one_counter_per_damage_event(self, builder):
        """Two blockers are two events, so two counters -- not one for the
        combat and not one per point of damage."""
        game, bear = shielded(builder, counters=2)
        damage_permanent(game.state, bear, 1, bear)
        assert game.state.objects[bear].counter(SHIELD) == 1
        damage_permanent(game.state, bear, 1, bear)

        assert game.state.objects[bear].counter(SHIELD) == 0
        assert game.state.objects[bear].damage == 0

    def test_the_next_damage_lands(self, builder):
        """The wearing-off. With the counter gone the permanent is ordinary."""
        game, bear = shielded(builder)
        damage_permanent(game.state, bear, 1, bear)

        assert damage_permanent(game.state, bear, 1, bear) == 1
        assert game.state.objects[bear].damage == 1

    def test_deathtouch_marks_nothing(self, builder):
        """Prevented damage was never dealt, so 702.2b never applies -- and a
        creature marked `deathtouched` would die to the state-based action even
        with the damage gone."""
        game, bear = shielded(builder, extra=(DEATHTOUCHER,))
        killer = only_oid(game, DEATHTOUCHER)
        damage_permanent(game.state, bear, 1, killer)
        sba.run(game.state)

        assert game.state.objects[bear].deathtouched is False
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_lifelink_gains_nothing(self, builder):
        game, bear = shielded(builder, extra=(LIFELINKER,))
        healer = only_oid(game, LIFELINKER)
        before = game.state.players[0].life
        damage_permanent(game.state, bear, 2, healer)

        assert game.state.players[0].life == before

    def test_the_damage_ledger_records_nobody(self, builder):
        """"Whenever a creature dealt damage by this creature dies" must not
        answer for damage that was replaced."""
        game, bear = shielded(builder, extra=(DEATHTOUCHER,))
        killer = only_oid(game, DEATHTOUCHER)
        damage_permanent(game.state, bear, 1, killer)

        assert killer not in game.state.damage_ledger.get(bear, set())

    def test_a_withering_source_places_no_counters(self, builder):
        """Wither is a different *place to put* the damage, not a reason it is
        not dealt, so the shield has to be read first -- a shielded creature
        taking -1/-1 counters would be shielded from nothing."""
        game, bear = shielded(builder)
        game.state.objects[bear].granted_keywords.add(Keyword.WITHER.value)
        game.state.bump_chars()
        damage_permanent(game.state, bear, 2, bear)

        assert game.state.objects[bear].counter(MINUS_ONE) == 0
        assert game.state.objects[bear].counter(SHIELD) == 0

    def test_absorb_is_spent_first_and_leaves_the_counter_alone(self, builder):
        """Both shield the same event. Checked this way round the counter is
        spent only on damage that would otherwise land, which is the choice its
        controller would make under 616.1."""
        game, wall = shielded(builder, ABSORBER)
        assert damage_permanent(game.state, wall, 2, wall) == 0

        assert game.state.objects[wall].counter(SHIELD) == 1


class TestWhatItDoesNotStop:
    def test_sacrifice_goes_through(self, builder):
        """701.16b: a sacrifice is not a destruction, and it never reaches
        `zones.destroy`. Regeneration and totem armor fail here for the same
        reason, which is the absence of a rule rather than an extra one."""
        game, bear = shielded(builder)

        assert sacrifice(game.state, bear) is True
        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_zero_toughness_goes_through(self, builder):
        """704.5a puts the creature in the graveyard without destroying it."""
        game, bear = shielded(builder)
        add_counters(game.state, bear, MINUS_ONE, 2)
        sba.run(game.state)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_it_does_not_follow_the_card_out_of_the_zone(self, builder):
        """Counters are wiped by `reset_permanent_state`, so a creature that
        dies and comes back is not still carrying a shield."""
        game, bear = shielded(builder)
        sacrifice(game.state, bear)

        assert game.state.objects[bear].counters == {}


class TestItLivesOnTheCounter:
    """The reason this is a counter kind and not a card ability: Diamond City's
    third line moves the counter onto a creature the land never mentions."""

    def test_a_moved_counter_shields_its_new_home(self, builder):
        game, land = shielded(builder, FOREST, extra=(BEAR,), lands=0)
        bear = only_oid(game, BEAR)
        ctx = EffectContext(state=game.state, controller=0, source_oid=land)
        gen = OPS["move_counters"](
            ctx,
            {
                "op": "move_counters",
                "counter": SHIELD,
                "amount": {"const": 1},
                "from": {"self_only": True},
                "objects": {"zone": "battlefield", "types": ["Creature"]},
            },
        )
        with contextlib.suppress(StopIteration):
            next(gen)

        assert game.state.objects[land].counter(SHIELD) == 0
        assert game.state.objects[bear].counter(SHIELD) == 1
        assert destroy(game.state, bear) is False
        assert destroy(game.state, land) is True


class TestTheConsumer:
    def test_it_reports_whether_it_found_one(self, builder):
        game, bear = shielded(builder)

        assert spend_shield_counter(game.state, bear) is True
        assert spend_shield_counter(game.state, bear) is False

    def test_it_does_nothing_off_the_battlefield(self, builder):
        """A card in a graveyard has no counters and replaces nothing."""
        game, bear = shielded(builder)
        sacrifice(game.state, bear)

        assert spend_shield_counter(game.state, bear) is False


class TestTheLoaderGuard:
    """A mis-spelled shield counter is the failure this whole capability exists
    to stop, and unlike a mis-spelled charge counter it is detectable: the
    engine reads the kind exactly, so anything that normalises onto `shield`
    without being it is a counter that is placed, shown, moved -- and never
    spent."""

    def base(self, kind: str) -> dict:
        return {
            "id": "t_shield_probe",
            "name": "Test Shield Probe",
            "types": ["Land"],
            "replacements": [
                {"event": "self_enters_with_counters", "counter": kind, "amount": 1}
            ],
        }

    def test_the_exact_spelling_loads(self):
        compile_card(CardModel.model_validate(self.base(SHIELD)))

    @pytest.mark.parametrize("kind", ["Shield", "shield counter", "shield counters"])
    def test_a_near_miss_is_refused(self, kind):
        with pytest.raises(DslError, match="write the shield counter as"):
            compile_card(CardModel.model_validate(self.base(kind)))

    def test_somebody_elses_counter_is_still_free(self):
        """The open vocabulary survives -- guessing at typos would refuse cards
        that are correct."""
        compile_card(CardModel.model_validate(self.base("shielding")))


DIAMOND_CITY = {
    "id": "t_diamond_city",
    "name": "Diamond City",
    "oracle_text": (
        "This land enters with a shield counter on it. (If it would be dealt damage "
        "or destroyed, remove a shield counter from it instead.)\n{T}: Add {C}.\n"
        "{T}: Move a shield counter from this land onto target creature. Activate "
        "only if two or more creatures entered the battlefield under your control "
        "this turn."
    ),
    "types": ["Land"],
    "replacements": [
        {"event": "self_enters_with_counters", "counter": SHIELD, "amount": 1}
    ],
    "abilities": [
        {
            "kind": "activated",
            "text": "{T}: Add {C}.",
            "is_mana_ability": True,
            "cost": {"tap": True},
            "effects": [{"op": "add_mana", "mana": "{C}"}],
        },
        {
            "kind": "activated",
            "text": (
                "{T}: Move a shield counter from this land onto target creature. "
                "Activate only if two or more creatures entered the battlefield "
                "under your control this turn."
            ),
            "cost": {"tap": True},
            "condition": {
                "cmp": ">=",
                "left": {
                    "permanents_entered_this_turn": {
                        "controller": "you",
                        "types": ["Creature"],
                    }
                },
                "right": {"const": 2},
            },
            "targets": [
                {
                    "id": "t1",
                    "kind": "permanent",
                    "selector": {"zone": "battlefield", "types": ["Creature"]},
                    "count": 1,
                }
            ],
            "effects": [
                {
                    "op": "move_counters",
                    "counter": SHIELD,
                    "amount": {"const": 1},
                    "from": {"self_only": True},
                    "objects": {"target": "t1"},
                }
            ],
        },
    ],
}


class TestDiamondCity:
    """The witness, end to end. The prototype is here rather than in `data/`
    because the point is the *engine*: the same card definition loaded and
    passed every gate before this change, and the land still died."""

    @pytest.fixture(scope="class")
    @classmethod
    def city_registry(cls, registry) -> CardRegistry:
        card = compile_card(CardModel.model_validate(DIAMOND_CITY))
        pool = CardRegistry.from_paths(authored_card_paths(Path("data/cards")))
        return CardRegistry({c.id: c for c in pool} | {card.id: card})

    @pytest.fixture
    def played(self, city_registry):
        """The land played from hand, so the replacement actually runs."""
        game = (
            GameBuilder(city_registry, players=2, seed=0)
            .hand(0, ["t_diamond_city"])
            .build()
        )
        action = next(
            a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND
        )
        game.apply(action)
        return game, only_oid(game, "t_diamond_city")

    def test_it_enters_with_a_shield_counter(self, played):
        game, land = played
        assert game.state.objects[land].counter(SHIELD) == 1

    def test_it_survives_the_removal_it_is_printed_to_survive(self, played):
        game, land = played

        assert destroy(game.state, land) is False
        assert game.state.objects[land].zone is Zone.BATTLEFIELD

    def test_and_dies_to_the_second_one(self, played):
        game, land = played
        destroy(game.state, land)

        assert destroy(game.state, land) is True
        assert game.state.objects[land].zone is Zone.GRAVEYARD
