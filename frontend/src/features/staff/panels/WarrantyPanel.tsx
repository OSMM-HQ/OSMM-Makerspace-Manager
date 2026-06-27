import { useState } from "react";

import { EmptyState, SkeletonRows } from "../../../components/ui";
import { WarrantyStatusBadge } from "../WarrantyStatusBadge";
import type { WarrantyReportRow, WarrantyStatus } from "../warrantyApi";
import { Panel, type Makerspace, useStaffGet } from "./shared";

type WarrantyResponse = {
  count: number;
  next: string | null;
  previous: string | null;
  results: WarrantyReportRow[];
};

type StatusFilter = "all" | WarrantyStatus;

const PAGE_SIZE = 50;

export function WarrantyPanel({
  makerspace,
  canEditInventory,
  canSeePrinting,
}: {
  makerspace: Makerspace;
  canEditInventory: boolean;
  canSeePrinting: boolean;
}) {
  const [status, setStatus] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);
  const statusQuery = status === "all" ? "" : `&status=${status}`;
  const warranties = useStaffGet<WarrantyResponse>(
    ["warranties", makerspace.id, page, PAGE_SIZE, status],
    `/admin/makerspace/${makerspace.id}/warranties?page=${page}&page_size=${PAGE_SIZE}${statusQuery}`,
  );

  // Status is filtered server-side (before pagination), so the loaded page is already scoped.
  const visibleRows = warranties.data?.results ?? [];
  const totalPages = Math.max(1, Math.ceil((warranties.data?.count ?? 0) / PAGE_SIZE));
  const scopeLabel = canEditInventory && canSeePrinting
    ? "hardware assets and printers"
    : canEditInventory
      ? "hardware assets"
      : "printers";

  function updateStatus(value: StatusFilter) {
    setStatus(value);
    setPage(1);
  }

  return (
    <Panel title="Warranties">
      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm text-muted">Warranty records for {scopeLabel} in {makerspace.name}.</p>
          {warranties.data ? <p className="mt-1 text-xs text-muted">{warranties.data.count} records total</p> : null}
        </div>
        <label className="grid gap-1 text-xs font-semibold uppercase tracking-wide text-muted sm:w-48">
          Status
          <select className="desk-input" value={status} onChange={(event) => updateStatus(event.target.value as StatusFilter)}>
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="expiring_soon">Expiring soon</option>
            <option value="expired">Expired</option>
            <option value="unknown">No warranty info</option>
          </select>
        </label>
      </div>

      {warranties.isLoading ? <WarrantyTableSkeleton /> : null}
      {warranties.error instanceof Error ? <p className="mb-3 text-sm text-danger">{warranties.error.message}</p> : null}
      {!warranties.isLoading && !warranties.error && !visibleRows.length ? (
        <EmptyState title="No warranties" description={status === "all" ? "No warranty records have been saved yet." : "No warranty records match this status."} />
      ) : null}

      {visibleRows.length ? (
        <div className="overflow-x-auto rounded-md border border-line">
          <table className="min-w-[820px] divide-y divide-line text-left text-sm">
            <thead className="bg-bg text-xs font-semibold uppercase text-muted">
              <tr>
                <th className="px-3 py-2">Host</th>
                <th className="px-3 py-2">Vendor</th>
                <th className="px-3 py-2">Purchased</th>
                <th className="px-3 py-2">Expires</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Docs</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-surface">
              {visibleRows.map((row) => (
                <tr key={`${row.host_kind}-${row.host_id}`}>
                  <td className="px-3 py-2 align-top">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-md border border-line bg-bg px-2 py-0.5 text-xs font-medium text-muted">
                        {row.host_kind}
                      </span>
                      <span className="max-w-56 break-words font-medium text-ink">{row.host_label}</span>
                    </div>
                    {row.serial_number ? <p className="mt-1 text-xs text-muted">Serial: {row.serial_number}</p> : null}
                  </td>
                  <td className="px-3 py-2 align-top text-ink"><span className="block max-w-48 break-words">{row.vendor_name || "-"}</span></td>
                  <td className="whitespace-nowrap px-3 py-2 align-top text-muted">{formatDate(row.purchased_on)}</td>
                  <td className="whitespace-nowrap px-3 py-2 align-top text-muted">{formatDate(row.warranty_expires_on)}</td>
                  <td className="whitespace-nowrap px-3 py-2 align-top"><WarrantyStatusBadge status={row.status} /></td>
                  <td className="whitespace-nowrap px-3 py-2 text-right align-top text-muted">{row.document_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="mt-3 flex items-center justify-between gap-3 text-sm">
        <button className="desk-button" type="button" disabled={!warranties.data?.previous} onClick={() => setPage((current) => Math.max(1, current - 1))}>
          Previous
        </button>
        <span className="text-muted">Page {page} of {totalPages}</span>
        <button className="desk-button" type="button" disabled={!warranties.data?.next} onClick={() => setPage((current) => current + 1)}>
          Next
        </button>
      </div>
    </Panel>
  );
}

function WarrantyTableSkeleton() {
  return (
    <div className="overflow-x-auto rounded-md border border-line" aria-hidden="true">
      <table className="min-w-[820px] divide-y divide-line text-left text-sm">
        <thead className="bg-bg text-xs font-semibold uppercase text-muted">
          <tr>
            {["Host", "Vendor", "Purchased", "Expires", "Status", "Docs"].map((label) => (
              <th key={label} className="px-3 py-2">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line bg-surface">
          <SkeletonRows rows={4} cols={6} />
        </tbody>
      </table>
    </div>
  );
}

function formatDate(value: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
