import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { Panel, type Makerspace, useStaffGet } from "./shared";
import {
  ErrorText,
  type FilamentSpool,
  PrintRows,
  type PrintPrinter,
  type PrintRequest,
  PrinterCard,
  type PrinterPayload,
  printingRequest,
  type SpoolPayload,
  SpoolRow,
} from "./PrintingPanelParts";
import { FailPrintDialog, PrinterEditDialog, SpoolEditDialog } from "./PrintingPanelDialogs";

type DeactivateTarget =
  | { kind: "printer"; id: number; label: string }
  | { kind: "spool"; id: number; label: string };

export function PrintingPanel({ makerspace }: { makerspace: Makerspace }) {
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

  const [printerName, setPrinterName] = useState("");
  const [printerModel, setPrinterModel] = useState("");
  const [spoolPrinter, setSpoolPrinter] = useState("");
  const [spoolMaterial, setSpoolMaterial] = useState("PLA");
  const [spoolColor, setSpoolColor] = useState("");
  const [spoolBrand, setSpoolBrand] = useState("");
  const [spoolWeight, setSpoolWeight] = useState("1000");
  const [selectedPrinter, setSelectedPrinter] = useState("");
  const [selectedSpool, setSelectedSpool] = useState("");
  const [estimatedMinutes, setEstimatedMinutes] = useState("60");
  const [estimatedGrams, setEstimatedGrams] = useState("100");
  const [editingPrinter, setEditingPrinter] = useState<PrintPrinter | null>(null);
  const [editingSpool, setEditingSpool] = useState<FilamentSpool | null>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<DeactivateTarget | null>(null);
  const [failingRequest, setFailingRequest] = useState<PrintRequest | null>(null);

  const invalidatePrinting = () => {
    queryClient.invalidateQueries({ queryKey: ["print-printers", makerspace.id] });
    queryClient.invalidateQueries({ queryKey: ["print-spools", makerspace.id] });
    queryClient.invalidateQueries({ queryKey: ["print-requests", makerspace.id] });
  };

  const createPrinter = useMutation({
    mutationFn: () =>
      printingRequest("/printing/manage/printers/", {
        method: "POST",
        body: JSON.stringify({
          makerspace: makerspace.id,
          name: printerName.trim(),
          model: printerModel.trim(),
          status: "active",
        }),
      }),
    onSuccess: () => {
      setPrinterName("");
      setPrinterModel("");
      invalidatePrinting();
    },
  });

  const createSpool = useMutation({
    mutationFn: () =>
      printingRequest("/printing/manage/spools/", {
        method: "POST",
        body: JSON.stringify({
          makerspace: makerspace.id,
          printer: spoolPrinter ? Number(spoolPrinter) : null,
          material: spoolMaterial.trim(),
          color: spoolColor.trim(),
          brand: spoolBrand.trim(),
          initial_weight_grams: spoolWeight,
          remaining_weight_grams: spoolWeight,
          is_active: true,
        }),
      }),
    onSuccess: () => {
      setSpoolColor("");
      setSpoolBrand("");
      invalidatePrinting();
    },
  });

  const updatePrinter = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: PrinterPayload }) =>
      printingRequest(`/printing/manage/printers/${id}/`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setEditingPrinter(null);
      invalidatePrinting();
    },
  });

  const updateSpool = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: SpoolPayload }) =>
      printingRequest(`/printing/manage/spools/${id}/`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setEditingSpool(null);
      invalidatePrinting();
    },
  });

  const deactivate = useMutation({
    mutationFn: (target: DeactivateTarget) =>
      printingRequest(`/printing/manage/${target.kind === "printer" ? "printers" : "spools"}/${target.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: false }),
      }),
    onSuccess: () => {
      setDeactivateTarget(null);
      invalidatePrinting();
    },
  });

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
      invalidatePrinting();
    },
  });

  const printerRows = printers.data?.results ?? [];
  const spoolRows = spools.data?.results ?? [];
  const anyQueueLoading = accepted.isLoading || printing.isLoading;
  const actionError = action.error instanceof Error ? action.error.message : undefined;

  return (
    <div className="grid gap-4">
      <Panel title="3D printers">
        {printers.isLoading ? <p className="text-sm text-muted">Loading printers...</p> : null}
        <div className="grid gap-3 md:grid-cols-3">
          {printerRows.map((printer) => (
            <PrinterCard
              key={printer.id}
              printer={printer}
              onEdit={() => setEditingPrinter(printer)}
              onDeactivate={() => setDeactivateTarget({ kind: "printer", id: printer.id, label: printer.name })}
            />
          ))}
        </div>
        {!printers.isLoading && !printerRows.length ? <p className="text-sm text-muted">No printers yet.</p> : null}
        <div className="mt-4 grid gap-2 md:grid-cols-[1fr_1fr_auto]">
          <input className="desk-input" placeholder="Printer name" value={printerName} onChange={(event) => setPrinterName(event.target.value)} />
          <input className="desk-input" placeholder="Model" value={printerModel} onChange={(event) => setPrinterModel(event.target.value)} />
          <button disabled={!printerName.trim() || createPrinter.isPending} onClick={() => createPrinter.mutate()}>
            {createPrinter.isPending ? "Adding..." : "Add printer"}
          </button>
        </div>
        <ErrorText message={printers.error instanceof Error ? printers.error.message : undefined} />
        <ErrorText message={createPrinter.error instanceof Error ? createPrinter.error.message : undefined} />
      </Panel>

      <Panel title="Filament spools">
        {spools.isLoading ? <p className="text-sm text-muted">Loading spools...</p> : null}
        <div className="grid gap-2 md:grid-cols-[1fr_1fr_1fr_1fr_auto]">
          <select className="desk-input" value={spoolPrinter} onChange={(event) => setSpoolPrinter(event.target.value)}>
            <option value="">Unassigned printer</option>
            {printerRows.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}
          </select>
          <input className="desk-input" placeholder="Material" value={spoolMaterial} onChange={(event) => setSpoolMaterial(event.target.value)} />
          <input className="desk-input" placeholder="Color" value={spoolColor} onChange={(event) => setSpoolColor(event.target.value)} />
          <input className="desk-input" placeholder="Brand" value={spoolBrand} onChange={(event) => setSpoolBrand(event.target.value)} />
          <input className="desk-input" placeholder="Weight g (1000 = 1kg)" type="number" min="0" value={spoolWeight} onChange={(event) => setSpoolWeight(event.target.value)} />
          <button disabled={!spoolMaterial.trim() || !spoolWeight || createSpool.isPending} onClick={() => createSpool.mutate()}>
            {createSpool.isPending ? "Adding..." : "Add spool"}
          </button>
        </div>
        <div className="mt-3 grid gap-2">
          {spoolRows.map((spool) => (
            <SpoolRow
              key={spool.id}
              spool={spool}
              onEdit={() => setEditingSpool(spool)}
              onDeactivate={() => setDeactivateTarget({ kind: "spool", id: spool.id, label: `${spool.material} ${spool.color}`.trim() })}
            />
          ))}
        </div>
        {!spools.isLoading && !spoolRows.length ? <p className="mt-3 text-sm text-muted">No filament spools yet.</p> : null}
        <ErrorText message={spools.error instanceof Error ? spools.error.message : undefined} />
        <ErrorText message={createSpool.error instanceof Error ? createSpool.error.message : undefined} />
      </Panel>

      <Panel title="Print queue">
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
              .map((spool) => <option key={spool.id} value={spool.id}>{spool.material} {spool.color} ({spool.remaining_weight_grams}g)</option>)}
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
      </Panel>

      <PrinterEditDialog
        printer={editingPrinter}
        pending={updatePrinter.isPending}
        error={updatePrinter.error instanceof Error ? updatePrinter.error.message : undefined}
        onClose={() => setEditingPrinter(null)}
        onSubmit={(payload) => editingPrinter && updatePrinter.mutate({ id: editingPrinter.id, payload })}
      />
      <SpoolEditDialog
        spool={editingSpool}
        printers={printerRows}
        pending={updateSpool.isPending}
        error={updateSpool.error instanceof Error ? updateSpool.error.message : undefined}
        onClose={() => setEditingSpool(null)}
        onSubmit={(payload) => editingSpool && updateSpool.mutate({ id: editingSpool.id, payload })}
      />
      <FailPrintDialog
        open={Boolean(failingRequest)}
        pending={action.isPending}
        error={failingRequest ? actionError : undefined}
        onClose={() => setFailingRequest(null)}
        onSubmit={(reason) => failingRequest && action.mutate({ request: failingRequest, name: "fail", reason })}
      />
      <ConfirmDialog
        open={Boolean(deactivateTarget)}
        title="Deactivate item"
        message={deactivateTarget ? `Deactivate ${deactivateTarget.label}? It will stay in history but no longer be available for new print work.` : ""}
        confirmLabel="Deactivate"
        tone="danger"
        pending={deactivate.isPending}
        onCancel={() => setDeactivateTarget(null)}
        onConfirm={() => deactivateTarget && deactivate.mutate(deactivateTarget)}
      />
      <ErrorText message={deactivate.error instanceof Error ? deactivate.error.message : undefined} />
    </div>
  );
}
