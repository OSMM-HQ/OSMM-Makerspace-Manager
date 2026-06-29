type PaginationProps = {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
  /** Total row count, shown as context when provided. */
  count?: number;
  pageSize?: number;
  disabled?: boolean;
};

/**
 * Shared prev/next pager for server-paginated staff lists. Renders nothing when
 * everything fits on one page. Pairs with `usePaginatedQuery`.
 */
export function Pagination({ page, totalPages, onChange, count, pageSize, disabled }: PaginationProps) {
  if (totalPages <= 1) {
    return null;
  }

  const rangeLabel =
    count != null && pageSize != null
      ? `${Math.min((page - 1) * pageSize + 1, count)}–${Math.min(page * pageSize, count)} of ${count}`
      : null;

  return (
    <div className="flex flex-wrap items-center justify-end gap-2 text-sm text-muted">
      {rangeLabel ? <span className="mr-auto">{rangeLabel}</span> : null}
      <button
        className="desk-button"
        type="button"
        disabled={disabled || page <= 1}
        onClick={() => onChange(Math.max(1, page - 1))}
      >
        Previous
      </button>
      <span>
        Page {page} of {totalPages}
      </span>
      <button
        className="desk-button"
        type="button"
        disabled={disabled || page >= totalPages}
        onClick={() => onChange(Math.min(totalPages, page + 1))}
      >
        Next
      </button>
    </div>
  );
}
