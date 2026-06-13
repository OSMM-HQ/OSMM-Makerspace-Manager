import { apiGet, publicV1Request } from "../../lib/api";
import type {
  CheckinVerifyResponse,
  Makerspace,
  PaginatedResponse,
  Product,
  PublicToolLoan,
  PublicRequestStatus,
  RequestSubmitResponse,
} from "../../types/inventory";

export const publicMakerspacesKey = ["public-makerspaces"] as const;

export const publicInventoryKey = (slug: string, page: number, query: string) =>
  ["public-inventory", slug, page, query] as const;
export const publicInventoryDetailKey = (slug: string, id: number) =>
  ["public-inventory-detail", slug, id] as const;

export async function fetchPublicMakerspaces(): Promise<Makerspace[]> {
  return apiGet<Makerspace[]>("/public/makerspaces/");
}

export async function fetchPublicInventory(
  slug: string,
  page: number,
  query: string,
): Promise<PaginatedResponse<Product>> {
  const params = new URLSearchParams();
  if (page > 1) {
    params.set("page", String(page));
  }
  if (query.trim()) {
    params.set("q", query.trim());
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
  return publicV1Request<CheckinVerifyResponse>(
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
    identifier: string;
    contact_email: string;
    contact_phone: string;
    requested_for: string;
    items: { product_id: number; quantity: number }[];
  },
): Promise<RequestSubmitResponse> {
  return publicV1Request<RequestSubmitResponse>(`/public/${slug}/requests`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
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
  return publicV1Request<PublicRequestStatus[]>(
    `/public/${slug}/requests/status`,
    {
      method: "POST",
      body: JSON.stringify({ identifier }),
    },
  );
}

export async function publicToolCheckout(
  slug: string,
  payload: { identifier: string; payload: string },
): Promise<PublicToolLoan> {
  return publicV1Request<PublicToolLoan>(`/public/${slug}/tools/checkout`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function publicToolReturn(
  slug: string,
  payload: { identifier: string; payload: string },
): Promise<PublicToolLoan> {
  return publicV1Request<PublicToolLoan>(`/public/${slug}/tools/return`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
