/**
 * The front door's drawn room, card frame and three illustrations.
 *
 * Ported from the door round's drawn ground (`docs/design-record.md#door`), which argues the case for drawing this
 * rather than fetching it: `art_crop` is 626x457 and it is the only art-only
 * asset published, so any field wider than about 780px is a deliberate blur --
 * and a front door has no card on it yet, so it has nothing to be a crop *of*.
 * Putting Edgar Markov behind "Play" would say the game is about Edgar Markov.
 * A vector ground is exact at 1280x800 and exact again at 2560, which is the
 * whole reason this screen scales past the Deck without softening.
 *
 * ## The room takes the selected card's colour
 *
 * `.room__sigil` is `stroke: var(--lit)` and carries NO `stroke` attribute of
 * its own. A presentation attribute beats an inherited value, so a sigil with a
 * stroke could never be recoloured by the page around it; leaving it unset lets
 * `stroke` inherit -- and inheritance crosses into a `<use>`'s shadow tree, so
 * one CSS declaration retints every ring, spoke and square in here, and
 * transitions while it does. The room is not tinted, it *is* that colour.
 *
 * ## Why `dangerouslySetInnerHTML`
 *
 * Same call `SeatIcon` and `ActionIcon` make, for the same reason: these are
 * module constants, no value from outside ever reaches them, and transcribing
 * four hundred SVG attributes into JSX casing is four hundred chances to get
 * one wrong silently. The `<svg>` element itself stays JSX so the class and the
 * viewBox are readable props.
 *
 * Every colour here is `theme.css`'s: `--void-*` for the ground, `--gold` and
 * `--astral` for what is drawn on it, `--stock-back` for the card field.
 */

/** The 1280x800 backdrop: a lit hall with a sigil cut into the floor. */
const GROUND = `
  <defs>
    <radialGradient id="d-sky" cx="50%" cy="2%" r="70%">
      <stop offset="0" stop-color="#8f7fe8" stop-opacity=".26"/>
      <stop offset=".55" stop-color="#5b4fa8" stop-opacity=".08"/>
      <stop offset="1" stop-color="#8f7fe8" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="d-vig" cx="50%" cy="46%" r="72%">
      <stop offset=".45" stop-color="#000" stop-opacity="0"/>
      <stop offset="1" stop-color="#000" stop-opacity=".72"/>
    </radialGradient>
    <!-- The beams fade out downward. A flat fill would be the right colour and
         the wrong object: three hard-edged translucent slabs. The colour has to
         stay a plain fill so CSS can retint it, so the fade is a mask rather
         than a gradient in the paint. -->
    <linearGradient id="d-fade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fff" stop-opacity="1"/>
      <stop offset=".55" stop-color="#fff" stop-opacity=".35"/>
      <stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>
    <mask id="d-beammask">
      <rect width="1280" height="800" fill="url(#d-fade)"/>
    </mask>
    <!-- The floor fades IN at the top rather than starting: a rect with a solid
         first stop draws a hard horizon line across the room. -->
    <linearGradient id="d-floor" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#1d1b38" stop-opacity="0"/>
      <stop offset=".22" stop-color="#1d1b38" stop-opacity=".7"/>
      <stop offset="1" stop-color="#08070f" stop-opacity="1"/>
    </linearGradient>
  </defs>

  <rect width="1280" height="800" fill="#0b0a16"/>
  <rect y="330" width="1280" height="470" fill="url(#d-floor)"/>
  <rect width="1280" height="800" fill="url(#d-sky)"/>

  <!-- Three shafts of light from somewhere above the frame, skewed rather than
       vertical so the room has a direction. -->
  <g mask="url(#d-beammask)">
    <path class="room__beam" d="M300 0 L470 0 L620 800 L230 800Z" opacity=".62"/>
    <path class="room__beam" d="M900 0 L1010 0 L1100 800 L770 800Z" opacity=".44"/>
    <path class="room__beam" d="M596 0 L684 0 L742 800 L538 800Z" opacity=".5"/>
  </g>

  <rect width="1280" height="800" fill="url(#d-vig)"/>
`;

/**
 * The sigil cut into the floor, on its own layer, and that split is the port's
 * one structural change to the drawing.
 *
 * The hall is full-bleed and `slice`s to the stage, which is right for the sky,
 * the beams and the vignette -- they are gradients and shafts, and stretching
 * them is what they are for. It is wrong for the sigil: on a 2560x1440 monitor
 * `slice` scales the ground 2x while the cards only scale 1.45x, so the ring on
 * the floor grew wider than the row standing in it and the composition came
 * apart in exactly the way a fixed-size mockup could never show.
 *
 * So this layer is sized `1280x800 * --du` and hung off the ROW's top rather
 * than off the stage, which puts the sigil the same distance under the cards at
 * every size -- see `.room__floor` in `room.css` for the two-line arithmetic.
 * Twice: a line, and a fat soft copy under it that reads as the glow it is
 * throwing onto the floor.
 */
const FLOOR = `
  <defs>
    <!-- No "stroke" attribute here, on purpose. See the header. -->
    <g id="d-sigil" fill="none" stroke-width="1.6">
      <circle r="292"/>
      <circle r="268" stroke-dasharray="2 14"/>
      <circle r="196" stroke-width="1"/>
      <circle r="150" stroke-dasharray="26 18"/>
      <circle r="96" stroke-width="1"/>
      <path d="M0-292V-196M0 292V196M-292 0H-196M292 0H196"/>
      <path d="M-206-206 -139-139M206 206 139 139M206-206 139-139M-206 206 -139 139"
            stroke-width="1"/>
      <rect x="-106" y="-106" width="212" height="212" transform="rotate(45)" stroke-width="1"/>
      <rect x="-106" y="-106" width="212" height="212" stroke-width="1"/>
    </g>
  </defs>
  <g class="room__sigil room__sigil--glow" transform="translate(640 585) scale(1.12 .3)" stroke-width="7">
    <use href="#d-sigil"/>
  </g>
  <g class="room__sigil" transform="translate(640 585) scale(1.12 .3)">
    <use href="#d-sigil"/>
  </g>
`;

/**
 * The printed field every card is drawn on.
 *
 * The shipped `.back` is a 135-degree hatch over #443e34, and `lobby.css` is
 * honest about what that is: the plate `cards.css` draws for a card with NO
 * printing. It is a placeholder, and on a screen where three of them are the
 * entire menu it reads as three blank brown rectangles. This is a plum field in
 * the client's own `--stock-back`, a gold rule, corner flourishes, and a lattice
 * too fine to read as content -- which is what makes a menu card look printed
 * rather than styled.
 */
const CARD_FRAME = `
  <defs>
    <linearGradient id="b-field" x1="0" y1="0" x2=".4" y2="1">
      <stop offset="0" stop-color="#332747"/>
      <stop offset=".55" stop-color="#241b32"/>
      <stop offset="1" stop-color="#171021"/>
    </linearGradient>
    <pattern id="b-lattice" width="16" height="16" patternUnits="userSpaceOnUse"
             patternTransform="rotate(45)">
      <path d="M8 0V16M0 8H16" stroke="#ffd479" stroke-opacity=".06" stroke-width="1"/>
      <circle cx="8" cy="8" r="1.6" fill="#ffd479" fill-opacity=".06"/>
    </pattern>
  </defs>

  <rect width="200" height="280" fill="url(#b-field)"/>
  <rect width="200" height="280" fill="url(#b-lattice)"/>

  <!-- Two rules, the outer heavy and the inner a hair, which is how an engraved
       card edge is actually built. -->
  <rect x="6" y="6" width="188" height="268" rx="6" fill="none"
        stroke="#d8a63c" stroke-opacity=".34" stroke-width="1.5"/>

  <!-- Corner flourishes: a quarter-round in each, so the frame has weight where
       an engraved border would have it. -->
  <g fill="none" stroke="#ffd479" stroke-opacity=".22" stroke-width="1.5">
    <path d="M16 34V22a6 6 0 016-6h12"/>
    <path d="M184 34V22a6 6 0 00-6-6h-12"/>
    <path d="M16 246v12a6 6 0 006 6h12"/>
    <path d="M184 246v12a6 6 0 01-6 6h-12"/>
  </g>
`;

/**
 * One illustration per card, and each draws WHAT THAT CARD DOES.
 *
 * A menu card is not a spell and a dragon on it would be decoration pretending
 * to be a card face. What is on these is the shape of the thing behind them -- a
 * table with four seats, a doorway somebody left open, the pad in your hands --
 * so the picture makes the same statement as the word under it, and a player who
 * cannot read the word still knows which is which.
 *
 * All three in one grammar: a gold line on a dark ground, one lit accent, no
 * fills that compete with the frame, and the same viewBox so they sit
 * identically in the window.
 *
 * A SHARED VIEWBOX IS NOT A SHARED COMPOSITION, which is the trap this file
 * fell into. `.door__art` centres the *viewBox* in the window, so drawings with
 * different bounding boxes inside the same 200x150 sit at different heights on
 * otherwise identical cards -- and the eye reads that as the cards being
 * misaligned rather than as the pictures being. Join centres on y=79 and is the
 * line the others were measured against; Play was at 83 and Settings at 97, with
 * 44 units of dead space above it and none below. The two that were out are wrapped in a `<g
 * transform>` rather than redrawn, so the coordinates below still say what the
 * drawing IS and the transform says where it sits. **Anything added here is
 * centred on y=79** -- measure the bounding box, do not eyeball it.
 */
const CARD_ART: Record<string, string> = {
  /* Four seats around a table, the near one yours and lit, a deal in the
     middle. This is literally what pressing it makes. */
  play: `
  <defs>
    <radialGradient id="p-table" cx="50%" cy="46%" r="54%">
      <stop offset="0" stop-color="#ffd479" stop-opacity=".18"/>
      <stop offset="1" stop-color="#ffd479" stop-opacity=".02"/>
    </radialGradient>
  </defs>
  <!-- Centred on y=79 with Join; see the note above. -->
  <g transform="translate(0 -4)">
  <ellipse cx="100" cy="78" rx="72" ry="42" fill="url(#p-table)"
           stroke="#ffd479" stroke-opacity=".5" stroke-width="1.5"/>
  <ellipse cx="100" cy="78" rx="56" ry="31" fill="none"
           stroke="#ffd479" stroke-opacity=".22" stroke-dasharray="4 6"/>

  <!-- Three chairs, and yours. Drawn as the card each seat is holding rather
       than as furniture, because a seat in this game IS a face-down card. -->
  <g stroke="#c3b6ff" stroke-opacity=".55" fill="#1d1b38" fill-opacity=".8">
    <rect x="14" y="62" width="20" height="28" rx="3" transform="rotate(-16 24 76)"/>
    <rect x="90" y="16" width="20" height="28" rx="3"/>
    <rect x="166" y="62" width="20" height="28" rx="3" transform="rotate(16 176 76)"/>
  </g>
  <rect x="86" y="112" width="28" height="38" rx="4" fill="#3a2c18"
        stroke="#ffd479" stroke-width="2"/>
  <path d="M100 122 l-6 9h4l-1.5 9 6-9h-4z" fill="#ffd479" fill-opacity=".9"/>

  <!-- The deal, mid-air over the middle of the table. -->
  <g fill="#2a1f38" stroke="#ffd479" stroke-opacity=".45">
    <rect x="82" y="62" width="17" height="24" rx="2" transform="rotate(-12 90 74)"/>
    <rect x="92" y="58" width="17" height="24" rx="2" transform="rotate(6 100 70)"/>
    <rect x="102" y="62" width="17" height="24" rx="2" transform="rotate(20 110 74)"/>
  </g>
  </g>
`,

  /* A door somebody left open for you, with the light of the room behind it. */
  join: `
  <defs>
    <linearGradient id="j-light" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffd479" stop-opacity=".42"/>
      <stop offset="1" stop-color="#ffd479" stop-opacity=".04"/>
    </linearGradient>
  </defs>
  <!-- The spill on the floor first, so the arch sits on top of it. -->
  <path d="M74 92 L126 92 L168 150 L32 150Z" fill="url(#j-light)" opacity=".55"/>

  <g fill="none" stroke="#c3b6ff" stroke-opacity=".5" stroke-width="1.5">
    <path d="M52 132V56a48 48 0 0196 0v76"/>
    <path d="M44 132h112"/>
  </g>
  <path d="M74 132V60a26 26 0 0152 0v72Z" fill="#ffd479" fill-opacity=".16"
        stroke="#ffd479" stroke-opacity=".6" stroke-width="1.5"/>
  <!-- The keystone, and a ring on the open leaf. -->
  <circle cx="100" cy="34" r="6" fill="none" stroke="#ffd479" stroke-opacity=".6"
          stroke-width="1.5"/>
  <circle cx="116" cy="100" r="4" fill="none" stroke="#ffd479" stroke-opacity=".7"
          stroke-width="1.5"/>
  <g stroke="#ffd479" stroke-opacity=".3" stroke-width="1">
    <path d="M86 60V126M100 56V128M114 60V126"/>
  </g>
`,

  /* A controller, seen flat on. The card is nominally "settings" and is in
     practice about the pad -- the control scheme lives here, and so does the
     answer to "why has my Deck not been detected". So it draws the thing it is
     for rather than a cog, which would have been a picture of a menu. */
  settings: `
  <!-- Centred on y=79 with Join; see the note above. -->
  <g transform="translate(0 -18)">
  <g stroke-width="1.5">
    <!-- The body: two grips under one deck, in the room's cold blue. -->
    <path d="M62 52h76c16 0 27 11 30 26l10 44c4 17-6 28-20 28-10 0-16-5-22-13l-9-12H73l-9 12c-6 8-12 13-22 13-14 0-24-11-20-28l10-44c3-15 14-26 30-26z"
          fill="#1e2f44" stroke="#9fc6ea" stroke-opacity=".6"/>
    <!-- The d-pad, left, drawn as the cross a Deck actually has. -->
    <path d="M62 88h10V78h12v10h10v12H84v10H72v-10H62z"
          fill="#0f1b28" stroke="#9fc6ea" stroke-opacity=".5"/>
  </g>
  <!-- The four face buttons, right, lettered the way this app labels them. -->
  <g fill="#0f1b28" stroke="#ffd479" stroke-opacity=".55" stroke-width="1.5">
    <circle cx="139" cy="80" r="7"/>
    <circle cx="126" cy="93" r="7"/>
    <circle cx="152" cy="93" r="7"/>
    <circle cx="139" cy="106" r="7"/>
  </g>
  <!-- Both sticks, resting centred. -->
  <g fill="#25384f" stroke="#9fc6ea" stroke-opacity=".45" stroke-width="1.5">
    <circle cx="82" cy="118" r="9"/>
    <circle cx="118" cy="118" r="9"/>
  </g>
  <!-- The shoulders, which are the buttons a Steam Deck most often loses. -->
  <g stroke="#9fc6ea" stroke-opacity=".4" stroke-width="2" fill="none">
    <path d="M74 50c-6-6-14-8-22-5"/>
    <path d="M126 50c6-6 14-8 22-5"/>
  </g>
  </g>
`,
};

/**
 * The hall.
 *
 * `slice` so it fills the stage at any aspect without letterboxing, and
 * deliberately NOT `will-change`: on a static backdrop, promoting to a
 * compositor layer throws away the raster cache that was already doing the job,
 * which cost the mockup round half its frame rate before it was found.
 */
export function RoomGround() {
  return (
    <svg
      className="room__ground"
      viewBox="0 0 1280 800"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
      // biome-ignore lint/security/noDangerouslySetInnerHtml: a module constant; see the header.
      dangerouslySetInnerHTML={{ __html: GROUND }}
    />
  );
}

/**
 * The floor the row stands on. Sized off `--du` rather than off the stage, so
 * the sigil is the same size relative to a card at 1280x800 and at 2560x1440.
 */
export function RoomFloor() {
  return (
    <svg
      className="room__floor"
      viewBox="0 0 1280 800"
      aria-hidden="true"
      focusable="false"
      // biome-ignore lint/security/noDangerouslySetInnerHtml: a module constant; see the header.
      dangerouslySetInnerHTML={{ __html: FLOOR }}
    />
  );
}

/** The printed field, under everything, filling a `.plank`. */
export function DoorCardFrame() {
  return (
    <svg
      className="plank__frame"
      viewBox="0 0 200 280"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
      // biome-ignore lint/security/noDangerouslySetInnerHtml: a module constant; see the header.
      dangerouslySetInnerHTML={{ __html: CARD_FRAME }}
    />
  );
}

/** One card's illustration. `id` is a `DOOR_CARDS` id, never anything typed. */
export function DoorCardArt({ id }: { id: string }) {
  return (
    <svg
      className="door__art"
      viewBox="0 0 200 150"
      aria-hidden="true"
      focusable="false"
      // biome-ignore lint/security/noDangerouslySetInnerHtml: a module constant looked up by a closed union; see the header.
      dangerouslySetInnerHTML={{ __html: CARD_ART[id] ?? "" }}
    />
  );
}
