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
  image_url?: string | null;
  is_active: boolean;
  active_spool: FilamentSpool | null;
  current_request: { id: number; title: string; estimated_minutes: number } | null;
  is_free: boolean;
  pending_estimated_minutes: number;
  estimated_spool_remaining_after_queue_grams: string | null;
};

export type PrintActor = {
  username: string;
  role: string;
};

export type PrintRequest = {
  id: number;
  title: string;
  requester_username: string;
  requester_display?: string;
  status: string;
  price?: string;
  payment_status?: "none" | "pending" | "paid";
  paid_at?: string | null;
  collected_at?: string | null;
  accepted_by?: PrintActor | null;
  collected_by?: number | null;
  material: string;
  color: string;
  estimated_minutes: number;
  estimated_filament_grams: string;
  filament_grams_reserved?: string;
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
    original_filename: string;
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

export const SPOOL_COLORS = [
  "Black", "White", "Gray", "Silver", "Red", "Orange", "Yellow", "Green",
  "Blue", "Purple", "Pink", "Brown", "Gold", "Transparent", "Natural",
];

export const SPOOL_COLOR_SWATCHES: Record<string, string> = {
  Black: "#000000",
  White: "#FFFFFF",
  Gray: "#6B7280",
  Silver: "#C0C0C0",
  Red: "#EF4444",
  Orange: "#F97316",
  Yellow: "#FACC15",
  Green: "#4ADE80",
  Blue: "#60A5FA",
  Purple: "#A855F7",
  Pink: "#EC4899",
  Brown: "#7C3F1D",
  Gold: "#D4AF37",
  Transparent: "#E5E7EB",
  Natural: "#F5F0E1",
};

export function SpoolColorInput({
  value,
  onChange,
  className = "desk-input",
}: {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  const options = SPOOL_COLORS.includes(value) || !value ? SPOOL_COLORS : [value, ...SPOOL_COLORS];
  const pickerValue = /^#[0-9a-f]{6}$/i.test(value)
    ? value
    : SPOOL_COLOR_SWATCHES[value] ?? "#888888";
  return (
    <div className="grid min-w-0 gap-2">
      <div className="flex flex-wrap gap-2">
        {SPOOL_COLORS.map((color) => {
          const selected = value === color;
          const needsBorder = color === "White" || color === "Transparent" || color === "Natural";
          return (
            <button
              key={color}
              type="button"
              aria-label={color}
              aria-pressed={selected}
              title={color}
              className={`h-8 w-8 rounded-full focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg ${
                selected ? "ring-2 ring-accent ring-offset-2 ring-offset-bg" : ""
              } ${needsBorder ? "border border-line" : "border border-transparent"}`}
              style={{ backgroundColor: SPOOL_COLOR_SWATCHES[color] }}
              onClick={() => onChange(color)}
            />
          );
        })}
      </div>
      <select className={className} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Select colour</option>
        {options.map((color) => (
          <option key={color} value={color}>
            {color}
          </option>
        ))}
      </select>
      <div className="flex min-w-0 flex-wrap gap-2">
        <input
          type="color"
          className="h-10 w-12 shrink-0 cursor-pointer rounded-md border border-line bg-surface p-1"
          aria-label="Custom colour picker"
          value={pickerValue}
          onChange={(event) => onChange(event.target.value)}
        />
        <input
          className={`${className} min-w-0 flex-1`}
          value={value}
          placeholder="Custom colour"
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
    </div>
  );
}
