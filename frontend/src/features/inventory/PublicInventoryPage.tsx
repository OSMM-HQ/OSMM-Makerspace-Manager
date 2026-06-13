import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ThemeToggle } from "../../components/ThemeToggle";
import { Card } from "../../components/ui/Card";
import { Spinner } from "../../components/ui/Spinner";
import type { Product, RequestCartItem } from "../../types/inventory";
import { ProductCard } from "./ProductCard";
import { PublicRequestPanel } from "./PublicRequestPanel";
import { usePublicInventory, useTenantBootstrap } from "./usePublicInventory";

const PAGE_SIZE = 24;

function formatSlug(slug: string): string {
  return slug
    .split("-")
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function LoadingState() {
  return (
    <div className="grid min-h-64 place-items-center">
      <Spinner />
    </div>
  );
}

function EmptyState({ query }: { query: string }) {
  return (
    <Card className="mx-auto max-w-lg text-center">
      <h2 className="text-xl font-semibold text-ink">
        {query ? "No matching items." : "No public items yet."}
      </h2>
      <p className="mt-2 text-sm leading-6 text-muted">
        {query
          ? "Try a different search term or clear the search field."
          : "This makerspace has not shared any inventory items publicly."}
      </p>
    </Card>
  );
}

function ErrorState({ error }: { error: Error }) {
  return (
    <Card className="mx-auto max-w-lg text-center">
      <h2 className="text-xl font-semibold text-ink">{error.message}</h2>
      <p className="mt-2 text-sm leading-6 text-muted">
        This makerspace may not exist or its public inventory is disabled.
      </p>
    </Card>
  );
}

export function PublicInventoryPage() {
  const { slug } = useParams();
  const makerspaceSlug = slug ?? "";
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [cart, setCart] = useState<Record<number, RequestCartItem>>({});
  const bootstrapQuery = useTenantBootstrap(makerspaceSlug);
  const inventoryQuery = usePublicInventory(makerspaceSlug, page, query);
  const displayName =
    bootstrapQuery.data?.branding.display_name ||
    bootstrapQuery.data?.makerspace.name ||
    formatSlug(makerspaceSlug) ||
    "Makerspace";
  const title = `${displayName} Inventory`;
  const modules = new Set(bootstrapQuery.data?.modules ?? []);
  const requestEnabled = modules.has("request_workflow");
  const products = inventoryQuery.data?.results ?? [];
  const pageCount = Math.max(
    1,
    Math.ceil((inventoryQuery.data?.count ?? 0) / PAGE_SIZE),
  );
  const selectedItems = useMemo(() => Object.values(cart), [cart]);

  function maxQuantity(product: Product): number {
    if (
      product.availability?.mode === "exact_count" &&
      typeof product.availability.count === "number"
    ) {
      return product.availability.count;
    }

    return 99;
  }

  function incrementItem(product: Product) {
    if (product.availability?.label === "Unavailable") {
      return;
    }

    setCart((current) => {
      const existing = current[product.id];
      const quantity = Math.min((existing?.quantity ?? 0) + 1, maxQuantity(product));
      return {
        ...current,
        [product.id]: {
          productId: product.id,
          name: product.name,
          quantity,
        },
      };
    });
  }

  function decrementItem(product: Product) {
    setCart((current) => {
      const existing = current[product.id];
      if (!existing || existing.quantity <= 1) {
        const next = { ...current };
        delete next[product.id];
        return next;
      }

      return {
        ...current,
        [product.id]: {
          ...existing,
          quantity: existing.quantity - 1,
        },
      };
    });
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery(searchInput.trim());
    setPage(1);
  }

  return (
    <main className="desk-shell">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-6 sm:px-8">
          <p className="text-sm font-semibold uppercase tracking-wide text-accent">
            Public Inventory
          </p>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-3xl font-bold text-ink sm:text-4xl">{title}</h1>
              <p className="mt-2 text-sm text-muted">
                Shared tools and equipment published by this makerspace.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-muted">
                {inventoryQuery.data?.count ?? "-"} listed items
              </div>
              <ThemeToggle />
              <Link className="desk-button" to="/admin">
                Staff login
              </Link>
            </div>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-5 px-5 py-6 lg:grid-cols-[1fr_360px] sm:px-8">
        <div className="space-y-4">
          <Card>
            <form
              className="flex flex-col gap-3 sm:flex-row"
              onSubmit={submitSearch}
            >
              <input
                className="desk-input min-w-0 flex-1"
                placeholder="Search tools, machines, kits, or materials"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
              />
              <button className="desk-button-primary" type="submit">
                Search
              </button>
              {query ? (
                <button
                  className="desk-button"
                  type="button"
                  onClick={() => {
                    setSearchInput("");
                    setQuery("");
                    setPage(1);
                  }}
                >
                  Clear
                </button>
              ) : null}
            </form>
          </Card>

          {inventoryQuery.isLoading ? <LoadingState /> : null}

          {inventoryQuery.isError ? (
            <ErrorState error={inventoryQuery.error} />
          ) : null}

          {inventoryQuery.data && products.length === 0 ? (
            <EmptyState query={query} />
          ) : null}

          {products.length > 0 ? (
            <>
              <div className="grid gap-3 md:grid-cols-2">
                {products.map((product) => (
                  <ProductCard
                    key={product.id}
                    makerspaceSlug={makerspaceSlug}
                    product={product}
                    quantity={cart[product.id]?.quantity ?? 0}
                    onDecrement={() => decrementItem(product)}
                    onIncrement={() => incrementItem(product)}
                  />
                ))}
              </div>
              <div className="desk-panel flex flex-wrap items-center justify-between gap-3 p-3">
                <p className="text-sm text-muted">
                  Page {page} of {pageCount}
                  {inventoryQuery.isFetching ? " loading..." : ""}
                </p>
                <div className="flex gap-2">
                  <button
                    className="desk-button"
                    disabled={!inventoryQuery.data?.previous || page === 1}
                    type="button"
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                  >
                    Previous
                  </button>
                  <button
                    className="desk-button"
                    disabled={!inventoryQuery.data?.next}
                    type="button"
                    onClick={() =>
                      setPage((current) => Math.min(pageCount, current + 1))
                    }
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          ) : null}
        </div>

        <PublicRequestPanel
          items={selectedItems}
          makerspaceSlug={makerspaceSlug}
          onClear={() => setCart({})}
          disabled={!requestEnabled}
        />
      </section>
    </main>
  );
}
