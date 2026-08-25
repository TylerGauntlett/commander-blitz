import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import "./theme.css";
// Before `board.css` and `room.css`, so either can tune the shared drifting
// layers it defines. The board dims its mote field; the lobby does not.
import "./styles/ambience.css";
import "./styles/cards.css";
import "./styles/board.css";
// After `board.css`: the seat re-shapes `.mat--compact`, which board.css
// declares. Same reason `handheld.css` loads last.
import "./styles/seat.css";
import "./styles/reader.css";
import "./styles/groups.css";
import "./styles/ui.css";
// After `ui.css`: the opening hand replaces that sheet's `.prompt` for one
// decision kind, and its own class names are new so nothing here is a contest.
import "./styles/opening.css";
import "./styles/lobby.css";
// After `lobby.css`, all four: `room.css` and the three screens standing in it
// replace that sheet's `.door`, `.pod` and `.cat` shells. `room.css` first,
// because the other three are written as additions to its kit.
import "./styles/room.css";
import "./styles/door.css";
import "./styles/pod.css";
import "./styles/shelf.css";
import "./styles/handheld.css";

// The engine is authoritative and every mutation returns fresh state, so there
// is nothing to refetch in the background.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: false, staleTime: Number.POSITIVE_INFINITY },
  },
});

const container = document.getElementById("root");
if (!container) throw new Error("no #root element");

// `BrowserRouter` here rather than inside `App` so a test can mount `<App/>`
// under a `MemoryRouter` and open it at any address. That is the only way to
// test a deep link, and deep links are the point of having routes at all.
createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>,
);
