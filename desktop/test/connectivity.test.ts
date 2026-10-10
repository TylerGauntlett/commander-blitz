import { describe, expect, it, vi } from "vitest";
import { ConnectivityWatcher } from "../src/connectivity.js";
import { memoryLogger } from "../src/logging.js";

const ORIGIN = "https://commanderblitz.com";

function watcher(answers: (() => Promise<Response>)[]) {
  let i = 0;
  const fetchFn = (async () => {
    const answer = answers[Math.min(i, answers.length - 1)];
    i += 1;
    return answer();
  }) as typeof fetch;
  const log = memoryLogger();
  const w = new ConnectivityWatcher({
    origin: `${ORIGIN}/`,
    log,
    fetch: fetchFn,
    intervalMs: 10,
  });
  const changes: boolean[] = [];
  w.on("change", (online) => changes.push(online));
  return { w, changes, log, probes: () => i };
}

const ok = async () => new Response("{}", { status: 200 });
const down = async () => {
  throw new Error("ENETUNREACH");
};
const busy = async () => new Response("", { status: 503 });

describe("ConnectivityWatcher", () => {
  it("asks /health on the origin and announces the first answer", async () => {
    const { w, changes } = watcher([ok]);
    expect(w.online).toBeNull();
    expect(await w.probe()).toBe(true);
    expect(changes).toEqual([true]);
    expect(w.online).toBe(true);
  });

  it("announces only changes", async () => {
    const { w, changes } = watcher([ok, ok, down, down, ok]);
    for (let i = 0; i < 5; i += 1) await w.probe();
    expect(changes).toEqual([true, false, true]);
  });

  it("treats a server error as offline: you cannot play on a 503", async () => {
    const { w } = watcher([busy]);
    expect(await w.probe()).toBe(false);
  });

  it("keeps probing on the interval until stopped", async () => {
    vi.useFakeTimers();
    try {
      const { w, probes } = watcher([ok]);
      w.start();
      w.start(); // idempotent
      await vi.advanceTimersByTimeAsync(0);
      expect(probes()).toBe(1);
      await vi.advanceTimersByTimeAsync(25);
      expect(probes()).toBe(3);
      w.stop();
      await vi.advanceTimersByTimeAsync(100);
      expect(probes()).toBe(3);
    } finally {
      vi.useRealTimers();
    }
  });
});
