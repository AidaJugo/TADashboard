/**
 * AdminUsersPage — list, add, edit role/hubs, and deactivate users.
 *
 * FR-USER-1..3 | TC-I-API-10 (last-admin guard) | TC-E-12 (409 UI block)
 */

import { useState } from "react";
import type React from "react";
import { tokens } from "@/theme/tokens";
import { useUsers, useCreateUser, useUpdateUser, useDeactivateUser } from "@/hooks/useAdmin";
import type { UserRecord } from "@/api/admin";

// ---------------------------------------------------------------------------
// Shared cell/button styles
// ---------------------------------------------------------------------------

const sectionTitle: React.CSSProperties = {
  fontSize: 17,
  fontWeight: 700,
  color: tokens.colors.black,
  marginBottom: tokens.spacing.md,
};

const table: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 13,
  background: tokens.colors.white,
  borderRadius: tokens.radius.md,
  overflow: "hidden",
  border: `1px solid ${tokens.colors.lightGrey}`,
};

const th: React.CSSProperties = {
  padding: "10px 14px",
  textAlign: "left",
  fontSize: 11,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.4px",
  background: tokens.colors.lightGrey,
  color: tokens.colors.black,
  borderBottom: `1px solid ${tokens.colors.lightGrey}`,
};

const td: React.CSSProperties = {
  padding: "10px 14px",
  color: tokens.colors.black,
  borderBottom: `1px solid ${tokens.colors.lightGrey}`,
  verticalAlign: "middle",
};

const primaryBtn: React.CSSProperties = {
  padding: "6px 14px",
  fontSize: 13,
  fontWeight: 600,
  fontFamily: tokens.typography.fontFamily,
  background: tokens.colors.primary,
  color: tokens.colors.white,
  border: "none",
  borderRadius: tokens.radius.sm,
  cursor: "pointer",
};

const dangerBtn: React.CSSProperties = {
  ...primaryBtn,
  background: tokens.colors.red,
};

const ghostBtn: React.CSSProperties = {
  padding: "5px 10px",
  fontSize: 12,
  fontWeight: 600,
  fontFamily: tokens.typography.fontFamily,
  background: "none",
  color: tokens.colors.black,
  border: `1px solid ${tokens.colors.primary}`,
  borderRadius: tokens.radius.sm,
  cursor: "pointer",
};

const inputStyle: React.CSSProperties = {
  padding: "6px 10px",
  fontSize: 13,
  fontFamily: tokens.typography.fontFamily,
  border: `1px solid ${tokens.colors.blueGrey}`,
  borderRadius: tokens.radius.sm,
  color: tokens.colors.black,
  width: "100%",
  boxSizing: "border-box",
};

const selectStyle: React.CSSProperties = { ...inputStyle, width: "auto" };

const errorMsg: React.CSSProperties = {
  color: tokens.colors.black,
  fontSize: 12,
  fontFamily: tokens.typography.fontFamily,
  marginTop: tokens.spacing.xs,
  borderLeft: `3px solid ${tokens.colors.red}`,
  paddingLeft: tokens.spacing.xs,
};

// ---------------------------------------------------------------------------
// AddUserForm
// ---------------------------------------------------------------------------

function AddUserForm({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<"admin" | "editor" | "viewer">("viewer");
  const [hubs, setHubs] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useCreateUser();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({
        email,
        display_name: displayName,
        role,
        allowed_hubs: hubs
          .split(",")
          .map((h) => h.trim())
          .filter(Boolean),
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add user.");
    }
  }

  const formCard: React.CSSProperties = {
    background: tokens.colors.white,
    border: `1px solid ${tokens.colors.lightGrey}`,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.lg,
    marginBottom: tokens.spacing.xl,
  };

  const formGrid: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: tokens.spacing.md,
    marginBottom: tokens.spacing.md,
  };

  const label: React.CSSProperties = {
    display: "block",
    fontSize: 12,
    fontWeight: 600,
    fontFamily: tokens.typography.fontFamily,
    color: tokens.colors.black,
    marginBottom: tokens.spacing.xs,
  };

  return (
    <div style={formCard}>
      <p style={{ ...sectionTitle, marginBottom: tokens.spacing.md, fontSize: 15 }}>Add user</p>
      <form onSubmit={handleSubmit}>
        <div style={formGrid}>
          <div>
            <label style={label} htmlFor="new-email">
              Email
            </label>
            <input
              id="new-email"
              style={inputStyle}
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label style={label} htmlFor="new-display-name">
              Display name
            </label>
            <input
              id="new-display-name"
              style={inputStyle}
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
          <div>
            <label style={label} htmlFor="new-role">
              Role
            </label>
            <select
              id="new-role"
              style={selectStyle}
              value={role}
              onChange={(e) => setRole(e.target.value as typeof role)}
            >
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div>
            <label style={label} htmlFor="new-hubs">
              Allowed hubs (comma-separated, blank = all)
            </label>
            <input
              id="new-hubs"
              style={inputStyle}
              value={hubs}
              onChange={(e) => setHubs(e.target.value)}
              placeholder="Sarajevo, Belgrade"
            />
          </div>
        </div>
        {error && <p style={errorMsg}>{error}</p>}
        <div style={{ display: "flex", gap: tokens.spacing.sm, marginTop: tokens.spacing.md }}>
          <button style={primaryBtn} type="submit" disabled={create.isPending}>
            {create.isPending ? "Adding…" : "Add user"}
          </button>
          <button
            style={{ ...ghostBtn }}
            type="button"
            onClick={onClose}
            disabled={create.isPending}
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EditUserRow — inline edit inside the table
// ---------------------------------------------------------------------------

function EditUserRow({ user, onDone }: { user: UserRecord; onDone: () => void }) {
  const [displayName, setDisplayName] = useState(user.display_name);
  const [role, setRole] = useState(user.role);
  const [hubs, setHubs] = useState(user.allowed_hubs.join(", "));
  const [error, setError] = useState<string | null>(null);

  const update = useUpdateUser();

  async function handleSave() {
    setError(null);
    try {
      await update.mutateAsync({
        id: user.id,
        body: {
          display_name: displayName,
          role,
          allowed_hubs: hubs
            .split(",")
            .map((h) => h.trim())
            .filter(Boolean),
        },
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed.");
    }
  }

  return (
    <tr style={{ background: tokens.colors.peach }}>
      <td style={td}>
        <input
          style={{ ...inputStyle, width: 180 }}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          aria-label="Display name"
        />
      </td>
      <td style={td}>{user.email}</td>
      <td style={td}>
        <select
          style={selectStyle}
          value={role}
          onChange={(e) => setRole(e.target.value as typeof role)}
          aria-label="Role"
        >
          <option value="viewer">Viewer</option>
          <option value="editor">Editor</option>
          <option value="admin">Admin</option>
        </select>
      </td>
      <td style={td}>
        <input
          style={{ ...inputStyle, width: 200 }}
          value={hubs}
          onChange={(e) => setHubs(e.target.value)}
          placeholder="Blank = all"
          aria-label="Allowed hubs"
        />
      </td>
      <td style={{ ...td, textAlign: "center" }}>{user.is_active ? "Active" : "Inactive"}</td>
      <td style={{ ...td }}>
        {error && <p style={{ ...errorMsg, marginBottom: 4 }}>{error}</p>}
        <div style={{ display: "flex", gap: tokens.spacing.xs }}>
          <button style={primaryBtn} onClick={handleSave} disabled={update.isPending}>
            {update.isPending ? "Saving…" : "Save"}
          </button>
          <button style={ghostBtn} onClick={onDone} disabled={update.isPending}>
            Cancel
          </button>
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// AdminUsersPage
// ---------------------------------------------------------------------------

export function AdminUsersPage() {
  const { data: users, isLoading, isError } = useUsers();
  const deactivate = useDeactivateUser();
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);

  async function handleDeactivate(user: UserRecord) {
    setDeactivateError(null);
    if (!window.confirm(`Deactivate ${user.email}? This cannot be undone.`)) return;
    try {
      await deactivate.mutateAsync(user.id);
    } catch (err) {
      setDeactivateError(err instanceof Error ? err.message : "Deactivation failed.");
    }
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: tokens.spacing.lg,
        }}
      >
        <h2 style={sectionTitle}>Users</h2>
        {!showAdd && (
          <button style={primaryBtn} onClick={() => setShowAdd(true)}>
            Add user
          </button>
        )}
      </div>

      {showAdd && <AddUserForm onClose={() => setShowAdd(false)} />}

      {isLoading && <p>Loading users…</p>}
      {isError && <p style={errorMsg}>Failed to load users. Please refresh.</p>}
      {deactivateError && <p style={errorMsg}>{deactivateError}</p>}

      {users && (
        <table style={table} aria-label="User list">
          <thead>
            <tr>
              {["Name", "Email", "Role", "Allowed hubs", "Status", "Actions"].map((h) => (
                <th key={h} style={th}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map((user, idx) =>
              editingId === user.id ? (
                <EditUserRow key={user.id} user={user} onDone={() => setEditingId(null)} />
              ) : (
                <tr
                  key={user.id}
                  style={{
                    background: !user.is_active
                      ? tokens.colors.lightGrey
                      : idx % 2 === 0
                        ? tokens.colors.white
                        : tokens.colors.lightGrey,
                    opacity: user.is_active ? 1 : 0.55,
                  }}
                >
                  <td style={{ ...td, fontWeight: 600 }}>{user.display_name}</td>
                  <td style={td}>{user.email}</td>
                  <td style={td}>{user.role}</td>
                  <td style={td}>
                    {user.allowed_hubs.length > 0 ? user.allowed_hubs.join(", ") : "All"}
                  </td>
                  <td style={{ ...td, textAlign: "center" }}>
                    <span
                      style={{
                        display: "inline-block",
                        padding: "2px 8px",
                        borderRadius: 10,
                        fontSize: 11,
                        fontWeight: 700,
                        background: user.is_active ? tokens.colors.primary : tokens.colors.blueGrey,
                        color: tokens.colors.white,
                      }}
                    >
                      {user.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td style={td}>
                    <div style={{ display: "flex", gap: tokens.spacing.xs }}>
                      {user.is_active && (
                        <>
                          <button
                            style={ghostBtn}
                            onClick={() => setEditingId(user.id)}
                            aria-label={`Edit ${user.email}`}
                          >
                            Edit
                          </button>
                          <button
                            style={dangerBtn}
                            onClick={() => handleDeactivate(user)}
                            disabled={deactivate.isPending}
                            aria-label={`Deactivate ${user.email}`}
                          >
                            Deactivate
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
