import { useState, type ReactNode } from "react";

import {
  type FilamentSpool,
  type PrintPrinter,
  type PrintRequest,
  printingRequest,
} from "./PrintingPanelParts";
import { ImageThumbnail } from "../../../components/ui/ImageThumbnail";

export function PrinterCard({
  printer,
  onEdit,
  onDeactivate,
  onDelete,
}: {
  printer: PrintPrinter;
  onEdit: () => void;
  onDeactivate: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-surface p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <ImageThumbnail src={printer.image_url} alt={printer.name} className="h-14 w-14" />
          <div className="min-w-0">
          <h3 className="break-words font-semibold text-ink">{printer.name}</h3>
          <p className="break-words text-xs text-muted">{printer.model || "No model"}</p>
          </div>
        </div>
        <span className={`rounded-md px-2 py-1 text-xs font-semibold ${printer.is_free ? "bg-success/15 text-success-ink" : "bg-warn/15 text-warn-ink"}`}>
          {printer.is_free ? "Free" : "Busy"}
        </span>
      </div>
      <dl className="mt-3 grid gap-1 text-sm text-muted">
        <Row label="Status" value={`${printer.status}${printer.is_active ? "" : " (inactive)"}`} />
        <Row label="Pending" value={`${printer.pending_estimated_minutes} min`} />
        <Row label="Current" value={printer.current_request?.title ?? "None"} />
        <Row label="Spool" value={printer.active_spool ? `${printer.active_spool.material} ${printer.active_spool.color}` : "None"} />
        <Row label="Left after queue" value={`${printer.estimated_spool_remaining_after_queue_grams ?? "-"} g`} />
      </dl>
      <div className="desk-actions mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={onEdit}>Edit</button>
        <button type="button" disabled={!printer.is_active} onClick={onDeactivate}>Deactivate</button>
        <button type="button" className="text-danger" onClick={onDelete}>Delete</button>
      </div>
    </div>
  );
}

export function SpoolRow({
  spool,
  onEdit,
  onActivate,
  onDeactivate,
  onDelete,
}: {
  spool: FilamentSpool;
  onEdit: () => void;
  onActivate: () => void;
  onDeactivate: () => void;
  onDelete: () => void;
}) {
  const usedGrams = Math.max(
    0,
    Number(spool.initial_weight_grams) - Number(spool.remaining_weight_grams),
  );
  const usedLabel = Number.isFinite(usedGrams) ? `${usedGrams}g used` : "-";
  return (
    <div className="min-w-0 rounded-md border border-line bg-surface px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="min-w-0 break-words font-medium text-ink">
          {[spool.brand, spool.material, spool.color].filter(Boolean).join(" ") || spool.material}
        </span>
        <span className="min-w-0 break-words text-muted">{spool.printer_name ?? "Unassigned"}</span>
        <span className="min-w-0 break-words text-muted">{usedLabel} - {spool.remaining_weight_grams}g left of {spool.initial_weight_grams}g</span>
        <span
          className={`rounded-md px-2 py-0.5 text-xs font-semibold ${
            spool.is_active ? "bg-success/15 text-success-ink" : "bg-warn/15 text-warn-ink"
          }`}
          title={spool.is_active ? "Shown to the public request form" : "Hidden from the public request form - activate to show"}
        >
          {spool.is_active ? "Active - public" : "Inactive - hidden"}
        </span>
      </div>
      <div className="desk-actions mt-2 flex flex-wrap gap-2">
        <button type="button" onClick={onEdit}>Edit</button>
        {spool.is_active ? (
          <button type="button" onClick={onDeactivate}>Deactivate</button>
        ) : (
          <button type="button" onClick={onActivate}>Activate</button>
        )}
        <button type="button" className="text-danger" onClick={onDelete}>Delete</button>
      </div>
    </div>
  );
}

export function PrintRows({
  title,
  rows,
  action,
}: {
  title: string;
  rows: PrintRequest[];
  action: (row: PrintRequest) => ReactNode;
}) {
  const [fileError, setFileError] = useState("");

  async function openFile(id: number) {
    setFileError("");
    try {
      const res = await printingRequest<{ url: string }>(`/printing/manage/files/${id}/url`);
      window.open(res.url, "_blank", "noopener");
    } catch (err) {
      setFileError(err instanceof Error ? err.message : "Could not open file.");
    }
  }

  return (
    <div className="rounded-md border border-line">
      <h3 className="border-b border-line bg-surface px-3 py-2 text-sm font-semibold text-muted">{title}</h3>
      {fileError ? <p className="border-b border-line px-3 py-2 text-sm text-danger">{fileError}</p> : null}
      <div className="grid gap-0">
        {rows.length ? rows.map((row) => (
          <article key={row.id} className="border-b border-line p-3 last:border-b-0">
            <div className="flex flex-wrap items-center gap-2">
              <strong className="min-w-0 break-words text-ink">#{row.id} {row.title}</strong>
              <span className={`status-box ${printStatusClassName(row.status)}`}>{printStatusLabel(row.status)}</span>
              <PaymentBadge request={row} />
              <div className="desk-actions ml-0 flex w-full flex-wrap gap-2 text-sm sm:ml-auto sm:w-auto">{action(row)}</div>
            </div>
            <p className="mt-2 text-xs text-muted">
              {row.requester_display || row.requester_name || row.requester_username} - {row.material || "material n/a"} {row.color || ""} - {row.estimated_minutes || 0} min - {row.estimated_filament_grams || "0.00"}g
            </p>
            {row.accepted_by ? (
              <p className="mt-1 text-xs text-muted">
                <span className="font-medium text-ink">Approved by: </span>
                {row.accepted_by.username}{row.accepted_by.role ? ` (${humanize(row.accepted_by.role)})` : ""}
              </p>
            ) : null}
            {row.requested_filament_spool ? (
              <p className="mt-1 text-xs text-accent-ink">
                <span className="font-medium">Requested spool: </span>
                {`#${row.requested_filament_spool.id} ${row.requested_filament_spool.material} ${row.requested_filament_spool.color}`.trim()}
                {` (${row.requested_filament_spool.remaining_weight_grams}g)`}
              </p>
            ) : null}
            {row.project_brief ? (
              <p className="mt-1 text-xs text-muted">
                <span className="font-medium text-ink">Brief: </span>{row.project_brief}
              </p>
            ) : null}
            {row.reason ? (
              <p className="mt-1 text-xs text-danger">
                <span className="font-medium">Reason: </span>{row.reason}
              </p>
            ) : null}
            {row.contact_email || row.contact_phone ? (
              <p className="mt-1 text-xs text-muted">
                <span className="font-medium text-ink">Contact: </span>
                {[row.contact_email, row.contact_phone].filter(Boolean).join(" ")}
              </p>
            ) : null}
            {row.files?.length ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {row.files.map((file, index) => (
                  <button
                    key={file.id}
                    type="button"
                    className="desk-button text-xs"
                    onClick={() => openFile(file.id)}
                  >
                    {file.kind ? `${humanize(file.kind)} ${index + 1}` : `File ${index + 1}`}
                  </button>
                ))}
              </div>
            ) : null}
          </article>
        )) : <p className="p-3 text-sm text-muted">No print requests.</p>}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return <div className="flex min-w-0 justify-between gap-2"><dt>{label}</dt><dd className="min-w-0 break-words text-right">{value}</dd></div>;
}

function printStatusClassName(status: string) {
  switch (status) {
    case "accepted":
    case "printing":
    case "in_progress":
      return "status-box-active";
    case "completed":
    case "collected":
      return "status-box-done";
    case "rejected":
    case "failed":
      return "status-box-danger";
    case "pending":
      return "status-box-pending";
    default:
      return "";
  }
}

function printStatusLabel(status: string) {
  switch (status) {
    case "pending":
      return "Pending";
    case "accepted":
      return "Approved";
    case "printing":
    case "in_progress":
      return "Printing";
    case "completed":
      return "Ready to collect";
    case "collected":
      return "Collected";
    case "rejected":
      return "Rejected";
    case "failed":
      return "Failed";
    default:
      return status.replace(/_/g, " ");
  }
}

function PaymentBadge({ request }: { request: PrintRequest }) {
  if (request.payment_status === undefined) return null;
  const price = request.price ?? "0";
  if (request.payment_status === "paid") {
    return <span className="status-box status-box-done">Paid {price}</span>;
  }
  if (request.payment_status === "pending") {
    return <span className="status-box status-box-active">Payment due {price}</span>;
  }
  if (Number(price) > 0) {
    return <span className="status-box">Price {price}</span>;
  }
  return <span className="status-box">Free</span>;
}

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/^\w/, (match) => match.toUpperCase());
}


