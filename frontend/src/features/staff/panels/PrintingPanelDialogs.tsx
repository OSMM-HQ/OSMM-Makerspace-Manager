import { useEffect, useState } from "react";

import { Modal } from "../../../components/ui/Modal";
import {
  ErrorText,
  type FilamentSpool,
  type PrintPrinter,
  type PrinterPayload,
  SpoolColorInput,
  type SpoolPayload,
} from "./PrintingPanelParts";

export function PrinterEditDialog({
  printer,
  pending,
  error,
  onClose,
  onSubmit,
}: {
  printer: PrintPrinter | null;
  pending: boolean;
  error?: string;
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

export function FailPrintDialog({ open, pending, error, onClose, onSubmit }: {
  open: boolean;
  pending: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  useEffect(() => { if (open) setReason(""); }, [open]);
  return (
    <Modal open={open} onClose={onClose} title="Fail print" footer={<DialogActions pending={pending} disabled={!reason.trim()} submitLabel="Submit failure" onCancel={onClose} onSubmit={() => onSubmit(reason.trim())} />}>
      <textarea className="desk-input min-h-28 w-full" placeholder="Failure reason" value={reason} onChange={(event) => setReason(event.target.value)} />
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
