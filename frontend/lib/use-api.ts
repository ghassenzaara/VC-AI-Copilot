"use client";

// React hook layer over lib/api.ts that injects the Clerk session token.
// Use this from any client component in the (app) route group so every
// backend request carries the user's bearer token.

import { useAuth } from "@clerk/nextjs";
import { useCallback, useMemo } from "react";
import * as api from "./api";

export function useApi() {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  const requireToken = useCallback(async (): Promise<string> => {
    const token = await getToken();
    if (!token) {
      throw new Error("Not signed in");
    }
    return token;
  }, [getToken]);

  return useMemo(
    () => ({
      isReady: isLoaded && isSignedIn,
      fetchCompanies: async () => api.fetchCompanies(await requireToken()),
      fetchCompanyFull: async (id: string) =>
        api.fetchCompanyFull(id, await requireToken()),
      fetchMarketMap: async () => api.fetchMarketMap(await requireToken()),
      regenerateMarketMap: async () =>
        api.regenerateMarketMap(await requireToken()),
      fetchDashboardSummary: async () =>
        api.fetchDashboardSummary(await requireToken()),
    }),
    [isLoaded, isSignedIn, requireToken]
  );
}
