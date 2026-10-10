# ADR 0009 — The desktop build runs its own server, and the site is for friends

**Status:** accepted

## Context

Playing on a Steam Deck meant adding Chrome as a non-Steam game, correcting its
resolution in the launch options, changing the Steam Input template by hand, going
without library artwork, and serving the game over https so the Gamepad API existed
at all ([steamdeck.md](../steamdeck.md) was mostly that list). It also meant a
connection: the game lived on `commanderblitz.com` and nowhere else.

The brief for the desktop build had four requirements that pull against each other:
a self-contained install that plays **fully offline**; a setup a player can finish
in one step; something that looks and behaves like a Steam title; and online play
with friends when there is a connection. And one constraint that shaped every
decision below: **no Steam Deck was available to test on.** Everything had to be
verifiable on Windows, in WSL, or in CI, and anything that could only be checked on
the device had to be designed out.

## Decisions

**The server runs on the device, always.** The desktop build is an Electron window
around the same FastAPI server the site runs, frozen with PyInstaller and started on
every launch as a sidecar on `127.0.0.1`. The window loads the client from it. An
offline launch is the normal launch; nothing waits on the network.

**Offline play is not a mode; it is the local server serving pods.** Solo play
already goes through a pod (the door's Play card creates one and fills the chairs
with CPUs), so the local server serving `/api/pods` *is* offline play. No new game
code. What the client learns from `GET /api/config` is which server it is talking
to (`desktop` or `hosted`) and whether the hosted one is reachable; the door greys
out what needs the other one.

**Online play with friends happens on the hosted site, in the hosted client.** The
desktop's Online card hands the window to `commanderblitz.com`, and a "Back to the
app" link brings it home. The alternative -- the local client talking to the hosted
API for pods -- would have meant CORS for a desktop origin, a protocol-version
handshake, and a stale app breaking online play until it updated. On the site the
client and the server are always the same build. The cost is a second deck list:
pods only seat decks the server they run on already has, so the hand-off carries the
Moxfield ids of decks imported at home (`?from=desktop&import=a,b`) and the site
imports them before showing the door. For that, imported decks now record their
`source_id`, case intact, which the lowercased deck id had lost.

**A deck imported on the desktop fetches its art at once.** The site fills art
lazily, on the first board that shows a card. A desktop whose next launch may be
offline cannot wait for that, so with `COMMANDERBLITZ_EAGER_ART` the import prefetches
every printing the deck will ask for, in parallel. The art store's lock used to be
held across each download, which made a hundred-card prefetch a hundred sequential
round trips; it now guards the bookkeeping only, with one gate per file.

**Updates never restart the Electron process.** Steam Game Mode watches the process
it launched, and what it does when that process is replaced by another could not be
tested without a Deck. So content -- the server, the client and the card data,
versioned together as one package -- is updated by restarting the *server* in place:
stop it, point `state.json` at the new directory, start it again, wait for
`/health`, reload the window. If the new server does not come up, the pointer goes
back and the old one is started again. Shell updates (Electron itself; rare)
download in the background and install when the app quits; `quitAndInstall` is never
called. The page shows one banner, Chrome-style, and the Restart button is disabled
at the table because games live only in the server's memory.

**Releases are public, and fetched without a token.** The updater on a player's Deck
must never hold a token, so every asset has to be readable anonymously. While the
source was private, that meant copying releases to a separate public repository. Since
the project went public, they are this repository's own Releases. The updater and the
install script read `releases/latest/download/…`, which needs no API and no token.
Every push to main that ships builds the AppImage and the content package and publishes
both. Before [ADR 0010](0010-release-every-main-build.md), a release needed a `v*` tag.

**Install is one command, and it is testable.** `install.sh` downloads the AppImage
to a fixed path (the Steam shortcut and the in-place updater both depend on the name
never changing), writes a launcher, adds the game to Steam through
`steamos-add-to-steam`, reads the shortcut's app id out of `shortcuts.vdf` and
copies the library artwork under it. Every external it touches -- the release URL,
the home directory, the Steam helper, the interpreter -- is a parameter, so the whole
script runs in CI against a stub Steam in a scratch directory.

## Consequences

- There are two update channels on one cadence. Every merge that ships deploys the site
  and releases the desktop build ([ADR 0010](0010-release-every-main-build.md)). This
  originally read "the desktop catches up when a release is tagged". The change came
  when the repository went public and Actions minutes stopped being rationed.
- Two deck lists. A deck imported at home follows its owner to the site through the
  hand-off; a deck imported on the site does not come back.
- A player who installed by hand, to a path of their choosing, gets a shell update
  that cannot swap the file. The banner says it installs on quit; the log says why
  it did not.
- Some things remain unverified until a Deck runs it: the non-Steam app id
  algorithm (the script prefers the id Steam wrote and falls back to the CRC
  community tools use), Chromium's behaviour under gamescope (`--no-sandbox` and
  `--ozone-platform-hint=auto` are set inside an AppImage; a `flags` file in the
  per-user directory adds more), and which Steam Input template a non-browser
  executable receives.

## Rejected

- **A progressive web app with a service worker.** Would have made the site itself
  work offline in any browser, but the engine is Python: it would mean running it
  in the browser (Pyodide), a large refactor of a server written around threads and
  blocking long-polls, with CPU players noticeably slower.
- **Tauri.** On Linux it renders with WebKitGTK, whose Gamepad API support is the one
  thing this build cannot do without.
- **A hosted-only shell** (the window loads `commanderblitz.com` and nothing else).
  Simplest, and what the first draft of this work was; it fails the offline
  requirement outright.
- **Relaunch-based updates** (`quitAndInstall`, or a launcher script that restarts
  the app). Both put the question of how Game Mode tracks a replaced process on the
  critical path, and that question has no answer without the device.
