""""Spend this mana only to activate abilities."

Cryptic Trilobite; Omen Hawker. `mana_restriction` already had the cast/activate
split Secluded Courtyard needed, but every group either half could hold was a set
of literal card type or subtype **names**: `RestrictionGroup.satisfied_by` asks
``required <= names``, where `names` is the types and subtypes of the source
whose ability is being activated. This line names no type at all, and there is
no name that every source has -- so no group in the language could mean it.

The wildcard is the other end of that axis: ``"any"`` compiles to a single
**empty** `RestrictionGroup`, which `satisfied_by` accepts for every purpose of
its kind, nothing being required. The restriction is then carried entirely by the
*other* half being omitted -- with no `cast` groups the mana can never pay for a
spell, and that is the whole of what the printed line forbids.

The three sinks below are an Enchantment, a Land and a Creature with the same
`{2}` ability, and they are the argument that this could not have been faked by
enumeration: no literal name is shared by all three, so any finite group that
funded one would fail another. The Land is the sharpest of them -- a restriction
language built for creature tribes has nothing to say about it.

Two near misses are kept as live cards, because a wildcard is only worth having
if the spellings available before it are worse:

- **The restriction omitted entirely**, which is what the shipped Omen Hawker and
  Automated Artificer approximations do today. That is plainly unrestricted mana
  that also casts spells -- a strictly *better* card, and silent.
  `TestTheUnrestrictedSpellingLeaks` is that claim.
- **Both halves wildcarded**, which is the same strictly better card wearing a
  restriction, and the one shape that would turn ``"any"`` into a way to say
  nothing. The loader refuses it, as it refuses a bare ``"any"`` -- bare means
  the `cast` half, so it would read as mana that pays for every spell ever
  printed and merely declines to activate an ability, one keystroke from the
  line that was meant.

``[]`` stays a load error throughout: a blank is what a mistake looks like, and
reading it as "everything" is how a strictly better card ships quietly.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.costs import mana_sources
from automtg.engine.enums import ActionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.mana import ACTIVATE, CAST, ManaRestriction, ManaSource, SpendPurpose
from tests.conftest import only_oid, pass_until

TRILOBITE = "t_trilobite_mana"  # {"activate": "any"}
UNRESTRICTED = "t_unrestricted_font"  # no restriction at all -- the leak
CAST_ANY = "t_cast_any_font"  # {"cast": "any"} -- the mirror

ENCHANTMENT_SINK = "t_sink_enchantment"
LAND_SINK = "t_sink_land"
CREATURE_SINK = "t_sink_creature"
SPELL = "t_generic_spell"  # a {2} Sorcery

SINKS = (ENCHANTMENT_SINK, LAND_SINK, CREATURE_SINK)


def position(builder, font: str, sink: str | None = None, hand=()):
    """One font and at most one sink, on a board with no other mana whatsoever.

    Starved deliberately: with any second source available the test could not
    tell a permitted payment from one the font never funded. `wastes` is absent
    for that reason, and the opponent's board is a single Plains so the turn
    structure still works.
    """
    board = [font] + ([sink] if sink else [])
    return (
        builder(players=2)
        .battlefield(0, board)
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 10)
        .hand(0, list(hand))
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def settle(game):
    game._advance()
    pass_until(game, lambda g: g.pending() is not None)


def activation_of(game, card_id: str):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and game.state.objects[a.source].def_id == card_id
        ),
        None,
    )


def cast_of(game, card_id: str):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        ),
        None,
    )


def source_with(restriction: ManaRestriction) -> ManaSource:
    return ManaSource(
        oid=1, ability_index=0, options=((0, 0, 0, 0, 0, 1),), restriction=restriction
    )


class TestTheWildcardGroupItself:
    """An empty group is satisfied by every purpose of its kind, and no other."""

    def source(self) -> ManaSource:
        return source_with(ManaRestriction(activate=_compiled(TRILOBITE).activate))

    @pytest.mark.parametrize(
        "names",
        [
            {"enchantment"},
            {"land"},
            {"creature", "crab"},
            {"artifact", "creature", "construct"},
            frozenset(),
        ],
        ids=["enchantment", "land", "creature", "artifact-creature", "nothing-at-all"],
    )
    def test_it_funds_an_ability_of_any_source(self, names):
        assert self.source().permits(SpendPurpose(ACTIVATE, frozenset(names)))

    def test_the_empty_name_set_is_the_point(self):
        """A source with no types at all is still "an ability".

        The case no enumeration reaches, and the reason this is a wildcard
        rather than a long list: `required <= names` holds against the empty
        set only when nothing is required.
        """
        assert self.source().permits(SpendPurpose(ACTIVATE, frozenset()))

    @pytest.mark.parametrize(
        "names", [{"sorcery"}, {"creature", "crab"}, frozenset()], ids=["sorcery", "creature", "none"]
    )
    def test_it_funds_no_spell_at_all(self, names):
        """The near miss, and the whole of the printed restriction.

        The wildcard permits everything *of its kind*; the restriction lives in
        the `cast` half being empty, which `ManaRestriction` documents as "never".
        """
        assert not self.source().permits(SpendPurpose(CAST, frozenset(names)))


class TestTheCompiledCard:
    def test_the_activate_half_is_one_empty_group(self, registry):
        restriction = _compiled(TRILOBITE)
        assert len(restriction.activate) == 1
        group = restriction.activate[0]
        assert not group.required and not group.forbidden

    def test_the_cast_half_is_empty_and_that_is_the_restriction(self, registry):
        assert _compiled(TRILOBITE).cast == ()

    def test_the_mirror_card_is_the_other_way_round(self, registry):
        restriction = _compiled(CAST_ANY)
        assert len(restriction.cast) == 1 and restriction.activate == ()


class TestInAGame:
    """The three sinks, and the spell the mana must refuse."""

    @pytest.mark.parametrize("sink", SINKS)
    def test_it_funds_an_ability_of_any_permanent_type(self, builder, sink):
        game = position(builder, TRILOBITE, sink)
        settle(game)
        assert activation_of(game, sink) is not None, f"{sink}'s {{2}} ability went unfunded"

    def test_it_does_not_cast_a_spell(self, builder):
        """The strictly better card this capability exists to avoid."""
        game = position(builder, TRILOBITE, hand=[SPELL])
        settle(game)
        assert cast_of(game, SPELL) is None

    def test_the_payment_really_happens(self, builder):
        """The drift test: legality saying yes and payment saying no would
        strand the ability halfway, so this applies the action and reads the
        board afterwards."""
        game = position(builder, TRILOBITE, ENCHANTMENT_SINK)
        settle(game)
        before = game.state.players[0].life
        game.apply(activation_of(game, ENCHANTMENT_SINK))
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert game.state.players[0].life == before + 1
        assert game.state.objects[only_oid(game, TRILOBITE)].tapped, "the font really paid"

    def test_the_solver_is_offered_the_font_for_an_ability_and_not_for_a_spell(self, builder):
        """A guard against the wildcard being compiled away to "no restriction".

        `mana_sources` drops a restricted source unless the purpose matches, and
        offers an unrestricted one for every purpose including `None`. So the
        three answers below are the shape of the restriction as the solver sees
        it, and they separate this card from `t_unrestricted_font` -- which is
        offered all three times.
        """
        game = position(builder, TRILOBITE)
        font = only_oid(game, TRILOBITE)

        def offered(purpose) -> bool:
            return any(s.oid == font for s in mana_sources(game.state, 0, purpose=purpose))

        assert offered(SpendPurpose(ACTIVATE, frozenset({"enchantment"})))
        assert not offered(SpendPurpose(CAST, frozenset({"sorcery"})))
        assert not offered(None), "restricted mana is not offered with no purpose in mind"

    def test_the_unrestricted_font_is_offered_for_all_three(self, builder):
        """The control for the assertion above, and the reason it is not vacuous."""
        game = position(builder, UNRESTRICTED)
        font = only_oid(game, UNRESTRICTED)

        def offered(purpose) -> bool:
            return any(s.oid == font for s in mana_sources(game.state, 0, purpose=purpose))

        assert offered(SpendPurpose(ACTIVATE, frozenset({"enchantment"})))
        assert offered(SpendPurpose(CAST, frozenset({"sorcery"})))
        assert offered(None)


class TestTheUnrestrictedSpellingLeaks:
    """Kept as a live card: the strictly better card shipped today.

    Omen Hawker and Automated Artificer both print a restriction and both ship
    without one, so each currently casts spells its printed line forbids. This
    is that card, and the assertion is what the wildcard fixes.
    """

    def test_it_casts_the_spell_the_printed_line_forbids(self, builder):
        game = position(builder, UNRESTRICTED, hand=[SPELL])
        settle(game)
        assert cast_of(game, SPELL) is not None, (
            "an omitted restriction is ordinary mana -- the leak the wildcard closes"
        )

    def test_and_it_funds_the_ability_too(self, builder):
        """Which is why the leak is invisible from the ability side alone."""
        game = position(builder, UNRESTRICTED, ENCHANTMENT_SINK)
        settle(game)
        assert activation_of(game, ENCHANTMENT_SINK) is not None


class TestTheMirrorHalf:
    """`{"cast": "any"}` -- the same word on the other half, and the inverse card."""

    def test_it_casts_the_spell(self, builder):
        game = position(builder, CAST_ANY, hand=[SPELL])
        settle(game)
        assert cast_of(game, SPELL) is not None

    def test_it_does_not_fund_an_ability(self, builder):
        game = position(builder, CAST_ANY, ENCHANTMENT_SINK)
        settle(game)
        assert activation_of(game, ENCHANTMENT_SINK) is None


class TestTheLoaderRefusesTheShapesThatSayNothing:
    def card(self, restriction):
        return {
            "id": "t_probe_any",
            "name": "Probe Any",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "activated",
                    "text": "{T}: Add {C}.",
                    "cost": {"tap": True},
                    "is_mana_ability": True,
                    "mana_restriction": restriction,
                    "effects": [{"op": "add_mana", "mana": "{C}", "player": "you"}],
                }
            ],
        }

    def test_both_halves_wildcarded(self):
        """Ordinary mana wearing a restriction."""
        with pytest.raises(DslError, match="restricts nothing"):
            compile_card(
                CardModel.model_validate(self.card({"cast": "any", "activate": "any"}))
            )

    def test_a_bare_wildcard(self):
        """Bare means the cast half, so this is one keystroke from the opposite card."""
        with pytest.raises(DslError, match="bare 'any'"):
            compile_card(CardModel.model_validate(self.card("any")))

    def test_an_empty_list_is_still_an_error(self):
        """The distinction the word exists to preserve: blank is not "everything"."""
        with pytest.raises(DslError, match="omit it for ordinary mana"):
            compile_card(CardModel.model_validate(self.card({"activate": []})))

    def test_a_wildcard_beside_a_named_half_is_fine(self):
        """Automated Artificer's shape: "to activate an ability **or** cast an
        artifact spell" -- a wildcard activate half beside a literal cast one."""
        card = compile_card(
            CardModel.model_validate(self.card({"activate": "any", "cast": ["artifact"]}))
        )
        restriction = card.abilities[0].mana_restriction
        assert len(restriction.activate) == 1 and not restriction.activate[0].required
        assert restriction.cast == (
            type(restriction.activate[0])(frozenset({"artifact"}), frozenset()),
        )


def _compiled(card_id: str) -> ManaRestriction:
    from automtg.cards.registry import CardRegistry
    from tests.conftest import TEST_CARD_DIR

    registry = CardRegistry.from_paths(
        [TEST_CARD_DIR / "mana_restriction_activate_any.cards.json"]
    )
    ability = next(a for a in registry.get(card_id).abilities if a.mana_restriction is not None)
    return ability.mana_restriction
