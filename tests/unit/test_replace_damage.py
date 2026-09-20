"""Damage multiplied on the way out.

    "If equipped creature would deal combat damage, it deals **double** that
    damage instead.
     If another creature would deal combat damage to equipped creature, it
     deals double that damage to equipped creature instead."
                                            -- Inquisitor's Flail

No damage-modifying static existed at all. The five multiplier replacements the
engine had were life and card economy -- `replace_life_gain`,
`replace_life_loss`, `replace_draw`, `replace_mill`, `replace_token_creation` --
all of them **player-wide** and keyed by player id, so none could be attached to
a permanent or filtered by who was dealing to whom. The only damage-facing
statics, `prevent_damage` and `protection`, subtract or forbid and have no way
to add.

`replace_life_loss` is the near miss and is a genuinely different sentence:
damage is not life loss. It is marked on creatures, feeds deathtouch and infect,
and only incidentally reduces a life total -- so doubling the loss would leave a
doubled hit on a *creature* undoubled, and would double a Village Rites as well.

**Filtered on both ends**, which is what the five could not do: `damage_source`
is "if **equipped creature** would deal", `affects` is "…**to** equipped
creature". The Flail prints one line of each, on one card, which is why both
filters had to exist at once.

**A replacement, not a trigger.** Applied inside `damage_permanent` and
`damage_player`, the two points every damage in the game passes through, so
deathtouch marks on the doubled number, lifelink gains it, the damage ledger and
the commander tally record it and `DAMAGE_DEALT` carries it. A trigger dealing
the extra damage afterwards would be a second event: two `DAMAGE_DEALT`s, two
lifelink gains, and a creature dying to the first half before the second landed.

**Where in the sequence.** After the preventions -- what is prevented was never
dealt -- and before the wither, infect and planeswalker branches, each of which
is a different *place to put* the damage rather than a change to how much there
is. 616.1 would let the damaged object's controller order a prevention against a
doubling and this engine does not ask; doubling last means "prevent the next 3"
answers 3 of the printed damage rather than 3 of the doubled damage, which is
the order its controller would have chosen -- the same judgement the shield
counter makes.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import Step
from automtg.engine.errors import DslError
from automtg.engine.primitives import attach, damage_permanent, damage_player
from tests.conftest import only_oid

FLAIL = "t_rd_flail"  # both filtered lines, combat only
FURNACE = "t_rd_furnace"  # neither filter, any damage
BEAR = "t_rd_bear"  # 2/2
OGRE = "t_rd_ogre"  # 3/9, tough enough to be hit repeatedly
LINKER = "t_rd_lifelinker"  # 2/2 lifelink


def board(builder, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def equip(game, equipment: str, creature: str) -> int:
    """Attach the Equipment to the creature, returning the creature's oid."""
    target = only_oid(game, creature)
    assert attach(game.state, only_oid(game, equipment), target)
    game.state.bump_chars()
    return target


def marked(game, oid: int) -> int:
    return game.state.objects[oid].damage


class TestTheSourceFilter:
    """"If **equipped creature** would deal combat damage…"."""

    def test_the_equipped_creature_deals_double(self, builder):
        game = board(builder, mine=[FLAIL, BEAR], theirs=[OGRE])
        bear = equip(game, FLAIL, BEAR)
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, bear, is_combat=True
        )
        assert dealt == 4

    def test_and_the_damage_really_is_marked(self, builder):
        """The return value and the board have to agree: several callers read
        one and the state-based actions read the other."""
        game = board(builder, mine=[FLAIL, BEAR], theirs=[OGRE])
        bear = equip(game, FLAIL, BEAR)
        damage_permanent(game.state, only_oid(game, OGRE), 2, bear, is_combat=True)
        assert marked(game, only_oid(game, OGRE)) == 4

    def test_an_unequipped_creature_does_not(self, builder):
        """The Flail is on the battlefield and attached to nothing, so its
        `{"attached": true}` filter finds nobody."""
        game = board(builder, mine=[FLAIL, BEAR], theirs=[OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, only_oid(game, BEAR), is_combat=True
        )
        assert dealt == 2

    def test_a_different_creature_does_not(self, builder):
        """Equipped is equipped: the Ogre's own blow is not doubled by the
        first line. Measured against a recipient the *second* line cannot
        match either -- an opposing Bear rather than the equipped creature --
        so this is the source filter alone."""
        game = board(builder, mine=[FLAIL, OGRE], theirs=[BEAR])
        equip(game, FLAIL, OGRE)
        dealt = damage_permanent(
            game.state, only_oid(game, BEAR), 3, only_oid(game, OGRE), is_combat=True
        )
        assert dealt == 6, "…doubled by the first line, since the Ogre is equipped"


class TestTheRecipientFilter:
    """"…if another creature would deal combat damage **to equipped
    creature**"."""

    def test_a_creature_hitting_the_equipped_creature_deals_double(self, builder):
        game = board(builder, mine=[FLAIL, OGRE], theirs=[BEAR])
        ogre = equip(game, FLAIL, OGRE)
        dealt = damage_permanent(
            game.state, ogre, 2, only_oid(game, BEAR), is_combat=True
        )
        assert dealt == 4

    def test_a_noncreature_source_does_not(self, builder):
        """"another **creature**". The Flail itself is a source with no
        creature type, and a burn spell would be another."""
        game = board(builder, mine=[FLAIL, OGRE])
        ogre = equip(game, FLAIL, OGRE)
        dealt = damage_permanent(
            game.state, ogre, 2, only_oid(game, FLAIL), is_combat=True
        )
        assert dealt == 2

    def test_a_creature_hitting_something_else_does_not(self, builder):
        game = board(builder, mine=[FLAIL, OGRE], theirs=[BEAR])
        equip(game, FLAIL, OGRE)
        dealt = damage_permanent(
            game.state, only_oid(game, BEAR), 3, only_oid(game, OGRE), is_combat=True
        )
        assert dealt == 6, "…but the Ogre is equipped, so its own line doubles it"

    def test_the_two_lines_compound_on_one_exchange(self, builder):
        """Both statics are separate replacements of different events, so the
        equipped creature's blow out and the blocker's blow back are each
        doubled once."""
        game = board(builder, mine=[FLAIL, OGRE], theirs=[BEAR])
        ogre = equip(game, FLAIL, OGRE)
        out = damage_permanent(
            game.state, only_oid(game, BEAR), 3, ogre, is_combat=True
        )
        back = damage_permanent(
            game.state, ogre, 2, only_oid(game, BEAR), is_combat=True
        )
        assert (out, back) == (6, 4)


class TestCombatOnly:
    def test_noncombat_damage_is_untouched(self, builder):
        """The Flail says "combat damage" and means it: a burn spell the
        equipped creature's ability deals is not doubled."""
        game = board(builder, mine=[FLAIL, BEAR], theirs=[OGRE])
        bear = equip(game, FLAIL, BEAR)
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, bear, is_combat=False
        )
        assert dealt == 2

    def test_a_static_without_the_clause_takes_both(self, builder):
        """Furnace of Rath does not say "combat", so it doubles a burn spell."""
        game = board(builder, mine=[FURNACE], theirs=[OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, None, is_combat=False
        )
        assert dealt == 4


class TestDamageToAPlayer:
    def test_an_unfiltered_replacement_reaches_a_player(self, builder):
        """"to a permanent **or player**" -- Furnace of Rath names neither end."""
        game = board(builder, mine=[FURNACE])
        life = game.state.players[1].life
        damage_player(game.state, 1, 3, None, is_combat=False)
        assert game.state.players[1].life == life - 6

    def test_the_equipped_creature_doubles_its_hit_on_a_player(self, builder):
        """The Flail's first line filters the *dealer* only, so it follows the
        equipped creature through to the face."""
        game = board(builder, mine=[FLAIL, BEAR])
        bear = equip(game, FLAIL, BEAR)
        life = game.state.players[1].life
        damage_player(game.state, 1, 2, bear, is_combat=True)
        assert game.state.players[1].life == life - 4

    def test_a_recipient_filter_never_matches_a_player(self, builder):
        """A player is not a permanent, and "…to equipped creature" is a
        sentence about one. Without this the Flail's second line would double
        every creature's damage to every player while it was equipped.

        Measured with a source the *first* line cannot match -- the Bear is
        unequipped -- so only the second line is in question.
        """
        game = board(builder, mine=[FLAIL, OGRE], theirs=[BEAR])
        equip(game, FLAIL, OGRE)
        life = game.state.players[0].life
        damage_player(game.state, 0, 3, only_oid(game, BEAR), is_combat=True)
        assert game.state.players[0].life == life - 3


class TestEverythingDownstreamSeesTheDoubledNumber:
    def test_lifelink_gains_the_doubled_amount(self, builder):
        """702.15b: lifelink gains "that much life", and "that much" is what was
        actually dealt. A doubling applied after lifelink would gain half."""
        game = board(builder, mine=[FLAIL, LINKER], theirs=[OGRE])
        linker = equip(game, FLAIL, LINKER)
        life = game.state.players[0].life
        damage_permanent(game.state, only_oid(game, OGRE), 2, linker, is_combat=True)
        assert game.state.players[0].life == life + 4

    def test_damage_dealt_carries_the_doubled_amount(self, builder):
        """Enrage, Sengir and "damaged this turn" all read this event, so a
        replacement it did not know about would be a card lying to them."""
        game = board(builder, mine=[FLAIL, BEAR], theirs=[OGRE])
        bear = equip(game, FLAIL, BEAR)
        mark = len(game.state.events)
        damage_permanent(game.state, only_oid(game, OGRE), 2, bear, is_combat=True)
        dealt = [e for e in game.state.events[mark:] if e.type == "damage_dealt"]
        assert [e.data["amount"] for e in dealt] == [4]


class TestSeveralCompound:
    def test_two_replacements_multiply(self, builder):
        """614.5 applies each once. Multiplication commutes, so 616.1's unasked
        ordering cannot show between two of these."""
        game = board(builder, mine=[FLAIL, FURNACE, BEAR], theirs=[OGRE])
        bear = equip(game, FLAIL, BEAR)
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, bear, is_combat=True
        )
        assert dealt == 8

    def test_a_replacement_does_not_re_apply_to_its_own_output(self, builder):
        game = board(builder, mine=[FURNACE], theirs=[OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 3, None, is_combat=True
        )
        assert dealt == 6


class TestWithNothingOnTheTable:
    """The control: damage is damage."""

    def test_a_permanent(self, builder):
        game = board(builder, mine=[BEAR], theirs=[OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, only_oid(game, BEAR), is_combat=True
        )
        assert dealt == 2

    def test_a_player(self, builder):
        game = board(builder, mine=[BEAR])
        life = game.state.players[1].life
        damage_player(game.state, 1, 2, only_oid(game, BEAR), is_combat=True)
        assert game.state.players[1].life == life - 2


class TestTheLoaderPlacesIt:
    def _card(self, ability):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "If a source would deal damage, it deals double that damage instead.",
                "mana_cost": "{R}",
                "types": ["Enchantment"],
                "abilities": [ability],
            }
        )

    def _static(self, **extra):
        return {
            "kind": "static",
            "text": "If a source would deal damage, it deals double that damage instead.",
            "effect": "replace_damage",
            **extra,
        }

    def test_a_bare_doubler_loads(self):
        compile_card(self._card(self._static(damage_multiplier=2)))

    def test_both_filters_load(self):
        compile_card(
            self._card(
                self._static(
                    damage_multiplier=2,
                    combat_only=True,
                    damage_source={"attached": True},
                    affects={"attached": True},
                )
            )
        )

    def test_without_a_multiplier_it_is_refused(self):
        """A replacement that says nothing about how much damage is dealt is
        not this effect; it would load clean and double nothing."""
        with pytest.raises(DslError, match="needs 'damage_multiplier'"):
            compile_card(self._card(self._static()))

    def test_a_multiplier_of_one_is_refused(self):
        with pytest.raises(DslError, match="must be 2 or more"):
            compile_card(self._card(self._static(damage_multiplier=1)))

    def test_a_multiplier_of_zero_is_refused(self):
        """0 prevents the damage, which is `prevent_damage`'s sentence and a
        much stronger card."""
        with pytest.raises(DslError, match="must be 2 or more"):
            compile_card(self._card(self._static(damage_multiplier=0)))

    def test_a_source_filter_may_only_read_printed_characteristics(self):
        with pytest.raises(DslError, match="printed characteristics"):
            compile_card(
                self._card(
                    self._static(damage_multiplier=2, damage_source={"zone": "graveyard"})
                )
            )

    def test_the_fields_are_refused_on_another_static(self):
        """Ignored elsewhere, the card would print a doubling it never does."""
        with pytest.raises(DslError, match="only mean anything on a replace_damage"):
            compile_card(
                self._card(
                    {
                        "kind": "static",
                        "text": "Creatures you control get +1/+1.",
                        "effect": "buff",
                        "affects": {"controller": "you"},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                        "damage_multiplier": 2,
                    }
                )
            )
