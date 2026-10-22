/**
 * Put a content package together: `build/content/{manifest.json, server/,
 * client/, data/}`, and optionally the tarball and `content-latest.json`.
 *
 *   node scripts/assemble-content.mjs --version 1.2.3 \
 *     --server ../desktop/sidecar/build/server/commanderblitz-server \
 *     --client ../frontend/dist --data ../data [--tar]
 *
 * `data/` is copied without what the server never reads at runtime:
 * `generated/` (per-user, written at runtime), `authoring/` (the card
 * pipeline's working files), `catalog/bulk/` (the Scryfall dump the index
 * was built from; `cards.sqlite` is the index) and `art_store/` (the crawled
 * catalog art, which a Deck asks the site for instead -- ADR 0021). The checksum and size in the
 * manifest describe the tarball, so with `--tar` the manifest inside the
 * directory is written first (with the version), the tarball is made from
 * it, and `content-latest.json` beside the tarball carries the final hash.
 */

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { cp, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pipeline } from "node:stream/promises";
import * as tar from "tar";

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  if (i < 0 || i + 1 >= process.argv.length) {
    if (fallback !== undefined) return fallback;
    throw new Error(`missing --${name}`);
  }
  return process.argv[i + 1];
}

const pkg = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
const version = arg("version", pkg.version);
const server = resolve(arg("server"));
const client = resolve(arg("client"));
const data = resolve(arg("data"));
const out = resolve(arg("out", "build"));
const makeTar = process.argv.includes("--tar");
const minShell = arg("min-shell", pkg.version);

const content = join(out, "content");
await rm(content, { recursive: true, force: true });
await mkdir(content, { recursive: true });

console.log(`server  ${server}`);
await cp(server, join(content, "server"), { recursive: true });
console.log(`client  ${client}`);
await cp(client, join(content, "client"), { recursive: true });
console.log(`data    ${data}`);
await cp(data, join(content, "data"), {
  recursive: true,
  filter: (source) => {
    const rel = source.slice(data.length).replace(/\\/g, "/");
    return !(
      rel.startsWith("/generated") ||
      rel.startsWith("/authoring") ||
      rel.startsWith("/catalog/bulk") ||
      rel.startsWith("/art_store")
    );
  },
});

const manifest = {
  content_version: version,
  app_version: pkg.version,
  min_shell_version: minShell,
  asset: `content-${version}.tar.gz`,
  sha256: "",
  size: 0,
  built: new Date().toISOString(),
};
await writeFile(join(content, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`content ${content} (${version})`);

if (makeTar) {
  const file = join(out, manifest.asset);
  await tar.c({ gzip: true, file, cwd: content, portable: true }, ["."]);
  const hash = createHash("sha256");
  await pipeline(createReadStream(file), hash);
  manifest.sha256 = hash.digest("hex");
  manifest.size = (await stat(file)).size;
  await writeFile(join(out, "content-latest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`tarball ${file} ${manifest.size} bytes sha256 ${manifest.sha256}`);
}
