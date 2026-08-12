"""The gates that decide whether a machine-written card is allowed into the pool.

This is the test file for the thing that makes the whole card-authoring pipeline
safe, so it is worth being blunt about what it is defending against.

``compile_card`` checks that every op, selector, trigger and keyword *exists*. It
cannot check that the card does what the card says. A generator -- template or
model -- can emit a Divination whose effect is `gain_life`, and it will compile,
cast, resolve and sit in the graveyard without ever raising. On the board it just
quietly does the wrong thing.

So the case below that matters most is `test_a_card_that_does_the_wrong_thing`.
Everything else is scaffolding around it.
"""

from __future__ import annotations

import pytest

from automtg.cards.authoring import verify as V
from automtg.cards.registry import CardRegistry

DIVINATION = {
    "id": "auto_test_divination",
    "name": "Auto Test Divination",
    "oracle_text": "Draw two cards.",
    "mana_cost": "{2}{U}",
    "types": ["Sorcery"],
    "spell_effects": [{"op": "draw", "player": "you", "amount": {"const": 2}}],
}

BEAR = {
    "id": "auto_test_bear",
    "name": "Auto Test Bear",
    "oracle_text": "",
    "mana_cost": "{1}{G}",
    "types": ["Creature"],
    "subtypes": ["Bear"],
    "power": 2,
    "toughness": 2,
}


@pytest.fixture(scope="module")
def pool(real_registry: CardRegistry) -> CardRegistry:
    """The shipped pool, which is what an authored card will actually join."""
    return real_registry


class TestTheGateThatMatters:
    def test_a_card_that_does_the_wrong_thing_is_rejected(self, pool):
        """Compiles, casts, resolves -- and draws nothing.

        The failure this whole pipeline exists to prevent. Nothing before gate 5
        can see it: the ops are real, the selectors parse, the spell ends in the
        graveyard exactly as a sorcery should.
        """
        liar = {
            **DIVINATION,
            "id": "auto_test_liar",
            "spell_effects": [{"op": "gain_life", "player": "you", "amount": {"const": 2}}],
        }
        verdict = V.verify(liar, {"hand_size": {"0": 2}}, pool)
        assert verdict.failed_gate == "behaviour"
        assert "hand_size" in verdict.reason
        # It got all the way there, which is the point.
        assert "compile" in verdict.passed
        assert "playable" in verdict.passed

    def test_a_correct_card_passes_every_gate(self, pool):
        verdict = V.verify(DIVINATION, {"hand_size": {"0": 2}}, pool)
        assert verdict.ok, str(verdict)
        assert set(verdict.passed) == set(V.GATES)

    def test_an_expectation_is_mandatory(self, pool):
        # A card nobody asserted anything about has not been verified, however
        # cleanly it compiles.
        verdict = V.verify(DIVINATION, {}, pool)
        assert verdict.failed_gate == "behaviour"
        assert "not been verified" in verdict.reason

    def test_an_expectation_that_overstates_the_card_is_rejected(self, pool):
        verdict = V.verify(DIVINATION, {"hand_size": {"0": 5}}, pool)
        assert verdict.failed_gate == "behaviour"

    def test_an_unknown_expectation_key_is_rejected(self, pool):
        # Silently ignoring it would mean an author could "verify" a card with an
        # assertion that never ran.
        verdict = V.verify(DIVINATION, {"vibes": {"0": 1}}, pool)
        assert verdict.failed_gate == "behaviour"
        assert "vibes" in verdict.reason


class TestTheEarlierGates:
    def test_a_malformed_payload_fails_on_schema(self, pool):
        verdict = V.verify({"id": "auto_x", "name": "X"}, {"life": {"0": 40}}, pool)
        assert verdict.failed_gate == "schema"

    def test_an_unknown_op_fails_on_compile(self, pool):
        bad = {**DIVINATION, "spell_effects": [{"op": "draw_two", "player": "you"}]}
        verdict = V.verify(bad, {"hand_size": {"0": 2}}, pool)
        assert verdict.failed_gate == "compile"
        assert "draw_two" in verdict.reason

    def test_an_unknown_keyword_fails_on_compile(self, pool):
        bad = {**BEAR, "keywords": ["annihilator"]}
        verdict = V.verify(bad, {"battlefield_count": 1}, pool)
        assert verdict.failed_gate == "compile"

    def test_printed_text_nobody_implemented_fails_on_residual(self, pool):
        """A permanent whose rules text no ability claims.

        The card would load and be a 2/2 that silently ignores half its own
        printing -- exactly the inert-proxy problem this pipeline is replacing.
        """
        half_done = {
            **BEAR,
            "id": "auto_test_half",
            "oracle_text": "Whenever this creature attacks, draw a card.",
        }
        verdict = V.verify(half_done, {"battlefield_count": 100}, pool)
        assert verdict.failed_gate == "residual"
        assert "draw a card" in verdict.reason

    def test_an_ability_claiming_its_line_clears_residual(self, pool):
        whole = {
            **BEAR,
            "id": "auto_test_whole",
            "oracle_text": "Whenever this creature attacks, draw a card.",
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "Whenever this creature attacks, draw a card.",
                    "trigger": {"event": "attacks", "source": "self", "controller": "you"},
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
        verdict = V.verify(whole, {"zone": "battlefield"}, pool)
        assert verdict.ok, str(verdict)

    def test_a_keyword_line_is_its_own_implementation(self, pool):
        # "Flying" on its own line is implemented *by* the keyword, so the
        # residual gate must not ask for an ability as well.
        flier = {
            **BEAR,
            "id": "auto_test_flier",
            "oracle_text": "Flying",
            "keywords": ["flying"],
        }
        assert V.verify(flier, {"zone": "battlefield"}, pool).ok

    def test_a_card_that_cannot_be_cast_fails_on_playable(self, pool):
        # Its only target is an attacking creature, and the sandbox never
        # attacks -- the same limitation that kept Condemn out of the Isperia
        # deck. "Not castable here" is a real answer, not a crash.
        uncastable = {
            "id": "auto_test_condemn",
            "name": "Auto Test Condemn",
            "oracle_text": "Destroy target attacking creature.",
            "mana_cost": "{W}",
            "types": ["Instant"],
            "targets": [
                {
                    "id": "t1",
                    "kind": "permanent",
                    "selector": {"zone": "battlefield", "types": ["Creature"], "attacking": True},
                    "count": 1,
                }
            ],
            "spell_effects": [{"op": "destroy", "objects": {"target": "t1"}}],
        }
        verdict = V.verify(uncastable, {"zone": "graveyard"}, pool)
        assert verdict.failed_gate == "playable"

    def test_a_card_may_not_overwrite_a_hand_written_one(self, pool):
        """The nastiest thing a card-writing machine could do.

        Merged naively into the pool, an authored card with an existing id
        *replaces* the hand-written one, and every deck referencing that id
        silently changes. Nothing about the deck would look different.
        """
        clash = {**DIVINATION, "id": "sol_ring"}
        verdict = V.verify(clash, {"hand_size": {"0": 2}}, pool)
        assert verdict.failed_gate == "registry"
        assert "already in the pool" in verdict.reason


class TestTheSandboxIsUsable:
    def test_it_builds_from_whatever_pool_it_is_given(self, pool):
        """No dependency on test-only fixture cards.

        The sandbox picks its props by *role* -- a creature, a flier, an
        artifact, an enchantment -- so the authoring pipeline can run against the
        shipped registry, which has no `t_bear` in it.
        """
        game = V.build_sandbox(pool, "sol_ring")
        assert len(game.state.battlefield) > len(V.MANA_BASE)
        opponent = [o.def_id for o in game.state.battlefield_objects(1)]
        assert opponent, "the opponent's board is empty; targeted spells have nothing to hit"

    def test_the_props_are_stable(self, pool):
        # An unstable board makes a verdict unreproducible, which is the one
        # thing a gate must never be.
        assert V._props(pool, V.OPPONENT_BOARD_ROLES) == V._props(pool, V.OPPONENT_BOARD_ROLES)

    def test_every_expectation_key_is_actually_checked(self, pool):
        """Guards the pairing of `EXPECTATION_KEYS` and `check_expectation`.

        A key listed but not implemented would be accepted by gate 5 and then
        assert nothing -- a verified card that was never verified.
        """
        game = V.build_sandbox(pool, "sol_ring")
        oid = game.state.battlefield[0]
        for key in V.EXPECTATION_KEYS:
            sample = {
                "counters": {"kind": "+1/+1", "amount": 999},
                "tokens": {"id": "treasure_token", "count": 999},
                "battlefield_count": 999,
                "opponent_battlefield_count": 999,
                "zone": "nowhere",
                "target_pt_delta": {"power": 999, "toughness": 999},
            }.get(key, {"0": 9999})
            problems = V.check_expectation(game, "x", oid, {key: sample})
            assert problems, f"expectation key {key!r} asserts nothing"


class TestThePacketCarriesTheWholeVocabulary:
    """A worker sees only its packet, so an omission there reads as an absence.

    Sharktocrab was filed as blocked on a new `adapt` op because the packet
    listed no condition vocabulary, so "if this creature has no +1/+1 counters
    on it" looked unsayable. It was always sayable -- `cmp` against
    `counters_on` -- and the card needed no engine work at all. A gap record is
    cheap, but it is read as a build order, so an omission here costs real
    engine work on a mechanic that already exists.
    """

    def test_it_lists_every_vocabulary_the_loader_validates_against(self):
        from automtg.cards.authoring.packet import reference
        from automtg.cards.loader import STATIC_EFFECTS, STATIC_FILTER_KEYS
        from automtg.engine.effects import known_ops
        from automtg.engine.effects.conditions import CONDITION_KEYS
        from automtg.engine.effects.selectors import SELECTOR_KEYS
        from automtg.engine.effects.values import VALUE_KEYS

        ref = reference()
        for key, expected in (
            ("ops", known_ops()),
            ("selector_keys", SELECTOR_KEYS),
            ("condition_keys", CONDITION_KEYS),
            ("value_keys", VALUE_KEYS),
            ("static_filter_keys", STATIC_FILTER_KEYS),
            ("static_effects", STATIC_EFFECTS),
        ):
            assert set(ref[key]) == set(expected), (
                f"packet {key!r} has drifted from the set the loader enforces; a "
                f"worker cannot use vocabulary it is never shown"
            )

    def test_the_selector_and_static_filter_lists_are_both_present(self):
        """They are different languages and being shown only the smaller one
        reads as the whole of it -- a static may read printed characteristics
        only, an effect's selector may read far more.

        Neither contains the other, which is the reason both have to travel.
        `attached` ("enchanted creature gets +2/+2") is static-only because it
        reads board state rather than a derived characteristic; everything the
        selector language adds on top is unreachable from a static.
        """
        from automtg.cards.authoring.packet import reference

        ref = reference()
        static, selector = set(ref["static_filter_keys"]), set(ref["selector_keys"])
        assert static - selector == {"attached"}
        assert len(selector - static) > 10, "the selector language is the larger one"

    def test_the_cost_vocabulary_is_shown(self):
        """A worker shown `ops` but not `cost_keys` cannot tell a cost from an
        effect, so every "<cost>: <effect>" card either guesses or files a gap
        for a cost that already exists. Derived, so it cannot go stale."""
        from automtg.cards.authoring.packet import reference
        from automtg.cards.schema import CostModel

        assert set(reference()["cost_keys"]) == set(CostModel.model_fields)

    def test_counters_on_is_reachable(self):
        """The specific omission that cost a card."""
        from automtg.cards.authoring.packet import reference

        ref = reference()
        assert "counters_on" in ref["value_keys"]
        assert "cmp" in ref["condition_keys"]
