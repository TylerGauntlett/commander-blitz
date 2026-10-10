/**
 * The other two places the desktop changes: the import strip, which needs
 * Moxfield, and the lobby's Invite, which needs somebody to be able to reach
 * this server.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AppConfig } from "../src/api/types";
import { PodLobby } from "../src/components/lobby/PodLobby";
import { DeckImport } from "../src/components/menu/DeckImport";
import { resetInputMode } from "../src/input/inputMode";
import { resetPad } from "../src/input/pad";
import { AppConfigContext } from "../src/state/useAppConfig";
import { deckSummary, podView } from "../src/testing/fixtures";

const DESKTOP: AppConfig = {
  mode: "desktop",
  online: false,
  remote_origin: "https://commanderblitz.com",
  app_version: "0.1.0",
  content_version: "1.2.3",
};

function asDesktop(children: ReactNode, online = false) {
  return (
    <AppConfigContext.Provider value={{ ...DESKTOP, online }}>
      {children}
    </AppConfigContext.Provider>
  );
}

afterEach(() => {
  resetPad();
  resetInputMode();
});

describe("DeckImport", () => {
  it("works as before when enabled", () => {
    render(<DeckImport onImported={vi.fn()} variant="row" />);
    expect((screen.getByTestId("import-url") as HTMLInputElement).disabled).toBe(false);
    expect(screen.queryByTestId("import-offline")).toBeNull();
  });

  it("is disabled, and says why, when there is no connection", () => {
    render(<DeckImport onImported={vi.fn()} variant="row" enabled={false} />);
    expect((screen.getByTestId("import-url") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByTestId("import-go") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("import-offline").textContent).toMatch(/needs a connection/);
  });
});

function lobby() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  return (
    <QueryClientProvider client={client}>
      <PodLobby
        pod={podView([{ kind: "human", is_you: true, is_host: true, deck: deckSummary() }])}
        decks={[deckSummary()]}
        busy={false}
        starting={false}
        error={null}
        onUpdateSeat={vi.fn()}
        onAdminSeat={vi.fn()}
        onSetSeatDeck={vi.fn()}
        onStart={vi.fn()}
        onLeave={vi.fn()}
        onDecksChanged={vi.fn()}
      />
    </QueryClientProvider>
  );
}

describe("PodLobby", () => {
  it("offers Invite on the site", () => {
    render(lobby());
    expect(screen.getByTestId("invite")).toBeTruthy();
  });

  it("has no Invite on the desktop: nobody can reach a server on 127.0.0.1", () => {
    render(asDesktop(lobby(), true));
    expect(screen.queryByTestId("invite")).toBeNull();
    // ...and the rest of the bar is still there.
    expect(screen.getByTestId("leave-pod")).toBeTruthy();
  });

  it("greys the catalogue's import strip when the desktop is offline", () => {
    render(asDesktop(lobby(), false));
    fireEvent.click(screen.getByTestId("change-deck"));
    expect(screen.getByTestId("deck-catalog")).toBeTruthy();
    expect(screen.getByTestId("import-offline")).toBeTruthy();
  });
});
