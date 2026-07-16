import { BarChart, DataState, PerMakerspaceTables, ReportTable, StatCards } from "./OperationsReportsParts";
import { Panel } from "./shared";
import { sum, useFablabReport, type FablabPanelProps, type MaintenanceActivityRow } from "./operationsReportsFablabApi";

export function OperationsReportsMaintenance(props: FablabPanelProps) {
  const query = useFablabReport<MaintenanceActivityRow>("maintenance-activity", props);
  if (!props.enabled) return <Panel title="Maintenance"><p className="text-sm text-muted">Module disabled</p></Panel>;
  const rows = query.data?.typed_rows ?? [];
  const stats: [string, number | undefined][] = [["Logs", sum(rows, "log_count")], ["Overdue schedules (snapshot)", sum(rows, "overdue_schedules")], ["Active schedules (snapshot)", sum(rows, "active_schedules")]];
  if (!props.aggregate) stats.splice(1, 0, ["Recorded cost", sum(rows, "total_cost")]);
  return (
    <Panel title="Maintenance activity">
      <DataState loading={query.isLoading} error={query.error} empty={!rows.length}>
        <StatCards stats={stats} />
        {props.aggregate ? <p className="mt-3 text-xs text-muted">Recorded costs remain per makerspace and are never combined across makerspaces.</p> : null}
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <BarChart rows={rows.map((row) => ({ label: row.machine_name, value: row.log_count }))} valueLabel="logs" />
          <BarChart rows={rows.map((row) => ({ label: row.machine_name, value: Number(row.total_cost) }))} valueLabel="recorded cost" />
        </div>
        {props.aggregate ? <PerMakerspaceTables data={query.data} nameOf={props.makerspaceName} /> : <ReportTable data={query.data} />}
      </DataState>
    </Panel>
  );
}
