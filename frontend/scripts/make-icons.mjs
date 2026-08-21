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

import { readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const PUBLIC = join(dirname(fileURLToPath(import.meta.url)), "..", "public");

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

  const shot = async (html, width, height) => {
    await page.setViewportSize({ width, height });
    await page.setContent(
      `<style>html,body{margin:0;padding:0;width:${width}px;height:${height}px;overflow:hidden}</style>${html}`,
    );
    // The mark is one inline SVG with no network fetch, but the page still has
    // to lay out and paint before the pixels exist.
    await page.waitForLoadState("load");
    return page.screenshot({ type: "png" });
  };

  /** The mark, edge to edge. */
  const plain = (size) =>
    shot(`<img src="${src}" width="${size}" height="${size}" alt="">`, size, size);

  const write = async (name, buffer) => {
    await writeFile(join(PUBLIC, name), buffer);
    console.log(`${name.padEnd(24)} ${buffer.length.toLocaleString()} bytes`);
  };

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

  await write("og.png", await shot(ogCard(src), 1200, 630));

  await browser.close();
}

/**
 * The social preview: the front door, cropped to 1200x630.
 *
 * Deliberately not a new composition. The gradient is `body`'s three washes from
 * `theme.css` and the wordmark is the hero's two-line stack, so a link unfurled
 * in Discord shows the page somebody is about to land on.
 */
function ogCard(src) {
  return `<div style="
      width:1200px;height:630px;box-sizing:border-box;
      display:flex;flex-direction:column;align-items:center;justify-content:center;
      font-family:'Segoe UI',Inter,system-ui,-apple-system,sans-serif;
      background:
        radial-gradient(60% 44% at 50% 6%, rgb(143 127 232 / 0.13) 0%, transparent 62%),
        radial-gradient(70% 50% at 50% 100%, rgb(90 190 220 / 0.07) 0%, transparent 60%),
        linear-gradient(180deg, #141328 0%, ${VOID} 62%);">
    <img src="${src}" width="104" height="104" alt="" style="margin-bottom:34px">
    <div style="
        font-size:88px;font-weight:800;line-height:0.95;letter-spacing:0.14em;
        text-transform:uppercase;color:${GOLD};text-align:center;
        text-shadow:0 0 60px rgb(255 212 121 / 0.22);
        /* The tracking is trailing space on the last glyph of each line; without
           the matching indent the stack reads as leaning left. */
        text-indent:0.14em;">
      <div>Commander</div>
      <div>Blitz</div>
    </div>
    <div style="margin-top:38px;font-size:25px;letter-spacing:0.04em;color:#a09bc4">
      Four seats, four cards, all face-down.
    </div>
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
