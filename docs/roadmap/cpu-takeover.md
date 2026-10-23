---
id: cpu-takeover
title: CPU takeover and reconnection
area: play
effort: M
impact: medium
why: every multi-human game somebody drops from; required before strangers share a table
depends_on: []
status: proposed
---

## Today

A seat whose human stops answering holds the table. The pod sweep already
evicts an idle chair before the deal; after it, the sweep ends the whole
session when it goes idle, and there is no middle state. Rejoining with the
same token is already the reconnect story, so a player who comes back finds
their seat if the game is still there, and nothing if it is not.

## The change

Once sessions persist, a seat idle past a threshold is piloted by the
strategy CPU for the deck it holds, the human may reclaim it with the same
token, and the table is told both times. The threshold is a constant on
`GameSession` beside the TTLs, the takeover is the existing `drive_ai` over
one more seat, and the handback is one tape entry that records the switch so
undo and replay see it. The pod view and the game view each carry the seat's
state, so an orb can say "away". This is the precondition for matchmaking
with strangers, where leaving is normal.

## Gate

A multiplayer server test that lets one seat go idle, asserts the CPU acts
for it and the others are told, then rejoins with the token and asserts the
human is back in control with the tape intact; and the pod e2e spec driving
two browsers through the same.
