"""The Scryfall bulk dump -> committed index pipeline.

Everything here runs against ``tests/data/mini_cards.jsonl``: nine real records
lifted verbatim from a bulk dump, one per branch the extractor has to get right.
Real records rather than hand-written ones because the shapes that break this
code are exactly the ones nobody would think to invent -- a modal DFC with no
top-level ``image_uris``, an adventure card where the *faces* have none, an art
series printing wearing a real card's name.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
import random
import sqlite3
import sys
from pathlib import Path

import pytest

from commanderblitz.cards import images as images_module
from commanderblitz.cards.images import CardIndex, image_url

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "data" / "mini_cards.jsonl"


def _load_builder():
    """Import ``scripts/build_card_index.py`` -- a script, not a package module."""
    path = REPO / "scripts" / "build_card_index.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("build_card_index", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


@pytest.fixture(scope="module")
def records() -> list[dict]:
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture(scope="module")
def rows(records) -> list[tuple]:
    return builder.extract(FIXTURE, include_funny=False)


@pytest.fixture(scope="module")
def index(tmp_path_factory, rows) -> CardIndex:
    target = tmp_path_factory.mktemp("catalog") / "cards.sqlite"
    builder.write_index(rows, target, {"source_name": FIXTURE.name, "rows": str(len(rows))})
    return CardIndex(target)


class TestFixtureIsWhatWeThink:
    """If the fixture drifts, every assertion below becomes meaningless."""

    def test_holds_one_record_per_branch(self, records):
        assert len(records) == 9
        layouts = sorted({r["layout"] for r in records})
        assert layouts == ["adventure", "art_series", "modal_dfc", "normal", "planar", "token"]

    def test_the_two_forests_differ_only_in_scan_quality(self, records):
        forests = [r for r in records if r["name"] == "Forest" and r["layout"] == "normal"]
        assert len(forests) == 2
        assert {r["image_status"] for r in forests} == {"lowres", "highres_scan"}


class TestImageExtraction:
    def test_takes_the_top_level_set_when_there_is_one(self, records):
        forest = next(r for r in records if r["name"] == "Forest" and r["layout"] == "normal")
        assert builder.face_images(forest) is forest["image_uris"]

    def test_falls_back_to_face_zero_on_a_modal_dfc(self, records):
        # transform / modal_dfc carry no top-level images at all: each face has
        # its own. Reading only the top level loses ~4,000 cards silently.
        mdfc = next(r for r in records if r["layout"] == "modal_dfc")
        assert "image_uris" not in mdfc
        assert builder.face_images(mdfc) is mdfc["card_faces"][0]["image_uris"]

    def test_prefers_the_top_level_on_an_adventure(self, records):
        # The mirror case: one physical card, so the top-level set is the only
        # one and the faces have none.
        adventure = next(r for r in records if r["layout"] == "adventure")
        assert "image_uris" not in adventure["card_faces"][0]
        assert builder.face_images(adventure) is adventure["image_uris"]


class TestFiltering:
    @pytest.mark.parametrize(
        ("layout_or_lang", "why"),
        [("ja", "a non-English printing"), ("digital", "a digital-only printing")],
    )
    def test_drops_what_cannot_be_shown(self, records, layout_or_lang, why):
        if layout_or_lang == "ja":
            record = next(r for r in records if r["lang"] == "ja")
        else:
            record = next(r for r in records if r.get("digital"))
        assert not builder.is_wanted(record, include_funny=False), why

    def test_drops_oversized(self, records):
        record = next(r for r in records if r.get("oversized"))
        assert not builder.is_wanted(record, include_funny=False)

    def test_drops_art_series(self, records):
        # 2,650 of these wear a real card's name while showing a different,
        # borderless illustration -- they must never win a name.
        record = next(r for r in records if r["layout"] == "art_series")
        assert not builder.is_wanted(record, include_funny=False)

    def test_keeps_the_ordinary_ones(self, records):
        keepers = [r for r in records if builder.is_wanted(r, include_funny=False)]
        assert sorted({r["name"] for r in keepers}) == [
            "Forest",
            "Obyra's Attendants // Desperate Parry",
            "Skyclave Cleric // Skyclave Basilica",
            "Vampire",
        ]


class TestDedupe:
    def test_one_row_per_name(self, rows):
        names = [row[0] for row in rows]
        assert len(names) == len(set(names)) == 4

    def test_the_better_scan_wins(self, rows, records):
        forest = next(row for row in rows if row[0] == "Forest")
        winner = next(
            r
            for r in records
            if r["name"] == "Forest" and r["layout"] == "normal" and r["image_status"] == "highres_scan"
        )
        assert forest[1] == winner["id"]

    def test_input_order_does_not_change_the_output(self, tmp_path, records):
        # A build has to be byte-stable or every refresh commit is noise. The
        # sort key ends in `id` precisely so ties cannot resolve arbitrarily.
        keepers = [r for r in records if builder.is_wanted(r, include_funny=False)]
        outputs = []
        for seed in (1, 2, 3):
            shuffled = list(keepers)
            random.Random(seed).shuffle(shuffled)
            path = tmp_path / f"shuffled-{seed}.jsonl"
            path.write_text(
                "\n".join(json.dumps(r) for r in shuffled) + "\n", encoding="utf-8"
            )
            outputs.append(builder.extract(path, include_funny=False))
        assert outputs[0] == outputs[1] == outputs[2]

    def test_rows_come_out_sorted_by_name(self, rows):
        assert [row[0] for row in rows] == sorted(row[0] for row in rows)


#: The two fixture Forests differ only in scan quality, so the sort has a clear
#: opinion about which one wins.  Pinning the loser is the sharpest test there
#: is that a pin overrules taste rather than merely agreeing with it.
LORES_FOREST = "2f5b488e-d725-4ef7-90f4-71091325c0b6"
HIGHRES_FOREST = "0000419b-0bba-4488-8f7a-6194544ce91e"


def _forest_id(records, pins):
    rows = builder.extract_records(records, include_funny=False, pins=pins)
    return next(row[1] for row in rows if row[0] == "Forest")


class TestArtPins:
    """A named exception beats retuning the sort for 32,000 cards."""

    def test_a_pin_beats_the_better_scan(self, records):
        assert _forest_id(records, {"Forest": LORES_FOREST}) == LORES_FOREST

    def test_no_pins_leaves_the_sort_alone(self, records):
        assert _forest_id(records, {}) == HIGHRES_FOREST

    def test_a_pin_holds_whatever_order_the_dump_arrives_in(self, records):
        # The pin is applied as records stream past, so a better printing
        # arriving *after* the pinned one must not displace it.
        keepers = [r for r in records if builder.is_wanted(r, include_funny=False)]
        for seed in (1, 2, 3):
            shuffled = list(keepers)
            random.Random(seed).shuffle(shuffled)
            assert _forest_id(shuffled, {"Forest": LORES_FOREST}) == LORES_FOREST

    def test_a_pin_at_an_unknown_id_says_so_and_changes_nothing(self, records, capsys):
        # The dump may predate the printing, or the id may just be wrong. Either
        # way the card silently keeps its old art, so the build has to say it.
        assert _forest_id(records, {"Forest": "not-a-real-id"}) == HIGHRES_FOREST
        assert "art pin for 'Forest'" in capsys.readouterr().out

    def test_a_pin_cannot_smuggle_in_a_printing_we_cannot_show(self, records):
        # `Forest // Forest` is an art series: a different illustration wearing
        # a real card's name. Pinning one must not get it past `is_wanted`.
        art_series = next(r for r in records if r["layout"] == "art_series")
        rows = builder.extract_records(
            records, include_funny=False, pins={art_series["name"]: art_series["id"]}
        )
        assert art_series["name"] not in [row[0] for row in rows]

    def test_the_committed_pins_name_printings_the_catalog_actually_has(self):
        # A pin whose card resolved to a different printing means the file and
        # the index have drifted apart -- the art on disk is then nobody's
        # choice, just whichever build ran last.
        pins = builder.read_art_pins()
        catalog = images_module.catalog_path()
        if not pins or not catalog.exists():
            pytest.skip("no pins, or no committed catalog to check them against")
        index = CardIndex(catalog)
        try:
            for name, scryfall_id in pins.items():
                entry = index.lookup(name)
                assert entry is not None, f"pinned card {name!r} is not in the catalog"
                assert entry.scryfall_id == scryfall_id, (
                    f"{name!r} is pinned to {scryfall_id} but the index holds "
                    f"{entry.scryfall_id} -- rebuild: python scripts/build_card_index.py"
                )
        finally:
            index.close()

    def test_a_missing_pin_file_is_not_a_failed_build(self, tmp_path):
        assert builder.read_art_pins(tmp_path / "absent.json") == {}

    def test_unreadable_pins_are_not_a_failed_build(self, tmp_path):
        broken = tmp_path / "art_pins.json"
        broken.write_text("{ not json", encoding="utf-8")
        assert builder.read_art_pins(broken) == {}

    def test_a_bare_id_is_accepted_as_well_as_a_documented_entry(self, tmp_path):
        path = tmp_path / "art_pins.json"
        path.write_text(
            json.dumps({"pins": {"A": "id-a", "B": {"scryfall_id": "id-b", "why": "..."}}}),
            encoding="utf-8",
        )
        assert builder.read_art_pins(path) == {"A": "id-a", "B": "id-b"}


class TestTheWrittenIndex:
    def test_every_name_is_queryable(self, index):
        assert len(index) == 4
        assert index.lookup("Forest") is not None

    def test_lookup_is_case_insensitive(self, index):
        assert index.lookup("forest").name == "Forest"

    def test_records_its_own_provenance(self, index):
        # Six months from now, "which dump did this come from" has to be
        # answerable without guessing.
        assert index.meta()["source_name"] == FIXTURE.name

    def test_a_token_is_marked_as_one(self, index):
        assert index.lookup("Vampire").is_token is True
        assert index.lookup("Forest").is_token is False

    def test_token_scoped_lookup_ignores_real_cards(self, index):
        assert index.lookup("Forest", token=True) is None

    def test_carries_the_fields_the_client_needs(self, index):
        forest = index.lookup("Forest")
        assert forest.type_line.startswith("Basic Land")
        assert forest.color_identity == "G"
        assert forest.artist

    def test_carries_the_fields_the_proxy_generator_needs(self, index):
        # Without these three a generated card is a blank permanent: no rules
        # text to read keywords out of, and -- worse -- no way to know a land
        # taps for anything.  A deck of inert lands is not a deck.
        forest = index.lookup("Forest")
        assert forest.produced_list() == ("G",)
        assert "{T}: Add {G}" in forest.oracle_text

        vampire = index.lookup("Vampire")
        assert vampire.keyword_list() == ("Lifelink",)
        assert vampire.produced_list() == ()

    def test_a_two_faced_card_borrows_its_rules_text_from_the_front_face(self, index):
        # Same shape as the mana_cost fallback below: an adventure or modal DFC
        # has no top-level oracle_text, only faces.  Without the fallback every
        # one of them would generate as a vanilla creature.
        entry = index.lookup("Obyra's Attendants // Desperate Parry")
        assert entry.oracle_text == "Flying"
        assert entry.keyword_list() == ("Flying",)

    def test_a_lookup_by_uuid_finds_the_same_row(self, index):
        forest = index.lookup("Forest")
        assert index.by_scryfall_id(forest.scryfall_id) == forest
        assert index.by_scryfall_id("nope") is None

    def test_a_modal_dfc_borrows_the_cost_from_its_front_face(self, index):
        # A modal DFC has no top-level mana_cost -- only the faces do -- so
        # `to_row` has to reach into face 0 or the catalog shows a blank cost.
        # `type_line` is different: the top level carries the combined line,
        # which is the one worth showing, so the fallback must not clobber it.
        entry = index.lookup("Skyclave Cleric // Skyclave Basilica")
        assert entry.mana_cost == "{1}{W}"
        assert entry.type_line == "Creature — Kor Cleric // Land"


class TestSearch:
    def test_returns_the_unclamped_total(self, index):
        total, results = index.search("o", limit=1)
        assert total > 1
        assert len(results) == 1

    def test_ranks_an_exact_name_first(self, index):
        _, results = index.search("Forest")
        assert results[0].name == "Forest"

    def test_filters_by_colour_identity(self, index):
        _, results = index.search(colors="W")
        assert [r.name for r in results] == [
            "Skyclave Cleric // Skyclave Basilica",
            "Vampire",
        ]

    def test_colour_filter_excludes_off_identity_cards(self, index):
        _, results = index.search(colors="G")
        assert [r.name for r in results] == ["Forest"]

    def test_filters_by_type_line(self, index):
        _, results = index.search(types="Land")
        assert "Forest" in [r.name for r in results]

    def test_a_wildcard_in_the_query_is_a_literal(self, index):
        # Unescaped, "%" would match everything and quietly turn a search box
        # into a full table scan.
        total, _ = index.search("%")
        assert total == 0


@pytest.fixture(scope="module")
def old_index(tmp_path_factory, rows) -> CardIndex:
    """An index written before the proxy columns existed."""
    target = tmp_path_factory.mktemp("old") / "cards.sqlite"
    early = [c for c in images_module.COLUMNS if c not in images_module.LATE_COLUMNS]
    con = sqlite3.connect(target)
    con.execute(f"CREATE TABLE cards ({', '.join(f'{c} TEXT' for c in early)})")
    con.executemany(
        f"INSERT INTO cards VALUES ({', '.join('?' * len(early))})",
        [row[: len(early)] for row in rows],
    )
    con.commit()
    con.close()
    return CardIndex(target)


class TestAnOlderIndexStillOpens:
    """A clone that has not rebuilt since the proxy columns landed.

    The committed sqlite is an *artifact*, not a migration target -- there is no
    migration machinery and there deliberately never was.  So the reader has to
    treat the late columns as optional, because the alternative is that pulling
    this branch without running the build script leaves the app unable to serve
    art it already has on disk.
    """

    def test_it_opens_and_still_answers_about_art(self, old_index):
        assert old_index.late_columns_present is False
        forest = old_index.lookup("Forest")
        assert forest is not None
        assert forest.art_url().endswith(".jpg")

    def test_the_missing_columns_read_as_empty_rather_than_crashing(self, old_index):
        forest = old_index.lookup("Forest")
        assert forest.oracle_text == ""
        assert forest.produced_list() == ()


class TestImageUrls:
    def test_derives_the_cdn_url_from_the_id_alone(self, records):
        # The index stores no URLs -- ~180 bytes a row of pure redundancy over
        # 33k rows. This asserts the derivation reproduces Scryfall's own URL.
        forest = next(
            r
            for r in records
            if r["name"] == "Forest" and r["layout"] == "normal" and r["image_status"] == "highres_scan"
        )
        published = forest["image_uris"]["art_crop"].split("?")[0]
        assert image_url(forest["id"], "art_crop") == published

    def test_rejects_a_size_it_cannot_serve_as_jpeg(self):
        with pytest.raises(ValueError, match="unsupported image size"):
            image_url("0000419b-0bba-4488-8f7a-6194544ce91e", "thumb")

    def test_rejects_an_implausible_id(self):
        with pytest.raises(ValueError, match="implausible"):
            image_url("x")


class TestBundleSource:
    """Getting a bundle must not require anyone to gather one by hand."""

    def test_reads_a_gzipped_bundle(self, tmp_path, records):
        # Scryfall serves .jsonl.gz and the file stays compressed on disk --
        # ~74 MB instead of ~600 MB. If the reader ever loses gzip support the
        # symptom is a JSONDecodeError on binary, so pin it.
        packed = tmp_path / "bundle.jsonl.gz"
        with gzip.open(packed, "wt", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
        assert builder.extract(packed, include_funny=False) == builder.extract(
            FIXTURE, include_funny=False
        )

    def test_finds_a_gzipped_bundle_in_the_drop_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(builder, "BULK_DIR", tmp_path)
        (tmp_path / "default_cards-2026-01-01.jsonl.gz").write_bytes(b"")
        found = builder.newest_bundle(tmp_path)
        assert found is not None and found.suffix == ".gz"

    def test_prefers_the_newest_bundle(self, tmp_path):
        old = tmp_path / "default_cards-2020-01-01.jsonl.gz"
        new = tmp_path / "default_cards-2026-01-01.jsonl.gz"
        old.write_bytes(b"")
        new.write_bytes(b"")
        os.utime(old, (1_000_000, 1_000_000))
        assert builder.newest_bundle(tmp_path) == new

    def test_default_bundle_is_the_english_one(self):
        # `all_cards` is five times the download and every extra row is a
        # non-English printing this build throws away.
        assert builder.DEFAULT_BULK_TYPE == "default_cards"

    def test_download_uses_the_jsonl_endpoint(self, tmp_path, monkeypatch):
        # The bulk-data API publishes both a JSON array and a newline-delimited
        # gzip. Only the latter streams, and only the latter is what `extract`
        # can read -- picking the wrong one fails on the very first line.
        monkeypatch.setattr(builder, "BULK_DIR", tmp_path)
        monkeypatch.setattr(
            builder,
            "bulk_entry",
            lambda kind: {
                "type": kind,
                "updated_at": "2026-08-07T21:14:33+00:00",
                "compressed_size": 77_000_000,
                "jsonl_download_uri": "https://data.scryfall.io/x.jsonl.gz",
            },
        )
        captured: dict[str, str] = {}

        class FakeResponse:
            def read(self, *_args):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

        def fake_urlopen(request, timeout=0):
            captured["url"] = request.full_url
            return FakeResponse()

        monkeypatch.setattr(builder.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(builder.shutil, "copyfileobj", lambda *a, **k: None)

        target = builder.download_bundle("default_cards")
        assert captured["url"] == "https://data.scryfall.io/x.jsonl.gz"
        assert target.name == "default_cards-2026-08-07.jsonl.gz"

    def test_a_cached_bundle_is_not_re_downloaded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(builder, "BULK_DIR", tmp_path)
        monkeypatch.setattr(
            builder,
            "bulk_entry",
            lambda kind: {"updated_at": "2026-08-07", "jsonl_download_uri": "https://x/y.gz"},
        )

        def explode(*_args, **_kwargs):
            raise AssertionError("re-downloaded a bundle that was already cached")

        monkeypatch.setattr(builder.urllib.request, "urlopen", explode)
        (tmp_path / "default_cards-2026-08-07.jsonl.gz").write_bytes(b"cached")
        assert builder.download_bundle("default_cards").read_bytes() == b"cached"


class TestRefreshLoop:
    """The property that stops this rotting into a one-off script."""

    def test_rebuilding_from_a_newer_dump_moves_the_row_and_the_provenance(
        self, tmp_path, records
    ):
        forests = {
            r["image_status"]: r
            for r in records
            if r["name"] == "Forest" and r["layout"] == "normal"
        }

        old = tmp_path / "old.jsonl"
        old.write_text(json.dumps(forests["lowres"]) + "\n", encoding="utf-8")
        new = tmp_path / "new.jsonl"
        new.write_text(
            "\n".join(json.dumps(f) for f in forests.values()) + "\n", encoding="utf-8"
        )

        target = tmp_path / "cards.sqlite"
        builder.write_index(
            builder.extract(old, include_funny=False), target, {"source_name": "old.jsonl"}
        )
        # Closed before the rebuild on purpose: Windows will not replace a file
        # another handle has open, which is the same reason `write_index` tells
        # you to stop the server. See `test_says_so_when_the_index_is_locked`.
        before = CardIndex(target)
        first = before.lookup("Forest").scryfall_id
        before.close()

        builder.write_index(
            builder.extract(new, include_funny=False), target, {"source_name": "new.jsonl"}
        )
        second = CardIndex(target)

        assert first == forests["lowres"]["id"]
        assert second.lookup("Forest").scryfall_id == forests["highres_scan"]["id"]
        assert second.meta()["source_name"] == "new.jsonl"
        second.close()

    def test_the_summary_reports_a_reprint_rather_than_an_add(self, tmp_path, records, capsys):
        forests = {
            r["image_status"]: r
            for r in records
            if r["name"] == "Forest" and r["layout"] == "normal"
        }
        # Keyed on (name, is_token), the same pair the table is keyed on.
        before = {("Forest", 0): forests["lowres"]["id"]}
        rows = [builder.to_row(forests["highres_scan"])]
        builder.summarise(before, rows)
        out = capsys.readouterr().out
        assert "added 0" in out
        assert "reprinted 1" in out

    def test_a_token_and_its_namesake_card_are_two_rows(self, tmp_path, records):
        """87 real cards used to be evicted by a token that shared their name.

        Tarmogoyf is the one that made this visible: the catalog's only
        "Tarmogoyf" row was a token printing, so an importer asking for the card
        by name got a token, and `validate_deck` then rejected the deck for
        containing one.
        """
        card = next(r for r in records if r["name"] == "Forest" and r["layout"] == "normal")
        token = {**card, "id": "0" * 8 + "-1111-2222-3333-444444444444", "layout": "token"}
        rows = builder.extract_records([card, token])
        target = tmp_path / "cards.sqlite"
        builder.write_index(rows, target, {"source_name": "collide"})
        index = CardIndex(target)
        try:
            assert index.lookup("Forest", token=False) is not None
            assert index.lookup("Forest", token=True) is not None
            # Unqualified, the real card wins: a deck can hold it and cannot
            # hold the token.
            assert index.lookup("Forest").is_token is False
        finally:
            index.close()

    @pytest.mark.skipif(sys.platform != "win32", reason="POSIX replaces open files happily")
    def test_says_so_when_the_index_is_locked(self, tmp_path, rows):
        # The realistic failure: someone leaves uvicorn running and re-runs the
        # build. Windows answers with a bare "WinError 5: Access is denied"
        # naming a temp file, which explains nothing.
        target = tmp_path / "cards.sqlite"
        builder.write_index(rows, target, {"source_name": "first"})
        holder = CardIndex(target)
        try:
            with pytest.raises(SystemExit, match="holding it open"):
                builder.write_index(rows, target, {"source_name": "second"})
        finally:
            holder.close()

    def test_an_interrupted_write_leaves_the_old_index_intact(self, tmp_path, rows, monkeypatch):
        target = tmp_path / "cards.sqlite"
        builder.write_index(rows, target, {"source_name": "good"})
        good = target.read_bytes()

        def explode(*_args, **_kwargs):
            raise sqlite3.OperationalError("disk full")

        monkeypatch.setattr(builder.sqlite3, "connect", explode)
        with pytest.raises(sqlite3.OperationalError):
            builder.write_index(rows, target, {"source_name": "bad"})

        assert target.read_bytes() == good
        assert not list(tmp_path.glob("*.tmp")), "a temp file was left behind"
