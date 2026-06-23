import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { staffRequest } from "../../../lib/api";
import { Panel, type Makerspace, useStaffGet } from "./shared";
import { invalidateInventoryViews } from "../queryInvalidation";

type StocktakeRow = { id: number; status: string; notes: string };
type StocktakeLine = {
  id: number;
  product: number | null;
  asset: number | null;
  expected_quantity: number;
  counted_quantity: number;
  variance_quantity: number;
  condition: string;
};
type StocktakeDetail = StocktakeRow & { lines: StocktakeLine[] };
type ProductOption = { id: number; name: string };

const CONDITIONS = ["available", "damaged", "lost", "unknown"];

export function StocktakePanel({ makerspace, isSuperadmin = false }: { makerspace: Makerspace; isSuperadmin?: boolean }) {
  const queryClient = useQueryClient();
  const [openId, setOpenId] = useState<number | null>(null);
  const stocktakes = useStaffGet<{ results: StocktakeRow[] }>(["stocktakes", makerspace.id], `/admin/makerspace/${makerspace.id}/stocktakes`);
  const create = useMutation({
    mutationFn: () =>
      staffRequest(`/admin/makerspace/${makerspace.id}/stocktakes`, { method: "POST", body: JSON.stringify({ notes: "Cycle count" }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["stocktakes", makerspace.id] }),
  });
  const action = useMutation({
    mutationFn: (path: string) => staffRequest(path, { method: "POST", body: JSON.stringify({}) }),
    onSuccess: (_data, path) => {
      queryClient.invalidateQueries({ queryKey: ["stocktakes", makerspace.id] });
      if (path.endsWith("/apply-adjustments")) {
        invalidateInventoryViews(queryClient, makerspace.id);
        queryClient.invalidateQueries({ queryKey: ["needs-fix-shelf", makerspace.id] });
      }
    },
  });
  const createError = create.error instanceof Error ? create.error.message : undefined;
  const actionError = action.error instanceof Error ? action.error.message : undefined;

  return (
    <Panel title="Stocktake">
      <button disabled={create.isPending} onClick={() => create.mutate()}>
        {create.isPending ? "Starting..." : "Start stocktake"}
      </button>
      {createError ? <p className="mt-2 text-sm text-danger">{createError}</p> : null}
      {actionError ? <p className="mt-2 text-sm text-danger">{actionError}</p> : null}
      <div className="mt-3 grid gap-2">
        {stocktakes.data?.results?.map((row) => (
          <div key={row.id} className="rounded-md border border-line bg-surface p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <strong>#{row.id}</strong>
              <span className="rounded-md border border-line bg-bg px-2 py-0.5 text-xs text-muted">{row.status}</span>
              {canCount(row.status) ? (
                <button type="button" onClick={() => setOpenId((id) => (id === row.id ? null : row.id))}>{openId === row.id ? "Hide counts" : "Count items"}</button>
              ) : null}
              {row.status === "counting" ? (
                <button type="button" disabled={action.isPending} onClick={() => action.mutate(`/admin/stocktakes/${row.id}/complete`)}>Complete</button>
              ) : null}
              {isSuperadmin && row.status === "completed" ? (
                <button type="button" disabled={action.isPending} onClick={() => action.mutate(`/admin/stocktakes/${row.id}/approve`)}>Approve</button>
              ) : null}
              {isSuperadmin && row.status === "approved" ? (
                <button type="button" disabled={action.isPending} onClick={() => action.mutate(`/admin/stocktakes/${row.id}/apply-adjustments`)}>Apply</button>
              ) : null}
            </div>
            <p className="mt-1 text-muted">{row.notes}</p>
            {openId === row.id ? <CountSection makerspace={makerspace} stocktakeId={row.id} /> : null}
          </div>
        ))}
      </div>
    </Panel>
  );
}

// The count step is what moves a stocktake forward and produces the variance the Apply
// step adjusts on - without it a stocktake has zero lines and Apply is a no-op. Records
// a counted quantity per product, then shows expected/counted/variance from the detail.
function CountSection({ makerspace, stocktakeId }: { makerspace: Makerspace; stocktakeId: number }) {
  const queryClient = useQueryClient();
  const [productId, setProductId] = useState("");
  const [counted, setCounted] = useState("0");
  const [condition, setCondition] = useState("available");
  const detail = useStaffGet<StocktakeDetail>(["stocktake-detail", stocktakeId], `/admin/stocktakes/${stocktakeId}`);
  const products = useStaffGet<{ results: ProductOption[] }>(["inventory-all", makerspace.id], `/admin/makerspace/${makerspace.id}/inventory?page_size=1000`);
  const productName = (id: number | null) => products.data?.results.find((product) => product.id === id)?.name ?? (id ? `#${id}` : "-");

  const record = useMutation({
    mutationFn: () =>
      staffRequest(`/admin/stocktakes/${stocktakeId}/count-lines`, {
        method: "POST",
        body: JSON.stringify({ product_id: Number(productId), counted_quantity: Number(counted) || 0, condition }),
      }),
    onSuccess: () => {
      setProductId("");
      setCounted("0");
      queryClient.invalidateQueries({ queryKey: ["stocktake-detail", stocktakeId] });
      queryClient.invalidateQueries({ queryKey: ["stocktakes", makerspace.id] });
    },
  });
  const recordError = record.error instanceof Error ? record.error.message : undefined;
  const lines = detail.data?.lines ?? [];

  return (
    <div className="mt-3 rounded-md border border-line bg-bg p-3">
      <div className="grid gap-2 md:grid-cols-[1fr_120px_140px_auto] md:items-end">
        <label className="grid gap-1 text-xs text-muted">
          <span>Product</span>
          <select className="desk-input" value={productId} disabled={products.isLoading} onChange={(event) => setProductId(event.target.value)}>
            <option value="">Select product</option>
            {products.data?.results.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs text-muted">
          <span>Counted</span>
          <input className="desk-input" type="number" min="0" value={counted} onChange={(event) => setCounted(event.target.value)} />
        </label>
        <label className="grid gap-1 text-xs text-muted">
          <span>Condition</span>
          <select className="desk-input" value={condition} onChange={(event) => setCondition(event.target.value)}>
            {CONDITIONS.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <button disabled={!productId || record.isPending} onClick={() => record.mutate()}>{record.isPending ? "Saving..." : "Record count"}</button>
      </div>
      {recordError ? <p className="mt-2 text-sm text-danger">{recordError}</p> : null}
      <div className="mt-3 grid min-w-0 gap-1">
        {lines.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-[560px] text-left text-xs">
              <thead className="text-muted">
                <tr><th className="py-1">Product</th><th>Expected</th><th>Counted</th><th>Variance</th><th>Condition</th></tr>
              </thead>
              <tbody>
                {lines.map((line) => (
                  <tr key={line.id} className="border-t border-line">
                    <td className="py-1"><span className="block max-w-48 break-words">{productName(line.product)}</span></td>
                    <td>{line.expected_quantity}</td>
                    <td>{line.counted_quantity}</td>
                    <td className={line.variance_quantity === 0 ? "text-muted" : "text-danger"}>{line.variance_quantity}</td>
                    <td>{line.condition}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="text-xs text-muted">No counts recorded yet.</p>}
      </div>
    </div>
  );
}

function canCount(status: string) {
  return status === "draft" || status === "counting";
}

