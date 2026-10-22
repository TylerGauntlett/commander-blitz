---
id: sound
title: Sound
area: brand
effort: S
impact: low
why: a nicer beat, in a game that already narrates every one
depends_on: []
status: proposed
---

## Today

`audio/sfx.ts` synthesises its palette at runtime, one cue per beat the
narration names, and the reduced-motion channel decides whether a cue plays.

## The change

A recorded set with the same cue names replaces the synthesis without
touching the scheduler or the narration queue; the mute setting and the
reduced-motion channel keep their meaning. Files ship under
`frontend/public/` and count toward the content package's size budget.

## Gate

The timing test still holds every golden batch at or under its cost, since a
cue that waits on a file load would be a lag the narration must never have;
and the mute setting's e2e assertion still passes.
