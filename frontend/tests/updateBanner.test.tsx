/**
 * The desktop's update banner: nothing until an update arrives, Restart for
 * content, a sentence for a shell update, and never a restart mid-game.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { AppConfig } from "../src/api/types";
import { UpdateBanner } from "../src/components/ui/UpdateBanner";
import type { CommanderBlitzBridge, UpdateReady } from "../src/desktop/bridge";
import { AppConfigContext } from "../src/state/useAppConfig";

const DESKTOP: AppConfig = {
  mode: "desktop",
  online: true,
  remote_origin: "https://commanderblitz.com",
  app_version: "0.1.0",
  content_version: "1.2.3",
};

function fakeBridge() {
  let listener: ((update: UpdateReady) => void) | null = null;
  const bridge: CommanderBlitzBridge & {
    emit: (u: UpdateReady) => void;
    unsubscribed: number;
    restarts: number;
  } = {
    version: { shell: "1.0.0", content: "1.2.3" },
    onUpdate(cb) {
      listener = cb;
      return () => {
        listener = null;
        bridge.unsubscribed += 1;
      };
    },
    restartToUpdate: async () => {
      bridge.restarts += 1;
    },
    openOnline: async () => undefined,
    returnLocal: async () => undefined,
    onConnectivity: () => () => undefined,
    diagnostics: async () => {
      throw new Error("unused");
    },
    emit: (u) => listener?.(u),
    unsubscribed: 0,
    restarts: 0,
  };
  return bridge;
}

function mount(path = "/", config: AppConfig = DESKTOP) {
  const client = new QueryClient();
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={client}>
        <AppConfigContext.Provider value={config}>
          <UpdateBanner />
        </AppConfigContext.Provider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  window.commanderblitz = undefined;
});

describe("UpdateBanner", () => {
  it("shows nothing until an update has arrived", () => {
    window.commanderblitz = fakeBridge();
    mount();
    expect(screen.queryByTestId("update-banner")).toBeNull();
  });

  it("shows nothing on the site, even with a bridge: the site has no updates", () => {
    const bridge = fakeBridge();
    window.commanderblitz = bridge;
    mount("/", { ...DESKTOP, mode: "hosted" });
    act(() => bridge.emit({ version: "1.3.0", appliesOnQuit: false }));
    expect(screen.queryByTestId("update-banner")).toBeNull();
  });

  it("offers Restart for a content update, and restarts once", () => {
    const bridge = fakeBridge();
    window.commanderblitz = bridge;
    mount();
    act(() => bridge.emit({ version: "1.3.0", appliesOnQuit: false }));
    expect(screen.getByTestId("update-banner").textContent).toContain("1.3.0");
    const button = screen.getByTestId("update-restart");
    expect(button.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(button);
    fireEvent.click(button);
    expect(bridge.restarts).toBe(1);
  });

  it("never restarts at the table: games live in the server's memory", () => {
    const bridge = fakeBridge();
    window.commanderblitz = bridge;
    mount("/games/g1");
    act(() => bridge.emit({ version: "1.3.0", appliesOnQuit: false }));
    expect(screen.getByTestId("update-banner").textContent).toMatch(/after this game/);
    const button = screen.getByTestId("update-restart");
    expect(button.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(button);
    expect(bridge.restarts).toBe(0);
  });

  it("says a shell update installs on quit, with nothing to press", () => {
    const bridge = fakeBridge();
    window.commanderblitz = bridge;
    mount();
    act(() => bridge.emit({ version: "2.0.0", appliesOnQuit: true }));
    expect(screen.getByTestId("update-banner").textContent).toMatch(/next time you quit/);
    expect(screen.queryByTestId("update-restart")).toBeNull();
  });

  it("lets go of the bridge when it unmounts", () => {
    const bridge = fakeBridge();
    window.commanderblitz = bridge;
    const view = mount();
    view.unmount();
    expect(bridge.unsubscribed).toBe(1);
  });
});
