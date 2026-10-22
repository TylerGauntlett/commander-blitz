---
id: outcome-log
title: Outcomes as data
area: site
effort: M
impact: medium
why: nothing a player sees, and everything brackets, matchmaking and the CPU need to be tuned from real play
depends_on: []
status: proposed
---

## Today

Several items want to know what actually happens at the table: how long
games run, which decks win, how often a draw is a `RulesLoopError`, how often
a seat is abandoned. `/health` counts live games and nothing else, and the
arena is the only source of outcomes, which measures the CPU against itself.

## The change

One structured log line per game end, carrying deck ids, seats, turns, the
outcome and its reason, and never a name or a token; and one per
abandonment. Written by `GameSession` at the moment it already emits
`GAME_OVER`, read by nothing in the request path, and rotated by the
container's log driver as every other line is. Opt-in on the desktop, where
the player's machine is the server and the line would otherwise go nowhere.
A small script under `scripts/` folds a log into the per-deck table the
arena already prints, so the two can be read side by side.

## Gate

A server test that plays a game to its end and asserts one line with the
documented fields and nothing identifying; the scripts table in
[scripts.md](../scripts.md) gains the folding script's row.
