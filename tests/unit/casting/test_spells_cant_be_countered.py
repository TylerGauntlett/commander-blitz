""""Spells can't be countered." — a static about everybody's spells.

Lier, Disciple of the Drowned. The engine had `uncounterable`, a **card-level**
flag, and it is a different claim: one card saying it about *itself*. It could
never cover a spell its controller does not own, which is most of what Lier
does — the card is famously symmetrical, and shutting off the opponents'
counterspells is the half people play it for and the half that also stops their
own.

So `spells_cant_be_countered` is a static, consulted by the `counter` op beside
the printed flag. It carries no `affects`, because it names no permanent: an
optional `affects_spells` narrows *which* spells, and Lier prints no filter at
all.

`TestItProtectsEverybody` is the load-bearing pair. A version that quietly read
the static's controller would pass the first of them and fail the second, and
would be a strictly better card than the one printed.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import pass_until

LIER = "t_lier"  # "Spells can't be countered."
COUNTER = "t_counterspell"  # {U}{U}, counter target spell
BAIT = "t_demo_draw"  # {R} instant -- something to counter, and to flash back


def position(builder, *, lier_for: int | None, caster: int, bait_from: int):
    """``bait_from`` casts a spell, ``caster`` tries to counter it.

    ``lier_for`` is which seat has the static out, or None for the control.
    """
    board0 = ["island", "island", "island", "mountain"]
    board1 = ["island", "island", "island", "mountain"]
    if lier_for == 0:
        board0 = [LIER, *board0]
    elif lier_for == 1:
        board1 = [LIER, *board1]
    game = (
        builder(players=2)
        .battlefield(0, board0)
        .battlefield(1, board1)
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(bait_from, [BAIT])
        .hand(caster, [COUNTER])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def bait_then_counter(game, *, caster: int) -> Zone:
    """Cast the bait, counter it, and report where the bait ended up."""
    bait = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BAIT
    )
    bait_oid = bait.source
    game.apply(bait)

    pass_until(
        game,
        lambda g: any(
            a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == COUNTER
            for a in g.legal_actions()
        )
        or not g.state.stack,
    )
    counter = next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == COUNTER
        ),
        None,
    )
    assert counter is not None, "the counterspell is castable -- it is not the target that failed"
    game.apply(counter)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return game.state.objects[bait_oid].zone


class TestWithoutTheStatic:
    def test_the_counterspell_works(self, builder):
        """The control. Without it there is nothing to attribute the rest to."""
        game = position(builder, lier_for=None, caster=1, bait_from=0)
        assert bait_then_counter(game, caster=1) is Zone.GRAVEYARD


class TestItProtectsEverybody:
    def test_your_spell_survives_their_counterspell(self, builder):
        """The half the card is played for."""
        game = position(builder, lier_for=0, caster=1, bait_from=0)
        assert bait_then_counter(game, caster=1) is Zone.GRAVEYARD

    def test_and_so_does_theirs_against_yours(self, builder):
        """The symmetrical half, and the one a controller-aware version fails.

        Lier turns off your own counterspells too. A static that checked whose
        it was would be strictly better than the printed card.
        """
        game = position(builder, lier_for=0, caster=0, bait_from=1)
        assert bait_then_counter(game, caster=0) is Zone.GRAVEYARD

    def test_an_opponents_lier_protects_your_spell_too(self, builder):
        """It does not matter whose battlefield it sits on."""
        game = position(builder, lier_for=1, caster=1, bait_from=0)
        assert bait_then_counter(game, caster=1) is Zone.GRAVEYARD


class TestGrantedFlashback:
    """"Each instant and sorcery card in your graveyard has flashback."

    Lier's second line, and the interesting part is how little of it was
    missing. A spell cast out of a graveyard **already** exiles as it resolves:
    `graveyard_cast_exiles` defaults to True and escape is the only thing that
    turns it off, so the exile half of flashback had been there all along.

    What Lier could not say was that it needs no rate limit. The loader refuses
    a `cast_from_graveyard` static with no `max_per_turn`, and it is right to --
    a permission that neither meters nor exiles recasts one graveyard card every
    turn for ever. `grants_flashback` is the card stating that the exile *is*
    the limit: spent card by card, capped by the graveyard running out.

    So the flag adds no behaviour, and deliberately: a second mechanism for an
    exile the engine already performs would be two spellings of one question.
    """

    def flashback_a_spell(self, builder, lier: str):
        """Cast BAIT out of the graveyard under ``lier``; report where it ends."""
        game = (
            builder(players=2)
            .battlefield(0, [lier, "island", "island", "island", "mountain"])
            .battlefield(1, ["plains"])
            .graveyard(0, [BAIT])
            .library(0, ["forest"] * 20)
            .hand(1, ["t_plain_instant"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        bait = game.state.players[0].graveyard[0]

        action = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == bait),
            None,
        )
        assert action is not None, f"{lier} offers the graveyard cast"
        game.apply(action)
        pass_until(
            game,
            lambda g: not g.state.stack
            and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
        )
        return game.state.objects[bait].zone

    def test_an_uncapped_permission_is_castable_at_all(self, builder):
        """The half that needed building: no `max_per_turn`, and it still loads.

        Lier prints no per-turn cap, and before `grants_flashback` the loader
        refused the card outright.
        """
        assert self.flashback_a_spell(builder, LIER) is Zone.EXILE

    def test_a_metered_permission_exiles_the_same_way(self, builder):
        """The comparison that shows the flag adds no behaviour of its own.

        Same cast, same zone, different rate limit -- and the same exile, because
        the exile was never the missing part.
        """
        assert self.flashback_a_spell(builder, "t_lier_no_exile") is Zone.EXILE
