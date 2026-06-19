import { useState } from "react";

import { Panel, useStaffGet } from "./shared";

type AuditLogEntry = {
  id: number;
  action: string;
  target_type: string;
  target_id: string | number | null;
  created_at: string;
};

type AuditLogResponse = {
  count: number;
  next: string | null;
  previous: string | null;
  results: AuditLogEntry[];
};

export function AuditLog() {
  const [targetType, setTargetType] = useState("");
  const [targetId, setTargetId] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams();
  if (targetType) params.set("target_type", targetType);
  if (targetId) params.set("target_id", targetId);
  params.set("page", String(page));
  const query = params.toString();
  const logs = useStaffGet<AuditLogResponse>(
    ["audit", query],
    `/admin/audit-logs?${query}`,
  );

  const updateTargetType = (value: string) => {
    setTargetType(value);
    setPage(1);
  };
  const updateTargetId = (value: string) => {
    setTargetId(value);
    setPage(1);
  };

  return (
    <Panel title="Audit logs">
      <div className="mb-3 grid gap-2 sm:grid-cols-2">
        <input className="desk-input" placeholder="target type, e.g. inventory.inventoryproduct" value={targetType} onChange={(e) => updateTargetType(e.target.value)} />
        <input className="desk-input" placeholder="target id" value={targetId} onChange={(e) => updateTargetId(e.target.value)} />
      </div>
      <div className="grid gap-2 text-sm">
        {logs.error ? <p className="text-sm text-danger">{logs.error.message}</p> : null}
        {logs.data?.results?.map((log) => (
          <div key={log.id} className="rounded-md border border-line bg-surface p-2">
            <span className="font-semibold">{log.action}</span>
            <span className="ml-2 text-muted">{log.target_type}:{log.target_id}</span>
            <span className="ml-2 text-muted">{formatLocalDateTime(log.created_at)}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 text-sm">
        <button className="desk-button" disabled={!logs.data?.previous} onClick={() => setPage((current) => Math.max(1, current - 1))}>
          Previous
        </button>
        <span className="text-muted">
          Page {page}{" \u2014 "}{logs.data?.count ?? 0} total
        </span>
        <button className="desk-button" disabled={!logs.data?.next} onClick={() => setPage((current) => current + 1)}>
          Next
        </button>
      </div>
    </Panel>
  );
}

function formatLocalDateTime(value: string) {
  return new Date(value).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
