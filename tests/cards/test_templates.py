"""The deterministic translator: one case per template, against a real card.

The templates are the free tier -- they run before any model does, and every card
they finish is a card nobody has to pay to have written. That makes them worth
testing precisely, because a template that quietly does the wrong thing writes
its mistake into hundreds of cards at once.

Each case here goes all the way through the six gates rather than stopping at
"the JSON looks right". A template's output is only interesting if the engine
agrees with it.
"""

from __future__ import annotations

import pytest

from automtg.cards.authoring import templates as T
from automtg.cards.authoring import verify as V
from automtg.cards.images import catalog_path, load_index
from automtg.cards.proxy import facts_from_index
from automtg.cards.registry import CardRegistry, data_dir

pytestmark = pytest.mark.skipif(
    not catalog_path().exists(), reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def index():
    idx = load_index()
    if idx is None or not idx.late_columns_present:
        pytest.skip("catalog predates the authoring columns")
    return idx


@pytest.fixture(scope="module")
def hand_written() -> CardRegistry:
    """The pool minus `auto/`, so a card the pipeline already wrote can still be
    translated here without tripping the duplicate-id gate."""
    return CardRegistry.from_paths(sorted((data_dir() / "cards").glob("*.cards.json")))


def run(index, hand_written, name: str) -> tuple[T.TemplateResult, V.Verdict | None]:
    entry = index.lookup(name, token=False)
    assert entry is not None, f"{name} is not in the catalog"
    result = T.translate(facts_from_index(entry))
    if not result.ok:
        return result, None
    payload = result.model.model_dump(exclude_defaults=True, exclude_none=True)
    return result, V.verify(payload, result.expectation, hand_written, oracle_text=entry.oracle_text)


class TestTemplatesProduceCardsTheEngineAgreesWith:
    @pytest.mark.parametrize(
        ("card", "expectation"),
        [
            # An ETB lifegain land: the shape that appears most often among the
            # cards people actually play.
            ("Jungle Hollow", {"life": {"0": 41}}),
            ("Blossoming Sands", {"life": {"0": 41}}),
            # Lifegain with a number rather than a word.
            ("Radiant Fountain", {"life": {"0": 42}}),
            # A creature whose whole text is an ETB draw.
            ("Wall of Blossoms", {"hand_size": {"0": 1}}),
        ],
    )
    def test_it_translates_and_verifies(self, index, hand_written, card, expectation):
        result, verdict = run(index, hand_written, card)
        assert result.ok, result.reason
        assert result.expectation == expectation
        assert verdict.ok, str(verdict)

    def test_a_card_the_proxy_already_finishes_is_taken_as_is(self, index, hand_written):
        """A vanilla creature needs no translation and is still a finished card.

        This case was being thrown away at first -- 309 cards discarded as
        "already complete without templates" when they were, in fact, complete.
        Noticing cost one line and sextupled the yield.
        """
        result, verdict = run(index, hand_written, "Grizzly Bears")
        assert result.ok, result.reason
        assert result.used == ["proxy:complete"]
        assert verdict.ok, str(verdict)


class TestItRefusesRatherThanGuessing:
    def test_a_card_with_one_untranslatable_line_produces_nothing(self, index, hand_written):
        """All or nothing.

        A partial translation is the inert-proxy problem again, one sentence
        smaller -- and it would look finished.
        """
        result, _ = run(index, hand_written, "Scute Swarm")
        assert not result.ok
        assert "no template" in result.reason

    def test_a_card_the_proxy_had_to_simplify_is_not_claimed(self, index, hand_written):
        # Nothing left over *as a sentence*, but the proxy rewrote the mana cost
        # or dropped a back face. Those are real divergences from the printed
        # card, so this tier does not pretend to have finished it.
        result, _ = run(index, hand_written, "Gitaxian Probe")
        assert not result.ok

    def test_a_bare_sentence_on_a_permanent_is_not_guessed_at(self, index, hand_written):
        """"Draw a card" on a creature is not a spell effect.

        It belongs to a trigger or an activated ability, and putting it in the
        wrong place makes a card that does its thing at the wrong time -- which
        no gate downstream would catch, because it would still resolve.
        """
        line = T._translate_line("Draw a card.", is_spell=False)
        assert line is None
        assert T._translate_line("Draw a card.", is_spell=True) is not None


class TestEveryTemplateCarriesAnAssertion:
    def test_no_template_produces_a_card_with_nothing_to_check(self, index, hand_written):
        """Gate 5 rejects a card with no expectation, so a template that omits
        one produces cards that can never be written. Better caught here."""
        for pattern, build in T.SENTENCES:
            match = pattern.match(_example_for(pattern.pattern))
            assert match is not None, f"no example matches {pattern.pattern}"
            translation = build(match)
            assert translation.effects, f"{pattern.pattern} produces no effects"


def _example_for(pattern: str) -> str:
    """A sentence each pattern should match, written by hand from the pattern."""
    return {
        r"^draw (?P<n>\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten) cards?$": "draw two cards",
    }.get(pattern, _generic_example(pattern))


def _generic_example(pattern: str) -> str:
    """Turn a pattern back into a sentence by substituting the count group."""
    text = pattern.lstrip("^").rstrip("$")
    text = text.replace(T.N, "two")
    return text.replace("cards?", "cards").replace("(?i)", "")
