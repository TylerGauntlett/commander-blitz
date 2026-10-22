---
id: brand-mark
title: A mark, a wordmark, and the surfaces that carry them
area: brand
effort: M
impact: medium
why: the first impression for a stranger; nothing for the games already being played
depends_on: []
status: proposed
---

## Today

The door's room art, the Steam capsule and hero and the OG card all exist and
are drawn from the same scene, and the board's look is settled by
[ADR 0011](../adr/0011-the-card-is-the-illustration.md): the card is the
illustration, and type is never carried by colour. What is missing is an
identity that holds at every size the project needs: a mark that survives a
favicon and a Steam library icon, a wordmark for the door and the README, and
the rule for how each sits over art it must not fight.

## The change

- The mark and wordmark as SVG under `frontend/public/`, with the Steam
  assets regenerated from them by `frontend/scripts/make-icons.mjs` rather
  than drawn again.
- A short `docs/brand.md` naming the type pair, the signal tokens already in
  `theme.css` that the brand may use, and where the mark may and may not sit
  (never over a card face).
- The splash the desktop shell shows until the sidecar prints READY, the
  game-over screen and the not-found screen, which are the three places a
  player looks at nothing but the brand.
- Store-page material in the README: screenshots per layout mode and a short
  capture of a turn, since the Steam Deck install is the project's front door
  for a stranger.

## Gate

The icon script regenerates every raster from the one SVG with no hand-drawn
file left in `frontend/public/`; the three brand-only screens have stories
under both layout modes; and the legibility spec covers the wordmark
wherever it sits over art.
