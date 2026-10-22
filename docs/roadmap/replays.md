---
id: replays
title: Replays and sharing
area: play
effort: M
impact: medium
why: every bug report becomes a tape and every CPU misplay becomes a training position
depends_on: [zero-downtime-deploys]
status: proposed
---

## Today

The seed and the tape are a replay ([ADR 0005](../adr/0005-no-state-cloning.md)),
and undo already rebuilds a game from them, but nothing exposes them: a game
ends and its tape goes with the session, so a bug seen at the table cannot be
handed to anybody, and a CPU misplay cannot be pointed at by the arena.

## The change

A "share this game" link that serves the seed and the tape to a replay
viewer. The viewer is the existing table in a read-only mode, stepping the
narration beat by beat with the playback controls that already exist, with
every seat's hand hidden as `player_view` hides it today unless the sharer
chose to reveal their own. A tape file is also what a bug report attaches
and what `run_arena.py` accepts as a starting position, so a misplay seen
once becomes a seeded test. Persisted sessions make the tape durable past
the game; this item makes it a URL.

## Gate

A server test that a shared tape replays to the same final state and the
same event log as the game that produced it; a client test that the viewer
sends no action; and the arena accepting a tape as a position under test.
