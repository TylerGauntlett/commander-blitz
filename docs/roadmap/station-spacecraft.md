---
id: station-spacecraft
title: "Station on Spacecraft: gated triggers, keywords and statics, and the creature at its number"
area: cards
effort: M
impact: medium
why: every Spacecraft in Edge of Eternities waits on it, two of them in the Counter Intelligence precon
depends_on: []
status: proposed
---

## Today

Station (702.184) is written out as a cost: `tap_permanents` with `as` and
`power_of {"binding": …}` charges the counters. A station symbol (721) is an
`Ability.threshold` of `{counter, at_least}`, and `cards.loader._compile_threshold`
accepts one on an **activated** ability only: `characteristics.abilities_of`
drops a gated ability below its number, and legality, the mana solver and the
AI read that list. A gated trigger or static is refused at load, because the
trigger collectors, `_ability_statics` and the player statics read printed
faces and would treat it as always on. A printed keyword has no threshold at
all, and nothing makes a Spacecraft a noncreature artifact below its highest
number and an artifact creature with its printed power and toughness at it
(721.2b). [rules-coverage.md](../rules-coverage.md#not-implemented) lists all
three as not implemented: "Spacecraft becoming artifact creatures at their
number, and a `threshold` on anything but an activated ability."

The two Planets (activated abilities only) are what ships. Inspirit, Flagship
Vessel and Uthros Research Craft, in the Counter Intelligence precon, are the
cards that found the rest; their gap records are
`data/authoring/gaps/inspirit_flagship_vessel.json` and
`data/authoring/gaps/uthros_research_craft.json`.

## The change

1. A threshold on a triggered ability. Every trigger collector asks
   `threshold_met` before it fires an ability with one, so a gated trigger
   below its number never triggers; the ability already on the stack resolves
   regardless (113.7a), as the activated form does.
2. A threshold on a static ability and on a printed keyword. The static
   collectors and the keyword reader skip a gated entry below its number, in
   the layer they already apply it in; a keyword threshold is a static
   `grant_keyword` on `self_only` gated the same way, or a keyword entry that
   carries its own threshold.
3. The Spacecraft rule. A card-level station number (the highest printed one,
   or a field the loader checks against it) makes `chars` read the Spacecraft
   as a noncreature artifact, with no power or toughness, below that number
   and as an artifact creature with its printed P/T at it (721.2b), in the
   type-changing layer.
4. `_compile_threshold` accepts the new homes, `_check_threshold_order` keeps
   its suffix rule, and rules-coverage.md moves the line to the implemented
   table.
5. Harvest the two Counter Intelligence Spacecraft and every other Spacecraft
   the template tier or one `/author-cards` wave can then express.

It does not add stationing with toughness (Tapestry Warden), which is a
separate cost reading.

## Gate

A unit test under `tests/unit/` for each home: a gated trigger that does not
fire below its number and fires at it, a gated keyword and a gated static that
switch on at the number and off when counters leave, the Spacecraft a
noncreature artifact below its number (no P/T, not attackable as a creature,
not hit by creature removal) and an artifact creature at it, and the loader
still refusing a threshold out of order. The harvested cards pass their six
gates.

## Open questions

- **How a keyword threshold is written.** A gated `grant_keyword` static on
  `self_only`, or a threshold field on the keyword entry itself? Recommended:
  the gated static, because it reuses the static gate this item builds and
  needs no new shape in `keywords`.
- **Where the Spacecraft's number lives.** Inferred from the highest
  threshold, or a card-level `station` field the loader checks against the
  thresholds? Recommended: a card-level field, because the reminder text prints
  the number and a Spacecraft whose top line is not a creature-gate would
  otherwise be read wrongly.
- **Is it an ADR.** Recommended: no; it extends the threshold 721 already
  uses here to the homes the rule names, and the rules-coverage line moves to
  the implemented table.
- **Scope of the harvest.** The two precon cards only, or every Spacecraft
  the template tier and one wave reach? Recommended: one template-tier
  `--retry` and one `/author-cards` wave, the precon items' convention.
