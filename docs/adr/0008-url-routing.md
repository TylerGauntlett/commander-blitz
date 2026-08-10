# ADR 0008 — Real URLs for the client

**Status:** accepted

Supersedes the "no router" decision recorded in `App.tsx` and `frontend.md`, which was
never written up as an ADR.

## Context

The client was a single page that never changed the address bar. Screens were a
discriminated union in one `useState`:

```ts
type Route =
  | { kind: "home" }
  | { kind: "lobby"; pod: PodSession }
  | { kind: "dealing"; gameId: string }
  | { kind: "table"; session: GameSession };
```

and `App.tsx` carried the argument for why that was right:

> A router would buy back-button navigation between a lobby and a game that are both
> *server* state -- going "back" to a pod that has already dealt is not a thing that
> can work, and a URL that pretends otherwise is worse than no URL.

The observation is correct. A pod that has dealt is `in_game`; its lobby cannot be
re-entered by anybody, and a Back button that offered to return there would be lying.

The conclusion does not follow, and three costs came with it:

- **Sharing a pod meant a query parameter.** The server emitted `/?join=GYRE-8412` and
  the client read it once at boot to *prefill a text field*. A pod had no address; it
  had a hint attached to the front door.
- **A refresh at the table dropped you at the front door**, mid-game, with the token
  still sitting in `sessionStorage` and no code left in memory to use it with.
- **Nothing else was linkable either** — not a deck, not the catalogue.

## Decision

**Use `react-router` v7 in declarative mode, with paths shaped like the API resources
behind them, and `replace` on every transition that cannot be undone.**

| Path | Screen |
|---|---|
| `/` | the front door; `?join=CODE` still prefills the code field |
| `/pods/:code` | the lobby |
| `/games/:gameId` | the table |
| `/decks`, `/decks/:deckId` | the catalogue, and one deck over it |
| anything else | a 404 screen, not a silent redirect |

Four rules make it work:

- **Plural collection nouns, matching the API.** `/pods/:code` sits beside
  `/api/pods/{code}`, `/games/:id` beside `/api/games/{id}`. One naming rule in the
  codebase rather than two that disagree by an `s`.
- **`replace`, not push, on the one-way transitions** — the deal, leaving a pod,
  quitting a table. This is the old objection, answered directly: a dead lobby is not
  something URLs make possible, it is something *pushing a history entry* makes
  possible. After a full session the stack is `["/", "/games/G"]`, so Back from the
  table lands on the front door.
- **The URL carries the place; `sessionStorage` carries the identity.** A link gets
  pasted into a group chat, so arriving at one must not be what grants a seat. A tab
  holding no token for `/pods/CODE` is redirected to `/?join=CODE` — the join flow
  that already existed.
- **`dealing` did not become an address.** It is the gap between knowing a game id and
  knowing which seat is yours, which resolves in one round trip. It is a state of
  `/games/:id`, not a URL of its own.

The server changes to match: `invite_link` becomes `/pods/{code}`, and `get_app()`
serves `frontend/dist` with a catch-all so a deep link resolves on a real deployment
the way Vite already resolves it in development.

## Consequences

**Good.** Reloading at the table returns you to your seat — a capability that did not
exist before, and the one users would have reported as a bug. An invite link points at
the pod it names. `App.tsx` went from 307 lines of nested ternary to ~60 lines of route
table, with each screen's wiring in its own file under `screens/`.

**The bare-render test invariant survives.** No component under `components/` imports
react-router, so every presentational unit test still renders with no providers around
it. Route components are the documented exception and share one `renderApp` helper.

**A cold deep link still needs the join handshake.** `/pods/CODE` on a machine that has
never joined cannot show the lobby, because identity is per-tab and not in the URL. It
lands at the door with the code filled in — one click, not none. That is deliberate:
taking a chair should be something somebody did on purpose.

**Deep links now depend on the host.** Vite's dev and preview servers do history
fallback; a plain static host does not. `create_app(serve_client=True)` covers the
deployment case, but any other hosting arrangement has to rewrite unknown paths to
`index.html` or every address but `/` will 404.

**Games are still in memory.** A server restart invalidates every `/games/:id` link,
and `SESSION_TTL_SECONDS` sweeps idle ones. A URL that outlives its game gets "that
game is over, or the server has restarted" rather than a blank screen.

## Alternatives considered

**Hash routing** (`/#/pods/GYRE-8412`) needs no server change at all and would have
made the catch-all unnecessary. Rejected because every invite link people paste would
carry the `#/`, and the `?join=` compatibility path gets fussy once the query string
sits on the other side of the fragment.

**Hand-rolled `pushState` over the existing union.** That is a router, minus the one
somebody else tests.

**TanStack Router**, whose typed params would pair with the TanStack Query already
here. Rejected for five routes: it wants a typed route tree and a build plugin, which
is more machinery than this earns.
