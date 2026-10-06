"""The rule the whole engine's reproducibility rests on, actually enforced.

`engine/rng.py` opens: "Every shuffle, coin flip and random choice routes
through :class:`Rng`.  Nothing else in ``automtg`` may call :mod:`random` or
``numpy.random`` directly -- a test in ``tests/unit/engine/test_determinism_hygiene.py``
enforces this by scanning the source."

That test did not exist. Three places cite it as the reason they are allowed to
do what they do -- `rng.py`'s own docstring, `server/lobby.py::make_code`, and
`docs/completed-features.md` -- so the claim was load-bearing and unbacked, which
is the worst of both: a reader trusts it and nothing checks it.

What it buys, and why a comment is not enough: golden replays, undo-by-replay
and reproducible training runs are all "the same seed gives the same game". One
`random.shuffle` anywhere in `engine/` breaks all three, silently, and only for
the games that happened to reach it. A shuffled library looks exactly as
plausible either way.

The scan is textual on purpose. An import-time or runtime check would only see
the paths a test happened to walk, and the failure mode here is a rarely-taken
branch.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "automtg"

#: The two modules allowed to reach for randomness directly, and why.
#:
#: `engine/rng.py` **is** the seam -- it wraps `random.Random` and is the single
#: source every other module goes through.
#:
#: `ai/train.py` is offline: it shuffles minibatch indices during training, not
#: game state. A training run is reproducible from its own `config.seed`, and
#: nothing it does reaches a `GameState`.
#:
#: `server/lobby.py` is deliberately absent from this list even though it is
#: random, because it uses `secrets` rather than `random` -- a pod code is not
#: part of a reproducible game, and `secrets` cannot be seeded by accident.
EXEMPT = {
    Path("engine/rng.py"),
    Path("ai/train.py"),
}

BANNED_MODULES = {"random", "numpy.random"}


def python_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def offences(path: Path) -> list[str]:
    """Every direct reach for a banned module in one file, as prose.

    Read as ``utf-8-sig``: several modules in this repo carry a UTF-8 BOM, which
    PEP 263 permits and the import machinery strips, but `ast.parse` chokes on
    once the text has already been decoded.
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in BANNED_MODULES or alias.name.startswith("random."):
                    found.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "") in BANNED_MODULES:
                names = ", ".join(a.name for a in node.names)
                found.append(f"line {node.lineno}: from {node.module} import {names}")
        elif isinstance(node, ast.Attribute):
            # `np.random.default_rng(...)` and `numpy.random.shuffle(...)`.
            value = node.value
            if (
                node.attr == "random"
                and isinstance(value, ast.Name)
                and value.id in ("np", "numpy")
            ):
                found.append(f"line {node.lineno}: {value.id}.random")
    return found


class TestNothingReachesPastTheSeam:
    @pytest.mark.parametrize(
        "path", python_files(), ids=lambda p: str(p.relative_to(SRC))
    )
    def test_this_module_routes_through_rng(self, path: Path):
        relative = path.relative_to(SRC)
        problems = offences(path)
        if relative in EXEMPT:
            return
        assert not problems, (
            f"{relative} reaches for randomness directly: {problems}. "
            "Everything in the engine routes through engine/rng.py's Rng, or "
            "golden replays, undo-by-replay and reproducible training all break "
            "for whichever games happen to reach this line."
        )

    def test_the_exemptions_are_all_real(self):
        """A stale exemption is a hole nobody is watching.

        If one of these stops importing `random`, the entry should go — leaving
        it behind means the next module to take that path inherits a licence
        that was granted for a different reason.
        """
        for relative in sorted(EXEMPT):
            path = SRC / relative
            assert path.exists(), f"{relative} is exempt and does not exist"
            assert offences(path), (
                f"{relative} no longer reaches for randomness; drop it from EXEMPT"
            )


class TestTheScanCatchesWhatItClaims:
    """The scanner is the thing being trusted, so it gets its own witnesses."""

    @pytest.mark.parametrize(
        "source",
        [
            "import random",
            "from random import shuffle",
            "import random as r",
            "import numpy.random",
            "np.random.default_rng(0)",
            "numpy.random.shuffle(x)",
        ],
    )
    def test_it_sees_a_direct_reach(self, source: str, tmp_path: Path):
        path = tmp_path / "probe.py"
        path.write_text(source, encoding="utf-8")
        assert offences(path)

    @pytest.mark.parametrize(
        "source",
        [
            "from .rng import Rng",
            "state.rng.shuffle(library)",
            "rng.randint(1, 6)",
            "self._random_choice(x)",
            "import secrets",
        ],
    )
    def test_it_does_not_flag_the_seam_or_its_callers(self, source: str, tmp_path: Path):
        path = tmp_path / "probe.py"
        path.write_text(source, encoding="utf-8")
        assert not offences(path)
