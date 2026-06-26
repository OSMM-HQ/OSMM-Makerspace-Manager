import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../../lib/api";

export type PublicStatsResponse = {
  printing: PublicStatsPrinting | null;
  hardware: PublicStatsHardware;
  current_loans: PublicStatsCurrentLoan[];
};

export type PublicStatsPrinting = {
  hours_all_time: number;
  hours_this_month: number;
  busiest_printer: {
    name: string;
    model: string;
    hours: number;
    completed: number;
    image_url?: string | null;
  } | null;
  per_printer: {
    name: string;
    model: string;
    jobs: number;
    hours: number;
    grams: number;
    image_url?: string | null;
  }[];
  grams_all_time: number;
  by_brand: { brand: string; grams: number }[];
  jobs: {
    completed: number;
    status_counts: {
      pending: number;
      accepted: number;
      printing: number;
      completed: number;
      collected: number;
      failed: number;
      rejected: number;
    };
    queue: {
      pending: number;
      accepted: number;
      printing: number;
    };
  };
  filament_trend: { period: string; grams: number }[];
};

export type PublicStatsHardware = {
  most_popular: {
    name: string;
    times_lent: number;
    total_quantity_lent: number;
  }[];
  tools_out: { name: string; quantity_out: number }[];
  library: {
    currently_out_count: number;
    library_size: number;
    available_count: number;
  };
  recently_added: { name: string; created_at: string }[];
};

export type PublicStatsCurrentLoan = {
  item_name: string;
  holder_name: string;
  due: string | null;
  since: string | null;
};

export const publicStatsKey = (slug: string) => ["public-stats", slug] as const;

export async function fetchPublicStats(
  slug: string,
): Promise<PublicStatsResponse> {
  return apiGet<PublicStatsResponse>(`/public/${slug}/stats/`);
}

export function usePublicStats(slug: string) {
  return useQuery({
    queryKey: publicStatsKey(slug),
    queryFn: () => fetchPublicStats(slug),
    enabled: Boolean(slug),
  });
}
