import { Card } from "../../components/ui/Card";
import type { Product } from "../../types/inventory";
import { AvailabilityBadge } from "./AvailabilityBadge";
import { Link } from "react-router-dom";

type ProductCardProps = {
  product: Product;
  makerspaceSlug: string;
  quantity: number;
  onDecrement: () => void;
  onIncrement: () => void;
};

function isUnavailable(product: Product): boolean {
  return product.availability?.label === "Unavailable";
}

export function ProductCard({
  product,
  makerspaceSlug,
  quantity,
  onDecrement,
  onIncrement,
}: ProductCardProps) {
  const disabled = isUnavailable(product);

  return (
    <Card className="flex h-full flex-col gap-4 transition hover:border-accent/40">
      <div className="flex flex-1 flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold leading-6 text-ink">
            {product.name}
          </h2>
          <AvailabilityBadge availability={product.availability} />
        </div>
        <p className="line-clamp-3 text-sm leading-6 text-muted">
          {product.description || "No description provided."}
        </p>
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-line pt-3">
        <div className="flex items-center rounded-md border border-line bg-bg">
          <button
            aria-label={`Remove ${product.name}`}
            className="h-9 w-9 text-lg font-semibold text-ink transition hover:bg-line disabled:cursor-not-allowed disabled:text-muted"
            disabled={quantity === 0}
            type="button"
            onClick={onDecrement}
          >
            -
          </button>
          <span className="grid h-9 min-w-10 place-items-center border-x border-line px-3 text-sm font-semibold text-ink">
            {quantity}
          </span>
          <button
            aria-label={`Add ${product.name}`}
            className="h-9 w-9 text-lg font-semibold text-ink transition hover:bg-line disabled:cursor-not-allowed disabled:text-muted"
            disabled={disabled}
            type="button"
            onClick={onIncrement}
          >
            +
          </button>
        </div>
        <span className="text-xs font-medium text-muted">
          {disabled ? "Not requestable" : quantity > 0 ? "Selected" : "Add to request"}
        </span>
      </div>
      <Link className="text-sm font-semibold text-accent" to={`/m/${makerspaceSlug}/items/${product.id}`}>
        Details
      </Link>
    </Card>
  );
}
