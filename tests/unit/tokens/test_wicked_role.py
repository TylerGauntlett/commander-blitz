"""Role tokens: "…then create a Wicked Role token attached to it." (303.7a, 704.5y)

    Not Dead After All — "Until end of turn, target creature you control gains
    'When this creature dies, return it to the battlefield tapped under its
    owner's control, then create a Wicked Role token attached to it.'"

A Wicked Role is a colorless Aura token, subtype Role: "Enchanted creature gets
+1/+1. When this Aura is put into a graveyard from the battlefield, each opponent
loses 1 life." The pool had no Aura token at all, and three rules come with it,
each of which a near miss gets wrong:

- **Created attached.** `create_token` then `attach` looks the same and is a
  different card exactly when the host is gone: the token arrives on nothing,
  704.5m puts it into the graveyard, and its own trigger drains every opponent
  for a Role that should never have existed. The Role rulings say it is simply
  not created, so `create_token` grew `attached_to`, resolved before anything is
  made.
- **One Role per player per permanent** (704.5y). A second Role from the same
  player puts the older one into the graveyard -- which is not destruction, so
  the replaced Wicked Role still drains on its way out.
- **Newest by attachment**, not arrival (613.7e): `attach` now stamps
  `attached_timestamp`, and the rule keeps the highest.

Witnesses in tests/data/role.cards.json: `t_role_maker` ("Create a Wicked Role
token attached to target creature") and `t_not_dead`, Not Dead After All's
printed shape.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import destroy, exile
from tests.conftest import only_oid, pass_until, settle

ROLE = "wicked_role"
BEAR = "t_bear"  # vanilla 2/2, {1}{G}
NOT_DEAD = "t_not_dead"
MAKER = "t_role_maker"


def board(builder, *, hand=(), theirs=()):
    """Player 0's main phase with a bear, and a castable bear in hand.

    The spare bear is what keeps player 0 holding a real decision, so the
    engine's auto-pass does not roll the game past the moment under test.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 3 + ["swamp"] * 2 + [BEAR])
        .battlefield(1, list(theirs))
        .hand(0, [*hand, BEAR])
        .library(0, ["swamp"] * 20)
        .library(1, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game, only_oid(game, BEAR, 0)


def make_role(game, host: int, controller: int = 0) -> None:
    """Resolve `t_role_maker`'s effect aimed at ``host``, as ``controller``."""
    card = game.state.registry.get(MAKER)
    ctx = EffectContext(
        state=game.state,
        controller=controller,
        targets={"t1": (TargetRef.obj(host),)},
    )
    gen = execute(ctx, card.spell_effects)
    for _ in gen:
        pass
    sba.run(game.state)
    settle(game)


def roles_on(game, host: int, controller: int | None = None) -> list[int]:
    return [
        oid
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == ROLE
        and game.state.objects[oid].attached_to == host
        and (controller is None or game.state.objects[oid].controller == controller)
    ]


def life(game) -> list[int]:
    return [p.life for p in game.state.players]


class TestTheToken:
    def test_it_is_a_colorless_aura_role_token(self, registry: CardRegistry):
        role = registry.get(ROLE)
        assert role.is_token and role.is_aura
        assert {"Aura", "Role"} <= set(role.subtypes)
        assert not role.colors

    def test_it_is_created_attached_and_pumps_its_creature(self, builder):
        game, bear = board(builder)
        make_role(game, bear)
        assert len(roles_on(game, bear)) == 1
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (3, 3)

    def test_going_to_the_graveyard_drains_each_opponent(self, builder):
        game, bear = board(builder)
        make_role(game, bear)
        destroy(game.state, roles_on(game, bear)[0])
        sba.run(game.state)
        settle(game)
        assert life(game) == [40, 39]

    def test_it_falls_off_with_its_creature_and_still_drains(self, builder):
        """704.5m puts the unattached Aura into the graveyard -- from the battlefield."""
        game, bear = board(builder)
        make_role(game, bear)
        destroy(game.state, bear)
        sba.run(game.state)
        settle(game)
        assert not [o for o in game.state.battlefield if game.state.objects[o].def_id == ROLE]
        assert life(game) == [40, 39]


class TestCreatedAttached:
    def test_no_host_on_the_battlefield_means_no_token(self, builder):
        """Created-then-attached would arrive on nothing, die, and drain."""
        game, bear = board(builder)
        exile(game.state, bear)
        make_role(game, bear)
        assert not [o for o in game.state.objects.values() if o.def_id == ROLE]
        assert life(game) == [40, 40]

    def test_the_token_is_yours_on_their_creature(self, builder):
        game, _ = board(builder, theirs=[BEAR])
        theirs = only_oid(game, BEAR, 1)
        make_role(game, theirs)
        (role,) = roles_on(game, theirs)
        assert game.state.objects[role].controller == 0
        assert chars(game.state, theirs).power == 3


class TestTheRoleRule:
    def test_a_second_role_replaces_the_first(self, builder):
        game, bear = board(builder)
        make_role(game, bear)
        (first,) = roles_on(game, bear)
        make_role(game, bear)
        (kept,) = roles_on(game, bear)
        assert kept != first
        assert chars(game.state, bear).power == 3, "one +1/+1, not two"

    def test_the_replaced_wicked_role_still_drains(self, builder):
        """Put into the graveyard, not destroyed or sacrificed -- its trigger fires."""
        game, bear = board(builder)
        make_role(game, bear)
        make_role(game, bear)
        assert life(game) == [40, 39]

    def test_roles_from_different_players_coexist(self, builder):
        game, bear = board(builder)
        make_role(game, bear, controller=0)
        make_role(game, bear, controller=1)
        assert len(roles_on(game, bear, 0)) == 1 and len(roles_on(game, bear, 1)) == 1
        assert chars(game.state, bear).power == 4

    def test_roles_on_different_creatures_coexist(self, builder):
        game, bear = board(builder, theirs=[BEAR])
        theirs = only_oid(game, BEAR, 1)
        make_role(game, bear)
        make_role(game, theirs)
        assert len(roles_on(game, bear)) == 1 and len(roles_on(game, theirs)) == 1

    def test_newest_is_by_attachment_not_by_arrival(self, builder):
        """613.7e: a Role moved onto the creature is newer than one already there."""
        game, bear = board(builder, theirs=[BEAR])
        theirs = only_oid(game, BEAR, 1)
        make_role(game, theirs)
        (moved,) = roles_on(game, theirs)
        make_role(game, bear)
        (stayed,) = roles_on(game, bear)
        attach(game.state, moved, bear)
        sba.run(game.state)
        settle(game)
        assert roles_on(game, bear) == [moved]
        assert stayed not in game.state.battlefield


class TestNotDeadAfterAll:
    def cast(self, game):
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and "Test Not Dead" in (a.label or "")
        )
        game.apply(action)
        settle(game)

    def test_the_creature_comes_back_tapped_wearing_the_role(self, builder):
        game, bear = board(builder, hand=[NOT_DEAD])
        self.cast(game)
        destroy(game.state, bear)
        sba.run(game.state)
        settle(game)
        obj = game.state.objects[bear]
        assert obj.zone is Zone.BATTLEFIELD and obj.tapped
        assert len(roles_on(game, bear)) == 1
        assert chars(game.state, bear).power == 3
        assert life(game) == [40, 40]

    def test_without_the_spell_it_stays_dead(self, builder):
        game, bear = board(builder)
        destroy(game.state, bear)
        sba.run(game.state)
        settle(game)
        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert not [o for o in game.state.objects.values() if o.def_id == ROLE]

    def test_the_grant_is_gone_next_turn(self, builder):
        game, bear = board(builder, hand=[NOT_DEAD])
        self.cast(game)
        start = game.state.turn
        pass_until(game, lambda g: g.state.turn == start + 1 and g.state.step is Step.PRECOMBAT_MAIN)
        destroy(game.state, bear)
        sba.run(game.state)
        settle(game)
        assert game.state.objects[bear].zone is Zone.GRAVEYARD


def maker(effect) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_x",
            "name": "X",
            "types": ["Sorcery"],
            "targets": [
                {"id": "t1", "kind": "permanent", "count": 1,
                 "selector": {"zone": "battlefield", "types": ["Creature"]}}
            ],
            "spell_effects": [effect],
        }
    )


class TestTheLoader:
    def test_attached_to_on_another_op_is_refused(self):
        with pytest.raises(DslError, match="only by create_token"):
            compile_card(
                maker({"op": "tap", "objects": {"target": "t1"}, "attached_to": {"target": "t1"}})
            )

    def test_attached_to_needs_an_aura_token(self, registry: CardRegistry):
        card = compile_card(
            maker({"op": "create_token", "token": "treasure_token", "attached_to": {"target": "t1"}})
        )
        cards = {c.id: c for c in registry}
        cards[card.id] = card
        from commanderblitz.cards.loader.linking import validate_token_references

        with pytest.raises(DslError, match="needs an Aura token"):
            validate_token_references(cards)

    def test_a_granted_ability_naming_an_unknown_token_is_refused(self, registry: CardRegistry):
        model = CardModel.model_validate(
            {
                "id": "t_y",
                "name": "Y",
                "types": ["Instant"],
                "targets": [{"id": "t1", "kind": "permanent", "count": 1,
                             "selector": {"zone": "battlefield", "types": ["Creature"]}}],
                "grantable_abilities": [
                    {"kind": "triggered", "text": "When this creature dies, make a thing.",
                     "trigger": {"event": "dies", "source": "self"},
                     "effects": [{"op": "create_token", "token": "no_such_token"}]}
                ],
                "spell_effects": [{"op": "grant_ability", "ability": 0, "objects": {"target": "t1"}}],
            }
        )
        cards = {c.id: c for c in registry}
        cards["t_y"] = compile_card(model)
        from commanderblitz.cards.loader.linking import validate_token_references

        with pytest.raises(DslError, match="no_such_token"):
            validate_token_references(cards)
