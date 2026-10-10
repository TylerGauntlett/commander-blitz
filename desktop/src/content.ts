/**
 * Content packages on disk, and which one is live.
 *
 * A content package is the server, the client and the card data together,
 * versioned as one: `content-<version>.tar.gz` with `manifest.json` at its
 * root. The AppImage carries one inside it (`resources/content/`) and that is
 * what runs on first launch, in place, straight off the read-only mount.
 * Updates land beside it as `content/<version>/` in the per-user directory,
 * and `state.json` says which directory is current and which was current
 * before -- so a package that fails to start can be backed out with a single
 * pointer swap.
 *
 * Every write here is atomic from the outside: a tarball is extracted into a
 * `.partial` directory and renamed into place only once its manifest has been
 * read back, and `state.json` is written to a temporary file and renamed. A
 * crash at any point leaves either the old state or the new, never a mixture.
 *
 * "bundled" is the floor. It is never deleted, because it is inside the
 * AppImage, and it is where a rollback goes when there is nothing newer.
 */

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { mkdir, readdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { pipeline } from "node:stream/promises";
import * as tar from "tar";
import type { Logger } from "./logging.js";

export interface ContentManifest {
  content_version: string;
  app_version: string;
  /** The oldest shell this content runs under. */
  min_shell_version: string;
  /** The tarball's file name on the release. */
  asset: string;
  sha256: string;
  size: number;
  built: string;
}

export const BUNDLED = "bundled";

export interface ContentState {
  current: string;
  previous: string | null;
}

export interface ActiveContent {
  version: string;
  dir: string;
  bundled: boolean;
}

export interface ContentOptions {
  /** `content/` in the per-user directory. */
  root: string;
  /** `resources/content/` inside the AppImage. */
  bundledDir: string;
  statePath: string;
  log: Logger;
}

export class ContentManager {
  private readonly root: string;
  private readonly bundledDir: string;
  private readonly statePath: string;
  private readonly log: Logger;

  constructor(options: ContentOptions) {
    this.root = options.root;
    this.bundledDir = options.bundledDir;
    this.statePath = options.statePath;
    this.log = options.log;
  }

  dirFor(version: string): string {
    return version === BUNDLED ? this.bundledDir : join(this.root, version);
  }

  async state(): Promise<ContentState> {
    try {
      const parsed = JSON.parse(
        await readFile(this.statePath, "utf8"),
      ) as Partial<ContentState>;
      if (typeof parsed.current === "string") {
        return { current: parsed.current, previous: parsed.previous ?? null };
      }
    } catch {
      // No state yet, or unreadable: first launch, or a corrupt file -- and
      // the bundled content is the right answer to both.
    }
    return { current: BUNDLED, previous: null };
  }

  async manifestOf(dir: string): Promise<ContentManifest> {
    return JSON.parse(await readFile(join(dir, "manifest.json"), "utf8")) as ContentManifest;
  }

  /**
   * The content to run. If the current directory has gone missing -- a
   * player cleaned up by hand -- the bundled content is used and the state
   * says so, rather than a launch that fails on a path.
   */
  async current(): Promise<ActiveContent> {
    const state = await this.state();
    if (state.current !== BUNDLED) {
      const dir = this.dirFor(state.current);
      try {
        await stat(join(dir, "manifest.json"));
        return { version: state.current, dir, bundled: false };
      } catch {
        this.log.warn(
          `content: ${state.current} is missing on disk; using the bundled content`,
        );
        await this.writeState({ current: BUNDLED, previous: null });
      }
    }
    const manifest = await this.manifestOf(this.bundledDir);
    return { version: manifest.content_version, dir: this.bundledDir, bundled: true };
  }

  /** Verify, extract and record `tarPath` as `manifest.content_version`. */
  async install(tarPath: string, manifest: ContentManifest): Promise<string> {
    const version = manifest.content_version;
    const digest = await sha256Of(tarPath);
    if (digest !== manifest.sha256) {
      throw new Error(
        `content ${version}: checksum mismatch (${digest} != ${manifest.sha256})`,
      );
    }
    await mkdir(this.root, { recursive: true });
    const partial = join(this.root, `${version}.partial`);
    const final = join(this.root, version);
    await rm(partial, { recursive: true, force: true });
    await mkdir(partial, { recursive: true });
    this.log.info(`content: extracting ${version}`);
    await tar.x({ file: tarPath, cwd: partial, gzip: true });
    const inside = await this.manifestOf(partial);
    if (inside.content_version !== version) {
      await rm(partial, { recursive: true, force: true });
      throw new Error(`content ${version}: the tarball says it is ${inside.content_version}`);
    }
    await rm(final, { recursive: true, force: true });
    await rename(partial, final);
    this.log.info(`content: installed ${version}`);
    return final;
  }

  /** Make `version` current; what was current becomes `previous`. */
  async activate(version: string): Promise<void> {
    const state = await this.state();
    if (state.current === version) return;
    await this.writeState({ current: version, previous: state.current });
    this.log.info(`content: ${version} is current (was ${state.current})`);
  }

  /** Back to `previous`. Returns the version now current. */
  async rollback(): Promise<string> {
    const state = await this.state();
    const target = state.previous ?? BUNDLED;
    await this.writeState({ current: target, previous: null });
    this.log.warn(`content: rolled back from ${state.current} to ${target}`);
    return target;
  }

  /** Delete everything under `root` that is neither current nor previous. */
  async prune(): Promise<string[]> {
    const state = await this.state();
    const keep = new Set([state.current, state.previous].filter(Boolean));
    let entries: string[];
    try {
      entries = await readdir(this.root);
    } catch {
      return [];
    }
    const removed: string[] = [];
    for (const entry of entries) {
      if (keep.has(entry)) continue;
      await rm(join(this.root, entry), { recursive: true, force: true });
      removed.push(entry);
    }
    if (removed.length) this.log.info(`content: pruned ${removed.join(", ")}`);
    return removed;
  }

  private async writeState(state: ContentState): Promise<void> {
    await mkdir(join(this.statePath, ".."), { recursive: true });
    const temp = `${this.statePath}.tmp`;
    await writeFile(temp, JSON.stringify(state, null, 2), "utf8");
    await rename(temp, this.statePath);
  }
}

export async function sha256Of(path: string): Promise<string> {
  const hash = createHash("sha256");
  await pipeline(createReadStream(path), hash);
  return hash.digest("hex");
}
