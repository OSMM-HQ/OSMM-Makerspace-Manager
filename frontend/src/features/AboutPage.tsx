import { Link } from "react-router-dom";

import { OsmmLogo } from "../components/OsmmLogo";
import { SiteFooter } from "../components/SiteFooter";
import { ThemeToggle } from "../components/ThemeToggle";

export function AboutPage() {
  return (
    <main className="desk-shell flex min-h-screen flex-col">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-4">
          <Link className="flex min-w-0 items-center gap-3" to="/">
            <OsmmLogo className="shrink-0 text-ink" size={36} />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">OSMM</p>
              <p className="text-xs text-muted">Shared equipment portal</p>
            </div>
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <ThemeToggle />
            <Link className="desk-button" to="/admin">
              Staff login
            </Link>
          </div>
        </div>
      </header>

      <section className="mx-auto w-full max-w-3xl flex-1 px-5 py-10">
        <p className="text-xs font-semibold tracking-wide text-accent-ink">About</p>
        <h1 className="mt-3 text-3xl font-bold text-ink">
          Open Source Makerspace Manager
        </h1>
        <div className="mt-5 space-y-4 text-sm leading-6 text-muted">
          <p>
            OSMM is an open-source platform for running community makerspaces &mdash;
            public equipment catalogs, hardware lending with traceable handovers,
            3D-print request queues, and multi-makerspace operations in one place.
          </p>
          <p>
            Each makerspace controls its own inventory, branding, staff, and
            notifications. Visitors browse catalogs and request equipment; staff
            handle approvals, issue and return with evidence, and reporting.
          </p>
        </div>

        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          <Link className="desk-panel p-4 transition hover:border-accent" to="/">
            <p className="text-sm font-semibold text-ink">Browse makerspaces &rarr;</p>
            <p className="mt-1 text-xs text-muted">View public equipment catalogs.</p>
          </Link>
          <Link className="desk-panel p-4 transition hover:border-accent" to="/admin">
            <p className="text-sm font-semibold text-ink">Staff login &rarr;</p>
            <p className="mt-1 text-xs text-muted">Manage your makerspace.</p>
          </Link>
        </div>
      </section>

      <SiteFooter />
    </main>
  );
}
