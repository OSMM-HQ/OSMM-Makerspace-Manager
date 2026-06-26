import { ImageThumbnail } from "../../../components/ui/ImageThumbnail";

type PrinterHoursRow = {
  printer_name: string;
  printer_model?: string;
  image_url?: string | null;
  completed_requests: number;
  hours: number;
  makerspace_id?: number;
};

type PrinterOutcomeRow = {
  printer_name: string;
  printer_model?: string;
  image_url?: string | null;
  completed: number;
  failed: number;
  grams_used: number;
  makerspace_id?: number;
};

export function PrinterHoursTable({
  rows,
  aggregate,
}: {
  rows: PrinterHoursRow[];
  aggregate: boolean;
}) {
  return (
    <PrinterTable
      aggregate={aggregate}
      headings={["Completed", "Hours"]}
      rows={rows.map((row) => ({
        makerspace_id: row.makerspace_id,
        name: row.printer_name,
        model: row.printer_model,
        image_url: row.image_url,
        values: [row.completed_requests, row.hours],
      }))}
    />
  );
}

export function PrinterOutcomesTable({
  rows,
  aggregate,
}: {
  rows: PrinterOutcomeRow[];
  aggregate: boolean;
}) {
  return (
    <PrinterTable
      aggregate={aggregate}
      headings={["Completed", "Failed", "Grams"]}
      rows={rows.map((row) => ({
        makerspace_id: row.makerspace_id,
        name: row.printer_name,
        model: row.printer_model,
        image_url: row.image_url,
        values: [row.completed, row.failed, row.grams_used],
      }))}
    />
  );
}

function PrinterTable({
  aggregate,
  headings,
  rows,
}: {
  aggregate: boolean;
  headings: string[];
  rows: {
    makerspace_id?: number;
    name: string;
    model?: string;
    image_url?: string | null;
    values: (number | string)[];
  }[];
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line bg-surface text-left text-muted">
            {aggregate ? <th className="px-3 py-2 font-semibold">Makerspace</th> : null}
            <th className="px-3 py-2 font-semibold">Image</th>
            <th className="px-3 py-2 font-semibold">Printer</th>
            {headings.map((heading) => (
              <th key={heading} className="px-3 py-2 text-right font-semibold">
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row, index) => (
              <tr key={`${row.name}-${index}`} className="border-b border-line last:border-b-0">
                {aggregate ? <td className="px-3 py-2 text-muted">{row.makerspace_id ?? ""}</td> : null}
                <td className="px-3 py-2">
                  <ImageThumbnail src={row.image_url} alt={row.name} className="h-10 w-10" />
                </td>
                <td className="px-3 py-2 text-ink">
                  {row.name}
                  {row.model ? <span className="block text-xs text-muted">{row.model}</span> : null}
                </td>
                {row.values.map((value, valueIndex) => (
                  <td key={valueIndex} className="px-3 py-2 text-right text-ink">
                    {value}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td className="px-3 py-3 text-sm text-muted" colSpan={headings.length + (aggregate ? 3 : 2)}>
                No printer rows.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
