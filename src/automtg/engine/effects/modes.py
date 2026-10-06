"""Modal answers shared by `op_choose_mode`, `Game._ask_modes` and `stack`.

How many modes a ``choose_mode`` asks for, what each is called, and the flag
that marks one spent. A leaf below `ops_control` so `stack` can ask without
importing the op layer, which imports `stack` back.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .conditions import evaluate
from .context import EffectContext
from .values import evaluate_value


def modal_bounds(ctx: EffectContext, spec: Mapping[str, Any]) -> tuple[int, int | None]:
    """How many modes this ``choose_mode`` asks for: ``(floor, ceiling)``.

    Four clauses, and each one is a different printed sentence:

    * ``count`` -- "choose two", the plain number, and the floor when nothing
      widens it.
    * ``all_if`` -- **entwine**: "choose both if you pay the entwine cost". A
      floor raised to every mode, because the price has already been paid.
    * ``up_to_if`` -- "if you control a commander as you cast this spell, you
      **may** choose both instead". A ceiling, not a floor: the difference is
      the word "may", and it is the whole card whenever taking one mode is the
      better line.
    * ``up_to`` -- "choose up to two", an unconditional ceiling with **no
      floor**. Taking none is a real line: Call Damage Control with an empty
      graveyard is cast for its other half, and a floor of one would force a
      mode that does nothing.
    * ``or_more`` -- "choose one **or more**". The floor `count` gives, with the
      ceiling opened to every mode. The fifth spelling because the other four
      cannot say it between them: `count` is exact, `all_if` forces the lot,
      `up_to` drops the floor to nothing, and `up_to_if` has the shape but
      demands a `condition` -- and "one or more" is not conditional on anything.

    ``None`` for the ceiling means "exactly the floor".  Lives in its own
    module because three callers need the same answer -- `op_choose_mode` for a
    triggered or nested modal, `Game._ask_modes` for the ordinary cast (601.2b), and
    `stack.free_cast_modes` for a spell cast with nobody to ask.
    """
    count = evaluate_value(ctx, spec.get("count", 1))
    modes = list(spec.get("modes") or [])
    if (gate := spec.get("all_if")) is not None and evaluate(ctx, gate):
        count = len(modes)
    up_to = None
    if (more := spec.get("up_to_if")) is not None and evaluate(ctx, more.get("condition")):
        up_to = evaluate_value(ctx, more.get("count", len(modes)))
    # "Choose one or more --". Every mode is on offer and `count` is the floor,
    # so a wider `up_to_if` still wins if a card ever prints both.
    if spec.get("or_more"):
        up_to = len(modes) if up_to is None else max(up_to, len(modes))
    if spec.get("up_to"):
        up_to = count if up_to is None else max(up_to, count)
        return 0, up_to
    return max(1, count), up_to


_COLOR_WORDS = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}


def mode_labels(modes: list[Mapping[str, Any]]) -> list[str]:
    """What each mode is called on the button that offers it.

    The printed ``label`` when the card has one. Without one, a mode whose whole
    effect is a single sentence the engine can say back is named after that
    sentence -- Giver of Runes shipped six unlabelled protection modes and
    offered them as "Mode 1" to "Mode 6", a choice nobody could make. "Mode N"
    is the last resort, not the default.

    Shared by the three places that ask: `Game._ask_modes`, the trigger push in
    `stack`, and the nested fallback in `op_choose_mode`.
    """
    return [str(m.get("label") or _describe_mode(m) or f"Mode {i + 1}") for i, m in enumerate(modes)]


def _describe_mode(mode: Mapping[str, Any]) -> str | None:
    effects = list(mode.get("effects") or [])
    if len(effects) != 1:
        return None
    effect = effects[0]
    op = effect.get("op")
    if op == "grant_protection":
        qualities = ["colorless"] if effect.get("from_colorless") else []
        qualities += [_COLOR_WORDS.get(c, str(c)) for c in effect.get("from_colors") or ()]
        if effect.get("from_everything"):
            qualities.append("everything")
        if qualities and all(isinstance(q, str) for q in qualities):
            return "Protection from " + " and ".join(qualities)
    if op == "add_mana" and isinstance(effect.get("mana"), str):
        return f"Add {effect['mana']}"
    return None


def _mode_flag(label: str) -> str:
    """The flag marking one mode as already taken.

    Keyed by the printed label rather than the index, so a card whose modes are
    reordered does not silently re-open a spent one.
    """
    return f"mode_chosen:{label}"
