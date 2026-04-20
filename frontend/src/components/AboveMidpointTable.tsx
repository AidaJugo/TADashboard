/**
 * AboveMidpointTable — exceptions table for above-midpoint hires.
 *
 * FR-REPORT-5: shows position, seniority, salary, midpoint, gap, recruiter,
 * and the stored comment (FR-COMMENT-1).
 *
 * FR-COMMENT-1..4: editor and admin users can add, edit, and delete comments
 * inline via CommentCell.  Comments are keyed by (position, seniority, hub,
 * salary_eur) and loaded from /api/comments.
 *
 * Hub is shown in a group header above each hub's rows.
 */

import { tokens } from "@/theme/tokens";
import type { AboveMidpointEntry } from "@/api/report";
import { CommentCell } from "@/components/CommentCell";
import {
  useComments,
  useCreateComment,
  useUpdateComment,
  useDeleteComment,
} from "@/hooks/useComments";

interface AboveMidpointTableProps {
  entries: AboveMidpointEntry[];
  canEdit?: boolean;
}

function fmt(n: number | null): string {
  if (n == null) return "—";
  return Math.round(n).toLocaleString("en-GB");
}

function fmtPct(n: number | null): string {
  if (n == null) return "—";
  return `+${(n * 100).toFixed(1)}%`;
}

/** Derive the salary_eur integer key from the entry (matches backend schema). */
function salaryKey(n: number | null): number {
  return n != null ? Math.round(n) : 0;
}

export function AboveMidpointTable({ entries, canEdit = false }: AboveMidpointTableProps) {
  if (entries.length === 0) return null;

  const { data: comments } = useComments();
  const createComment = useCreateComment();
  const updateComment = useUpdateComment();
  const deleteComment = useDeleteComment();

  // Build a lookup: "position|seniority|hub|salary_eur" → CommentRecord
  const commentMap = new Map(
    (comments ?? []).map((c) => [`${c.position}|${c.seniority}|${c.hub}|${c.salary_eur}`, c]),
  );

  async function handleSave(
    hireKey: { position: string; seniority: string; hub: string; salary_eur: number },
    text: string,
    existingId?: string,
  ) {
    if (existingId) {
      await updateComment.mutateAsync({ id: existingId, text });
    } else {
      await createComment.mutateAsync({ ...hireKey, text });
    }
  }

  async function handleDelete(commentId: string) {
    await deleteComment.mutateAsync(commentId);
  }

  // Group by hub.
  const byHub = new Map<string, AboveMidpointEntry[]>();
  for (const entry of entries) {
    if (!byHub.has(entry.hub)) byHub.set(entry.hub, []);
    byHub.get(entry.hub)!.push(entry);
  }

  return (
    <div style={{ marginBottom: tokens.spacing.xl }} data-testid="above-midpoint-section">
      <div
        style={{
          fontSize: 15,
          fontWeight: 700,
          color: tokens.colors.black,
          marginBottom: tokens.spacing.md,
          fontFamily: tokens.typography.fontFamily,
        }}
      >
        Above mid-point — exceptions and justifications
      </div>

      {Array.from(byHub.entries()).map(([hub, rows]) => (
        <div key={hub} style={{ marginBottom: tokens.spacing.lg }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: tokens.spacing.sm,
              marginBottom: tokens.spacing.sm,
            }}
          >
            <span
              style={{
                fontSize: 13,
                fontWeight: 700,
                color: tokens.colors.black,
                fontFamily: tokens.typography.fontFamily,
              }}
            >
              {hub}
            </span>
            <span
              style={{
                background: tokens.colors.lightGrey,
                color: tokens.colors.black,
                border: `1px solid ${tokens.colors.red}`,
                fontSize: 10,
                fontWeight: 700,
                padding: `2px ${tokens.spacing.sm}px`,
                borderRadius: tokens.radius.md,
                fontFamily: tokens.typography.fontFamily,
              }}
            >
              {rows.length} hire{rows.length > 1 ? "s" : ""}
            </span>
          </div>

          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 12,
              background: tokens.colors.white,
              borderRadius: tokens.radius.md,
              overflow: "hidden",
              border: `1px solid ${tokens.colors.lightGrey}`,
              fontFamily: tokens.typography.fontFamily,
            }}
          >
            <thead>
              <tr style={{ background: tokens.colors.lightGrey }}>
                {[
                  "Position",
                  "Seniority",
                  "Salary (€)",
                  "Midpoint (€)",
                  "Gap (€)",
                  "Gap (%)",
                  "Recruiter",
                  "Justification",
                ].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: "9px 12px",
                      textAlign: ["Salary (€)", "Midpoint (€)", "Gap (€)", "Gap (%)"].includes(h)
                        ? "right"
                        : "left",
                      fontSize: 10.5,
                      fontWeight: 700,
                      color: tokens.colors.black,
                      textTransform: "uppercase",
                      letterSpacing: "0.4px",
                      borderBottom: `2px solid ${tokens.colors.lightGrey}`,
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, idx) => {
                const key = `${r.position}|${r.seniority}|${hub}|${salaryKey(r.salary)}`;
                const storedComment = commentMap.get(key);
                const commentText = storedComment?.text ?? r.comment ?? r.hire_note ?? "";

                return (
                  <tr
                    key={`${hub}-${r.position}-${r.seniority}-${r.salary ?? "x"}-${idx}`}
                    style={{
                      background: idx % 2 === 0 ? tokens.colors.white : tokens.colors.lightGrey,
                    }}
                  >
                    <td
                      style={{
                        padding: "10px 12px",
                        borderBottom: `1px solid ${tokens.colors.lightGrey}`,
                        color: tokens.colors.black,
                        fontWeight: 600,
                      }}
                    >
                      {r.position}
                    </td>
                    <td
                      style={{
                        padding: "10px 12px",
                        borderBottom: `1px solid ${tokens.colors.lightGrey}`,
                        color: tokens.colors.black,
                      }}
                    >
                      {r.seniority}
                    </td>
                    <td
                      style={{
                        padding: "10px 12px",
                        borderBottom: `1px solid ${tokens.colors.lightGrey}`,
                        color: tokens.colors.black,
                        textAlign: "right",
                      }}
                    >
                      {fmt(r.salary)}
                    </td>
                    <td
                      style={{
                        padding: "10px 12px",
                        borderBottom: `1px solid ${tokens.colors.lightGrey}`,
                        color: tokens.colors.black,
                        textAlign: "right",
                      }}
                    >
                      {fmt(r.midpoint)}
                    </td>
                    {/* gap_pct is stored as a decimal fraction (0.176 = 17.6%); × 100 applied in fmtPct. */}
                    <td
                      style={{
                        padding: "10px 12px",
                        borderBottom: `1px solid ${tokens.colors.lightGrey}`,
                        color: tokens.colors.black,
                        fontWeight: 700,
                        textAlign: "right",
                      }}
                    >
                      {r.gap_eur != null ? `+${fmt(r.gap_eur)}` : "—"}
                    </td>
                    <td
                      style={{
                        padding: "10px 12px",
                        borderBottom: `1px solid ${tokens.colors.lightGrey}`,
                        color: tokens.colors.black,
                        fontWeight: 700,
                        textAlign: "right",
                      }}
                    >
                      {fmtPct(r.gap_pct)}
                    </td>
                    <td
                      style={{
                        padding: "10px 12px",
                        borderBottom: `1px solid ${tokens.colors.lightGrey}`,
                        color: tokens.colors.black,
                      }}
                    >
                      {r.recruiter || "—"}
                    </td>
                    <td
                      style={{
                        padding: "10px 12px",
                        borderBottom: `1px solid ${tokens.colors.lightGrey}`,
                        verticalAlign: "top",
                        maxWidth: 320,
                      }}
                    >
                      <CommentCell
                        commentId={storedComment?.id}
                        commentText={commentText}
                        hireKey={{
                          position: r.position,
                          seniority: r.seniority,
                          hub,
                          salary_eur: salaryKey(r.salary),
                        }}
                        canEdit={canEdit}
                        onSave={handleSave}
                        onDelete={handleDelete}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
