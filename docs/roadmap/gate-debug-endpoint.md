---
id: gate-debug-endpoint
title: Gate the debug endpoint
area: site
effort: S
impact: medium
why: a hidden-information leak that is harmless until strangers share a table
depends_on: []
status: proposed
---

## Today

`GET /api/games/{id}/debug` reveals every hand on the hosted site to anyone
holding a `game_id`. It is `SV-01` in [TECH_DEBT.md](../../TECH_DEBT.md), the
cheapest item there, and nothing in `server/routes.py` gates it: no setting,
mode or environment check.

## The change

Refuse it unless the app runs in a development or desktop mode;
`settings.py` already distinguishes hosted from desktop, so this is one
check in the handler. It should land before anything that puts more
strangers at one table. Delete the debt entry in the same pull request.

## Gate

A server test that builds the app with the hosted settings and asserts the
route returns a 404, beside the existing test that asserts the desktop mode
still reveals what `player_view` hides.
