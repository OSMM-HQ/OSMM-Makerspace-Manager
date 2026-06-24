export type RawRow = Record<string, unknown>;
export type Field =
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
export type Mapping = Partial<Record<Field, string>>;
export type RowMessages = Record<string, string>;
export type ImportRow = { row: number; action?: string; data?: RawRow; errors?: RowMessages; warnings?: RowMessages };
export type ImportResult = {
  applied?: boolean;
  created?: number;
  updated?: number;
  valid?: boolean;
  summary?: { create?: number; update?: number; errors?: number; warnings?: number; total?: number };
  rows?: ImportRow[];
  errors?: { row: number; errors: RowMessages }[];
  warnings?: { row: number; warnings: RowMessages }[];
};
export type BulkImportJob = {
  id: number;
  mode: "preview" | "apply";
  status: "pending" | "running" | "completed" | "failed";
  total_rows: number;
  processed_rows: number;
  created_count: number;
  updated_count: number;
  error_count: number;
  warning_count: number;
  result?: ImportResult;
  error?: string;
};

const sampleBytes = 256 * 1024;
export const fields: Field[] = [
  "name", "total_quantity", "available_quantity", "reserved_quantity", "issued_quantity", "damaged_quantity", "lost_quantity",
  "description", "image_key", "tracking_mode", "is_public", "public_self_checkout_enabled", "show_public_count",
  "public_availability_mode", "storage_location", "category", "box_code",
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

export async function parseFileSample(file: File) {
  if (file.name.toLowerCase().endsWith(".xlsx")) return parseFile(file);
  const data = await file.slice(0, sampleBytes).arrayBuffer();
  return parseDelimited(new TextDecoder().decode(data), file.name.toLowerCase().endsWith(".tsv") ? "\t" : undefined);
}

export async function parseFile(file: File) {
  const data = await file.arrayBuffer();
  if (file.name.toLowerCase().endsWith(".xlsx")) {
    const XLSX = await import("xlsx");
    const workbook = XLSX.read(data, { type: "array" });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    return XLSX.utils.sheet_to_json<RawRow>(sheet, { defval: "" });
  }
  return parseDelimited(new TextDecoder().decode(data), file.name.toLowerCase().endsWith(".tsv") ? "\t" : undefined);
}

export function parseDelimited(text: string, forcedDelimiter?: string) {
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

export function suggestMapping(headers: string[]): Mapping {
  return Object.fromEntries(fields.map((field) => {
    const accepted = new Set([field, ...aliases[field]].map(normalizeHeader));
    return [field, headers.find((header) => accepted.has(normalizeHeader(header)))];
  }).filter(([, header]) => header)) as Mapping;
}

export function mapRow(row: RawRow, mapping: Mapping) {
  return Object.fromEntries(fields.filter((field) => mapping[field]).map((field) => [field, row[mapping[field] as string] ?? ""])) as RawRow;
}

export function messageFor(messages: RowMessages) {
  return Object.entries(messages).map(([key, value]) => `${key}: ${value}`).join("; ");
}

export function labelFor(field: Field) {
  return field.replace(/_/g, " ");
}
