/**
 * API client for admin endpoints.
 *
 * All mutating calls read the CSRF token from the ta_csrf cookie and attach
 * it as X-CSRF-Token.  This mirrors the same pattern used in postRefresh.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UserRecord {
  id: string;
  email: string;
  display_name: string;
  role: "admin" | "editor" | "viewer";
  is_active: boolean;
  allowed_hubs: string[];
  created_at: string;
  updated_at: string;
}

export interface UserCreateBody {
  email: string;
  display_name: string;
  role: "admin" | "editor" | "viewer";
  allowed_hubs: string[];
}

export interface UserUpdateBody {
  display_name?: string;
  role?: "admin" | "editor" | "viewer";
  allowed_hubs?: string[];
}

export interface ConfigRecord {
  spreadsheet_id: string;
  spreadsheet_tab_name: string;
  audit_retention_months: number;
  backup_retention_days: number;
  column_mappings: Record<string, string>;
}

export interface ConfigUpdateBody {
  spreadsheet_id?: string;
  spreadsheet_tab_name?: string;
  column_mappings?: Record<string, string>;
}

export interface RetentionUpdateBody {
  audit_retention_months?: number;
  backup_retention_days?: number;
}

export interface HubPairRecord {
  id: string;
  city_name: string;
  hub_name: string;
}

export interface HubPairCreateBody {
  city_name: string;
  hub_name: string;
}

export interface HubPairUpdateBody {
  city_name?: string;
  hub_name?: string;
}

// ---------------------------------------------------------------------------
// CSRF helper
// ---------------------------------------------------------------------------

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
    throw new Error(`API ${method} ${path}: ${res.status} — ${detail}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export const listUsers = () => apiJSON<UserRecord[]>("GET", "/api/admin/users");

export const createUser = (body: UserCreateBody) =>
  apiJSON<UserRecord>("POST", "/api/admin/users", body);

export const updateUser = (id: string, body: UserUpdateBody) =>
  apiJSON<UserRecord>("PATCH", `/api/admin/users/${id}`, body);

export const deactivateUser = (id: string) =>
  apiJSON<void>("POST", `/api/admin/users/${id}/deactivate`);

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export const getConfig = () => apiJSON<ConfigRecord>("GET", "/api/admin/config");

export const updateConfig = (body: ConfigUpdateBody) =>
  apiJSON<ConfigRecord>("POST", "/api/admin/config", body);

export const updateRetention = (body: RetentionUpdateBody) =>
  apiJSON<ConfigRecord>("PATCH", "/api/admin/config/retention", body);

// ---------------------------------------------------------------------------
// Hub pairs
// ---------------------------------------------------------------------------

export const listHubPairs = () => apiJSON<HubPairRecord[]>("GET", "/api/admin/hub-pairs");

export const createHubPair = (body: HubPairCreateBody) =>
  apiJSON<HubPairRecord>("POST", "/api/admin/hub-pairs", body);

export const updateHubPair = (id: string, body: HubPairUpdateBody) =>
  apiJSON<HubPairRecord>("PATCH", `/api/admin/hub-pairs/${id}`, body);

export const deleteHubPair = (id: string) => apiJSON<void>("DELETE", `/api/admin/hub-pairs/${id}`);
