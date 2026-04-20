/**
 * CommentCell — inline comment Add / Edit / Delete for the above-midpoint
 * exceptions table (FR-COMMENT-1..4).
 *
 * The cell shows:
 *  - The current comment text (italic), with Edit and Delete buttons.
 *  - An inline textarea when editing / adding.
 *  - "Add justification" when no comment exists (editor/admin only).
 *
 * Props:
 *  - commentId    — undefined when no comment exists yet
 *  - commentText  — current text ("" when no comment)
 *  - hireKey      — {position, seniority, hub, salary_eur} for POST create
 *  - canEdit      — true for editor + admin roles
 *  - onSave       — called after create or update succeeds
 *  - onDelete     — called after delete succeeds
 */

import { useState } from "react";
import type React from "react";
import { tokens } from "@/theme/tokens";

interface HireKey {
  position: string;
  seniority: string;
  hub: string;
  salary_eur: number;
}

interface CommentCellProps {
  commentId?: string | undefined;
  commentText: string;
  hireKey: HireKey;
  canEdit: boolean;
  onSave: (hireKey: HireKey, text: string, existingId?: string) => Promise<void>;
  onDelete: (commentId: string) => Promise<void>;
}

const ghostBtn: React.CSSProperties = {
  background: "none",
  border: "none",
  cursor: "pointer",
  padding: "2px 4px",
  fontSize: 11,
  fontFamily: tokens.typography.fontFamily,
  color: tokens.colors.black,
  fontWeight: 600,
  textDecoration: "underline",
};

const deleteBtn: React.CSSProperties = {
  ...ghostBtn,
  textDecoration: "underline",
};

const textarea: React.CSSProperties = {
  width: "100%",
  fontSize: 11,
  fontFamily: tokens.typography.fontFamily,
  color: tokens.colors.black,
  border: `1px solid ${tokens.colors.primary}`,
  borderRadius: tokens.radius.sm,
  padding: "4px 6px",
  resize: "vertical",
  boxSizing: "border-box",
};

const saveBtn: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  fontFamily: tokens.typography.fontFamily,
  padding: "3px 8px",
  background: tokens.colors.primary,
  color: tokens.colors.white,
  border: "none",
  borderRadius: tokens.radius.sm,
  cursor: "pointer",
  marginRight: tokens.spacing.xs,
};

const cancelBtn: React.CSSProperties = {
  fontSize: 11,
  fontFamily: tokens.typography.fontFamily,
  padding: "3px 8px",
  background: "none",
  color: tokens.colors.black,
  border: `1px solid ${tokens.colors.blueGrey}`,
  borderRadius: tokens.radius.sm,
  cursor: "pointer",
};

export function CommentCell({
  commentId,
  commentText,
  hireKey,
  canEdit,
  onSave,
  onDelete,
}: CommentCellProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(commentText);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (!draft.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(hireKey, draft.trim(), commentId);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!commentId) return;
    setSaving(true);
    setError(null);
    try {
      await onDelete(commentId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setSaving(false);
    }
  }

  function handleEdit() {
    setDraft(commentText);
    setEditing(true);
    setError(null);
  }

  function handleCancel() {
    setDraft(commentText);
    setEditing(false);
    setError(null);
  }

  if (editing) {
    return (
      <div>
        <textarea
          style={textarea}
          rows={3}
          maxLength={500}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          aria-label="Edit justification"
          disabled={saving}
        />
        <div style={{ display: "flex", gap: tokens.spacing.xs, marginTop: 4 }}>
          <button style={saveBtn} onClick={handleSave} disabled={saving || !draft.trim()}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button style={cancelBtn} onClick={handleCancel} disabled={saving}>
            Cancel
          </button>
        </div>
        {error && (
          <p
            style={{
              color: tokens.colors.black,
              fontSize: 10,
              fontFamily: tokens.typography.fontFamily,
              marginTop: 2,
            }}
          >
            {error}
          </p>
        )}
      </div>
    );
  }

  if (commentText) {
    return (
      <div>
        <span
          style={{
            fontSize: 11.5,
            color: tokens.colors.black,
            fontStyle: "italic",
            fontFamily: tokens.typography.fontFamily,
          }}
        >
          {commentText}
        </span>
        {canEdit && (
          <div style={{ display: "flex", gap: 0, marginTop: 2 }}>
            <button style={ghostBtn} onClick={handleEdit} aria-label="Edit justification">
              Edit
            </button>
            <button
              style={deleteBtn}
              onClick={handleDelete}
              disabled={saving}
              aria-label="Remove justification"
            >
              {saving ? "…" : "Remove"}
            </button>
          </div>
        )}
        {error && (
          <p
            style={{
              color: tokens.colors.black,
              fontSize: 10,
              fontFamily: tokens.typography.fontFamily,
            }}
          >
            {error}
          </p>
        )}
      </div>
    );
  }

  if (!canEdit) {
    return <span style={{ color: tokens.colors.black, fontSize: 11 }}>—</span>;
  }

  return (
    <div>
      <button style={ghostBtn} onClick={handleEdit} aria-label="Add justification">
        + Add justification
      </button>
      {error && (
        <p
          style={{
            color: tokens.colors.black,
            fontSize: 10,
            fontFamily: tokens.typography.fontFamily,
          }}
        >
          {error}
        </p>
      )}
    </div>
  );
}
