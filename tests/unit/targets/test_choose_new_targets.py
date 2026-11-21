"""Choosing new targets for a spell or ability already on the stack (115.7).

    Wild Ricochet -- "You may choose new targets for target instant or sorcery
    spell. Then copy that spell. You may choose new targets for the copy."

`copy_spell`'s ``new_targets`` re-aims a *copy* and leaves the original where it
was pointed, so the first sentence of Wild Ricochet was unsayable: written as a
copy alone, the card lets an opponent's removal spell resolve at its original
target and looks entirely normal doing it. `choose_new_targets` changes the
original's targets where it sits on the stack.

The rules argument is three clauses of 115.7:

* 115.7d ("choose new targets", the default): any number of targets may be
  left as they are, **even one that has become illegal**, and every new target
  must be legal. `TestAnIllegalTargetMayBeKept` is the half a "pick any legal
  tuple" menu gets wrong.
* Legal for *whom*: the retargeted object's controller, whose "you" its
  selectors mean. `TestLegalityIsTheObjects` is an opponent's "target creature
  an opponent controls" spell, which a redirect cannot point at its caster's
  own creature.
* 115.7a ("change the target", ``must_change``): every target moves to another
  legal one or none does -- no "keep" on the menu.

And the number of targets never changes. Boltbender's "any number of other
spells and/or abilities" is ``all_on_stack``; Deflecting Swat's "spell or
ability" is a `spell_or_ability` target on the same op.

Witness: Wild Ricochet (`wild_ricochet`, the card this capability unblocks).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.stack import push_activated_ability, push_spell
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, oids_of, only_oid, settle

ZAP = "t_zap"  # {R}: 3 damage to target creature
TWIN = "t_twin_zap"  # {R}: 1 damage to each of two target creatures
THEIR_ZAP = "t_their_zap"  # {R}: 3 damage to target creature an opponent controls
RICOCHET = "t_ricochet"
BEAR = "grizzly_bears"
WARDED = "t_warded"  # a second creature with a name of its own
GOBLIN = "t_goblin"
PINGER = "t_camera_pinger"  # {T}: target player loses 1 life


def board(builder, mine=(BEAR,), theirs=(GOBLIN,), hand0=(), hand1=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine) + ["mountain"] * 4)
        .battlefield(1, list(theirs) + ["mountain"] * 2)
        .hand(0, list(hand0))
        .hand(1, list(hand1))
        .build()
    )


def in_hand(game, card_id: str, pid: int) -> int:
    return next(
        oid for oid in game.state.players[pid].hand if game.state.objects[oid].def_id == card_id
    )


def cast(game, card_id: str, pid: int, *targets: int):
    """Put a spell on the stack aimed at exactly these objects."""
    return push_spell(
        game.state, in_hand(game, card_id, pid), pid, [TargetRef.obj(t) for t in targets]
    )


def retarget(game, item, pick=lambda decision: 0, spec=None, controller: int = 0):
    """Run `choose_new_targets` on one stack item; return every decision it asked."""
    ctx = EffectContext(
        state=game.state,
        controller=controller,
        source_oid=None,
        targets={"t1": (TargetRef.stack(item.sid),)},
    )
    gen = OPS["choose_new_targets"](ctx, spec or {"target": "t1"})
    asked, sent = [], None
    while True:
        try:
            decision = gen.send(sent)
        except StopIteration:
            return asked
        asked.append(decision)
        sent = [pick(decision)]


def labelled(text: str):
    """Pick the option whose label is exactly ``text``."""

    def pick(decision):
        labels = [o.label for o in decision.options]
        assert text in labels, labels
        return labels.index(text)

    return pick


def labels(decision) -> list[str]:
    return [o.label for o in decision.options]


class TestTheOriginalMoves:
    def test_the_spell_resolves_at_its_new_target(self, builder):
        game = board(builder, hand0=[ZAP])
        bear, goblin = only_oid(game, BEAR, 0), only_oid(game, GOBLIN, 1)
        item = cast(game, ZAP, 0, bear)

        retarget(game, item, labelled("Test Goblin"))
        settle(game)

        assert game.state.objects[goblin].zone is Zone.GRAVEYARD
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD, (
            "the original was moved, so its first target is untouched"
        )

    def test_keep_is_offered_first_and_changes_nothing(self, builder):
        game = board(builder, hand0=[ZAP])
        bear = only_oid(game, BEAR, 0)
        item = cast(game, ZAP, 0, bear)

        (decision,) = retarget(game, item)

        assert labels(decision)[0] == "Keep: Grizzly Bears"
        assert item.targets == (TargetRef.obj(bear),)

    def test_nothing_is_asked_when_there_is_nowhere_else(self, builder):
        game = board(builder, theirs=(), hand0=[ZAP])
        bear = only_oid(game, BEAR, 0)
        item = cast(game, ZAP, 0, bear)

        assert retarget(game, item) == []
        assert item.targets == (TargetRef.obj(bear),)

    def test_the_number_of_targets_is_kept(self, builder):
        game = board(builder, mine=(BEAR, WARDED), hand0=[TWIN])
        bear, warded = only_oid(game, BEAR, 0), only_oid(game, WARDED, 0)
        item = cast(game, TWIN, 0, bear, warded)

        (decision,) = retarget(game, item)

        assert all(label.count(",") == 1 for label in labels(decision)), labels(decision)


class TestLegalityIsTheObjects:
    def test_an_opponents_spell_keeps_its_own_you(self, builder):
        """Their "target creature an opponent controls" is aimed at my bear. I
        may move it onto my other creature, never onto their own goblin: the
        selector's "opponent" is the spell's controller's."""
        game = board(builder, mine=(BEAR, WARDED), hand1=[THEIR_ZAP])
        item = cast(game, THEIR_ZAP, 1, only_oid(game, BEAR, 0))

        (decision,) = retarget(game, item, controller=0)

        assert labels(decision) == ["Keep: Grizzly Bears", "Test Warded"]

    def test_the_chooser_is_the_resolving_player(self, builder):
        game = board(builder, mine=(BEAR, WARDED), hand1=[THEIR_ZAP])
        item = cast(game, THEIR_ZAP, 1, only_oid(game, BEAR, 0))

        (decision,) = retarget(game, item, controller=0)

        assert decision.player == 0


class TestAnIllegalTargetMayBeKept:
    """115.7d: "the player may leave any number of the targets unchanged, even
    if those targets would be illegal"."""

    def test_keep_survives_its_target_leaving(self, builder):
        game = board(builder, hand0=[ZAP])
        bear = only_oid(game, BEAR, 0)
        item = cast(game, ZAP, 0, bear)
        move_object(game.state, bear, Zone.GRAVEYARD, to_player=0)

        (decision,) = retarget(game, item)

        assert labels(decision)[0].startswith("Keep:")
        assert "Test Goblin" in labels(decision)

    def test_one_target_kept_illegal_while_the_other_moves(self, builder):
        game = board(builder, mine=(BEAR, WARDED), hand0=[TWIN])
        bear, warded = only_oid(game, BEAR, 0), only_oid(game, WARDED, 0)
        goblin = only_oid(game, GOBLIN, 1)
        item = cast(game, TWIN, 0, goblin, bear)
        move_object(game.state, goblin, Zone.GRAVEYARD, to_player=1)

        retarget(game, item, labelled("Test Goblin, Test Warded"))

        assert item.targets == (TargetRef.obj(goblin), TargetRef.obj(warded))

    def test_a_legal_tuple_never_holds_the_illegal_target_twice(self, builder):
        game = board(builder, mine=(BEAR, WARDED), hand0=[TWIN])
        bear = only_oid(game, BEAR, 0)
        goblin = only_oid(game, GOBLIN, 1)
        item = cast(game, TWIN, 0, goblin, bear)
        move_object(game.state, goblin, Zone.GRAVEYARD, to_player=1)

        (decision,) = retarget(game, item)

        assert all(label.count("Test Goblin") <= 1 for label in labels(decision))


class TestMustChange:
    """115.7a: each target changes to another legal target, or none does."""

    SPEC = {"target": "t1", "must_change": True}

    def test_keep_is_not_offered(self, builder):
        game = board(builder, mine=(BEAR, WARDED), hand0=[ZAP])
        item = cast(game, ZAP, 0, only_oid(game, BEAR, 0))

        (decision,) = retarget(game, item, spec=self.SPEC)

        assert sorted(labels(decision)) == ["Test Goblin", "Test Warded"]

    def test_one_other_target_is_taken_without_asking(self, builder):
        game = board(builder, hand0=[ZAP])
        goblin = only_oid(game, GOBLIN, 1)
        item = cast(game, ZAP, 0, only_oid(game, BEAR, 0))

        assert retarget(game, item, spec=self.SPEC) == []
        assert item.targets == (TargetRef.obj(goblin),)

    def test_no_other_target_leaves_it_unchanged(self, builder):
        game = board(builder, theirs=(), hand0=[ZAP])
        bear = only_oid(game, BEAR, 0)
        item = cast(game, ZAP, 0, bear)

        assert retarget(game, item, spec=self.SPEC) == []
        assert item.targets == (TargetRef.obj(bear),)


class TestAnAbility:
    def test_an_activated_ability_is_retargeted(self, builder):
        """Deflecting Swat's "spell or ability": the ability's own specs."""
        game = board(builder, mine=(BEAR, PINGER))
        item = push_activated_ability(
            game.state, only_oid(game, PINGER, 0), 0, 0, [TargetRef.player(1)]
        )

        (decision,) = retarget(game, item, lambda d: 1)

        assert item.targets == (TargetRef.player(0),)
        assert decision.options[0].label.startswith("Keep:")


class TestAllOnStack:
    SPEC = {"all_on_stack": True}

    def test_each_targeted_object_is_asked_top_first(self, builder):
        game = board(builder, mine=(BEAR, WARDED), theirs=(GOBLIN, BEAR), hand0=[ZAP, THEIR_ZAP])
        first = cast(game, ZAP, 0, only_oid(game, BEAR, 0))
        second = cast(game, THEIR_ZAP, 0, only_oid(game, GOBLIN, 1))

        asked = retarget(game, first, spec=self.SPEC)

        assert [d.prompt for d in asked] == [
            "New targets for Test Their Zap?",
            "New targets for Test Zap?",
        ]
        assert first.targets and second.targets

    def test_an_object_without_targets_is_not_asked(self, builder):
        game = board(builder, mine=(BEAR, WARDED), hand0=[ZAP, "mountain"])
        cast(game, ZAP, 0, only_oid(game, BEAR, 0))
        push_spell(game.state, in_hand(game, "mountain", 0), 0)

        assert len(retarget(game, game.state.stack[0], spec=self.SPEC)) == 1


class TestBecameTarget:
    def became_target(self, game, oid):
        return [
            e
            for e in game.state.events
            if e.type is EventType.BECAME_TARGET and e.data.get("oid") == oid
        ]

    def test_the_new_target_becomes_a_target(self, builder):
        game = board(builder, hand0=[ZAP])
        goblin = only_oid(game, GOBLIN, 1)
        item = cast(game, ZAP, 0, only_oid(game, BEAR, 0))

        retarget(game, item, labelled("Test Goblin"))

        assert len(self.became_target(game, goblin)) == 1

    def test_keeping_announces_nothing(self, builder):
        game = board(builder, hand0=[ZAP])
        bear = only_oid(game, BEAR, 0)
        item = cast(game, ZAP, 0, bear)
        before = len(self.became_target(game, bear))

        retarget(game, item)

        assert len(self.became_target(game, bear)) == before


class TestWildRicochet:
    """The whole card, through `Game.apply`: retarget the original, then copy
    it -- the copy starts from the new target."""

    def play(self, builder, original_to: str, copy_to: str):
        game = board(builder, mine=(BEAR, WARDED), hand0=[ZAP, RICOCHET])
        bear = only_oid(game, BEAR, 0)
        zap = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == ZAP
            and a.targets
            and a.targets[0].id == bear
        )
        game.apply(zap)
        ricochet = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == RICOCHET
        )
        game.apply(ricochet)
        prompts = []
        for _ in range(300):
            decision = game.pending()
            if decision is None or (
                decision.kind is DecisionKind.PRIORITY and not game.state.stack
            ):
                break
            if decision.kind is DecisionKind.CHOOSE_MODE and "New targets" in (
                decision.prompt or ""
            ):
                prompts.append(decision.prompt)
                want = copy_to if "(copy)" in decision.prompt else original_to
                index = next(
                    i for i, o in enumerate(decision.options) if want in (o.label or "")
                )
                game.apply(
                    next(
                        a
                        for a in game.legal_actions()
                        if a.kind is ActionKind.CHOOSE and a.choice == index
                    )
                )
                continue
            game.apply(_default_answer(game, decision))
        return game, prompts

    def test_both_sentences_are_asked(self, builder):
        _, prompts = self.play(builder, "Test Goblin", "Test Goblin")
        assert prompts == ["New targets for Test Zap?", "New targets for Test Zap (copy)?"]

    def test_the_original_is_moved_off_my_creature(self, builder):
        game, _ = self.play(builder, "Test Goblin", "Test Warded")
        assert oids_of(game, BEAR, 0), "the original was redirected away from the bear"
        assert not oids_of(game, GOBLIN, 1), "and resolved at the goblin"
        assert not oids_of(game, WARDED, 0), "while the copy was pointed elsewhere"

    def test_declining_leaves_the_original_where_it_was(self, builder):
        game, _ = self.play(builder, "Keep:", "Test Goblin")
        assert not oids_of(game, BEAR, 0)
        assert not oids_of(game, GOBLIN, 1)


class TestTheLoaderRefuses:
    def _card(self, effect, targets=None):
        return CardModel.model_validate(
            {
                "id": "t_bad_retarget",
                "name": "Bad Retarget",
                "oracle_text": "Bad.",
                "mana_cost": "{R}",
                "types": ["Instant"],
                "colors": ["R"],
                "color_identity": ["R"],
                "targets": targets
                if targets is not None
                else [{"id": "t1", "kind": "spell", "count": 1, "selector": {}}],
                "spell_effects": [effect],
            }
        )

    def test_a_permanent_target(self):
        target = [
            {
                "id": "t1",
                "kind": "permanent",
                "count": 1,
                "selector": {"zone": "battlefield", "types": ["Creature"]},
            }
        ]
        with pytest.raises(DslError, match="choose_new_targets needs a target of kind"):
            compile_card(self._card({"op": "choose_new_targets", "target": "t1"}, target))

    def test_an_undeclared_target(self):
        with pytest.raises(DslError, match="does not declare"):
            compile_card(self._card({"op": "choose_new_targets", "target": "t2"}))

    def test_all_on_stack_beside_a_target(self):
        with pytest.raises(DslError, match="replaces 'target'"):
            compile_card(
                self._card({"op": "choose_new_targets", "target": "t1", "all_on_stack": True})
            )

    def test_objects(self):
        with pytest.raises(DslError, match="reads no 'objects'"):
            compile_card(
                self._card(
                    {"op": "choose_new_targets", "target": "t1", "objects": {"target": "t1"}}
                )
            )

    def test_must_change_on_another_op(self):
        with pytest.raises(DslError, match="must_change"):
            compile_card(self._card({"op": "counter", "target": "t1", "must_change": True}))

    def test_a_non_boolean_switch(self):
        with pytest.raises(DslError, match="boolean"):
            compile_card(
                self._card({"op": "choose_new_targets", "target": "t1", "must_change": "yes"})
            )
