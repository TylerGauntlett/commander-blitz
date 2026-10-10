/**
 * Version comparison, just enough of semver for release tags.
 *
 * `1.2.3`, `1.2.3-beta.1`, `v1.2.3`: numeric parts compared as numbers, a
 * pre-release sorting below its release, and nothing else. A dependency for
 * this would be the only one the pure modules had.
 */

export function parseVersion(text: string): { parts: number[]; pre: string | null } {
  const trimmed = text.trim().replace(/^v/, "");
  const [main, pre = null] = trimmed.split("-", 2);
  const parts = main.split(".").map((p) => Number.parseInt(p, 10));
  if (parts.length === 0 || parts.some((p) => Number.isNaN(p))) {
    throw new Error(`not a version: ${JSON.stringify(text)}`);
  }
  while (parts.length < 3) parts.push(0);
  return { parts, pre };
}

/** Negative when `a < b`, zero when equal, positive when `a > b`. */
export function compareVersions(a: string, b: string): number {
  const x = parseVersion(a);
  const y = parseVersion(b);
  for (let i = 0; i < Math.max(x.parts.length, y.parts.length); i += 1) {
    const d = (x.parts[i] ?? 0) - (y.parts[i] ?? 0);
    if (d !== 0) return d;
  }
  if (x.pre === y.pre) return 0;
  if (x.pre === null) return 1;
  if (y.pre === null) return -1;
  return x.pre < y.pre ? -1 : 1;
}

/** Whether a shell at `shell` can run content that asks for at least `min`. */
export function satisfiesMin(shell: string, min: string | undefined | null): boolean {
  if (!min) return true;
  return compareVersions(shell, min) >= 0;
}
