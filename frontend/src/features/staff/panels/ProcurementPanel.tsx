import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import { downloadStaffFile, staffRequest } from "../../../lib/api";
import {
  ProcurementRow,
  itemTotal,
  labelStatus,
  statusOptions,
  type Kind,
  type ToBuyItem,
  type ToBuyStatus,
} from "./ProcurementPanelRows";
import { Panel, type Makerspace, useStaffGet } from "./shared";

type StatusFilter = "all" | ToBuyStatus;
type UpdateVariables = { id: number; payload: { status: ToBuyStatus; vendor_name: string; actual_unit_cost: number | null } };

type Form = {
  name: string;
  quantity: string;
  link: string;
  estimated_unit_cost: string;
  vendor_name: string;
  actual_unit_cost: string;
  kind: Kind;
};

const emptyForm: Form = {
  name: "",
  quantity: "1",
  link: "",
  estimated_unit_cost: "",
  vendor_name: "",
  actual_unit_cost: "",
  kind: "hardware",
};

export function ProcurementPanel({ makerspace, canChooseKind = false }: { makerspace: Makerspace; canChooseKind?: boolean }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Form>(emptyForm);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("requested");
  const base = `/procurement/makerspace/${makerspace.id}/to-buy`;
  const statusParam = statusFilter === "all" ? "" : `&status=${statusFilter}`;
  const queryKey = ["procurement", makerspace.id, statusFilter];
  const items = useStaffGet<ToBuyItem[]>(queryKey, `${base}?limit=200${statusParam}`);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["procurement", makerspace.id] });

  const create = useMutation({
    mutationFn: () => {
      const path = canChooseKind ? `${base}?kind=${form.kind}` : base;
      return staffRequest(path, {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          quantity: Number(form.quantity) || 1,
          link: form.link,
          estimated_unit_cost: form.estimated_unit_cost ? Number(form.estimated_unit_cost) : null,
          vendor_name: form.vendor_name,
          actual_unit_cost: form.actual_unit_cost ? Number(form.actual_unit_cost) : null,
        }),
      });
    },
    onSuccess: () => {
      setForm(emptyForm);
      invalidate();
    },
  });

  const update = useMutation({
    mutationFn: (vars: UpdateVariables) =>
      staffRequest(`/procurement/to-buy/${vars.id}`, {
        method: "PATCH",
        body: JSON.stringify(vars.payload),
      }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: number) => staffRequest(`/procurement/to-buy/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const exportToBuy = useMutation({
    mutationFn: (format: "csv" | "xlsx") => {
      const params = new URLSearchParams({ format });
      if (statusFilter !== "all") params.set("status", statusFilter);
      return downloadStaffFile(`${base}/export?${params.toString()}`, `to-buy-${makerspace.slug}.${format}`);
    },
  });

  const rows = items.data ?? [];
  const visibleEstimatedTotal = rows.reduce((sum, item) => sum + itemTotal(item, "estimated"), 0);
  const openBudget = rows.filter((item) => !["received", "cancelled"].includes(item.status)).reduce((sum, item) => sum + itemTotal(item, "estimated"), 0);
  const receivedTotal = rows.filter((item) => item.status === "received").reduce((sum, item) => sum + itemTotal(item, "actual"), 0);

  return (
    <Panel title="To Buy">
      <p className="mb-3 text-xs text-muted">
        Shopping list for {makerspace.name}. Track requested, approved, ordered, and received purchases with receipts.
      </p>

      <form className="grid gap-2 sm:grid-cols-2 xl:grid-cols-8" onSubmit={(event) => { event.preventDefault(); if (form.name.trim()) create.mutate(); }}>
        <input className="desk-input xl:col-span-2" placeholder="Item name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className="desk-input" type="number" min={1} placeholder="Qty" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
        <input className="desk-input" placeholder="Link (optional)" value={form.link} onChange={(e) => setForm({ ...form, link: e.target.value })} />
        <input className="desk-input" type="number" min={0} step="0.01" placeholder="Est. unit cost" value={form.estimated_unit_cost} onChange={(e) => setForm({ ...form, estimated_unit_cost: e.target.value })} />
        <input className="desk-input" placeholder="Vendor" value={form.vendor_name} onChange={(e) => setForm({ ...form, vendor_name: e.target.value })} />
        <input className="desk-input" type="number" min={0} step="0.01" placeholder="Actual unit cost" value={form.actual_unit_cost} onChange={(e) => setForm({ ...form, actual_unit_cost: e.target.value })} />
        {canChooseKind ? <KindSelect value={form.kind} onChange={(kind) => setForm({ ...form, kind })} /> : <AddButton disabled={create.isPending || !form.name.trim()} label="Add" />}
        {canChooseKind ? <AddButton disabled={create.isPending || !form.name.trim()} label="Add item" className="xl:col-span-8" /> : null}
      </form>
      <MutationErrors create={create.error} update={update.error} remove={remove.error} exportError={exportToBuy.error} />

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Visible estimated total" value={formatAmount(visibleEstimatedTotal)} />
          <Metric label="Open budget" value={formatAmount(openBudget)} />
          <Metric label="Received actual total" value={formatAmount(receivedTotal)} />
          <label className="grid gap-1 text-xs font-semibold uppercase tracking-wide text-muted">
            Status
            <select className="desk-input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
              <option value="all">All</option>
              {statusOptions.map((status) => <option key={status} value={status}>{labelStatus(status)}</option>)}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap gap-2 justify-self-start lg:justify-self-end">
          <button className="desk-button" type="button" disabled={exportToBuy.isPending} onClick={() => exportToBuy.mutate("csv")}>Export CSV</button>
          <button className="desk-button" type="button" disabled={exportToBuy.isPending} onClick={() => exportToBuy.mutate("xlsx")}>Export XLSX</button>
        </div>
      </div>
      <ProcurementTable rows={rows} items={items} update={update} remove={remove} invalidate={invalidate} />
    </Panel>
  );
}

function ProcurementTable({ rows, items, update, remove, invalidate }: { rows: ToBuyItem[]; items: UseQueryResult<ToBuyItem[], Error>; update: UseMutationResult<unknown, Error, UpdateVariables>; remove: UseMutationResult<unknown, Error, number>; invalidate: () => void }) {
  if (items.isFetching && !items.isLoading) return <p className="mt-2 text-xs text-muted">Refreshing list...</p>;
  if (items.isLoading) return <p className="mt-3 text-sm text-muted">Loading...</p>;
  if (items.error) return <p className="mt-3 text-sm text-danger">{items.error instanceof Error ? items.error.message : "Unable to load list."}</p>;
  if (!rows.length) return <p className="mt-3 text-sm text-muted">Nothing on the list yet.</p>;
  return (
    <div className="mt-3 max-h-[32rem] overflow-x-auto overflow-y-auto rounded-md border border-line">
      <table className="min-w-[1180px] divide-y divide-line text-left text-sm">
        <thead className="sticky top-0 bg-surface text-xs uppercase tracking-wide text-muted">
          <tr>{["kind", "item", "qty", "link", "est.", "vendor", "actual", "purchaser", "ordered", "received", "receipts", "status", ""].map((header) => <th key={header} className="whitespace-nowrap px-3 py-2 font-semibold">{header}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-line bg-bg text-ink">
          {rows.map((item) => <ProcurementRow key={item.id} item={item} updatePending={update.isPending} deletePending={remove.isPending} onSave={(draft) => update.mutate({ id: item.id, payload: { status: draft.status, vendor_name: draft.vendor_name, actual_unit_cost: draft.actual_unit_cost ? Number(draft.actual_unit_cost) : null } })} onDelete={() => remove.mutate(item.id)} onReceiptsChanged={invalidate} />)}
        </tbody>
      </table>
    </div>
  );
}

function KindSelect({ value, onChange }: { value: Kind; onChange: (kind: Kind) => void }) {
  return <select className="desk-input" value={value} onChange={(e) => onChange(e.target.value as Kind)}><option value="hardware">Hardware</option><option value="printing">Printing</option></select>;
}

function AddButton({ disabled, label, className = "" }: { disabled: boolean; label: string; className?: string }) {
  return <button className={`desk-button-primary ${className}`} type="submit" disabled={disabled}>{label}</button>;
}

function MutationErrors({ create, update, remove, exportError }: { create: unknown; update: unknown; remove: unknown; exportError: unknown }) {
  const errors = [[create, "Could not add item."], [update, "Could not update item."], [remove, "Could not delete item."], [exportError, "Could not export list."]] as const;
  return <>{errors.map(([error, fallback]) => error ? <p key={fallback} className="mt-2 text-sm text-danger">{error instanceof Error ? error.message : fallback}</p> : null)}</>;
}

function formatAmount(value: number) {
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-md border border-line bg-bg px-3 py-2"><p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p><p className="mt-1 text-lg font-semibold text-ink">{value}</p></div>;
}


