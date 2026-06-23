import { tenantPublicRequest } from "../../lib/api";

export type PublicToolLoanResult = {
  public_token: string;
  status: string;
  items: { product_name: string; quantity: number }[];
};

export function checkoutTool(
  slug: string,
  body: {
    payload: string;
    requester_name: string;
    contact_email: string;
    contact_phone: string;
  },
) {
  return tenantPublicRequest<PublicToolLoanResult>(
    slug,
    `/public/${slug}/tools/checkout`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function returnTool(slug: string, identifier: string, payload: string) {
  return tenantPublicRequest<PublicToolLoanResult>(
    slug,
    `/public/${slug}/tools/return`,
    {
      method: "POST",
      body: JSON.stringify({ identifier, payload }),
    },
  );
}

