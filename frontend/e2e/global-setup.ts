/**
 * Playwright global setup — seeds test users via POST /api/e2e/seed-session.
 *
 * Produces two storageState files so every spec can log in as:
 *   - e2e/auth/viewer.json      — unscoped viewer (sees all hubs)
 *   - e2e/auth/scoped-viewer.json — hub-scoped to Sarajevo + Skopje only
 *
 * The backend must be running at E2E_BACKEND_URL (default http://localhost:8001)
 * with APP_ENV=test for the /api/e2e/seed-session endpoint to be active.
 *
 * Session credentials are stored on disk so individual test files can load them
 * via `storageState` without repeating the seed call.
 */

import { mkdir, writeFile } from "fs/promises";
import path from "path";

const BACKEND = process.env.E2E_BACKEND_URL ?? "http://localhost:8001";
const FRONTEND = process.env.E2E_BASE_URL ?? "http://localhost:5173";

interface SeedResponse {
  session_id: string;
  cookie_name: string;
  cookie_value: string;
}

async function seedSession(params: {
  email: string;
  role: string;
  display_name: string;
  allowed_hubs: string[];
}): Promise<SeedResponse> {
  const res = await fetch(`${BACKEND}/api/e2e/seed-session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `seed-session failed (${res.status}): ${body}\n` +
        `Make sure the backend is running at ${BACKEND} with APP_ENV=test.`,
    );
  }

  return res.json() as Promise<SeedResponse>;
}

function makeStorageState(cookieName: string, cookieValue: string, frontendUrl: string): object {
  const { hostname } = new URL(frontendUrl);
  return {
    cookies: [
      {
        name: cookieName,
        value: cookieValue,
        domain: hostname,
        path: "/",
        httpOnly: true,
        secure: false, // SESSION_COOKIE_INSECURE=1 in test stack
        sameSite: "Lax" as const,
        expires: -1,
      },
    ],
    origins: [],
  };
}

export default async function globalSetup(): Promise<void> {
  const authDir = path.join(__dirname, "auth");
  await mkdir(authDir, { recursive: true });

  // --- Unscoped viewer (sees all hubs) ------------------------------------
  const viewer = await seedSession({
    email: "e2e-viewer@symphony.is",
    role: "viewer",
    display_name: "E2E Viewer",
    allowed_hubs: [],
  });
  await writeFile(
    path.join(authDir, "viewer.json"),
    JSON.stringify(makeStorageState(viewer.cookie_name, viewer.cookie_value, FRONTEND)),
  );

  // --- Hub-scoped viewer (Sarajevo + Skopje only) -------------------------
  const scoped = await seedSession({
    email: "e2e-scoped@symphony.is",
    role: "viewer",
    display_name: "E2E Scoped Viewer",
    allowed_hubs: ["Sarajevo", "Skopje"],
  });
  await writeFile(
    path.join(authDir, "scoped-viewer.json"),
    JSON.stringify(makeStorageState(scoped.cookie_name, scoped.cookie_value, FRONTEND)),
  );

  // --- Admin user (for refresh test) --------------------------------------
  const admin = await seedSession({
    email: "e2e-admin@symphony.is",
    role: "admin",
    display_name: "E2E Admin",
    allowed_hubs: [],
  });
  await writeFile(
    path.join(authDir, "admin.json"),
    JSON.stringify(makeStorageState(admin.cookie_name, admin.cookie_value, FRONTEND)),
  );

  console.log("E2E sessions seeded.");
}
