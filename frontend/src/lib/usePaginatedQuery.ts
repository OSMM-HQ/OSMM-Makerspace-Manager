import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { staffRequest } from "./api";

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

type Options = {
  /** Stable query-key prefix; page/pageSize/search are appended automatically. */
  key: unknown[];
  /** Base staff API path. May already contain a `?query` (we pick the right separator). */
  path: string;
  pageSize?: number;
  enabled?: boolean;
  /** Optional server-side `?search` term. Changing it resets to page 1. */
  search?: string;
  /**
   * When this string changes (e.g. the selected makerspace id, a status tab),
   * the view resets to page 1 so a filter switch never leaves you on a now-empty
   * high page number.
   */
  resetKey?: string;
};

/**
 * Server-paginated list query for the staff console. Wraps the existing
 * `{count,next,previous,results}` DRF shape (PageNumberPagination) and keeps the
 * previous page's data on screen during a page change (placeholderData) so the
 * table doesn't flash empty. Mirrors the hand-rolled pattern in Ledger/Warranty,
 * extracted so every operational queue gets the same behavior.
 */
export function usePaginatedQuery<T>(options: Options) {
  const { key, path, pageSize = 24, enabled = true, search = "", resetKey = "" } = options;
  const [page, setPage] = useState(1);
  const trimmedSearch = search.trim();

  useEffect(() => {
    setPage(1);
  }, [trimmedSearch, resetKey]);

  const separator = path.includes("?") ? "&" : "?";
  let url = `${path}${separator}page=${page}&page_size=${pageSize}`;
  if (trimmedSearch) {
    url += `&search=${encodeURIComponent(trimmedSearch)}`;
  }

  const query = useQuery({
    queryKey: [...key, page, pageSize, trimmedSearch],
    queryFn: () => staffRequest<Paginated<T>>(url),
    enabled,
    placeholderData: keepPreviousData,
  });

  const count = query.data?.count ?? 0;
  const totalPages = Math.max(1, Math.ceil(count / pageSize));

  return {
    ...query,
    page,
    setPage,
    totalPages,
    count,
    pageSize,
    results: query.data?.results ?? [],
  };
}
