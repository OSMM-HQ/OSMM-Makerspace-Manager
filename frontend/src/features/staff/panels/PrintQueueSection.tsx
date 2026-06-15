import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Panel, type Makerspace, useStaffGet } from "./shared";
import {
  ErrorText,
  type FilamentSpool,
  PrintRows,
  type PrintPrinter,
  type PrintRequest,
  printingRequest,
} from "./PrintingPanelParts";
import { FailPrintDialog } from "./PrintingPanelDialogs";

// The print queue (accepted -> printing -> complete/fail) lives here so it can be
// shown inside the unified "Requests" tab alongside hardware requests. Printer &
// spool management stays in PrintingPanel. Both query the same TanStack keys, so
// the shared cache means no duplicate network calls.
export function PrintQueueSection({ makerspace }: { makerspace: Makerspace }) {
  const queryClient = useQueryClient();
  const printers = useStaffGet<{ results: PrintPrinter[] }>(
    ["print-printers", makerspace.id],
    `/printing/manage/printers/?makerspace=${makerspace.id}`,
  );
  const spools = useStaffGet<{ results: FilamentSpool[] }>(
    ["print-spools", makerspace.id],
    `/printing/manage/spools/?makerspace=${makerspace.id}`,
  );
  const accepted = useStaffGet<{ results: PrintRequest[] }>(
    ["print-requests", makerspace.id, "accepted"],
    `/printing/manage/requests/?makerspace=${makerspace.id}&status=accepted`,
  );
  const printing = useStaffGet<{ results: PrintRequest[] }>(
    ["print-requests", makerspace.id, "printing"],
    `/printing/manage/requests/?makerspace=${makerspace.id}&status=printing`,
  );

  const [selectedPrinter, setSelectedPrinter] = useState("");
  const [selectedSpool, setSelectedSpool] = useState("");
  const [estimatedMinutes, setEstimatedMinutes] = useState("60");
  const [estimatedGrams, setEstimatedGrams] = useState("100");
  const [failingRequest, setFailingRequest] = useState<PrintRequest | null>(null);

  const action = useMutation({
    mutationFn: ({ request, name, reason }: { request: PrintRequest; name: "start" | "complete" | "fail"; reason?: string }) => {
      const body =
        name === "start"
          ? {
              printer_id: selectedPrinter ? Number(selectedPrinter) : undefined,
              filament_spool_id: selectedSpool ? Number(selectedSpool) : undefined,
              estimated_minutes: Number(estimatedMinutes),
              estimated_filament_grams: estimatedGrams,
            }
          : name === "fail"
            ? { reason }
            : {};
      return printingRequest(`/printing/manage/requests/${request.id}/${name}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      setFailingRequest(null);
      queryClient.invalidateQueries({ queryKey: ["print-printers", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["print-spools", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["print-requests", makerspace.id] });
    },
  });

  const printerRows = printers.data?.results ?? [];
  const spoolRows = spools.data?.results ?? [];
  const anyQueueLoading = accepted.isLoading || printing.isLoading;
  const actionError = action.error instanceof Error ? action.error.message : undefined;

  return (
    <Panel title="Print requests">
      {anyQueueLoading ? <p className="mb-3 text-sm text-muted">Loading queue...</p> : null}
      <div className="mb-3 grid gap-2 md:grid-cols-4">
        <select className="desk-input" value={selectedPrinter} onChange={(event) => setSelectedPrinter(event.target.value)}>
          <option value="">Printer</option>
          {printerRows.filter((printer) => printer.is_active).map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}
        </select>
        <select className="desk-input" value={selectedSpool} onChange={(event) => setSelectedSpool(event.target.value)}>
          <option value="">Spool</option>
          {spoolRows
            .filter((spool) => spool.is_active && (!selectedPrinter || spool.printer === Number(selectedPrinter) || spool.printer === null))
            .map((spool) => <option key={spool.id} value={spool.id}>{[spool.material, spool.color].filter(Boolean).join(" ")} ({spool.remaining_weight_grams}g)</option>)}
        </select>
        <input className="desk-input" type="number" min="0" value={estimatedMinutes} onChange={(event) => setEstimatedMinutes(event.target.value)} />
        <input className="desk-input" type="number" min="0" value={estimatedGrams} onChange={(event) => setEstimatedGrams(event.target.value)} />
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <PrintRows title="Accepted" rows={accepted.data?.results ?? []} action={(row) => (
          <button disabled={!selectedPrinter || action.isPending} onClick={() => action.mutate({ request: row, name: "start" })}>
            {action.isPending ? "Starting..." : "Start on printer"}
          </button>
        )} />
        <PrintRows title="Printing" rows={printing.data?.results ?? []} action={(row) => (
          <>
            <button disabled={action.isPending} onClick={() => action.mutate({ request: row, name: "complete" })}>Complete</button>
            <button disabled={action.isPending} onClick={() => setFailingRequest(row)}>Fail</button>
          </>
        )} />
      </div>
      <ErrorText message={accepted.error instanceof Error ? accepted.error.message : undefined} />
      <ErrorText message={printing.error instanceof Error ? printing.error.message : undefined} />
      <ErrorText message={!failingRequest ? actionError : undefined} />

      <FailPrintDialog
        open={Boolean(failingRequest)}
        pending={action.isPending}
        error={failingRequest ? actionError : undefined}
        onClose={() => setFailingRequest(null)}
        onSubmit={(reason) => failingRequest && action.mutate({ request: failingRequest, name: "fail", reason })}
      />
    </Panel>
  );
}
