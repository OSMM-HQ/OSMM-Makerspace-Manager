import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Panel, type Makerspace, useStaffGet } from "./shared";
import {
  ErrorText,
  type FilamentSpool,
  type PrintPrinter,
  printingRequest,
} from "./PrintingPanelParts";

type ManualPrintLog = {
  id: number;
  title: string;
  printer_name: string | null;
  spool_label: string | null;
  grams_used: string;
  duration_minutes: number;
  requester_name: string;
  contact_email: string;
  contact_phone: string;
  logged_by_username: string | null;
  created_at: string;
};

type ManualLogsResponse = { results: ManualPrintLog[] } | ManualPrintLog[];

export function ManualPrintLogSection({
  makerspace,
  printers,
  spools,
}: {
  makerspace: Makerspace;
  printers: PrintPrinter[];
  spools: FilamentSpool[];
}) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [printerId, setPrinterId] = useState("");
  const [spoolId, setSpoolId] = useState("");
  const [gramsUsed, setGramsUsed] = useState("");
  const [durationMinutes, setDurationMinutes] = useState("");
  const [requesterName, setRequesterName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [note, setNote] = useState("");
  const logs = useStaffGet<ManualLogsResponse>(
    ["manual-print-logs", makerspace.id],
    `/printing/manage/manual-logs/?makerspace=${makerspace.id}`,
  );
  const compatibleSpools = spools.filter((spool) => {
    if (!spool.is_active) return false;
    if (!printerId) return true;
    return spool.printer === null || spool.printer === Number(printerId);
  });
  const logRows = Array.isArray(logs.data) ? logs.data : logs.data?.results ?? [];
  const gramsValue = Number(gramsUsed);
  const canSubmit = Boolean(
    title.trim()
    && printerId
    && spoolId
    && gramsUsed
    && Number.isFinite(gramsValue)
    && gramsValue > 0
  );

  const createLog = useMutation({
    mutationFn: () =>
      printingRequest("/printing/manage/manual-logs/", {
        method: "POST",
        body: JSON.stringify({
          makerspace_id: makerspace.id,
          printer_id: Number(printerId),
          filament_spool_id: Number(spoolId),
          grams_used: gramsUsed,
          duration_minutes: Number(durationMinutes) || 0,
          title: title.trim(),
          requester_name: requesterName.trim(),
          contact_email: contactEmail.trim(),
          contact_phone: contactPhone.trim(),
          note: note.trim(),
        }),
      }),
    onSuccess: () => {
      setTitle("");
      setPrinterId("");
      setSpoolId("");
      setGramsUsed("");
      setDurationMinutes("");
      setRequesterName("");
      setContactEmail("");
      setContactPhone("");
      setNote("");
      queryClient.invalidateQueries({ queryKey: ["print-spools", makerspace.id] });
      // The deduction also feeds printer cards (active spool remaining), so refresh them too.
      queryClient.invalidateQueries({ queryKey: ["print-printers", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["manual-print-logs", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["operations-report", "printing"] });
    },
  });

  return (
    <Panel title="Manual print log">
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (canSubmit) createLog.mutate();
        }}
      >
        <div className="grid gap-2 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_auto_auto]">
          <input
            className="desk-input min-w-0"
            placeholder="Print title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <select
            className="desk-input min-w-0"
            value={printerId}
            onChange={(event) => {
              setPrinterId(event.target.value);
              setSpoolId("");
            }}
          >
            <option value="">Select printer</option>
            {printers.map((printer) => (
              <option key={printer.id} value={printer.id}>{printer.name}</option>
            ))}
          </select>
          <select
            className="desk-input min-w-0"
            value={spoolId}
            onChange={(event) => setSpoolId(event.target.value)}
          >
            <option value="">Select spool</option>
            {compatibleSpools.map((spool) => (
              <option key={spool.id} value={spool.id}>
                {[spool.brand, spool.material, spool.color].filter(Boolean).join(" ")}
                {` (${spool.remaining_weight_grams}g)`}
              </option>
            ))}
          </select>
          <input
            className="desk-input min-w-0"
            placeholder="Grams used"
            type="number"
            min="0.01"
            step="0.01"
            value={gramsUsed}
            onChange={(event) => setGramsUsed(event.target.value)}
          />
          <input
            className="desk-input min-w-0"
            placeholder="Print time (min)"
            type="number"
            min="0"
            step="1"
            value={durationMinutes}
            onChange={(event) => setDurationMinutes(event.target.value)}
          />
        </div>
        <div className="grid gap-2 md:grid-cols-3">
          <input
            className="desk-input min-w-0"
            placeholder="Name"
            value={requesterName}
            onChange={(event) => setRequesterName(event.target.value)}
          />
          <input
            className="desk-input min-w-0"
            placeholder="Email"
            type="email"
            value={contactEmail}
            onChange={(event) => setContactEmail(event.target.value)}
          />
          <input
            className="desk-input min-w-0"
            placeholder="Phone"
            value={contactPhone}
            onChange={(event) => setContactPhone(event.target.value)}
          />
        </div>
        <textarea
          className="desk-input min-h-20"
          placeholder="Note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
        <div className="desk-actions flex flex-wrap items-center gap-2">
          <button type="submit" disabled={!canSubmit || createLog.isPending}>
            {createLog.isPending ? "Logging..." : "Log print"}
          </button>
          <ErrorText message={createLog.error instanceof Error ? createLog.error.message : undefined} />
        </div>
      </form>

      <div className="mt-4 grid gap-2">
        {logs.isLoading ? <p className="text-sm text-muted">Loading manual logs...</p> : null}
        {logRows.map((log) => (
          <article key={log.id} className="rounded-md border border-line bg-surface px-3 py-2 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <strong className="text-ink">{log.title}</strong>
              <span className="text-muted">
                {Number(log.grams_used).toFixed(2)}g
                {log.duration_minutes ? ` · ${log.duration_minutes} min` : ""}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted">
              {[log.printer_name, log.spool_label].filter(Boolean).join(" - ") || "No printer"}
            </p>
            {log.requester_name || log.contact_email || log.contact_phone ? (
              <p className="mt-1 text-xs text-muted">
                <span className="font-medium text-ink">For: </span>
                {[log.requester_name, log.contact_email, log.contact_phone].filter(Boolean).join(" - ")}
              </p>
            ) : null}
            <p className="mt-1 text-xs text-muted">
              {log.logged_by_username ?? "Unknown"} - {new Date(log.created_at).toLocaleString()}
            </p>
          </article>
        ))}
        {!logs.isLoading && !logRows.length ? <p className="text-sm text-muted">No manual logs yet.</p> : null}
        <ErrorText message={logs.error instanceof Error ? logs.error.message : undefined} />
      </div>
    </Panel>
  );
}
