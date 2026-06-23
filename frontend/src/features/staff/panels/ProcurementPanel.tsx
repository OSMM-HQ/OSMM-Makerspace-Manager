import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { downloadStaffFile, staffRequest } from "../../../lib/api";
import { Panel, type Makerspace, useStaffGet } from "./shared";

type Kind = "hardware" | "printing";

type ToBuyItem = {
  id: number;
  kind: Kind;
  name: string;
  quantity: number;
  link: string;
  status: "pending" | "bought";
  estimated_unit_cost: string | null;
  created_by_username: string | null;
};

type Form = { name: string; quantity: string; link: string; estimated_unit_cost: string; kind: Kind };

const emptyForm: Form = { name: "", quantity: "1", link: "", estimated_unit_cost: "", kind: "hardware" };

// Only render a clickable link for http(s) URLs. The backend URLField already
// rejects javascript:/data: at write time; this is defense-in-depth so a stored
// non-http scheme can never become a clickable href.
function safeHref(link: string): string | null {
  return /^https?:\/\//i.test(link) ? link : null;
}

export function ProcurementPanel({ makerspace, canChooseKind = false }: { makerspace: Makerspace; canChooseKind?: boolean }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Form>(emptyForm);
  const base = `/procurement/makerspace/${makerspace.id}/to-buy`;
  const queryKey = ["procurement", makerspace.id];
  const items = useStaffGet<ToBuyItem[]>(queryKey, `${base}?limit=200`);
  const invalidate = () => queryClient.invalidateQueries({ queryKey });

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
        }),
      });
    },
    onSuccess: () => {
      setForm(emptyForm);
      invalidate();
    },
  });

  const update = useMutation({
    mutationFn: (vars: { id: number; status: "pending" | "bought" }) =>
      staffRequest(`/procurement/to-buy/${vars.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: vars.status }),
      }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: number) => staffRequest(`/procurement/to-buy/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const exportCsv = useMutation({
    mutationFn: () => downloadStaffFile(`${base}/export`, `to-buy-${makerspace.slug}.csv`),
  });

  const rows = items.data ?? [];

  return (
    <Panel title="To Buy">
      <p className="mb-3 text-xs text-muted">
        Shopping list for {makerspace.name}. Add what to buy with quantity and a link, mark items bought, and export to CSV.
      </p>

      <form
        className="grid gap-2 sm:grid-cols-2 xl:grid-cols-6"
        onSubmit={(event) => {
          event.preventDefault();
          if (form.name.trim()) create.mutate();
        }}
      >
        <input className="desk-input xl:col-span-2" placeholder="Item name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className="desk-input" type="number" min={1} placeholder="Qty" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
        <input className="desk-input" placeholder="Link (optional)" value={form.link} onChange={(e) => setForm({ ...form, link: e.target.value })} />
        <input className="desk-input" type="number" min={0} step="0.01" placeholder="Est. unit cost" value={form.estimated_unit_cost} onChange={(e) => setForm({ ...form, estimated_unit_cost: e.target.value })} />
        {canChooseKind ? (
          <select className="desk-input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as Kind })}>
            <option value="hardware">Hardware</option>
            <option value="printing">Printing</option>
          </select>
        ) : (
          <button className="desk-button-primary" type="submit" disabled={create.isPending || !form.name.trim()}>
            Add
          </button>
        )}
        {canChooseKind ? (
          <button className="desk-button-primary xl:col-span-6" type="submit" disabled={create.isPending || !form.name.trim()}>
            Add item
          </button>
        ) : null}
      </form>
      {create.error ? <p className="mt-2 text-sm text-danger">{create.error instanceof Error ? create.error.message : "Could not add item."}</p> : null}
      {exportCsv.error ? <p className="mt-2 text-sm text-danger">{exportCsv.error instanceof Error ? exportCsv.error.message : "Could not export CSV."}</p> : null}

      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <button className="desk-button" type="button" disabled={exportCsv.isPending} onClick={() => exportCsv.mutate()}>
          Export CSV
        </button>
      </div>

      {items.isLoading ? (
        <p className="mt-3 text-sm text-muted">Loading...</p>
      ) : items.error ? (
        <p className="mt-3 text-sm text-danger">{items.error instanceof Error ? items.error.message : "Unable to load list."}</p>
      ) : !rows.length ? (
        <p className="mt-3 text-sm text-muted">Nothing on the list yet.</p>
      ) : (
        <div className="mt-3 max-h-[28rem] overflow-x-auto overflow-y-auto rounded-md border border-line">
          <table className="min-w-[760px] divide-y divide-line text-left text-sm">
            <thead className="sticky top-0 bg-surface text-xs uppercase tracking-wide text-muted">
              <tr>
                {["kind", "item", "qty", "link", "est. cost", "added by", "status", ""].map((header) => (
                  <th key={header} className="whitespace-nowrap px-3 py-2 font-semibold">{header}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-bg text-ink">
              {rows.map((item) => (
                <tr key={item.id}>
                  <td className="px-3 py-2 text-xs uppercase text-muted">{item.kind}</td>
                  <td className="px-3 py-2"><span className="block max-w-56 break-words">{item.name}</span></td>
                  <td className="px-3 py-2">{item.quantity}</td>
                  <td className="px-3 py-2">
                    {safeHref(item.link) ? (
                      <a className="text-accent-ink underline" href={safeHref(item.link)!} target="_blank" rel="noreferrer">link</a>
                    ) : item.link ? (
                      <span className="block max-w-56 break-all text-muted" title={item.link}>{item.link}</span>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td className="px-3 py-2">{item.estimated_unit_cost ?? "-"}</td>
                  <td className="px-3 py-2 text-muted"><span className="block max-w-40 break-words">{item.created_by_username ?? "-"}</span></td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      className={`rounded px-2 py-1 text-xs font-semibold ${item.status === "bought" ? "bg-accent text-on-accent" : "border border-line text-muted"}`}
                      onClick={() => update.mutate({ id: item.id, status: item.status === "bought" ? "pending" : "bought" })}
                    >
                      {item.status === "bought" ? "Bought" : "Pending"}
                    </button>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button type="button" className="desk-button" onClick={() => remove.mutate(item.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

