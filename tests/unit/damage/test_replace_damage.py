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

----

**The recipient may be a seat, and the two recipient filters are a union.**

    "If a source you control would deal damage to an opponent or a permanent
     an opponent controls, it deals double that damage instead."
                                            -- Twinflame Tyrant

`affects` is permanent-only by construction -- a player is not a permanent --
so the printed "to an opponent" had no spelling at all: the static had to be
written without a recipient filter, which is Furnace of Rath restricted to your
sources and doubles your own Pyroclasm onto your own board, the damage your own
City of Brass deals to *you*, and your own fight damage onto your own creature.
Strictly stronger than printed on offence and strictly worse on defence, which
is a catastrophically different card and is what
`TestTheAsymmetryIsTheWholeCard` exists to refuse.

`affects_player` is the seat half. It was accepted by the loader on this static
already and read by nothing -- a silent no-op, the worst of the three outcomes
-- and is now read in `damage_multiplier`'s player branch. The two filters are a
**union**, not the conjunction every other pair of filters in the DSL forms: one
damage event is dealt either to a player or to a permanent and never to both, so
ANDing them would double nothing at all.

**And "a source you control" is not "a permanent you control".** 109.5's source
of damage is the instant on the stack as readily as the creature on the
battlefield, and `op_damage`'s dealer for a burn spell is the resolving *spell*
object. `_matches` refuses anything off the battlefield by construction, so a
`damage_source` matched through it cannot name a spell. The widening is keyed on
the filter's shape rather than a new key: a `damage_source` naming **only**
``controller`` is answered off the dealer's controller in whatever zone it
stands, and the moment a card names a type, an attachment or any other
characteristic it is describing a permanent and gets the permanent reading. The
Flail's "another **creature**" and the Tyrant's "a **source** you control" are
different sentences and the filters say so.

Fiery Emancipation is the second witness for the source half and `t_rd_scourge`
the shape that names only the seat, so each half can be measured without the
other.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach, damage_permanent, damage_player
from commanderblitz.engine.structs import TargetRef
from tests.conftest import only_oid, pass_until, two_seat_board

FLAIL = "t_rd_flail"  # both filtered lines, combat only
FURNACE = "t_rd_furnace"  # neither filter, any damage
BEAR = "t_rd_bear"  # 2/2
OGRE = "t_rd_ogre"  # 3/9, tough enough to be hit repeatedly
LINKER = "t_rd_lifelinker"  # 2/2 lifelink
TYRANT = "t_rd_tyrant"  # Twinflame Tyrant: a seat *or* a permanent, your sources
EMANCIPATION = "t_rd_emancipation"  # "a source you control", x3, no recipient named
SCOURGE = "t_rd_scourge"  # "to an opponent" and nothing else
SCORCH = "t_rd_scorch"  # {R} instant, 3 damage to target player


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
        game = two_seat_board(builder, mine=[FLAIL, BEAR], theirs=[OGRE])
        bear = equip(game, FLAIL, BEAR)
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, bear, is_combat=True
        )
        assert dealt == 4

    def test_and_the_damage_really_is_marked(self, builder):
        """The return value and the board have to agree: several callers read
        one and the state-based actions read the other."""
        game = two_seat_board(builder, mine=[FLAIL, BEAR], theirs=[OGRE])
        bear = equip(game, FLAIL, BEAR)
        damage_permanent(game.state, only_oid(game, OGRE), 2, bear, is_combat=True)
        assert marked(game, only_oid(game, OGRE)) == 4

    def test_an_unequipped_creature_does_not(self, builder):
        """The Flail is on the battlefield and attached to nothing, so its
        `{"attached": true}` filter finds nobody."""
        game = two_seat_board(builder, mine=[FLAIL, BEAR], theirs=[OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, only_oid(game, BEAR), is_combat=True
        )
        assert dealt == 2

    def test_a_different_creature_does_not(self, builder):
        """Equipped is equipped: the Ogre's own blow is not doubled by the
        first line. Measured against a recipient the *second* line cannot
        match either -- an opposing Bear rather than the equipped creature --
        so this is the source filter alone."""
        game = two_seat_board(builder, mine=[FLAIL, OGRE], theirs=[BEAR])
        equip(game, FLAIL, OGRE)
        dealt = damage_permanent(
            game.state, only_oid(game, BEAR), 3, only_oid(game, OGRE), is_combat=True
        )
        assert dealt == 6, "…doubled by the first line, since the Ogre is equipped"


class TestTheRecipientFilter:
    """"…if another creature would deal combat damage **to equipped
    creature**"."""

    def test_a_creature_hitting_the_equipped_creature_deals_double(self, builder):
        game = two_seat_board(builder, mine=[FLAIL, OGRE], theirs=[BEAR])
        ogre = equip(game, FLAIL, OGRE)
        dealt = damage_permanent(
            game.state, ogre, 2, only_oid(game, BEAR), is_combat=True
        )
        assert dealt == 4

    def test_a_noncreature_source_does_not(self, builder):
        """"another **creature**". The Flail itself is a source with no
        creature type, and a burn spell would be another."""
        game = two_seat_board(builder, mine=[FLAIL, OGRE])
        ogre = equip(game, FLAIL, OGRE)
        dealt = damage_permanent(
            game.state, ogre, 2, only_oid(game, FLAIL), is_combat=True
        )
        assert dealt == 2

    def test_a_creature_hitting_something_else_does_not(self, builder):
        game = two_seat_board(builder, mine=[FLAIL, OGRE], theirs=[BEAR])
        equip(game, FLAIL, OGRE)
        dealt = damage_permanent(
            game.state, only_oid(game, BEAR), 3, only_oid(game, OGRE), is_combat=True
        )
        assert dealt == 6, "…but the Ogre is equipped, so its own line doubles it"

    def test_the_two_lines_compound_on_one_exchange(self, builder):
        """Both statics are separate replacements of different events, so the
        equipped creature's blow out and the blocker's blow back are each
        doubled once."""
        game = two_seat_board(builder, mine=[FLAIL, OGRE], theirs=[BEAR])
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
        game = two_seat_board(builder, mine=[FLAIL, BEAR], theirs=[OGRE])
        bear = equip(game, FLAIL, BEAR)
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, bear, is_combat=False
        )
        assert dealt == 2

    def test_a_static_without_the_clause_takes_both(self, builder):
        """Furnace of Rath does not say "combat", so it doubles a burn spell."""
        game = two_seat_board(builder, mine=[FURNACE], theirs=[OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, None, is_combat=False
        )
        assert dealt == 4


class TestDamageToAPlayer:
    def test_an_unfiltered_replacement_reaches_a_player(self, builder):
        """"to a permanent **or player**" -- Furnace of Rath names neither end."""
        game = two_seat_board(builder, mine=[FURNACE])
        life = game.state.players[1].life
        damage_player(game.state, 1, 3, None, is_combat=False)
        assert game.state.players[1].life == life - 6

    def test_the_equipped_creature_doubles_its_hit_on_a_player(self, builder):
        """The Flail's first line filters the *dealer* only, so it follows the
        equipped creature through to the face."""
        game = two_seat_board(builder, mine=[FLAIL, BEAR])
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
        game = two_seat_board(builder, mine=[FLAIL, OGRE], theirs=[BEAR])
        equip(game, FLAIL, OGRE)
        life = game.state.players[0].life
        damage_player(game.state, 0, 3, only_oid(game, BEAR), is_combat=True)
        assert game.state.players[0].life == life - 3


class TestEverythingDownstreamSeesTheDoubledNumber:
    def test_lifelink_gains_the_doubled_amount(self, builder):
        """702.15b: lifelink gains "that much life", and "that much" is what was
        actually dealt. A doubling applied after lifelink would gain half."""
        game = two_seat_board(builder, mine=[FLAIL, LINKER], theirs=[OGRE])
        linker = equip(game, FLAIL, LINKER)
        life = game.state.players[0].life
        damage_permanent(game.state, only_oid(game, OGRE), 2, linker, is_combat=True)
        assert game.state.players[0].life == life + 4

    def test_damage_dealt_carries_the_doubled_amount(self, builder):
        """Enrage, Sengir and "damaged this turn" all read this event, so a
        replacement it did not know about would be a card lying to them."""
        game = two_seat_board(builder, mine=[FLAIL, BEAR], theirs=[OGRE])
        bear = equip(game, FLAIL, BEAR)
        mark = len(game.state.events)
        damage_permanent(game.state, only_oid(game, OGRE), 2, bear, is_combat=True)
        dealt = [e for e in game.state.events[mark:] if e.type == "damage_dealt"]
        assert [e.data["amount"] for e in dealt] == [4]


class TestSeveralCompound:
    def test_two_replacements_multiply(self, builder):
        """614.5 applies each once. Multiplication commutes, so 616.1's unasked
        ordering cannot show between two of these."""
        game = two_seat_board(builder, mine=[FLAIL, FURNACE, BEAR], theirs=[OGRE])
        bear = equip(game, FLAIL, BEAR)
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, bear, is_combat=True
        )
        assert dealt == 8

    def test_a_replacement_does_not_re_apply_to_its_own_output(self, builder):
        game = two_seat_board(builder, mine=[FURNACE], theirs=[OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 3, None, is_combat=True
        )
        assert dealt == 6


class TestWithNothingOnTheTable:
    """The control: damage is damage."""

    def test_a_permanent(self, builder):
        game = two_seat_board(builder, mine=[BEAR], theirs=[OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, only_oid(game, BEAR), is_combat=True
        )
        assert dealt == 2

    def test_a_player(self, builder):
        game = two_seat_board(builder, mine=[BEAR])
        life = game.state.players[1].life
        damage_player(game.state, 1, 2, only_oid(game, BEAR), is_combat=True)
        assert game.state.players[1].life == life - 2


def scorch_at(game, pid: int) -> None:
    """Cast `t_rd_scorch` at a seat and let it resolve.

    The dealer is the resolving **spell**, which is the whole point: a source
    on the stack is not a permanent, and it is what "a source you control"
    mostly means on the cards that print it.
    """
    for action in game.legal_actions():
        if action.kind is not ActionKind.CAST or action.source is None:
            continue
        obj = game.state.objects.get(action.source)
        if obj is None or obj.def_id != SCORCH:
            continue
        if TargetRef.player(pid) in action.targets:
            game.apply(action)
            pass_until(game, lambda g: not g.state.stack)
            return
    raise AssertionError(
        f"no cast of {SCORCH} targeting player {pid}; "
        f"legal: {[(a.kind.value, a.targets) for a in game.legal_actions()]}"
    )


class TestTheAsymmetryIsTheWholeCard:
    """Twinflame Tyrant doubles **outwards only**, and both ends say so.

    A version that dropped the recipient filter would pass every "the damage
    was doubled" assertion above and be a strictly different card: Furnace of
    Rath restricted to your sources, doubling your own sweeper onto your own
    board and the ping your own painland deals to you. Each half of the union
    is asserted here *against its mirror* for that reason.
    """

    def test_damage_to_an_opponent_doubles(self, builder):
        """The `affects_player` half -- the one `affects` could never spell."""
        game = two_seat_board(builder, mine=[TYRANT, BEAR])
        life = game.state.players[1].life
        damage_player(game.state, 1, 3, only_oid(game, BEAR), is_combat=True)
        assert game.state.players[1].life == life - 6

    def test_damage_to_you_does_not(self, builder):
        """Your own City of Brass, your own Mana Crypt, your own Pyroclasm's
        half that hits you. "To an opponent" is not "to a player"."""
        game = two_seat_board(builder, mine=[TYRANT, BEAR])
        life = game.state.players[0].life
        damage_player(game.state, 0, 3, only_oid(game, BEAR), is_combat=False)
        assert game.state.players[0].life == life - 3

    def test_damage_to_an_opponents_permanent_doubles(self, builder):
        """The `affects` half, in the same static and the same event."""
        game = two_seat_board(builder, mine=[TYRANT, BEAR], theirs=[OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, only_oid(game, BEAR), is_combat=True
        )
        assert dealt == 4

    def test_damage_to_your_own_permanent_does_not(self, builder):
        """Your sweeper, your fight spell, your own blocker taking its blow --
        none of them are "a permanent an opponent controls"."""
        game = two_seat_board(builder, mine=[TYRANT, BEAR, OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, only_oid(game, BEAR), is_combat=False
        )
        assert dealt == 2

    def test_an_opponents_source_is_not_doubled_either(self, builder):
        """"A source **you control**". Without the dealer filter this would be
        Furnace of Rath pointed one way, doubling the opponent's own burn back
        at them -- stronger than printed, and not what the card says."""
        game = two_seat_board(builder, mine=[TYRANT], theirs=[BEAR, OGRE])
        life = game.state.players[1].life
        damage_player(game.state, 1, 3, only_oid(game, BEAR), is_combat=True)
        assert game.state.players[1].life == life - 3

    def test_the_four_cases_in_one_position(self, builder):
        """The asymmetry as one table, because it is one sentence.

        Each cell measured on the same board, so no cell can pass by accident
        of a different position.
        """
        game = two_seat_board(builder, mine=[TYRANT, BEAR, OGRE], theirs=[BEAR, OGRE])
        mine = only_oid(game, BEAR, 0)
        their_ogre = only_oid(game, OGRE, 1)
        my_ogre = only_oid(game, OGRE, 0)
        to_them = damage_permanent(game.state, their_ogre, 2, mine, is_combat=False)
        to_mine = damage_permanent(game.state, my_ogre, 2, mine, is_combat=False)
        their_life = game.state.players[1].life
        damage_player(game.state, 1, 2, mine, is_combat=False)
        my_life = game.state.players[0].life
        damage_player(game.state, 0, 2, mine, is_combat=False)
        assert (
            to_them,
            to_mine,
            their_life - game.state.players[1].life,
            my_life - game.state.players[0].life,
        ) == (4, 2, 4, 2)


class TestTheRecipientFiltersAreAUnionNotAConjunction:
    """One damage event is dealt to a player *or* a permanent, never to both.

    ANDing the two filters would double nothing at all, which is the failure
    mode that looks exactly like the static not being there.
    """

    def test_a_seat_only_filter_never_reaches_a_permanent(self, builder):
        """`t_rd_scourge` says "to an opponent" and stops there, so an
        opponent's creature is not a recipient it named."""
        game = two_seat_board(builder, mine=[SCOURGE, BEAR], theirs=[OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, only_oid(game, BEAR), is_combat=True
        )
        assert dealt == 2

    def test_a_seat_only_filter_reaches_the_seat(self, builder):
        game = two_seat_board(builder, mine=[SCOURGE, BEAR])
        life = game.state.players[1].life
        damage_player(game.state, 1, 3, only_oid(game, BEAR), is_combat=True)
        assert game.state.players[1].life == life - 6

    def test_a_permanent_only_filter_still_never_reaches_a_seat(self, builder):
        """The pre-existing reading, unchanged: the Flail's second line has no
        `affects_player`, so a player is not among its recipients."""
        game = two_seat_board(builder, mine=[FLAIL, OGRE], theirs=[BEAR])
        equip(game, FLAIL, OGRE)
        life = game.state.players[0].life
        damage_player(game.state, 0, 3, only_oid(game, BEAR), is_combat=True)
        assert game.state.players[0].life == life - 3

    def test_naming_neither_still_reaches_both(self, builder):
        """Furnace of Rath, the control for the whole union."""
        game = two_seat_board(builder, mine=[FURNACE], theirs=[OGRE])
        life = game.state.players[1].life
        damage_player(game.state, 1, 3, None, is_combat=False)
        dealt = damage_permanent(game.state, only_oid(game, OGRE), 2, None, is_combat=False)
        assert (game.state.players[1].life, dealt) == (life - 6, 4)


class TestASourceYouControlIsNotAPermanentYouControl:
    """109.5: the resolving instant is a source of damage too.

    `_matches` refuses anything off the battlefield, so a `damage_source`
    answered through it can only ever name a permanent. A filter naming **only**
    ``controller`` is read off the dealer's controller in whatever zone it
    stands, which is what "a source you control" says.
    """

    def test_your_burn_spell_doubles_at_an_opponent(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [TYRANT, "mountain"])
            .hand(0, [SCORCH])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        life = game.state.players[1].life
        scorch_at(game, 1)
        assert game.state.players[1].life == life - 6

    def test_your_burn_spell_aimed_at_yourself_does_not(self, builder):
        """The recipient half still holds over a spell source: the Tyrant
        names an opponent, and you are not one."""
        game = (
            builder(players=2)
            .battlefield(0, [TYRANT, "mountain"])
            .hand(0, [SCORCH])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        life = game.state.players[0].life
        scorch_at(game, 0)
        assert game.state.players[0].life == life - 3

    def test_an_opponents_burn_spell_is_not_doubled(self, builder):
        """The dealer filter is "you control", and a spell on the stack has a
        controller like anything else."""
        game = (
            builder(players=2)
            .battlefield(0, [TYRANT])
            .battlefield(1, ["mountain"])
            .hand(1, [SCORCH])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        life = game.state.players[0].life
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().player == 1,
        )
        scorch_at(game, 0)
        assert game.state.players[0].life == life - 3

    def test_fiery_emancipation_triples_your_spell(self, builder):
        """The second witness, and with no recipient named at all -- so this
        measures the source widening and nothing else."""
        game = (
            builder(players=2)
            .battlefield(0, [EMANCIPATION, "mountain"])
            .hand(0, [SCORCH])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        life = game.state.players[1].life
        scorch_at(game, 1)
        assert game.state.players[1].life == life - 9

    def test_it_still_follows_your_creatures(self, builder):
        """The widening adds spells; it does not drop the permanents the same
        filter always matched."""
        game = two_seat_board(builder, mine=[EMANCIPATION, BEAR], theirs=[OGRE])
        dealt = damage_permanent(
            game.state, only_oid(game, OGRE), 2, only_oid(game, BEAR), is_combat=True
        )
        assert dealt == 6

    def test_a_characteristic_naming_filter_stays_permanent_only(self, builder):
        """The Flail's second line filters its dealer on
        ``{"controller": "any", "types": ["Creature"]}``. It names a type, so
        it is a sentence about a permanent and a spell is not one -- otherwise
        "another **creature**" would start reading burn spells."""
        game = (
            builder(players=2)
            .battlefield(0, [FLAIL, OGRE, "mountain"])
            .hand(0, [SCORCH])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        equip(game, FLAIL, OGRE)
        life = game.state.players[1].life
        scorch_at(game, 1)
        assert game.state.players[1].life == life - 3, "the Flail names a creature"


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

    def test_the_seat_filter_reaches_the_compiled_static(self):
        """`affects_player` was accepted here before anything read it, which
        is the one failure a loader test can catch and a game cannot: the card
        loads clean, prints "to an opponent", and doubles everybody's damage.
        Pinned on the compiled dict rather than on `compile_card` returning,
        because the whitelist copy loop is where it would be dropped."""
        card = compile_card(
            self._card(
                self._static(
                    damage_multiplier=2,
                    affects_player="opponent",
                    affects={"controller": "opponent"},
                )
            )
        )
        static = card.abilities[0].static
        assert static["affects_player"] == "opponent"
        assert static["affects"] == {"controller": "opponent"}

    def test_a_source_filter_may_name_only_the_controller(self):
        """"A source you control" -- the shape `damage_multiplier` answers off
        the dealer's controller whatever zone it is in."""
        compile_card(
            self._card(
                self._static(damage_multiplier=2, damage_source={"controller": "you"})
            )
        )

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
