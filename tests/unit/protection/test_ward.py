"""Ward, and specifically ward **granted to somebody else**.

"Each other Human you control gets +1/+0 and has ward {1}." — Coppercoat
Vanguard, the witness.

Ward on yourself already shipped: `t_warded` and Vein Ripper both write the
trigger out by hand on the creature that has it, and `carddef.CLOAK_WARD` is the
same trigger supplied by rule 701.61a. None of that generalises, because a
keyword written as a per-card trigger cannot be handed to a *different*
permanent — and `KNOWN_KEYWORDS` is a set of bare strings with nowhere to put the
`{1}`, so ward could not be a keyword either.

Two things had to exist. A **cost-carrying ward** (`carddef.ward_ability`, one
interned trigger per distinct cost) and a **continuous effect** that gives it to
a filtered set (`characteristics.granted_wards`, read by
`triggers._candidate_abilities`).

**The claim that decides the design is who the trigger's source is.** The cheap
version puts one `becomes_target` trigger on the Vanguard, filtered to
`{"controller": "you", "subtypes": ["Human"], "exclude_self": true}`. In a duel
it is nearly indistinguishable — same prompt, same payer, same counter — and it
is a different, weaker card: the trigger's source is the Vanguard, so an
opponent who answers the ward trigger by killing the Vanguard escapes a tax the
printed card still collects, because the printed ability belongs to the creature
being targeted. `TestTheGranterIsNotTheSource` is that difference, played out on
a real stack.

The rest is scope (603.2d fires it as the spell goes on the stack, so the tax is
paid before the removal does anything) and the wearing-off, which for a static
means the moment its source leaves the battlefield.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.carddef import CLOAK_WARD, ward_ability
from commanderblitz.engine.characteristics import chars, ward_abilities
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid, pass_until, settle

LORD = "t_ward_lord"  # "Each other Human you control gets +1/+0 and has ward {1}."
HUMAN = "t_human"  # a plain 2/2 Human Soldier
BEAR = "t_bear"  # a plain 2/2 Bear, so not a Human
SACRIFICER = "t_ward_sacrifice"  # printed "Ward--Sacrifice a creature."
BOLT = "t_bolt"  # {R} instant, 3 damage to a creature


def board(builder, mine=(LORD, HUMAN), bolts: int = 1, theirs=()):
    """P0 holds the board; P1 holds the removal and the mana to pay ward with."""
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 2 + list(mine))
        .battlefield(1, ["mountain"] * 6 + list(theirs))
        .hand(1, [BOLT] * bolts)
        .active(0)
        .build()
    )


def bolt_at(game, oid: int) -> None:
    """P1 points a Test Bolt at ``oid``, passing priority until they can."""

    def offer(g):
        return next(
            (
                a
                for a in g.legal_actions()
                if a.kind is ActionKind.CAST
                and g.state.objects[a.source].def_id == BOLT
                and any(ref.id == oid for ref in a.targets)
            ),
            None,
        )

    pass_until(game, lambda g: offer(g) is not None)
    game.apply(offer(game))


def ward_prompt(game) -> object | None:
    """Run the game forward until somebody is asked to pay ward, or nobody is."""
    pass_until(
        game,
        lambda g: (
            (d := g.pending()) is not None and d.kind is DecisionKind.MAY
        )
        or (not g.state.stack and not g.state.pending_triggers),
    )
    decision = game.pending()
    return decision if decision is not None and decision.kind is DecisionKind.MAY else None


def answer(game, kind: ActionKind) -> None:
    game.apply(next(a for a in game.legal_actions() if a.kind is kind))


class TestTheKeywordCarriesACost:
    """What `Keyword` could not hold, because it is a set of bare strings."""

    def test_the_same_cost_is_the_same_ability(self):
        """Interned, so two Humans with ward {1} have one ability between them —
        the way two creatures with flying have one keyword, and the way
        `_granter_of`'s identity comparison and `_queue`'s per-(object, index)
        tallies both assume."""
        assert ward_ability({"mana": "{1}"}) is ward_ability({"mana": "{1}"})

    def test_a_different_cost_is_a_different_ability(self):
        assert ward_ability({"mana": "{1}"}) is not ward_ability({"mana": "{2}"})

    def test_the_unset_fields_of_a_cost_model_do_not_split_it(self):
        """A `CostModel` dump carries every field it did not use. Ward {1} written
        by a card and ward {1} written in a test must not be two abilities."""
        assert ward_ability({"mana": "{1}"}) is ward_ability(
            {"mana": "{1}", "tap": False, "discard": 0, "sacrifice": None}
        )

    def test_cloaks_ward_is_the_same_mechanism(self):
        """701.61a's ward {2} was a hand-written twin of this trigger, and was one
        only because the keyword had nowhere to put its cost."""
        assert CLOAK_WARD is ward_ability({"mana": "{2}"})

    def test_the_cost_reaches_the_prompt(self):
        assert ward_ability({"mana": "{3}"}).effects[0]["pay"] == {"mana": "{3}"}
        assert ward_ability({"mana": "{3}"}).text == "Ward {3}"


class TestWhoHasIt:
    """The static's filter, read off the characteristic layer rather than played."""

    def test_the_filtered_set_has_ward(self, builder):
        game = board(builder)
        assert ward_abilities(game.state, only_oid(game, HUMAN, 0))

    def test_the_source_does_not(self, builder):
        """"Each **other** Human" — `exclude_self`."""
        game = board(builder)
        assert not ward_abilities(game.state, only_oid(game, LORD, 0))

    def test_a_creature_outside_the_filter_does_not(self, builder):
        game = board(builder, mine=(LORD, HUMAN, BEAR))
        assert not ward_abilities(game.state, only_oid(game, BEAR, 0))

    def test_an_opponents_human_does_not(self, builder):
        """"…you control". A pod is where this would otherwise go unnoticed."""
        game = board(builder, theirs=(HUMAN,))
        assert not ward_abilities(game.state, only_oid(game, HUMAN, 1))

    def test_two_sources_grant_two_wards(self, builder):
        """Two instances of a keyword ability are two triggers, so the second
        Vanguard really does double the tax rather than being redundant."""
        game = board(builder, mine=(LORD, LORD, HUMAN))
        assert len(ward_abilities(game.state, only_oid(game, HUMAN, 0))) == 2

    def test_the_buff_half_of_the_same_line_still_applies(self, builder):
        """The `+1/+0` is an ordinary anthem and shares one printed sentence with
        the ward, which is why shipping it alone would have been half a card."""
        game = board(builder)
        assert chars(game.state, only_oid(game, HUMAN, 0)).power == 3

    def test_it_wears_off_with_its_source(self, builder):
        """A static, so it ends the moment the granter leaves the battlefield —
        which is what `grant_ability` (a one-shot op) could not have said."""
        game = board(builder)
        human = only_oid(game, HUMAN, 0)
        lord = only_oid(game, LORD, 0)
        assert ward_abilities(game.state, human)

        bolt_at(game, lord)
        settle(game)

        assert game.state.objects[lord].zone is not Zone.BATTLEFIELD
        assert not ward_abilities(game.state, human)


class TestTheTax:
    def test_targeting_a_granted_human_asks_the_caster_to_pay(self, builder):
        game = board(builder)
        bolt_at(game, only_oid(game, HUMAN, 0))

        decision = ward_prompt(game)
        assert decision is not None
        assert decision.player == 1, "ward taxes the caster, not the ward's controller"

    def test_refusing_counters_the_spell(self, builder):
        game = board(builder)
        human = only_oid(game, HUMAN, 0)
        bolt_at(game, human)
        assert ward_prompt(game) is not None

        answer(game, ActionKind.NO)
        settle(game)

        assert game.state.objects[human].zone is Zone.BATTLEFIELD
        assert game.state.objects[human].damage == 0

    def test_paying_lets_the_spell_through(self, builder):
        game = board(builder)
        human = only_oid(game, HUMAN, 0)
        bolt_at(game, human)
        assert ward_prompt(game) is not None

        answer(game, ActionKind.YES)
        settle(game)

        assert game.state.objects[human].zone is Zone.GRAVEYARD

    def test_the_ungranted_creature_is_taxed_nothing(self, builder):
        """The control. Same board, same spell, a creature the filter misses."""
        game = board(builder, mine=(LORD, HUMAN, BEAR))
        bear = only_oid(game, BEAR, 0)
        bolt_at(game, bear)

        assert ward_prompt(game) is None
        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_a_creature_with_no_ward_static_at_all_is_taxed_nothing(self, builder):
        """And the witness that the static is doing the work rather than the
        subtype: the same Human, with nobody granting."""
        game = board(builder, mine=(HUMAN,))
        human = only_oid(game, HUMAN, 0)
        bolt_at(game, human)

        assert ward_prompt(game) is None
        assert game.state.objects[human].zone is Zone.GRAVEYARD


class TestTheGranterIsNotTheSource:
    """The whole reason this is a granted ability rather than a filtered trigger.

    603.2d puts the ward trigger on the stack as the removal spell is cast, so
    the opponent gets priority with it sitting there. Killing the granter in that
    window is the line the cheap implementation loses to.
    """

    def test_killing_the_granter_in_response_does_not_escape_the_tax(self, builder):
        game = board(builder, bolts=2)
        human = only_oid(game, HUMAN, 0)
        lord = only_oid(game, LORD, 0)

        bolt_at(game, human)  # ward triggers and goes on the stack
        bolt_at(game, lord)  # ...and the opponent answers it by killing the lord
        pass_until(game, lambda g: g.state.objects[lord].zone is not Zone.BATTLEFIELD)
        assert not ward_abilities(game.state, human), "the static is gone"

        decision = ward_prompt(game)
        assert decision is not None, "the trigger already on the stack still resolves"
        assert decision.player == 1

        answer(game, ActionKind.NO)
        settle(game)
        assert game.state.objects[human].zone is Zone.BATTLEFIELD

    def test_the_trigger_belongs_to_the_warded_creature(self, builder):
        """Read off the log, which is also where a player would read it. The
        cheap implementation puts the Vanguard's name on this line, and that is
        not a cosmetic difference — `_queue` writes the same `source` into the
        `TriggerInstance` that decides who the ability's source is."""
        game = board(builder)
        human = only_oid(game, HUMAN, 0)
        lord = only_oid(game, LORD, 0)
        bolt_at(game, human)

        fired = [e for e in game.state.events if e.type == "ability_triggered"]
        assert len(fired) == 1
        assert fired[0].source == human
        assert fired[0].source != lord
        assert fired[0].data["card"] == HUMAN
        assert fired[0].player == 0, "the warded creature's controller controls it"

    def test_the_ability_is_the_rules_own_rather_than_an_index_into_a_card(self, builder):
        """A negative `ability_index`. Index 0 on the Human would resolve
        whatever that card prints first — nothing, here, which is the quiet
        version of this going wrong."""
        game = board(builder)
        bolt_at(game, only_oid(game, HUMAN, 0))

        fired = next(e for e in game.state.events if e.type == "ability_triggered")
        assert fired.data["ability"] < 0


class TestACostThatIsNotMana:
    """Ward is a `pay` spec, not a mana string — Vein Ripper's
    "Ward--Sacrifice a creature" needs nothing the mana form does not."""

    def test_it_asks_for_the_sacrifice(self, builder):
        game = board(builder, mine=(SACRIFICER,), theirs=(BEAR,))
        bolt_at(game, only_oid(game, SACRIFICER, 0))

        decision = ward_prompt(game)
        assert decision is not None
        assert decision.player == 1

    def test_refusing_counters_the_spell(self, builder):
        game = board(builder, mine=(SACRIFICER,), theirs=(BEAR,))
        warded = only_oid(game, SACRIFICER, 0)
        bolt_at(game, warded)
        assert ward_prompt(game) is not None

        answer(game, ActionKind.NO)
        settle(game)
        assert game.state.objects[warded].zone is Zone.BATTLEFIELD

    def test_a_payer_with_nothing_to_sacrifice_is_not_asked(self, builder):
        """`op_may` does not offer a cost the player cannot afford (601.2 in
        spirit) — so the spell is countered without a prompt rather than after a
        yes nobody could honour."""
        game = board(builder, mine=(SACRIFICER,))
        warded = only_oid(game, SACRIFICER, 0)
        bolt_at(game, warded)

        assert ward_prompt(game) is None
        assert game.state.objects[warded].zone is Zone.BATTLEFIELD


class TestFaceDown:
    def test_a_face_down_permanent_is_not_granted_ward(self, builder):
        """707.2's trade, the one `_compute` already makes by returning
        `FACE_DOWN_CHARS` before any static runs: a static's filter reads the
        *printed* face, so "each other Human you control" would otherwise reach
        through the shell and a ward trigger would announce what is under it."""
        game = board(builder)
        human = only_oid(game, HUMAN, 0)
        game.state.objects[human].face_down = True
        game.state.bump_chars()

        assert not ward_abilities(game.state, human)


class TestTheLoaderRefusesTheHalfCards:
    def _compile(self, ability: dict):
        model = CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [ability],
            }
        )
        return compile_card(model)

    def test_ward_without_a_cost_is_a_load_error(self):
        """Ward {0} taxes nothing and can never be declined: a keyword that
        prints on the card, shows in the log and does not exist."""
        with pytest.raises(DslError, match="ward needs a 'cost'"):
            self._compile(
                {"kind": "static", "effect": "ward", "affects": {"self_only": True}}
            )

    def test_ward_without_affects_is_a_load_error(self):
        with pytest.raises(DslError, match="needs 'affects'"):
            self._compile(
                {"kind": "static", "effect": "ward", "cost": {"mana": "{1}"}}
            )

    def test_a_cost_on_another_static_is_a_load_error(self):
        """Statics do not pay for anything, so a `cost` on one was silently
        dropped before ward gave the field a meaning."""
        with pytest.raises(DslError, match="no cost to pay"):
            self._compile(
                {
                    "kind": "static",
                    "effect": "buff",
                    "affects": {"self_only": True},
                    "power": {"const": 1},
                    "cost": {"mana": "{1}"},
                }
            )

    def test_a_malformed_ward_cost_is_a_load_error(self):
        """Through the same validator an activated ability's cost goes through,
        so ward cannot grow a second, laxer spelling of a price."""
        with pytest.raises(DslError):
            self._compile(
                {
                    "kind": "static",
                    "effect": "ward",
                    "affects": {"self_only": True},
                    "cost": {"sacrifice": {"not_a_selector_key": True}},
                }
            )
