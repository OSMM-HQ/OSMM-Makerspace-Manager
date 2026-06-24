import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { uploadPublicImage } from "../ImageUploader";
import { Panel, type Makerspace, useStaffGet } from "./shared";
import { ManualPrintLogSection } from "./ManualPrintLogSection";
import {
  ErrorText,
  type FilamentSpool,
  type PrintPrinter,
  type PrinterPayload,
  printingRequest,
  SpoolColorInput,
  type SpoolPayload,
} from "./PrintingPanelParts";
import { PrinterCard, SpoolRow } from "./PrintingPanelCards";
import { PrinterEditDialog, SpoolEditDialog } from "./PrintingPanelDialogs";
import { invalidatePrintingViews } from "../queryInvalidation";

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

  const [printerName, setPrinterName] = useState("");
  const [printerModel, setPrinterModel] = useState("");
  const [printerPhoto, setPrinterPhoto] = useState<File | null>(null);
  const [printerPhotoError, setPrinterPhotoError] = useState("");
  const [spoolPrinter, setSpoolPrinter] = useState("");
  const [spoolMaterial, setSpoolMaterial] = useState("PLA");
  const [spoolColor, setSpoolColor] = useState("");
  const [spoolBrand, setSpoolBrand] = useState("");
  const [spoolWeight, setSpoolWeight] = useState("1000");
  const [editingPrinter, setEditingPrinter] = useState<PrintPrinter | null>(null);
  const [editingSpool, setEditingSpool] = useState<FilamentSpool | null>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<DeactivateTarget | null>(null);
  const [deletePrinterTarget, setDeletePrinterTarget] = useState<{ id: number; label: string } | null>(null);
  const [deleteSpoolTarget, setDeleteSpoolTarget] = useState<{ id: number; label: string } | null>(null);

  const invalidatePrinting = () => invalidatePrintingViews(queryClient, makerspace.id);

  const createPrinter = useMutation({
    mutationFn: async () => {
      setPrinterPhotoError("");
      const created = await printingRequest<PrintPrinter>("/printing/manage/printers/", {
        method: "POST",
        body: JSON.stringify({
          makerspace: makerspace.id,
          name: printerName.trim(),
          model: printerModel.trim(),
          status: "active",
        }),
      });
      let photoError = "";
      if (printerPhoto) {
        try {
          await uploadPublicImage(`/admin/printing/printers/${created.id}/image`, printerPhoto);
        } catch (err) {
          photoError = err instanceof Error ? `Printer was added, but photo upload failed. ${err.message}` : "Printer was added, but photo upload failed.";
        }
      }
      return { created, photoError };
    },
    onSuccess: ({ created, photoError }) => {
      setPrinterName("");
      setPrinterModel("");
      setPrinterPhoto(null);
      setPrinterPhotoError(photoError);
      invalidatePrinting();
      if (!printerPhoto || photoError) setEditingPrinter(created);
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

  // Re-activating a spool puts it back on the public print-request form (the public
  // /spools endpoint only lists is_active spools), which is the fix for "the spool I
  // added isn't showing publicly" - it was inactive.
  const activateSpool = useMutation({
    mutationFn: (id: number) =>
      printingRequest(`/printing/manage/spools/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: true }),
      }),
    onSuccess: () => invalidatePrinting(),
  });

  const deleteSpool = useMutation({
    mutationFn: (id: number) => printingRequest(`/printing/manage/spools/${id}/`, { method: "DELETE" }),
    onSuccess: () => { setDeleteSpoolTarget(null); invalidatePrinting(); },
  });

  const deletePrinter = useMutation({
    mutationFn: (id: number) => printingRequest(`/printing/manage/printers/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      setDeletePrinterTarget(null);
      // Deleting a printer SET_NULLs its spools' + requests' printer FK, so refresh
      // those panels too (not just the printers list) to avoid showing a stale printer.
      invalidatePrinting();
    },
  });

  const printerRows = printers.data?.results ?? [];
  const spoolRows = spools.data?.results ?? [];

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
              onDelete={() => setDeletePrinterTarget({ id: printer.id, label: printer.name })}
            />
          ))}
        </div>
        {!printers.isLoading && !printerRows.length ? <p className="text-sm text-muted">No printers yet.</p> : null}
        <div className="mt-4 grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(180px,0.8fr)_auto]">
          <input className="desk-input min-w-0" placeholder="Printer name" value={printerName} onChange={(event) => setPrinterName(event.target.value)} />
          <input className="desk-input min-w-0" placeholder="Model" value={printerModel} onChange={(event) => setPrinterModel(event.target.value)} />
          <label className="desk-input flex min-w-0 cursor-pointer items-center overflow-hidden px-3 py-2 text-sm text-muted">
            <span className="truncate">{printerPhoto ? printerPhoto.name : "Printer photo"}</span>
            <input
              className="sr-only"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={createPrinter.isPending}
              onChange={(event) => setPrinterPhoto(event.target.files?.[0] ?? null)}
            />
          </label>
          <button disabled={!printerName.trim() || createPrinter.isPending} onClick={() => createPrinter.mutate()}>
            {createPrinter.isPending ? "Adding..." : "Add printer"}
          </button>
        </div>
        <p className="mt-1 text-xs text-muted">Choose a photo now, or use Edit later to add or replace it.</p>
        <ErrorText message={printers.error instanceof Error ? printers.error.message : undefined} />
        <ErrorText message={createPrinter.error instanceof Error ? createPrinter.error.message : undefined} />
        <ErrorText message={printerPhotoError} />
        <ErrorText message={deletePrinter.error instanceof Error ? deletePrinter.error.message : undefined} />
      </Panel>

      <Panel title="Filament spools">
        {spools.isLoading ? <p className="text-sm text-muted">Loading spools...</p> : null}
        <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
          <select className="desk-input min-w-0" value={spoolPrinter} onChange={(event) => setSpoolPrinter(event.target.value)}>
            <option value="">Unassigned printer</option>
            {printerRows.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}
          </select>
          <input className="desk-input min-w-0" placeholder="Material" value={spoolMaterial} onChange={(event) => setSpoolMaterial(event.target.value)} />
          <SpoolColorInput className="desk-input min-w-0" value={spoolColor} onChange={setSpoolColor} />
          <input className="desk-input min-w-0" placeholder="Brand" value={spoolBrand} onChange={(event) => setSpoolBrand(event.target.value)} />
          <input className="desk-input min-w-0" placeholder="Weight g (1000 = 1kg)" type="number" min="0" value={spoolWeight} onChange={(event) => setSpoolWeight(event.target.value)} />
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
              onActivate={() => activateSpool.mutate(spool.id)}
              onDeactivate={() => setDeactivateTarget({ kind: "spool", id: spool.id, label: `${spool.material} ${spool.color}`.trim() })}
              onDelete={() => setDeleteSpoolTarget({ id: spool.id, label: `${spool.material} ${spool.color}`.trim() })}
            />
          ))}
        </div>
        {!spools.isLoading && !spoolRows.length ? <p className="mt-3 text-sm text-muted">No filament spools yet.</p> : null}
        <ErrorText message={spools.error instanceof Error ? spools.error.message : undefined} />
        <ErrorText message={createSpool.error instanceof Error ? createSpool.error.message : undefined} />
        <ErrorText message={deleteSpool.error instanceof Error ? deleteSpool.error.message : undefined} />
        <ErrorText message={activateSpool.error instanceof Error ? activateSpool.error.message : undefined} />
      </Panel>

      <ManualPrintLogSection
        makerspace={makerspace}
        printers={printerRows}
        spools={spoolRows}
      />

      <PrinterEditDialog
        printer={editingPrinter}
        pending={updatePrinter.isPending}
        error={updatePrinter.error instanceof Error ? updatePrinter.error.message : undefined}
        onClose={() => setEditingPrinter(null)}
        onSubmit={(payload) => editingPrinter && updatePrinter.mutate({ id: editingPrinter.id, payload })}
        onImageChanged={invalidatePrinting}
      />
      <SpoolEditDialog
        spool={editingSpool}
        printers={printerRows}
        pending={updateSpool.isPending}
        error={updateSpool.error instanceof Error ? updateSpool.error.message : undefined}
        onClose={() => setEditingSpool(null)}
        onSubmit={(payload) => editingSpool && updateSpool.mutate({ id: editingSpool.id, payload })}
      />
      <ConfirmDialog open={Boolean(deactivateTarget)} title="Deactivate item" message={deactivateTarget ? `Deactivate ${deactivateTarget.label}? It will stay in history but no longer be available for new print work.` : ""} confirmLabel="Deactivate" tone="danger" pending={deactivate.isPending} onCancel={() => setDeactivateTarget(null)} onConfirm={() => deactivateTarget && deactivate.mutate(deactivateTarget)} />
      <ConfirmDialog open={Boolean(deletePrinterTarget)} title="Delete printer" message={deletePrinterTarget ? `Permanently delete ${deletePrinterTarget.label}? Past print requests and spools keep their history but will no longer show this printer. This cannot be undone.` : ""} confirmLabel="Delete" tone="danger" pending={deletePrinter.isPending} onCancel={() => setDeletePrinterTarget(null)} onConfirm={() => deletePrinterTarget && deletePrinter.mutate(deletePrinterTarget.id)} />
      <ConfirmDialog open={Boolean(deleteSpoolTarget)} title="Delete spool" message={deleteSpoolTarget ? `Permanently delete ${deleteSpoolTarget.label}? This cannot be undone. Spools linked to print requests cannot be deleted - deactivate them instead.` : ""} confirmLabel="Delete" tone="danger" pending={deleteSpool.isPending} onCancel={() => setDeleteSpoolTarget(null)} onConfirm={() => deleteSpoolTarget && deleteSpool.mutate(deleteSpoolTarget.id)} />
      <ErrorText message={deactivate.error instanceof Error ? deactivate.error.message : undefined} />
    </div>
  );
}
