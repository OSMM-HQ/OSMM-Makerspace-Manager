import type React from "react";

type ChartRow = { label: string; value: number };

export function StatTile({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number | string;
  tone?: "default" | "accent";
}) {
  const valueClass = tone === "accent" ? "text-accent" : "text-ink";

  return (
    <div className="rounded-md border border-line bg-surface p-3">
      <p className={`text-2xl font-bold ${valueClass}`}>{value}</p>
      <p className="mt-1 text-xs text-muted">{label}</p>
    </div>
  );
}

export function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="desk-panel overflow-hidden">
      <div className="border-b border-line bg-surface px-4 py-3">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
      </div>
      <div className="space-y-4 p-4">{children}</div>
    </section>
  );
}

export function CompactList({
  rows,
  empty,
}: {
  rows: { label: string; value: string }[];
  empty: string;
}) {
  if (!rows.length) {
    return <p className="mt-3 text-sm text-muted">{empty}</p>;
  }

  return (
    <ul className="mt-3 space-y-2 text-sm">
      {rows.map((row) => (
        <li className="flex min-w-0 items-start gap-3" key={`${row.label}-${row.value}`}>
          <span className="min-w-0 flex-1 truncate text-ink" title={row.label}>
            {row.label}
          </span>
          <span className="shrink-0 text-right text-xs text-muted">{row.value}</span>
        </li>
      ))}
    </ul>
  );
}

export function BarChart({
  rows,
  valueLabel,
}: {
  rows: ChartRow[];
  valueLabel: string;
}) {
  const maxValue = Math.max(...rows.map((row) => row.value), 0);
  if (!rows.length || maxValue <= 0) {
    return <p className="text-sm text-muted">No chart data.</p>;
  }

  return (
    <div className="space-y-2">
      {rows.map((row) => {
        const width = `${Math.max((row.value / maxValue) * 100, 4)}%`;
        return (
          <div
            className="grid grid-cols-[minmax(0,1fr)_minmax(4rem,2fr)_auto] items-center gap-2 text-sm sm:grid-cols-[minmax(7rem,11rem)_1fr_auto]"
            key={row.label}
          >
            <span className="truncate text-ink" title={row.label}>
              {row.label}
            </span>
            <div className="h-3 overflow-hidden rounded bg-bg">
              <div className="h-full rounded bg-accent" style={{ width }} />
            </div>
            <span className="min-w-14 text-right text-xs text-muted">
              {formatNumber(row.value)} {valueLabel}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function formatNumber(value: number) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value);
}

export function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
