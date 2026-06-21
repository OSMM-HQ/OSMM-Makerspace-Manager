import type { ReactNode } from "react";
import { useEffect } from "react";

type DetailDrawerProps = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
};

export function DetailDrawer({ open, title, onClose, children }: DetailDrawerProps) {
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  return (
    <div
      aria-hidden={!open}
      className={`fixed inset-0 z-50 transition ${open ? "pointer-events-auto" : "pointer-events-none"}`}
    >
      <button
        type="button"
        aria-label="Close detail drawer"
        className={`absolute inset-0 bg-ink/30 transition-opacity ${open ? "opacity-100" : "opacity-0"}`}
        onClick={onClose}
      />
      <aside
        aria-modal="true"
        role="dialog"
        aria-labelledby="detail-drawer-title"
        className={`absolute right-0 top-0 flex h-full w-full max-w-xl flex-col border-l border-line bg-panel shadow-xl transition-transform duration-200 ${open ? "translate-x-0" : "translate-x-full"}`}
      >
        <header className="flex items-center gap-3 border-b border-line px-4 py-3">
          <h2 id="detail-drawer-title" className="text-sm font-semibold tracking-wide text-muted">
            {title}
          </h2>
          <button type="button" className="desk-button ml-auto" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </aside>
    </div>
  );
}
