""""Return target **spell or creature** to its owner's hand."

Fatehold Charm's bounce mode. One instance of the word "target" spanning the
stack and the battlefield -- a `spell_or_permanent` spec -- where "creature"
narrows only the **permanent** half: any spell is legal, and of the permanents
only creatures.

One `selector` cannot say it. `spell_or_permanent` applies its selector to both
halves, which is right for Sink into Stupor ("nonland", "an opponent controls"
are meant to narrow both) and wrong here: `types: [Creature]` on the spell half
makes the card "target **creature spell** or creature", and an instant on the
stack stops being a legal target. `permanent_selector` gives the permanent half
its own clause and leaves `selector` to the spell half.

608.2b re-checks a target by the question it was chosen by, so `still_legal`
reads the same `TargetSpec.permanent_half` `candidates` does: a creature that
stops being one before the charm resolves is no longer legal, and the charm
fizzles rather than bouncing a noncreature permanent nobody could have targeted.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.targeting import still_legal
from tests.conftest import pass_until, settle_to_priority

BOUNCE = "t_soc_bounce"  # "target spell or creature"
WIDE = "t_soc_wide"  # the near miss: "target creature spell or creature"
BEAR = "t_bear"
RELIC = "t_glory_relic"  # a noncreature permanent
BAIT = "t_plain_instant"  # a noncreature spell, {W}


def position(builder, *, their_board=(), their_hand=()):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 4)
        .battlefield(1, [*their_board, "plains", "plains"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [BOUNCE, WIDE])
        .hand(1, list(their_hand))
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def casts(game, def_id):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
    ]


def offered(game, def_id):
    return [a.targets[0] for a in casts(game, def_id) if a.targets]


def with_bait_on_stack(builder, **kw):
    """Seat 1 casts the noncreature instant; seat 0 holds priority over it."""
    game = position(builder, their_hand=[BAIT], **kw)
    game._advance()
    pass_until(game, lambda g: bool(casts(g, BAIT)))
    bait = casts(game, BAIT)[0]
    game.apply(bait)
    pass_until(game, lambda g: bool(casts(g, BOUNCE)))
    return game, bait.source


def oid_of(game, seat, def_id):
    return next(o.oid for o in game.state.battlefield_objects(seat) if o.def_id == def_id)


class TestThePermanentHalfIsCreaturesOnly:
    def test_a_creature_is_offered(self, builder):
        game = position(builder, their_board=[BEAR, RELIC])
        game._advance()
        assert oid_of(game, 1, BEAR) in [r.id for r in offered(game, BOUNCE)]

    def test_a_noncreature_permanent_is_not(self, builder):
        game = position(builder, their_board=[BEAR, RELIC])
        game._advance()
        ids = [r.id for r in offered(game, BOUNCE)]
        assert oid_of(game, 1, RELIC) not in ids
        assert not set(ids) & {o.oid for o in game.state.battlefield_objects(1) if o.def_id == "plains"}

    def test_with_no_creature_and_no_spell_it_cannot_be_cast(self, builder):
        game = position(builder, their_board=[RELIC])
        game._advance()
        assert not offered(game, BOUNCE)


class TestTheSpellHalfIsUnrestricted:
    def test_a_noncreature_spell_is_offered(self, builder):
        game, _ = with_bait_on_stack(builder)
        refs = offered(game, BOUNCE)
        assert [r.kind for r in refs] == ["stack"]

    def test_the_near_miss_refuses_it(self, builder):
        """One selector over both halves is "creature spell or creature"."""
        game, _ = with_bait_on_stack(builder)
        assert not offered(game, WIDE)


class TestItBouncesEitherOne:
    def test_a_creature_goes_to_its_owners_hand(self, builder):
        game = position(builder, their_board=[BEAR])
        game._advance()
        bear = oid_of(game, 1, BEAR)
        game.apply(next(a for a in casts(game, BOUNCE) if a.targets and a.targets[0].id == bear))
        settle_to_priority(game)

        assert game.state.objects[bear].zone is Zone.HAND
        assert bear in game.state.players[1].hand

    def test_a_spell_goes_to_its_owners_hand(self, builder):
        game, bait = with_bait_on_stack(builder)
        game.apply(casts(game, BOUNCE)[0])
        settle_to_priority(game)

        assert bait in game.state.players[1].hand


class TestTheRecheckReadsThePermanentHalf:
    def test_a_creature_is_still_legal_and_a_relic_is_not(self, builder):
        game = position(builder, their_board=[BEAR, RELIC])
        game._advance()
        state = game.state
        spec = state.registry.get(BOUNCE).targets[0]
        bear = next(r for r in offered(game, BOUNCE) if r.id == oid_of(game, 1, BEAR))
        relic = type(bear).obj(oid_of(game, 1, RELIC))

        assert still_legal(state, 0, spec, bear, None)
        assert not still_legal(state, 0, spec, relic, None)


class TestTheLoaderRefuses:
    def _card(self, target: dict):
        return CardModel.model_validate(
            {
                "id": "t_bad_soc",
                "name": "Test Bad Spell or Creature",
                "oracle_text": "Return target spell or creature to its owner's hand.",
                "mana_cost": "{U}",
                "types": ["Instant"],
                "targets": [{"id": "t1", "count": 1, **target}],
                "spell_effects": [{"op": "return_spell_to_hand", "target": "t1"}],
            }
        )

    def test_on_any_other_kind(self):
        """A second selector on a one-pool kind would be read nowhere."""
        with pytest.raises(DslError, match="permanent half of a 'spell_or_permanent'"):
            compile_card(
                self._card({"kind": "spell", "permanent_selector": {"types": ["Creature"]}}),
                source="test",
            )

    def test_a_zone_off_the_battlefield(self):
        with pytest.raises(DslError, match="is on the battlefield"):
            compile_card(
                self._card(
                    {"kind": "spell_or_permanent", "permanent_selector": {"zone": "graveyard"}}
                ),
                source="test",
            )

    def test_a_sibling_reference(self):
        with pytest.raises(DslError, match="sibling target"):
            compile_card(
                self._card(
                    {
                        "kind": "spell_or_permanent",
                        "permanent_selector": {"controller": {"target": "t0"}},
                    }
                ),
                source="test",
            )

    def test_the_shipped_shape_loads(self):
        compile_card(
            self._card(
                {"kind": "spell_or_permanent", "permanent_selector": {"types": ["Creature"]}}
            ),
            source="test",
        )
