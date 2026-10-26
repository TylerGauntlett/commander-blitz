"""Hold `docs/roadmap.md` and the items under `docs/roadmap/` to `scripts/roadmap.py`.

The roadmap is the feature backlog as data: one item per file with a small
front matter, a page generated from them, and a queue derived from impact,
effort and dependencies. `/plan-feature` writes items and `/extend-roadmap`
reads the queue, so the rules the script enforces are what keep the two
skills honest with each other. They are pinned here on synthetic items, and
the committed backlog is held to the generator the way
`tests/cards/test_dsl_reference.py` holds the DSL reference.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "roadmap.py"


@pytest.fixture(scope="module")
def rm():
    spec = importlib.util.spec_from_file_location("roadmap", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("roadmap", module)
    spec.loader.exec_module(module)
    return module


BASE = "\n## Today\n\nWhat is.\n\n## The change\n\nWhat will be.\n\n## Gate\n\nA test.\n"
DECIDED = BASE + "\n## Decisions\n\n- Where? Here.\n"
OPEN = DECIDED + "\n## Open questions\n\n- How far?\n"


def item(
    id_: str,
    *,
    effort: str = "M",
    impact: str = "high",
    depends: str = "",
    status: str = "proposed",
    extra: str = "",
    body: str | None = None,
) -> str:
    body = body if body is not None else BASE
    return (
        f"---\nid: {id_}\ntitle: Item {id_}\narea: play\neffort: {effort}\n"
        f"impact: {impact}\nwhy: because\ndepends_on: [{depends}]\nstatus: {status}\n{extra}---\n"
        + body
    )


def backlog(tmp_path: Path, *items: str) -> Path:
    for text in items:
        id_ = text.split("id: ", 1)[1].split("\n", 1)[0]
        (tmp_path / f"{id_}.md").write_text(text, encoding="utf-8")
    return tmp_path


class TestAnItemIsHeldToItsShape:
    def test_a_well_formed_item_parses(self, rm):
        parsed = rm.parse_item(item("a", depends="b", extra="adr: true\ncontinuous: true\n"))
        assert parsed.depends_on == ["b"]
        assert parsed.adr and parsed.continuous
        assert parsed.effort_label == "M, continuous"

    @pytest.mark.parametrize(
        "text, message",
        [
            (item("Bad Id"), "kebab-case"),
            (item("a", effort="XL"), "effort"),
            (item("a", impact="huge"), "impact"),
            (item("a", status="done"), "status"),
            (item("a", depends="a"), "depends on itself"),
            (item("a", body="\n## Today\n\nx\n\n## Gate\n\ny\n"), "sections"),
            (item("a", body="\n## Today\n\n## The change\n\nx\n\n## Gate\n\ny\n"), "empty"),
            (
                item("a", body="\n# Top\n\n## Today\n\nx\n\n## The change\n\nx\n\n## Gate\n\nx\n"),
                "top-level",
            ),
            (item("a", body=BASE + "\n## Open questions\n\nq\n\n## Decisions\n\nd\n"), "order"),
            (item("a", body=BASE + "\n## Notes\n\nn\n"), "may follow"),
            (item("a", body=BASE + "\n## Decisions\n\n"), "empty"),
            (item("a").replace("area: play", "area: moon"), "area"),
            (item("a").replace("why: because\n", ""), "missing"),
            (item("a").replace("status: proposed", "status: proposed\nowner: me"), "unknown"),
        ],
    )
    def test_a_malformed_item_is_refused(self, rm, text, message):
        with pytest.raises(rm.RoadmapError, match=message):
            rm.parse_item(text)

    def test_a_scaffold_cannot_be_committed_as_a_plan(self, rm):
        text = rm.scaffold("a", "Item a", "play", "M", "high", "because", [], False, False)
        with pytest.raises(rm.RoadmapError, match="fill me in"):
            rm.parse_item(text)

    def test_the_id_must_match_the_file_name(self, rm, tmp_path):
        path = tmp_path / "b.md"
        path.write_text(item("a"), encoding="utf-8")
        with pytest.raises(rm.RoadmapError, match="file name"):
            rm.parse_item(path.read_text(encoding="utf-8"), path)


class TestTheGraphIsHeldTogether:
    def test_a_dependency_must_be_an_item(self, rm, tmp_path):
        backlog(tmp_path, item("a", depends="ghost"))
        with pytest.raises(rm.RoadmapError, match="not an item"):
            rm.load_items(tmp_path)

    def test_a_cycle_is_refused_and_named(self, rm, tmp_path):
        backlog(tmp_path, item("a", depends="b"), item("b", depends="c"), item("c", depends="a"))
        with pytest.raises(rm.RoadmapError, match="cycle: a -> b -> c -> a"):
            rm.load_items(tmp_path)

    def test_retiring_an_item_unblocks_its_dependants(self, rm, tmp_path):
        backlog(tmp_path, item("a"), item("b", depends="a"), item("c", depends="a, b"))
        freed = rm.retire("a", tmp_path)
        assert freed == ["b"]
        assert not (tmp_path / "a.md").exists()
        ids = {i.id: i for i in rm.load_items(tmp_path)}
        assert ids["b"].depends_on == []
        assert ids["c"].depends_on == ["b"]


class TestTheQueueRanks:
    def test_impact_then_effort_then_what_it_unlocks(self, rm, tmp_path):
        backlog(
            tmp_path,
            item("small-low", effort="S", impact="low"),
            item("big-high", effort="L", impact="high"),
            item("mid-high", effort="M", impact="high"),
            item("mid-high-key", effort="M", impact="high"),
            item("waits", depends="mid-high-key"),
            item("waits-more", depends="waits"),
        )
        items = rm.load_items(tmp_path)
        assert [i.id for i in rm.ready(items)] == [
            "mid-high-key",  # unlocks two, transitively
            "mid-high",
            "big-high",
            "small-low",
        ]
        assert [i.id for i in rm.blocked(items)] == ["waits", "waits-more"]
        assert rm.unlocks(items)["mid-high-key"] == 2

    def test_an_item_in_progress_is_neither_ready_nor_blocked(self, rm, tmp_path):
        backlog(tmp_path, item("a", status="in_progress"), item("b"))
        items = rm.load_items(tmp_path)
        assert [i.id for i in rm.ready(items)] == ["b"]
        assert [i.id for i in rm.in_progress(items)] == ["a"]


class TestTheAutopilotBuildsOnlyWhatIsDecided:
    def test_decisions_without_open_questions_is_decided(self, rm):
        assert rm.parse_item(item("a", body=DECIDED)).decided
        assert not rm.parse_item(item("a", body=OPEN)).decided
        assert not rm.parse_item(item("a")).decided

    def test_the_queue_is_ready_decided_and_never_continuous(self, rm, tmp_path):
        backlog(
            tmp_path,
            item("decided", body=DECIDED),
            item("open", body=OPEN),
            item("unplanned"),
            item("cards", extra="continuous: true\n", body=DECIDED),
            item("waits", depends="decided", body=DECIDED),
        )
        items = rm.load_items(tmp_path)
        assert [i.id for i in rm.autopilot(items)] == ["decided"]
        assert [i.id for i in rm.awaiting_decisions(items)] == ["open", "unplanned"]

    def test_the_page_says_an_item_awaits_decisions(self, rm, tmp_path):
        backlog(tmp_path, item("a", body=OPEN), item("b", body=DECIDED))
        text = rm.generate(tmp_path)
        assert text.count("Awaiting decisions") == 1
        assert "#### Decisions" in text and "#### Open questions" in text


class TestThePage:
    def test_the_page_lifts_links_and_demotes_sections(self, rm, tmp_path):
        body = "\n## Today\n\nSee [x](../x.md).\n\n## The change\n\nx\n\n## Gate\n\nx\n"
        (tmp_path / "x.md").write_text("", encoding="utf-8")
        backlog(tmp_path, item("a", body=body))
        (tmp_path / "x.md").unlink()
        text = rm.generate(tmp_path)
        assert text.startswith(rm.HEADER)
        assert "#### Today" in text and "## Today" not in text.replace("#### Today", "")
        assert "[x](x.md)" in text
        assert "| [Item a](#item-a) | M | high | nothing | 0 |" in text

    def test_slugs_follow_github(self, rm):
        assert rm.slugify("Why `default_cards`") == "why-default_cards"
        assert rm.slugify("Viewing a deck's list") == "viewing-a-decks-list"
        assert rm.slugify("Compressed art, shipped for offline precon play") == (
            "compressed-art-shipped-for-offline-precon-play"
        )


class TestTheCommittedBacklogIsCurrent:
    def test_check_passes_on_the_repository(self, rm):
        assert rm.check() == []

    def test_the_page_uses_lf_line_endings(self, rm):
        assert b"\r" not in rm.PAGE.read_bytes()

    def test_every_item_is_in_one_area_the_page_lists(self, rm):
        for it in rm.load_items():
            assert it.area in rm.AREAS
