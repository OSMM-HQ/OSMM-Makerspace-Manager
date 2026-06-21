import { useMemo, useState } from "react";

import { Skeleton, SkeletonRows } from "../../../components/ui";
import { useDebouncedValue } from "../../../lib/useDebouncedValue";
import { Panel, type Makerspace, useStaffGet } from "./shared";

type LedgerSource = "request" | "self_checkout" | "direct_handout";

type LedgerRow = {
  source: LedgerSource;
  item_name: string;
  container: string | null;
  units: Array<{ asset_tag: string; serial_number: string }>;
  target_label: string | null;
  holder: string;
  quantity: number;
  since: string | null;
  due: string | null;
  makerspace_id: number;
  reference_id: number;
  status: string;
};

type LedgerResponse = {
  count: number;
  results: LedgerRow[];
};

type SortKey = "item_name" | "holder" | "quantity" | "since" | "due" | "source" | "makerspace_id";
type SortDirection = "asc" | "desc";

const sourceLabels: Record<LedgerSource, string> = {
  request: "Request",
  self_checkout: "Self-checkout",
  direct_handout: "Direct",
};

export function Ledger({ makerspace, isSuperadmin }: { makerspace: Makerspace; isSuperadmin: boolean }) {
  const [allMakerspaces, setAllMakerspaces] = useState(false);
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({
    key: "due",
    direction: "asc",
  });
  const debouncedFilter = useDebouncedValue(filter);
  const aggregate = isSuperadmin && allMakerspaces;
  const ledger = useStaffGet<LedgerResponse>(
    ["ledger", aggregate ? "all" : makerspace.id],
    aggregate ? "/admin/ledger" : `/admin/makerspace/${makerspace.id}/ledger`,
  );

  const rows = ledger.data?.results ?? [];
  const now = Date.now();
  const visibleRows = useMemo(() => {
    const normalizedFilter = debouncedFilter.trim().toLowerCase();
    const filtered = normalizedFilter
      ? rows.filter((row) => `${row.holder} ${row.item_name}`.toLowerCase().includes(normalizedFilter))
      : rows;

    return [...filtered].sort((a, b) => compareRows(a, b, sort.key, sort.direction));
  }, [debouncedFilter, rows, sort.direction, sort.key]);
  const itemCount = visibleRows.reduce((total, row) => total + row.quantity, 0);

  const setSortKey = (key: SortKey) => {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
  };

  return (
    <Panel title="Ledger">
      <div className="grid gap-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-lg font-semibold text-ink">{itemCount} items out</p>
            <p className="text-sm text-muted">
              {aggregate ? "Across all makerspaces" : makerspace.name}
              {ledger.data ? ` - ${ledger.data.count} records` : ""}
            </p>
          </div>
          {isSuperadmin ? (
            <label className="inline-flex items-center gap-2 text-sm font-medium text-ink">
              <input
                type="checkbox"
                checked={allMakerspaces}
                onChange={(event) => setAllMakerspaces(event.target.checked)}
              />
              All makerspaces
            </label>
          ) : null}
        </div>

        <input
          className="desk-input"
          placeholder="Filter by holder or item"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />

        {ledger.isLoading ? <LedgerSkeleton aggregate={aggregate} /> : null}
        {ledger.error ? <p className="text-sm text-danger">{ledger.error.message}</p> : null}
        {!ledger.isLoading && !ledger.error && !visibleRows.length ? (
          <p className="rounded-md border border-line bg-surface p-3 text-sm text-muted">No items are currently out.</p>
        ) : null}

        {visibleRows.length ? (
          <div className="overflow-x-auto rounded-md border border-line">
            <table className="min-w-[760px] divide-y divide-line text-left text-sm">
              <thead className="bg-bg text-xs font-semibold uppercase text-muted">
                <tr>
                  <SortableHeader label="Item" sortKey="item_name" sort={sort} onSort={setSortKey} />
                  <SortableHeader label="Holder" sortKey="holder" sort={sort} onSort={setSortKey} />
                  <SortableHeader label="Qty" sortKey="quantity" sort={sort} onSort={setSortKey} align="right" />
                  <SortableHeader label="Out since" sortKey="since" sort={sort} onSort={setSortKey} />
                  <SortableHeader label="Due" sortKey="due" sort={sort} onSort={setSortKey} />
                  <SortableHeader label="Source" sortKey="source" sort={sort} onSort={setSortKey} />
                  {aggregate ? <SortableHeader label="Makerspace" sortKey="makerspace_id" sort={sort} onSort={setSortKey} /> : null}
                </tr>
              </thead>
              <tbody className="divide-y divide-line bg-surface">
                {visibleRows.map((row) => {
                  const overdue = isOverdue(row.due, now);
                  return (
                    <tr key={`${row.source}-${row.reference_id}-${row.makerspace_id}-${row.item_name}`} className={overdue ? "bg-danger/10" : ""}>
                      <td className="px-3 py-2 align-top">
                        <div className="max-w-56 break-words font-medium text-ink">{row.item_name}</div>
                        {row.container ? <div className="mt-0.5 break-words text-xs text-muted">Box: {row.container}</div> : null}
                        <UnitLines row={row} />
                      </td>
                      <td className="px-3 py-2 align-top text-ink"><span className="block max-w-48 break-words">{row.holder}</span></td>
                      <td className="whitespace-nowrap px-3 py-2 text-right font-semibold text-ink">{row.quantity}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-muted">{formatDate(row.since)}</td>
                      <td className={`whitespace-nowrap px-3 py-2 ${overdue ? "font-semibold text-danger" : "text-muted"}`}>
                        <span className="inline-flex items-center gap-2">
                          {formatDate(row.due)}
                          {overdue ? <span className="status-box status-box-danger">Overdue</span> : null}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2">
                        <span className="rounded-md border border-line bg-bg px-2 py-0.5 text-xs font-medium text-muted">
                          {sourceLabels[row.source]}
                        </span>
                      </td>
                      {aggregate ? <td className="whitespace-nowrap px-3 py-2 text-muted">#{row.makerspace_id}</td> : null}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

function LedgerSkeleton({ aggregate }: { aggregate: boolean }) {
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="min-w-[760px] divide-y divide-line text-left text-sm" aria-hidden="true">
        <thead className="bg-bg text-xs font-semibold uppercase text-muted">
          <tr>
            {["Item", "Holder", "Qty", "Out since", "Due", "Source", aggregate ? "Makerspace" : ""]
              .filter(Boolean)
              .map((label) => (
                <th key={label} className="whitespace-nowrap px-3 py-2">
                  <Skeleton className="h-3 w-20" />
                </th>
              ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line bg-surface">
          <SkeletonRows rows={4} cols={aggregate ? 7 : 6} />
        </tbody>
      </table>
    </div>
  );
}

function UnitLines({ row }: { row: LedgerRow }) {
  if (row.units.length) {
    return (
      <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-muted">
        {row.units.map((unit) => (
          <span className="break-words" key={`${unit.asset_tag}-${unit.serial_number || "no-serial"}`}>
            #{unit.asset_tag}
            {unit.serial_number ? ` · ${unit.serial_number}` : ""}
          </span>
        ))}
      </div>
    );
  }

  return row.target_label ? <div className="mt-0.5 break-words text-xs text-muted">{row.target_label}</div> : null;
}

function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
  align = "left",
}: {
  label: string;
  sortKey: SortKey;
  sort: { key: SortKey; direction: SortDirection };
  onSort: (key: SortKey) => void;
  align?: "left" | "right";
}) {
  const active = sort.key === sortKey;
  return (
    <th className={`whitespace-nowrap px-3 py-2 ${align === "right" ? "text-right" : "text-left"}`}>
      <button
        type="button"
        className={`inline-flex items-center gap-1 hover:text-accent ${align === "right" ? "justify-end" : ""}`}
        onClick={() => onSort(sortKey)}
      >
        {label}
        <span className="text-[10px]">{active ? (sort.direction === "asc" ? "^" : "v") : "-"}</span>
      </button>
    </th>
  );
}

function compareRows(a: LedgerRow, b: LedgerRow, key: SortKey, direction: SortDirection) {
  const directionMultiplier = direction === "asc" ? 1 : -1;
  const left = sortableValue(a, key);
  const right = sortableValue(b, key);

  if (typeof left === "number" && typeof right === "number") {
    return (left - right) * directionMultiplier;
  }

  return String(left).localeCompare(String(right)) * directionMultiplier;
}

function sortableValue(row: LedgerRow, key: SortKey) {
  if (key === "since" || key === "due") {
    return row[key] ? new Date(row[key]).getTime() : Number.MAX_SAFE_INTEGER;
  }
  if (key === "source") return sourceLabels[row.source];
  return row[key];
}

function isOverdue(value: string | null, now: number) {
  return Boolean(value && new Date(value).getTime() < now);
}

function formatDate(value: string | null) {
  if (!value) return "\u2014";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "\u2014";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
