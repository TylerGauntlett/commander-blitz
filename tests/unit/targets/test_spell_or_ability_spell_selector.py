""""Counter target **instant spell, sorcery spell**, activated ability, or
triggered ability."

Sister of Silence. One instance of the word "target", so one `spell_or_ability`
spec -- but the printed type words narrow only its spell half: a creature spell
is no target, every activated or triggered ability is. `spell_selector` holds
those clauses, merged over `selector` for spells alone
(`TargetSpec.spell_half`), while `selector`'s `controller` and `that_targets`
still narrow both halves.

The rules this rests on:

* 115.1 / 601.2c -- the printed words decide what may be chosen; a plain
  `spell_or_ability` (Disallow) is a wider card that counters creature,
  artifact, enchantment and planeswalker spells too.
* 113.7a -- an ability on the stack has no types, so a type clause asked of it
  would be read off its source's face instead, making "target activated
  ability" mean "ability of an instant". The clauses never reach
  `_ability_matches`.
* 608.2b -- the target is re-checked on resolution by the same half it was
  offered through, so `candidates` and `still_legal` agree.

Witness: Sister of Silence (`data/authoring/gaps/sister_of_silence.json`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.stack import push_activated_ability, push_spell
from commanderblitz.engine.state import new_object
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.targeting import candidates, still_legal
from tests.conftest import (
    action_for_card,
    only_oid,
    pass_until,
    settle_to_priority,
)

SISTER = "t_sister_of_silence"
SNAP = "t_silence_snap"
THEIRS = "t_silence_snap_theirs"
GAINER = "t_gainer"  # {T}: you gain 2 life
INSTANT = "t_plain_instant"
SORCERY = "t_quiet_sorcery"
BEAR = "t_bear"


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 2 + [GAINER])
        .battlefield(1, ["plains"] * 2 + [GAINER])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [SNAP])
        .build(advance=False)
    )


def spell(game, def_id: str, seat: int = 1):
    obj = new_object(game.state, def_id, owner=seat, zone=Zone.HAND)
    game.state.players[seat].hand.append(obj.oid)
    push_spell(game.state, obj.oid, seat)
    return game.state.stack[-1]


def ability(game, seat: int = 1):
    return push_activated_ability(game.state, only_oid(game, GAINER, seat), 0, seat)


def spec(game, def_id=SNAP):
    card = game.state.registry.get(def_id)
    return card.targets[0] if card.targets else card.abilities[0].targets[0]


def offered(game, def_id=SNAP) -> set[int]:
    return {ref.id for ref in candidates(game.state, 0, spec(game, def_id), None)}


class TestTheSpellHalfIsNarrowed:
    def test_instants_and_sorceries_are_offered(self, builder):
        game = board(builder)
        instant, sorcery = spell(game, INSTANT), spell(game, SORCERY)
        assert offered(game) == {instant.sid, sorcery.sid}

    def test_a_creature_spell_is_not(self, builder):
        game = board(builder)
        bear = spell(game, BEAR)
        assert bear.sid not in offered(game)
        assert not still_legal(game.state, 0, spec(game), TargetRef.stack(bear.sid), None)

    def test_disallow_would_have_offered_it(self, builder):
        """The near miss: a plain `spell_or_ability` is the wider card."""
        game = board(builder)
        bear = spell(game, BEAR)
        assert bear.sid in offered(game, "t_disallow")


class TestTheAbilityHalfIsNot:
    def test_every_ability_is_still_offered(self, builder):
        game = board(builder)
        mine, theirs = ability(game, 0), ability(game, 1)
        spell(game, BEAR)
        assert offered(game) == {mine.sid, theirs.sid}

    def test_still_legal_agrees(self, builder):
        game = board(builder)
        item = ability(game)
        assert still_legal(game.state, 0, spec(game), TargetRef.stack(item.sid), None)

    def test_the_trigger_reads_the_same(self, builder):
        """Sister of Silence's own target: the shape on an ETB trigger."""
        game = board(builder)
        item, bear, instant = ability(game), spell(game, BEAR), spell(game, INSTANT)
        assert offered(game, SISTER) == {item.sid, instant.sid}
        assert bear.sid not in offered(game, SISTER)


class TestTheSharedClauseNarrowsBoth:
    def test_controller_still_reads_on_each_half(self, builder):
        game = board(builder)
        my_ability, their_ability = ability(game, 0), ability(game, 1)
        my_instant, their_instant = spell(game, INSTANT, 0), spell(game, INSTANT, 1)
        spell(game, BEAR, 1)
        assert offered(game, THEIRS) == {their_ability.sid, their_instant.sid}
        assert {my_ability.sid, my_instant.sid} <= offered(game)


class TestItCounters:
    def test_an_opponents_instant(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 2)
            .battlefield(1, ["plains"] * 2)
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .hand(0, [SNAP])
            .hand(1, [INSTANT])
            .build(advance=False)
        )
        game._advance()

        def can_cast(card_id):
            return lambda g: any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == card_id
                for a in g.legal_actions()
            )

        pass_until(game, can_cast(INSTANT))
        bait = action_for_card(game, ActionKind.CAST, INSTANT)
        game.apply(bait)
        pass_until(game, can_cast(SNAP))
        life = game.state.players[1].life
        game.apply(action_for_card(game, ActionKind.CAST, SNAP))
        settle_to_priority(game)
        assert game.state.objects[bait.source].zone is Zone.GRAVEYARD
        assert game.state.players[1].life == life


class TestTheLoader:
    def _card(self, target) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_silence_probe",
                "name": "Silence Probe",
                "oracle_text": "Counter target instant spell or ability.",
                "mana_cost": "{U}",
                "types": ["Instant"],
                "targets": [target],
                "spell_effects": [{"op": "counter", "target": "t1"}],
            }
        )

    def _target(self, **extra):
        return {"id": "t1", "kind": "spell_or_ability", **extra}

    def test_it_loads(self):
        compile_card(self._card(self._target(spell_selector={"types": ["Instant"]})))

    def test_a_face_clause_in_selector_points_at_spell_selector(self):
        with pytest.raises(DslError, match="spell_selector"):
            compile_card(self._card(self._target(selector={"types": ["Instant"]})))

    @pytest.mark.parametrize("kind", ["spell", "ability_on_stack", "spell_or_permanent"])
    def test_refused_on_every_other_kind(self, kind):
        with pytest.raises(DslError, match="spell_selector"):
            compile_card(
                self._card({"id": "t1", "kind": kind, "spell_selector": {"types": ["Instant"]}})
            )

    @pytest.mark.parametrize(
        "clause", [{"controller": "opponent"}, {"that_targets": {"player": "you"}}]
    )
    def test_a_shared_clause_belongs_in_selector(self, clause):
        with pytest.raises(DslError, match="both halves"):
            compile_card(self._card(self._target(spell_selector=clause)))

    def test_a_zone_is_refused(self):
        with pytest.raises(DslError, match="zone"):
            compile_card(
                self._card(self._target(spell_selector={"types": ["Instant"], "zone": "hand"}))
            )

    def test_an_empty_one_is_refused(self):
        with pytest.raises(DslError, match="narrows nothing"):
            compile_card(self._card(self._target(spell_selector={})))

    def test_a_malformed_clause_is_refused(self):
        with pytest.raises(DslError):
            compile_card(self._card(self._target(spell_selector={"tpyes": ["Instant"]})))
