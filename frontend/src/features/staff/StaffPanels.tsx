import { Fragment, useEffect, useState } from "react";
import type React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { downloadStaffFile, staffRequest } from "../../lib/api";

export type Makerspace = {
  id: number;
  name: string;
  public_code: string;
  slug: string;
  telegram_group_chat_id: string;
};
type Product = {
  id: number;
  name: string;
  total_quantity: number;
  available_quantity: number;
  issued_quantity: number;
  damaged_quantity: number;
  lost_quantity: number;
  box?: number | null;
  description: string;
  tracking_mode: string;
  is_public: boolean;
  public_self_checkout_enabled: boolean;
};
type Container = {
  id: number;
  label: string;
  location: string;
};
type RequestItem = {
  id: number;
  product_id: number;
  product_name: string;
  requested_quantity: number;
  issued_quantity: number;
  returned_quantity: number;
  damaged_quantity: number;
  missing_quantity: number;
};
type HardwareRequest = {
  id: number;
  status: string;
  requester_username: string;
  requested_for: string;
  return_due_at: string | null;
  return_reminder_sent_at: string | null;
  items: RequestItem[];
  assigned_box?: { code: string; label: string };
};
type FilamentSpool = {
  id: number;
  printer: number | null;
  printer_name?: string;
  material: string;
  color: string;
  brand: string;
  initial_weight_grams: string;
  remaining_weight_grams: string;
  is_active: boolean;
};
type PrintPrinter = {
  id: number;
  makerspace: number;
  name: string;
  model: string;
  status: string;
  is_active: boolean;
  active_spool: FilamentSpool | null;
  current_request: { id: number; title: string; estimated_minutes: number } | null;
  is_free: boolean;
  pending_estimated_minutes: number;
  estimated_spool_remaining_after_queue_grams: string | null;
};
type PrintRequest = {
  id: number;
  title: string;
  requester_username: string;
  status: string;
  material: string;
  color: string;
  estimated_minutes: number;
  estimated_filament_grams: string;
  printer: PrintPrinter | null;
  filament_spool: FilamentSpool | null;
};

export function useStaffGet<T>(key: unknown[], path: string, enabled = true) {
  return useQuery({
    queryKey: key,
    queryFn: () => staffRequest<T>(path),
    enabled,
  });
}

export function Queues({ makerspace, guestOnly }: { makerspace: Makerspace; guestOnly: boolean }) {
  const queryClient = useQueryClient();
  const policy = useStaffGet<{ id: number; default_loan_days: number }>(
    ["return-policy", makerspace.id],
    `/admin/makerspace/${makerspace.id}/return-policy`,
    !guestOnly,
  );
  const [defaultLoanDays, setDefaultLoanDays] = useState("7");
  const pending = useStaffGet<{ results: HardwareRequest[] }>(
    ["pending", makerspace.id],
    `/admin/makerspace/${makerspace.id}/pending-requests`,
    !guestOnly,
  );
  const accepted = useStaffGet<{ results: HardwareRequest[] }>(
    ["accepted", makerspace.id],
    `/admin/makerspace/${makerspace.id}/accepted-requests`,
  );
  const active = useStaffGet<{ results: HardwareRequest[] }>(
    ["active", makerspace.id],
    `/admin/makerspace/${makerspace.id}/active-loans`,
  );
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: object }) =>
      staffRequest(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
    onSuccess: () => queryClient.invalidateQueries(),
  });
  const savePolicy = useMutation({
    mutationFn: () =>
      staffRequest(`/admin/makerspace/${makerspace.id}/return-policy`, {
        method: "PATCH",
        body: JSON.stringify({ default_loan_days: Number(defaultLoanDays) || 7 }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["return-policy", makerspace.id] }),
  });
  useEffect(() => {
    if (policy.data) {
      setDefaultLoanDays(String(policy.data.default_loan_days));
    }
  }, [policy.data]);
  const setDue = (row: HardwareRequest) => {
    const value = prompt(
      "Return due date/time",
      row.return_due_at ? localDateTimeValue(row.return_due_at) : localDateTimeValue(defaultDueDate(Number(defaultLoanDays) || 7).toISOString()),
    );
    if (value === null) return;
    action.mutate({
      path: `/admin/requests/${row.id}/return-due`,
      body: { return_due_at: value ? new Date(value).toISOString() : null },
    });
  };
  return (
    <div className="grid gap-4">
      {!guestOnly ? (
        <Panel title="Return policy">
          <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
            <input
              className="desk-input"
              type="number"
              min="1"
              value={defaultLoanDays}
              onChange={(event) => setDefaultLoanDays(event.target.value)}
            />
            <button disabled={savePolicy.isPending} onClick={() => savePolicy.mutate()}>
              Save default days
            </button>
          </div>
          <p className="mt-2 text-sm text-muted">
            Default return time is used when a request is issued. Current default: {policy.data?.default_loan_days ?? 7} days.
          </p>
        </Panel>
      ) : null}
      {!guestOnly ? (
        <Panel title="Pending review">
          <RequestList
            rows={pending.data?.results ?? []}
            actions={(row) => (
              <>
                <button onClick={() => action.mutate({ path: `/admin/requests/${row.id}/accept` })}>Accept</button>
                <button onClick={() => action.mutate({ path: `/admin/requests/${row.id}/reject`, body: { reason: "Rejected in admin app." } })}>Reject</button>
                <button onClick={() => setDue(row)}>Set due</button>
              </>
            )}
          />
        </Panel>
      ) : null}
      <Panel title="Handover queue">
        <RequestList
          rows={accepted.data?.results ?? []}
          actions={(row) => (
            <>
              <button onClick={() => action.mutate({ path: `/admin/requests/${row.id}/assign-box`, body: { box_code: prompt("Box QR code") ?? "" } })}>Assign box</button>
              <button onClick={() => action.mutate({ path: `/admin/requests/${row.id}/issue`, body: { evidence_id: Number(prompt("Issue evidence id")), remark: "Issued from staff app." } })}>Issue</button>
              <button onClick={() => setDue(row)}>Set due</button>
            </>
          )}
        />
      </Panel>
      {!guestOnly ? (
        <Panel title="Active loans">
          <RequestList
            rows={active.data?.results ?? []}
            actions={(row) => (
              <>
                <button onClick={() => setDue(row)}>Set due</button>
                <button onClick={() => action.mutate({ path: `/admin/requests/${row.id}/return`, body: returnPayload(row) })}>Return</button>
              </>
            )}
          />
        </Panel>
      ) : null}
    </div>
  );
}

function returnPayload(row: HardwareRequest) {
  return {
    evidence_id: Number(prompt("Return evidence id")),
    box_code: prompt("Returned box QR code") ?? row.assigned_box?.code ?? "",
    remark: prompt("Return remark") ?? "",
    resolutions: row.items.map((item) => ({
      item_id: item.id,
      returned: item.issued_quantity - item.returned_quantity - item.damaged_quantity - item.missing_quantity,
      damaged: 0,
      missing: 0,
    })),
  };
}

function RequestList({ rows, actions }: { rows: HardwareRequest[]; actions: (row: HardwareRequest) => React.ReactNode }) {
  if (!rows.length) return <p className="text-sm text-ink/60">No requests.</p>;
  return (
    <div className="overflow-hidden rounded-md border border-line">
      {rows.map((row) => (
        <article key={row.id} className="border-b border-line bg-surface/50 p-3 last:border-b-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-ink">#{row.id} {row.requester_username}</h3>
            <span className="rounded-md border border-line bg-bg px-2 py-0.5 text-xs text-muted">{row.status}</span>
            <div className="desk-actions ml-auto flex flex-wrap gap-2 text-sm">
              {actions(row)}
            </div>
          </div>
          <p className="mt-2 text-sm text-muted">{row.requested_for || "No note"}</p>
          <p className="mt-1 text-xs text-muted">
            {row.return_due_at ? `Due ${new Date(row.return_due_at).toLocaleString()}` : "No return due time set"}
            {row.return_reminder_sent_at ? ` · reminder sent ${new Date(row.return_reminder_sent_at).toLocaleString()}` : ""}
          </p>
          <p className="mt-2 text-xs text-ink/60">
            {row.items.map((item) => `${item.product_name} x${item.requested_quantity}`).join(", ")}
          </p>
        </article>
      ))}
    </div>
  );
}

function defaultDueDate(days: number) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date;
}

function localDateTimeValue(value: string) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function Inventory({ makerspace }: { makerspace: Makerspace }) {
  const queryClient = useQueryClient();
  const storageKey = `inventory.view.${makerspace.id}`;
  const [search, setSearch] = useState(() => localStorage.getItem(storageKey) ?? "");
  const [selected, setSelected] = useState<Record<number, boolean>>({});
  const [expanded, setExpanded] = useState<number | null>(null);
  const products = useStaffGet<{ results: Product[] }>(
    ["inventory", makerspace.id],
    `/admin/makerspace/${makerspace.id}/inventory`,
  );
  const toggle = useMutation({
    mutationFn: (product: Product) =>
      staffRequest(`/admin/inventory/${product.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          public_self_checkout_enabled: !product.public_self_checkout_enabled,
        }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["inventory", makerspace.id] }),
  });
  const bulkQr = useMutation({
    mutationFn: (enabled: boolean) =>
      Promise.all(
        Object.keys(selected)
          .filter((id) => selected[Number(id)])
          .map((id) =>
            staffRequest(`/admin/inventory/${id}`, {
              method: "PATCH",
              body: JSON.stringify({ public_self_checkout_enabled: enabled }),
            }),
          ),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["inventory", makerspace.id] }),
  });
  const rows = (products.data?.results ?? []).filter((product) =>
    [product.name, product.description, product.tracking_mode]
      .join(" ")
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  const selectedCount = Object.values(selected).filter(Boolean).length;
  return (
    <Panel title="Inventory">
      <div className="mb-3 flex flex-wrap gap-2">
        <input
          className="desk-input min-w-64 flex-1"
          placeholder="Filter table"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <button
          onClick={() => {
            localStorage.setItem(storageKey, search);
          }}
        >
          Save view
        </button>
        <button disabled={!selectedCount || bulkQr.isPending} onClick={() => bulkQr.mutate(true)}>
          Enable QR
        </button>
        <button disabled={!selectedCount || bulkQr.isPending} onClick={() => bulkQr.mutate(false)}>
          Disable QR
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="bg-surface text-xs uppercase tracking-wide text-muted"><tr className="border-b border-line"><th className="px-3 py-2">Select</th><th>Name</th><th>Mode</th><th>Total</th><th>Available</th><th>Issued</th><th>Damaged</th><th>Lost</th><th>Public QR</th></tr></thead>
          <tbody>
            {rows.map((product) => (
              <Fragment key={product.id}>
                <tr className="border-b border-line last:border-b-0">
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={Boolean(selected[product.id])}
                      onChange={(event) => setSelected((current) => ({ ...current, [product.id]: event.target.checked }))}
                    />
                  </td>
                  <td className="py-2 font-medium text-ink">
                    <button className="text-left font-semibold" onClick={() => setExpanded(expanded === product.id ? null : product.id)}>
                      {product.name}
                    </button>
                  </td>
                  <td>{product.tracking_mode}</td>
                  <td>{product.total_quantity}</td>
                  <td>{product.available_quantity}</td>
                  <td>{product.issued_quantity}</td>
                  <td>{product.damaged_quantity}</td>
                  <td>{product.lost_quantity}</td>
                  <td>
                    <button onClick={() => toggle.mutate(product)}>
                      {product.public_self_checkout_enabled ? "Allowed" : "Off"}
                    </button>
                  </td>
                </tr>
                {expanded === product.id ? (
                  <tr className="border-b border-line bg-bg">
                    <td className="px-3 py-3 text-sm text-muted" colSpan={9}>
                      <div className="grid gap-2 md:grid-cols-3">
                        <span>Public: {product.is_public ? "yes" : "no"}</span>
                        <span>Box: {product.box ?? "none"}</span>
                        <span>Tracking: {product.tracking_mode}</span>
                      </div>
                      <p className="mt-2 max-w-3xl">{product.description || "No description."}</p>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

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
  const [spoolWeight, setSpoolWeight] = useState("1000");
  const [selectedPrinter, setSelectedPrinter] = useState("");
  const [selectedSpool, setSelectedSpool] = useState("");
  const [estimatedMinutes, setEstimatedMinutes] = useState("60");
  const [estimatedGrams, setEstimatedGrams] = useState("100");

  const invalidatePrinting = () => {
    queryClient.invalidateQueries({ queryKey: ["print-printers", makerspace.id] });
    queryClient.invalidateQueries({ queryKey: ["print-spools", makerspace.id] });
    queryClient.invalidateQueries({ queryKey: ["print-requests", makerspace.id] });
  };
  const createPrinter = useMutation({
    mutationFn: () =>
      staffRequest("/printing/manage/printers/", {
        method: "POST",
        body: JSON.stringify({
          makerspace: makerspace.id,
          name: printerName,
          model: printerModel,
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
      staffRequest("/printing/manage/spools/", {
        method: "POST",
        body: JSON.stringify({
          makerspace: makerspace.id,
          printer: spoolPrinter ? Number(spoolPrinter) : null,
          material: spoolMaterial,
          color: spoolColor,
          initial_weight_grams: spoolWeight,
          remaining_weight_grams: spoolWeight,
          is_active: true,
        }),
      }),
    onSuccess: () => {
      setSpoolColor("");
      invalidatePrinting();
    },
  });
  const action = useMutation({
    mutationFn: ({ request, name }: { request: PrintRequest; name: "start" | "complete" | "fail" }) => {
      const body =
        name === "start"
          ? {
              printer_id: selectedPrinter ? Number(selectedPrinter) : undefined,
              filament_spool_id: selectedSpool ? Number(selectedSpool) : undefined,
              estimated_minutes: Number(estimatedMinutes),
              estimated_filament_grams: estimatedGrams,
            }
          : name === "fail"
            ? { reason: prompt("Failure reason") ?? "Failed from staff app." }
            : {};
      return staffRequest(`/printing/manage/requests/${request.id}/${name}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    onSuccess: invalidatePrinting,
  });

  const printerRows = printers.data?.results ?? [];
  const spoolRows = spools.data?.results ?? [];
  return (
    <div className="grid gap-4">
      <Panel title="3D printers">
        <div className="grid gap-3 md:grid-cols-3">
          {printerRows.map((printer) => (
            <div key={printer.id} className="rounded-md border border-line bg-surface p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold text-ink">{printer.name}</h3>
                  <p className="text-xs text-muted">{printer.model || "No model"}</p>
                </div>
                <span className={`rounded-md px-2 py-1 text-xs font-semibold ${printer.is_free ? "bg-success/15 text-success" : "bg-warn/15 text-warn"}`}>
                  {printer.is_free ? "Free" : "Busy"}
                </span>
              </div>
              <dl className="mt-3 grid gap-1 text-sm text-muted">
                <div className="flex justify-between gap-2"><dt>Status</dt><dd>{printer.status}</dd></div>
                <div className="flex justify-between gap-2"><dt>Pending</dt><dd>{printer.pending_estimated_minutes} min</dd></div>
                <div className="flex justify-between gap-2"><dt>Current</dt><dd>{printer.current_request?.title ?? "None"}</dd></div>
                <div className="flex justify-between gap-2">
                  <dt>Spool</dt>
                  <dd>{printer.active_spool ? `${printer.active_spool.material} ${printer.active_spool.color}` : "None"}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Left after queue</dt>
                  <dd>{printer.estimated_spool_remaining_after_queue_grams ?? "-"} g</dd>
                </div>
              </dl>
            </div>
          ))}
        </div>
        <div className="mt-4 grid gap-2 md:grid-cols-[1fr_1fr_auto]">
          <input className="desk-input" placeholder="Printer name" value={printerName} onChange={(event) => setPrinterName(event.target.value)} />
          <input className="desk-input" placeholder="Model" value={printerModel} onChange={(event) => setPrinterModel(event.target.value)} />
          <button disabled={!printerName || createPrinter.isPending} onClick={() => createPrinter.mutate()}>Add printer</button>
        </div>
      </Panel>

      <Panel title="Filament spools">
        <div className="grid gap-2 md:grid-cols-[1fr_1fr_1fr_1fr_auto]">
          <select className="desk-input" value={spoolPrinter} onChange={(event) => setSpoolPrinter(event.target.value)}>
            <option value="">Unassigned printer</option>
            {printerRows.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}
          </select>
          <input className="desk-input" placeholder="Material" value={spoolMaterial} onChange={(event) => setSpoolMaterial(event.target.value)} />
          <input className="desk-input" placeholder="Color" value={spoolColor} onChange={(event) => setSpoolColor(event.target.value)} />
          <input className="desk-input" placeholder="Weight g" type="number" min="0" value={spoolWeight} onChange={(event) => setSpoolWeight(event.target.value)} />
          <button disabled={!spoolMaterial || !spoolWeight || createSpool.isPending} onClick={() => createSpool.mutate()}>Add spool</button>
        </div>
        <div className="mt-3 grid gap-2 text-sm">
          {spoolRows.map((spool) => (
            <div key={spool.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-line bg-surface px-3 py-2">
              <span className="font-medium text-ink">{spool.material} {spool.color || ""}</span>
              <span className="text-muted">{spool.printer_name ?? "Unassigned"}</span>
              <span className="text-muted">{spool.remaining_weight_grams}g left</span>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Print queue">
        <div className="mb-3 grid gap-2 md:grid-cols-4">
          <select className="desk-input" value={selectedPrinter} onChange={(event) => setSelectedPrinter(event.target.value)}>
            <option value="">Printer</option>
            {printerRows.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}
          </select>
          <select className="desk-input" value={selectedSpool} onChange={(event) => setSelectedSpool(event.target.value)}>
            <option value="">Spool</option>
            {spoolRows
              .filter((spool) => !selectedPrinter || spool.printer === Number(selectedPrinter) || spool.printer === null)
              .map((spool) => <option key={spool.id} value={spool.id}>{spool.material} {spool.color} ({spool.remaining_weight_grams}g)</option>)}
          </select>
          <input className="desk-input" type="number" min="0" value={estimatedMinutes} onChange={(event) => setEstimatedMinutes(event.target.value)} />
          <input className="desk-input" type="number" min="0" value={estimatedGrams} onChange={(event) => setEstimatedGrams(event.target.value)} />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <PrintRows title="Accepted" rows={accepted.data?.results ?? []} action={(row) => (
            <button disabled={!selectedPrinter || action.isPending} onClick={() => action.mutate({ request: row, name: "start" })}>Start on printer</button>
          )} />
          <PrintRows title="Printing" rows={printing.data?.results ?? []} action={(row) => (
            <>
              <button onClick={() => action.mutate({ request: row, name: "complete" })}>Complete</button>
              <button onClick={() => action.mutate({ request: row, name: "fail" })}>Fail</button>
            </>
          )} />
        </div>
      </Panel>
    </div>
  );
}

function PrintRows({
  title,
  rows,
  action,
}: {
  title: string;
  rows: PrintRequest[];
  action: (row: PrintRequest) => React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-line">
      <h3 className="border-b border-line bg-surface px-3 py-2 text-sm font-semibold text-muted">{title}</h3>
      <div className="grid gap-0">
        {rows.length ? rows.map((row) => (
          <article key={row.id} className="border-b border-line p-3 last:border-b-0">
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-ink">#{row.id} {row.title}</strong>
              <span className="rounded-md border border-line bg-bg px-2 py-0.5 text-xs text-muted">{row.status}</span>
              <div className="desk-actions ml-auto flex flex-wrap gap-2 text-sm">{action(row)}</div>
            </div>
            <p className="mt-2 text-xs text-muted">
              {row.requester_username} · {row.material || "material n/a"} {row.color || ""} · {row.estimated_minutes || 0} min · {row.estimated_filament_grams || "0.00"}g
            </p>
          </article>
        )) : <p className="p-3 text-sm text-muted">No print requests.</p>}
      </div>
    </div>
  );
}

export function BulkImport({ makerspace }: { makerspace: Makerspace }) {
  const [text, setText] = useState('[{"name":"New Kit","total_quantity":"1","available_quantity":"1"}]');
  const mutation = useMutation({
    mutationFn: (apply: boolean) =>
      staffRequest(`/admin/makerspace/${makerspace.id}/inventory/import/${apply ? "apply" : "preview"}`, {
        method: "POST",
        body: JSON.stringify({ rows: JSON.parse(text) }),
      }),
  });
  return (
    <Panel title="Bulk import">
      <textarea className="desk-input h-40 w-full font-mono text-sm" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="mt-3 flex gap-2">
        <button onClick={() => mutation.mutate(false)}>Preview</button>
        <button onClick={() => mutation.mutate(true)}>Apply</button>
      </div>
      {mutation.data ? <pre className="mt-3 max-h-80 overflow-auto rounded-md border border-line bg-bg p-3 text-xs text-muted">{JSON.stringify(mutation.data, null, 2)}</pre> : null}
    </Panel>
  );
}

export function QrTools({ makerspace }: { makerspace: Makerspace }) {
  const [batchTitle, setBatchTitle] = useState("QR labels");
  const mutation = useMutation({
    mutationFn: () =>
      staffRequest("/admin/qr/containers", {
        method: "POST",
        body: JSON.stringify({ makerspace_id: makerspace.id, label: prompt("Box label") ?? "" }),
      }),
  });
  const batch = useMutation({
    mutationFn: () =>
      staffRequest(`/admin/makerspace/${makerspace.id}/qr-print-batches`, {
        method: "POST",
        body: JSON.stringify({ title: batchTitle }),
      }),
  });
  return (
    <Panel title="QR tools">
      <div className="flex flex-wrap gap-2">
        <button onClick={() => mutation.mutate()}>Create container QR</button>
        <input className="desk-input" value={batchTitle} onChange={(event) => setBatchTitle(event.target.value)} />
        <button onClick={() => batch.mutate()}>Create print batch</button>
      </div>
      {mutation.data ? <pre className="mt-3 rounded-md border border-line bg-bg p-3 text-xs text-muted">{JSON.stringify(mutation.data, null, 2)}</pre> : null}
      {batch.data ? <pre className="mt-3 rounded-md border border-line bg-bg p-3 text-xs text-muted">{JSON.stringify(batch.data, null, 2)}</pre> : null}
    </Panel>
  );
}

export function StockTransferPanel({ makerspace }: { makerspace: Makerspace }) {
  const queryClient = useQueryClient();
  const products = useStaffGet<{ results: Product[] }>(["inventory", makerspace.id], `/admin/makerspace/${makerspace.id}/inventory`);
  const transfers = useStaffGet<{ results: unknown[] }>(["transfers", makerspace.id], `/admin/makerspace/${makerspace.id}/stock-transfers`);
  const containers = useStaffGet<{ results: Container[] }>(["containers", makerspace.id], `/admin/makerspace/${makerspace.id}/containers`);
  const [productId, setProductId] = useState("");
  const [destinationId, setDestinationId] = useState("");
  const [reason, setReason] = useState("Operational transfer");
  const create = useMutation({
    mutationFn: () =>
      staffRequest(`/admin/makerspace/${makerspace.id}/stock-transfers`, {
        method: "POST",
        body: JSON.stringify({
          destination_container_id: destinationId ? Number(destinationId) : null,
          reason,
          lines: [{ product_id: Number(productId), quantity: 1 }],
        }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["transfers", makerspace.id] }),
  });
  return (
    <Panel title="Stock transfers">
      <div className="grid gap-2 md:grid-cols-[1fr_1fr_1fr_auto]">
        <select className="desk-input" value={productId} onChange={(event) => setProductId(event.target.value)}>
          <option value="">Product</option>
          {products.data?.results?.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
        </select>
        <select className="desk-input" value={destinationId} onChange={(event) => setDestinationId(event.target.value)}>
          <option value="">Destination</option>
          {containers.data?.results?.map((container) => <option key={container.id} value={container.id}>{container.label}</option>)}
        </select>
        <input className="desk-input" value={reason} onChange={(event) => setReason(event.target.value)} />
        <button disabled={!productId || create.isPending} onClick={() => create.mutate()}>Create</button>
      </div>
      <JsonRows data={transfers.data?.results ?? []} />
    </Panel>
  );
}

export function StocktakePanel({ makerspace }: { makerspace: Makerspace }) {
  const queryClient = useQueryClient();
  const stocktakes = useStaffGet<{ results: { id: number; status: string; notes: string }[] }>(["stocktakes", makerspace.id], `/admin/makerspace/${makerspace.id}/stocktakes`);
  const create = useMutation({
    mutationFn: () =>
      staffRequest(`/admin/makerspace/${makerspace.id}/stocktakes`, {
        method: "POST",
        body: JSON.stringify({ notes: "Cycle count" }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["stocktakes", makerspace.id] }),
  });
  const action = useMutation({
    mutationFn: (path: string) => staffRequest(path, { method: "POST", body: JSON.stringify({}) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["stocktakes", makerspace.id] }),
  });
  return (
    <Panel title="Stocktake">
      <button onClick={() => create.mutate()}>Start stocktake</button>
      <div className="mt-3 grid gap-2">
        {stocktakes.data?.results?.map((row) => (
          <div key={row.id} className="rounded-md border border-line bg-surface p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <strong>#{row.id}</strong>
              <span className="rounded-md border border-line bg-bg px-2 py-0.5 text-xs text-muted">{row.status}</span>
              <button onClick={() => action.mutate(`/admin/stocktakes/${row.id}/complete`)}>Complete</button>
              <button onClick={() => action.mutate(`/admin/stocktakes/${row.id}/approve`)}>Approve</button>
              <button onClick={() => action.mutate(`/admin/stocktakes/${row.id}/apply-adjustments`)}>Apply</button>
            </div>
            <p className="mt-1 text-muted">{row.notes}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export function OperationsReports({ makerspace }: { makerspace: Makerspace }) {
  const summary = useStaffGet<Record<string, number>>(["analytics", makerspace.id], `/admin/makerspace/${makerspace.id}/analytics/summary`);
  const reports = ["taken-items", "active-loans", "returns", "damaged-missing"];
  return (
    <Panel title="Reports">
      <div className="grid gap-3 sm:grid-cols-4">
        {Object.entries(summary.data ?? {}).map(([key, value]) => (
          <div key={key} className="rounded-md border border-line bg-surface p-3">
            <p className="text-2xl font-bold text-ink">{value}</p>
            <p className="text-xs text-muted">{key.replace(/_/g, " ")}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {reports.map((report) => (
          <button
            key={report}
            className="desk-button"
            onClick={() => downloadStaffFile(`/admin/makerspace/${makerspace.id}/reports/${report}/export?format=csv`, `${report}.csv`)}
          >
            {report} CSV
          </button>
        ))}
      </div>
    </Panel>
  );
}

function JsonRows({ data }: { data: unknown[] }) {
  if (!data.length) return <p className="mt-3 text-sm text-muted">No records.</p>;
  return <pre className="mt-3 max-h-80 overflow-auto rounded-md border border-line bg-bg p-3 text-xs text-muted">{JSON.stringify(data, null, 2)}</pre>;
}

export function Users() {
  const spaceManagers = useStaffGet<{ results: unknown[] }>(
    ["space-managers"],
    "/admin/users/space-managers",
  );
  const inventoryManagers = useStaffGet<{ results: unknown[] }>(
    ["inventory-managers"],
    "/admin/users/inventory-managers",
  );
  const guests = useStaffGet<{ results: unknown[] }>(["guests"], "/admin/users/guest-admins");
  const printManagers = useStaffGet<{ results: unknown[] }>(
    ["print-managers"],
    "/admin/users/print-managers",
  );
  return (
    <Panel title="Users">
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-md border border-line bg-surface p-3">
          <p className="text-2xl font-bold text-ink">{spaceManagers.data?.results?.length ?? 0}</p>
          <p className="text-xs text-muted">Space managers</p>
        </div>
        <div className="rounded-md border border-line bg-surface p-3">
          <p className="text-2xl font-bold text-ink">{inventoryManagers.data?.results?.length ?? 0}</p>
          <p className="text-xs text-muted">Inventory managers</p>
        </div>
        <div className="rounded-md border border-line bg-surface p-3">
          <p className="text-2xl font-bold text-ink">{guests.data?.results?.length ?? 0}</p>
          <p className="text-xs text-muted">Guest admins</p>
        </div>
        <div className="rounded-md border border-line bg-surface p-3">
          <p className="text-2xl font-bold text-ink">{printManagers.data?.results?.length ?? 0}</p>
          <p className="text-xs text-muted">Print managers</p>
        </div>
      </div>
    </Panel>
  );
}

export function AuditLog() {
  const [targetType, setTargetType] = useState("");
  const [targetId, setTargetId] = useState("");
  const params = new URLSearchParams();
  if (targetType) params.set("target_type", targetType);
  if (targetId) params.set("target_id", targetId);
  const query = params.toString();
  const logs = useStaffGet<{ results: { id: number; action: string; target_type: string; target_id: string; created_at: string }[] }>(
    ["audit", query],
    `/admin/audit-logs${query ? `?${query}` : ""}`,
  );
  return (
    <Panel title="Audit logs">
      <div className="mb-3 grid gap-2 sm:grid-cols-2">
        <input className="desk-input" placeholder="target type, e.g. inventory.inventoryproduct" value={targetType} onChange={(e) => setTargetType(e.target.value)} />
        <input className="desk-input" placeholder="target id" value={targetId} onChange={(e) => setTargetId(e.target.value)} />
      </div>
      <div className="grid gap-2 text-sm">
        {logs.data?.results?.map((log) => (
          <div key={log.id} className="rounded-md border border-line bg-surface p-2">
            <span className="font-semibold">{log.action}</span>
            <span className="ml-2 text-muted">{log.target_type}:{log.target_id}</span>
            <span className="ml-2 text-muted">{new Date(log.created_at).toLocaleString()}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="desk-panel overflow-hidden">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>
      </div>
      <div className="desk-panel-body p-4">
        {children}
      </div>
    </section>
  );
}
