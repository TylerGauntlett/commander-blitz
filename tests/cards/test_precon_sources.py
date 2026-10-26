"""The precon manifest, and the promise the word "precon" makes (ADR 0024).

``data/decks/sources.json`` is written by ``scripts/sync_precons.py`` from
MTGJSON. These hold what the shelf depends on: the window is the script's one
constant, every row is inside it, and every deck shipped as a ``precon`` is a
row, so nothing a person built can be filed under the word again.
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest

from commanderblitz.cards.registry import load_decks
from tests.cards.test_deck_legality import PRECONS

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sync_precons.py"


@pytest.fixture(scope="module")
def sync():
    spec = importlib.util.spec_from_file_location("sync_precons", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def manifest(sync):
    return sync.read_manifest()


@pytest.fixture(scope="module")
def rows(manifest):
    return {row["id"]: row for row in manifest["rows"]}


class TestTheWindow:
    def test_the_manifest_was_written_with_the_scripts_window(self, sync, manifest):
        assert manifest["window_years"] == sync.WINDOW_YEARS

    def test_every_row_is_inside_the_window(self, sync, manifest):
        as_of = datetime.date.fromisoformat(manifest["as_of"])
        outside = [r["id"] for r in manifest["rows"] if not sync.in_window(r["date"], as_of)]
        assert outside == []

    def test_the_rows_are_newest_first(self, manifest):
        dates = [row["date"] for row in manifest["rows"]]
        assert dates == sorted(dates, reverse=True)

    def test_every_row_names_its_commanders_and_their_printings(self, manifest):
        """A coming-soon shell draws its commander from these, so a row
        without them is a blank tile on the shelf."""
        for row in manifest["rows"]:
            assert row["commanders"], row["id"]
            assert all(c["name"] and c["scryfall_id"] for c in row["commanders"]), row["id"]

    def test_ids_are_unique(self, manifest):
        ids = [row["id"] for row in manifest["rows"]]
        assert len(ids) == len(set(ids))


class TestEveryPreconHasARow:
    def test_the_precons_the_tests_name_are_the_ones_on_disk(self):
        on_disk = {d.id for d in load_decks().values() if d.source == "precon"}
        assert on_disk == PRECONS

    @pytest.mark.parametrize("deck_id", sorted(PRECONS))
    def test_a_precon_is_a_row(self, deck_id, rows):
        assert deck_id in rows

    @pytest.mark.parametrize("deck_id", sorted(PRECONS))
    def test_its_release_is_the_rows(self, deck_id, rows):
        deck = load_decks()[deck_id]
        row = rows[deck_id]
        assert deck.release == {
            "set_code": row["set_code"],
            "set_name": row["set_name"],
            "date": row["date"],
        }
        assert deck.name == row["product"]


class TestTheRules:
    """The script's filters on synthetic lists, so they hold without a download."""

    AS_OF = datetime.date(2026, 10, 24)
    SETS = [
        {"code": "AAC", "name": "Alpha Commander", "type": "commander"},
        {"code": "SLD", "name": "Secret Lair Drop", "type": "box"},
    ]

    def deck(self, name, code="AAC", date="2026-01-01", kind="Commander Deck"):
        return {"name": name, "code": code, "releaseDate": date, "type": kind, "fileName": name}

    def ids(self, sync, decks):
        return [row["id"] for row in sync.manifest_rows(decks, self.SETS, self.AS_OF)]

    def test_a_commander_deck_in_a_commander_set_is_a_row(self, sync):
        assert self.ids(sync, [self.deck("Angels All Around")]) == ["aac_angels_all_around"]

    def test_a_collectors_edition_is_its_plain_deck(self, sync):
        decks = [self.deck("Angels"), self.deck("Angels Collector's Edition")]
        assert self.ids(sync, decks) == ["aac_angels"]

    def test_a_secret_lair_is_not_a_precon(self, sync):
        assert self.ids(sync, [self.deck("Odds", code="SLD")]) == []

    def test_only_commander_decks(self, sync):
        assert self.ids(sync, [self.deck("Jumpstart", kind="Jumpstart")]) == []

    def test_the_window_is_inclusive_at_both_ends(self, sync):
        start = sync.window_start(self.AS_OF).isoformat()
        before = (sync.window_start(self.AS_OF) - datetime.timedelta(days=1)).isoformat()
        decks = [
            self.deck("Old", date=before),
            self.deck("Edge", date=start),
            self.deck("Today", date=self.AS_OF.isoformat()),
            self.deck("Future", date="2026-12-01"),
        ]
        assert sorted(self.ids(sync, decks)) == ["aac_edge", "aac_today"]

    def test_newest_first(self, sync):
        decks = [self.deck("Older", date="2024-01-01"), self.deck("Newer", date="2025-01-01")]
        assert self.ids(sync, decks) == ["aac_newer", "aac_older"]

    def test_an_id_is_the_set_and_the_product(self, sync):
        assert sync.precon_id("FDC", "Calling All Angels") == "fdc_calling_all_angels"
        assert sync.precon_id("PIP", "Mutant Menace") == "pip_mutant_menace"
        assert sync.precon_id("FIC", "Counter Blitz (FINAL FANTASY X)") == (
            "fic_counter_blitz_final_fantasy_x"
        )


class TestTheRoadmapFollowsTheManifest:
    """Every precon not shipped is a roadmap item, ranked set by set, newest first."""

    def test_every_pending_precon_is_an_item_and_every_item_a_pending_precon(self, sync, rows):
        pending = {sync.roadmap_id(i) for i in rows if not (sync.DECKS / f"{i}.deck.json").exists()}
        items = {p.stem for p in sync.ROADMAP.glob("precon-*.md")} - {"precon-sets"}
        assert items == pending, "run `python scripts/sync_precons.py --roadmap`"

    def test_the_ranks_close_out_one_set_at_a_time_newest_first(self, sync, rows):
        by_item = {sync.roadmap_id(i): row for i, row in rows.items()}
        ranked = []
        for path in sync.ROADMAP.glob("precon-*.md"):
            if path.stem == "precon-sets":
                continue
            rank = next(
                int(line.split(":", 1)[1])
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("rank:")
            )
            ranked.append((rank, by_item[path.stem]))
        sets = [row["set_code"] for _, row in sorted(ranked, key=lambda pair: pair[0])]
        runs = [code for n, code in enumerate(sets) if n == 0 or sets[n - 1] != code]
        assert len(runs) == len(set(runs)), "a set's precons are not contiguous in rank"
        dates = [max(r["date"] for _, r in ranked if r["set_code"] == code) for code in runs]
        assert dates == sorted(dates, reverse=True)

    def test_inside_a_set_the_closest_to_whole_goes_first(self, sync):
        rows = [
            {"id": "a_far", "set_code": "A", "date": "2026-01-01", "product": "Far"},
            {"id": "b_only", "set_code": "B", "date": "2026-06-01", "product": "Only"},
            {"id": "a_near", "set_code": "A", "date": "2026-01-01", "product": "Near"},
        ]
        order = sync.precon_order(rows, {"a_far": 40, "a_near": 3, "b_only": 50})
        assert [r["id"] for r in order] == ["b_only", "a_near", "a_far"]
