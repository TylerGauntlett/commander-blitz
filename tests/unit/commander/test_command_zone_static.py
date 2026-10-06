"""Eminence (702.106) — a static ability that works from the **command zone**.

    Eminence — As long as The Ur-Dragon is in the command zone or on the
    battlefield, other Dragon spells you cast cost {1} less to cast.

The effect itself was already shipped: `spell_cost_reduction` with an
`affects_spells` filter is Warden of Evos Isle, and it says "other Dragon spells
you cast cost {1} less" exactly. The **zone** was the whole gap. The engine
collected statics from the battlefield (`_battlefield_statics`) and from
graveyards (`_graveyard_statics`) and from nowhere else, and the loader refused
`active_zones: ["command"]` in as many words — "nothing collects one in
['command']" — so the clause was a load error rather than an inert card.

`characteristics._command_zone_statics` is the missing walk, built like the
graveyard one and appended to the same list, so every downstream reader gets it
at once: the characteristic layers, `cost_reduction.spell_cost_reduction`, and
— through its own line, because it walks the battlefield itself —
`player_statics._active_player_statics`.

**The trap this file exists to pin.** A cost reduction is invisible to every
authoring expectation key: the sandbox casts the card from hand onto an empty
board and no `expect` can observe a price. So a battlefield-only approximation
passes all six gates while silently dropping the half of eminence that matters
most — the discount while the commander sits in the command zone, which is
where a nine-mana commander is for most of the game, and which is the only
reason the ability is worth printing. `t_battlefield_dragon` is that
approximation, kept as the counterfactual, byte-for-byte the same static with
`active_zones` omitted; `TestTheCounterfactualIsDeadWhereItMatters` asserts the
two disagree in exactly the zone the card is about.

**"Other" only became sayable here, and only became necessary here.** A
permanent's own spell is never on the stack while that permanent is on the
battlefield, so no battlefield static ever needed `exclude_self`. A commander's
is: `Game._cast` prices the spell while `obj.zone` is still `COMMAND`, so the
eminence static is collected against its own card, and without the word The
Ur-Dragon would discount its own nine-mana cast by the {1} it prints for
everything else.

The same walk is what `loader._compile_emblems` named when it refused an emblem
static ("a static is read by several separate walks … none of which look at the
command zone"), so `TestAnEmblemMayNowBeAStatic` is the second item this closes
— an emblem is only ever in the command zone (114.1), so it is the same
question one card type over.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.cost_reduction import cost_reduction
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.player_statics import player_extra_land_drops
from automtg.engine.primitives import give_emblem
from tests.conftest import only_oid

EMINENCE = "t_eminence_dragon"  # the command-zone-or-battlefield discount
BATTLEFIELD_ONLY = "t_battlefield_dragon"  # the same static, no `active_zones`
DRAGON = "t_plain_dragon"  # {4}{R} 4/4 Dragon, the spell being discounted
BEAR = "t_bear"  # {1}{G}, not a Dragon
WALKER = "t_emblem_anthem_walker"  # +1: an emblem whose abilities are statics


def table(builder, *, command=(), battlefield=(), lands=6, hand=(DRAGON,), pid=0):
    """Player 0's main phase, with ``command`` waiting in the command zone."""
    b = (
        builder(players=2)
        .battlefield(pid, ["mountain"] * lands + list(battlefield))
        .hand(pid, list(hand))
        .active(0)
        .max_turns(1)
    )
    if command:
        b = b.commander(pid, list(command))
    return b.build()


def discount(builder, spell: str, *, command=(), battlefield=(), pid=0) -> int:
    game = table(builder, command=command, battlefield=battlefield, hand=(spell,))
    return cost_reduction(game.state, pid, game.state.registry.get(spell))


def can_cast(game, def_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == def_id
        for a in game.legal_actions()
    )


class TestTheDiscountAppliesFromTheCommandZone:
    """The claim the whole capability exists for."""

    def test_a_dragon_spell_is_cheaper_while_the_commander_waits(self, builder):
        assert discount(builder, DRAGON, command=[EMINENCE]) == 1

    def test_and_it_is_the_command_zone_doing_it(self, builder):
        """Nothing else on the table. With no commander there is no discount."""
        assert discount(builder, DRAGON) == 0

    def test_the_cast_is_actually_offered_at_the_reduced_price(self, builder):
        """Legality and payment read one function, so the offer is the charge.

        {4}{R} on four Mountains is a mana short. The command zone is what
        closes the gap, and this is the assertion a battlefield-only
        approximation cannot pass.
        """
        assert not can_cast(table(builder, lands=4), DRAGON)
        assert can_cast(table(builder, lands=4, command=[EMINENCE]), DRAGON)


class TestTheDiscountAppliesFromTheBattlefieldToo:
    """"…or on the battlefield" is the second zone on one static, not a second
    ability, because being gathered from either *is* the "as long as"."""

    def test_the_same_card_in_play_discounts_the_same_spell(self, builder):
        assert discount(builder, DRAGON, battlefield=[EMINENCE]) == 1

    def test_both_zones_are_declared_on_one_ability(self, registry):
        (ability,) = registry.get(EMINENCE).abilities
        assert ability.active_zones == (Zone.BATTLEFIELD, Zone.COMMAND)


class TestTheCounterfactualIsDeadWhereItMatters:
    """`t_battlefield_dragon`: the same static with `active_zones` omitted.

    It passes every authoring gate — no expectation key can observe a price —
    and is a different card in the one zone a commander starts every game in.
    """

    def test_the_old_shape_still_works_from_play(self, builder):
        assert discount(builder, DRAGON, battlefield=[BATTLEFIELD_ONLY]) == 1

    def test_and_discounts_nothing_from_the_command_zone(self, builder):
        assert discount(builder, DRAGON, command=[BATTLEFIELD_ONLY]) == 0

    def test_the_two_disagree_exactly_there(self, builder):
        assert discount(builder, DRAGON, command=[EMINENCE]) == 1
        assert discount(builder, DRAGON, command=[BATTLEFIELD_ONLY]) == 0

    def test_and_agree_everywhere_else(self, builder):
        for where in ("battlefield", "nowhere"):
            kwargs = {} if where == "nowhere" else {"battlefield": [EMINENCE]}
            real = discount(builder, DRAGON, **kwargs)
            kwargs = {} if where == "nowhere" else {"battlefield": [BATTLEFIELD_ONLY]}
            old = discount(builder, DRAGON, **kwargs)
            assert real == old, f"they must only differ in the command zone, not {where}"


class TestOther:
    """"**Other** Dragon spells" — the word the command zone made load-bearing."""

    def test_the_commander_does_not_discount_its_own_cast(self, builder):
        assert discount(builder, EMINENCE, command=[EMINENCE]) == 0, (
            "a nine-mana commander that discounts itself is a different card"
        )

    def test_without_the_word_it_would(self, registry):
        """The counterfactual, taken at the filter.

        Drop `exclude_self` and the commander's own printed face matches its own
        `affects_spells` in every other respect -- it is a Dragon spell you cast
        -- so the word is the only thing standing between a nine-drop and a
        {1} discount on itself.
        """
        from automtg.engine.characteristics import _matches_printed

        card = registry.get(EMINENCE)
        filt = dict(card.abilities[0].static["affects_spells"])
        assert filt.pop("exclude_self") is True
        assert _matches_printed(card, filt)


class TestWhatItDoesNotDiscount:
    def test_a_spell_that_is_not_a_dragon(self, builder):
        assert discount(builder, BEAR, command=[EMINENCE]) == 0

    def test_an_opponents_dragon(self, builder):
        """`controller: "you"` is measured against the static's own source,
        which in the command zone is the seat that owns the zone."""
        game = table(builder, command=[EMINENCE], hand=(DRAGON,))
        assert cost_reduction(game.state, 1, game.state.registry.get(DRAGON)) == 0

    def test_a_battlefield_only_static_is_not_collected_from_the_command_zone(
        self, builder
    ):
        """The inverse of Anger: a commander's ordinary anthem is not live while
        it waits in the command zone, and this walk must not make it so."""
        assert discount(builder, DRAGON, command=[BATTLEFIELD_ONLY]) == 0


class TestAnEmblemMayNowBeAStatic:
    """114.4 — an emblem's abilities work from the command zone, all of them.

    Refused at load time until this walk existed, because a "creatures you
    control get +1/+1" emblem would have loaded clean and done nothing.
    """

    def setup_board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + [BEAR])
            .active(0)
            .max_turns(1)
            .build(advance=False)
        )
        return game

    def test_an_object_wide_emblem_static_reaches_the_characteristic_layers(
        self, builder
    ):
        game = self.setup_board(builder)
        bear = only_oid(game, BEAR)
        before = chars(game.state, bear).power
        give_emblem(game.state, WALKER, 0, 0)
        game.state.bump_chars()
        assert chars(game.state, bear).power == before + 1

    def test_a_player_wide_emblem_static_reaches_its_own_walk(self, builder):
        """`_active_player_statics` walks the battlefield itself rather than
        reading `_battlefield_statics`, so it needed its own command-zone line."""
        game = self.setup_board(builder)
        assert player_extra_land_drops(game.state, 0) == 0
        give_emblem(game.state, WALKER, 0, 0)
        game.state.bump_chars()
        assert player_extra_land_drops(game.state, 0) == 1

    def test_the_emblem_belongs_to_the_player_who_got_it(self, builder):
        game = self.setup_board(builder)
        give_emblem(game.state, WALKER, 0, 0)
        game.state.bump_chars()
        assert player_extra_land_drops(game.state, 1) == 0

    def test_the_loader_puts_every_emblem_static_in_the_command_zone(self, registry):
        (emblem,) = registry.get(WALKER).emblems
        assert [a.active_zones for a in emblem.abilities] == [
            (Zone.COMMAND,),
            (Zone.COMMAND,),
        ]


class TestTheLoader:
    def test_the_command_zone_is_admitted(self):
        card = compile_card(_static_card(["command"]))
        assert card.abilities[0].active_zones == (Zone.COMMAND,)

    def test_a_zone_nothing_collects_is_still_refused(self):
        """`hand` would load clean and never once be gathered."""
        with pytest.raises(DslError, match="command zone"):
            compile_card(_static_card(["hand"]))

    def test_other_is_refused_where_no_price_could_read_it(self):
        """`exclude_self` is read by `spell_cost_reduction` itself, not by
        `_matches_printed`, so it is kept out of the shared spell-filter set --
        on `cast_from_graveyard` it would be a word that does nothing."""
        card = CardModel.model_validate(
            {
                "id": "t_bad_other",
                "name": "Test Bad Other",
                "oracle_text": "You may cast creature spells from your graveyard.",
                "mana_cost": "{2}{B}",
                "types": ["Creature"],
                "power": 2,
                "toughness": 2,
                "abilities": [
                    {
                        "kind": "static",
                        "text": "You may cast creature spells from your graveyard.",
                        "effect": "cast_from_graveyard",
                        "affects_spells": {
                            "controller": "you",
                            "types": ["Creature"],
                            "exclude_self": True,
                        },
                        "static_max_per_turn": 1,
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="exclude_self"):
            compile_card(card)


def _static_card(zones: list[str]) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_zone_probe",
            "name": "Test Zone Probe",
            "oracle_text": "Other Dragon spells you cast cost {1} less to cast.",
            "mana_cost": "{4}{R}",
            "types": ["Creature"],
            "subtypes": ["Dragon"],
            "power": 4,
            "toughness": 4,
            "abilities": [
                {
                    "kind": "static",
                    "text": "Other Dragon spells you cast cost {1} less to cast.",
                    "effect": "spell_cost_reduction",
                    "active_zones": zones,
                    "affects_spells": {
                        "controller": "you",
                        "subtypes": ["Dragon"],
                        "exclude_self": True,
                    },
                    "amount": {"const": 1},
                }
            ],
        }
    )
