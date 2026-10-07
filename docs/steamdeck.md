# Playing on a Steam Deck

The game is built for this device — 1280×800 is the size every layout was
measured at, and the whole controller layer exists for it. Getting there needs a
few minutes of setup, because **in gaming mode a Steam Deck hands a browser a
keyboard rather than a gamepad**.

## The symptom

Only the D-pad and A do anything. The sticks are dead, the shoulder buttons do
nothing, and the hint bar (if you have turned it on) says `Enter` and `Esc`
instead of `A` and `B`.

That is Steam Input working as designed. Steam applies a controller layout to
every non-Steam shortcut, and it recognises browsers and picks a *keyboard and
mouse* template for them. Under that template Steam takes the controller
exclusively and publishes no gamepad at all, so `navigator.getGamepads()` is
empty while the D-pad arrives as arrow keys and A arrives as Enter.

The game is still playable in that state — see [the fallback](#the-fallback) —
but the sticks cannot work, because nothing is sending them.

## The fix, in the order worth trying

### 1. Serve the game over https (or localhost)

**Check this first.** The Gamepad API is secure-context only: over plain `http://`
to anything but `localhost`, `navigator.getGamepads` *does not exist*, and no
amount of Steam configuration will help. Opening the dev server by LAN address —
`http://192.168.1.x:5173`, which is exactly how you would test on a handheld — is
the single most common cause, and it is invisible because the same URL works
perfectly on the machine serving it.

Use an https tunnel, or run the server on the Deck itself and use `localhost`.

### 2. Set the layout template to Gamepad

In gaming mode, select the shortcut → the controller icon → **Controller
settings** → **Templates** → **Gamepad**.

This stops Steam translating the pad into keystrokes and lets it through as a
standard gamepad. Analog sticks start working the moment it takes effect.

### 3. If the browser is a Flatpak, let it reach the device

A browser installed from Discover is sandboxed away from the hardware, and the
Gamepad API stays dead *even with a gamepad layout*. In Desktop Mode:

```bash
flatpak override --user --filesystem=/run/udev:ro com.google.Chrome
```

Substitute the right application id for another browser
(`org.mozilla.firefox`, `com.brave.Browser`, …). Restart the browser afterwards.

## Checking whether it worked

Open the **Settings** card on the front door. It lists every controller the
browser can see, and when it can see none it names which of the causes above
applies. That panel is the fastest way to tell "the game is broken" from "the
environment has not been set up", which from inside the game look identical.

## The fallback

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
that never change -- move, region, decide -- are listed there too.

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
