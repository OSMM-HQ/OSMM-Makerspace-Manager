import type { ReactNode } from "react";
import { useId } from "react";

type FilterBarProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  searchLabel?: string;
  children?: ReactNode;
  actions?: ReactNode;
};

export function FilterBar({
  value,
  onChange,
  placeholder = "Search",
  searchLabel = "Search table",
  children,
  actions,
}: FilterBarProps) {
  const searchId = useId();

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-line bg-panel p-3 sm:flex-row sm:items-center">
      <label className="sr-only" htmlFor={searchId}>
        {searchLabel}
      </label>
      <input
        id={searchId}
        className="desk-input min-w-0 flex-1"
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
      {actions ? <div className="flex flex-wrap items-center gap-2 sm:ml-auto">{actions}</div> : null}
    </div>
  );
}
