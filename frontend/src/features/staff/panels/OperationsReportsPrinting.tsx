import { useState } from "react";

import { BarChart, DataState, PerMakerspaceTables, PieChart, ReportTable, StatCards } from "./OperationsReportsParts";
import { PrinterHoursTable, PrinterOutcomesTable } from "./OperationsReportsPrintingTables";
import { Panel, type Makerspace, useStaffGet } from "./shared";

export type PrintingReport = {
  totals: Record<string, number>;
  payments: {
    paid_amount: string;
    paid_count: number;
    outstanding_amount: string;
    outstanding_count: number;
  };
  printer_hours: {
    printer_id: number;
    printer_name: string;
    image_url?: string | null;
    completed_requests: number;
    hours: number;
    makerspace_id?: number;
  }[];
  printer_outcomes: {
    printer_id: number;
    printer_name: string;
    image_url?: string | null;
    completed: number;
    failed: number;
    grams_used: number;
    makerspace_id?: number;
  }[];
  filament_used: {
    spool_id: number;
    material: string;
    color: string;
    grams_used: number;
    remaining_grams: number;
    makerspace_id?: number;
  }[];
  filament_by_brand: { brand: string; grams_used: number; spools: number }[];
  top_requesters: {
    requester_id: number;
    requester: string;
    grams: number;
    requests: number;
    items: number;
    makerspace_id?: number;
  }[];
  total_grams_used: number;
  filament_estimated_by_period: {
    by_month: { period: string; grams: number }[];
    by_day: { period: string; grams: number }[];
    by_hour: { period: string; grams: number }[];
  };
};

type PeriodKey = "month" | "day" | "hour";

const periods: { key: PeriodKey; label: string; dataKey: keyof PrintingReport["filament_estimated_by_period"] }[] = [
  { key: "month", label: "Month", dataKey: "by_month" },
  { key: "day", label: "Day", dataKey: "by_day" },
  { key: "hour", label: "Hour", dataKey: "by_hour" },
];

// Print-status pie slices, in a stable display order.
const statusPie: { key: keyof PrintingReport["totals"]; label: string }[] = [
  { key: "completed", label: "Completed" },
  { key: "collected", label: "Collected" },
  { key: "printing", label: "Printing" },
  { key: "pending", label: "Pending" },
  { key: "accepted", label: "Accepted" },
  { key: "failed", label: "Failed" },
  { key: "rejected", label: "Rejected" },
];

export function PrintingReportSection({
  makerspace,
  aggregate,
  makerspaceName,
}: {
  makerspace: Makerspace;
  aggregate: boolean;
  makerspaceName?: (id: number) => string;
}) {
  const nameOf = (id: number) => (makerspaceName ? makerspaceName(id) : `#${id}`);
  const [period, setPeriod] = useState<PeriodKey>("month");
  const scopeKey = aggregate ? "all" : makerspace.id;
  // printing routes are mounted under /api/v1/printing/ (not /api/v1/admin/).
  const printingPath = aggregate
    ? "/printing/admin/printing/reports"
    : `/printing/admin/makerspace/${makerspace.id}/printing/reports`;
  const printing = useStaffGet<PrintingReport>(["operations-report", "printing", scopeKey], printingPath);

  const activePeriod = periods.find((item) => item.key === period) ?? periods[0];
  const filamentRows = printing.data?.filament_estimated_by_period[activePeriod.dataKey] ?? [];
  const statusRows = statusPie
    .map((item) => ({ label: item.label, value: printing.data?.totals[item.key] ?? 0 }))
    .filter((row) => row.value > 0);
  const brandRows = (printing.data?.filament_by_brand ?? [])
    .slice(0, 8)
    .map((row) => ({ label: row.brand, value: row.grams_used }));

  return (
    <Panel title="3D printing">
      <DataState loading={printing.isLoading} error={printing.error} empty={!printing.data}>
        <div className="space-y-5">
          <StatCards
            stats={[
              ["Total requests", printing.data?.totals.total_requests],
              ["Completed", printing.data?.totals.completed],
              ["Collected", printing.data?.totals.collected],
              ["Printing", printing.data?.totals.printing],
              ["Pending", printing.data?.totals.pending],
              ["Accepted", printing.data?.totals.accepted],
              ["Failed", printing.data?.totals.failed],
              ["Rejected", printing.data?.totals.rejected],
              ["Spool grams used", printing.data?.total_grams_used],
            ]}
          />

          <div>
            <h3 className="mb-2 text-sm font-semibold text-ink">Payments</h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-md border border-line bg-surface p-3">
                <p className="text-2xl font-bold text-ink">{printing.data?.payments.paid_amount ?? "0"}</p>
                <p className="text-xs text-muted">Collected ({printing.data?.payments.paid_count ?? 0})</p>
              </div>
              <div className="rounded-md border border-line bg-surface p-3">
                <p className="text-2xl font-bold text-ink">{printing.data?.payments.outstanding_amount ?? "0"}</p>
                <p className="text-xs text-muted">Outstanding ({printing.data?.payments.outstanding_count ?? 0})</p>
              </div>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="rounded-md border border-line bg-bg p-3">
              <h3 className="mb-3 text-sm font-semibold text-ink">Requests by status</h3>
              <PieChart rows={statusRows} valueLabel="" />
            </div>
            <div className="rounded-md border border-line bg-bg p-3">
              <h3 className="mb-3 text-sm font-semibold text-ink">Filament share by brand</h3>
              <PieChart rows={brandRows} valueLabel="g" />
            </div>
          </div>

          <div>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-ink">Estimated filament</h3>
              <div className="flex rounded-md border border-line bg-bg p-1">
                {periods.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    className={`rounded px-3 py-1 text-xs font-semibold ${period === item.key ? "bg-surface text-accent-ink" : "text-muted"}`}
                    onClick={() => setPeriod(item.key)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <BarChart rows={filamentRows.map((row) => ({ label: row.period, value: row.grams }))} valueLabel="g" />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-ink">Printer hours</h3>
              <PrinterHoursTable rows={printing.data?.printer_hours ?? []} aggregate={aggregate} />
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-ink">Printer outcomes (success / fail / grams)</h3>
              <PrinterOutcomesTable rows={printing.data?.printer_outcomes ?? []} aggregate={aggregate} />
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-ink">Filament used</h3>
              <ReportTable
                data={{
                  rows: [
                    aggregate
                      ? ["makerspace_id", "material", "color", "grams_used", "remaining_grams"]
                      : ["material", "color", "grams_used", "remaining_grams"],
                    ...(printing.data?.filament_used ?? []).map((row) =>
                      aggregate
                        ? [row.makerspace_id ?? "", row.material, row.color, row.grams_used, row.remaining_grams]
                        : [row.material, row.color, row.grams_used, row.remaining_grams],
                    ),
                  ],
                }}
              />
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-ink">Filament by brand</h3>
              <BarChart
                rows={(printing.data?.filament_by_brand ?? []).slice(0, 8).map((row) => ({ label: row.brand, value: row.grams_used }))}
                valueLabel="g"
              />
              <ReportTable
                data={{
                  rows: [
                    ["brand", "grams_used", "spools"],
                    ...(printing.data?.filament_by_brand ?? []).map((row) => [row.brand, row.grams_used, row.spools]),
                  ],
                }}
              />
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-ink">Top requesters (by grams printed)</h3>
              {aggregate ? (
                <PerMakerspaceTables
                  data={{
                    rows: [
                      ["makerspace_id", "requester", "grams", "requests", "items"],
                      ...(printing.data?.top_requesters ?? []).map((row) => [
                        row.makerspace_id ?? "",
                        row.requester,
                        row.grams,
                        row.requests,
                        row.items,
                      ]),
                    ],
                  }}
                  nameOf={nameOf}
                />
              ) : (
                <>
                  <BarChart
                    rows={(printing.data?.top_requesters ?? []).slice(0, 8).map((row) => ({ label: row.requester, value: row.grams }))}
                    valueLabel="g"
                  />
                  <ReportTable
                    data={{
                      rows: [
                        ["requester", "grams", "requests", "items"],
                        ...(printing.data?.top_requesters ?? []).map((row) => [row.requester, row.grams, row.requests, row.items]),
                      ],
                    }}
                  />
                </>
              )}
            </div>
          </div>
        </div>
      </DataState>
    </Panel>
  );
}
