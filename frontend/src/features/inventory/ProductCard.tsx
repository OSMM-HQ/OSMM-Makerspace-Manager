import { Link } from "react-router-dom";

import type { Availability, Product } from "../../types/inventory";

type ProductCardProps = {
  product: Product;
  detailPath: string;
  quantity: number;
  onDecrement: () => void;
  onIncrement: () => void;
};

function isUnavailable(product: Product): boolean {
  return product.availability?.label === "Unavailable";
}

function statusChip(availability: Availability): { text: string; cls: string } | null {
  if (availability === null) {
    return null;
  }
  const label = availability.label ?? "Available";
  const count =
    availability.mode === "exact_count" && availability.count != null
      ? availability.count
      : null;

  if (label === "Unavailable") {
    return { text: "Unavailable", cls: "chip" };
  }
  if (label === "Limited") {
    return { text: count != null ? `Limited (${count})` : "Limited", cls: "chip chip-active" };
  }
  return {
    text: count != null ? `Available (${count})` : "Available",
    cls: "chip chip-available",
  };
}

export function ProductCard({
  product,
  detailPath,
  quantity,
  onDecrement,
  onIncrement,
}: ProductCardProps) {
  const disabled = isUnavailable(product);
  const chip = statusChip(product.availability);
  const idLabel = `ID: ${String(product.id).padStart(4, "0")}`;

  return (
    <article className="group flex h-full flex-col rounded-xl border border-line bg-panel shadow-soft transition-transform duration-150 hover:-translate-y-0.5 hover:shadow-soft-lg">
      {/* Image header — blueprint placeholder when no photo on file. */}
      <div className="relative h-44 overflow-hidden rounded-t-xl border-b border-line bg-surface">
        {product.image_url ? (
          <img
            src={product.image_url}
            alt={product.name}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="blueprint-bg grid h-full w-full place-items-center">
            <span className="font-display text-4xl font-bold uppercase text-ink/15">
              {product.name.slice(0, 2)}
            </span>
          </div>
        )}
        {chip ? (
          <span className={`absolute right-2 top-2 max-w-[calc(100%-1rem)] ${chip.cls}`}>{chip.text}</span>
        ) : null}
      </div>

      {/* Body */}
      <div className="flex flex-1 flex-col p-4">
        <h2 className="break-words font-display text-lg font-semibold leading-tight text-ink">
          {product.name}
        </h2>
        <p className="mt-1 font-mono text-xs uppercase text-muted">{idLabel}</p>
        <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted">
          {product.description || "No description provided."}
        </p>
        {product.category_name ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="chip">{product.category_name}</span>
          </div>
        ) : null}

        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-4">
          <div className="flex items-center rounded-lg border border-line bg-bg">
            <button
              aria-label={`Remove ${product.name}`}
                className="h-9 w-9 font-mono text-lg font-semibold text-ink transition hover:bg-surface hover:text-ink disabled:cursor-not-allowed disabled:text-muted"
              disabled={quantity === 0}
              type="button"
              onClick={onDecrement}
            >
              -
            </button>
            <span className="grid h-9 min-w-10 place-items-center border-x border-line px-2 font-mono text-sm font-semibold text-ink">
              {quantity}
            </span>
            <button
              aria-label={`Add ${product.name}`}
                className="h-9 w-9 font-mono text-lg font-semibold text-ink transition hover:bg-surface hover:text-ink disabled:cursor-not-allowed disabled:text-muted"
              disabled={disabled}
              type="button"
              onClick={onIncrement}
            >
              +
            </button>
          </div>
          <Link
            className="min-w-0 break-words font-mono text-xs font-semibold tracking-tight text-secondary-ink underline-offset-4 hover:underline"
            to={detailPath}
          >
            Details &rarr;
          </Link>
        </div>
      </div>
    </article>
  );
}
