/**
 * Finding and fetching a newer content package.
 *
 * `content-latest.json` on the latest release is the manifest of the newest
 * content package. The check reads it, compares versions, and says one of
 * three things: nothing newer, something newer this shell can run, or
 * something newer that needs a newer shell first (`min_shell_version`). The
 * download streams the tarball into `downloads/`, hands it to
 * `ContentManager.install`, and deletes it.
 *
 * Nothing here applies an update. Applying is a restart of the server, and
 * when that happens is the banner's decision (never mid-game), not this
 * module's.
 */

import { createWriteStream } from "node:fs";
import { mkdir, rm } from "node:fs/promises";
import { join } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import type { ContentManager, ContentManifest } from "./content.js";
import type { Logger } from "./logging.js";
import { compareVersions, satisfiesMin } from "./version.js";

export type Verdict =
  | { kind: "none"; manifest: ContentManifest | null }
  | { kind: "available"; manifest: ContentManifest }
  | { kind: "needs-shell"; manifest: ContentManifest };

export interface UpdaterOptions {
  /** `https://github.com/<owner>/<repo>/releases/latest/download` */
  releasesBase: string;
  shellVersion: string;
  content: ContentManager;
  downloadsDir: string;
  log: Logger;
  fetch?: typeof fetch;
}

/** After the server is healthy, and then on this cadence. */
export const FIRST_CHECK_MS = 20_000;
export const CHECK_EVERY_MS = 6 * 60 * 60 * 1000;

export class ContentUpdater {
  private readonly releasesBase: string;
  private readonly shellVersion: string;
  private readonly content: ContentManager;
  private readonly downloadsDir: string;
  private readonly log: Logger;
  private readonly fetchFn: typeof fetch;

  constructor(options: UpdaterOptions) {
    this.releasesBase = options.releasesBase.replace(/\/$/, "");
    this.shellVersion = options.shellVersion;
    this.content = options.content;
    this.downloadsDir = options.downloadsDir;
    this.log = options.log;
    this.fetchFn = options.fetch ?? fetch;
  }

  /** Never throws: being offline, or a release with no content, is "none". */
  async check(): Promise<Verdict> {
    let manifest: ContentManifest;
    try {
      const response = await this.fetchFn(`${this.releasesBase}/content-latest.json`, {
        signal: AbortSignal.timeout(10_000),
        cache: "no-store",
      });
      if (!response.ok) {
        this.log.info(`update: content-latest.json answered ${response.status}`);
        return { kind: "none", manifest: null };
      }
      manifest = (await response.json()) as ContentManifest;
    } catch (error) {
      this.log.info(`update: no check (${String(error)})`);
      return { kind: "none", manifest: null };
    }
    const running = await this.content.current();
    if (compareVersions(manifest.content_version, running.version) <= 0) {
      return { kind: "none", manifest };
    }
    if (!satisfiesMin(this.shellVersion, manifest.min_shell_version)) {
      this.log.info(
        `update: ${manifest.content_version} needs shell ${manifest.min_shell_version}, have ${this.shellVersion}`,
      );
      return { kind: "needs-shell", manifest };
    }
    return { kind: "available", manifest };
  }

  /** Fetch the tarball and install it. Resolves with the installed directory. */
  async download(
    manifest: ContentManifest,
    onProgress?: (received: number, total: number) => void,
  ): Promise<string> {
    await mkdir(this.downloadsDir, { recursive: true });
    const target = join(this.downloadsDir, manifest.asset);
    const url = `${this.releasesBase}/${manifest.asset}`;
    this.log.info(`update: downloading ${url}`);
    try {
      const response = await this.fetchFn(url);
      if (!response.ok || !response.body) {
        throw new Error(`download answered ${response.status}`);
      }
      let received = 0;
      const counted = new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          received += chunk.byteLength;
          onProgress?.(received, manifest.size);
          controller.enqueue(chunk);
        },
      });
      await pipeline(
        Readable.fromWeb(
          response.body.pipeThrough(counted) as import("node:stream/web").ReadableStream,
        ),
        createWriteStream(target),
      );
      return await this.content.install(target, manifest);
    } finally {
      await rm(target, { force: true });
    }
  }
}

/**
 * The cadence: once soon after launch, then every few hours. `setTimer` is
 * injected so the tests can run the clock; the return value stops it.
 */
export function scheduleChecks(
  run: () => Promise<void>,
  options: {
    firstMs?: number;
    everyMs?: number;
    setTimer?: typeof setTimeout;
    clearTimer?: typeof clearTimeout;
  } = {},
): () => void {
  const firstMs = options.firstMs ?? FIRST_CHECK_MS;
  const everyMs = options.everyMs ?? CHECK_EVERY_MS;
  const setTimer = options.setTimer ?? setTimeout;
  const clearTimer = options.clearTimer ?? clearTimeout;
  let handle: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;
  const tick = async (next: number) => {
    if (stopped) return;
    try {
      await run();
    } catch {
      // `check` never throws, and a download failure is the caller's to log.
    }
    if (!stopped) handle = setTimer(() => void tick(everyMs), next);
  };
  handle = setTimer(() => void tick(everyMs), firstMs);
  return () => {
    stopped = true;
    if (handle) clearTimer(handle);
  };
}
