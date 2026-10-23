# Playing on a Steam Deck

The game is built for this device — 1280×800 is the size every layout was
measured at, and the whole controller layer exists for it. There is a desktop
build that installs in one step, plays with no connection at all, and goes to
the site when you want to play with friends.

## Install

In **Desktop Mode**, open Konsole and paste:

```bash
curl -fsSL https://github.com/TylerGauntlett/commander-blitz/releases/latest/download/install.sh | bash
```

That downloads the app to `~/Applications/CommanderBlitz.AppImage`, adds it to
Steam, puts the library artwork in place, and says so as it goes. Switch back to
**Game Mode** and Commander Blitz is in your library with a capsule, a hero and
a logo like anything else there.

If Steam was not running when the script ran, or you would rather do it by hand:
Steam → Games → **Add a Non-Steam Game** → Browse → the AppImage above, then
Properties → **Launch Options**: `--no-sandbox` (without it, Chromium refuses
to start inside an AppImage on SteamOS and Steam's spinner never ends). Then
run the script again to get the artwork.

### What the script does, so you can undo it

| It wrote | Why |
|---|---|
| `~/Applications/CommanderBlitz.AppImage` | The app. A fixed name: the Steam shortcut points at it and updates replace it in place |
| `~/.local/share/applications/commanderblitz.desktop` and an icon | A launcher for Desktop Mode, and what Steam reads the name, icon and the `--no-sandbox` launch option from. Start the app through it, not by double-clicking the AppImage |
| `~/.steam/steam/userdata/<you>/config/grid/<appid>*.png` | The library artwork, named by the shortcut's app id |
| `~/.local/share/commanderblitz/` | Everything the app writes while running: imported decks, art it fetched, logs, updates |

Uninstall: remove the shortcut in Steam, then delete those four.

## Offline and online

**Everything you can do alone works with no connection.** The app runs the
game's own server on the device; dealing a pod, filling the chairs with CPUs,
and playing is all local. The only things that need the internet are the two
that reach another machine:

- **Online** (the third card on the door) takes you to `commanderblitz.com` to
  play with friends. Pods with other people run there, in the site's own client;
  there is a **Back to the app** link on the site's door. Any deck you imported
  from Moxfield at home comes with you — the site imports it before showing the
  door.
- **Importing a Moxfield deck** goes through the site, which reads Moxfield and
  sends the deck back with the rules for every card in it, so a card the site
  learned since your last update plays in full. If the site does not answer,
  the app reads Moxfield itself.

When there is no connection the Online card is dimmed (it is still there, so the
row does not move) and pressing it says why; the import strip in the deck
catalogue is disabled with a note. The moment the connection is back, both come
back on their own.

A deck imported while online fetches all of its art at once, so it is complete the
next time you are offline. If the import is cut short, the deck's tile and its
details say some art is not on the device yet, and the next launch with a
connection finishes it before the front door appears.

## Updates

The app checks for updates when it starts and every few hours after, downloads
them in the background, and shows one line at the top of the screen when one is
ready. Two kinds:

- **The game** (the engine, the cards, the client): **Update ready — Restart.**
  Restart takes a few seconds — the server restarts underneath the window — and
  if the new version does not come up, the app goes back to the one that did.
  The button waits while you are at a table: a restart mid-game would lose it.
- **The app itself** (rare): *installs the next time you quit.* Nothing to press.

Offline, no check happens and the version you have runs. Nothing about an update
ever restarts the app or takes you out of Game Mode.

## The controller

The app is served from the device over `localhost`, which is a secure context,
so the Gamepad API exists without any of the https work a browser needed. What
can still happen is Steam Input handing the app a keyboard:

**The symptom:** only the D-pad and A do anything, and the hint bar (if you have
turned it on) says `Enter` and `Esc` instead of `A` and `B`.

**The fix:** in Game Mode, select the game → the controller icon → **Controller
settings** → **Templates** → **Gamepad**. The sticks and shoulder buttons start
working the moment it takes effect. The in-game **Settings** card lists every
controller the app can see and, when it sees none, what to check.

## If it will not start

The app shows the last lines of the server's log and where the full logs are
(`~/.local/share/commanderblitz/logs/`). The **Settings** card on the door shows
the app and content versions, the server's port, whether the device is online,
and what the last update did — a screenshot of it is most of a bug report.

Two switches, if the window is black under Game Mode: create
`~/.local/share/commanderblitz/flags` with one Chromium flag per line
(`--disable-gpu` is the one to try first) and relaunch.

## Playing in a browser instead

The site at <https://commanderblitz.com> plays the same game in any browser, and
the fallback below applies there too. In a browser on a Deck three things need
to be true before a gamepad works, in this order:

1. **Serve it over https, or localhost.** The Gamepad API does not exist over
   plain `http://` to anything but `localhost`; a dev server opened by LAN
   address is the single most common cause, and invisible because the same URL
   works on the machine serving it.
2. **Set the Steam Input template to Gamepad**, as above — Steam recognises
   browsers and picks a keyboard-and-mouse template for them.
3. **If the browser is a Flatpak, let it reach the device:** in Desktop Mode,
   `flatpak override --user --filesystem=/run/udev:ro com.google.Chrome` (or the
   right application id), then restart it.

### The fallback

**The game is fully playable without any of this.** Every region of the board is
reachable with the D-pad alone — walking into the edge of a region leaves it —
and every action can be taken with Enter and Escape. What you lose is the
sticks, the shoulder shortcuts, and rumble.

Two things make that bearable:

- The **Settings** card lets you set the control scheme to **Gamepad**, so the
  hints read `A`/`B`/`X`/`Y` even when the pad arrives as a keyboard. On a
  handheld the game usually works this out by itself.
- The **Regions** button in the footer opens the region dial, which `L2` would
  otherwise be the only way to reach.

### The hint bar is off by default

The row under the hand that says what `A`, `X`, `Y` and `B` do on the thing
the ring is standing on is a setting, and it starts hidden: it costs a strip
of an 800px screen for the whole game. Open the in-game **Settings** (the gear,
or the `Menu` button) and flip **Button hints** under *Controls*. The buttons
that never change -- move, region, decide -- are listed there too. The
**`L2` Regions** button beside the bar goes with it: hidden by default, shown
when the hints are on. Holding `L2` still opens the region dial either way.

`L2` pressed is *decide*, everywhere: on the board it jumps the ring to the
button that ends the decision, and over a prompt (a proliferate pick, a
target choice) it jumps to the prompt's primary button. In a pick-several
prompt, `A` on a card picks it and steps the ring to the next one, so
choosing three is `A A A`, then Confirm.

Holding `R2` stands you at an opponent's seat, and letting go brings your own
board back. Each press reads the next opponent in seat order, wrapping, so
press, release, press is the first opponent, your board, the second opponent.

### The keys, if you would rather bind them yourself

Point a Steam keyboard layout at these and every control works:

| Button    | Key                     |
| --------- | ----------------------- |
| D-pad     | arrow keys, or `W A S D` |
| A         | `Enter` (or `J`)        |
| B         | `Escape` (or `K`)       |
| X         | `X`                     |
| Y         | `I`                     |
| L1 / R1   | `[` / `]`, or `PageUp` / `PageDown` |
| L2 / R2   | `Z` / `V`               |
| View      | `Tab`                   |
| Menu      | `\`                     |

The board keeps its own shortcuts alongside these: `Space` passes, `1`–`9` play
the nth card in hand, `U` undoes, and `G` / `E` / `C` peek at the graveyard,
exile and command zone.

`X` is the one worth knowing on a controller. It is the secondary button, it
does nothing on most of the board, and it presses whatever the turn is waiting
on you for without walking to the rail first:

| when | `X` does |
| --- | --- |
| a priority window | Pass |
| declaring attackers, nothing sent yet | All attack |
| ...and once something is | Attack |
| declaring blockers, nothing blocking yet | All defend |
| ...and once something is | Block |

So a whole combat is two presses from wherever you are standing, and the first
one only *stages* — nothing is committed until the second, and the hint bar
changes from `All attack` to `Attack` to tell you which one you are on. It says
nothing for `X` when there is nothing worth pressing, which is its way of saying
the decision is yours to make on the board.

Where `X` already means something — activating an ability on a card you could
also cast, re-aiming a staged attacker at a different opponent — it keeps
meaning that.

## How it is put together

For the design and its reasons — why the server runs on the device, why online
play goes to the site, why an update never restarts the app — see
[adr/0009-offline-first-desktop.md](adr/0009-offline-first-desktop.md). For
building and releasing it, [deployment.md](deployment.md#desktop-releases) and
[`desktop/README.md`](../desktop/README.md).
