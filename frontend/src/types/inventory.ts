export type Availability =
  | null
  | {
      mode: "status_only" | "exact_count";
      label?: "Available" | "Limited" | "Unavailable";
      count?: number;
    };

export type Product = {
  id: number;
  name: string;
  description: string;
  tracking_mode?: "quantity" | "individual";
  availability: Availability;
};

export type Makerspace = {
  name: string;
  public_code: string;
  slug: string;
  location: string;
};

export type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type RequestCartItem = {
  productId: number;
  name: string;
  quantity: number;
};

export type CheckinVerifyResponse = {
  username: string;
};

export type RequestSubmitResponse = {
  public_token: string;
  status: string;
};

export type PublicRequestStatus = {
  public_token?: string;
  requested_for?: string;
  status: string;
  rejection_reason: string;
  created_at: string;
  items: {
    product_name: string;
    requested_quantity: number;
  }[];
};

export type PublicToolLoan = {
  public_token: string;
  status: string;
  target_type: string;
  target_label: string;
  items: {
    product_name: string;
    quantity: number;
  }[];
};
