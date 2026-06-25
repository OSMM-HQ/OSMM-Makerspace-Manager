import { useEffect, useState } from "react";

import { Modal } from "../../../components/ui/Modal";
import { ImageUploader } from "../ImageUploader";
import {
  ErrorText,
  type FilamentSpool,
  type PrintPrinter,
  type PrinterPayload,
  type PrintRequest,
  SpoolColorInput,
  type SpoolPayload,
} from "./PrintingPanelParts";

export function PrinterEditDialog({
  printer,
  pending,
  error,
  onImageChanged,
  onClose,
  onSubmit,
}: {
  printer: PrintPrinter | null;
  pending: boolean;
  error?: string;
  onImageChanged: () => void;
  onClose: () => void;
  onSubmit: (payload: PrinterPayload) => void;
}) {
  const [form, setForm] = useState<PrinterPayload>({ name: "", model: "", status: "active", is_active: true });
  useEffect(() => {
    if (printer) setForm({ name: printer.name, model: printer.model, status: printer.status, is_active: printer.is_active });
  }, [printer]);
  return (
    <Modal open={Boolean(printer)} onClose={onClose} title="Edit printer" footer={<DialogActions pending={pending} disabled={!form.name.trim()} submitLabel="Save printer" onCancel={onClose} onSubmit={() => onSubmit(form)} />}>
      <PrinterFields form={form} onChange={setForm} />
      {printer ? (
        <div className="border-t border-line pt-3">
          <ImageUploader
            endpoint={`/admin/printing/printers/${printer.id}/image`}
            currentUrl={printer.image_url}
            label="Printer photo"
            onChanged={onImageChanged}
          />
        </div>
      ) : null}
      <ErrorText message={error} />
    </Modal>
  );
}

export function SpoolEditDialog({ spool, printers, pending, error, onClose, onSubmit }: {
  spool: FilamentSpool | null;
  printers: PrintPrinter[];
  pending: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (payload: SpoolPayload) => void;
}) {
  const [form, setForm] = useState<SpoolPayload>({ printer: null, material: "", color: "", brand: "", initial_weight_grams: "0", remaining_weight_grams: "0", is_active: true });
  useEffect(() => {
    if (spool) setForm({ printer: spool.printer, material: spool.material, color: spool.color, brand: spool.brand, initial_weight_grams: spool.initial_weight_grams, remaining_weight_grams: spool.remaining_weight_grams, is_active: spool.is_active });
  }, [spool]);
  return (
    <Modal open={Boolean(spool)} onClose={onClose} title="Edit spool" footer={<DialogActions pending={pending} disabled={!form.material.trim() || !form.initial_weight_grams || !form.remaining_weight_grams} submitLabel="Save spool" onCancel={onClose} onSubmit={() => onSubmit(form)} />}>
      <SpoolFields form={form} printers={printers} onChange={setForm} />
      <ErrorText message={error} />
    </Modal>
  );
}

// A free-text "reason" dialog shared by Fail print (default copy) and Reject request
// (pass title/submitLabel/placeholder). Both backends require a non-blank reason
// (RejectFailSerializer), so the submit stays disabled until text is entered. When
// showPercent is set (Fail print), a "% completed at failure" field is shown so the
// spool can be charged for the wasted filament (grams x percent / 100).
export function FailPrintDialog({ open, pending, error, onClose, onSubmit, title = "Fail print", submitLabel = "Submit failure", placeholder = "Failure reason", showPercent = false }: {
  open: boolean;
  pending: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (reason: string, percentComplete: number) => void;
  title?: string;
  submitLabel?: string;
  placeholder?: string;
  showPercent?: boolean;
}) {
  const [reason, setReason] = useState("");
  const [percent, setPercent] = useState("0");
  useEffect(() => { if (open) { setReason(""); setPercent("0"); } }, [open]);
  // Clamp to 0-100 so a stray value can't over-charge the spool; the backend re-validates.
  const percentValue = Math.min(100, Math.max(0, Math.round(Number(percent) || 0)));
  return (
    <Modal open={open} onClose={onClose} title={title} footer={<DialogActions pending={pending} disabled={!reason.trim()} submitLabel={submitLabel} onCancel={onClose} onSubmit={() => onSubmit(reason.trim(), percentValue)} />}>
      <textarea className="desk-input min-h-28 w-full" placeholder={placeholder} value={reason} onChange={(event) => setReason(event.target.value)} />
      {showPercent ? (
        <label className="mt-3 block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">% completed at failure</span>
          <input className="desk-input w-full" type="number" min="0" max="100" value={percent} onChange={(event) => setPercent(event.target.value)} />
          <span className="mt-1 block text-xs text-muted">Charges the spool for filament used so far. Reprint, when completed, charges the full amount.</span>
        </label>
      ) : null}
      <ErrorText message={error} />
    </Modal>
  );
}

export function CompletePrintDialog({ request, pending, error, onClose, onSubmit }: {
  request: PrintRequest | null;
  pending: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (actualGrams?: string) => void;
}) {
  const [actualGrams, setActualGrams] = useState("");
  useEffect(() => {
    if (request) setActualGrams(request.estimated_filament_grams || "");
  }, [request]);
  const trimmed = actualGrams.trim();
  const numericValue = Number(trimmed);
  const disabled = Boolean(trimmed) && (!Number.isFinite(numericValue) || numericValue < 0);
  return (
    <Modal open={Boolean(request)} onClose={onClose} title="Complete print" footer={<DialogActions pending={pending} disabled={disabled} submitLabel="Complete print" onCancel={onClose} onSubmit={() => onSubmit(trimmed || undefined)} />}>
      <label className="block">
        <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">Actual filament used (g)</span>
        <input className="desk-input w-full" type="number" min="0" step="0.01" value={actualGrams} onChange={(event) => setActualGrams(event.target.value)} />
      </label>
      <ErrorText message={error} />
    </Modal>
  );
}

export function AcceptPrintDialog({ open, pending, error, onClose, onSubmit }: {
  open: boolean;
  pending: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (price: string) => void;
}) {
  const [price, setPrice] = useState("0");
  useEffect(() => { if (open) setPrice("0"); }, [open]);
  const priceValue = Number(price);
  const disabled = !price.trim() || !Number.isFinite(priceValue) || priceValue < 0;
  return (
    <Modal open={open} onClose={onClose} title="Accept print request" footer={<DialogActions pending={pending} disabled={disabled} submitLabel="Accept request" onCancel={onClose} onSubmit={() => onSubmit(price.trim() || "0")} />}>
      <label className="block">
        <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">Price (cash) &mdash; 0 = free</span>
        <input className="desk-input w-full" type="number" min="0" step="0.01" value={price} onChange={(event) => setPrice(event.target.value)} />
      </label>
      <ErrorText message={error} />
    </Modal>
  );
}

function PrinterFields({ form, onChange }: { form: PrinterPayload; onChange: (form: PrinterPayload) => void }) {
  return (
    <div className="grid gap-3">
      <input className="desk-input" placeholder="Printer name" value={form.name} onChange={(event) => onChange({ ...form, name: event.target.value })} />
      <input className="desk-input" placeholder="Model" value={form.model} onChange={(event) => onChange({ ...form, model: event.target.value })} />
      <select className="desk-input" value={form.status} onChange={(event) => onChange({ ...form, status: event.target.value })}>
        <option value="active">Active</option>
        <option value="maintenance">Maintenance</option>
        <option value="offline">Offline</option>
      </select>
      <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={form.is_active} onChange={(event) => onChange({ ...form, is_active: event.target.checked })} /> Active</label>
    </div>
  );
}

function SpoolFields({ form, printers, onChange }: { form: SpoolPayload; printers: PrintPrinter[]; onChange: (form: SpoolPayload) => void }) {
  return (
    <div className="grid gap-3">
      <select className="desk-input" value={form.printer ?? ""} onChange={(event) => onChange({ ...form, printer: event.target.value ? Number(event.target.value) : null })}>
        <option value="">Unassigned printer</option>
        {printers.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}
      </select>
      <input className="desk-input" placeholder="Material" value={form.material} onChange={(event) => onChange({ ...form, material: event.target.value })} />
      <SpoolColorInput value={form.color} onChange={(value) => onChange({ ...form, color: value })} />
      <input className="desk-input" placeholder="Brand" value={form.brand} onChange={(event) => onChange({ ...form, brand: event.target.value })} />
      <input className="desk-input" type="number" min="0" placeholder="Initial weight g" value={form.initial_weight_grams} onChange={(event) => onChange({ ...form, initial_weight_grams: event.target.value })} />
      <input className="desk-input" type="number" min="0" placeholder="Remaining weight g" value={form.remaining_weight_grams} onChange={(event) => onChange({ ...form, remaining_weight_grams: event.target.value })} />
      <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={form.is_active} onChange={(event) => onChange({ ...form, is_active: event.target.checked })} /> Active</label>
    </div>
  );
}

function DialogActions({ pending, disabled, submitLabel, onCancel, onSubmit }: {
  pending: boolean;
  disabled: boolean;
  submitLabel: string;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="desk-actions flex flex-wrap justify-end gap-2">
      <button type="button" disabled={pending} onClick={onCancel}>Cancel</button>
      <button type="button" disabled={pending || disabled} onClick={onSubmit}>{pending ? "Saving..." : submitLabel}</button>
    </div>
  );
}
