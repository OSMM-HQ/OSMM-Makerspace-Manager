import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { downloadStaffFile } from "../../../lib/api";
import {
  BarChart,
  DataState,
  PerMakerspaceTables,
  ReportTable,
  StatCards,
  chartRows,
  reportRows,
  type ReportRows,
} from "./OperationsReportsParts";
import { PrintingReportSection } from "./OperationsReportsPrinting";
import { Panel, type Makerspace, useStaffGet } from "./shared";

type Summary = {
  products: number;
  assets: number;
  active_loans: number;
  available_quantity: number;
  issued_quantity: number;
  damaged_quantity: number;
  missing_quantity: number;
};

const exportReports = ["taken-items", "active-loans", "returns", "damaged-lost"] as const;

export function OperationsReports({
  makerspace,
  makerspaces,
  isSuperadmin,
  printingOnly = false,
  canViewAudit,
  canSeePrinting,
}: {
  makerspace: Makerspace;
  makerspaces: Makerspace[];
  isSuperadmin: boolean;
  printingOnly?: boolean;
  canViewAudit: boolean;
  canSeePrinting: boolean;
}) {
  const [allMakerspaces, setAllMakerspaces] = useState(false);
  const aggregate = isSuperadmin && allMakerspaces;
  const scopeKey = aggregate ? "all" : makerspace.id;
  const analyticsBase = aggregate ? "/admin/analytics" : `/admin/makerspace/${makerspace.id}/analytics`;
  const reportsBase = aggregate ? "/admin/reports" : `/admin/makerspace/${makerspace.id}/reports`;
  const analyticsPreview = (report: string) => `${analyticsBase}/${report}?limit=100`;

  // Hardware report data contains borrower PII and requires VIEW_AUDIT; print-only
  // users keep this tab for printing reports without firing hardware queries.
  const hardwareEnabled = canViewAudit;
  const summary = useStaffGet<Summary>(["operations-report", "summary", scopeKey], `${analyticsBase}/summary`, hardwareEnabled);
  const mostLent = useStaffGet<ReportRows>(["operations-report", "most-lent", scopeKey], analyticsPreview("most-lent"), hardwareEnabled);
  const topBorrowers = useStaffGet<ReportRows>(["operations-report", "top-borrowers", scopeKey], analyticsPreview("top-borrowers"), hardwareEnabled);
  const damagedLost = useStaffGet<ReportRows>(["operations-report", "damaged-lost", scopeKey], analyticsPreview("damaged-lost"), hardwareEnabled);
  const recentlyAdded = useStaffGet<ReportRows>(["operations-report", "recently-added", scopeKey], analyticsPreview("recently-added"), hardwareEnabled);

  const scopeLabel = aggregate ? "all makerspaces" : makerspace.name;
  const makerspaceName = (id: number) => makerspaces.find((space) => space.id === id)?.name ?? `#${id}`;

  const exportReport = useMutation({
    mutationFn: ({ report, format }: { report: string; format: "csv" | "xlsx" }) =>
      downloadStaffFile(
        `${reportsBase}/${report}/export?format=${format}`,
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
          {isSuperadmin ? (
            <label className="flex items-center gap-2 text-sm text-ink">
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
        {!printingOnly ? (
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
        ) : null}
      </Panel>

      {!printingOnly ? (
      <>
      <Panel title="Exports">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {exportReports.map((report) => (
            <div key={report} className="rounded-md border border-line bg-bg p-3">
              <p className="text-sm font-semibold capitalize text-ink">{report.replace(/-/g, " ")}</p>
              <div className="mt-3 flex gap-2">
                <button className="desk-button" type="button" disabled={exportReport.isPending} onClick={() => exportReport.mutate({ report, format: "csv" })}>
                  CSV
                </button>
                <button className="desk-button" type="button" disabled={exportReport.isPending} onClick={() => exportReport.mutate({ report, format: "xlsx" })}>
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

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Most lent">
          <DataState loading={mostLent.isLoading} error={mostLent.error} empty={!reportRows(mostLent.data).length}>
            <BarChart rows={chartRows(mostLent.data, "product_name", "times_lent")} valueLabel="loans" />
            <ReportTable data={mostLent.data} />
          </DataState>
        </Panel>

        <Panel title="Top borrowers">
          <DataState loading={topBorrowers.isLoading} error={topBorrowers.error} empty={!reportRows(topBorrowers.data).length}>
            {aggregate ? (
              <PerMakerspaceTables data={topBorrowers.data} nameOf={makerspaceName} />
            ) : (
              <>
                <BarChart rows={chartRows(topBorrowers.data, "holder", "requests")} valueLabel="requests" />
                <ReportTable data={topBorrowers.data} />
              </>
            )}
          </DataState>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Damaged / lost">
          <DataState loading={damagedLost.isLoading} error={damagedLost.error} empty={!reportRows(damagedLost.data).length}>
            <ReportTable data={damagedLost.data} />
          </DataState>
        </Panel>

        <Panel title="Recently added">
          <DataState loading={recentlyAdded.isLoading} error={recentlyAdded.error} empty={!reportRows(recentlyAdded.data).length}>
            <ReportTable data={recentlyAdded.data} />
          </DataState>
        </Panel>
      </div>
      </>
      ) : null}

      {canSeePrinting ? (
        <PrintingReportSection makerspace={makerspace} aggregate={aggregate} makerspaceName={makerspaceName} />
      ) : null}
    </div>
  );
}


