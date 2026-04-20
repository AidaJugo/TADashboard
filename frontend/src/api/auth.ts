/**
 * API client for /api/auth endpoints.
 */

export interface MeResponse {
  id: string;
  email: string;
  display_name: string;
  role: "admin" | "editor" | "viewer";
}

export async function fetchMe(): Promise<MeResponse> {
  const res = await fetch("/api/auth/me", { credentials: "include" });
  if (res.status === 401) {
    window.location.href = "/api/auth/login";
    throw new Error("session_expired");
  }
  if (!res.ok) throw new Error(`/me failed: ${res.status}`);
  return res.json() as Promise<MeResponse>;
}
