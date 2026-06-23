import { apiGet, publicV1Request, tenantPublicRequest } from "../../lib/api";
import type {
  CheckinVerifyResponse,
  Makerspace,
  PaginatedResponse,
  Product,
  PublicCategory,
  PublicToolLoan,
  PublicRequestStatus,
  RequestSubmitResponse,
} from "../../types/inventory";

export const publicMakerspacesKey = ["public-makerspaces"] as const;

export const publicCategoriesKey = (slug: string) =>
  ["public-categories", slug] as const;
export const publicInventoryKey = (
  slug: string,
  page: number,
  query: string,
  category?: string,
  sort?: string,
) =>
  [
    "public-inventory",
    slug,
    page,
    query,
    category ?? "",
    sort ?? "name",
  ] as const;
export const publicInventoryDetailKey = (slug: string, id: number) =>
  ["public-inventory-detail", slug, id] as const;

export async function fetchPublicMakerspaces(): Promise<Makerspace[]> {
  return apiGet<Makerspace[]>("/public/makerspaces/");
}

export async function fetchPublicCategories(
  slug: string,
): Promise<PublicCategory[]> {
  return apiGet<PublicCategory[]>(`/public/${slug}/inventory/categories/`);
}

export async function fetchPublicInventory(
  slug: string,
  page: number,
  query: string,
  category?: string,
  sort?: string,
): Promise<PaginatedResponse<Product>> {
  const params = new URLSearchParams();
  if (page > 1) {
    params.set("page", String(page));
  }
  if (query.trim()) {
    params.set("q", query.trim());
  }
  if (category) {
    params.set("category", category);
  }
  if (sort && sort !== "name") {
    params.set("sort", sort);
  }

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiGet<PaginatedResponse<Product>>(
    `/public/${slug}/inventory/${suffix}`,
  );
}

export async function fetchPublicInventoryDetail(
  slug: string,
  id: number,
): Promise<Product> {
  return apiGet<Product>(`/public/${slug}/inventory/${id}/`);
}

export async function verifyCheckin(
  slug: string,
  identifier: string,
): Promise<CheckinVerifyResponse> {
  return tenantPublicRequest<CheckinVerifyResponse>(
    slug,
    `/public/${slug}/checkin/verify`,
    {
      method: "POST",
      body: JSON.stringify({ identifier }),
    },
  );
}

export async function submitPublicRequest(
  slug: string,
  payload: {
    requester_name: string;
    contact_email: string;
    contact_phone: string;
    requested_for: string;
    items: { product_id: number; quantity: number }[];
  },
): Promise<RequestSubmitResponse> {
  return tenantPublicRequest<RequestSubmitResponse>(
    slug,
    `/public/${slug}/requests`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function fetchRequestStatus(
  publicToken: string,
): Promise<PublicRequestStatus> {
  return publicV1Request<PublicRequestStatus>(
    `/public/requests/${publicToken}/status`,
  );
}

export async function fetchRequestsByIdentifier(
  slug: string,
  identifier: string,
): Promise<PublicRequestStatus[]> {
  return tenantPublicRequest<PublicRequestStatus[]>(
    slug,
    `/public/${slug}/requests/status`,
    {
      method: "POST",
      body: JSON.stringify({ identifier }),
    },
  );
}

export async function publicToolCheckout(
  slug: string,
  payload: {
    payload: string;
    requester_name: string;
    contact_email: string;
    contact_phone: string;
    evidence_id: number;
    remark?: string;
  },
): Promise<PublicToolLoan> {
  return tenantPublicRequest<PublicToolLoan>(
    slug,
    `/public/${slug}/tools/checkout`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function publicToolReturn(
  slug: string,
  payload: { identifier: string; payload: string; evidence_id: number; remark: string },
): Promise<PublicToolLoan> {
  return tenantPublicRequest<PublicToolLoan>(
    slug,
    `/public/${slug}/tools/return`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

