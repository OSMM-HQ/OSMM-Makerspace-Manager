export const focusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function focusFirstDialogElement(panel: HTMLElement) {
  const target = panel.querySelector<HTMLElement>(focusableSelector) ?? panel;
  target.focus();
}

export function trapDialogFocus(event: KeyboardEvent, panel: HTMLElement) {
  if (event.key !== "Tab") return;
  const items = Array.from(panel.querySelectorAll<HTMLElement>(focusableSelector))
    .filter((item) => !item.hasAttribute("disabled") && item.offsetParent !== null);
  if (!items.length) {
    event.preventDefault();
    panel.focus();
    return;
  }
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
