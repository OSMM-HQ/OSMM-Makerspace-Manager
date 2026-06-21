import { Link, Navigate, Route, Routes } from "react-router-dom";

import { MakerspaceBrand } from "./components/MakerspaceBrand";
import { MakerspaceMapLink } from "./components/MakerspaceMapLink";
import { ThemeToggle } from "./components/ThemeToggle";
import { Card } from "./components/ui/Card";
import { Spinner } from "./components/ui/Spinner";
import { PublicInventoryPage } from "./features/inventory/PublicInventoryPage";
import { PublicItemDetailPage } from "./features/inventory/PublicItemDetailPage";
import { PublicSelfCheckoutPage } from "./features/inventory/PublicSelfCheckoutPage";
import { usePublicMakerspaces } from "./features/inventory/usePublicInventory";
import { PublicPrintRequestPage } from "./features/printing/PublicPrintRequestPage";
import { KioskPage, ScannerPage, SuperadminPage } from "./features/staff/PlatformApps";
import { ResetPasswordPage } from "./features/staff/ResetPasswordPage";
import { StaffApp } from "./features/staff/StaffApp";
import { PublicStatsPage } from "./features/stats/PublicStatsPage";
import { useTenant } from "./lib/tenant";

function LandingPage() {
  const makerspacesQuery = usePublicMakerspaces();
  const onlyMakerspace = makerspacesQuery.data?.length === 1 ? makerspacesQuery.data[0] : null;

  if (onlyMakerspace) {
    return <Navigate replace to={`/m/${onlyMakerspace.slug}`} />;
  }

  return (
    <main className="desk-shell">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-md bg-accent text-sm font-black text-on-accent">
              MM
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">Makerspace Manager</p>
              <p className="text-xs text-muted">Shared equipment portal</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ThemeToggle />
            <Link className="desk-button" to="/admin">
              Staff login
            </Link>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-5 py-8 lg:grid-cols-[280px_minmax(0,1fr)]">
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

        <div className="min-w-0 space-y-4">
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
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
            {makerspacesQuery.data.map((makerspace) => (
              <article
                key={makerspace.slug}
                className="group relative flex flex-col border-2 border-ink bg-panel transition-transform duration-150 hover:-translate-y-1 hover:shadow-brutal"
              >
                <div className="relative h-40 overflow-hidden border-b-2 border-secondary bg-surface">
                  {makerspace.cover_image_url ? (
                    <img
                      src={makerspace.cover_image_url}
                      alt={`${makerspace.name} cover`}
                      loading="lazy"
                      className="h-full w-full object-cover grayscale transition-all duration-500 group-hover:grayscale-0"
                    />
                  ) : (
                    <div className="blueprint-bg h-full w-full" />
                  )}
                  <span className="absolute left-3 top-3 chip chip-available">
                    <span className="h-2 w-2 rounded-full bg-bg" /> Public
                  </span>
                </div>
                <div className="flex min-w-0 flex-1 flex-col p-card-padding p-5">
                  <MakerspaceBrand
                    name={makerspace.name}
                    logoUrl={makerspace.logo_url}
                    size="md"
                  />
                  <MakerspaceMapLink
                    makerspace={makerspace}
                    className="relative z-10 mt-2"
                    locationClassName="break-words font-mono text-xs uppercase text-muted"
                  />
                  <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-5">
                    <span className="min-w-0 truncate font-mono text-xs uppercase text-muted">
                      {makerspace.public_code}
                    </span>
                    <Link
                      className="inline-flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-tight text-secondary hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 after:absolute after:inset-0 after:content-['']"
                      to={`/m/${makerspace.slug}`}
                      aria-label={`Open ${makerspace.name} catalog`}
                    >
                      Open catalog &rarr;
                    </Link>
                  </div>
                </div>
              </article>
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
  const tenant = useTenant();

  if (tenant.mode === "single" && tenant.loading) {
    return (
      <main className="desk-shell grid place-items-center px-5">
        <div className="desk-panel w-full max-w-md p-6 text-sm font-semibold text-muted">
          Loading site...
        </div>
      </main>
    );
  }

  if (tenant.mode === "single" && tenant.error) {
    return (
      <main className="desk-shell grid place-items-center px-5">
        <div className="desk-panel w-full max-w-md p-6">
          <h1 className="text-xl font-bold text-ink">Site unavailable</h1>
          <p className="mt-2 text-sm text-muted">
            The configured tenant could not be resolved.
          </p>
        </div>
      </main>
    );
  }

  if (tenant.mode === "single") {
    return (
      <Routes>
        <Route path="/" element={<PublicInventoryPage />} />
        <Route path="/items/:id" element={<PublicItemDetailPage />} />
        <Route path="/checkout" element={<PublicSelfCheckoutPage />} />
        <Route path="/print" element={<PublicPrintRequestPage />} />
        <Route path="/stats" element={<PublicStatsPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/admin" element={<StaffApp />} />
        <Route path="/guest-admin" element={<StaffApp guestOnly />} />
        <Route path="/scanner" element={<ScannerPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/m/:slug" element={<PublicInventoryPage />} />
      <Route path="/m/:slug/items/:id" element={<PublicItemDetailPage />} />
      <Route path="/m/:slug/checkout" element={<PublicSelfCheckoutPage />} />
      <Route path="/m/:slug/print" element={<PublicPrintRequestPage />} />
      <Route path="/m/:slug/stats" element={<PublicStatsPage />} />
      <Route path="/kiosk/:slug" element={<KioskPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/admin" element={<StaffApp />} />
      <Route path="/guest-admin" element={<StaffApp guestOnly />} />
      <Route path="/scanner" element={<ScannerPage />} />
      <Route path="/superadmin" element={<SuperadminPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
