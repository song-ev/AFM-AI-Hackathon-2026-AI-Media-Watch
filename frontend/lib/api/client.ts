import axios, {
  AxiosError,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from "axios";

import { useAuthStore } from "@/lib/stores/authStore";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Shared axios instance for all backend calls. */
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// --- Request: attach the JWT access token from the store ------------------
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// --- Response: on 401, try a single refresh then retry, else go to login ---
interface RetriableConfig extends AxiosRequestConfig {
  _retry?: boolean;
}

function redirectToLogin() {
  useAuthStore.getState().clearAuth();
  if (typeof window !== "undefined") {
    window.location.href = "/login";
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;

    if (error.response?.status !== 401 || !original || original._retry) {
      return Promise.reject(error);
    }

    original._retry = true;
    const { refreshToken, setTokens } = useAuthStore.getState();
    if (!refreshToken) {
      redirectToLogin();
      return Promise.reject(error);
    }

    try {
      // Bare axios (no interceptors) to avoid recursive refresh.
      const { data } = await axios.post(`${API_BASE_URL}/api/auth/refresh/`, {
        refresh: refreshToken,
      });
      setTokens(data.access, data.refresh);
      original.headers = {
        ...original.headers,
        Authorization: `Bearer ${data.access}`,
      };
      return apiClient(original);
    } catch (refreshError) {
      redirectToLogin();
      return Promise.reject(refreshError);
    }
  }
);
