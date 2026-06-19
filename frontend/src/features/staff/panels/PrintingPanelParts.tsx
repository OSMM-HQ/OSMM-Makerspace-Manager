import type React from "react";

import {
  API_V1_URL,
  expireStaffAuthSession,
  getAccessToken,
  refreshAccessToken,
} from "../../../lib/api";


export type FilamentSpool = {
  id: number;
  makerspace: number;
  printer: number | null;
  printer_name?: string;
  material: string;
  color: string;
  brand: string;
  initial_weight_grams: string;
  remaining_weight_grams: string;
  is_active: boolean;
};

export type PrintPrinter = {
  id: number;
  makerspace: number;
  name: string;
  model: string;
  status: string;
  is_active: boolean;
  active_spool: FilamentSpool | null;
  current_request: { id: number; title: string; estimated_minutes: number } | null;
  is_free: boolean;
  pending_estimated_minutes: number;
  estimated_spool_remaining_after_queue_grams: string | null;
};

export type PrintRequest = {
  id: number;
  title: string;
  requester_username: string;
  status: string;
  price?: string;
  payment_status?: "none" | "pending" | "paid";
  paid_at?: string | null;
  collected_at?: string | null;
  collected_by?: number | null;
  material: string;
  color: string;
  estimated_minutes: number;
  estimated_filament_grams: string;
  filament_grams_used?: string;
  reprint_of?: number | null;
  printer: PrintPrinter | null;
  filament_spool: FilamentSpool | null;
  requested_filament_spool?: FilamentSpool | null;
  requester_name?: string;
  project_brief?: string;
  contact_email?: string;
  contact_phone?: string;
  reason?: string;
  files?: {
    id: number;
    kind: string;
    content_type: string;
    size_bytes: number;
  }[];
};

export type PrinterPayload = {
  name: string;
  model: string;
  status: string;
  is_active: boolean;
};

export type SpoolPayload = {
  printer: number | null;
  material: string;
  color: string;
  brand: string;
  initial_weight_grams: string;
  remaining_weight_grams: string;
  is_active: boolean;
};

export async function printingRequest<T>(path: string, options: RequestInit = {}) {
  const makeRequest = () => {
    const token = getAccessToken();
    return fetch(`${API_V1_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers ?? {}),
      },
    });
  };

  let response = await makeRequest();
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await makeRequest();
      if (response.status === 401) {
        expireStaffAuthSession();
      }
    } else {
      expireStaffAuthSession();
    }
  }

  if (response.ok) {
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }
  const body = await response.json().catch(() => null);
  throw new Error(formatApiError(body, response.status));
}

export function formatApiError(body: unknown, status: number): string {
  const rendered = renderErrorValue(body);
  return rendered || `Request failed (${status})`;
}

function renderErrorValue(value: unknown, label?: string): string {
  if (!value) return "";
  if (typeof value === "string") return label ? `${humanize(label)}: ${value}` : value;
  if (Array.isArray(value)) {
    return value.map((item) => renderErrorValue(item, label)).filter(Boolean).join(" ");
  }
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([key, item]) => renderErrorValue(item, key))
      .filter(Boolean)
      .join(" ");
  }
  return label ? `${humanize(label)}: ${String(value)}` : String(value);
}

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/^\w/, (match) => match.toUpperCase());
}

export function ErrorText({ message }: { message?: string }) {
  return message ? <p className="mt-2 text-sm text-danger">{message}</p> : null;
}

// Common filament colors offered as a pick-list. Backed by a <datalist> so staff can
// pick a standard color OR type a custom one (the model stores free text).
export const SPOOL_COLORS = [
  "Black", "White", "Gray", "Silver", "Red", "Orange", "Yellow", "Green",
  "Blue", "Purple", "Pink", "Brown", "Gold", "Transparent", "Natural",
];

export function SpoolColorInput({
  value,
  onChange,
  className = "desk-input",
}: {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  // Visible dropdown of the available colours. Any existing custom value not in the
  // palette is preserved as its own option so editing an old spool never loses data.
  const options = SPOOL_COLORS.includes(value) || !value ? SPOOL_COLORS : [value, ...SPOOL_COLORS];
  return (
    <select className={className} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">Select colour</option>
      {options.map((color) => (
        <option key={color} value={color}>
          {color}
        </option>
      ))}
    </select>
  );
}

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
    <div className="rounded-md border border-line bg-surface p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-ink">{printer.name}</h3>
          <p className="text-xs text-muted">{printer.model || "No model"}</p>
        </div>
        <span className={`rounded-md px-2 py-1 text-xs font-semibold ${printer.is_free ? "bg-success/15 text-success" : "bg-warn/15 text-warn"}`}>
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

function Row({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between gap-2"><dt>{label}</dt><dd className="text-right">{value}</dd></div>;
}

function PaymentBadge({ request }: { request: PrintRequest }) {
  if (request.payment_status === undefined) return null;
  const price = request.price ?? "0";
  if (request.payment_status === "paid") {
    return <span className="rounded-md bg-success/15 px-2 py-0.5 text-xs font-semibold text-success">Paid {price}</span>;
  }
  if (request.payment_status === "pending") {
    return <span className="rounded-md bg-warn/15 px-2 py-0.5 text-xs font-semibold text-warn">Payment due {price}</span>;
  }
  // payment_status === "none": a truly zero-priced request is Free; a priced request that
  // hasn't reached completion (where payment becomes due) shows its price, NOT "Free".
  if (Number(price) > 0) {
    return <span className="rounded-md bg-accent/15 px-2 py-0.5 text-xs font-semibold text-accent">Price {price}</span>;
  }
  return <span className="rounded-md border border-line bg-bg px-2 py-0.5 text-xs font-semibold text-muted">Free</span>;
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
  const usedLabel = Number.isFinite(usedGrams) ? `${usedGrams}g used` : "—";
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="font-medium text-ink">
          {[spool.brand, spool.material, spool.color].filter(Boolean).join(" ") || spool.material}
        </span>
        <span className="text-muted">{spool.printer_name ?? "Unassigned"}</span>
        <span className="text-muted">{usedLabel} · {spool.remaining_weight_grams}g left of {spool.initial_weight_grams}g</span>
        <span
          className={`rounded-md px-2 py-0.5 text-xs font-semibold ${
            spool.is_active ? "bg-success/15 text-success" : "bg-warn/15 text-warn"
          }`}
          title={spool.is_active ? "Shown to the public request form" : "Hidden from the public request form — activate to show"}
        >
          {spool.is_active ? "Active · public" : "Inactive · hidden"}
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
  action: (row: PrintRequest) => React.ReactNode;
}) {
  async function openFile(id: number) {
    const res = await printingRequest<{ url: string }>(`/printing/manage/files/${id}/url`);
    window.open(res.url, "_blank", "noopener");
  }

  return (
    <div className="rounded-md border border-line">
      <h3 className="border-b border-line bg-surface px-3 py-2 text-sm font-semibold text-muted">{title}</h3>
      <div className="grid gap-0">
        {rows.length ? rows.map((row) => (
          <article key={row.id} className="border-b border-line p-3 last:border-b-0">
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-ink">#{row.id} {row.title}</strong>
              <span className="rounded-md border border-line bg-bg px-2 py-0.5 text-xs text-muted">{row.status}</span>
              <PaymentBadge request={row} />
              <div className="desk-actions ml-auto flex flex-wrap gap-2 text-sm">{action(row)}</div>
            </div>
            <p className="mt-2 text-xs text-muted">
              {row.requester_name || row.requester_username} - {row.material || "material n/a"} {row.color || ""} - {row.estimated_minutes || 0} min - {row.estimated_filament_grams || "0.00"}g
            </p>
            {row.requested_filament_spool ? (
              <p className="mt-1 text-xs text-accent">
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
