import type React from "react";

import { StatusStepper, statusStageLabel } from "../../../components/ui/StatusStepper";
import { staffRequest } from "../../../lib/api";
import type { HardwareRequest } from "./Queues";

// Evidence object keys are never exposed; fetch a short-lived signed URL on click and open it.
async function openEvidence(id: number) {
  try {
    const res = await staffRequest<{ url: string }>(`/admin/evidence/${id}`);
    window.open(res.url, "_blank", "noopener");
  } catch (error) {
    window.alert(error instanceof Error ? error.message : "Could not load evidence photo.");
  }
}

export function RequestList({ rows, actions }: { rows: HardwareRequest[]; actions: (row: HardwareRequest) => React.ReactNode }) {
  if (!rows.length) return <p className="text-sm text-ink/60">No requests.</p>;
  return (
    <div className="overflow-hidden rounded-md border border-line">
      {rows.map((row) => (
        <article key={row.id} className="border-b border-line bg-surface/50 p-3 last:border-b-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-ink">#{row.id} {row.requester_username}</h3>
            <span className={`rounded-md border px-2 py-0.5 text-xs font-medium ${statusBadgeClassName(row.status)}`}>
              {statusStageLabel(row.status)}
            </span>
            <div className="desk-actions ml-auto flex flex-wrap gap-2 text-sm">
              {actions(row)}
            </div>
          </div>
          <div className="mt-3 max-w-md">
            <StatusStepper status={row.status} />
          </div>
          <p className="mt-2 text-sm text-muted">{row.requested_for || "No note"}</p>
          {row.requester_contact_email || row.requester_contact_phone ? (
            <p className="mt-1 text-xs text-muted">
              <span className="font-medium text-ink">Contact: </span>
              {[row.requester_contact_email, row.requester_contact_phone].filter(Boolean).join(" · ")}
            </p>
          ) : null}
          {row.status === "rejected" && row.rejection_reason ? (
            <p className="mt-1 text-xs text-danger">
              <span className="font-medium">Rejected: </span>{row.rejection_reason}
            </p>
          ) : null}
          <p className="mt-1 text-xs text-muted">
            {row.return_due_at ? `Due ${new Date(row.return_due_at).toLocaleString()}` : "No return due time set"}
            {row.return_reminder_sent_at ? ` · reminder sent ${new Date(row.return_reminder_sent_at).toLocaleString()}` : ""}
          </p>
          <p className="mt-2 text-xs text-ink/60">
            {row.items.map((item) => `${item.product_name} x${item.requested_quantity}`).join(", ")}
          </p>
          {row.issue_evidence_id || (row.return_evidence_ids?.length ?? 0) > 0 ? (
            <div className="desk-actions mt-2 flex flex-wrap gap-2 text-xs">
              {row.issue_evidence_id ? (
                <button type="button" onClick={() => openEvidence(row.issue_evidence_id as number)}>View issue photo</button>
              ) : null}
              {(row.return_evidence_ids ?? []).map((id, index) => (
                <button key={id} type="button" onClick={() => openEvidence(id)}>
                  View return photo{(row.return_evidence_ids?.length ?? 0) > 1 ? ` ${index + 1}` : ""}
                </button>
              ))}
            </div>
          ) : null}
          {row.items.some((item) => item.damaged_quantity || item.missing_quantity || item.needs_fix_quantity) ? (
            <ul className="mt-1 text-xs text-danger">
              {row.items
                .filter((item) => item.damaged_quantity || item.missing_quantity || item.needs_fix_quantity)
                .map((item) => (
                  <li key={item.id}>
                    {item.product_name}:
                    {item.damaged_quantity ? ` ${item.damaged_quantity} damaged` : ""}
                    {item.missing_quantity ? ` ${item.missing_quantity} missing` : ""}
                    {item.needs_fix_quantity ? ` ${item.needs_fix_quantity} to-fix` : ""}
                  </li>
                ))}
            </ul>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function statusBadgeClassName(status: string) {
  switch (status) {
    case "returned":
      return "border-green-600/40 bg-green-600/10 text-green-700";
    case "accepted":
    case "issued":
    case "partially_returned":
      return "border-amber-600/40 bg-amber-500/10 text-amber-700";
    case "rejected":
    case "closed_with_issue":
      return "border-danger bg-danger/10 text-danger";
    case "draft":
    case "pending_approval":
    default:
      return "border-slate-300 bg-slate-100 text-slate-700";
  }
}
