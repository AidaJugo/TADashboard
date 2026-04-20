/**
 * AdminConfigPage — manage spreadsheet config, column mappings, hub pairs,
 * and retention windows.
 *
 * FR-CONFIG-1..5 | TC-I-API-5 (spreadsheet validation) | TC-I-API-13 (retention bounds)
 */

import { useState } from "react";
import type React from "react";
import { tokens } from "@/theme/tokens";
import {
  useConfig,
  useUpdateConfig,
  useUpdateRetention,
  useHubPairs,
  useCreateHubPair,
  useUpdateHubPair,
  useDeleteHubPair,
} from "@/hooks/useAdmin";
import type { HubPairRecord, RetentionUpdateBody } from "@/api/admin";

// ---------------------------------------------------------------------------
// Shared styles (same palette as UsersPage)
// ---------------------------------------------------------------------------

const sectionCard: React.CSSProperties = {
  background: tokens.colors.white,
  border: `1px solid ${tokens.colors.lightGrey}`,
  borderRadius: tokens.radius.md,
  padding: tokens.spacing.lg,
  marginBottom: tokens.spacing.xl,
};

const sectionTitle: React.CSSProperties = {
  fontSize: 17,
  fontWeight: 700,
  color: tokens.colors.black,
  margin: `0 0 ${tokens.spacing.md}px`,
};

const formGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: tokens.spacing.md,
};

const label: React.CSSProperties = {
  display: "block",
  fontSize: 12,
  fontWeight: 600,
  fontFamily: tokens.typography.fontFamily,
  color: tokens.colors.black,
  marginBottom: tokens.spacing.xs,
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

const errorMsg: React.CSSProperties = {
  color: tokens.colors.black,
  fontSize: 12,
  fontFamily: tokens.typography.fontFamily,
  marginTop: tokens.spacing.xs,
  borderLeft: `3px solid ${tokens.colors.red}`,
  paddingLeft: tokens.spacing.xs,
};

const successMsg: React.CSSProperties = {
  color: tokens.colors.black,
  fontSize: 12,
  fontFamily: tokens.typography.fontFamily,
  marginTop: tokens.spacing.xs,
  borderLeft: `3px solid ${tokens.colors.primary}`,
  paddingLeft: tokens.spacing.xs,
};

// ---------------------------------------------------------------------------
// SpreadsheetConfigSection
// ---------------------------------------------------------------------------

function SpreadsheetConfigSection() {
  const { data: config } = useConfig();
  const updateConfig = useUpdateConfig();

  const [spreadsheetId, setSpreadsheetId] = useState("");
  const [tabName, setTabName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Sync form state from fetched config when it first loads.
  const [seeded, setSeeded] = useState(false);
  if (config && !seeded) {
    setSpreadsheetId(config.spreadsheet_id);
    setTabName(config.spreadsheet_tab_name);
    setSeeded(true);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    try {
      await updateConfig.mutateAsync({
        spreadsheet_id: spreadsheetId,
        spreadsheet_tab_name: tabName,
      });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    }
  }

  return (
    <div style={sectionCard}>
      <h3 style={sectionTitle}>Spreadsheet</h3>
      <form onSubmit={handleSave}>
        <div style={formGrid}>
          <div>
            <label style={label} htmlFor="spreadsheet-id">
              Spreadsheet ID
            </label>
            <input
              id="spreadsheet-id"
              style={inputStyle}
              value={spreadsheetId}
              onChange={(e) => setSpreadsheetId(e.target.value)}
              required
            />
          </div>
          <div>
            <label style={label} htmlFor="tab-name">
              Tab name
            </label>
            <input
              id="tab-name"
              style={inputStyle}
              value={tabName}
              onChange={(e) => setTabName(e.target.value)}
              required
            />
          </div>
        </div>
        {error && <p style={errorMsg}>{error}</p>}
        {success && <p style={successMsg}>Saved.</p>}
        <div style={{ marginTop: tokens.spacing.md }}>
          <button style={primaryBtn} type="submit" disabled={updateConfig.isPending}>
            {updateConfig.isPending ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RetentionSection
// ---------------------------------------------------------------------------

function RetentionSection() {
  const { data: config } = useConfig();
  const updateRetention = useUpdateRetention();

  const [auditMonths, setAuditMonths] = useState<number | "">("");
  const [backupDays, setBackupDays] = useState<number | "">("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [seeded, setSeeded] = useState(false);
  if (config && !seeded) {
    setAuditMonths(config.audit_retention_months);
    setBackupDays(config.backup_retention_days);
    setSeeded(true);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    try {
      const body: RetentionUpdateBody = {};
      if (auditMonths !== "") body.audit_retention_months = Number(auditMonths);
      if (backupDays !== "") body.backup_retention_days = Number(backupDays);
      await updateRetention.mutateAsync(body);
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    }
  }

  return (
    <div style={sectionCard}>
      <h3 style={sectionTitle}>Retention windows</h3>
      <form onSubmit={handleSave}>
        <div style={formGrid}>
          <div>
            <label style={label} htmlFor="audit-months">
              Audit log retention (months, 6–60)
            </label>
            <input
              id="audit-months"
              style={{ ...inputStyle, width: 120 }}
              type="number"
              min={6}
              max={60}
              value={auditMonths}
              onChange={(e) => setAuditMonths(e.target.value === "" ? "" : Number(e.target.value))}
              required
            />
          </div>
          <div>
            <label style={label} htmlFor="backup-days">
              Backup retention (days, 7–90)
            </label>
            <input
              id="backup-days"
              style={{ ...inputStyle, width: 120 }}
              type="number"
              min={7}
              max={90}
              value={backupDays}
              onChange={(e) => setBackupDays(e.target.value === "" ? "" : Number(e.target.value))}
              required
            />
          </div>
        </div>
        {error && <p style={errorMsg}>{error}</p>}
        {success && <p style={successMsg}>Saved.</p>}
        <div style={{ marginTop: tokens.spacing.md }}>
          <button style={primaryBtn} type="submit" disabled={updateRetention.isPending}>
            {updateRetention.isPending ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ColumnMappingSection
// ---------------------------------------------------------------------------

const REQUIRED_LOGICAL: string[] = [
  "Position",
  "Seniority",
  "City",
  "Salary",
  "Midpoint",
  "Gap_EUR",
  "Gap_PCT",
  "Status",
  "Month",
  "Type",
];

const OPTIONAL_LOGICAL: string[] = ["Year", "Recruiter", "Note"];

const ALL_LOGICAL = [...REQUIRED_LOGICAL, ...OPTIONAL_LOGICAL];

const DEFAULT_MAPPING: Record<string, string> = {
  Position: "Position",
  Seniority: "Seniority",
  City: "City",
  Salary: "Salary",
  Midpoint: "Midpoint",
  Gap_EUR: "Gap_EUR",
  Gap_PCT: "Gap_PCT",
  Status: "Status",
  Month: "Month",
  Type: "Type",
  Year: "Year",
  Recruiter: "Recruiter",
  Note: "Note",
};

function ColumnMappingSection() {
  const { data: config } = useConfig();
  const updateConfig = useUpdateConfig();

  const [values, setValues] = useState<Record<string, string>>({});
  const [seeded, setSeeded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  if (config && !seeded) {
    const initial: Record<string, string> = {};
    for (const key of ALL_LOGICAL) {
      initial[key] = config.column_mappings[key] ?? DEFAULT_MAPPING[key] ?? "";
    }
    setValues(initial);
    setSeeded(true);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    try {
      await updateConfig.mutateAsync({ column_mappings: values });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    }
  }

  const thStyle: React.CSSProperties = {
    padding: "8px 12px",
    textAlign: "left",
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    background: tokens.colors.lightGrey,
    color: tokens.colors.black,
    borderBottom: `1px solid ${tokens.colors.lightGrey}`,
  };

  const tdStyle: React.CSSProperties = {
    padding: "7px 12px",
    color: tokens.colors.black,
    borderBottom: `1px solid ${tokens.colors.lightGrey}`,
    verticalAlign: "middle",
  };

  return (
    <div style={sectionCard}>
      <h3 style={sectionTitle}>Column mapping</h3>
      <p style={{ fontSize: 13, color: tokens.colors.black, marginBottom: tokens.spacing.md }}>
        Map each logical field to the exact column header in your Google Sheet. Required fields must
        match a column header. Optional fields can be left blank.
      </p>
      <form onSubmit={handleSave}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: 13,
            border: `1px solid ${tokens.colors.lightGrey}`,
            borderRadius: tokens.radius.md,
            overflow: "hidden",
            marginBottom: tokens.spacing.md,
          }}
          aria-label="Column mapping"
        >
          <thead>
            <tr>
              <th style={thStyle}>Logical field</th>
              <th style={thStyle}>Sheet column header</th>
              <th style={thStyle}>Required</th>
            </tr>
          </thead>
          <tbody>
            {ALL_LOGICAL.map((key, idx) => {
              const isRequired = REQUIRED_LOGICAL.includes(key);
              return (
                <tr
                  key={key}
                  style={{
                    background: idx % 2 === 0 ? tokens.colors.white : tokens.colors.lightGrey,
                  }}
                >
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{key}</td>
                  <td style={tdStyle}>
                    <input
                      style={{ ...inputStyle, width: 260 }}
                      value={values[key] ?? ""}
                      onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
                      placeholder={isRequired ? "required" : "optional"}
                      required={isRequired}
                      aria-label={`Sheet header for ${key}`}
                    />
                  </td>
                  <td
                    style={{
                      ...tdStyle,
                      color: isRequired ? tokens.colors.black : tokens.colors.blueGrey,
                    }}
                  >
                    {isRequired ? "Yes" : "No"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {error && <p style={errorMsg}>{error}</p>}
        {success && <p style={successMsg}>Saved.</p>}
        <button style={primaryBtn} type="submit" disabled={updateConfig.isPending}>
          {updateConfig.isPending ? "Saving…" : "Save mapping"}
        </button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// HubPairsSection
// ---------------------------------------------------------------------------

function HubPairsSection() {
  const { data: pairs, isLoading } = useHubPairs();
  const create = useCreateHubPair();
  const update = useUpdateHubPair();
  const remove = useDeleteHubPair();

  const [newCity, setNewCity] = useState("");
  const [newHub, setNewHub] = useState("");
  const [addError, setAddError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editCity, setEditCity] = useState("");
  const [editHub, setEditHub] = useState("");
  const [editError, setEditError] = useState<string | null>(null);

  function startEdit(pair: HubPairRecord) {
    setEditingId(pair.id);
    setEditCity(pair.city_name);
    setEditHub(pair.hub_name);
    setEditError(null);
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setAddError(null);
    try {
      await create.mutateAsync({ city_name: newCity.trim(), hub_name: newHub.trim() });
      setNewCity("");
      setNewHub("");
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Failed to add hub pair.");
    }
  }

  async function handleUpdate() {
    if (!editingId) return;
    setEditError(null);
    try {
      await update.mutateAsync({
        id: editingId,
        body: { city_name: editCity.trim(), hub_name: editHub.trim() },
      });
      setEditingId(null);
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Update failed.");
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm("Remove this hub pair?")) return;
    try {
      await remove.mutateAsync(id);
    } catch {
      // Error surfacing handled by query state
    }
  }

  const tableStyle: React.CSSProperties = {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13,
    background: tokens.colors.white,
    border: `1px solid ${tokens.colors.lightGrey}`,
    borderRadius: tokens.radius.md,
    overflow: "hidden",
    marginBottom: tokens.spacing.lg,
  };

  const thStyle: React.CSSProperties = {
    padding: "9px 12px",
    textAlign: "left",
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    background: tokens.colors.lightGrey,
    color: tokens.colors.black,
    borderBottom: `1px solid ${tokens.colors.lightGrey}`,
  };

  const tdStyle: React.CSSProperties = {
    padding: "9px 12px",
    color: tokens.colors.black,
    borderBottom: `1px solid ${tokens.colors.lightGrey}`,
    verticalAlign: "middle",
  };

  return (
    <div style={sectionCard}>
      <h3 style={sectionTitle}>Hub pairs</h3>
      <p
        style={{
          fontSize: 13,
          color: tokens.colors.black,
          marginBottom: tokens.spacing.md,
        }}
      >
        Each row maps a city name (as it appears in the Sheet) to the canonical hub name shown in
        the report.
      </p>

      {isLoading && <p>Loading…</p>}

      {pairs && (
        <table style={tableStyle} aria-label="Hub pairs">
          <thead>
            <tr>
              {["City (Sheet value)", "Hub (report display)", ""].map((h) => (
                <th key={h} style={thStyle}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pairs.map((pair, idx) =>
              editingId === pair.id ? (
                <tr key={pair.id} style={{ background: tokens.colors.peach }}>
                  <td style={tdStyle}>
                    <input
                      style={{ ...inputStyle, width: 160 }}
                      value={editCity}
                      onChange={(e) => setEditCity(e.target.value)}
                      aria-label="City name"
                    />
                  </td>
                  <td style={tdStyle}>
                    <input
                      style={{ ...inputStyle, width: 160 }}
                      value={editHub}
                      onChange={(e) => setEditHub(e.target.value)}
                      aria-label="Hub name"
                    />
                  </td>
                  <td style={tdStyle}>
                    {editError && <p style={errorMsg}>{editError}</p>}
                    <div style={{ display: "flex", gap: tokens.spacing.xs }}>
                      <button style={primaryBtn} onClick={handleUpdate} disabled={update.isPending}>
                        Save
                      </button>
                      <button
                        style={ghostBtn}
                        onClick={() => setEditingId(null)}
                        disabled={update.isPending}
                      >
                        Cancel
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr
                  key={pair.id}
                  style={{
                    background: idx % 2 === 0 ? tokens.colors.white : tokens.colors.lightGrey,
                  }}
                >
                  <td style={tdStyle}>{pair.city_name}</td>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{pair.hub_name}</td>
                  <td style={tdStyle}>
                    <div style={{ display: "flex", gap: tokens.spacing.xs }}>
                      <button
                        style={ghostBtn}
                        onClick={() => startEdit(pair)}
                        aria-label={`Edit ${pair.city_name}`}
                      >
                        Edit
                      </button>
                      <button
                        style={dangerBtn}
                        onClick={() => handleDelete(pair.id)}
                        disabled={remove.isPending}
                        aria-label={`Delete ${pair.city_name}`}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      )}

      <form onSubmit={handleAdd}>
        <p
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: tokens.colors.black,
            marginBottom: tokens.spacing.sm,
          }}
        >
          Add hub pair
        </p>
        <div style={{ display: "flex", gap: tokens.spacing.md, alignItems: "flex-end" }}>
          <div>
            <label style={label} htmlFor="new-city">
              City name
            </label>
            <input
              id="new-city"
              style={{ ...inputStyle, width: 180 }}
              value={newCity}
              onChange={(e) => setNewCity(e.target.value)}
              required
            />
          </div>
          <div>
            <label style={label} htmlFor="new-hub">
              Hub name
            </label>
            <input
              id="new-hub"
              style={{ ...inputStyle, width: 180 }}
              value={newHub}
              onChange={(e) => setNewHub(e.target.value)}
              required
            />
          </div>
          <button style={primaryBtn} type="submit" disabled={create.isPending}>
            {create.isPending ? "Adding…" : "Add"}
          </button>
        </div>
        {addError && <p style={errorMsg}>{addError}</p>}
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AdminConfigPage
// ---------------------------------------------------------------------------

export function AdminConfigPage() {
  return (
    <div>
      <h2
        style={{
          fontSize: 17,
          fontWeight: 700,
          color: tokens.colors.black,
          marginBottom: tokens.spacing.lg,
        }}
      >
        Config &amp; hub pairs
      </h2>
      <SpreadsheetConfigSection />
      <ColumnMappingSection />
      <HubPairsSection />
      <RetentionSection />
    </div>
  );
}
