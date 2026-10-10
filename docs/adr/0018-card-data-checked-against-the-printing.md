# ADR 0018 — Card data is checked against the printed card, and the loader refuses what it would ignore

**Status:** accepted

## Context

`compile_card` validates vocabulary, not meaning. A card whose ops all exist
and whose selectors all parse can still do something subtly different from what
it prints, and nothing on the board says so. The authoring gates in
`src/commanderblitz/cards/authoring/verify.py` exist to catch that, and the one
that asks "does this card implement everything it prints" — the residual gate —
works by matching the implementation against the card's `oracle_text`.

That gate was quietly disabled for a long time, because `oracle_text` was
described as display-only and written that way: a summary of what the card had
been made to do. A summary written after a shortcut agrees with the shortcut. A
card recorded as "A large boar." was a faithful implementation of a vanilla
creature, and shipped without its second ability with nothing to notice.

The changelog of the DSL is, to a large degree, a list of the other way a card
goes wrong silently: a key that the loader accepted and then nobody read. A
`controller` clause read three ways with a fallthrough that matched everybody. A
reduction filter that validated many keys and priced off a few, so a card that
said "for each legendary creature" priced off every creature. Trigger filter
keys that were legal selector keys and ignored on a trigger, making the trigger
wider than the printed line. A key coerced with `str()` into a subtype nobody
has. A restriction name that was a valid word and matched nothing. In every
case the card loaded clean.

## Decision

**`oracle_text` is the printed text, verbatim. Each ability's `text` is the
printed line it implements. A key the loader would accept and then ignore is a
load error.**

- **The printing is the contract.** The residual gate consumes `oracle_text`
  line by line against the abilities that claim each line, and a card with text
  left over fails. `tests/cards/test_hand_written_cards.py` compares every
  card's `oracle_text` to the catalogue and runs all six gates over the pool;
  `scripts/audit_cards.py` reports and can re-point text, and the recorded
  deficit list is kept empty.
- **A narrowing key ignored is a wider or cheaper card**, and that is the
  direction the loader refuses hardest. A filter, a controller clause, a zone, a
  supertype, a `tapped` on a trigger: if it is written, it is read, or loading
  raises `DslError` (`src/commanderblitz/engine/errors.py`) naming the key.
- **A trigger filter is a subset of the selector language.** `matches_card_filter`
  answers `TRIGGER_FILTER_KEYS` (`src/commanderblitz/engine/triggers.py`) and
  nothing else, and any other selector key on a trigger is refused rather than
  dropped.
- **Widening options default off.** A key that makes a card do more than the
  common printing — fire on battles as well as players, retarget a copy, give a
  cascaded creature haste — is opt-in, so every card written before it keeps its
  meaning.
- **A key with only one valid home is refused elsewhere.** `no_regeneration` on
  anything but `destroy`, `objects` on `proliferate`, a negative cost increase, a
  `chosen_color_of` inside a mode list: each would be read by nobody, which is
  how such clauses came to be dropped in the first place.
- **Every op added through `/extend-dsl` refuses unknown keys** at its spec
  (`src/commanderblitz/cards/loader/`), and a near-miss spelling is a refusal
  with a pointer, not an approximation.

## Consequences

- A "summary" `oracle_text` is not a style choice; it disables the only gate that
  asks whether a card is complete. An authoring tool that writes the text after
  the implementation has written the answer key from the answer.
- A capability the engine lacks is a card the pool refuses, not a weaker card
  that loads. The worker brief under `.agents/skills/author-cards/` is built on
  that: refuse rather than approximate, because the approximated card is the
  one nobody finds.
- Adding a key to any spec means adding its reader in the same change, or the
  loader must refuse it. "Accepted for forward compatibility" is the failure mode
  this decision exists to stop.
- Some refusals cost nothing because no card in the pool wrote the shape; those
  are still added, because the next card will.
- A fixed silent-ignore is a test, pinned on the shipped card that exposed it,
  not a paragraph here. History is git.

## Rejected

- **`oracle_text` as a caption**, maintained by hand to describe the
  implementation. That is the state this decision replaces.
- **Accept and warn.** A warning in a loader that runs at import time is read
  by nobody, and the card still plays wrong.
- **An allow-list of "harmless" extra keys.** There is no harmless ignored key
  on a card: an ignored narrowing widens, an ignored widening disappoints, and
  the loader cannot tell which a key is without reading it — at which point it
  should read it.
- **Approximate the nearest expressible card** when a line cannot be said. The
  near miss is strictly better or strictly worse than the printing and looks
  ordinary on screen; the changelog's worst entries are all of this shape.
