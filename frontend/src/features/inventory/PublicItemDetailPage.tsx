import { Link, useParams } from "react-router-dom";

import { ThemeToggle } from "../../components/ThemeToggle";
import { Card } from "../../components/ui/Card";
import { Spinner } from "../../components/ui/Spinner";
import { AvailabilityBadge } from "./AvailabilityBadge";
import { usePublicInventoryDetail, useTenantBootstrap } from "./usePublicInventory";

export function PublicItemDetailPage() {
  const { slug, id } = useParams();
  const makerspaceSlug = slug ?? "";
  const itemId = Number(id ?? 0);
  const bootstrap = useTenantBootstrap(makerspaceSlug);
  const item = usePublicInventoryDetail(makerspaceSlug, itemId);
  const displayName =
    bootstrap.data?.branding.display_name ||
    bootstrap.data?.makerspace.name ||
    makerspaceSlug;

  return (
    <main className="desk-shell">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">
              {displayName}
            </p>
            <h1 className="text-2xl font-bold text-ink">Item detail</h1>
          </div>
          <div className="flex gap-2">
            <ThemeToggle />
            <Link className="desk-button" to={`/m/${makerspaceSlug}`}>
              Catalog
            </Link>
          </div>
        </div>
      </header>
      <section className="mx-auto max-w-5xl px-5 py-6">
        {item.isLoading ? (
          <div className="grid min-h-64 place-items-center">
            <Spinner />
          </div>
        ) : null}
        {item.isError ? (
          <Card>
            <h2 className="text-xl font-semibold text-ink">Item unavailable</h2>
            <p className="mt-2 text-sm text-muted">
              This item may no longer be public.
            </p>
          </Card>
        ) : null}
        {item.data ? (
          <Card>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-3xl font-bold text-ink">{item.data.name}</h2>
                <p className="mt-2 text-sm text-muted">
                  {item.data.tracking_mode === "individual"
                    ? "Serialized item"
                    : item.data.tracking_mode === "quantity"
                      ? "Quantity-tracked item"
                      : "Public catalog item"}
                </p>
              </div>
              <AvailabilityBadge availability={item.data.availability} />
            </div>
            <p className="mt-6 whitespace-pre-wrap text-sm leading-6 text-ink">
              {item.data.description || "No description provided."}
            </p>
          </Card>
        ) : null}
      </section>
    </main>
  );
}
