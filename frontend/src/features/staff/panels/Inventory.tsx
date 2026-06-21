import type { Key, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ConfirmDialog, DataTable, FilterBar, Modal, StatusBadge } from "../../../components/ui";
import type { DataTableColumn } from "../../../components/ui";
import { staffRequest } from "../../../lib/api";
import { useDebouncedValue } from "../../../lib/useDebouncedValue";
import { ImageUploader } from "../ImageUploader";
import { categoryResults, Panel, type Category, type CategoryListResponse, type Makerspace, type Product, useStaffGet } from "./shared";

type AdminProduct = Product & {
  reserved_quantity: number;
  storage_location: string;
  show_public_count: boolean;
  public_availability_mode: string;
  is_archived: boolean;
};
type ItemForm = {
  name: string; tracking_mode: string; category: string; description: string; total_quantity: string; available_quantity: string;
  storage_location: string; is_public: boolean; public_self_checkout_enabled: boolean; show_public_count: boolean; public_availability_mode: string;
};
type AdjustmentForm = { delta_available: string; delta_damaged: string; delta_lost: string; reason: string };
type Actor = { username: string; role: string };
type LendingHistoryEntry = { id: number; username: string; issued_at: string; quantity: number; accepted_by: Actor | null; issued_by: Actor | null };
type LendingHistoryResponse = { product_id: number; last_borrower: LendingHistoryEntry | null; recent: LendingHistoryEntry[] };

const emptyForm: ItemForm = {
  name: "", tracking_mode: "quantity", category: "", description: "", total_quantity: "1", available_quantity: "1",
  storage_location: "", is_public: true, public_self_checkout_enabled: false, show_public_count: false, public_availability_mode: "status_only",
};
const emptyAdjust: AdjustmentForm = { delta_available: "0", delta_damaged: "0", delta_lost: "0", reason: "" };

export function Inventory({ makerspace, canViewAudit = false }: { makerspace: Makerspace; canViewAudit?: boolean }) {
  const queryClient = useQueryClient();
  const storageKey = `inventory.view.${makerspace.id}`;
  const [search, setSearch] = useState(() => localStorage.getItem(storageKey) ?? "");
  const [selectedIds, setSelectedIds] = useState<Key[]>([]);
  const [form, setForm] = useState<ItemForm>(emptyForm);
  const [adjustForm, setAdjustForm] = useState<AdjustmentForm>(emptyAdjust);
  const [editing, setEditing] = useState<AdminProduct | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [archiveTarget, setArchiveTarget] = useState<AdminProduct | null>(null);
  const [qrConfirm, setQrConfirm] = useState<boolean | null>(null);
  const [bulkQrMessage, setBulkQrMessage] = useState("");
  const debouncedSearch = useDebouncedValue(search);
  useEffect(() => {
    setSearch(localStorage.getItem(`inventory.view.${makerspace.id}`) ?? "");
    setSelectedIds([]);
    setForm(emptyForm);
    setAdjustForm(emptyAdjust);
    setEditing(null);
    setAddOpen(false);
    setArchiveTarget(null);
    setQrConfirm(null);
    setBulkQrMessage("");
  }, [makerspace.id]);
  const products = useStaffGet<{ results: AdminProduct[] }>(["inventory", makerspace.id], `/admin/makerspace/${makerspace.id}/inventory`);
  const categories = useStaffGet<CategoryListResponse>(["categories", makerspace.id], `/admin/makerspace/${makerspace.id}/categories`);
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["inventory", makerspace.id] });
    queryClient.invalidateQueries({ queryKey: ["categories", makerspace.id] });
  };
  const create = useMutation({
    mutationFn: () => staffRequest(`/admin/makerspace/${makerspace.id}/inventory`, { method: "POST", body: JSON.stringify(payloadFromForm(form, true)) }),
    onSuccess: () => { setAddOpen(false); setForm(emptyForm); invalidate(); },
  });
  const update = useMutation({
    mutationFn: () => editing ? staffRequest(`/admin/inventory/${editing.id}`, { method: "PATCH", body: JSON.stringify(payloadFromForm(form, false)) }) : Promise.resolve(),
    onSuccess: () => { setEditing(null); setAdjustForm(emptyAdjust); invalidate(); },
  });
  const adjust = useMutation({
    mutationFn: () => editing ? staffRequest(`/admin/inventory/${editing.id}/adjust-quantity`, { method: "POST", body: JSON.stringify(adjustPayload(adjustForm)) }) : Promise.resolve(),
    onSuccess: () => { setAdjustForm(emptyAdjust); invalidate(); },
  });
  const archive = useMutation({
    mutationFn: (product: AdminProduct) => staffRequest(`/admin/inventory/${product.id}`, { method: "PATCH", body: JSON.stringify({ is_archived: true }) }),
    onSuccess: () => { setArchiveTarget(null); invalidate(); },
  });
  const bulkQr = useMutation({
    mutationFn: async (enabled: boolean) => {
      const ids = [...selectedIds];
      const results = await Promise.allSettled(
        ids.map((id) =>
          staffRequest(`/admin/inventory/${String(id)}`, {
            method: "PATCH",
            body: JSON.stringify({ public_self_checkout_enabled: enabled }),
          }),
        ),
      );
      return {
        total: ids.length,
        succeeded: results.filter((result) => result.status === "fulfilled").length,
        failed: results.filter((result) => result.status === "rejected").length,
      };
    },
    onSuccess: (result) => {
      setQrConfirm(null);
      setBulkQrMessage(`${result.succeeded} of ${result.total} items updated. ${result.failed} failed.`);
      invalidate();
    },
  });
  const rows = useMemo(() => {
    const normalizedSearch = debouncedSearch.toLowerCase();
    return (products.data?.results ?? []).filter((product) =>
      [product.name, product.description, product.tracking_mode, product.storage_location].join(" ").toLowerCase().includes(normalizedSearch),
    );
  }, [debouncedSearch, products.data?.results]);
  const categoryRows = categoryResults(categories.data);
  const openEdit = (product: AdminProduct) => {
    setEditing(product);
    setForm(formFromProduct(product));
    setAdjustForm(emptyAdjust);
  };
  const columns: DataTableColumn<AdminProduct>[] = [
    { key: "image", header: "", render: (product) => (
      <div className="h-10 w-10 overflow-hidden border-2 border-ink bg-surface">
        {product.image_url ? <img src={product.image_url} alt="" className="h-full w-full object-cover" /> : <div className="blueprint-bg h-full w-full" />}
      </div>
    ) },
    { key: "name", header: "Name", sortable: true, render: (product) => <button type="button" className="text-left font-semibold text-ink hover:text-accent" onClick={() => openEdit(product)}>{product.name}</button> },
    { key: "tracking_mode", header: "Mode", sortable: true },
    { key: "total_quantity", header: "Total", sortable: true },
    { key: "available_quantity", header: "Available", sortable: true, render: (product) => <InventoryAvailability product={product} /> },
    { key: "issued_quantity", header: "Issued", sortable: true },
    { key: "damaged_quantity", header: "Damaged", sortable: true },
    { key: "lost_quantity", header: "Lost", sortable: true },
    { key: "actions", header: "", render: (product) => (
      <div className="desk-actions flex flex-wrap gap-2">
        <button className="desk-button" type="button" onClick={() => openEdit(product)}>Edit</button>
        <button className="desk-button" type="button" onClick={() => setArchiveTarget(product)}>Archive</button>
      </div>
    ) },
  ];
  return (
    <Panel title="Inventory">
      <div className="grid gap-3">
        <FilterBar
          value={search}
          onChange={setSearch}
          placeholder="Filter table"
          actions={(
            <>
              <button className="desk-button" type="button" onClick={() => { setForm(emptyForm); setAddOpen(true); }}>Add item</button>
              <button className="desk-button" type="button" onClick={() => localStorage.setItem(storageKey, search)}>Save view</button>
              <button className="desk-button" type="button" disabled={!selectedIds.length || bulkQr.isPending} onClick={() => { setBulkQrMessage(""); setQrConfirm(true); }}>Enable QR</button>
              <button className="desk-button" type="button" disabled={!selectedIds.length || bulkQr.isPending} onClick={() => { setBulkQrMessage(""); setQrConfirm(false); }}>Disable QR</button>
            </>
          )}
        />
        <DataTable<AdminProduct> columns={columns} data={rows} getRowId={(row) => row.id} selectedIds={selectedIds} onSelectionChange={setSelectedIds} loading={products.isLoading} emptyTitle="No inventory" skeletonCols={columns.length + 1} />
        {bulkQrMessage ? <p className="text-sm text-muted">{bulkQrMessage}</p> : null}
      </div>
      <ItemModal title="Add item" open={addOpen} onClose={() => setAddOpen(false)} form={form} setForm={setForm} categories={categoryRows} includeQuantities pending={create.isPending} error={create.error?.message} onSubmit={() => create.mutate()} />
      <ItemModal title={editing?.name ?? "Edit item"} open={Boolean(editing)} onClose={() => setEditing(null)} form={form} setForm={setForm} categories={categoryRows} pending={update.isPending} error={update.error?.message} onSubmit={() => update.mutate()}>
        {editing ? <div className="border-t border-line pt-3"><ImageUploader endpoint={`/admin/inventory/${editing.id}/image`} currentUrl={editing.image_url} label="Item photo" onChanged={invalidate} /></div> : null}
        {editing ? <QuantityAdjust product={editing} form={adjustForm} setForm={setAdjustForm} pending={adjust.isPending} error={adjust.error?.message} onSubmit={() => adjust.mutate()} /> : null}
        {editing && canViewAudit ? <LendingHistory productId={editing.id} /> : null}
      </ItemModal>
      <ConfirmDialog open={Boolean(archiveTarget)} title="Archive item" message={archiveTarget ? `Archive ${archiveTarget.name}? It will be hidden from active inventory views.` : ""} confirmLabel="Archive" tone="danger" pending={archive.isPending} onCancel={() => setArchiveTarget(null)} onConfirm={() => { if (archiveTarget) archive.mutate(archiveTarget); }} />
      <ConfirmDialog open={qrConfirm !== null} title={qrConfirm ? "Enable public QR" : "Disable public QR"} message={`${qrConfirm ? "Enable" : "Disable"} public self-checkout QR for ${selectedIds.length} selected items?`} confirmLabel={qrConfirm ? "Enable" : "Disable"} pending={bulkQr.isPending} onCancel={() => setQrConfirm(null)} onConfirm={() => { if (qrConfirm !== null) bulkQr.mutate(qrConfirm); }} />
    </Panel>
  );
}

function ItemModal({ title, open, onClose, form, setForm, categories, includeQuantities = false, pending, error, onSubmit, children }: {
  title: string; open: boolean; onClose: () => void; form: ItemForm; setForm: (updater: (current: ItemForm) => ItemForm) => void; categories: Category[];
  includeQuantities?: boolean; pending: boolean; error?: string; onSubmit: () => void; children?: ReactNode;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title} footer={<div className="desk-actions flex flex-wrap justify-end gap-2"><button className="desk-button" type="button" disabled={pending} onClick={onClose}>Cancel</button><button className="desk-button" type="button" disabled={pending || !form.name.trim()} onClick={onSubmit}>Save</button></div>}>
      <div className="grid gap-3 text-sm">
        <input className="desk-input" placeholder="Name" value={form.name} onChange={(e) => setForm((c) => ({ ...c, name: e.target.value }))} />
        <div className="grid gap-2 sm:grid-cols-2">
          <select className="desk-input" value={form.tracking_mode} onChange={(e) => setForm((c) => ({ ...c, tracking_mode: e.target.value }))}><option value="quantity">Quantity</option><option value="individual">Individual</option></select>
          <select className="desk-input" value={form.category} onChange={(e) => setForm((c) => ({ ...c, category: e.target.value }))}><option value="">Uncategorized</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select>
        </div>
        <textarea className="desk-input h-20" placeholder="Description" value={form.description} onChange={(e) => setForm((c) => ({ ...c, description: e.target.value }))} />
        <input className="desk-input" placeholder="Storage location" value={form.storage_location} onChange={(e) => setForm((c) => ({ ...c, storage_location: e.target.value }))} />
        {includeQuantities ? <div className="grid gap-2 sm:grid-cols-2"><input className="desk-input" type="number" min="0" value={form.total_quantity} onChange={(e) => setForm((c) => ({ ...c, total_quantity: e.target.value }))} /><input className="desk-input" type="number" min="0" value={form.available_quantity} onChange={(e) => setForm((c) => ({ ...c, available_quantity: e.target.value }))} /></div> : null}
        <div className="grid gap-2 sm:grid-cols-3"><label><input type="checkbox" checked={form.is_public} onChange={(e) => setForm((c) => ({ ...c, is_public: e.target.checked }))} /> Public</label><label><input type="checkbox" checked={form.public_self_checkout_enabled} onChange={(e) => setForm((c) => ({ ...c, public_self_checkout_enabled: e.target.checked }))} /> Self checkout</label><label><input type="checkbox" checked={form.show_public_count} onChange={(e) => setForm((c) => ({ ...c, show_public_count: e.target.checked }))} /> Show count</label></div>
        <select className="desk-input" value={form.public_availability_mode} onChange={(e) => setForm((c) => ({ ...c, public_availability_mode: e.target.value }))}><option value="status_only">Status only</option><option value="exact_count">Exact count</option><option value="hidden">Hidden</option></select>
        {children}
        {error ? <p className="text-sm text-danger">{error}</p> : null}
      </div>
    </Modal>
  );
}

function QuantityAdjust({ product, form, setForm, pending, error, onSubmit }: { product: AdminProduct; form: AdjustmentForm; setForm: (updater: (current: AdjustmentForm) => AdjustmentForm) => void; pending: boolean; error?: string; onSubmit: () => void }) {
  return (
    <div className="grid gap-3 border-t border-line pt-3">
      <div className="grid gap-2 sm:grid-cols-3"><InventoryMetric label="Available" value={product.available_quantity} /><InventoryMetric label="Damaged" value={product.damaged_quantity} /><InventoryMetric label="Lost" value={product.lost_quantity} /></div>
      <div className="grid gap-2 sm:grid-cols-3"><input className="desk-input" type="number" value={form.delta_available} onChange={(e) => setForm((c) => ({ ...c, delta_available: e.target.value }))} /><input className="desk-input" type="number" value={form.delta_damaged} onChange={(e) => setForm((c) => ({ ...c, delta_damaged: e.target.value }))} /><input className="desk-input" type="number" value={form.delta_lost} onChange={(e) => setForm((c) => ({ ...c, delta_lost: e.target.value }))} /></div>
      <input className="desk-input" placeholder="Adjustment reason" value={form.reason} onChange={(e) => setForm((c) => ({ ...c, reason: e.target.value }))} />
      <div className="desk-actions flex justify-end"><button className="desk-button" type="button" disabled={pending || !form.reason.trim()} onClick={onSubmit}>Apply adjustment</button></div>
      {error ? <p className="text-sm text-danger">{error}</p> : null}
    </div>
  );
}

function LendingHistory({ productId }: { productId: number }) {
  const history = useStaffGet<LendingHistoryResponse>(["lending-history", productId], `/admin/inventory/${productId}/lending-history`);
  const last = history.data?.last_borrower;
  const recent = history.data?.recent ?? [];
  return (
    <div className="grid gap-2 border-t border-line pt-3">
      <h3 className="text-sm font-semibold text-ink">Lending history</h3>
      {history.isLoading ? <p className="text-sm text-muted">Loading lending history...</p> : null}
      {history.error ? <p className="text-sm text-danger">{history.error.message}</p> : null}
      {!history.isLoading && !history.error && !recent.length ? <p className="text-sm text-muted">No lending history yet.</p> : null}
      {last ? (
        <div className="text-sm text-ink">
          <p>Last borrower: {last.username} ({formatDate(last.issued_at)})</p>
          <AttributionLine acceptedBy={last.accepted_by} issuedBy={last.issued_by} />
        </div>
      ) : null}
      {recent.length ? (
        <ul className="grid gap-1 text-sm text-muted">
          {recent.map((entry) => (
            <li key={entry.id}>
              {entry.username} — {entry.quantity} on {formatDate(entry.issued_at)}
              <AttributionLine acceptedBy={entry.accepted_by} issuedBy={entry.issued_by} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function payloadFromForm(form: ItemForm, includeQuantities: boolean) {
  return {
    name: form.name.trim(), tracking_mode: form.tracking_mode, category: form.category ? Number(form.category) : null, description: form.description,
    storage_location: form.storage_location, is_public: form.is_public, public_self_checkout_enabled: form.public_self_checkout_enabled,
    show_public_count: form.show_public_count, public_availability_mode: form.public_availability_mode,
    ...(includeQuantities ? { total_quantity: Number(form.total_quantity || 0), available_quantity: Number(form.available_quantity || 0) } : {}),
  };
}

function adjustPayload(form: AdjustmentForm) {
  return { delta_available: Number(form.delta_available || 0), delta_damaged: Number(form.delta_damaged || 0), delta_lost: Number(form.delta_lost || 0), reason: form.reason.trim() };
}

function formFromProduct(product: AdminProduct): ItemForm {
  return { name: product.name, tracking_mode: product.tracking_mode, category: product.category ? String(product.category) : "", description: product.description, total_quantity: String(product.total_quantity), available_quantity: String(product.available_quantity), storage_location: product.storage_location ?? "", is_public: product.is_public, public_self_checkout_enabled: product.public_self_checkout_enabled, show_public_count: product.show_public_count, public_availability_mode: product.public_availability_mode };
}

function InventoryAvailability({ product }: { product: AdminProduct }) {
  const badge = product.available_quantity <= 0 ? <StatusBadge status="lost" label="Unavailable" /> : product.available_quantity <= Math.ceil(product.total_quantity * 0.2) ? <StatusBadge status="limited" label="Limited" /> : <StatusBadge status="available" label="Available" />;
  return <span className="inline-flex items-center gap-2"><span className="font-medium text-ink">{product.available_quantity}</span>{badge}</span>;
}

function InventoryMetric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-md border border-line bg-surface p-3"><p className="text-xs font-semibold uppercase text-muted">{label}</p><p className="mt-1 text-xl font-bold text-ink">{value}</p></div>;
}

function AttributionLine({ acceptedBy, issuedBy }: { acceptedBy: Actor | null; issuedBy: Actor | null }) {
  const parts = [
    acceptedBy ? `Accepted by ${formatActor(acceptedBy)}` : "",
    issuedBy ? `Issued by ${formatActor(issuedBy)}` : "",
  ].filter(Boolean);
  return parts.length ? <p className="text-xs text-muted">{parts.join(" | ")}</p> : null;
}

function formatActor(actor: Actor) {
  return actor.role ? `${actor.username} (${actor.role})` : actor.username;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
