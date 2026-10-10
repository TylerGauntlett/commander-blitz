/**
 * Two log files, rotated by size, and a way to read their tails.
 *
 * `shell.log` is what the Electron side says; `sidecar.log` is the server's
 * stderr, piped through unchanged. Both live in the per-user `logs/`
 * directory so a bug report from a device with no terminal can still carry
 * them: the settings panel shows the path, and the splash shows the tail
 * when the server fails to start.
 *
 * Synchronous appends, deliberately. A log line that may or may not have
 * been written when the process died is not a log line.
 */

import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  statSync,
} from "node:fs";
import { join } from "node:path";

export interface Logger {
  info(message: string): void;
  warn(message: string): void;
  error(message: string): void;
  /** Append a raw line, no level, no timestamp: the sidecar's own output. */
  raw(line: string): void;
  tail(lines: number): string[];
  readonly path: string;
}

export interface LogOptions {
  /** Rotate when the file passes this many bytes. */
  maxBytes?: number;
  /** How many rotated files to keep beside the live one. */
  keep?: number;
  now?: () => Date;
}

export function fileLogger(dir: string, name: string, options: LogOptions = {}): Logger {
  const maxBytes = options.maxBytes ?? 2 * 1024 * 1024;
  const keep = options.keep ?? 4;
  const now = options.now ?? (() => new Date());
  const path = join(dir, `${name}.log`);
  mkdirSync(dir, { recursive: true });

  const rotate = () => {
    if (!existsSync(path) || statSync(path).size < maxBytes) return;
    // shell.log.3 -> shell.log.4, ..., shell.log -> shell.log.1; the oldest
    // falls off the end.
    for (let i = keep - 1; i >= 1; i -= 1) {
      const from = `${path}.${i}`;
      if (existsSync(from)) renameSync(from, `${path}.${i + 1}`);
    }
    renameSync(path, `${path}.1`);
  };

  const write = (line: string) => {
    rotate();
    appendFileSync(path, `${line}\n`, "utf8");
  };

  const stamp = (level: string, message: string) =>
    write(`${now().toISOString()} ${level.padEnd(5)} ${message}`);

  return {
    path,
    info: (m) => stamp("info", m),
    warn: (m) => stamp("warn", m),
    error: (m) => stamp("error", m),
    raw: (line) => write(line),
    tail(lines) {
      if (!existsSync(path)) return [];
      const all = readFileSync(path, "utf8").split("\n").filter(Boolean);
      return all.slice(-lines);
    },
  };
}

/** A logger that keeps everything in memory: for tests and `--smoke`. */
export function memoryLogger(): Logger & { lines: string[] } {
  const lines: string[] = [];
  return {
    lines,
    path: "<memory>",
    info: (m) => void lines.push(`info ${m}`),
    warn: (m) => void lines.push(`warn ${m}`),
    error: (m) => void lines.push(`error ${m}`),
    raw: (l) => void lines.push(l),
    tail: (n) => lines.slice(-n),
  };
}
