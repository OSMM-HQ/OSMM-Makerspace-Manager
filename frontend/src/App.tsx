import { Link, Navigate, Route, Routes } from "react-router-dom";

import { ThemeToggle } from "./components/ThemeToggle";
import { Card } from "./components/ui/Card";
import { Spinner } from "./components/ui/Spinner";
import { PublicInventoryPage } from "./features/inventory/PublicInventoryPage";
import { PublicItemDetailPage } from "./features/inventory/PublicItemDetailPage";
import { PublicSelfCheckoutPage } from "./features/inventory/PublicSelfCheckoutPage";
import { usePublicMakerspaces } from "./features/inventory/usePublicInventory";
import { PublicPrintRequestPage } from "./features/printing/PublicPrintRequestPage";
import { KioskPage, ScannerPage, SuperadminPage } from "./features/staff/PlatformApps";
import { StaffApp } from "./features/staff/StaffApp";

function LandingPage() {
  const makerspacesQuery = usePublicMakerspaces();
  const onlyMakerspace = makerspacesQuery.data?.length === 1 ? makerspacesQuery.data[0] : null;

  if (onlyMakerspace) {
    return <Navigate replace to={`/m/${onlyMakerspace.slug}`} />;
  }

  return (
    <main className="desk-shell">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-md bg-accent text-sm font-black text-bg">
              MM
            </span>
            <div>
              <p className="text-sm font-semibold text-ink">Makerspace Manager</p>
              <p className="text-xs text-muted">Shared equipment portal</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link className="desk-button" to="/admin">
              Staff login
            </Link>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-6 px-5 py-8 lg:grid-cols-[280px_1fr]">
        <aside className="desk-panel h-fit p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">
            Inventory Directory
          </p>
          <h1 className="mt-3 text-3xl font-bold text-ink">Makerspaces</h1>
          <p className="mt-3 text-sm leading-6 text-muted">
            Browse public catalogs across connected workshops, labs, and community spaces.
          </p>
          <div className="mt-6 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-md border border-line bg-surface p-3">
              <p className="text-2xl font-bold text-ink">
                {makerspacesQuery.data?.length ?? "-"}
              </p>
              <p className="text-xs text-muted">Public spaces</p>
            </div>
            <div className="rounded-md border border-line bg-surface p-3">
              <p className="text-2xl font-bold text-accent">Live</p>
              <p className="text-xs text-muted">Status access</p>
            </div>
          </div>
        </aside>

        <div className="space-y-4">
          <div className="desk-panel flex flex-wrap items-center justify-between gap-3 p-4">
            <div>
              <h2 className="text-lg font-semibold text-ink">Available public catalogs</h2>
              <p className="text-sm text-muted">Select a makerspace to view shared equipment.</p>
            </div>
            <span className="rounded-md border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">
              Standard public portal
            </span>
          </div>

        {makerspacesQuery.isLoading ? (
          <div className="grid min-h-32 place-items-center desk-panel">
            <Spinner />
          </div>
        ) : null}

        {makerspacesQuery.isError ? (
          <Card>
            <h2 className="text-xl font-semibold text-ink">
              Makerspaces are unavailable
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              The public makerspace directory could not be loaded.
            </p>
          </Card>
        ) : null}

        {makerspacesQuery.data && makerspacesQuery.data.length === 0 ? (
          <Card>
            <h2 className="text-xl font-semibold text-ink">
              No public makerspaces yet
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              Public inventory appears here after a makerspace is enabled.
            </p>
          </Card>
        ) : null}

        {makerspacesQuery.data && makerspacesQuery.data.length > 0 ? (
          <div className="grid gap-3">
            {makerspacesQuery.data.map((makerspace) => (
              <Link
                key={makerspace.slug}
                className="desk-panel group flex items-center justify-between gap-4 p-4 transition hover:border-accent/50 hover:bg-surface focus:outline-none focus:ring-2 focus:ring-accent/30"
                to={`/m/${makerspace.slug}`}
              >
                <div>
                  <h2 className="text-base font-semibold text-ink">
                    {makerspace.name}
                  </h2>
                  <p className="mt-1 text-sm text-muted">
                    {makerspace.location || makerspace.slug}
                  </p>
                </div>
                <p className="text-sm font-semibold text-accent group-hover:text-accent/90">
                  Open
                </p>
              </Link>
            ))}
          </div>
        ) : null}
        </div>
      </section>
    </main>
  );
}

function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-bg px-6">
      <div className="text-center">
        <p className="text-sm font-semibold uppercase tracking-wide text-muted">
          404
        </p>
        <h1 className="mt-2 text-3xl font-bold text-ink">Page not found</h1>
      </div>
    </main>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/m/:slug" element={<PublicInventoryPage />} />
      <Route path="/m/:slug/items/:id" element={<PublicItemDetailPage />} />
      <Route path="/m/:slug/checkout" element={<PublicSelfCheckoutPage />} />
      <Route path="/m/:slug/print" element={<PublicPrintRequestPage />} />
      <Route path="/kiosk/:slug" element={<KioskPage />} />
      <Route path="/admin" element={<StaffApp />} />
      <Route path="/guest-admin" element={<StaffApp guestOnly />} />
      <Route path="/scanner" element={<ScannerPage />} />
      <Route path="/superadmin" element={<SuperadminPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
