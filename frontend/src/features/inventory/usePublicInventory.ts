import { useQuery } from "@tanstack/react-query";

import { bootstrapTenant } from "../../lib/api";
import {
  fetchPublicCategories,
  fetchPublicInventory,
  fetchPublicMakerspaces,
  publicCategoriesKey,
  publicInventoryKey,
  publicMakerspacesKey,
} from "./api";

export function usePublicMakerspaces() {
  return useQuery({
    queryKey: publicMakerspacesKey,
    queryFn: fetchPublicMakerspaces,
  });
}

export function usePublicInventory(
  slug: string,
  page: number,
  query: string,
  category = "",
  sort = "name",
  enabled = true,
) {
  return useQuery({
    queryKey: publicInventoryKey(slug, page, query, category, sort),
    queryFn: () => fetchPublicInventory(slug, page, query, category, sort),
    enabled: enabled && Boolean(slug),
    placeholderData: (previousData) => previousData,
  });
}

export function usePublicCategories(slug: string) {
  return useQuery({
    queryKey: publicCategoriesKey(slug),
    queryFn: () => fetchPublicCategories(slug),
    enabled: Boolean(slug),
  });
}

export function useTenantBootstrap(slug: string, enabled = true) {
  return useQuery({
    queryKey: ["tenant-bootstrap", slug],
    queryFn: () => bootstrapTenant({ slug }),
    enabled: enabled && Boolean(slug),
  });
}
