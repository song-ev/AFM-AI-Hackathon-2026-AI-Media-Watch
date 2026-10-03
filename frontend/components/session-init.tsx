"use client";

import { useEffect } from "react";

import { fetchMe } from "@/lib/api/auth";
import { useAuthStore } from "@/lib/stores/authStore";

/**
 * Runs once on app start: if an access token is present (e.g. set during this
 * session), fetch the current user to populate role/profile, then mark auth as
 * ready so guards can act.
 *
 * NOTE: tokens are in-memory (see authStore), so after a hard reload there is
 * nothing to restore and this resolves immediately to "unauthenticated". The
 * mechanism is here and forward-compatible with a future cookie-based flow.
 */
export function SessionInit() {
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { accessToken, user, setUser, clearAuth, setAuthReady } =
        useAuthStore.getState();
      if (accessToken && !user) {
        try {
          const me = await fetchMe();
          if (!cancelled) setUser(me);
        } catch {
          if (!cancelled) clearAuth();
        }
      }
      if (!cancelled) setAuthReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}
