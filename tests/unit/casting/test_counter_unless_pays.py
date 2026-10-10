"""``controller_of_target`` — "unless **its controller** pays {3}".

Frontline Medic is the witness, and it is now shipped: "Sacrifice this creature:
Counter target spell with {X} in its mana cost unless its controller pays {3}."

**The rules argument.** "Unless its controller pays" names a player by way of an
object, and rule 109.5 is explicit that "its controller" on a spell means the
controller of *that spell* — not the controller of the ability making the
demand. In a duel the two are usually opponents and the difference is invisible;
at a pod it is the whole clause, because there are two wrong seats to pick and
only one right one. The payment itself is 118.3: the seat asked either pays or
does not, and the `else` branch is what "unless" means.

**The shape already shipped; the *payer* did not.** `may` + `pay` + `else` is
exactly "unless", and Rhystic Study is the working card — but it can only bill a
player some **trigger binding** already names. Rhystic Study's payer arrives as
`{"controller_of": "subject"}` off a `spell_cast` event, and ward's the same way
off `becomes_target`. `select_players`' `controller_of` reads `ctx.bindings` and
nothing else, and an activated ability's `StackItem` carries its targets and its
bindings as separate things: it binds nothing for what it was activated at. So a
targeted counterspell had no way to say who was being billed.

**What was silently wrong, and why this is a load error now.**
`{"player": {"target": "t1"}}` is the obvious thing to write and it plays as the
card's own opposite. `ctx.target_players` keeps only refs of kind `"player"`,
and a spell's ref is kind `"stack"` — so it returns `[]`, and `op_may` reads an
empty list as "nobody, so me" (`chooser = ctx.controller`). The Medic would have
asked *its own controller* to pay {3} to counter the spell they had just chosen
to counter. Nothing raises, nothing logs, and the card is legal-looking and
inverted. `loader._validate_player_spec` refuses the combination by name
instead: a `player` spec may say `target` only of a target that can *be* a
player, and `controller_of_target` only of one that has a controller.

That check found a second one on the way in. Hellrider's "deals 1 damage to the
player or planeswalker it's attacking" was written `{"player": {"target":
"defender"}}`, and `defender` is a trigger *binding*, not a declared target — so
`ctx.targets` had no such key, `select_players` returned `[]`, and the shipped
card dealt no damage at all. `TestTheLoaderRefusesEveryWayOfMissing` pins both.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import select_players
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import TargetRef
from tests.conftest import (
    _default_answer,
    action_for_card,
    find_action,
    only_oid,
    pass_until,
)

#: The shipped card. Tested as shipped rather than through a `t_` stand-in:
#: the whole claim is about which seat a printed line bills, and a fixture
#: written by the same hand as the engine change could agree with it by
#: construction.
MEDIC = "frontline_medic"

#: `{X}{R}`, "deals X damage to any target" — a legal target for the Medic.
FIREBALL = "t_fireball"
#: `{R}`, fixed cost. Not a spell with {X} in its mana cost, so not a target.
BOLT = "t_bolt"
BEAR = "t_bear"


def position(builder, *, players: int = 2, caster: int = 1, mana: int = 6):
    """P0 has the Medic out; ``caster`` puts a Fireball on the stack.

    Returns ``(game, medic_oid, bear_oid)`` with **P0 holding priority** and the
    Fireball still on the stack — the only moment the Medic's ability can be
    activated at it.

    ``mana`` is how many untapped Mountains the caster keeps *after* paying for
    the Fireball, which is the whole of the difference between "declines" and
    "cannot pay": `op_may` does not offer a cost the player cannot afford.
    """
    build = builder(players=players)
    build.battlefield(0, ["plains"] * 3 + [MEDIC])
    build.battlefield(caster, ["mountain"] * (mana + 2) + [BEAR])
    build.hand(caster, [FIREBALL])
    build.active(caster)
    game = build.build()

    # At the caster's **own** Bear, deliberately. The Medic is a creature and
    # therefore a legal target too, and a Fireball pointed at it would be
    # countered by 608.2b when the Medic is sacrificed for its own ability --
    # which would make every "paying lets the spell through" assertion below
    # pass for the wrong reason.
    bear = only_oid(game, BEAR, caster)
    for action in game.legal_actions():
        if action.kind is not ActionKind.CAST or action.source is None:
            continue
        obj = game.state.objects.get(action.source)
        if obj is not None and obj.def_id == FIREBALL and TargetRef.obj(bear) in action.targets:
            game.apply(action)
            break
    else:
        raise AssertionError(f"no cast of {FIREBALL} at the Bear")

    pending = game.pending()
    if pending is not None and pending.kind is DecisionKind.CHOOSE_X:
        # X = 1, not the maximum: the caster has to keep mana back, or "declines
        # to pay" and "cannot pay" become the same test.
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == 1
            )
        )
    pass_until(game, lambda g: g.state.priority_player == 0 and bool(g.state.stack))
    return game, only_oid(game, MEDIC, 0), bear


def activate_at_the_spell(game) -> None:
    """Sacrifice the Medic, targeting the spell on top of the stack."""
    sid = game.state.stack[-1].sid
    for action in game.legal_actions():
        if action.kind is ActionKind.ACTIVATE and TargetRef.stack(sid) in action.targets:
            game.apply(action)
            return
    raise AssertionError(
        f"no activation targeting stack item {sid}; "
        f"legal: {[(a.kind.value, a.targets) for a in game.legal_actions()]}"
    )


def the_bill(game):
    """The pending payment prompt, or ``None`` if nobody was asked for anything."""
    decision = game.pending()
    if decision is None or decision.kind is not DecisionKind.MAY:
        return None
    return decision


def settle(game) -> None:
    """Just far enough for the stack to empty — not into another turn."""
    for _ in range(40):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def fireball_zone(game, caster: int = 1) -> Zone:
    return next(
        o.zone for o in game.state.objects.values() if o.def_id == FIREBALL
    )


class TestTheSpellsControllerIsTheOneAsked:
    """The claim, on a real stack: the bill goes to the seat that cast the
    spell, and never to the Medic's own controller."""

    def test_the_question_is_put_to_the_casting_player(self, builder):
        game, _, _ = position(builder)
        activate_at_the_spell(game)
        bill = the_bill(game)
        assert bill is not None, "nobody was asked to pay"
        assert bill.player == 1, "the Fireball's controller pays, not the Medic's"

    def test_and_specifically_not_the_medics_controller(self, builder):
        """The near miss stated as its own claim. `{"target": "t1"}` resolved to
        nobody and `op_may` fell back to `ctx.controller`, which is this."""
        game, _, _ = position(builder)
        activate_at_the_spell(game)
        assert the_bill(game).player != 0

    def test_paying_counters_nothing(self, builder):
        game, _, bear = position(builder)
        activate_at_the_spell(game)
        game.apply(find_action(game, ActionKind.YES))
        settle(game)
        assert game.state.objects[bear].damage == 1, "X was 1 and the spell resolved"
        assert not any(
            e.type == EventType.SPELL_COUNTERED for e in game.state.events
        ), "paying is what buys the absence of the counter"

    def test_declining_counters_the_spell(self, builder):
        game, _, bear = position(builder)
        activate_at_the_spell(game)
        game.apply(find_action(game, ActionKind.NO))
        settle(game)
        assert game.state.objects[bear].damage == 0, "countered, so it dealt nothing"
        assert fireball_zone(game) is Zone.GRAVEYARD

    def test_the_payment_actually_leaves_the_payers_side(self, builder):
        """"Pays {3}" is a real cost paid by the billed seat — not a flag. Three
        of the caster's lands tap, and the Medic's controller pays nothing."""
        game, _, _ = position(builder)

        def untapped(pid: int, land: str) -> int:
            return sum(
                1
                for o in game.state.battlefield_objects(pid)
                if o.def_id == land and not o.tapped
            )

        theirs, mine = untapped(1, "mountain"), untapped(0, "plains")
        activate_at_the_spell(game)
        game.apply(find_action(game, ActionKind.YES))
        assert untapped(1, "mountain") == theirs - 3
        assert untapped(0, "plains") == mine, "the Medic's controller was never charged"

    def test_a_controller_who_cannot_pay_is_not_asked_at_all(self, builder):
        """601.2 in spirit, and `op_may`'s existing contract: a cost nobody can
        afford is not offered. The `else` runs and the spell is countered."""
        game, _, bear = position(builder, mana=0)
        activate_at_the_spell(game)
        assert the_bill(game) is None, "there was no {3} to offer"
        settle(game)
        assert fireball_zone(game) is Zone.GRAVEYARD
        assert game.state.objects[bear].damage == 0


class TestThePodIsWhereTheSeatsDiffer:
    """A duel hides this: with two players, "the spell's controller" and "an
    opponent" are the same seat, so `player: "opponent"` would pass every test
    above. Three players is where the approximation shows."""

    def test_the_third_seat_is_not_billed(self, builder):
        game, _, _ = position(builder, players=3, caster=1)
        activate_at_the_spell(game)
        assert the_bill(game).player == 1

    def test_the_other_opponent_casting_moves_the_bill(self, builder):
        """The same board, the same Medic, a different caster — and the bill
        follows the spell. `"opponent"` cannot say this: `select_players` returns
        both opponents and `op_may` bills whichever is first in seat order."""
        game, _, _ = position(builder, players=3, caster=2)
        activate_at_the_spell(game)
        assert the_bill(game).player == 2


class TestTheKeyReadsRefsAndNotBindings:
    """`select_players` in isolation, on the two ref kinds that have a
    controller and the one that does not."""

    def test_a_stack_ref_answers_with_the_spells_controller(self, builder):
        game, _, _ = position(builder)
        sid = game.state.stack[-1].sid
        ctx = EffectContext(
            state=game.state, controller=0, targets={"t1": (TargetRef.stack(sid),)}
        )
        assert select_players(ctx, {"controller_of_target": "t1"}) == [1]

    def test_an_object_ref_answers_with_the_permanents_controller(self, builder):
        """"Unless that permanent's controller pays" is the same clause about a
        different object, so the key is total over every ref kind that has a
        controller rather than being spelled for spells alone."""
        game, medic, bear = position(builder)
        ctx = EffectContext(
            state=game.state,
            controller=0,
            targets={"t1": (TargetRef.obj(bear),), "t2": (TargetRef.obj(medic),)},
        )
        assert select_players(ctx, {"controller_of_target": "t1"}) == [1]
        assert select_players(ctx, {"controller_of_target": "t2"}) == [0]

    def test_two_targets_one_seat_is_billed_once(self, builder):
        """"Counter each of them unless their controllers pay" is one bill per
        seat. A duplicated player id would charge the same seat twice."""
        game, _, bear = position(builder)
        sid = game.state.stack[-1].sid
        ctx = EffectContext(
            state=game.state,
            controller=0,
            targets={"t1": (TargetRef.stack(sid), TargetRef.obj(bear))},
        )
        assert select_players(ctx, {"controller_of_target": "t1"}) == [1]

    def test_a_target_that_is_gone_answers_with_nobody(self, builder):
        """The wearing-off. A stack id that no longer names anything must not
        invent a payer — and `op_may`'s fallback is why this matters, which is
        the next class."""
        game, _, _ = position(builder)
        ctx = EffectContext(
            state=game.state, controller=0, targets={"t1": (TargetRef.stack(9999),)}
        )
        assert select_players(ctx, {"controller_of_target": "t1"}) == []

    def test_it_does_not_read_bindings(self, builder):
        """The distinction from `controller_of`, which is the reason this key
        exists: a binding of the same name must not answer for a target."""
        game, _, _ = position(builder)
        ctx = EffectContext(
            state=game.state, controller=0, bindings={"t1": {"controller": 1}}
        )
        assert select_players(ctx, {"controller_of_target": "t1"}) == []
        assert select_players(ctx, {"controller_of": "t1"}) == [1]


class TestNobodyIsBilledWhenTheTargetIsGone:
    """The boundary that keeps the empty list from becoming the old bug again.

    `op_may` still reads "no players" as "the controller", so an empty
    `controller_of_target` would bill the Medic — the exact inversion this
    capability exists to remove. It cannot happen, and the reason is 608.2b
    rather than anything in `op_may`: the ability's only target is the spell, so
    a spell that has left the stack takes the ability with it.
    """

    def test_the_ability_fizzles_rather_than_asking_the_wrong_seat(self, builder):
        game, _, bear = position(builder)
        activate_at_the_spell(game)
        game.apply(find_action(game, ActionKind.NO))
        settle(game)
        # The Fireball is countered and gone. Activating again is impossible --
        # the Medic is in the graveyard -- so the fizzle is asserted from the
        # other side: no second prompt was ever put to anybody.
        assert fireball_zone(game) is Zone.GRAVEYARD
        assert game.state.objects[bear].damage == 0
        assert the_bill(game) is None


class TestTheTargetFilterIsStillTheMedicsOwn:
    """The Medic counters spells **with {X} in their mana cost**, and the payer
    clause must not have widened that."""

    def test_a_fixed_cost_spell_is_not_a_target(self, builder):
        build = builder(players=2)
        build.battlefield(0, ["plains"] * 3 + [MEDIC])
        build.battlefield(1, ["mountain"] * 6 + [BEAR])
        build.hand(1, [BOLT])
        build.active(1)
        game = build.build()
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        pass_until(game, lambda g: g.state.priority_player == 0 and bool(g.state.stack))
        assert not [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE], (
            "a Bolt has no {X}, so the Medic has nothing to point at"
        )


class TestTheLoaderRefusesEveryWayOfMissing:
    """Each of these loaded clean before, and each played a different card than
    the one printed."""

    def card(self, player_spec, *, kind: str = "spell"):
        return {
            "id": "t_probe",
            "name": "Probe",
            "mana_cost": "{U}",
            "types": ["Instant"],
            "targets": [{"id": "t1", "kind": kind, "selector": {}, "count": 1}],
            "spell_effects": [
                {
                    "op": "may",
                    "player": player_spec,
                    "pay": {"mana": "{3}"},
                    "else": [{"op": "draw", "amount": {"const": 1}}],
                }
            ],
        }

    def compile(self, player_spec, *, kind: str = "spell"):
        compile_card(
            CardModel.model_validate(self.card(player_spec, kind=kind)), source="probe"
        )

    def test_a_spell_target_used_as_a_player_is_refused(self):
        """The silent misfire itself: it resolved to nobody and `op_may` billed
        the counterspell's own controller."""
        with pytest.raises(DslError, match="never a player"):
            self.compile({"target": "t1"})

    def test_and_the_refusal_names_the_key_that_works(self):
        """A load error that does not say what to write instead is a load error
        somebody routes around."""
        with pytest.raises(DslError, match="controller_of_target"):
            self.compile({"target": "t1"})

    def test_a_player_target_has_no_controller(self):
        """The mirror, and not a pedantry: `{"controller_of_target": "t1"}` on
        "target player" would resolve to nobody every time and land in the same
        `chooser = ctx.controller` fallback from the other direction."""
        with pytest.raises(DslError, match="no controller"):
            self.compile({"controller_of_target": "t1"}, kind="player")

    def test_an_undeclared_target_is_refused(self):
        """Hellrider's bug: `defender` is a trigger binding, and naming it here
        left `ctx.targets` without the key, so the card did nothing at all."""
        with pytest.raises(DslError, match="does not declare"):
            self.compile({"controller_of_target": "defender"})

    def test_a_misspelled_name_is_refused(self):
        with pytest.raises(DslError, match="unknown player spec"):
            self.compile("each_oponent")

    def test_the_right_spelling_loads(self):
        self.compile({"controller_of_target": "t1"})

    def test_an_any_target_may_still_be_named_as_a_player(self):
        """The regression guard on the check itself. "Any target" is creatures,
        planeswalkers *and* players (115.4), so `{"target": "t1"}` against one is
        the ordinary spelling every damage spell uses and must keep loading."""
        self.compile({"target": "t1"}, kind="any")


class TestTheShippedCardSaysWhatItPrints:
    def test_the_medic_bills_through_the_new_key(self, registry):
        """Pinned as data as well as behaviour: the whole point of the run is
        that this card's second line reads the *target's* controller."""
        card = registry.get(MEDIC)
        ability = next(a for a in card.abilities if a.targets)
        assert ability.targets[0].kind == "spell"
        assert ability.targets[0].selector == {"x_in_mana_cost": True}
        assert ability.effects[0]["player"] == {"controller_of_target": "t1"}
