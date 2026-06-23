import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Skeleton } from "../../../components/ui";
import { Panel, type Makerspace, useStaffGet } from "./shared";
import {
  ErrorText,
  type FilamentSpool,
  type PrintPrinter,
  type PrintRequest,
  printingRequest,
} from "./PrintingPanelParts";
import { PrintRows } from "./PrintingPanelCards";
import { AcceptPrintDialog, FailPrintDialog } from "./PrintingPanelDialogs";
import { invalidatePrintingViews } from "../queryInvalidation";

// The print queue lives here so it can be shown inside the unified "Requests" tab
// alongside hardware requests. It now covers the FULL lifecycle to match hardware:
// pending (accept/reject) -> accepted (start) -> printing (complete/fail) ->
// completed (collect), failed (reprint), plus a read-only history (collected/rejected). Printer & spool management stays in
// PrintingPanel; both query the same TanStack keys so the cache is shared.
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
  const reqUrl = (status: string) =>
    `/printing/manage/requests/?makerspace=${makerspace.id}&status=${status}`;
  const pending = useStaffGet<{ results: PrintRequest[] }>(["print-requests", makerspace.id, "pending"], reqUrl("pending"));
  const accepted = useStaffGet<{ results: PrintRequest[] }>(["print-requests", makerspace.id, "accepted"], reqUrl("accepted"));
  const printing = useStaffGet<{ results: PrintRequest[] }>(["print-requests", makerspace.id, "printing"], reqUrl("printing"));
  const completed = useStaffGet<{ results: PrintRequest[] }>(["print-requests", makerspace.id, "completed"], reqUrl("completed"));

  const [showHistory, setShowHistory] = useState(false);
  // History queries only fire when expanded (terminal lists can be large) — useStaffGet's
  // third arg is the TanStack `enabled` flag, so the network call is deferred until needed.
  const collected = useStaffGet<{ results: PrintRequest[] }>(["print-requests", makerspace.id, "collected"], reqUrl("collected"), showHistory);
  const rejected = useStaffGet<{ results: PrintRequest[] }>(["print-requests", makerspace.id, "rejected"], reqUrl("rejected"), showHistory);
  const failed = useStaffGet<{ results: PrintRequest[] }>(["print-requests", makerspace.id, "failed"], reqUrl("failed"));

  const [selectedPrinter, setSelectedPrinter] = useState("");
  const [selectedSpool, setSelectedSpool] = useState("");
  const [estimatedMinutes, setEstimatedMinutes] = useState("60");
  const [estimatedGrams, setEstimatedGrams] = useState("100");
  const [acceptingRequest, setAcceptingRequest] = useState<PrintRequest | null>(null);
  const [failingRequest, setFailingRequest] = useState<PrintRequest | null>(null);
  const [rejectingRequest, setRejectingRequest] = useState<PrintRequest | null>(null);

  const action = useMutation({
    mutationFn: ({ request, name, reason, percentComplete, price }: { request: PrintRequest; name: "start" | "complete" | "fail" | "accept" | "reject" | "reprint" | "collect"; reason?: string; percentComplete?: number; price?: string }) => {
      const body =
        name === "start"
          ? {
              printer_id: selectedPrinter ? Number(selectedPrinter) : undefined,
              filament_spool_id: selectedSpool ? Number(selectedSpool) : undefined,
              estimated_minutes: Number(estimatedMinutes),
              estimated_filament_grams: estimatedGrams,
            }
          : name === "fail"
            ? { reason, percent_complete: percentComplete ?? 0 }
            : name === "reject"
              ? { reason }
              : name === "accept"
                ? { price: price ?? "0" }
                : {};
      return printingRequest(`/printing/manage/requests/${request.id}/${name}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      setAcceptingRequest(null);
      setFailingRequest(null);
      setRejectingRequest(null);
      invalidatePrintingViews(queryClient, makerspace.id);
    },
  });

  const printerRows = printers.data?.results ?? [];
  const spoolRows = spools.data?.results ?? [];
  const actionError = action.error instanceof Error ? action.error.message : undefined;
  // Backend _assign_print_job blocks start unless the printer is is_active AND status active,
  // so only offer those as start targets (otherwise the user hits a 409 after clicking Start).
  const startablePrinters = printerRows.filter((printer) => printer.is_active && printer.status === "active");

  return (
    <Panel title="Print requests">
      <div className="mb-3">
        {pending.isLoading ? (
          <PrintRowsSkeleton title="Pending review" />
        ) : (
          <PrintRows title="Pending review" rows={pending.data?.results ?? []} action={(row) => (
            <>
              <button disabled={action.isPending} onClick={() => setAcceptingRequest(row)}>Accept</button>
              <button disabled={action.isPending} onClick={() => setRejectingRequest(row)}>Reject</button>
            </>
          )} />
        )}
      </div>

      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Start-on-printer settings</p>
      <p className="mb-2 text-xs text-muted">Used by “Start on printer” below — not by Accept.</p>
      {startablePrinters.length === 0 ? (
        <p className="mb-2 text-xs text-warn-ink">No active printer — add or activate one on the 3D Printing tab.</p>
      ) : null}
      <div className="mb-3 grid gap-2 md:grid-cols-4">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">Printer</span>
          <select className="desk-input w-full" value={selectedPrinter} onChange={(event) => setSelectedPrinter(event.target.value)}>
            <option value="">Printer</option>
            {startablePrinters.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">Spool</span>
          <select className="desk-input w-full" value={selectedSpool} onChange={(event) => setSelectedSpool(event.target.value)}>
            <option value="">Spool</option>
            {spoolRows
              .filter((spool) => spool.is_active && (!selectedPrinter || spool.printer === Number(selectedPrinter) || spool.printer === null))
              .map((spool) => <option key={spool.id} value={spool.id}>{[spool.material, spool.color].filter(Boolean).join(" ")} ({spool.remaining_weight_grams}g)</option>)}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">Print time (min)</span>
          <input className="desk-input w-full" type="number" min="0" value={estimatedMinutes} onChange={(event) => setEstimatedMinutes(event.target.value)} />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">Filament (g)</span>
          <input className="desk-input w-full" type="number" min="0" value={estimatedGrams} onChange={(event) => setEstimatedGrams(event.target.value)} />
        </label>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {accepted.isLoading ? (
          <PrintRowsSkeleton title="Accepted" />
        ) : (
          <PrintRows title="Accepted" rows={accepted.data?.results ?? []} action={(row) => (
            <button disabled={!selectedPrinter || action.isPending} onClick={() => action.mutate({ request: row, name: "start" })}>
              {action.isPending ? "Starting..." : "Start on printer"}
            </button>
          )} />
        )}
        {printing.isLoading ? (
          <PrintRowsSkeleton title="Printing" />
        ) : (
          <PrintRows title="Printing" rows={printing.data?.results ?? []} action={(row) => (
            <>
              <button disabled={action.isPending} onClick={() => action.mutate({ request: row, name: "complete" })}>Complete</button>
              <button disabled={action.isPending} onClick={() => setFailingRequest(row)}>Fail</button>
            </>
          )} />
        )}
      </div>

      <div className="mt-3">
        {completed.isLoading ? (
          <PrintRowsSkeleton title="Ready for collection" />
        ) : (
          <PrintRows title="Ready for collection" rows={completed.data?.results ?? []} action={(row) => (
            <button disabled={action.isPending} onClick={() => action.mutate({ request: row, name: "collect" })}>
              {action.isPending ? "..." : "Mark collected"}
            </button>
          )} />
        )}
      </div>

      <div className="mt-3">
        {failed.isLoading ? (
          <PrintRowsSkeleton title="Failed" />
        ) : (
          <PrintRows title="Failed" rows={failed.data?.results ?? []} action={(row) => (
            <button disabled={action.isPending} onClick={() => action.mutate({ request: row, name: "reprint" })}>
              {action.isPending ? "..." : "Reprint"}
            </button>
          )} />
        )}
      </div>

      <div className="mt-4">
        <button type="button" className="text-sm text-accent-ink" onClick={() => setShowHistory((value) => !value)}>
          {showHistory ? "Hide history" : "Show history (collected / rejected)"}
        </button>
        {showHistory ? (
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <PrintRows title="Collected" rows={collected.data?.results ?? []} action={() => null} />
            <PrintRows title="Rejected" rows={rejected.data?.results ?? []} action={() => null} />
          </div>
        ) : null}
      </div>

      <ErrorText message={pending.error instanceof Error ? pending.error.message : undefined} />
      <ErrorText message={accepted.error instanceof Error ? accepted.error.message : undefined} />
      <ErrorText message={printing.error instanceof Error ? printing.error.message : undefined} />
      <ErrorText message={completed.error instanceof Error ? completed.error.message : undefined} />
      <ErrorText message={collected.error instanceof Error ? collected.error.message : undefined} />
      <ErrorText message={rejected.error instanceof Error ? rejected.error.message : undefined} />
      <ErrorText message={failed.error instanceof Error ? failed.error.message : undefined} />
      <ErrorText message={!acceptingRequest && !failingRequest && !rejectingRequest ? actionError : undefined} />

      <AcceptPrintDialog
        open={Boolean(acceptingRequest)}
        pending={action.isPending}
        error={acceptingRequest ? actionError : undefined}
        onClose={() => setAcceptingRequest(null)}
        onSubmit={(price) => acceptingRequest && action.mutate({ request: acceptingRequest, name: "accept", price })}
      />
      <FailPrintDialog
        open={Boolean(failingRequest)}
        pending={action.isPending}
        error={failingRequest ? actionError : undefined}
        showPercent
        onClose={() => setFailingRequest(null)}
        onSubmit={(reason, percentComplete) => failingRequest && action.mutate({ request: failingRequest, name: "fail", reason, percentComplete })}
      />
      <FailPrintDialog
        open={Boolean(rejectingRequest)}
        pending={action.isPending}
        error={rejectingRequest ? actionError : undefined}
        title="Reject print request"
        submitLabel="Reject request"
        placeholder="Reason for rejection (shown to the requester)"
        onClose={() => setRejectingRequest(null)}
        onSubmit={(reason) => rejectingRequest && action.mutate({ request: rejectingRequest, name: "reject", reason })}
      />
    </Panel>
  );
}

function PrintRowsSkeleton({ title, rows = 3 }: { title: string; rows?: number }) {
  return (
    <div className="rounded-md border border-line" aria-hidden="true">
      <h3 className="border-b border-line bg-surface px-3 py-2 text-sm font-semibold text-muted">{title}</h3>
      <div className="grid gap-0">
        {Array.from({ length: rows }, (_, index) => (
          <article key={index} className="border-b border-line p-3 last:border-b-0">
            <div className="flex flex-wrap items-center gap-2">
              <Skeleton className="h-4 w-44" />
              <Skeleton className="h-5 w-20" />
              <Skeleton className="ml-0 h-7 w-28 sm:ml-auto" />
            </div>
            <Skeleton className="mt-3 h-3 w-full" />
            <Skeleton className="mt-2 h-3 w-2/3" />
          </article>
        ))}
      </div>
    </div>
  );
}
