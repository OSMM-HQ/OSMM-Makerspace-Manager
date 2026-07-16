import { BarChart, DataState, PerMakerspaceTables, ReportTable, StatCards } from "./OperationsReportsParts";
import { Panel } from "./shared";
import { sum, useFablabReport, type FablabPanelProps, type MachineUsageRow } from "./operationsReportsFablabApi";

export function OperationsReportsMachineUsage(props: FablabPanelProps) {
  const query = useFablabReport<MachineUsageRow>("machine-usage", props);
  if (!props.enabled) return <Panel title="Machine usage"><p className="text-sm text-muted">Module disabled</p></Panel>;
  const rows = query.data?.typed_rows ?? [];
  return (
    <Panel title="Machine usage">
      <DataState loading={query.isLoading} error={query.error} empty={!rows.length}>
        <StatCards stats={[["Usage hours", sum(rows, "usage_hours")], ["Usage entries", sum(rows, "usage_entries")], ["Machines", rows.length], ["Active", rows.filter((row) => row.is_active).length]]} />
        <div className="mt-4"><BarChart rows={rows.slice(0, 10).map((row) => ({ label: row.machine_name, value: Number(row.usage_hours) }))} valueLabel="hours" /></div>
        {props.aggregate ? <PerMakerspaceTables data={query.data} nameOf={props.makerspaceName} /> : <ReportTable data={query.data} />}
      </DataState>
    </Panel>
  );
}
