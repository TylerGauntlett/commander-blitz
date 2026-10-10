"""The ten tokens the Atraxa, Praetors' Voice superfriends deck prints, each proved.

Rule 111.4: a token's characteristics are exactly the ones the effect creating
it specifies. `create_token` names an id in a **closed** pool, and nothing on
the op recolours, resizes or retypes what it names -- so a near miss is not a
cheaper spelling of the card, it is a different card. Every one of these was a
gap record because the nearest id in the pool was wrong in a way that matters:

| new | the card | shipped neighbour | the difference |
|---|---|---|---|
| `wizard_2_2_u` | Kasmina, Enigmatic Mentor | `drake_2_2_u_flying` | Wizard, and no flying |
| `fractal_0_0_gu` | Kasmina, Enigma Sage | `germ_0_0_b` | green and blue Fractal |
| `spirit_1_1_w_flying` | Kaya the Inexorable | `spirit_1_1_c` | white, and flying |
| `octopus_8_8_u` | Kiora, Master of the Depths | `kraken_8_8_u` | Octopus |
| `kraken_9_9_u` | Kiora, the Crashing Wave | `kraken_8_8_u` | the body |
| `kor_ally_1_1_w` | Oath of Gideon | `soldier_1_1_w` | Kor Ally |
| `vampire_knight_1_1_b_lifelink` | Sorin, Grim Nemesis | `vampire_1_1_b_lifelink` | Knight |
| `pirate_2_2_b_menace` | Vraska, Relic Seeker | `zombie_2_2_b` | Pirate, and menace |
| `illusion_2_2_u_sac_when_targeted` | Jace, Cunning Castaway | `illusion_1_1_u` | the body, and the trigger |
| `tamiyos_notebook` | Tamiyo, Compleated Sage | -- | a legendary Book with two abilities |

The two with a printed ability of their own are proved by behaviour rather than
by fields, because a token definition never goes through the authoring gates --
`verify.py` casts a card and reads the board, and a token is not cast -- so this
file is the only coverage they have:

- **Jace's Illusion** dies to *a spell* aimed at it, whoever cast it, and not to
  an ability. The shape is Goldspan Dragon's `targeted_by: "spell"`; without it
  the Illusion would be sacrificed to its own controller's equip.
- **Tamiyo's Notebook** discounts generic mana only, draws on a tap, and is
  legendary -- a second one made by a second Tamiyo is put into the graveyard.

Vraska the Unseen's Assassin is deliberately **not** here: "that player loses
the game" needs a `lose_game` op the engine does not have, and `win_game` on
the controller is not the same sentence in a multiplayer game.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine import sba
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.structs import TargetRef
from tests.conftest import _default_answer, oids_of, only_oid

PRINTED: tuple[tuple[str, int, int, frozenset[str], frozenset[str], frozenset[str]], ...] = (
    ("wizard_2_2_u", 2, 2, frozenset("U"), frozenset({"Wizard"}), frozenset()),
    ("fractal_0_0_gu", 0, 0, frozenset("GU"), frozenset({"Fractal"}), frozenset()),
    ("spirit_1_1_w_flying", 1, 1, frozenset("W"), frozenset({"Spirit"}), frozenset({"flying"})),
    ("octopus_8_8_u", 8, 8, frozenset("U"), frozenset({"Octopus"}), frozenset()),
    ("kraken_9_9_u", 9, 9, frozenset("U"), frozenset({"Kraken"}), frozenset()),
    ("kor_ally_1_1_w", 1, 1, frozenset("W"), frozenset({"Kor", "Ally"}), frozenset()),
    ("vampire_knight_1_1_b_lifelink", 1, 1, frozenset("B"), frozenset({"Vampire", "Knight"}),
     frozenset({"lifelink"})),
    ("pirate_2_2_b_menace", 2, 2, frozenset("B"), frozenset({"Pirate"}), frozenset({"menace"})),
    ("illusion_2_2_u_sac_when_targeted", 2, 2, frozenset("U"), frozenset({"Illusion"}),
     frozenset()),
)

ILLUSION = "illusion_2_2_u_sac_when_targeted"
NOTEBOOK = "tamiyos_notebook"

PUMP = "t_pump_spell"  # {G} instant, target creature gets +3/+3
BOLT = "t_bolt"  # {R} instant, 3 damage to any target
PASSAGE = "t_passage"  # {4}, {T}: target creature can't be blocked this turn
DRAW_SPELL = "t_draw_spell"  # {2}{U} sorcery, draw two cards
BEAR = "t_bear"  # {1}{G} creature


def settle(game, limit: int = 80) -> None:
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def position(builder, token: str | None, *, lands=(), hand=(), pid: int = 0, active: int = 0,
             opponent_lands=(), opponent_hand=(), count: int = 1):
    """`count` copies of `token` for seat `pid`, in seat `active`'s main phase."""
    game = (
        builder(players=2)
        .battlefield(0, list(lands))
        .battlefield(1, list(opponent_lands))
        .hand(0, list(hand))
        .hand(1, list(opponent_hand))
        .library(0, ["island"] * 10)
        .library(1, ["island"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
        .build(advance=False)
    )
    # The token goes in before the engine advances: with no creature on the
    # board a targeted spell in hand is no play at all, and auto-pass would roll
    # the position into the next turn before the Illusion ever arrived.
    if token is not None:
        create_token(game.state, token, pid, count)
    game.state.bump_chars()
    game._advance()
    return game


def _act(game, kind: ActionKind, card_id: str, target_oid: int | None = None) -> None:
    for action in game.legal_actions():
        if action.kind is not kind or action.source is None:
            continue
        obj = game.state.objects.get(action.source)
        if obj is None or obj.def_id != card_id:
            continue
        if target_oid is not None and TargetRef.obj(target_oid) not in action.targets:
            continue
        game.apply(action)
        return
    raise AssertionError(
        f"no {kind.value} of {card_id} at {target_oid}; "
        f"legal: {[(a.kind.value, a.label) for a in game.legal_actions()]}"
    )


def can_cast(game, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


class TestEachTokenIsWhatItsCardPrints:
    """Size, colour, creature types and keywords, read off the characteristics
    layer -- which is what every rule asks, rather than the printed fields."""

    @pytest.mark.parametrize(
        "token,power,toughness,colors,subtypes,keywords",
        PRINTED,
        ids=[row[0] for row in PRINTED],
    )
    def test_it_matches(self, builder, token, power, toughness, colors, subtypes, keywords):
        game = position(builder, None)
        (oid,) = create_token(game.state, token, 0, 1)
        game.state.bump_chars()
        c = chars(game.state, oid)

        assert (c.power, c.toughness) == (power, toughness)
        assert set(c.colors) == set(colors)
        assert {str(s) for s in c.subtypes} == set(subtypes)
        assert {str(k) for k in c.keywords} == set(keywords)
        assert "Creature" in {str(t) for t in c.types}

    def test_every_one_of_them_is_marked_a_token(self, registry):
        for tid in [row[0] for row in PRINTED] + [NOTEBOOK]:
            assert registry.get(tid).is_token, tid


class TestTheNearMissesAreStillSeparateTokens:
    """Each new id sits beside a shipped one that differs by a word or a number.
    If a pair ever converges, one of the cards naming them is quietly wrong."""

    def test_the_eight_eight_kraken_is_still_eight_eight(self, registry):
        kraken = registry.get("kraken_8_8_u")
        assert (kraken.power, kraken.toughness) == (8, 8)
        assert "Kraken" in kraken.subtypes

    def test_the_octopus_is_not_a_kraken(self, registry):
        """Kiora's -8 makes Octopuses; the Kraken is the right body, wrong type."""
        assert "Kraken" not in registry.get("octopus_8_8_u").subtypes

    def test_the_plain_vampire_is_not_a_knight(self, registry):
        assert "Knight" not in registry.get("vampire_1_1_b_lifelink").subtypes

    def test_the_colorless_spirit_does_not_fly(self, registry):
        spirit = registry.get("spirit_1_1_c")
        assert not spirit.colors and "flying" not in spirit.keywords

    def test_the_small_illusion_has_no_trigger(self, registry):
        small = registry.get("illusion_1_1_u")
        assert (small.power, small.toughness) == (1, 1)


class TestTheFractalIsAZeroZero:
    """Kasmina's Fractal is printed 0/0; its size is the X counters the ability
    puts on it, which is the card's job, not the token's. A bare one is put into
    the graveyard by 704.5f -- which proves nothing sneaked a size in."""

    def test_a_bare_fractal_does_not_survive(self, builder):
        game = position(builder, None)
        create_token(game.state, "fractal_0_0_gu", 0, 1)
        game.state.bump_chars()
        assert oids_of(game, "fractal_0_0_gu"), "it arrives"
        sba.run(game.state)
        assert not oids_of(game, "fractal_0_0_gu")


class TestJacesIllusionIsSacrificedToASpell:
    """"When this creature becomes the target of a spell, sacrifice it.\""""

    def test_your_own_spell(self, builder):
        game = position(builder, ILLUSION, lands=["forest"], hand=[PUMP])
        illusion = only_oid(game, ILLUSION, 0)
        _act(game, ActionKind.CAST, PUMP, illusion)
        settle(game)
        assert illusion not in game.state.battlefield

    def test_an_opponents_spell(self, builder):
        """No caster is named, so the removal aimed at it kills it too -- and the
        sacrifice resolves first, so the Bolt then has no legal target."""
        game = position(
            builder, ILLUSION, active=1, opponent_lands=["mountain"], opponent_hand=[BOLT]
        )
        illusion = only_oid(game, ILLUSION, 0)
        _act(game, ActionKind.CAST, BOLT, illusion)
        settle(game)
        assert illusion not in game.state.battlefield
        # 111.7: a token that left the battlefield ceases to exist.
        assert illusion not in game.state.objects or (
            game.state.objects[illusion].zone is not Zone.BATTLEFIELD
        )

    def test_an_ability_does_not(self, builder):
        """The restriction that makes it Jace's Illusion: an activated ability
        aimed at it -- here your own -- leaves it on the battlefield."""
        game = position(builder, ILLUSION, lands=["mountain"] * 4 + [PASSAGE])
        illusion = only_oid(game, ILLUSION, 0)
        _act(game, ActionKind.ACTIVATE, PASSAGE, illusion)
        settle(game)
        assert illusion in game.state.battlefield

    def test_a_spell_aimed_elsewhere_does_not(self, builder):
        game = position(builder, ILLUSION, lands=["forest", "forest", "forest"], hand=[PUMP])
        create_token(game.state, "wizard_2_2_u", 0, 1)
        game.state.bump_chars()
        illusion = only_oid(game, ILLUSION, 0)
        _act(game, ActionKind.CAST, PUMP, only_oid(game, "wizard_2_2_u", 0))
        settle(game)
        assert illusion in game.state.battlefield


class TestTamiyosNotebook:
    """"Spells you cast cost {2} less to cast" and "{T}: Draw a card." on a
    legendary colorless Book artifact."""

    def test_it_is_a_legendary_colorless_book_artifact(self, builder):
        game = position(builder, NOTEBOOK)
        c = chars(game.state, only_oid(game, NOTEBOOK, 0))
        assert "Legendary" in {str(s) for s in c.supertypes}
        assert {str(t) for t in c.types} == {"Artifact"}
        assert {str(s) for s in c.subtypes} == {"Book"}
        assert not c.colors

    def test_it_takes_two_generic_off_a_spell(self, builder):
        """{2}{U} for one Island: castable only with the Notebook out."""
        without = position(builder, None, lands=["island"], hand=[DRAW_SPELL])
        assert not can_cast(without, DRAW_SPELL)

        game = position(builder, NOTEBOOK, lands=["island"], hand=[DRAW_SPELL])
        assert can_cast(game, DRAW_SPELL)

    def test_it_never_touches_coloured_mana(self, builder):
        """The boundary: {1}{G} still needs its {G}; the discount has only one
        generic to take and stops there."""
        game = position(builder, NOTEBOOK, lands=["island"], hand=[BEAR])
        assert not can_cast(game, BEAR)
        game = position(builder, NOTEBOOK, lands=["forest"], hand=[BEAR])
        assert can_cast(game, BEAR)

    def test_it_does_not_discount_an_opponents_spell(self, builder):
        game = position(
            builder, NOTEBOOK, active=1, opponent_lands=["island"], opponent_hand=[DRAW_SPELL]
        )
        assert not can_cast(game, DRAW_SPELL)

    def test_tapping_it_draws_a_card(self, builder):
        game = position(builder, NOTEBOOK)
        notebook = only_oid(game, NOTEBOOK, 0)
        before = len(game.state.players[0].hand)
        _act(game, ActionKind.ACTIVATE, NOTEBOOK)
        settle(game)
        assert len(game.state.players[0].hand) == before + 1
        assert game.state.objects[notebook].tapped

    def test_a_second_notebook_is_put_into_the_graveyard(self, builder):
        """The legend rule reads the name, and the token's name is the printed
        "Tamiyo's Notebook" -- so a second Tamiyo ultimate leaves one."""
        game = position(builder, None)
        create_token(game.state, NOTEBOOK, 0, 2)
        game.state.bump_chars()
        assert len(oids_of(game, NOTEBOOK, 0)) == 2, "both arrive"
        sba.run(game.state)
        assert len(oids_of(game, NOTEBOOK, 0)) == 1
