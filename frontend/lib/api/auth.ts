import { apiClient } from "@/lib/api/client";
import type { AuthUser } from "@/lib/stores/authStore";

export interface LoginResponse {
  access: string;
  refresh: string;
  user: AuthUser;
}

/** POST /api/auth/login/ — exchange credentials for tokens. */
export async function login(
  username: string,
  password: string
): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>("/api/auth/login/", {
    username,
    password,
  });
  return data;
}

/** GET /api/auth/me/ — current user (id, username, role, profile). */
export async function fetchMe(): Promise<AuthUser> {
  const { data } = await apiClient.get<AuthUser>("/api/auth/me/");
  return data;
}

/** POST /api/auth/logout/ — blacklist the refresh token (best effort). */
export async function logout(refresh: string | null): Promise<void> {
  if (!refresh) return;
  try {
    await apiClient.post("/api/auth/logout/", { refresh });
  } catch {
    // Logout is best-effort; clear local state regardless.
  }
}
