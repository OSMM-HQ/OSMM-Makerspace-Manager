import { useState } from "react";

import { EmptyState, Skeleton } from "../../../../components/ui";
import { MaintenanceDocuments } from "./MaintenanceDocuments";
import { MaintenanceSchedules } from "./MaintenanceSchedules";
import {
  useLogMaintenance,
  useMaintenanceLogs,
  useMaintenanceSchedules,
  type LogInput,
  type MaintenanceSchedule,
} from "./maintenanceApi";

type MaintenanceTabProps = {
  makerspaceId: number;
  machineId: number;
  canEdit: boolean;
  canOperate: boolean;
  retired: boolean;
};

export function MaintenanceTab({
  makerspaceId, machineId, canEdit, canOperate, retired,
}: MaintenanceTabProps) {
  const schedules = useMaintenanceSchedules(makerspaceId, machineId, true);
  const logs = useMaintenanceLogs(makerspaceId, machineId, true);
  const complete = useLogMaintenance(makerspaceId, machineId);

  const completeSchedule = (schedule: MaintenanceSchedule) => {
    if (!window.confirm(`Record "${schedule.description}" as completed now?`)) return;
    complete.mutate({ summary: schedule.description, schedule_id: schedule.id });
  };

  if (schedules.isLoading || logs.isLoading) {
    return (
      <div className="grid gap-3" aria-label="Loading maintenance details">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const queryError = schedules.error ?? logs.error;
  if (queryError instanceof Error) {
    return <EmptyState title="Unable to load maintenance" description={queryError.message} />;
  }

  const scheduleRows = schedules.data?.results ?? [];
  const logRows = logs.data?.results ?? [];

  return (
    <div className="grid gap-5">
      <MaintenanceSchedules
        makerspaceId={makerspaceId}
        machineId={machineId}
        schedules={scheduleRows}
        canEdit={canEdit}
        retired={retired}
        onComplete={completeSchedule}
      />
      {complete.error instanceof Error ? (
        <p className="text-sm text-danger" role="alert">{complete.error.message}</p>
      ) : null}
      {canOperate && !retired ? (
        <MaintenanceLogForm makerspaceId={makerspaceId} machineId={machineId} />
      ) : null}
      <section className="grid gap-3" aria-labelledby="maintenance-history-title">
        <h3 id="maintenance-history-title" className="text-sm font-semibold text-ink">
          Maintenance history
        </h3>
        {!logRows.length ? (
          <EmptyState
            title="No maintenance logged"
            description="Completed maintenance records will appear here."
          />
        ) : null}
        {logRows.map((log) => (
          <details key={log.id} className="rounded-lg border border-line bg-bg p-3">
            <summary className="cursor-pointer list-none text-sm marker:hidden">
              <span className="flex flex-wrap items-start justify-between gap-2">
                <strong className="min-w-0 flex-1 text-ink">{log.summary}</strong>
                <span className="text-xs text-muted">{formatDateTime(log.performed_at)}</span>
              </span>
              {log.cost ? <span className="mt-1 block text-xs text-muted">Cost: {log.cost}</span> : null}
            </summary>
            <div className="mt-3 border-t border-line pt-3 text-sm text-muted">
              {log.parts_note ? (
                <p className="whitespace-pre-wrap break-words">{log.parts_note}</p>
              ) : <p>No parts notes.</p>}
              <MaintenanceDocuments
                machineId={machineId}
                logId={log.id}
                documents={log.documents}
                canDelete={canEdit}
                retired={retired}
              />
            </div>
          </details>
        ))}
      </section>
    </div>
  );
}

function MaintenanceLogForm({ makerspaceId, machineId }: {
  makerspaceId: number;
  machineId: number;
}) {
  const [summary, setSummary] = useState("");
  const [performedAt, setPerformedAt] = useState("");
  const [cost, setCost] = useState("");
  const [partsNote, setPartsNote] = useState("");
  const [setIdle, setSetIdle] = useState(false);
  const log = useLogMaintenance(makerspaceId, machineId);

  const reset = () => {
    setSummary("");
    setPerformedAt("");
    setCost("");
    setPartsNote("");
    setSetIdle(false);
  };

  return (
    <section aria-labelledby="log-maintenance-title">
      <h3 id="log-maintenance-title" className="mb-3 text-sm font-semibold text-ink">
        Log maintenance
      </h3>
      <form
        className="grid gap-2 rounded-lg border border-line bg-surface p-3 sm:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault();
          const input: LogInput = {
            summary: summary.trim(),
            performed_at: performedAt ? new Date(performedAt).toISOString() : undefined,
            cost: cost.trim() || null,
            parts_note: partsNote.trim(),
            set_idle: setIdle,
          };
          log.mutate(input, { onSuccess: reset });
        }}
      >
        <label className="grid gap-1 text-xs font-semibold text-muted sm:col-span-2">
          Summary
          <input className="desk-input" value={summary}
            onChange={(event) => setSummary(event.target.value)} required />
        </label>
        <label className="grid gap-1 text-xs font-semibold text-muted">
          Performed at (optional)
          <input className="desk-input" type="datetime-local" value={performedAt}
            onChange={(event) => setPerformedAt(event.target.value)} />
        </label>
        <label className="grid gap-1 text-xs font-semibold text-muted">
          Cost (optional)
          <input className="desk-input" type="number" min="0" step="0.01" value={cost}
            onChange={(event) => setCost(event.target.value)} />
        </label>
        <label className="grid gap-1 text-xs font-semibold text-muted sm:col-span-2">
          Parts and notes (optional)
          <textarea className="desk-input min-h-20" value={partsNote}
            onChange={(event) => setPartsNote(event.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm text-muted sm:col-span-2">
          <input type="checkbox" checked={setIdle}
            onChange={(event) => setSetIdle(event.target.checked)} />
          Set machine status to idle
        </label>
        <button className="desk-button-primary justify-self-start" type="submit"
          disabled={log.isPending || !summary.trim()}>
          {log.isPending ? "Logging..." : "Log maintenance"}
        </button>
      </form>
      {log.error instanceof Error ? (
        <p className="mt-2 text-sm text-danger" role="alert">{log.error.message}</p>
      ) : null}
    </section>
  );
}

function formatDateTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
