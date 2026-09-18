""""Whenever you cast an instant or sorcery spell, **if it targets one or more
other permanents you control**, create a token that's a copy of one of those
permanents."

Orvar, the All-Form. A trigger that asks about **another spell's chosen targets**,
which nothing in the language could reach: `SPELL_CAST` carried the caster, the
spell and its card, and no target information at all, so even a new condition key
would have had nothing to read.

The whole capability is one payload key. `Game._cast` now puts the spell's
**object** targets on the event and `EVENT_BINDING_KEYS` carries them into the
trigger's bindings as `spell_targets`; from there the existing language does the
rest, which is why no new condition key and no new op were needed:

- the intervening-if is `{"exists": {"binding": "spell_targets", …}}`, the same
  binding-plus-filter shape Sphinx's Tutelage uses over `milled`;
- the effect points `copy_permanent` at that same pool, so the token copies a
  permanent *the spell actually chose*.

**Both halves are one key, and that is the point.** A condition without the
binding would let the card copy any permanent you control — a different and much
stronger card, which `TestTheUnconditionalSpellingIsStronger` keeps alive and
measures.

Two near misses, each wrong by construction:

- **`{"target": "t1"}`** resolves through `ctx.target_oids`, which is the
  *ability's own* declared targets. It can never name what somebody else's spell
  chose.
- **`becomes_target`** is a per-permanent trigger: written on Orvar it would see
  only spells aimed at Orvar himself, and there is no way to put a trigger on
  every permanent you control.

Only **object** targets go on the payload. A spell aimed at a player has targets
that are not permanents, and a list mixing seat numbers with oids would be read as
oids by every consumer — both are `int`, and `_bound_oids` cannot tell them apart.
`TestAPlayerTargetIsNotAPermanentTarget` is that claim.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Step

ORVAR = "t_orvar"
LOOSE = "t_orvar_unconditional"  # the stronger card, kept as a control
PUMP = "t_pump_other"  # targets a Bear -- never Orvar, so the auto-answer cannot drift
SHAPE = "t_pump_shapeshifter"  # targets a Shapeshifter, i.e. Orvar himself
PLAYER_SPELL = "t_pump_player"  # targets a player
UNTARGETED = "t_untargeted_gain"  # targets nothing

BEAR = "t_bear"
ISLAND = "island"


def position(builder, *, orvar: str = ORVAR, hand: list[str], board=(BEAR,)):
    """Orvar and one other creature out, with mana for anything in hand."""
    return (
        builder(players=2)
        .battlefield(0, [ISLAND] * 4 + [orvar, *board])
        .battlefield(1, [ISLAND])
        .hand(0, list(hand))
        .library(0, ["plains"] * 10)
        .library(1, ["plains"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )


def cast(game, card_id: str, limit: int = 120) -> None:
    from tests.conftest import _default_answer

    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            game._advance()
            decision = game.pending()
            if decision is None:
                return
        if decision.kind is DecisionKind.PRIORITY and decision.player == 0:
            action = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CAST
                    and game.state.objects[a.source].def_id == card_id
                ),
                None,
            )
            if action is not None:
                game.apply(action)
                for _ in range(limit):
                    if not game.state.stack and not game.state.pending_triggers:
                        return
                    d = game.pending()
                    if d is None:
                        return
                    game.apply(_default_answer(game, d))
                return
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"never cast {card_id}")


def tokens(game) -> int:
    return sum(
        1
        for oid in game.state.battlefield
        if game.state.objects[oid].is_token and game.state.objects[oid].controller == 0
    )


class TestTheBindingCarriesTheSpellsTargets:
    def test_a_spell_targeting_your_creature_makes_a_copy(self, builder):
        game = position(builder, hand=[PUMP])
        assert tokens(game) == 0
        cast(game, PUMP)
        assert tokens(game) == 1

    def test_the_token_copies_the_permanent_the_spell_chose(self, builder):
        """Not merely "a token appeared" -- the right one."""
        game = position(builder, hand=[PUMP])
        cast(game, PUMP)
        made = [
            game.state.objects[oid]
            for oid in game.state.battlefield
            if game.state.objects[oid].is_token
        ]
        assert [o.def_id for o in made] == [BEAR]


class TestItDoesNotFireWithoutATargetedPermanent:
    def test_an_untargeted_spell_does_nothing(self, builder):
        game = position(builder, hand=[UNTARGETED])
        cast(game, UNTARGETED)
        assert tokens(game) == 0, "the intervening-if has nothing to be true about"

    def test_a_spell_targeting_only_a_player_does_nothing(self, builder):
        game = position(builder, hand=[PLAYER_SPELL])
        cast(game, PLAYER_SPELL)
        assert tokens(game) == 0


class TestAPlayerTargetIsNotAPermanentTarget:
    """Only object targets reach the payload.

    A seat number and an oid are both `int`, so a mixed list would be read as
    oids by every consumer. This pins that a player-targeting spell contributes
    nothing rather than contributing a number that happens to match an object.
    """

    def test_the_binding_holds_no_player_ids(self, builder):
        from automtg.engine.events import EventType

        game = position(builder, hand=[PLAYER_SPELL])
        cast(game, PLAYER_SPELL)
        casts = [e for e in game.state.events if e.type is EventType.SPELL_CAST]
        assert casts, "the spell was cast"
        assert casts[-1].data.get("spell_targets") == []


class TestTheOtherClause:
    """"…one or more **other** permanents **you control**"."""

    def test_a_spell_targeting_orvar_himself_does_nothing(self, builder):
        """`exclude_self` is the printed "other"."""
        game = position(builder, hand=[SHAPE])
        cast(game, SHAPE)
        assert tokens(game) == 0, "a permanent is not another permanent"

    def test_a_spell_targeting_an_opponents_creature_does_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [ISLAND] * 4 + [ORVAR])
            .battlefield(1, [ISLAND, BEAR])
            .hand(0, [PUMP])
            .library(0, ["plains"] * 10)
            .library(1, ["plains"] * 10)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build(advance=False)
        )
        cast(game, PUMP)
        assert tokens(game) == 0, "you control is the other half of the clause"


class TestTheUnconditionalSpellingIsStronger:
    """Kept as a live card: the approximation the gap record refused to write.

    It fires on a spell that targets nothing and copies a permanent the spell
    never chose — strictly stronger than the printed card, and identical on the
    board until exactly this line of play.
    """

    def test_it_fires_on_an_untargeted_spell(self, builder):
        game = position(builder, orvar=LOOSE, hand=[UNTARGETED])
        cast(game, UNTARGETED)
        assert tokens(game) == 1, "the control: no intervening-if, so nothing stops it"

    def test_where_the_real_card_does_not(self, builder):
        game = position(builder, orvar=ORVAR, hand=[UNTARGETED])
        cast(game, UNTARGETED)
        assert tokens(game) == 0
