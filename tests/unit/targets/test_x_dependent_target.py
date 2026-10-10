"""A target pool that only exists once X is known.

    "{X}, {T}: This land becomes a copy of target nontoken artifact you control
    **with mana value X**."                   -- The Mycosynth Gardens

601.2b announces X *before* 601.2c declares targets, and the engine had that
order backwards for an activated ability. `legality._ability_aims` enumerated
one activation per target tuple with X hard-coded to 0, `game._activate_ability`
asked for X afterwards, and every `EffectContext` targeting built left `x` at
its dataclass default -- so the selector's `{"x": true}` leaf read zero twice
over: once when the candidates were listed and again when 608.2b re-checked them
on resolution.

**It loads and fails silently**, which is why it needed building rather than
noticing: `validate_selector` has no guard against a value expression on
`mana_value` and `VALUE_KEYS` contains `x`, so the card compiles, offers the
artifacts whose mana value is 0, and fizzles.

**The shape is the one `ability_modes` already took.** A modal ability whose
bullets own their targets has the same problem -- 601.2b picks the mode before
601.2c declares its targets -- and it was solved by making the mode part of the
*action*: legality offers one activation per mode, each carrying only the
targets that mode owns. X is the same rule and gets the same answer: one
activation per payable X, each carrying the targets legal at that value, and
`_activate_ability` takes the number off the action rather than asking again.

Only for an ability that asks. `_targets_read_x` is gated on the cost having an
announced `{X}` and then on a target selector actually mentioning it, so every
other activation in the pool pays one attribute check and keeps its old shape.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.legality import _mentions_x, _targets_read_x
from tests.conftest import only_oid, pass_until

GARDENS = "t_xdt_gardens"  # target artifact with mana value X
PLAIN = "t_xdt_plain"  # the same ability, no X in the filter
ONE = "t_xdt_one"  # mana value 1
TWO = "t_xdt_two"  # mana value 2
THREE = "t_xdt_three"  # mana value 3


def board(builder, land: str = GARDENS, artifacts=(TWO,), lands: int = 4):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * lands)
        .battlefield(0, [land, *artifacts])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def activations(game, land: str = GARDENS):
    """Every offered activation of the copy ability, as ``(x, target def id)``."""
    oid = only_oid(game, land)
    return sorted(
        (a.x, game.state.objects[a.targets[0].id].def_id)
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == oid and a.targets
    )


class TestTheOffer:
    def test_the_artifact_is_offered_at_its_own_mana_value(self, builder):
        game = board(builder, artifacts=[TWO])
        assert (2, TWO) in activations(game)

    def test_and_at_no_other(self, builder):
        """The whole clause. Offered at X = 0 -- which is what the engine did
        before -- the land copies a two-drop for nothing."""
        assert [x for x, _ in activations(board(builder, artifacts=[TWO]))] == [2]

    def test_each_artifact_is_offered_at_its_own_value(self, builder):
        game = board(builder, artifacts=[ONE, TWO, THREE], lands=6)
        assert activations(game) == [(1, ONE), (2, TWO), (3, THREE)]

    def test_an_unaffordable_x_is_not_offered(self, builder):
        """The ceiling is `max_affordable_x` over the mana actually available,
        and the tapped land cannot help pay for itself."""
        game = board(builder, artifacts=[ONE, THREE], lands=2)
        assert activations(game) == [(1, ONE)]

    def test_with_nothing_to_copy_nothing_is_offered(self, builder):
        game = board(builder, artifacts=[])
        assert activations(game) == []


class TestWithoutTheClause:
    """The control. An ability whose targets do not read X keeps its old shape:
    one activation, X = 0, and the number asked for afterwards."""

    def test_one_activation_at_x_zero(self, builder):
        game = board(builder, land=PLAIN, artifacts=[ONE, TWO, THREE], lands=6)
        assert activations(game, PLAIN) == [(0, ONE), (0, THREE), (0, TWO)]


class TestItResolves:
    def test_the_land_becomes_the_copy(self, builder):
        """608.2b re-checks the target as the ability resolves, and "with mana
        value X" is a question with an X in it. Re-checked at 0 -- which is what
        `filter_legal` did -- the ability would fizzle every time it was paid
        for, and the land would sit there having spent the mana."""
        game = board(builder, artifacts=[TWO])
        land = only_oid(game, GARDENS)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == land and a.targets
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert game.state.card_of(game.state.objects[land]).name == "Test Artifact Two"

    def test_it_did_not_fizzle(self, builder):
        game = board(builder, artifacts=[TWO])
        land = only_oid(game, GARDENS)
        mark = len(game.state.events)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == land and a.targets
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert not [
            e for e in game.state.events[mark:] if e.type == "spell_fizzled"
        ]


class TestTheDetector:
    """`_targets_read_x` decides whether an ability changes shape at all, so it
    is worth measuring directly: a false positive multiplies every activation in
    the pool by its payable X values."""

    def test_it_finds_x_in_a_nested_value(self):
        assert _mentions_x({"mana_value": {"op": "=", "value": {"x": True}}})

    def test_it_finds_the_bare_string_spelling(self):
        assert _mentions_x({"mana_value": {"op": "=", "value": "x"}})

    def test_an_ordinary_selector_does_not(self):
        assert not _mentions_x({"types": ["Artifact"], "controller": "you"})

    def test_the_gardens_ability_reads_x(self, registry):
        card = registry.get(GARDENS)
        assert _targets_read_x(card.abilities[1])

    def test_the_plain_one_does_not(self, registry):
        """Same `{X}` cost, no X in the filter."""
        card = registry.get(PLAIN)
        assert not _targets_read_x(card.abilities[0])

    def test_a_mana_ability_does_not(self, registry):
        """No X at all -- the gate that keeps every other activation cheap."""
        card = registry.get(GARDENS)
        assert not _targets_read_x(card.abilities[0])
