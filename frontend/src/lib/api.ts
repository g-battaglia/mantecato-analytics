import { useAuthStore } from "@/stores/auth";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

/**
 * Fetch wrapper that prepends VITE_API_URL and adds the JWT Bearer token.
 * On 401, clears the token and redirects to /login.
 */
export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const token = useAuthStore.getState().token;

  const headers = new Headers(init?.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (res.status === 401 && !path.startsWith("/api/auth")) {
    useAuthStore.getState().clearToken();
    window.location.href = "/login";
  }

  return res;
}
