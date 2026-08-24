/*
 * The art, drawn rather than fetched.
 *
 * NOT LOADED BY THE MOCKUPS. `inline.py` splices this into each file between
 * its BEGIN/END `_art.js` markers, same as the other masters.
 *
 * ---------------------------------------------------------------------------
 * WHY IT IS DRAWN, AND WHY THAT IS NOT A COMPROMISE.
 *
 * The rest of this folder has one hard art constraint, established in
 * `../menu/README.md` and inherited by everything since: **Scryfall's
 * `art_crop` is 626x457 and it is the only art-only asset published**, so any
 * field wider than about 780px is a deliberate blur with something crisp on top
 * of it. `05-the-lantern.html` is built entirely around working within it.
 *
 * A front door has no card on it yet, so it has nothing to be a crop OF -- and
 * dressing the menu in somebody's commander would be the screen claiming a
 * deck it has not been given. Putting Edgar Markov behind "Play" says the game
 * is about Edgar Markov.
 *
 * So this round draws its own, in SVG, and the constraint stops applying: a
 * vector ground is exact at 1280x800 and exact again at 2560, there is nothing
 * to upscale and nothing to blur on purpose. It is also the only kind of asset
 * that can be inlined -- these files open from `file://` with no network, and a
 * mockup that needs a folder of PNGs beside it is one a reviewer can lose half
 * of.
 *
 * WHAT IS HERE:
 *
 *   GROUND       the 1280x800 backdrop: a lit hall with a sigil on the floor.
 *                THE SIGIL AND THE BEAMS TAKE THEIR COLOUR FROM CSS, not from
 *                an attribute, which is what lets the room change colour with
 *                the selection. `05-the-lantern.html` established that idea
 *                over a photograph; drawn art can go further, because a line
 *                can be recoloured and a photograph can only be washed over.
 *   CARD_FRAME   the printed field a card is drawn on -- the same on all three
 *   CARD_ART[]   one illustration per menu card, and each draws the thing that
 *                card DOES rather than a picture of a spell
 *
 * ---------------------------------------------------------------------------
 * NO BACKTICKS BELOW THIS LINE. Every asset here is a template literal, so a
 * backtick anywhere inside one -- including inside an SVG comment quoting a CSS
 * property, which is exactly how it happened twice -- ends the string early and
 * the file stops parsing. The failure is a `SyntaxError` naming whatever word
 * came next, which points nowhere near the quote that caused it. Quote things
 * with "double quotes" in here.
 *
 * The palette is `theme.css`'s and nothing here invents a colour: `--void-*`
 * for the ground, `--gold` and `--astral` for everything drawn on it,
 * `--stock-back` (#2a1f38) for the card back, which is the tone the shipped
 * client already uses for the back of a card.
 */

/*
 * The ground.
 *
 * Three things, in the order they are painted: light from above, a sigil cut
 * into the floor, and the pool of light the cards stand in. Deliberately almost
 * monochrome -- everything on this screen that carries information is gold, and
 * a backdrop competing for that channel is the mistake `05` is here to
 * demonstrate. Nothing below is above 14% opacity.
 *
 * `preserveAspectRatio="slice"` so it fills the deck at any scale without
 * letterboxing; the sigil is centred on the card row rather than on the screen,
 * because it is meant to read as the thing the cards are standing on.
 */
const GROUND = `
<svg class="ground" viewBox="0 0 1280 800" preserveAspectRatio="xMidYMid slice"
     aria-hidden="true" focusable="false">
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
         the wrong object: two hard-edged translucent slabs, which is what they
         were until this was added. The colour has to stay a plain fill so CSS
         can retint it, so the fade is a mask instead of a gradient in the
         paint. -->
    <linearGradient id="d-fade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fff" stop-opacity="1"/>
      <stop offset=".55" stop-color="#fff" stop-opacity=".35"/>
      <stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>
    <mask id="d-beammask">
      <rect width="1280" height="800" fill="url(#d-fade)"/>
    </mask>
    <!-- The floor. It fades IN at the top rather than starting: a rect with a
         solid first stop draws a hard horizon line across the room, which is
         what this was and what it looked like. -->
    <linearGradient id="d-floor" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#1d1b38" stop-opacity="0"/>
      <stop offset=".22" stop-color="#1d1b38" stop-opacity=".7"/>
      <stop offset="1" stop-color="#08070f" stop-opacity="1"/>
    </linearGradient>
    <!-- The sigil is one group used twice, once as a line and once as a halo.
         IT CARRIES NO "stroke" ATTRIBUTE ON PURPOSE. A presentation attribute
         beats an inherited value, so a sigil with a stroke of its own
         could never be recoloured by the page around it. Leaving it unset lets
         "stroke" inherit from the "use" -- and an inherited property crosses
         into a shadow tree, so one CSS declaration retints every ring, spoke
         and square in here, and transitions while it does. -->
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

  <rect width="1280" height="800" fill="#0b0a16"/>
  <rect y="330" width="1280" height="470" fill="url(#d-floor)"/>
  <rect width="1280" height="800" fill="url(#d-sky)"/>

  <!-- Two shafts of light from somewhere above the frame. Skewed rather than
       vertical so the room has a direction. -->
  <g mask="url(#d-beammask)">
    <path class="beam" d="M300 0 L470 0 L620 800 L230 800Z" opacity=".62"/>
    <path class="beam" d="M900 0 L1010 0 L1100 800 L770 800Z" opacity=".44"/>
    <path class="beam" d="M596 0 L684 0 L742 800 L538 800Z" opacity=".5"/>
  </g>

  <!-- The floor sigil, flattened into perspective and centred under the row.
       Twice: a line, and a fat soft copy under it that reads as the glow it is
       throwing onto the floor. -->
  <g class="sigil sigil--glow" transform="translate(640 585) scale(1.12 .3)" stroke-width="7">
    <use href="#d-sigil"/>
  </g>
  <g class="sigil" transform="translate(640 585) scale(1.12 .3)">
    <use href="#d-sigil"/>
  </g>

  <rect width="1280" height="800" fill="url(#d-vig)"/>
</svg>`;

/*
 * The printed field every card is drawn on.
 *
 * This began as the BACK of a card, for a version of this direction where the
 * two you were not on were face-down and the one you were on turned over. The
 * turn is gone -- see the note in `01-the-hand.html` -- and what it was drawn
 * on turns out to be worth more as the FRONT: a plum field in the client's own
 * `--stock-back`, a gold rule inside a gold border, corner flourishes, and a
 * lattice too fine to read as content.
 *
 * It is what makes a menu card look printed rather than styled. The shipped
 * `.back` is a 135-degree hatch over #443e34, and `lobby.css` is honest about
 * what that is: the plate `cards.css` draws for a card with NO PRINTING. It is
 * a placeholder, and on a screen where three of them are the entire menu it
 * reads as three blank brown rectangles.
 *
 * No medallion any more, because the illustration sits where it was. Nothing in
 * here is information and `assert.js` never sees a word of it, because there is
 * not one.
 */
const CARD_FRAME = `
<svg class="cardframe" viewBox="0 0 200 280" preserveAspectRatio="none"
     aria-hidden="true" focusable="false">
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
</svg>`;

/*
 * One illustration per card, and each one draws WHAT THE CARD DOES.
 *
 * A menu card is not a spell and a picture of a dragon on it would be
 * decoration pretending to be a card face. What is on these is the shape of the
 * thing behind them -- a table with four seats, a doorway somebody left open, a
 * shelf of decks -- so the picture is the same statement as the word under it
 * and a player who cannot read the word still knows which is which.
 *
 * All three are drawn in one grammar: a gold line on a dark ground, one lit
 * accent, no fills that compete with the frame. `viewBox` is the same on all
 * three so they sit identically in the window.
 */
const CARD_ART = {
  /* Four seats around a table, the near one yours and lit, a deal in the
     middle. This is literally what pressing it makes. */
  play: `
<svg class="cardart" viewBox="0 0 200 150" aria-hidden="true" focusable="false">
  <defs>
    <radialGradient id="p-table" cx="50%" cy="46%" r="54%">
      <stop offset="0" stop-color="#ffd479" stop-opacity=".18"/>
      <stop offset="1" stop-color="#ffd479" stop-opacity=".02"/>
    </radialGradient>
  </defs>
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
</svg>`,

  /* A door somebody left open for you, with the light of the room behind it.
     `flow/02-face-up` made the argument this borrows: an open chair and an
     invitation are one picture. */
  join: `
<svg class="cardart" viewBox="0 0 200 150" aria-hidden="true" focusable="false">
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
</svg>`,

  /* A shelf of decks, faced with their art windows and edged in colour --
     which is `menu/02-deck-rack`'s object, drawn small. The gap on the right is
     that round's idea too: dashed means not-here, and a deck you have not
     imported is the purest not-here there is. */
  decks: `
<svg class="cardart" viewBox="0 0 200 150" aria-hidden="true" focusable="false">
  <g stroke-width="1.5">
    <rect x="26" y="34" width="26" height="94" rx="3" fill="#1f3a34" stroke="#9bd3ab" stroke-opacity=".6"/>
    <rect x="56" y="26" width="26" height="102" rx="3" fill="#2b2140" stroke="#c3b6ff" stroke-opacity=".6"/>
    <rect x="86" y="32" width="26" height="96" rx="3" fill="#3a2320" stroke="#f9aa8f" stroke-opacity=".6"/>
    <rect x="116" y="24" width="26" height="104" rx="3" fill="#2b3348" stroke="#aae0fa" stroke-opacity=".6"/>
    <rect x="146" y="36" width="26" height="92" rx="3" fill="none"
          stroke="#ffd479" stroke-opacity=".45" stroke-dasharray="5 5"/>
  </g>
  <!-- The art window on each face. -->
  <g fill="#ffd479" fill-opacity=".18">
    <rect x="31" y="42" width="16" height="20" rx="2"/>
    <rect x="61" y="34" width="16" height="20" rx="2"/>
    <rect x="91" y="40" width="16" height="20" rx="2"/>
    <rect x="121" y="32" width="16" height="20" rx="2"/>
  </g>
  <!-- The shelf. -->
  <path d="M18 128h164" stroke="#ffd479" stroke-opacity=".5" stroke-width="2"/>
  <path d="M24 134h152" stroke="#ffd479" stroke-opacity=".2" stroke-width="1"/>
</svg>`,
};
