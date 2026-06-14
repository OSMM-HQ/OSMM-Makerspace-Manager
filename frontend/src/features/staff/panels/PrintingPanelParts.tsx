import type React from "react";

import { API_URL } from "../../../lib/api";

const API_V1_URL = API_URL.replace(/\/api$/, "/api/v1");
const ACCESS_TOKEN_KEY = "makerspace.access";

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
  material: string;
  color: string;
  estimated_minutes: number;
  estimated_filament_grams: string;
  printer: PrintPrinter | null;
  filament_spool: FilamentSpool | null;
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
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  const response = await fetch(`${API_V1_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  if (response.ok) return (await response.json()) as T;
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

export function PrinterCard({
  printer,
  onEdit,
  onDeactivate,
}: {
  printer: PrintPrinter;
  onEdit: () => void;
  onDeactivate: () => void;
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
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between gap-2"><dt>{label}</dt><dd className="text-right">{value}</dd></div>;
}

export function SpoolRow({
  spool,
  onEdit,
  onDeactivate,
}: {
  spool: FilamentSpool;
  onEdit: () => void;
  onDeactivate: () => void;
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
        <span className={spool.is_active ? "text-success" : "text-muted"}>{spool.is_active ? "Active" : "Inactive"}</span>
      </div>
      <div className="desk-actions mt-2 flex flex-wrap gap-2">
        <button type="button" onClick={onEdit}>Edit</button>
        <button type="button" disabled={!spool.is_active} onClick={onDeactivate}>Deactivate</button>
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
  return (
    <div className="rounded-md border border-line">
      <h3 className="border-b border-line bg-surface px-3 py-2 text-sm font-semibold text-muted">{title}</h3>
      <div className="grid gap-0">
        {rows.length ? rows.map((row) => (
          <article key={row.id} className="border-b border-line p-3 last:border-b-0">
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-ink">#{row.id} {row.title}</strong>
              <span className="rounded-md border border-line bg-bg px-2 py-0.5 text-xs text-muted">{row.status}</span>
              <div className="desk-actions ml-auto flex flex-wrap gap-2 text-sm">{action(row)}</div>
            </div>
            <p className="mt-2 text-xs text-muted">
              {row.requester_username} - {row.material || "material n/a"} {row.color || ""} - {row.estimated_minutes || 0} min - {row.estimated_filament_grams || "0.00"}g
            </p>
          </article>
        )) : <p className="p-3 text-sm text-muted">No print requests.</p>}
      </div>
    </div>
  );
}
