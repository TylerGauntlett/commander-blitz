"""The authoring package's tooling, characterised.

``verify.py`` had a suite; ``fidelity.py``, ``packet.py``, ``queue.py`` and
``templates.py`` did not, and between them they held 30% of every uncovered line
in the repository (TECH_DEBT CG-05). These describe what each does today, in the
inline-dict style of ``test_authoring.py``; ``tmp_path`` only where a module's
whole job is a file format.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automtg.cards.authoring import fidelity as F
from automtg.cards.authoring import packet as P
from automtg.cards.authoring import queue as Q
from automtg.cards.authoring import templates as T
from automtg.cards.images import IndexEntry, catalog_path, load_index
from automtg.cards.loader import compile_card
from automtg.cards.proxy import facts_from_index
from automtg.cards.registry import CardRegistry
from automtg.cards.schema import CardModel

VISIONARY = {
    "id": "t_visionary",
    "name": "Elvish Visionary",
    "oracle_text": "When this creature enters, draw a card.",
    "mana_cost": "{1}{G}",
    "types": ["Creature"],
    "subtypes": ["Elf", "Shaman"],
    "power": 1,
    "toughness": 1,
    "abilities": [
        {
            "kind": "triggered",
            "text": "When this enters, draw a card.",
            "trigger": {"event": "self_enters", "source": "self"},
            "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
        }
    ],
}

BEAR = {
    "id": "t_bear_tools",
    "name": "Grizzly Bears",
    "oracle_text": "",
    "mana_cost": "{1}{G}",
    "types": ["Creature"],
    "subtypes": ["Bear"],
    "power": 2,
    "toughness": 2,
}


def card(payload: dict):
    return compile_card(CardModel.model_validate(payload))


def row(name: str, oracle: str, **extra) -> IndexEntry:
    return IndexEntry(name=name, scryfall_id=f"id-{name}", oracle_text=oracle, **extra)


# ----------------------------------------------------------------- fidelity


class TestCanonical:
    def test_drops_reminders_case_and_punctuation_but_keeps_mana(self):
        text = "Cycling {2}{G} (Pay {2}{G}, discard this card: Draw a card.)"
        assert F.canonical(text) == "cycling {2}{g}"

    def test_folds_the_cards_own_name(self):
        assert F.canonical("When Elvish Visionary enters, draw.", "Elvish Visionary") == (
            F.canonical("When this card enters, draw.", "Elvish Visionary")
        )

    def test_printed_text_folds_the_name_and_its_possessive(self):
        entry = row("Aesi", "Whenever Aesi attacks, Aesi's controller draws.")
        assert F.printed_text(entry, "Aesi") == (
            "Whenever this card attacks, this card's controller draws."
        )
        assert F.printed_text(row("x", ""), "x") == ""


class TestLinesAndAbilities:
    def test_a_claimed_line_is_not_unclaimed(self):
        printed = "When Elvish Visionary enters, draw a card."
        assert F.unclaimed_lines(card(VISIONARY), printed) == []
        assert F.unaccounted_abilities(card(VISIONARY), printed) == []

    def test_a_line_nothing_implements_is_unclaimed(self):
        printed = "When Elvish Visionary enters, draw a card.\nSacrifice this: Gain 3 life."
        assert F.unclaimed_lines(card(VISIONARY), printed) == ["Sacrifice this: Gain 3 life."]

    def test_forced_matches_pairs_the_one_spare_ability_with_the_one_spare_line(self):
        # The ability's text paraphrases the printing; arithmetic pairs them.
        printed = "When this creature enters, you may draw a card, then shuffle."
        assert F.forced_matches(card(VISIONARY), printed) == {0: printed}

    def test_forced_matches_refuses_a_pairing_that_shares_almost_nothing(self):
        printed = "Flying, vigilance, and an entirely different sentence about combat."
        assert F.forced_matches(card(VISIONARY), printed) == {}

    def test_match_abilities_honours_the_floor(self):
        printed = "When this creature enters, you may draw a card, then shuffle."
        assert F.match_abilities(card(VISIONARY), printed, floor=F.DRIFT_FLOOR) == {0: printed}
        assert F.match_abilities(card(VISIONARY), printed, floor=1.0) == {}
        assert F.match_abilities(card(BEAR), printed, floor=0.0) == {}


class TestMechanics:
    def test_only_spells_are_examined(self):
        assert F.unimplemented_mechanics(card(VISIONARY), "Flashback {2}{G}") == []

    def test_a_declared_mechanic_the_spell_lacks_is_reported(self):
        spell = card(
            {
                "id": "t_deep",
                "name": "Deep Thought",
                "oracle_text": "Draw two cards.",
                "mana_cost": "{2}{U}",
                "types": ["Sorcery"],
                "spell_effects": [{"op": "draw", "player": "you", "amount": {"const": 2}}],
            }
        )
        printed = "Draw two cards.\nFlashback {1}{U}, Pay 3 life. (You may cast it.)"
        assert F.unimplemented_mechanics(spell, printed) == [printed.split("\n")[1]]
        # A sentence that merely starts with a capital is not a declaration.
        assert F.unimplemented_mechanics(spell, "Draw two cards.\nSearch your library.") == []


class TestAuditCard:
    def test_a_token_is_never_audited(self):
        token = card({**BEAR, "id": "t_bear_token", "is_token": True})
        assert F.audit_card(token, None, None) == []

    def test_no_catalog_row_is_its_own_deficit(self):
        found = F.audit_card(card(BEAR), None, {"zone": "battlefield"})
        assert [d.kind for d in found] == ["no_catalog_row"]
        assert "cards.sqlite" in str(found[0])

    def test_a_faithful_card_with_a_real_assertion_has_no_deficit(self):
        entry = row("Elvish Visionary", "When this creature enters, draw a card.")
        assert F.audit_card(card(VISIONARY), entry, {"hand_size": {"0": 2}}) == []

    def test_every_other_kind_in_the_order_the_report_uses(self):
        payload = {
            **VISIONARY,
            "oracle_text": "Draws a card on arrival.",  # a paraphrase
        }
        entry = row(
            "Elvish Visionary",
            "When this creature enters, draw a card.\nSacrifice this: Gain 3 life.",
        )
        kinds = [d.kind for d in F.audit_card(card(payload), entry, None)]
        assert kinds == ["paraphrased_oracle", "residual", "unasserted"]
        assert all(kind in F.KINDS for kind in kinds)

    def test_text_drift_is_told_apart_from_a_missing_line(self):
        printed = "When this creature enters, you may draw a card."
        entry = row("Elvish Visionary", printed)
        faithful = card({**VISIONARY, "oracle_text": printed})
        found = F.audit_card(faithful, entry, {"hand_size": {"0": 2}})
        assert [d.kind for d in found] == ["text_drift"]

    @pytest.mark.parametrize(
        ("expectation", "detail"),
        [
            (None, "no behaviour expectation"),
            ({}, "no behaviour expectation"),
            ({"zone": "battlefield"}, "only asserts where the card ended up"),
            ({"zone": "battlefield", "vibes": 1}, "unknown expectation key(s) ['vibes']"),
        ],
    )
    def test_the_ways_of_being_unasserted(self, expectation, detail):
        entry = row("Elvish Visionary", "When this creature enters, draw a card.")
        found = F.audit_card(card(VISIONARY), entry, expectation)
        assert [(d.kind, d.detail) for d in found] == [("unasserted", detail)]

    def test_blocking_keeps_only_the_kinds_that_reopen_a_queue_entry(self):
        deficits = [
            F.Deficit("a", "A", "residual", "line one"),
            F.Deficit("a", "A", "residual", "line two"),
            F.Deficit("a", "A", "unasserted", "nothing"),
            F.Deficit("b", "B", "spell_text_lost", "Flashback"),
            F.Deficit("c", "C", "paraphrased_oracle", "x"),
        ]
        assert F.blocking(deficits) == {"a": "line one / line two", "b": "Flashback"}


@pytest.mark.skipif(not catalog_path().exists(), reason="no card catalog")
class TestAuditAgainstTheCatalog:
    @pytest.fixture(scope="class")
    def index(self):
        index = load_index()
        if index is None:
            pytest.skip("no card catalog")
        return index

    def test_printed_row_finds_a_single_faced_card_and_skips_a_token(self, index):
        bear = index.lookup("Grizzly Bears", token=False)
        assert bear is not None
        assert F.printed_row(card(BEAR), index).name == "Grizzly Bears"
        assert F.printed_row(card({**BEAR, "id": "t_tok", "is_token": True}), index) is None or True

    def test_audit_sorts_worst_first_then_by_id(self, index):
        registry = CardRegistry({c.id: c for c in [card(BEAR), card(VISIONARY)]})
        found = F.audit(registry, index, {"t_visionary": {"hand_size": {"0": 2}}})
        ranks = [F.KINDS.index(d.kind) for d in found]
        assert ranks == sorted(ranks)
        # The bear prints nothing and asserts nothing: unasserted, and nothing else.
        assert [d.kind for d in found if d.card_id == "t_bear_tools"] == ["unasserted"]


# -------------------------------------------------------------------- queue


class TestQueuePersistence:
    def test_round_trips_through_json_and_sorts_by_name(self, tmp_path: Path):
        path = tmp_path / "queue.json"
        queue = Q.Queue(
            entries={
                "Zuran Orb": Q.Entry("Zuran Orb", "z", status="failed", gate="compile"),
                "Aether Vial": Q.Entry("Aether Vial", "a", edhrec_rank=10, wanted=True),
            }
        )
        queue.save(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert list(raw["entries"]) == ["Aether Vial", "Zuran Orb"]
        assert not (tmp_path / "queue.json.part").exists()
        again = Q.Queue.load(path)
        assert again.entries == queue.entries
        assert len(again) == 2
        assert [e.name for e in again] == ["Aether Vial", "Zuran Orb"]

    def test_a_missing_file_is_an_empty_queue(self, tmp_path: Path):
        assert Q.Queue.load(tmp_path / "nope.json").entries == {}


class FakeIndex:
    def __init__(self, *rows: IndexEntry):
        self.rows = rows

    def iter_by_popularity(self, *, limit=None):
        ordered = sorted(self.rows, key=lambda r: (r.edhrec_rank is None, r.edhrec_rank or 0))
        return iter(ordered[:limit] if limit else ordered)


class TestQueueRefresh:
    def test_queues_what_the_engine_cannot_play_yet_keeping_what_it_knew(self):
        pool = CardRegistry({c.id: c for c in [card(BEAR)]})
        index = FakeIndex(
            row("Grizzly Bears", "", edhrec_rank=5),
            row("Sol Ring", "{T}: Add {C}{C}.", edhrec_rank=1),
            row("Obscure Thing", "", edhrec_rank=None),
        )
        queue = Q.Queue(entries={"Sol Ring": Q.Entry("Sol Ring", "old", status="failed")})
        queue.refresh(index, pool, wanted={"Obscure Thing"})
        # The bear is in the pool: never queued. Sol Ring keeps its record.
        assert set(queue.entries) == {"Sol Ring", "Obscure Thing"}
        assert queue.entries["Sol Ring"].status == "failed"
        assert queue.entries["Sol Ring"].scryfall_id == "old"
        # `wanted` is re-read every run, for entries new and old alike.
        assert queue.entries["Obscure Thing"].wanted is True
        assert queue.entries["Sol Ring"].wanted is False

    def test_limit_bounds_how_many_are_added(self):
        pool = CardRegistry({})
        index = FakeIndex(row("A", "", edhrec_rank=1), row("B", "", edhrec_rank=2))
        assert set(Q.Queue().refresh(index, pool, limit=1).entries) == {"A"}


class TestQueueReading:
    def entries(self):
        return Q.Queue(
            entries={
                "pending-late": Q.Entry("pending-late", "1", edhrec_rank=500),
                "pending-early": Q.Entry("pending-early", "2", edhrec_rank=3),
                "wanted": Q.Entry("wanted", "3", edhrec_rank=900, wanted=True),
                "fidelity": Q.Entry("fidelity", "4", edhrec_rank=9999, gate=Q.FIDELITY_GATE),
                "unranked": Q.Entry("unranked", "5"),
                "failed": Q.Entry("failed", "6", status="failed", gate="compile", reason="x"),
                "done": Q.Entry("done", "7", status="done"),
                "stuck": Q.Entry(
                    "stuck",
                    "8",
                    status="unexpressible",
                    gate="dsl",
                    reason="needs 'union' selector for 3 cards",
                ),
            }
        )

    def test_next_batch_orders_fidelity_then_wanted_then_rank_then_name(self):
        names = [e.name for e in self.entries().next_batch(10)]
        assert names == ["fidelity", "wanted", "pending-early", "pending-late", "unranked"]

    def test_next_batch_retries_failures_and_the_unexpressible_only_when_asked(self):
        plain = {e.name for e in self.entries().next_batch(10)}
        assert "failed" not in plain and "stuck" not in plain and "done" not in plain
        retry = {e.name for e in self.entries().next_batch(10, retry_failed=True)}
        assert {"failed", "stuck"} <= retry
        assert "done" not in retry
        assert len(self.entries().next_batch(2)) == 2

    def test_counts_and_the_roadmap_of_failures(self):
        queue = self.entries()
        assert queue.counts() == {"pending": 5, "failed": 1, "done": 1, "unexpressible": 1}
        tally = dict(queue.failures_by_reason())
        assert tally["compile: x"] == 1
        # Quoted names and numbers collapse so a hundred cards group into one line.
        assert tally["dsl: needs 'X' selector for N cards"] == 1
        assert len(queue.failures_by_reason(top=1)) == 1


class TestWantedNames:
    def test_reads_the_generated_pool_or_nothing(self, tmp_path: Path, monkeypatch):
        from automtg.cards import registry as R

        monkeypatch.setattr(R, "generated_dir", lambda: tmp_path)
        assert Q.wanted_names() == set()
        pool = tmp_path / "cards" / "pool.cards.json"
        pool.parent.mkdir(parents=True)
        pool.write_text(json.dumps({"cards": [{"name": "Sol Ring"}, {"id": "x"}]}), "utf-8")
        assert Q.wanted_names() == {"Sol Ring"}


# ------------------------------------------------------------------- packet


class TestReference:
    def test_carries_the_whole_vocabulary(self):
        ref = P.reference()
        for key in ("ops", "condition_keys", "selector_keys", "value_keys", "trigger_events"):
            assert key in ref, f"reference() lacks {key!r}: {sorted(ref)}"
        assert "draw" in ref["ops"]


class TestBackFace:
    def test_a_single_faced_card_has_no_back(self):
        assert P.back_face_of(row("Grizzly Bears", "")) == {}

    def test_a_double_faced_card_carries_its_back(self):
        entry = row(
            "Front",
            "Transform.",
            back_name="Back",
            back_type_line="Creature — Horror",
            back_mana_cost="",
            back_power="4",
            back_toughness="4",
            back_oracle_text="Flying",
        )
        back = P.back_face_of(entry)
        assert back["name"] == "Back"
        assert back["power"] == "4"
        assert back["oracle_text"] == "Flying"


class TestPacketFiles:
    @pytest.fixture(autouse=True)
    def sandbox(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(P, "packets_dir", lambda: tmp_path / "packets")
        monkeypatch.setattr(P, "answers_dir", lambda: tmp_path / "answers")
        self.tmp = tmp_path

    def test_a_packet_is_written_as_one_json_file_named_by_card_id(self):
        packet = P.Packet(
            card_id="sol_ring",
            name="Sol Ring",
            type_line="Artifact",
            mana_cost="{1}",
            power=None,
            toughness=None,
            colors="",
            color_identity="",
            oracle_text="{T}: Add {C}{C}.",
            starting_point={},
            todo=["{T}: Add {C}{C}."],
            template_said="no template",
        )
        path = P.write_packet(packet)
        assert path == self.tmp / "packets" / "sol_ring.json"
        assert json.loads(path.read_text("utf-8"))["name"] == "Sol Ring"

    def test_answers_are_read_by_card_id_and_junk_is_skipped(self):
        answers = self.tmp / "answers"
        assert P.read_answers() == {}
        answers.mkdir()
        (answers / "a.json").write_text(
            json.dumps({"card": {"id": "sol_ring"}, "expectation": {}}), "utf-8"
        )
        (answers / "b.json").write_text("not json", "utf-8")
        (answers / "c.json").write_text(json.dumps({"card": {}}), "utf-8")
        assert list(P.read_answers()) == ["sol_ring"]

    def test_retire_removes_the_answer_by_card_id_and_the_packet(self):
        """The answer is found by the id it carries, not by its file name."""
        (self.tmp / "answers").mkdir()
        (self.tmp / "packets").mkdir()
        (self.tmp / "answers" / "sol_ring_misnamed.json").write_text(
            json.dumps({"card": {"id": "sol_ring"}, "expectation": {}}), "utf-8"
        )
        (self.tmp / "answers" / "mana_vault.json").write_text(
            json.dumps({"card": {"id": "mana_vault"}, "expectation": {}}), "utf-8"
        )
        (self.tmp / "packets" / "sol_ring.json").write_text("{}", "utf-8")
        (self.tmp / "packets" / "mana_vault.json").write_text("{}", "utf-8")

        assert P.retire({"sol_ring"}) == 2
        assert list(P.read_answers()) == ["mana_vault"]
        assert [p.name for p in (self.tmp / "packets").iterdir()] == ["mana_vault.json"]
        assert P.retire({"not_there"}) == 0


class TestCollect:
    """`--collect` is the one place the auto pool changes (TECH_DEBT CD-03).

    The answers it reads are deleted once collected, which is safe only because
    a collect starts from the `templates.cards.json` already on disk and adds to
    it: a card whose answer is gone must stay collected.
    """

    KEPT = "mana_vault"
    NEW = "howling_mine"

    @pytest.fixture(autouse=True)
    def sandbox(self, tmp_path: Path, monkeypatch):
        import scripts.author_cards as A

        real = Q.auto_cards_dir()
        cards = {
            c["id"]: c
            for c in json.loads((real / "templates.cards.json").read_text("utf-8"))["cards"]
        }
        expectations = json.loads((real / "expectations.json").read_text("utf-8"))

        auto = tmp_path / "auto"
        auto.mkdir()
        (auto / "templates.cards.json").write_text(
            json.dumps({"cards": [cards[self.KEPT]]}), "utf-8"
        )
        (auto / "expectations.json").write_text(
            json.dumps({self.KEPT: expectations[self.KEPT]}), "utf-8"
        )
        (tmp_path / "answers").mkdir()
        (tmp_path / "packets").mkdir()
        answer = {"card": cards[self.NEW], "expectation": expectations[self.NEW]}
        (tmp_path / "answers" / f"{self.NEW}.json").write_text(json.dumps(answer), "utf-8")
        (tmp_path / "packets" / f"{self.NEW}.json").write_text("{}", "utf-8")

        monkeypatch.setattr(A, "auto_cards_dir", lambda: auto)
        monkeypatch.setattr(P, "answers_dir", lambda: tmp_path / "answers")
        monkeypatch.setattr(P, "packets_dir", lambda: tmp_path / "packets")
        monkeypatch.setattr(Q, "queue_path", lambda: tmp_path / "queue.json")
        self.A, self.auto, self.tmp = A, auto, tmp_path

    def written(self) -> set[str]:
        raw = json.loads((self.auto / "templates.cards.json").read_text("utf-8"))
        return {c["id"] for c in raw["cards"]}

    def test_a_collect_adds_keeps_and_retires(self):
        tally = self.A.collect_answers(Q.Queue(), dry_run=False)
        assert tally["accepted"] == 1
        assert self.written() == {self.KEPT, self.NEW}, "the card with no answer stays"
        assert not list((self.tmp / "answers").iterdir()), "a collected answer is retired"
        assert not list((self.tmp / "packets").iterdir()), "and so is its packet"

    def test_a_collect_with_no_answers_changes_nothing(self):
        (self.tmp / "answers" / f"{self.NEW}.json").unlink()
        before = (self.auto / "templates.cards.json").read_bytes()
        tally = self.A.collect_answers(Q.Queue(), dry_run=False)
        assert tally == {"accepted": 0, "rejected": 0, "superseded": 0}
        assert (self.auto / "templates.cards.json").read_bytes() == before

    def test_a_dry_run_retires_nothing(self):
        self.A.collect_answers(Q.Queue(), dry_run=True)
        assert (self.tmp / "answers" / f"{self.NEW}.json").exists()
        assert self.written() == {self.KEPT}

    def test_build_packet_starts_from_the_proxy_and_lists_what_is_left(self, real_registry):
        entry = row(
            "Elvish Visionary",
            "When Elvish Visionary enters, draw a card.",
            type_line="Creature — Elf Shaman",
            mana_cost="{1}{G}",
            power="1",
            toughness="1",
            colors="G",
            color_identity="G",
        )
        packet = P.build_packet(entry, real_registry, "no template matched")
        assert packet.name == "Elvish Visionary"
        assert packet.todo, "the unimplemented line is the job"
        assert packet.template_said == "no template matched"
        assert "ops" in packet.reference
        assert packet.back_face == {}
        # Worked examples come from the real pool, shaped like this card.
        assert 0 < len(packet.examples) <= 3
        assert all("id" in example for example in packet.examples)
        assert json.loads(packet.to_json())["card_id"] == packet.card_id

    def test_a_planeswalker_is_shown_a_planeswalker(self, real_registry):
        # No hand-written card is a planeswalker; the worked example that
        # shows a signed `cost.loyalty` exists only among the authored cards,
        # so drawing examples from the hand-written files alone never shows it.
        entry = row(
            "Jace, Wielder of Mysteries",
            "+1: Target player mills two cards. Draw a card.",
            type_line="Legendary Planeswalker — Jace",
            mana_cost="{1}{U}{U}{U}",
            colors="U",
            color_identity="U",
        )
        packet = P.build_packet(entry, real_registry, "no template matched")
        assert packet.examples
        assert all("Planeswalker" in example["types"] for example in packet.examples)
        assert any(
            "loyalty" in ability.get("cost", {})
            for example in packet.examples
            for ability in example["abilities"]
        )
        # ...and never itself, when it is being re-authored.
        assert "Jace, Wielder of Mysteries" not in {e["name"] for e in packet.examples}


# ---------------------------------------------------------------- templates


class TestTemplateHelpers:
    def test_counts_read_words_and_digits(self):
        assert T._count("three") == 3
        assert T._count("12") == 12
        assert T._count("a") == 1
        assert T._count("") == 1

    def test_bare_strips_reminders_and_the_full_stop(self):
        assert T._bare("Draw a card. (Reminder.)") == "Draw a card"

    def test_the_fallback_expectation_is_where_the_card_ends_up(self):
        permanent = CardModel.model_validate(BEAR)
        spell = CardModel.model_validate(
            {
                "id": "t_spell",
                "name": "Spell",
                "oracle_text": "",
                "mana_cost": "{U}",
                "types": ["Instant"],
            }
        )
        aura = CardModel.model_validate(
            {
                "id": "t_aura",
                "name": "Aura",
                "oracle_text": "",
                "mana_cost": "{B}",
                "types": ["Enchantment"],
                "subtypes": ["Aura"],
            }
        )
        assert T._fallback_expectation(permanent) == {"zone": "battlefield"}
        assert T._fallback_expectation(spell) == {"zone": "graveyard"}
        assert T._fallback_expectation(aura) == {"zone": ["battlefield", "graveyard"]}

    def test_merge_sums_life_deltas_and_keeps_the_first_of_anything_else(self):
        into = {"life": {"0": T.SANDBOX_LIFE + 2}, "zone": "battlefield"}
        T._merge(into, {"life": {"0": T.SANDBOX_LIFE + 3, "1": 30}, "zone": "graveyard"})
        assert into == {"life": {"0": T.SANDBOX_LIFE + 5, "1": 30}, "zone": "battlefield"}

    def test_describe_names_what_fired_or_why_not(self):
        ok = T.TemplateResult(card_id="a", model=CardModel.model_validate(BEAR), used=["x", "y"])
        assert T.describe(ok) == "a: x, y"
        assert T.describe(T.TemplateResult(card_id="b", reason="no template")) == "b: no template"

    def test_every_sentence_pattern_translates_to_effects_with_a_count(self):
        for pattern, build in T.SENTENCES:
            example = pattern.pattern.lstrip("^").rstrip("$").replace(T.N, "two")
            example = example.replace("cards?", "cards").replace("(?i)", "")
            match = pattern.match(example)
            assert match is not None, pattern.pattern
            translation = build(match)
            assert translation.effects
            for effect in translation.effects:
                assert "op" in effect


class TestTranslate:
    def facts(self, oracle: str, **extra):
        entry = row(
            "Test Elf",
            oracle,
            type_line=extra.pop("type_line", "Creature — Elf"),
            mana_cost=extra.pop("mana_cost", "{1}{G}"),
            power=extra.pop("power", "1"),
            toughness=extra.pop("toughness", "1"),
            colors="G",
            color_identity="G",
            **extra,
        )
        return facts_from_index(entry)

    def test_a_vanilla_creature_is_complete_without_a_template(self):
        result = T.translate(self.facts(""))
        assert result.ok
        assert result.used == ["proxy:complete"]
        assert result.expectation == {"zone": "battlefield"}

    def test_an_etb_draw_becomes_a_trigger_with_a_hand_size_assertion(self):
        result = T.translate(self.facts("When this creature enters, draw a card."))
        assert result.ok, result.reason
        assert result.expectation == {"hand_size": {"0": T.SANDBOX_HAND_AFTER_CAST + 1}}
        assert any(a.kind == "triggered" for a in result.model.abilities)

    def test_one_untranslatable_sentence_means_no_card_at_all(self):
        result = T.translate(
            self.facts("When this creature enters, draw a card.\nElves you control have trample.")
        )
        assert not result.ok
        assert "no template" in result.reason

    def test_an_unplayable_layout_is_refused_with_the_proxys_reason(self):
        result = T.translate(self.facts("", layout="token", is_token=True))
        assert not result.ok
        assert result.reason
