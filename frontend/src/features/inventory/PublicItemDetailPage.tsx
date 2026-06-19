import { Link, useParams } from "react-router-dom";

import { MakerspaceBrand } from "../../components/MakerspaceBrand";
import { ThemeToggle } from "../../components/ThemeToggle";
import { Card } from "../../components/ui/Card";
import { Spinner } from "../../components/ui/Spinner";
import { useTenant, useTenantPath } from "../../lib/tenant";
import { AvailabilityBadge } from "./AvailabilityBadge";
import { usePublicInventoryDetail, useTenantBootstrap } from "./usePublicInventory";

export function PublicItemDetailPage() {
  const { slug, id } = useParams();
  const tenant = useTenant();
  const makerspaceSlug = tenant.mode === "single" ? tenant.slug : slug ?? "";
  const tenantPath = useTenantPath(makerspaceSlug);
  const itemId = Number(id ?? 0);
  const bootstrap = useTenantBootstrap(makerspaceSlug, tenant.mode === "central");
  const item = usePublicInventoryDetail(makerspaceSlug, itemId);
  const bootstrapData = tenant.mode === "single" ? tenant.bootstrap : bootstrap.data;
  const displayName =
    bootstrapData?.branding.display_name ||
    bootstrapData?.makerspace.name ||
    makerspaceSlug;

  return (
    <main className="desk-shell">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div className="min-w-0">
            <MakerspaceBrand
              name={displayName}
              logoUrl={bootstrapData?.makerspace.logo_url}
              size="md"
            />
            <h1 className="mt-1 text-2xl font-bold text-ink">Item detail</h1>
          </div>
          <div className="flex gap-2">
            <ThemeToggle />
            <Link className="desk-button" to={tenantPath()}>
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
          <div className="grid gap-6 md:grid-cols-2">
            {/* Image hero */}
            <div className="border-2 border-ink bg-panel">
              <div className="relative aspect-square overflow-hidden border-b-2 border-secondary bg-surface">
                {item.data.image_url ? (
                  <img
                    src={item.data.image_url}
                    alt={item.data.name}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="blueprint-bg grid h-full w-full place-items-center">
                    <span className="font-display text-6xl font-bold uppercase text-ink/15">
                      {item.data.name.slice(0, 2)}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Spec manifest */}
            <div className="flex flex-col border-2 border-ink bg-panel p-6 shadow-brutal-sm">
              <div className="flex items-start justify-between gap-3">
                <h2 className="font-display text-3xl font-bold uppercase leading-tight text-ink">
                  {item.data.name}
                </h2>
                <AvailabilityBadge availability={item.data.availability} />
              </div>
              <p className="mt-2 font-mono text-xs uppercase text-muted">
                ID: {String(item.data.id).padStart(4, "0")}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="chip">
                  {item.data.tracking_mode === "individual"
                    ? "Serialized"
                    : item.data.tracking_mode === "quantity"
                      ? "Quantity-tracked"
                      : "Catalog item"}
                </span>
                {item.data.category_name ? (
                  <span className="chip">{item.data.category_name}</span>
                ) : null}
              </div>
              <h3 className="mt-6 border-b border-line pb-1 font-mono text-xs uppercase text-muted">
                Description
              </h3>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-ink">
                {item.data.description || "No description provided."}
              </p>
            </div>
          </div>
        ) : null}
      </section>
    </main>
  );
}
