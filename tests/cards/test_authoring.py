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


@pytest.fixture(scope="module")
def hand_written() -> CardRegistry:
    """The pool minus `auto/` -- the position an authored card is measured in.

    Not the same board as `pool`, and the difference matters wherever a test
    reads a *number* off it. `--collect` and `tests/cards/test_auto_cards.py`
    both verify against the hand-written pool, so that is the board every
    expectation in `data/cards/auto/` was written against; the whole shipped
    registry picks its props from 2,400 machine-authored cards instead, and one
    of them is an Aura, which state-based actions bin on sight.
    """
    from automtg.cards.registry import data_dir

    return CardRegistry.from_paths(sorted((data_dir() / "cards").glob("*.cards.json")))


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


class TestASelfLegalTriggerIsExercisedAgainstTheBoard:
    """The half of gate 4 that must not be traded away to make a card pass.

    Commander Sofia Daguerre's "When this enters, destroy up to one target
    legendary permanent" may lawfully name *her*. Until the sandbox carried a
    legendary permanent of its own she was the only legal target it could offer,
    so she destroyed herself and gate 4 rejected her for "ended in graveyard" --
    a correct card failing for a harness reason.

    The fix was a prop, not a wider gate (`verify._play_once` carries the
    argument). Which means the two claims below are one claim: a permanent whose
    own trigger may finish it is verified against the board, **and** a permanent
    that genuinely vanishes is still rejected. Drop the second and the first is
    a weakened gate wearing a test.
    """

    #: Sofia's shape, reduced to the part that mattered: a Legendary permanent
    #: whose enters trigger is a removal effect its own source satisfies.
    SELF_LEGAL = {
        "id": "auto_test_crash_landing",
        "name": "Auto Test Crash Landing",
        "oracle_text": "When this creature enters, destroy up to one target legendary permanent.",
        "mana_cost": "{2}{W}",
        "types": ["Creature"],
        "supertypes": ["Legendary"],
        "subtypes": ["Human", "Soldier"],
        "power": 3,
        "toughness": 3,
        "abilities": [
            {
                "kind": "triggered",
                "text": (
                    "When this creature enters, destroy up to one target legendary permanent."
                ),
                "trigger": {"event": "self_enters", "source": "self"},
                "targets": [
                    {
                        "id": "t1",
                        "kind": "permanent",
                        "selector": {"zone": "battlefield", "supertypes": ["Legendary"]},
                        "count": 1,
                        "optional": True,
                    }
                ],
                "effects": [{"op": "destroy", "objects": {"target": "t1"}}],
            }
        ],
    }

    #: No target, no choice, no ambiguity: it enters and it is gone. Gate 4's
    #: entire reason for existing.
    VANISHES = {
        "id": "auto_test_vanishing_ogre",
        "name": "Auto Test Vanishing Ogre",
        "oracle_text": "When this creature enters, sacrifice it.",
        "mana_cost": "{1}{R}",
        "types": ["Creature"],
        "subtypes": ["Ogre"],
        "power": 3,
        "toughness": 3,
        "abilities": [
            {
                "kind": "triggered",
                "text": "When this creature enters, sacrifice it.",
                "trigger": {"event": "self_enters", "source": "self"},
                "effects": [{"op": "sacrifice", "objects": {"self_only": True}}],
            }
        ],
    }

    def test_a_card_that_may_target_itself_clears_every_gate(self, hand_written):
        verdict = V.verify(
            self.SELF_LEGAL,
            # 6 down to 5, and the opponent's graveyard says which one. Two
            # keys rather than one because `zone: "battlefield"` on its own is
            # satisfied by a trigger that declined and did nothing.
            {"zone": "battlefield", "graveyard_size": {"1": 1}, "opponent_battlefield_count": 5},
            hand_written,
        )
        assert verdict.ok, str(verdict)

    def test_it_is_exercised_against_the_board_rather_than_itself(self, hand_written):
        """The card survives, and the *opponent's* legendary is the one that died.

        This is the observation the gap record asked for: a self-legal removal
        trigger pointed at the position instead of at the card under test.
        """
        card = V.compile_card(V.CardModel.model_validate(self.SELF_LEGAL))
        merged = V.CardRegistry({**{c.id: c for c in hand_written}, card.id: card})
        game, oid, _, _ = V._cast(merged, card)

        assert game.state.objects[oid].zone is V.Zone.BATTLEFIELD
        opponent_graveyard = game.state.players[1].graveyard
        assert len(opponent_graveyard) == 1, "the trigger destroyed nothing"
        died = game.state.registry.get(game.state.objects[opponent_graveyard[0]].def_id)
        assert "Legendary" in died.supertypes
        assert died.id != card.id

    def test_a_permanent_that_genuinely_vanishes_is_still_rejected(self, hand_written):
        """The gate is not weaker than it was.

        A creature that leaves the battlefield on arrival is exactly what gate 4
        catches, and no expectation could reveal it: `zone: "graveyard"` is a
        legal thing for an authored card to claim.
        """
        verdict = V.verify(self.VANISHES, {"zone": "graveyard"}, hand_written)
        assert verdict.failed_gate == "playable"
        assert "ended in graveyard" in verdict.reason


class TestTheLegendaryProp:
    """What the sandbox gained, and what it was not allowed to cost."""

    def test_the_board_carries_exactly_one_legendary_permanent(self, hand_written):
        game = V.build_sandbox(hand_written, "sol_ring")
        legendary = [
            o
            for pid in (0, 1)
            for o in game.state.battlefield_objects(pid)
            if "Legendary" in game.state.registry.get(o.def_id).supertypes
        ]
        assert len(legendary) == 1, "a legendary target, and only one, or the counts move"
        assert legendary[0].controller == 1, "it is the opponent's, so removal points across"

    def test_the_boards_are_still_the_documented_sizes(self, hand_written):
        """32 and 6, because every authored expectation was written against them.

        `_props` silently drops a role the pool cannot fill, so a role narrow
        enough to go unfilled would shrink the opponent's board by one and
        falsify every `opponent_battlefield_count` in `data/cards/auto/`
        without changing a single card file. This is the tripwire for that.
        """
        game = V.build_sandbox(hand_written, "sol_ring")
        assert len(game.state.battlefield_objects(0)) == 32
        assert len(game.state.battlefield_objects(1)) == 6

    def test_the_prop_is_inert(self, hand_written):
        """Nothing on it triggers and nothing on it can be activated.

        A prop exists to be pointed at. One that *acts* folds its own behaviour
        into every card's verdict -- and in the opponent's hands a payable
        non-mana activated ability is worse than noise: it stops the auto-pass,
        so the opponent takes a real priority window while the card under test
        is still on the stack, `drive` returns at `PRIORITY`, and every card in
        the pool fails gate 4 with "never left the stack".
        """
        prop_id = V._props(hand_written, V.OPPONENT_BOARD_ROLES)[0]
        prop = hand_written.get(prop_id)
        assert "Legendary" in prop.supertypes
        assert prop.is_creature
        assert not [a for a in prop.abilities if a.is_activated or a.is_triggered]


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
        The static-only keys are mostly one category -- **relationships between
        two permanents**, read off a field rather than off a characteristic:
        soulbond's two are "as long as this creature is paired, **both** get
        +1/+1", one static written once and applied to two creatures. Both are
        board state, so no static can depend on another's output through them.

        `owner` is the exception and is static-only for a duller reason: no card
        has yet needed an *effect* to say "creatures you own". It arrived for
        Inspiring Leader's "Commander creatures you own have …", where 903.3
        makes ownership the rules-relevant relation, and it stays on this side
        of the line until a one-shot prints the word.

        `attached` used to be here and is now in *both* lists. The claim that it
        was "meaningless to an effect's selector" was simply wrong: Blade of the
        Bloodchief puts a counter on equipped creature and Skullclamp draws when
        it dies, and neither is a continuous effect. Being static-only was the
        reason no `op` could reach the equipped creature at all.
        """
        from automtg.cards.authoring.packet import reference

        ref = reference()
        static, selector = set(ref["static_filter_keys"]), set(ref["selector_keys"])
        assert static - selector == {"paired", "paired_with_source", "owner"}
        assert "attached" in static and "attached" in selector
        assert len(selector - static) > 10, "the selector language is the larger one"

    def test_the_static_condition_vocabulary_is_shown(self):
        """A third language, and the packet showed neither of the other two in
        its place: a worker who cannot see that a static may be conditional
        files a gap for "as long as" clauses that already work."""
        from automtg.cards.authoring.packet import reference
        from automtg.cards.loader import STATIC_CONDITION_HEADS

        assert set(reference()["static_condition_keys"]) == set(STATIC_CONDITION_HEADS)

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

class TestATransformingCardIsOneAnswer:
    """Henrika Domnathi, Edgar Charmed Groom -- two faces, one answer file.

    The *engine* has shipped transforming double-faced cards for a long time:
    `card_of` picks a face, `back_face` links them, and bloodline_keeper /
    lord_of_lineage is a shipped pair. Only the authoring path was missing --
    `collect_answers` read `answer["card"]` as a single dict, so a card that is
    two entries could not be written at all.

    The back travels with the front rather than as a second answer, because a
    second answer would need its own expectation and a back face has no position
    it can be cast in. What it does is proven through the front.
    """

    def front_and_back(self):
        front = {
            "id": "t_two_faced_probe",
            "name": "Two Faced Probe",
            "oracle_text": "Flying",
            "mana_cost": "{1}{B}",
            "types": ["Creature"],
            "subtypes": ["Vampire"],
            "power": 2,
            "toughness": 2,
            "keywords": ["flying"],
            "colors": ["B"],
            "color_identity": ["B"],
            "back_face": "t_two_faced_probe_back",
        }
        back = {
            "id": "t_two_faced_probe_back",
            "name": "Two Faced Probe Back",
            "oracle_text": "Deathtouch",
            "types": ["Creature"],
            "subtypes": ["Vampire"],
            "power": 3,
            "toughness": 3,
            "keywords": ["deathtouch"],
            "colors": ["B"],
            "color_identity": ["B"],
        }
        return front, back

    def test_a_front_with_its_back_passes(self, real_registry):
        from automtg.cards.authoring import verify as V

        front, back = self.front_and_back()
        verdict = V.verify(
            front, {"zone": "battlefield"}, real_registry, companions=[back]
        )
        assert verdict.ok, verdict.reason

    def test_a_front_without_its_back_is_refused(self, real_registry):
        """The dangling link is a registry failure, not a silent half-card.

        This is the gate that makes the feature safe: `link_faces` refuses a
        one-way link, so an answer that forgot its back face cannot ship a
        creature whose transform ability points at nothing.
        """
        from automtg.cards.authoring import verify as V

        front, _ = self.front_and_back()
        verdict = V.verify(front, {"zone": "battlefield"}, real_registry)
        assert verdict.failed_gate == "registry"
        assert "back_face" in verdict.reason

    def test_the_collector_reads_one_back_or_several(self):
        from scripts.author_cards import _companion_faces

        assert _companion_faces({"card": {}}) == []
        assert _companion_faces({"card": {}, "back": {"id": "a"}}) == [{"id": "a"}]
        assert _companion_faces({"card": {}, "back": [{"id": "a"}, {"id": "b"}]}) == [
            {"id": "a"},
            {"id": "b"},
        ]



class TestTheQueueTracksWhatIsInYourDecks:
    """`wanted` is what puts an imported deck's cards at the head of the queue.

    `Queue._priority` sorts fidelity deficits, then `wanted`, then EDHREC rank --
    so a card somebody actually put in a list is worked on before the global
    popularity tail. That ordering is the queue's whole editorial claim.
    """

    def _queue_with(self, *names: str):
        from automtg.cards.authoring.queue import Entry, Queue

        return Queue(entries={n: Entry(name=n, scryfall_id=f"id-{n}") for n in names})

    def test_refresh_marks_a_card_already_queued_before_the_import(self, real_registry):
        """The case the flag exists for, and the one it used to miss.

        `refresh` skips a name it already holds, so `wanted` was only ever set at
        the moment an entry was *created*. Import a deck afterwards -- which is
        the normal order, the queue is built from the catalog long before anybody
        pastes a list -- and every one of its cards stayed `wanted: False`.
        `--report`'s "in your decks" line read 0 no matter how many decks were in
        `data/generated/`.
        """
        from automtg.cards.images import load_index

        queue = self._queue_with("Sol Ring", "Llanowar Elves")
        assert not any(e.wanted for e in queue)

        queue.refresh(load_index(), real_registry, wanted={"Sol Ring"}, limit=0)

        assert queue.entries["Sol Ring"].wanted
        assert not queue.entries["Llanowar Elves"].wanted

    def test_a_card_dropped_from_every_deck_stops_being_wanted(self, real_registry):
        """It is re-read every run, not accumulated.

        `wanted_names()` reads `data/generated/` fresh each time, so deleting an
        imported deck has to be able to take the flag back off -- otherwise the
        priority list silently keeps promoting cards nobody plays any more.
        """
        from automtg.cards.images import load_index

        queue = self._queue_with("Sol Ring")
        queue.entries["Sol Ring"].wanted = True

        queue.refresh(load_index(), real_registry, wanted=set(), limit=0)

        assert not queue.entries["Sol Ring"].wanted

    def test_refresh_still_keeps_a_recorded_verdict(self, real_registry):
        """`wanted` is an input; `status`, `gate` and `reason` are results.

        The docstring's promise -- "without disturbing what is already recorded"
        -- is about the run's findings, and re-reading the flag must not cost
        them.
        """
        from automtg.cards.images import load_index

        queue = self._queue_with("Sol Ring")
        entry = queue.entries["Sol Ring"]
        entry.status, entry.gate, entry.reason = "unexpressible", "residual", "nope"

        queue.refresh(load_index(), real_registry, wanted={"Sol Ring"}, limit=0)

        assert (entry.status, entry.gate, entry.reason) == ("unexpressible", "residual", "nope")
        assert entry.wanted
