import { QueryClient } from "@tanstack/react-query";

/**
 * Create a QueryClient with sensible defaults. A factory (not a singleton) so
 * each browser session / SSR pass gets its own instance (see Providers).
 */
export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000, // 1 min — data is not real-time critical
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}
