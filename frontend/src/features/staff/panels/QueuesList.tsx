import type React from "react";

import { StatusStepper, statusStageLabel } from "../../../components/ui/StatusStepper";
import type { HardwareRequest } from "./Queues";

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
          <p className="mt-1 text-xs text-muted">
            {row.return_due_at ? `Due ${new Date(row.return_due_at).toLocaleString()}` : "No return due time set"}
            {row.return_reminder_sent_at ? ` · reminder sent ${new Date(row.return_reminder_sent_at).toLocaleString()}` : ""}
          </p>
          <p className="mt-2 text-xs text-ink/60">
            {row.items.map((item) => `${item.product_name} x${item.requested_quantity}`).join(", ")}
          </p>
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
