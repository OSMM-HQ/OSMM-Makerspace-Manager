import { BarChart, DataState, PerMakerspaceTables, PieChart, ReportTable, StatCards } from "./OperationsReportsParts";
import { Panel } from "./shared";
import { sum, useFablabReport, type EventAttendanceRow, type FablabPanelProps } from "./operationsReportsFablabApi";

export function OperationsReportsEvents(props: FablabPanelProps) {
  const query = useFablabReport<EventAttendanceRow>("event-attendance", props);
  if (!props.enabled) return <Panel title="Events"><p className="text-sm text-muted">Module disabled</p></Panel>;
  const rows = query.data?.typed_rows ?? [];
  const statusRows = ["registered", "waitlisted", "cancelled", "attended"].map((key) => ({ label: key, value: sum(rows, key) }));
  return (
    <Panel title="Events attendance">
      <DataState loading={query.isLoading} error={query.error} empty={!rows.length}>
        <StatCards stats={[["Events", rows.length], ["Registrations", sum(rows, "registrations")], ["Confirmed", sum(rows, "confirmed")], ["Attended", sum(rows, "attended")]]} />
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <PieChart rows={statusRows} valueLabel="registrations" />
          <BarChart rows={rows.filter((row) => row.attendance_rate_percent !== null).map((row) => ({ label: row.title, value: row.attendance_rate_percent ?? 0 }))} valueLabel="% attended" />
        </div>
        {props.aggregate ? <PerMakerspaceTables data={query.data} nameOf={props.makerspaceName} /> : <ReportTable data={query.data} />}
      </DataState>
    </Panel>
  );
}
