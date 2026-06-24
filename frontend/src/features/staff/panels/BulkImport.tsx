import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { Modal } from "../../../components/ui";
import { staffRequest } from "../../../lib/api";
import { Panel, type Makerspace } from "./shared";

type RawRow = Record<string, unknown>;
type Field =
  | "name"
  | "total_quantity"
  | "available_quantity"
  | "reserved_quantity"
  | "issued_quantity"
  | "damaged_quantity"
  | "lost_quantity"
  | "description"
  | "image_key"
  | "tracking_mode"
  | "is_public"
  | "public_self_checkout_enabled"
  | "show_public_count"
  | "public_availability_mode"
  | "storage_location"
  | "category"
  | "box_code";
type Mapping = Partial<Record<Field, string>>;
type RowMessages = Record<string, string>;
type ImportRow = { row: number; action?: string; data?: RawRow; errors?: RowMessages; warnings?: RowMessages };
type ImportResult = {
  applied?: boolean;
  created?: number;
  updated?: number;
  valid?: boolean;
  summary?: { create?: number; update?: number; errors?: number; warnings?: number; total?: number };
  rows?: ImportRow[];
  errors?: { row: number; errors: RowMessages }[];
  warnings?: { row: number; warnings: RowMessages }[];
};

const fields: Field[] = [
  "name",
  "total_quantity",
  "available_quantity",
  "reserved_quantity",
  "issued_quantity",
  "damaged_quantity",
  "lost_quantity",
  "description",
  "image_key",
  "tracking_mode",
  "is_public",
  "public_self_checkout_enabled",
  "show_public_count",
  "public_availability_mode",
  "storage_location",
  "category",
  "box_code",
];
const aliases: Record<Field, string[]> = {
  name: ["name", "item", "product"],
  total_quantity: ["total", "total quantity", "quantity", "qty"],
  available_quantity: ["available", "available quantity", "in stock"],
  reserved_quantity: ["reserved", "reserved quantity"],
  issued_quantity: ["issued", "issued quantity", "loaned", "checked out"],
  damaged_quantity: ["damaged", "damaged quantity"],
  lost_quantity: ["lost", "lost quantity"],
  description: ["description", "details", "notes"],
  image_key: ["image", "image key", "image object key", "photo", "photo key"],
  tracking_mode: ["tracking", "tracking mode"],
  is_public: ["public", "is public", "visible"],
  public_self_checkout_enabled: ["self checkout", "public self checkout", "self checkout enabled"],
  show_public_count: ["show count", "show public count", "public count"],
  public_availability_mode: ["availability", "public availability", "public availability mode"],
  storage_location: ["location", "storage", "storage location", "shelf"],
  category: ["category", "category name", "type"],
  box_code: ["box", "box code", "container", "container code"],
};

export function BulkImport({ makerspace }: { makerspace: Makerspace }) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [rawJson, setRawJson] = useState('[{"name":"New Kit","total_quantity":"1","available_quantity":"1"}]');
  const [tableText, setTableText] = useState("");
  const [headers, setHeaders] = useState<string[]>([]);
  const [sourceRows, setSourceRows] = useState<RawRow[]>([]);
  const [mapping, setMapping] = useState<Mapping>({});
  const [mappingOpen, setMappingOpen] = useState(false);
  const [error, setError] = useState("");
  const mutation = useMutation({
    mutationFn: ({ apply, rows }: { apply: boolean; rows: RawRow[] }) =>
      staffRequest<ImportResult>(`/admin/makerspace/${makerspace.id}/inventory/import/${apply ? "apply" : "preview"}`, {
        method: "POST",
        body: JSON.stringify({ rows }),
      }),
  });
  const pending = mutation.isPending;
  const mappedRows = () => sourceRows.map((row) => mapRow(row, mapping));
  const submitRows = (apply: boolean, rows: RawRow[]) => {
    setError("");
    mutation.mutate({ apply, rows });
  };
  const submitJson = (apply: boolean) => {
    try {
      const parsed = JSON.parse(rawJson);
      if (!Array.isArray(parsed) || parsed.some((row) => !row || typeof row !== "object" || Array.isArray(row))) {
        setError("Advanced JSON must be an array of row objects.");
        return;
      }
      submitRows(apply, parsed as RawRow[]);
    } catch {
      setError("Advanced JSON could not be parsed. Check commas, quotes, and brackets.");
    }
  };
  const loadRows = (rows: RawRow[]) => {
    if (!rows.length) {
      setError("No rows were found.");
      return;
    }
    const nextHeaders = Object.keys(rows[0]);
    setSourceRows(rows);
    setHeaders(nextHeaders);
    setMapping(suggestMapping(nextHeaders));
    setMappingOpen(true);
    setError("");
  };
  return (
    <Panel title="Bulk import">
      <div className="grid gap-4">
        <div className="grid gap-2">
          <label className="text-xs font-semibold uppercase text-muted">Upload CSV or XLSX</label>
          <input
            className="desk-input"
            type="file"
            accept=".csv,.tsv,.xlsx"
            disabled={pending}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) parseFile(file).then(loadRows).catch((exc: Error) => setError(exc.message));
            }}
          />
        </div>
        <div className="grid gap-2">
          <label className="text-xs font-semibold uppercase text-muted">Paste table</label>
          <textarea className="desk-input h-28 w-full text-sm" value={tableText} onChange={(e) => setTableText(e.target.value)} />
          <div className="desk-actions flex flex-wrap gap-2">
            <button className="desk-button" type="button" disabled={pending || !tableText.trim()} onClick={() => loadRows(parseDelimited(tableText))}>
              Map pasted table
            </button>
            <button className="desk-button" type="button" disabled={pending || !sourceRows.length} onClick={() => setMappingOpen(true)}>
              Edit mapping
            </button>
            <button className="desk-button" type="button" disabled={pending || !sourceRows.length} onClick={() => submitRows(false, mappedRows())}>
              Preview
            </button>
            <button className="desk-button" type="button" disabled={pending || !sourceRows.length} onClick={() => submitRows(true, mappedRows())}>
              Apply
            </button>
          </div>
        </div>
        <details open={advancedOpen} onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}>
          <summary className="cursor-pointer text-sm font-semibold text-ink">Advanced JSON</summary>
          <textarea className="desk-input mt-2 h-32 w-full font-mono text-sm" value={rawJson} onChange={(e) => setRawJson(e.target.value)} />
          <div className="desk-actions mt-2 flex flex-wrap gap-2">
            <button className="desk-button" type="button" disabled={pending} onClick={() => submitJson(false)}>
              Preview JSON
            </button>
            <button className="desk-button" type="button" disabled={pending} onClick={() => submitJson(true)}>
              Apply JSON
            </button>
          </div>
        </details>
        {pending ? <ProgressBar /> : null}
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        {mutation.error ? <p className="text-sm text-danger">{mutation.error.message}</p> : null}
        {mutation.data ? <ImportSummary result={mutation.data} /> : null}
      </div>
      <Modal
        open={mappingOpen}
        onClose={() => setMappingOpen(false)}
        title="Map columns"
        footer={(
          <div className="desk-actions flex flex-wrap justify-end gap-2">
            <button className="desk-button" type="button" onClick={() => setMappingOpen(false)}>Cancel</button>
            <button className="desk-button" type="button" onClick={() => { setMappingOpen(false); submitRows(false, mappedRows()); }}>
              Preview
            </button>
          </div>
        )}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {fields.map((field) => (
            <label key={field} className="grid gap-1 text-sm">
              <span className="font-medium text-ink">{labelFor(field)}</span>
              <select className="desk-input" value={mapping[field] ?? ""} onChange={(e) => setMapping((current) => ({ ...current, [field]: e.target.value || undefined }))}>
                <option value="">Do not import</option>
                {headers.map((header) => <option key={header} value={header}>{header}</option>)}
              </select>
            </label>
          ))}
        </div>
      </Modal>
    </Panel>
  );
}

function ProgressBar() {
  return (
    <div className="grid gap-1" role="status" aria-live="polite">
      <div className="h-2 overflow-hidden rounded-sm bg-line">
        <div className="h-full w-1/2 animate-pulse rounded-sm bg-accent" />
      </div>
      <p className="text-xs text-muted">Processing import...</p>
    </div>
  );
}

function ImportSummary({ result }: { result: ImportResult }) {
  const errorRows = new Map((result.errors ?? []).map((item) => [item.row, item.errors]));
  const warningRows = new Map((result.warnings ?? []).map((item) => [item.row, item.warnings]));
  return (
    <div className="grid gap-3 rounded-md border border-line bg-panel p-3">
      <div className="grid gap-2 text-sm sm:grid-cols-5">
        <Metric label="Create" value={result.created ?? result.summary?.create ?? 0} />
        <Metric label="Update" value={result.updated ?? result.summary?.update ?? 0} />
        <Metric label="Errors" value={result.summary?.errors ?? result.errors?.length ?? 0} />
        <Metric label="Warnings" value={result.summary?.warnings ?? result.warnings?.length ?? 0} />
        <Metric label="Rows" value={result.summary?.total ?? result.rows?.length ?? 0} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-xs uppercase text-muted"><tr><th className="px-2 py-1">Row</th><th className="px-2 py-1">Status</th><th className="px-2 py-1">Name</th><th className="px-2 py-1">Message</th></tr></thead>
          <tbody>
            {(result.rows ?? []).map((row) => {
              const errors = errorRows.get(row.row) ?? row.errors;
              const warnings = warningRows.get(row.row) ?? row.warnings;
              const message = errors ? messageFor(errors) : warnings ? messageFor(warnings) : "";
              return <tr key={row.row} className="border-t border-line"><td className="px-2 py-1">{row.row}</td><td className="px-2 py-1">{errors ? "error" : row.action ?? "ready"}</td><td className="px-2 py-1">{String(row.data?.name ?? "")}</td><td className={errors ? "px-2 py-1 text-danger" : "px-2 py-1 text-amber-700"}>{message}</td></tr>;
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div><p className="text-xs uppercase text-muted">{label}</p><p className="font-semibold text-ink">{value}</p></div>;
}

async function parseFile(file: File) {
  const data = await file.arrayBuffer();
  if (file.name.toLowerCase().endsWith(".xlsx")) {
    const XLSX = await import("xlsx");
    const workbook = XLSX.read(data, { type: "array" });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    return XLSX.utils.sheet_to_json<RawRow>(sheet, { defval: "" });
  }
  return parseDelimited(new TextDecoder().decode(data), file.name.toLowerCase().endsWith(".tsv") ? "\t" : undefined);
}

function parseDelimited(text: string, forcedDelimiter?: string) {
  const delimiter = forcedDelimiter ?? (text.includes("\t") ? "\t" : ",");
  const rows = csvRows(text, delimiter).filter((row) => row.some((cell) => cell.trim()));
  if (!rows.length) return [];
  const headers = rows[0].map((cell) => cell.trim());
  return rows.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] ?? ""])));
}

function csvRows(text: string, delimiter: string) {
  const rows: string[][] = [[]];
  let value = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (char === '"' && text[i + 1] === '"') { value += '"'; i += 1; }
    else if (char === '"') quoted = !quoted;
    else if (char === delimiter && !quoted) { rows[rows.length - 1].push(value); value = ""; }
    else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[i + 1] === "\n") i += 1;
      rows[rows.length - 1].push(value); value = ""; rows.push([]);
    } else value += char;
  }
  rows[rows.length - 1].push(value);
  return rows;
}

function normalizeHeader(value: string): string {
  return value.trim().toLowerCase().replace(/[_\s]+/g, " ");
}

function suggestMapping(headers: string[]): Mapping {
  return Object.fromEntries(
    fields
      .map((field) => {
        const accepted = new Set([field, ...aliases[field]].map(normalizeHeader));
        return [field, headers.find((header) => accepted.has(normalizeHeader(header)))];
      })
      .filter(([, header]) => header),
  ) as Mapping;
}

function mapRow(row: RawRow, mapping: Mapping) {
  return Object.fromEntries(fields.filter((field) => mapping[field]).map((field) => [field, row[mapping[field] as string] ?? ""])) as RawRow;
}

function messageFor(messages: RowMessages) {
  return Object.entries(messages).map(([key, value]) => `${key}: ${value}`).join("; ");
}

function labelFor(field: Field) {
  return field.replace(/_/g, " ");
}

