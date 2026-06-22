import { Link } from "react-router-dom";

// Shared public footer: copyright + a link out to the in-app About page.
export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="mt-auto border-t border-line bg-panel">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-5 text-xs text-muted">
        <p>
          &copy; {year} OSMM &mdash; Open Source Makerspace Manager
        </p>
        <nav className="flex items-center gap-4">
          <Link className="hover:text-ink" to="/about">
            About
          </Link>
        </nav>
      </div>
    </footer>
  );
}
