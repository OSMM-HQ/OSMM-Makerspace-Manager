import { staffRequest } from "../../lib/api";

export type WarrantyStatus = "unknown" | "active" | "expiring_soon" | "expired";
export type WarrantyHostKind = "asset" | "printer";

export type WarrantyDocument = {
  id: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type Warranty = {
  id: number;
  host_kind: WarrantyHostKind;
  host_id: number;
  host_label: string;
  asset_id: number | null;
  asset_tag: string | null;
  serial_number: string | null;
  printer_id: number | null;
  printer_name: string | null;
  printer_model: string | null;
  purchased_on: string | null;
  warranty_expires_on: string | null;
  vendor_name: string;
  vendor_contact: string;
  status: WarrantyStatus;
  documents: WarrantyDocument[];
};

export type WarrantyReportRow = {
  host_kind: WarrantyHostKind;
  host_id: number;
  host_label: string;
  serial_number: string | null;
  vendor_name: string;
  purchased_on: string | null;
  warranty_expires_on: string | null;
  status: WarrantyStatus;
  document_count: number;
};

export type WarrantyPayload = {
  purchased_on: string | null;
  warranty_expires_on: string | null;
  vendor_name: string;
  vendor_contact: string;
};

type WarrantyUpload =
  | { url: string; fields: Record<string, string>; method?: string; headers?: Record<string, string> }
  | { url: string; method: "PUT"; headers?: Record<string, string>; fields?: Record<string, string> };

type WarrantyPresignResponse = {
  object_key: string;
  upload: WarrantyUpload;
};

export function warrantyHostPath(hostKind: WarrantyHostKind, hostId: number) {
  return hostKind === "asset"
    ? `/admin/assets/${hostId}/warranty`
    : `/admin/printing/printers/${hostId}/warranty`;
}

export function getWarranty(hostKind: WarrantyHostKind, hostId: number) {
  return staffRequest<Warranty | null>(warrantyHostPath(hostKind, hostId));
}

export function saveWarranty(hostKind: WarrantyHostKind, hostId: number, payload: WarrantyPayload) {
  return staffRequest<Warranty>(warrantyHostPath(hostKind, hostId), {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function uploadWarrantyDocument(warrantyId: number, file: File) {
  const presigned = await staffRequest<WarrantyPresignResponse>(
    `/admin/warranty/${warrantyId}/documents/presign`,
    {
      method: "POST",
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type || "application/octet-stream",
      }),
    },
  );

  if (presigned.upload.method === "PUT") {
    const res = await fetch(presigned.upload.url, {
      method: "PUT",
      body: file,
      headers: presigned.upload.headers,
    });
    if (!res.ok) throw new Error(`Storage upload failed (${res.status})`);
  } else {
    const formData = new FormData();
    Object.entries(presigned.upload.fields ?? {}).forEach(([key, value]) => {
      formData.append(key, value);
    });
    formData.append("file", file);
    const res = await fetch(presigned.upload.url, { method: "POST", body: formData });
    if (!res.ok) throw new Error(`Storage upload failed (${res.status})`);
  }

  return staffRequest<WarrantyDocument>(`/admin/warranty/${warrantyId}/documents`, {
    method: "POST",
    body: JSON.stringify({
      object_key: presigned.object_key,
      original_filename: file.name,
    }),
  });
}

export function getWarrantyDocumentUrl(documentId: number) {
  return staffRequest<{ url: string }>(`/admin/warranty/documents/${documentId}/url`);
}

export function deleteWarrantyDocument(documentId: number) {
  return staffRequest<void>(`/admin/warranty/documents/${documentId}`, { method: "DELETE" });
}
