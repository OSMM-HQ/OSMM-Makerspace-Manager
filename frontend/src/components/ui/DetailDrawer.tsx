import type { ReactNode } from "react";
import { useEffect, useId, useRef } from "react";
import { focusFirstDialogElement, trapDialogFocus } from "./dialogFocus";

type DetailDrawerProps = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
};

export function DetailDrawer({ open, title, onClose, children }: DetailDrawerProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);
  // See Modal.tsx: onClose lives in a ref so this focus effect depends only on `open`.
  // Otherwise a fresh inline onClose each render re-runs the effect and steals focus.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panel = panelRef.current;
    if (panel) focusFirstDialogElement(panel);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
      if (panel) trapDialogFocus(event, panel);
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Close detail drawer"
        className="absolute inset-0 bg-ink/30"
        onClick={onClose}
      />
      <aside
        aria-modal="true"
        role="dialog"
        aria-labelledby={titleId}
        ref={panelRef}
        tabIndex={-1}
        className="absolute right-0 top-0 flex h-full w-full max-w-xl flex-col border-l border-line bg-panel shadow-xl outline-none"
      >
        <header className="flex items-center gap-3 border-b border-line px-4 py-3">
          <h2 id={titleId} className="text-sm font-semibold tracking-wide text-muted">
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
