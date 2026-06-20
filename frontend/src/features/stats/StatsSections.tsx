import type {
  PublicStatsCurrentLoan,
  PublicStatsHardware,
  PublicStatsPrinting,
} from "./api";
import {
  BarChart,
  CompactList,
  Section,
  StatTile,
  formatDate,
  formatNumber,
} from "./StatsParts";

export function PrintingSection({ printing }: { printing: PublicStatsPrinting }) {
  const queueTotal =
    printing.jobs.queue.pending +
    printing.jobs.queue.accepted +
    printing.jobs.queue.printing;

  return (
    <Section title="Printing">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Print hours all time"
          value={formatNumber(printing.hours_all_time)}
        />
        <StatTile
          label="Print hours this month"
          value={formatNumber(printing.hours_this_month)}
          tone="accent"
        />
        <StatTile
          label="Filament used"
          value={`${formatNumber(printing.grams_all_time)} g`}
        />
        <StatTile label="Completed jobs" value={printing.jobs.completed} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-md border border-line bg-panel p-3">
          <h3 className="text-sm font-semibold text-ink">Busiest printer</h3>
          {printing.busiest_printer ? (
            <div className="mt-3 space-y-2 text-sm">
              <p className="text-xl font-bold text-ink">
                {printing.busiest_printer.name}
              </p>
              <p className="text-muted">
                {formatNumber(printing.busiest_printer.hours)} hours /{" "}
                {printing.busiest_printer.completed} completed
              </p>
            </div>
          ) : (
            <p className="mt-3 text-sm text-muted">No printer activity yet.</p>
          )}
        </div>

        <div className="rounded-md border border-line bg-panel p-3">
          <h3 className="text-sm font-semibold text-ink">Queue</h3>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="status-box status-box-active">
              {printing.jobs.queue.pending} pending
            </span>
            <span className="status-box">
              {printing.jobs.queue.accepted} accepted
            </span>
            <span className="status-box">
              {printing.jobs.queue.printing} printing
            </span>
            <span className="status-box">{queueTotal} active</span>
          </div>
        </div>

        <div className="rounded-md border border-line bg-panel p-3">
          <h3 className="text-sm font-semibold text-ink">By brand</h3>
          <CompactList
            empty="No filament records."
            rows={printing.by_brand.map((row) => ({
              label: row.brand,
              value: `${formatNumber(row.grams)} g`,
            }))}
          />
        </div>
      </div>

      <div className="rounded-md border border-line bg-panel p-3">
        <h3 className="mb-3 text-sm font-semibold text-ink">Filament trend</h3>
        <BarChart
          rows={printing.filament_trend.map((row) => ({
            label: row.period,
            value: row.grams,
          }))}
          valueLabel="g"
        />
      </div>
    </Section>
  );
}

export function HardwareSection({ hardware }: { hardware: PublicStatsHardware }) {
  return (
    <Section title="Hardware">
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile label="Public library" value={hardware.library.library_size} />
        <StatTile
          label="Available now"
          value={hardware.library.available_count}
          tone="accent"
        />
        <StatTile
          label="Currently out"
          value={hardware.library.currently_out_count}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-md border border-line bg-panel p-3">
          <h3 className="text-sm font-semibold text-ink">Most popular</h3>
          <CompactList
            empty="No lending history yet."
            rows={hardware.most_popular.map((row) => ({
              label: row.name,
              value: `${row.times_lent} loans / ${row.total_quantity_lent} total`,
            }))}
          />
        </div>
        <div className="rounded-md border border-line bg-panel p-3">
          <h3 className="text-sm font-semibold text-ink">Tools out</h3>
          <CompactList
            empty="No tools are out."
            rows={hardware.tools_out.map((row) => ({
              label: row.name,
              value: `${row.quantity_out} out`,
            }))}
          />
        </div>
        <div className="rounded-md border border-line bg-panel p-3">
          <h3 className="text-sm font-semibold text-ink">Recently added</h3>
          <CompactList
            empty="No new public gear this month."
            rows={hardware.recently_added.map((row) => ({
              label: row.name,
              value: formatDate(row.created_at),
            }))}
          />
        </div>
      </div>
    </Section>
  );
}

export function CurrentLoansSection({
  loans,
}: {
  loans: PublicStatsCurrentLoan[];
}) {
  return (
    <Section title="Currently out">
      {loans.length ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {loans.map((loan, index) => (
            <article
              className="rounded-md border border-line bg-panel p-3"
              key={`${loan.item_name}-${loan.holder_name}-${index}`}
            >
              <h3 className="truncate text-base font-semibold text-ink">
                {loan.item_name}
              </h3>
              <p className="mt-2 text-sm text-muted">
                With <span className="font-semibold text-ink">{loan.holder_name}</span>
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="status-box">
                  Due {loan.due ? formatDate(loan.due) : "not set"}
                </span>
                {loan.since ? (
                  <span className="status-box">Since {formatDate(loan.since)}</span>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted">No public tools are currently out.</p>
      )}
    </Section>
  );
}
