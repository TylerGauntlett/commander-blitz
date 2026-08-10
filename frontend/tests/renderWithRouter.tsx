/**
 * Mounting `<App/>` at an address.
 *
 * The one place a test needs providers around it. Everything presentational
 * still renders bare -- no component under `components/` imports react-router,
 * which is what keeps that invariant true rather than merely aspirational. What
 * needs a router is the wiring in `screens/`, and the wiring is exactly what
 * these tests are about.
 *
 * `MemoryRouter` rather than the real history, so a spec can open a deep link
 * without a browser, and `location` can be read back to assert where a
 * navigation went.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type RenderResult, render } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigationType } from "react-router";
import { App } from "../src/App";

/** Where the app is now, updated on every navigation. */
export interface Where {
  pathname: string;
  search: string;
  /**
   * How the app got here: `PUSH` left an entry behind, `REPLACE` did not.
   *
   * This is the assertion behind "back never lands on a dead lobby" -- the
   * property is about history, so checking the rendered screen would not see it.
   */
  how: "POP" | "PUSH" | "REPLACE";
}

function Spy({ into }: { into: Where }) {
  const location = useLocation();
  into.pathname = location.pathname;
  into.search = location.search;
  into.how = useNavigationType();
  return null;
}

export function renderApp(path = "/"): RenderResult & { where: Where } {
  const where: Where = { pathname: path, search: "", how: "POP" };
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Number.POSITIVE_INFINITY },
      mutations: { retry: false },
    },
  });
  const view = render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={client}>
        <App />
        <Spy into={where} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return Object.assign(view, { where });
}
