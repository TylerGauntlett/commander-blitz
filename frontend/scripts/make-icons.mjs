/**
 * Every brand raster in `public/`, rendered from `public/favicon.svg`.
 *
 * Run with `npm run icons`. The outputs are committed, because the Docker build
 * runs `vite build` against the repo as it stands and has no icon step -- Vite
 * copies `public/` verbatim into `dist/`, and the server hands back any real
 * file inside `dist` as itself.
 *
 * Chromium does the rasterising. It is already here as a Playwright dependency
 * for the e2e suite, so this costs nothing new; the alternative was adding an
 * image library to a project that needs one for six files. It also means the
 * icons are drawn by the same engine that will draw them in a tab.
 *
 * Determinism: re-running must not dirty the tree, so nothing here reads a
 * clock or a random source and every size is pinned. The one soft spot is the
 * OG card's type, which resolves "Segoe UI" from the host -- regenerate that
 * one on Windows, or accept the fallback face.
 */

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const PUBLIC = join(dirname(fileURLToPath(import.meta.url)), "..", "public");

/**
 * `--steam`: the Steam library artwork instead, into `desktop/steam/grid/`.
 *
 * Five rasters at the sizes Steam's library draws for a non-Steam shortcut --
 * the portrait capsule, the wide capsule, the hero banner, the transparent
 * logo over it, and the icon -- composed from the same mark and wordmark as
 * the OG card, so the library tile is the front door. `install.sh` copies
 * them into Steam's `grid/` under the shortcut's app id.
 */
const STEAM = process.argv.includes("--steam");
const GRID = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "desktop",
  "steam",
  "grid",
);

/** The ground the mark sits on: `--void-0`. */
const VOID = "#0b0a16";
const GOLD = "#ffd479";

/** The sizes packed into `favicon.ico`. 48 is what Windows uses for shortcuts. */
const ICO_SIZES = [16, 32, 48];

/**
 * Android masks a maskable icon to whatever shape the launcher likes, and only
 * the middle 80% is guaranteed to survive. The whole mark -- frame included --
 * is scaled into that safe circle rather than cropped by it.
 */
const MASKABLE_SCALE = 0.64;

async function main() {
  const svg = await readFile(join(PUBLIC, "favicon.svg"), "utf8");
  const src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;

  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 1 });

  /**
   * `transparent`: keep the alpha. Without it the page's white canvas is the
   * ground, which is how the Steam logo shipped as a white box with a gold glow
   * on it and the icon shipped with white corners outside its radius.
   */
  const shot = async (html, width, height, { transparent = false } = {}) => {
    await page.setViewportSize({ width, height });
    await page.setContent(
      `<style>html,body{margin:0;padding:0;width:${width}px;height:${height}px;overflow:hidden}</style>${html}`,
    );
    // The mark is one inline SVG with no network fetch, but the page still has
    // to lay out and paint before the pixels exist.
    await page.waitForLoadState("load");
    return page.screenshot({ type: "png", omitBackground: transparent });
  };

  /** The mark, edge to edge. */
  const plain = (size, opts) =>
    shot(`<img src="${src}" width="${size}" height="${size}" alt="">`, size, size, opts);

  const write = async (name, buffer) => {
    await writeFile(join(PUBLIC, name), buffer);
    console.log(`${name.padEnd(24)} ${buffer.length.toLocaleString()} bytes`);
  };

  if (STEAM) {
    await mkdir(GRID, { recursive: true });
    const grid = async (name, buffer) => {
      await writeFile(join(GRID, name), buffer);
      console.log(`${name.padEnd(24)} ${buffer.length.toLocaleString()} bytes`);
    };
    const room = await readRoom();
    await grid("portrait.png", await shot(portrait(room), 600, 900));
    await grid("header.png", await shot(wide(src, room, 920, 430), 920, 430));
    await grid("hero.png", await shot(hero(room), 1920, 620));
    await grid("logo.png", await shot(logo(), 1280, 420, { transparent: true }));
    await grid("icon.png", await plain(256, { transparent: true }));
    await browser.close();
    return;
  }

  // `favicon.ico` -- the address a browser asks for whether or not the document
  // links one, which is why it exists at all in a page that also ships an SVG.
  const frames = [];
  for (const size of ICO_SIZES) frames.push(await plain(size));
  await write("favicon.ico", packIco(ICO_SIZES, frames));

  // iOS ignores the manifest and reads this one. It also composites no alpha,
  // so the icon has to carry its own ground -- which the mark does already.
  await write("apple-touch-icon.png", await plain(180));
  await write("icon-192.png", await plain(192));
  await write("icon-512.png", await plain(512));

  await write(
    "icon-512-maskable.png",
    await shot(
      `<div style="width:512px;height:512px;background:${VOID};display:grid;place-items:center">
         <img src="${src}" width="${Math.round(512 * MASKABLE_SCALE)}" alt="">
       </div>`,
      512,
      512,
    ),
  );

  await write("og.png", await shot(ogCard(src, await readRoom()), 1200, 630));

  await browser.close();
}

/**
 * The social preview, 1200x630: the Steam hero's room, cropped to a link card.
 *
 * The mark and the stacked wordmark hold the left half; the doorway stands in
 * the lit ring on the right, as on the hero banner and the portrait capsule, so
 * a link unfurled in Discord shows the same front door as the Steam library.
 */
function ogCard(src, room) {
  return `<div style="width:1200px;height:630px;position:relative;overflow:hidden">
    ${roomSvg(room, 1200, 630, {
      ySlice: "YMin",
      sigil: { x: 880, y: 545, s: 1.1 },
      door: { x: 880, y: 545, s: 2.7 },
      scale: 1.2,
    })}
    <div style="position:absolute;left:90px;top:0;bottom:0;display:flex;flex-direction:column;
        justify-content:center;align-items:flex-start;gap:34px;font-family:${FONT};">
      <img src="${src}" width="112" height="112" alt="">
      ${wordmark(76, "text-align:left;text-indent:0")}
    </div>
  </div>`;
}

const FONT = "'Segoe UI',Inter,system-ui,-apple-system,sans-serif";

/** The wordmark: two lines, tracked, gold -- the OG card's, at a given size. */
function wordmark(size, extra = "") {
  return `<div style="
      font-size:${size}px;font-weight:800;line-height:0.95;letter-spacing:0.14em;
      text-transform:uppercase;color:${GOLD};text-align:center;
      text-shadow:0 0 ${Math.round(size * 0.7)}px rgb(255 212 121 / 0.22);
      text-indent:0.14em;${extra}">
    <div>Commander</div>
    <div>Blitz</div>
  </div>`;
}

/**
 * The front door's room, lifted out of `doorArt.tsx` rather than restated.
 *
 * The hall (sky, beams, vignette), the sigil cut into its floor, and the open
 * doorway from the Join card are module constants there, and that file is the
 * one place their geometry lives. It is TSX and this is plain Node, so the
 * strings are read out of the source by name; a rename there fails loudly here
 * rather than drawing an empty room.
 */
async function readRoom() {
  const file = join(
    dirname(fileURLToPath(import.meta.url)),
    "..",
    "src",
    "components",
    "lobby",
    "doorArt.tsx",
  );
  const source = await readFile(file, "utf8");
  const lift = (pattern, name) => {
    const found = source.match(pattern);
    if (!found) throw new Error(`make-icons: no ${name} in doorArt.tsx`);
    return found[1];
  };
  return {
    ground: lift(/const GROUND = `([\s\S]*?)`;/, "GROUND"),
    floor: lift(/const FLOOR = `([\s\S]*?)`;/, "FLOOR"),
    door: lift(/\n {2}join: `([\s\S]*?)`,/, "CARD_ART.join"),
  };
}

/**
 * What `room.css` gives those classes on the door with no card selected -- the
 * room's resting colour, since there is no `--lit` here to inherit.
 */
const ROOM_STYLE = `<style>
  .room__beam { fill: rgb(195 182 255 / 0.12); }
  .room__sigil { stroke: ${GOLD}; opacity: 0.34; }
  .room__sigil--glow { opacity: 0.16; filter: blur(3px); }
</style>`;

/**
 * Specks of the door's motes (`ambience.css`), frozen. Fixed positions, as
 * fractions of the frame, so a re-run draws the same pixels.
 */
const MOTES = [
  [0.12, 0.62, 2.2, 0.5],
  [0.21, 0.34, 1.4, 0.35],
  [0.33, 0.71, 1.8, 0.4],
  [0.41, 0.22, 1.2, 0.3],
  [0.48, 0.55, 2.6, 0.45],
  [0.57, 0.38, 1.5, 0.35],
  [0.64, 0.78, 2, 0.4],
  [0.72, 0.18, 1.3, 0.3],
  [0.79, 0.49, 2.4, 0.5],
  [0.86, 0.66, 1.6, 0.35],
  [0.92, 0.29, 1.9, 0.4],
  [0.06, 0.41, 1.5, 0.3],
  [0.27, 0.86, 1.3, 0.3],
  [0.68, 0.58, 1.2, 0.3],
  [0.53, 0.12, 1.7, 0.35],
];

/**
 * The room as one SVG at the frame's own size.
 *
 * The hall `slice`s to the frame the way `RoomGround` does on the door; `ySlice`
 * picks which band of it survives a frame wider than 16:10. The sigil and the
 * doorway are placed independently: `sigil` is where the ring's centre lands and
 * its scale, `door` is where the doorway's threshold lands -- so the door stands
 * in the ring the way the menu cards stand on it.
 */
function roomSvg(room, width, height, { ySlice = "YMid", sigil, door, scale = 1 }) {
  const place = (x, y, s, ox, oy) => `translate(${x - ox * s} ${y - oy * s}) scale(${s})`;
  const motes = MOTES.map(
    ([fx, fy, r, a]) =>
      `<circle cx="${fx * width}" cy="${fy * height}" r="${r * scale}" fill="${GOLD}" fill-opacity="${a}"/>`,
  ).join("");
  return `${ROOM_STYLE}
    <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"
         viewBox="0 0 ${width} ${height}" style="display:block">
      <defs>
        <filter id="s-mote" x="-200%" y="-200%" width="500%" height="500%">
          <feGaussianBlur stdDeviation="${1.2 * scale}"/>
        </filter>
      </defs>
      <svg width="${width}" height="${height}" viewBox="0 0 1280 800"
           preserveAspectRatio="xMid${ySlice} slice">${room.ground}</svg>
      <g transform="${place(sigil.x, sigil.y, sigil.s, 640, 585)}">${room.floor}</g>
      ${door ? `<g transform="${place(door.x, door.y, door.s, 100, 132)}">${room.door}</g>` : ""}
      <g filter="url(#s-mote)">${motes}</g>
    </svg>`;
}

/**
 * The portrait capsule, 600x900: the door's room, the wordmark in the sky
 * above the doorway. The doorway standing in the lit ring is the whole front
 * door in one picture; the title sits clear of it in the band the beams fall
 * from, sized so the tracked "COMMANDER" keeps a margin inside 600px.
 */
function portrait(room) {
  return `<div style="width:600px;height:900px;position:relative;overflow:hidden">
    ${roomSvg(room, 600, 900, {
      sigil: { x: 300, y: 700, s: 0.9 },
      door: { x: 300, y: 700, s: 2.5 },
    })}
    <div style="position:absolute;left:0;right:0;top:110px;display:flex;justify-content:center;
        font-family:${FONT};">
      ${wordmark(58)}
    </div>
  </div>`;
}

/**
 * The wide capsule: the mark and the stacked wordmark, over the room.
 *
 * The wordmark is sized to the frame rather than the frame's height: at 20% of
 * 430 the tracked "COMMANDER" ran off both edges.
 */
function wide(src, room, width, height) {
  return `<div style="width:${width}px;height:${height}px;position:relative;overflow:hidden">
    ${roomSvg(room, width, height, {
      sigil: { x: width / 2, y: height * 0.9, s: 0.75 },
      scale: 0.8,
    })}
    <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
        gap:36px;font-family:${FONT};">
      <img src="${src}" width="150" height="150" alt="">
      ${wordmark(62, "text-align:left;text-indent:0")}
    </div>
  </div>`;
}

/**
 * The hero banner, 1920x620: the door's room, with its doorway standing in the
 * ring at the right. The left half is left as dark hall so the logo Steam draws
 * over it has somewhere to sit; the sky band is kept (`YMin`) because a slice
 * from the middle would be all floor.
 */
function hero(room) {
  return `<div style="width:1920px;height:620px;overflow:hidden">
    ${roomSvg(room, 1920, 620, {
      ySlice: "YMin",
      sigil: { x: 1440, y: 540, s: 1.45 },
      door: { x: 1440, y: 540, s: 3.1 },
      scale: 1.6,
    })}
  </div>`;
}

/**
 * The logo, transparent, 1280x420: the wordmark and nothing else. The second
 * shadow is dark, so the gold still separates from a bright patch of whatever
 * hero Steam -- or a user's custom art -- puts behind it.
 */
function logo() {
  return `<div style="width:1280px;height:420px;box-sizing:border-box;display:flex;
      align-items:center;justify-content:center;font-family:${FONT};background:transparent;">
    ${wordmark(132, "filter:drop-shadow(0 4px 14px rgb(0 0 0 / 0.55))")}
  </div>`;
}

/**
 * Pack PNGs into an `.ico`.
 *
 * An ICO is a 6-byte header, one 16-byte directory entry per image, then the
 * images end to end. Since Vista the payload may be a PNG rather than a DIB,
 * which is the only reason this is twenty lines instead of a bitmap encoder.
 */
function packIco(sizes, frames) {
  const HEADER = 6;
  const ENTRY = 16;
  const dir = Buffer.alloc(HEADER + ENTRY * frames.length);
  dir.writeUInt16LE(0, 0); // reserved
  dir.writeUInt16LE(1, 2); // 1 = icon
  dir.writeUInt16LE(frames.length, 4);

  let offset = dir.length;
  frames.forEach((png, i) => {
    const at = HEADER + ENTRY * i;
    // 256 is stored as 0: the field is one byte and the format predates the size.
    dir.writeUInt8(sizes[i] % 256, at);
    dir.writeUInt8(sizes[i] % 256, at + 1);
    dir.writeUInt8(0, at + 2); // palette size -- none, it is a PNG
    dir.writeUInt8(0, at + 3); // reserved
    dir.writeUInt16LE(1, at + 4); // colour planes
    dir.writeUInt16LE(32, at + 6); // bits per pixel
    dir.writeUInt32LE(png.length, at + 8);
    dir.writeUInt32LE(offset, at + 12);
    offset += png.length;
  });

  return Buffer.concat([dir, ...frames]);
}

await main();
