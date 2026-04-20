/**
 * API client for /api/comments endpoints (FR-COMMENT-1..4).
 */

export interface CommentRecord {
  id: string;
  position: string;
  seniority: string;
  hub: string;
  salary_eur: number;
  text: string;
  created_at: string;
  updated_at: string;
}

export interface CommentCreateBody {
  position: string;
  seniority: string;
  hub: string;
  salary_eur: number;
  text: string;
}

function csrfHeaders(): Record<string, string> {
  const token = document.cookie
    .split("; ")
    .find((c) => c.startsWith("ta_csrf="))
    ?.split("=")[1];
  return token ? { "X-CSRF-Token": token } : {};
}

async function apiJSON<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...csrfHeaders(),
    },
    ...(body !== undefined && { body: JSON.stringify(body) }),
  });

  if (res.status === 401) {
    window.location.href = "/api/auth/login";
    throw new Error("session_expired");
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => String(res.status));
    throw new Error(`${res.status} — ${detail}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

export const listComments = () => apiJSON<CommentRecord[]>("GET", "/api/comments");

export const createComment = (body: CommentCreateBody) =>
  apiJSON<CommentRecord>("POST", "/api/comments", body);

export const updateComment = (id: string, text: string) =>
  apiJSON<CommentRecord>("PATCH", `/api/comments/${id}`, { text });

export const deleteComment = (id: string) => apiJSON<void>("DELETE", `/api/comments/${id}`);
