/**
 * "Update ready": the desktop's three states and the site's two.
 *
 * It renders nothing until there is an update, so each desktop story stands in
 * for the shell -- a fake bridge on `window`, a desktop config, and one emitted
 * update -- and each site story stands in for a deploy: a hosted config whose
 * version moves after the page has loaded.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect, useState } from "react";
import { MemoryRouter } from "react-router";
import { expect, fn, within } from "storybook/test";
import type { AppConfig } from "../../api/types";
import type { CommanderBlitzBridge, UpdateReady } from "../../desktop/bridge";
import { AppConfigContext } from "../../state/useAppConfig";
import { expectFontFloor, expectHitFloor } from "../../testing/asserts";
import { UpdateBanner } from "./UpdateBanner";

const DESKTOP: AppConfig = {
  mode: "desktop",
  online: true,
  remote_origin: "https://commanderblitz.com",
  app_version: "0.1.0",
  content_version: "1.2.3",
};

/** A bridge that hands every listener `update` as soon as it subscribes. */
function shellWith(update: UpdateReady): CommanderBlitzBridge {
  return {
    version: { shell: "1.0.0", content: "1.2.3" },
    onUpdate(listener) {
      queueMicrotask(() => listener(update));
      return () => undefined;
    },
    restartToUpdate: fn(async () => undefined),
    openOnline: async () => undefined,
    returnLocal: async () => undefined,
    onConnectivity: () => () => undefined,
    diagnostics: async () => {
      throw new Error("not in this story");
    },
  };
}

function Stage({ path, update }: { path: string; update: UpdateReady }) {
  window.commanderblitz = shellWith(update);
  return (
    <MemoryRouter initialEntries={[path]}>
      <AppConfigContext.Provider value={DESKTOP}>
        <UpdateBanner />
      </AppConfigContext.Provider>
    </MemoryRouter>
  );
}

const meta = {
  title: "ui/UpdateBanner",
  component: Stage,
  parameters: { commanderblitz: { mount: "bare" } },
} satisfies Meta<typeof Stage>;

export default meta;
type Story = StoryObj<typeof meta>;

/** At the door: Restart is live. */
export const ContentReady: Story = {
  args: { path: "/", update: { version: "1.3.0", appliesOnQuit: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const button = await canvas.findByTestId("update-restart");
    expect(button).not.toHaveAttribute("aria-disabled");
    expect(Math.round(button.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
  },
};

/** At the table: the same update, and the button waits for the game to end. */
export const ContentReadyMidGame: Story = {
  args: { path: "/games/g1", update: { version: "1.3.0", appliesOnQuit: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(await canvas.findByTestId("update-restart")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(canvasElement.textContent).toMatch(/after this game/);
  },
};

/** A shell update: nothing to press, only something to know. */
export const ShellInstallsOnQuit: Story = {
  args: { path: "/", update: { version: "2.0.0", appliesOnQuit: true } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("update-banner");
    expect(canvas.queryByTestId("update-restart")).toBeNull();
  },
};

const SITE: AppConfig = {
  mode: "hosted",
  online: true,
  remote_origin: null,
  app_version: "1.4.0",
  content_version: "1.4.0",
};

/** The site, whose `/api/config` answers with `next` once the page is up. */
function SiteStage({ path, next }: { path: string; next: string }) {
  window.commanderblitz = undefined;
  const [config, setConfig] = useState(SITE);
  useEffect(() => {
    const moved = setTimeout(() => setConfig({ ...SITE, app_version: next }), 0);
    return () => clearTimeout(moved);
  }, [next]);
  return (
    <MemoryRouter initialEntries={[path]}>
      <AppConfigContext.Provider value={config}>
        <UpdateBanner />
      </AppConfigContext.Provider>
    </MemoryRouter>
  );
}

/** A deploy landed: Reload, at the floor every touch target keeps. */
export const SiteDeployed: StoryObj<typeof SiteStage> = {
  render: (args) => <SiteStage {...args} />,
  args: { path: "/", next: "1.5.0" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const button = await canvas.findByTestId("update-reload");
    expect(canvasElement.textContent).toMatch(/1\.5\.0 is live/);
    expect(Math.round(button.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
  },
};

/**
 * At the table: still the player's to press, and the game survives it. Held
 * at the handheld floors too, since a phone or a Deck in a browser reaches the
 * site the same way (ADR 0013).
 */
export const SiteDeployedMidGame: StoryObj<typeof SiteStage> = {
  globals: { handheld: "on" },
  tags: ["handheld"],
  render: (args) => <SiteStage {...args} />,
  args: { path: "/games/g1", next: "1.5.0" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const button = await canvas.findByTestId("update-reload");
    expect(button).not.toHaveAttribute("aria-disabled");
    expect(canvasElement.textContent).toMatch(/carries over/);
    expectFontFloor(canvasElement);
    expectHitFloor(canvasElement);
  },
};

/** No deploy: the same build answers, and there is nothing to say. */
export const SiteUnchanged: StoryObj<typeof SiteStage> = {
  render: (args) => <SiteStage {...args} />,
  args: { path: "/", next: "1.4.0" },
  play: async ({ canvasElement }) => {
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(within(canvasElement).queryByTestId("update-banner")).toBeNull();
  },
};
