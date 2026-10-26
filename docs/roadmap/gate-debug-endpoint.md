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
mode or environment check. Nothing in the client, the desktop shell or
`scripts/` calls it; two server tests do, `test_api.py` and
`test_multiplayer_game.py`, each asserting it reveals what `player_view`
hides. `ServerSettings.mode` is `desktop` or `hosted` and nothing else, and
`ServerSettings()` defaults to `hosted`, so every `create_app` a test builds
and a local `uvicorn` run are hosted too: there is no development mode to
check for.

## The change

Refuse it unless the app runs in a development or desktop mode;
`settings.py` already distinguishes hosted from desktop, so this is one
check in the handler. It should land before anything that puts more
strangers at one table. Delete the debt entry in the same pull request.

## Gate

A server test that builds the app with the hosted settings and asserts the
route returns a 404, beside the existing test that asserts the desktop mode
still reveals what `player_view` hides.

## Open questions

- **What does "development" mean, when no such mode exists?** Recommended: a
  new `ServerSettings.debug_endpoint` flag, read by `settings_from_env` from
  `COMMANDERBLITZ_DEBUG_ENDPOINT=1`, on by default when `mode` is `desktop`
  and off when it is `hosted`. A third `Mode` would change what the client is
  told by `GET /api/config` for a flag only the server reads; a flag keeps
  `mode` meaning where the server runs.
- **Does the desktop keep it?** The desktop's games are local to the
  sidecar, so nobody else holds their `game_id`. Recommended: yes, on by
  default there, so the item's "desktop still reveals" test stays true without
  an environment variable.
- **What happens to the two existing tests, whose clients are hosted?**
  Recommended: build those clients with the flag on and keep their
  assertions, and add the hosted-404 test beside each, for a single-player
  game and for a dealt pod, so both regimes in `_authorise` are covered.
- **Gate the route, or delete it?** Nothing calls it. Recommended: gate it;
  it is the one way to read a hidden zone while debugging the engine through
  the server, and deleting it would also delete the tests that hold the
  separation between `full_view` and `player_view`.
- **A check in the handler, or a route registered only when allowed?**
  Recommended: the check in the handler against `app.state.settings`, raising
  the same 404 an unknown game gets, so the route table is one fixed list and
  the refusal tells a stranger nothing.
- **Which docs move with it?** Recommended: delete `SV-01` and its line in
  the ordering at the top of `TECH_DEBT.md`, rewrite the `/debug` section of
  [server.md](../server.md) to name the flag, and change the row in
  [api.md](../api.md) from "development only" to the flag's name, all in the
  same pull request.
