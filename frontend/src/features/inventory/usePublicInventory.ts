import { useQuery } from "@tanstack/react-query";

import { bootstrapTenant } from "../../lib/api";
import {
  fetchPublicInventory,
  fetchPublicInventoryDetail,
  fetchPublicMakerspaces,
  publicInventoryDetailKey,
  publicInventoryKey,
  publicMakerspacesKey,
} from "./api";

export function usePublicMakerspaces() {
  return useQuery({
    queryKey: publicMakerspacesKey,
    queryFn: fetchPublicMakerspaces,
  });
}

export function usePublicInventory(slug: string, page: number, query: string) {
  return useQuery({
    queryKey: publicInventoryKey(slug, page, query),
    queryFn: () => fetchPublicInventory(slug, page, query),
    placeholderData: (previousData) => previousData,
  });
}

export function useTenantBootstrap(slug: string) {
  return useQuery({
    queryKey: ["tenant-bootstrap", slug],
    queryFn: () => bootstrapTenant({ slug }),
    enabled: Boolean(slug),
  });
}

export function usePublicInventoryDetail(slug: string, id: number) {
  return useQuery({
    queryKey: publicInventoryDetailKey(slug, id),
    queryFn: () => fetchPublicInventoryDetail(slug, id),
    enabled: Boolean(slug && id),
  });
}
