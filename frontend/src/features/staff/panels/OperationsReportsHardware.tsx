import { BarChart, DataState, PerMakerspaceTables, ReportTable, chartRows, reportRows, type ReportRows } from "./OperationsReportsParts";
import { Panel, useStaffGet } from "./shared";

function useHardwareReport(key: string, analyticsBase: string, scopeKey: string | number, startDate: string, endDate: string, enabled: boolean) {
  const dateQuery = [startDate && `start=${encodeURIComponent(startDate)}`, endDate && `end=${encodeURIComponent(endDate)}`].filter(Boolean).join("&");
  const path = `${analyticsBase}/${key}?limit=100${dateQuery ? `&${dateQuery}` : ""}`;
  return useStaffGet<ReportRows>(["operations-report", key, scopeKey, startDate, endDate], path, enabled);
}

export function OperationsReportsHardware({
  analyticsBase, scopeKey, startDate, endDate, enabled, aggregate, makerspaceName,
}: {
  analyticsBase: string;
  scopeKey: string | number;
  startDate: string;
  endDate: string;
  enabled: boolean;
  aggregate: boolean;
  makerspaceName: (id: number) => string;
}) {
  const mostLent = useHardwareReport("most-lent", analyticsBase, scopeKey, startDate, endDate, enabled);
  const topBorrowers = useHardwareReport("top-borrowers", analyticsBase, scopeKey, startDate, endDate, enabled);
  const damagedLost = useHardwareReport("damaged-lost", analyticsBase, scopeKey, startDate, endDate, enabled);
  const recentlyAdded = useHardwareReport("recently-added", analyticsBase, scopeKey, startDate, endDate, enabled);
  const takenItems = useHardwareReport("taken-items", analyticsBase, scopeKey, startDate, endDate, enabled);
  const activeLoans = useHardwareReport("active-loans", analyticsBase, scopeKey, startDate, endDate, enabled);
  const returns = useHardwareReport("returns", analyticsBase, scopeKey, startDate, endDate, enabled);
  const qrScans = useHardwareReport("qr-scans", analyticsBase, scopeKey, startDate, endDate, enabled);
  return (
    <>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Most lent"><DataState loading={mostLent.isLoading} error={mostLent.error} empty={!reportRows(mostLent.data).length}><BarChart rows={chartRows(mostLent.data, "product_name", "times_lent")} valueLabel="loans" /><ReportTable data={mostLent.data} /></DataState></Panel>
        <Panel title="Top borrowers"><DataState loading={topBorrowers.isLoading} error={topBorrowers.error} empty={!reportRows(topBorrowers.data).length}>{aggregate ? <PerMakerspaceTables data={topBorrowers.data} nameOf={makerspaceName} /> : <><BarChart rows={chartRows(topBorrowers.data, "holder", "requests")} valueLabel="requests" /><ReportTable data={topBorrowers.data} /></>}</DataState></Panel>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ReportPanel title="Damaged / lost" query={damagedLost} />
        <ReportPanel title="Recently added" query={recentlyAdded} />
        <ReportPanel title="Taken items" query={takenItems} />
        <ReportPanel title="Active loans" query={activeLoans} />
        <ReportPanel title="Returns" query={returns} />
        <ReportPanel title="QR scans" query={qrScans} />
      </div>
    </>
  );
}

function ReportPanel({ title, query }: { title: string; query: { isLoading: boolean; error: unknown; data?: ReportRows } }) {
  return <Panel title={title}><DataState loading={query.isLoading} error={query.error} empty={!reportRows(query.data).length}><ReportTable data={query.data} /></DataState></Panel>;
}
