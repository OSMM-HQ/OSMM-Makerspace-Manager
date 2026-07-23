export const reportDefinitions = [
  { key: "summary", title: "Summary" },
  { key: "taken-items", title: "Taken items" },
  { key: "active-loans", title: "Active loans" },
  { key: "returns", title: "Returns" },
  { key: "damaged-missing", title: "Damaged / missing" },
  { key: "damaged-lost", title: "Damaged / lost" },
  { key: "qr-scans", title: "QR scans" },
  { key: "most-lent", title: "Most lent" },
  { key: "top-borrowers", title: "Top borrowers" },
  { key: "recently-added", title: "Recently added" },
  { key: "machine-usage", title: "Machine usage" },
  { key: "event-attendance", title: "Event attendance" },
  { key: "booking-utilization", title: "Booking utilization" },
  { key: "maintenance-activity", title: "Maintenance activity" },
  { key: "member-activity", title: "Member activity" },
  { key: "fablab-health", title: "FabLab health" },
  { key: "payment-reconciliation", title: "Payment reconciliation" },
] as const;

export type ReportKey = (typeof reportDefinitions)[number]["key"];

export type SavedReportView = {
  id: string; name: string; startDate: string; endDate: string;
  scope: "all" | `makerspace:${number}`; scopeLabel: string;
  selectedReport: ReportKey;
};

export const savedViewsStorageKey = "operations-reports-saved-views-v1";
export const exportReports = reportDefinitions.map((report) => report.key).filter((key) => key !== "summary");

export function sourceModule(key: ReportKey) {
  if (key === "machine-usage" || key === "maintenance-activity") return "machines";
  if (key === "event-attendance") return "events";
  if (key === "booking-utilization") return "bookings";
  return null;
}

export function reportTitle(key: ReportKey) {
  return reportDefinitions.find((report) => report.key === key)?.title ?? key;
}

export function newSavedViewId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function loadSavedReportViews(): SavedReportView[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(savedViewsStorageKey);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((view): view is SavedReportView => Boolean(
      view && typeof view.id === "string" && typeof view.name === "string" &&
      typeof view.startDate === "string" && typeof view.endDate === "string" &&
      typeof view.scope === "string" && typeof view.scopeLabel === "string" &&
      typeof view.selectedReport === "string" &&
      reportDefinitions.some((report) => report.key === view.selectedReport),
    ));
  } catch {
    return [];
  }
}
