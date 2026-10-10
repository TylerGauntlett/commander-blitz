/**
 * The desktop's "update ready", in its three states.
 *
 * It renders nothing on the site and nothing until the shell says an update
 * has landed, so each story stands in for the shell: a fake bridge on
 * `window`, a desktop config, and one emitted update.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { MemoryRouter } from "react-router";
import { expect, fn, within } from "storybook/test";
import type { AppConfig } from "../../api/types";
import type { CommanderBlitzBridge, UpdateReady } from "../../desktop/bridge";
import { AppConfigContext } from "../../state/useAppConfig";
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
  parameters: { automtg: { mount: "bare" } },
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
