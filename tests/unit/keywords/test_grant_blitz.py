"""`grant_blitz` -- blitz handed to a class of creature spells by another permanent.

    Each creature spell you cast with mana value 4 or greater has blitz. The
    blitz cost is equal to its mana cost. (You may choose to cast that spell
    for its blitz cost. If you do, it gains haste and "When this creature dies,
    draw a card." Sacrifice it at the beginning of the next end step.)

Witness: Henzie "Toolbox" Torre, the commander of the Riveteers Rampage precon.

Rule 702.152a makes blitz an alternative cost with three riders, and a spell
cast for it is *blitzed*. A printed blitz is the `evoke` slot under
`evoke_label: "blitz"`, and the card writes its riders on its own `evoked`
enters trigger (Caldaia Guardian). A granted one cannot: the creature prints no
sentence to hang a trigger on, so the riders are the rule's and the engine owes
them, the way it owes warp's exile (`stack._place_after_resolution`).

What would be wrong without each claim below:

* **The price is the spell's own mana cost**, so the blitz line costs exactly
  what the printed line costs. The flag on the action is the only thing that
  tells them apart, and a lookup that ignored it would sacrifice a creature the
  player paid full price to keep.
* **The draw is an ability the creature has**, not a watcher on the board: it
  fires on the creature's own death, and a creature that loses its abilities
  after arriving does not have it (613.1f).
* **The sacrifice names that permanent**, at the *next* end step, so it attacks
  first and a creature that already died is not chased.
* **The scope is the printed filter**: creature spells, mana value 4 or more,
  cast by the granter's controller. The near miss is `grant_warp`, which is
  hand-only, exiles instead of sacrificing and grants neither haste nor the
  draw.
* **A card with a printed blitz keeps it**, and has two blitz lines because the
  prices differ; each pays for one set of riders, never both.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import AbilityModel, CardModel
from commanderblitz.engine.characteristics import granted_abilities
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import lose_all_abilities_timed
from commanderblitz.engine.zones import destroy
from tests.conftest import keywords, pass_until, settle

GRANTER = "t_blitz_granter"  # Henzie's first line on a free body
BRUTE = "t_blitz_brute"      # {3}{R} creature, mana value 4: the boundary
CUB = "t_blitz_cub"          # {2}{R} creature, mana value 3: under it
BONFIRE = "t_blitz_bonfire"  # {4}{R} sorcery: over it, and not a creature
GUARDIAN = "caldaia_guardian"  # {3}{G}, prints Blitz {2}{G}


def board(builder, *, hand, lands=8, granter=True, granter_seat=0, library=("forest",) * 30):
    """Player 0 on Mountains and Forests, with the granter out unless told otherwise.

    The Forest in hand keeps a play on offer, so the main phase does not
    auto-advance before a test looks at it.
    """
    b = (
        builder(players=2)
        .hand(0, [*hand, "forest"])
        .battlefield(0, ["mountain"] * (lands // 2) + ["forest"] * (lands - lands // 2))
        .hand(1, ["forest"])
        .library(0, list(library))
        .library(1, ["forest"] * 30)
    )
    if granter:
        b = b.battlefield(granter_seat, [GRANTER])
    return b.build()


def casts(game, card_id, pid=0):
    oid = next(o for o in game.state.players[pid].hand if game.state.objects[o].def_id == card_id)
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def blitz_line(game, card_id):
    return next(a for a in casts(game, card_id) if a.blitzed)


def printed_line(game, card_id):
    return next(a for a in casts(game, card_id) if not a.blitzed and not a.evoked)


def cast(game, action):
    game.apply(action)
    settle(game)


def permanent(game, card_id, pid=0):
    return next(o.oid for o in game.state.battlefield_objects(pid) if o.def_id == card_id)


def on_battlefield(game, card_id, pid=0):
    return any(o.def_id == card_id for o in game.state.battlefield_objects(pid))


def zone_ids(game, zone, pid=0):
    return [game.state.objects[o].def_id for o in game.state.players[pid].zone_list(zone)]


def tapped_lands(game, pid=0):
    return sum(
        1 for o in game.state.battlefield_objects(pid) if o.tapped and game.state.card_of(o).is_land
    )


def run_to_main_of(game, pid):
    pass_until(
        game, lambda g: g.state.active_player == pid and g.state.step is Step.PRECOMBAT_MAIN
    )


class TestTheGrantedLine:
    """An alternative cost priced at the mana cost, offered beside the printed line."""

    def test_both_lines_are_offered(self, builder):
        game = board(builder, hand=[BRUTE])
        assert sorted(a.blitzed for a in casts(game, BRUTE)) == [False, True]

    def test_the_blitz_line_charges_the_mana_cost(self, builder):
        game = board(builder, hand=[BRUTE])
        cast(game, blitz_line(game, BRUTE))
        assert on_battlefield(game, BRUTE)
        assert tapped_lands(game) == 4

    def test_the_two_lines_are_different_actions(self, builder):
        # Same price, same source, same targets: the flag is the identity.
        game = board(builder, hand=[BRUTE])
        assert blitz_line(game, BRUTE).key() != printed_line(game, BRUTE).key()
        assert blitz_line(game, BRUTE).base_label != printed_line(game, BRUTE).base_label

    def test_the_label_names_the_price(self, builder):
        game = board(builder, hand=[BRUTE])
        assert "(blitz {3}{R})" in blitz_line(game, BRUTE).base_label


class TestTheRiders:
    """Haste, the dies-draw, and the sacrifice at the next end step."""

    def test_it_has_haste(self, builder):
        game = board(builder, hand=[BRUTE])
        cast(game, blitz_line(game, BRUTE))
        assert "haste" in keywords(game, permanent(game, BRUTE))

    def test_the_printed_cast_has_none_of_them(self, builder):
        # The control: the same creature cast normally under the same granter.
        game = board(builder, hand=[BRUTE])
        cast(game, printed_line(game, BRUTE))
        assert "haste" not in keywords(game, permanent(game, BRUTE))
        assert not game.state.delayed_triggers
        run_to_main_of(game, 1)
        assert on_battlefield(game, BRUTE)

    def test_it_survives_to_attack(self, builder):
        game = board(builder, hand=[BRUTE])
        cast(game, blitz_line(game, BRUTE))
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
        assert on_battlefield(game, BRUTE)

    def test_it_is_sacrificed_at_the_end_step_and_draws(self, builder):
        # Sacrificed is "dies", so the granted trigger pays the card back.
        game = board(builder, hand=[BRUTE])
        cast(game, blitz_line(game, BRUTE))
        hand = len(game.state.players[0].hand)
        run_to_main_of(game, 1)
        assert not on_battlefield(game, BRUTE)
        assert zone_ids(game, Zone.GRAVEYARD) == [BRUTE]
        assert len(game.state.players[0].hand) == hand + 1

    def test_it_draws_when_it_dies_before_the_end_step(self, builder):
        game = board(builder, hand=[BRUTE])
        cast(game, blitz_line(game, BRUTE))
        hand = len(game.state.players[0].hand)
        destroy(game.state, permanent(game, BRUTE))
        settle(game)
        assert len(game.state.players[0].hand) == hand + 1

    def test_a_creature_that_already_died_is_not_chased(self, builder):
        game = board(builder, hand=[BRUTE])
        cast(game, blitz_line(game, BRUTE))
        destroy(game.state, permanent(game, BRUTE))
        settle(game)
        run_to_main_of(game, 1)
        assert zone_ids(game, Zone.GRAVEYARD) == [BRUTE]
        assert not game.state.delayed_triggers

    def test_the_sacrifice_names_that_permanent(self, builder):
        game = board(builder, hand=[BRUTE, BRUTE], lands=12)
        cast(game, blitz_line(game, BRUTE))
        cast(game, printed_line(game, BRUTE))
        run_to_main_of(game, 1)
        assert [o.def_id for o in game.state.battlefield_objects(0)].count(BRUTE) == 1

    def test_the_draw_is_an_ability_the_creature_has(self, builder):
        # Granted onto the permanent, not watched for from the board -- and
        # hidden by a later "loses all abilities" while it is there (613.1f).
        game = board(builder, hand=[BRUTE])
        cast(game, blitz_line(game, BRUTE))
        oid = permanent(game, BRUTE)
        granted = [a.text for _, a in granted_abilities(game.state, oid)]
        assert granted == ["When this creature dies, draw a card."]
        lose_all_abilities_timed(game.state, oid, cutoff=game.state.alloc_timestamp())
        assert list(granted_abilities(game.state, oid)) == []

    def test_the_riders_outlive_the_granter(self, builder):
        # The grant decides the cast; the riders are the blitzed spell's.
        game = board(builder, hand=[BRUTE])
        cast(game, blitz_line(game, BRUTE))
        destroy(game.state, permanent(game, GRANTER))
        settle(game)
        assert "haste" in keywords(game, permanent(game, BRUTE))
        run_to_main_of(game, 1)
        assert not on_battlefield(game, BRUTE)


class TestTheGrantsScope:
    def test_mana_value_three_has_no_blitz(self, builder):
        game = board(builder, hand=[CUB])
        assert [a.blitzed for a in casts(game, CUB)] == [False]

    def test_a_noncreature_spell_has_no_blitz(self, builder):
        game = board(builder, hand=[BONFIRE])
        assert [a.blitzed for a in casts(game, BONFIRE)] == [False]

    def test_without_the_granter_nothing_has_blitz(self, builder):
        game = board(builder, hand=[BRUTE], granter=False)
        assert [a.blitzed for a in casts(game, BRUTE)] == [False]

    def test_an_opponents_granter_grants_you_nothing(self, builder):
        game = board(builder, hand=[BRUTE], granter_seat=1)
        assert [a.blitzed for a in casts(game, BRUTE)] == [False]

    def test_the_grant_wears_off_with_its_source(self, builder):
        game = board(builder, hand=[BRUTE])
        destroy(game.state, permanent(game, GRANTER))
        settle(game)
        assert [a.blitzed for a in casts(game, BRUTE)] == [False]


class TestAPrintedBlitzBesideAGrantedOne:
    """Two blitz lines because the prices differ, and one set of riders each."""

    def test_three_lines(self, builder):
        game = board(builder, hand=[GUARDIAN])
        lines = casts(game, GUARDIAN)
        assert sorted((a.evoked, a.blitzed) for a in lines) == [
            (False, False),
            (False, True),
            (True, False),
        ]
        labels = {a.base_label for a in lines}
        assert len(labels) == 3, "the printed (blitz) row and the granted one must not collapse"

    def test_the_granted_line_gets_the_riders_once(self, builder):
        game = board(builder, hand=[GUARDIAN])
        cast(game, blitz_line(game, GUARDIAN))
        assert tapped_lands(game) == 4, "the mana cost, not the printed {2}{G}"
        assert len(game.state.delayed_triggers) == 1, "the printed trigger did not also fire"
        run_to_main_of(game, 1)
        assert not on_battlefield(game, GUARDIAN)

    def test_the_printed_line_is_untouched(self, builder):
        game = board(builder, hand=[GUARDIAN])
        cast(game, next(a for a in casts(game, GUARDIAN) if a.evoked))
        assert tapped_lands(game) == 3
        assert len(game.state.delayed_triggers) == 1


class TestTheLoaderRefusesTheSilentFailures:
    """Each of these would load clean and grant blitz the card does not print."""

    def _card(self, **grant):
        base = dict(
            kind="static",
            text="x",
            effect="grant_blitz",
            affects_player="you",
            affects_spells={"types": ["Creature"], "mana_value": {"op": ">=", "value": 4}},
        )
        base.update(grant)
        return CardModel(
            id="t_bad", name="Bad", mana_cost="{3}", types=["Creature"],
            power=1, toughness=1, abilities=[AbilityModel(**base)],
        )

    def test_the_well_formed_grant_loads(self):
        compile_card(self._card())

    def test_a_grant_with_no_filter_is_refused(self):
        with pytest.raises(DslError, match="affects_spells"):
            compile_card(self._card(affects_spells=None))

    def test_a_grant_to_noncreature_spells_is_refused(self):
        with pytest.raises(DslError, match="Creature"):
            compile_card(self._card(affects_spells={"types": ["Sorcery"]}))

    def test_a_filter_that_reads_board_state_is_refused(self):
        with pytest.raises(DslError, match="tapped"):
            compile_card(self._card(affects_spells={"types": ["Creature"], "tapped": True}))

    def test_a_mana_value_that_is_not_a_literal_is_refused(self):
        with pytest.raises(DslError, match="mana_value"):
            compile_card(
                self._card(
                    affects_spells={"types": ["Creature"], "mana_value": {"count": "x"}}
                )
            )
