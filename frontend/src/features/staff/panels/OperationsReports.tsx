import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { downloadStaffFile } from "../../../lib/api";
import { DataState, StatCards } from "./OperationsReportsParts";
import { OperationsReportsFablab } from "./OperationsReportsFablab";
import { OperationsReportsHardware } from "./OperationsReportsHardware";
import { OperationsReportsMachineService } from "./OperationsReportsMachineService";
import { OperationsReportsMembers } from "./OperationsReportsMembers";
import { PrintingReportSection } from "./OperationsReportsPrinting";
import { Panel, type Makerspace, useStaffGet } from "./shared";

type Summary = {
  products: number; assets: number; active_loans: number;
  available_quantity: number; issued_quantity: number;
  damaged_quantity: number; missing_quantity: number;
};

const reportDefinitions = [
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
] as const;

type ReportKey = (typeof reportDefinitions)[number]["key"];

type SavedReportView = {
  id: string; name: string; startDate: string; endDate: string;
  scope: "all" | `makerspace:${number}`; scopeLabel: string;
  selectedReport: ReportKey;
};

const savedViewsStorageKey = "operations-reports-saved-views-v1";
const exportReports = reportDefinitions.map((report) => report.key).filter((key) => key !== "summary");
function sourceModule(key: ReportKey) {
  if (key === "machine-usage" || key === "maintenance-activity") return "machines";
  if (key === "event-attendance") return "events";
  if (key === "booking-utilization") return "bookings";
  return null;
}
function isReportKey(value: string): value is ReportKey {
  return reportDefinitions.some((report) => report.key === value);
}

function reportTitle(key: ReportKey) {
  return reportDefinitions.find((report) => report.key === key)?.title ?? key;
}

function newSavedViewId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function loadSavedReportViews(): SavedReportView[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(savedViewsStorageKey);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((view): view is SavedReportView => {
      return Boolean(
        view &&
          typeof view.id === "string" &&
          typeof view.name === "string" &&
          typeof view.startDate === "string" &&
          typeof view.endDate === "string" &&
          typeof view.scope === "string" &&
          typeof view.scopeLabel === "string" &&
          typeof view.selectedReport === "string" &&
          isReportKey(view.selectedReport),
      );
    });
  } catch {
    return [];
  }
}

export function OperationsReports({
  makerspace,
  makerspaces,
  isSuperadmin,
  printingOnly = false,
  canViewAudit,
  canSeePrinting,
  canManageMachines,
}: {
  makerspace: Makerspace;
  makerspaces: Makerspace[];
  isSuperadmin: boolean;
  printingOnly?: boolean;
  canViewAudit: boolean;
  canSeePrinting: boolean;
  canManageMachines: boolean;
}) {
  const [allMakerspaces, setAllMakerspaces] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedReport, setSelectedReport] = useState<ReportKey>("most-lent");
  const [presetName, setPresetName] = useState("");
  const [savedViews, setSavedViews] = useState<SavedReportView[]>(loadSavedReportViews);
  useEffect(() => {
    window.localStorage.setItem(savedViewsStorageKey, JSON.stringify(savedViews));
  }, [savedViews]);
  const aggregate = isSuperadmin && allMakerspaces;
  const scopeKey = aggregate ? "all" : makerspace.id;
  const analyticsBase = aggregate ? "/admin/analytics" : `/admin/makerspace/${makerspace.id}/analytics`;
  const reportsBase = aggregate ? "/admin/reports" : `/admin/makerspace/${makerspace.id}/reports`;
  const dateQuery = [startDate ? `start=${encodeURIComponent(startDate)}` : "", endDate ? `end=${encodeURIComponent(endDate)}` : ""].filter(Boolean).join("&");
  const dateSuffix = dateQuery ? `&${dateQuery}` : "";
  const reportsEnabled = aggregate || (makerspace.enabled_modules ?? []).includes("reports");
  const hardwareEnabled = canViewAudit && reportsEnabled;
  const summary = useStaffGet<Summary>(["operations-report", "summary", scopeKey, startDate, endDate], `${analyticsBase}/summary?${dateQuery}`, hardwareEnabled);

  const scopeLabel = aggregate ? "all makerspaces" : makerspace.name;
  const currentScope: SavedReportView["scope"] = aggregate ? "all" : `makerspace:${makerspace.id}`;
  const makerspaceName = (id: number) => makerspaces.find((space) => space.id === id)?.name ?? `#${id}`;
  const availableExports = exportReports.filter((key) => {
    if (!reportsEnabled) return false;
    const module = sourceModule(key);
    if (key === "maintenance-activity" && !aggregate && !(makerspace.enabled_modules ?? []).includes("maintenance")) return false;
    return aggregate || module === null || (makerspace.enabled_modules ?? []).includes(module);
  });
  const saveCurrentView = () => {
    const name = presetName.trim() || `${reportTitle(selectedReport)} - ${scopeLabel}`;
    const view: SavedReportView = {
      id: newSavedViewId(),
      name,
      startDate,
      endDate,
      scope: currentScope,
      scopeLabel,
      selectedReport,
    };
    setSavedViews((existing) => [view, ...existing.filter((item) => item.name !== name)].slice(0, 12));
    setPresetName("");
  };

  const applySavedView = (view: SavedReportView) => {
    setStartDate(view.startDate);
    setEndDate(view.endDate);
    setSelectedReport(view.selectedReport);
    setAllMakerspaces(view.scope === "all" && isSuperadmin);
  };

  const removeSavedView = (id: string) => {
    setSavedViews((existing) => existing.filter((view) => view.id !== id));
  };

  const exportReport = useMutation({
    mutationFn: ({ report, format }: { report: string; format: "csv" | "xlsx" }) =>
      downloadStaffFile(
        `${reportsBase}/${report}/export?format=${format}${dateSuffix}`,
        `${aggregate ? "all-makerspaces-" : ""}${report}.${format}`,
      ),
  });

  return (
    <div className="space-y-4">
      <Panel title="Reports">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-ink">
              {printingOnly ? "3D printing reporting" : "Operations reporting"} for {scopeLabel}
            </p>
            <p className="text-xs text-muted">
              {printingOnly
                ? "Print jobs, printer hours, and filament usage."
                : "Inventory movement, borrower activity, exceptions, and print usage."}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="grid gap-1 text-xs text-muted">
              <span>Start</span>
              <input className="desk-input" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            </label>
            <label className="grid gap-1 text-xs text-muted">
              <span>End</span>
              <input className="desk-input" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
            </label>
            <label className="grid gap-1 text-xs text-muted">
              <span>Report</span>
              <select className="desk-input" value={selectedReport} onChange={(event) => setSelectedReport(event.target.value as ReportKey)}>
                {reportDefinitions.map((report) => (
                  <option key={report.key} value={report.key}>
                    {report.title}
                  </option>
                ))}
              </select>
            </label>
            {isSuperadmin ? (
              <label className="flex items-center gap-2 pb-2 text-sm text-ink">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-current"
                  checked={allMakerspaces}
                  onChange={(event) => setAllMakerspaces(event.target.checked)}
                />
                All makerspaces
              </label>
            ) : null}
          </div>
        </div>
        <div className="mt-4 space-y-3 border-t border-line pt-3">
          <div className="flex flex-wrap items-end gap-2">
            <label className="grid min-w-48 gap-1 text-xs text-muted">
              <span>View name</span>
              <input
                className="desk-input"
                value={presetName}
                onChange={(event) => setPresetName(event.target.value)}
                placeholder={`${reportTitle(selectedReport)} - ${scopeLabel}`}
              />
            </label>
            <button className="desk-button" type="button" onClick={saveCurrentView}>
              Save view
            </button>
          </div>
          {savedViews.length ? (
            <div className="flex flex-wrap gap-2">
              {savedViews.map((view) => (
                <div key={view.id} className="flex items-center gap-1 rounded-md border border-line bg-bg px-2 py-1">
                  <button className="text-sm font-semibold text-ink" type="button" onClick={() => applySavedView(view)}>
                    {view.name}
                  </button>
                  <span className="text-xs text-muted">
                    {reportTitle(view.selectedReport)} / {view.scopeLabel}
                  </span>
                  <button className="px-1 text-sm text-danger" type="button" onClick={() => removeSavedView(view.id)} aria-label={`Remove ${view.name}`}>
                    x
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        {!printingOnly && reportsEnabled ? (
          <DataState loading={summary.isLoading} error={summary.error} empty={!summary.data}>
            <StatCards
              stats={[
                ["Products", summary.data?.products],
                ["Assets", summary.data?.assets],
                ["Active loans", summary.data?.active_loans],
                ["Available", summary.data?.available_quantity],
                ["Issued", summary.data?.issued_quantity],
                ["Damaged", summary.data?.damaged_quantity],
                ["Missing", summary.data?.missing_quantity],
              ]}
            />
          </DataState>
        ) : !printingOnly ? <p className="mt-3 text-sm text-muted">Module disabled</p> : null}
      </Panel>

      {!printingOnly ? (
      <>
      <Panel title="Exports">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {availableExports.map((report) => (
            <div key={report} className={`rounded-md border p-3 ${selectedReport === report ? "border-accent bg-accent/10" : "border-line bg-bg"}`}>
              <p className="text-sm font-semibold text-ink">{reportTitle(report)}</p>
              <div className="mt-3 flex gap-2">
                <button className="desk-button" type="button" disabled={exportReport.isPending} onClick={() => { setSelectedReport(report); exportReport.mutate({ report, format: "csv" }); }}>
                  CSV
                </button>
                <button className="desk-button" type="button" disabled={exportReport.isPending} onClick={() => { setSelectedReport(report); exportReport.mutate({ report, format: "xlsx" }); }}>
                  XLSX
                </button>
              </div>
            </div>
          ))}
        </div>
        {exportReport.error ? (
          <p className="mt-3 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {exportReport.error instanceof Error ? exportReport.error.message : "Could not export report."}
          </p>
        ) : null}
      </Panel>

      <OperationsReportsHardware analyticsBase={analyticsBase} scopeKey={scopeKey} startDate={startDate} endDate={endDate} enabled={hardwareEnabled} aggregate={aggregate} makerspaceName={makerspaceName} />
      <OperationsReportsMembers makerspaceId={makerspace.id} aggregate={aggregate} startDate={startDate} endDate={endDate} enabled={hardwareEnabled} />
      </>
      ) : null}

      {!printingOnly ? <OperationsReportsFablab makerspace={makerspace} aggregate={aggregate} canViewAudit={canViewAudit} startDate={startDate} endDate={endDate} makerspaceName={makerspaceName} /> : null}

      <OperationsReportsMachineService makerspace={makerspace} aggregate={aggregate} canManageMachines={canManageMachines} startDate={startDate} endDate={endDate} makerspaceName={makerspaceName} />

      {canSeePrinting ? (
        <PrintingReportSection makerspace={makerspace} aggregate={aggregate} makerspaceName={makerspaceName} startDate={startDate} endDate={endDate} />
      ) : null}
    </div>
  );
}


