/**
 * Which server this is, for every component that has to care.
 *
 * `GET /api/config` once at boot, then every half-minute on the desktop, where
 * the answer to "is the hosted server reachable" can change while the door is
 * open. On the site it is fetched once and never again: the answer there is
 * constant.
 *
 * The context's default is `HOSTED_DEFAULT`, so a component rendered bare -- a
 * story, a unit test, a screen somebody forgot to wrap -- sees the site's
 * behaviour. That is the one that was here before the desktop existed, and the
 * one that must keep working if the config request fails: a door that greys
 * out Join because a fetch errored is a door nobody can get through.
 */

import { useQuery } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext, useEffect } from "react";
import { api } from "../api/client";
import type { AppConfig } from "../api/types";
import { bridge } from "../desktop/bridge";
import { HOSTED_DEFAULT } from "../logic/desktop";

/** How often the desktop asks again. Matches the sidecar's probe cache. */
export const CONFIG_REFRESH_MS = 30_000;

/**
 * Exported for tests and stories, which render a component "as the desktop"
 * by providing a value directly rather than answering a fetch.
 */
export const AppConfigContext = createContext<AppConfig>(HOSTED_DEFAULT);

export function AppConfigProvider({ children }: { children: ReactNode }) {
  const { data, refetch } = useQuery({
    queryKey: ["config"],
    queryFn: api.config,
    placeholderData: HOSTED_DEFAULT,
    staleTime: CONFIG_REFRESH_MS,
    // Only the desktop has anything to re-ask. `data` is the placeholder until
    // the first answer, and the placeholder is hosted, so the first fetch
    // decides whether there will be a second.
    refetchInterval: (query) =>
      query.state.data?.mode === "desktop" ? CONFIG_REFRESH_MS : false,
    retry: 1,
  });

  // The shell watches the connection too, and says so the moment it changes;
  // that beats waiting out the interval with a greyed-out button.
  useEffect(() => bridge()?.onConnectivity(() => void refetch()), [refetch]);

  return (
    <AppConfigContext.Provider value={data ?? HOSTED_DEFAULT}>
      {children}
    </AppConfigContext.Provider>
  );
}

export function useAppConfig(): AppConfig {
  return useContext(AppConfigContext);
}
