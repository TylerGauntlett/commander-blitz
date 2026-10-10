/**
 * `useAppConfig`: one fetch of `/api/config`, hosted until it answers, and on
 * the desktop re-asked when the shell says the connection changed.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AppConfig } from "../src/api/types";
import type { CommanderBlitzBridge } from "../src/desktop/bridge";
import { canPlayOnline } from "../src/logic/desktop";
import { AppConfigProvider, useAppConfig } from "../src/state/useAppConfig";

const DESKTOP_OFFLINE: AppConfig = {
  mode: "desktop",
  online: false,
  remote_origin: "https://commanderblitz.com",
  app_version: "0.1.0",
  content_version: "1.2.3",
};

function Probe() {
  const config = useAppConfig();
  return (
    <output data-testid="probe">
      {config.mode}/{canPlayOnline(config) ? "online" : "offline"}/{config.content_version}
    </output>
  );
}

let fetches: string[];
let answer: AppConfig | Error;

function mount(withProvider = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  const tree = withProvider ? (
    <AppConfigProvider>
      <Probe />
    </AppConfigProvider>
  ) : (
    <Probe />
  );
  return render(<QueryClientProvider client={client}>{tree}</QueryClientProvider>);
}

function fakeBridge(): CommanderBlitzBridge & {
  emit: (online: boolean) => void;
  unsubscribed: number;
} {
  const listeners = new Set<(online: boolean) => void>();
  const bridge = {
    version: { shell: "1.0.0", content: "1.2.3" },
    onUpdate: () => () => undefined,
    restartToUpdate: async () => undefined,
    openOnline: async () => undefined,
    returnLocal: async () => undefined,
    onConnectivity(listener: (online: boolean) => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
        bridge.unsubscribed += 1;
      };
    },
    diagnostics: async () => {
      throw new Error("not in this test");
    },
    emit: (online: boolean) => {
      for (const listener of listeners) listener(online);
    },
    unsubscribed: 0,
  };
  return bridge;
}

beforeEach(() => {
  fetches = [];
  answer = DESKTOP_OFFLINE;
  vi.stubGlobal("fetch", async (url: string) => {
    fetches.push(String(url));
    if (answer instanceof Error) throw answer;
    return new Response(JSON.stringify(answer), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.commanderblitz = undefined;
});

describe("AppConfigProvider", () => {
  it("is hosted and online until the server says otherwise", async () => {
    mount();
    expect(screen.getByTestId("probe").textContent).toBe("hosted/online/");
    await waitFor(() =>
      expect(screen.getByTestId("probe").textContent).toBe("desktop/offline/1.2.3"),
    );
    expect(fetches).toEqual(["/api/config"]);
  });

  it("stays hosted when the request fails: a greyed door nobody can pass is worse", async () => {
    answer = new Error("network");
    mount();
    await waitFor(() => expect(fetches.length).toBeGreaterThan(0));
    // Give the failure time to land; the probe must not have changed.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.getByTestId("probe").textContent).toBe("hosted/online/");
  });

  it("asks again when the shell reports a change in connectivity", async () => {
    const bridge = fakeBridge();
    window.commanderblitz = bridge;
    const view = mount();
    await waitFor(() => expect(fetches).toEqual(["/api/config"]));

    answer = { ...DESKTOP_OFFLINE, online: true };
    act(() => bridge.emit(true));
    await waitFor(() =>
      expect(screen.getByTestId("probe").textContent).toBe("desktop/online/1.2.3"),
    );
    expect(fetches).toEqual(["/api/config", "/api/config"]);

    view.unmount();
    expect(bridge.unsubscribed).toBe(1);
  });
});

describe("useAppConfig without a provider", () => {
  it("is the site: a story or a bare component sees what shipped before", () => {
    mount(false);
    expect(screen.getByTestId("probe").textContent).toBe("hosted/online/");
    expect(fetches).toEqual([]);
  });
});
