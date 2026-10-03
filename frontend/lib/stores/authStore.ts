import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type Role = "analyst" | "bank_admin";

// On the server (SSR/prerender) there is no localStorage; use a no-op store so
// persist doesn't crash. The browser gets real localStorage.
const noopStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
};

export interface AuthUser {
  id: number;
  username: string;
  role: Role;
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  /** False until the initial session check has run (see SessionInit). */
  authReady: boolean;
  setAuth: (user: AuthUser, access: string, refresh: string) => void;
  setTokens: (access: string, refresh?: string) => void;
  setUser: (user: AuthUser) => void;
  setAuthReady: (ready: boolean) => void;
  clearAuth: () => void;
}

/**
 * Auth state, persisted to localStorage so a page reload keeps the session.
 *
 * Tokens are short-lived JWTs (access 30 min) with rotating refresh; on reload
 * SessionInit revalidates them via /api/auth/me/ and the axios interceptor
 * refreshes/clears as needed. Only tokens + user are persisted; runtime flags
 * (authReady) are not.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      authReady: false,
      setAuth: (user, access, refresh) =>
        set({
          user,
          accessToken: access,
          refreshToken: refresh,
          isAuthenticated: true,
        }),
      setTokens: (access, refresh) =>
        set((state) => ({
          accessToken: access,
          refreshToken: refresh ?? state.refreshToken,
        })),
      setUser: (user) => set({ user, isAuthenticated: true }),
      setAuthReady: (ready) => set({ authReady: ready }),
      clearAuth: () =>
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        }),
    }),
    {
      name: "aimw-auth",
      storage: createJSONStorage(() =>
        typeof window !== "undefined" ? window.localStorage : noopStorage
      ),
      partialize: (s) => ({
        user: s.user,
        accessToken: s.accessToken,
        refreshToken: s.refreshToken,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) state.isAuthenticated = !!state.user;
      },
    }
  )
);
