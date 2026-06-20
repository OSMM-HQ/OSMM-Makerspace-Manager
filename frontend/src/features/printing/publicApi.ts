import { publicV1Request, tenantPublicRequest } from "../../lib/api";

export type PrintBucket = {
  id: number;
  name: string;
  description: string;
};

export type PublicFilamentSpool = {
  id: number;
  material: string;
  color: string;
  remaining_weight_grams: string;
};

export type PrintStatus = {
  public_token: string;
  status: string;
  title: string;
  created_at: string;
  accepted_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  estimated_minutes: number;
  queue_position: number | null;
  queue_approved_ahead: number | null;
  queue_awaiting_review_ahead: number | null;
};

export type PrintUploadBody = {
  identifier: string;
  kind: "stl" | "screenshot";
  filename: string;
  content_type: string;
};

export type PrintUpload = {
  url: string;
  fields: Record<string, string>;
  method?: string;
  headers?: Record<string, string>;
};

export type PrintRequestPayload = {
  website?: string;
  identifier: string;
  bucket_id?: number;
  requester_name?: string;
  title: string;
  description?: string;
  project_brief?: string;
  preferred_settings?: string;
  material?: string;
  color?: string;
  filament_spool_id?: number | null;
  quantity: number;
  source_link?: string;
  contact_email?: string;
  contact_phone?: string;
  file_ids: number[];
};

export function fetchPrintBuckets(slug: string) {
  return tenantPublicRequest<PrintBucket[]>(
    slug,
    `/printing/public/${slug}/buckets`,
  );
}

export function fetchPublicSpools(slug: string) {
  return tenantPublicRequest<PublicFilamentSpool[]>(
    slug,
    `/printing/public/${slug}/spools`,
  );
}

export function verifyPrintCheckin(slug: string, identifier: string) {
  return tenantPublicRequest<{ username: string }>(
    slug,
    `/printing/public/${slug}/checkin/verify`,
    { method: "POST", body: JSON.stringify({ identifier }) },
  );
}

export function presignPrintUpload(slug: string, body: PrintUploadBody) {
  return tenantPublicRequest<{ file_id: number; upload: PrintUpload }>(
    slug,
    `/printing/public/${slug}/uploads`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function uploadToStorage(upload: PrintUpload, file: File) {
  if (upload.method === "PUT") {
    const res = await fetch(upload.url, {
      method: "PUT",
      body: file,
      headers: upload.headers,
    });
    if (!res.ok) throw new Error(`Upload failed (${res.status})`);
    return;
  }

  const formData = new FormData();
  for (const [key, value] of Object.entries(upload.fields)) {
    formData.append(key, value);
  }
  formData.append("file", file);

  const res = await fetch(upload.url, { method: "POST", body: formData });
  if (!res.ok) {
    throw new Error(`Upload failed (${res.status})`);
  }
}

export function submitPrintRequest(slug: string, payload: PrintRequestPayload) {
  return tenantPublicRequest<{ public_token: string; status: string }>(
    slug,
    `/printing/public/${slug}/requests`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function fetchPrintStatus(publicToken: string) {
  return publicV1Request<PrintStatus>(
    `/printing/public/requests/${publicToken}/status`,
  );
}

export function fetchPrintStatusByEmail(slug: string, email: string) {
  return tenantPublicRequest<{ results: PrintStatus[] }>(
    slug,
    `/printing/public/${slug}/status-by-email`,
    { method: "POST", body: JSON.stringify({ email }) },
  );
}
