import { staffRequest } from '../../lib/api';
import type { MachineCollection, MachineDocument } from './machinesApi';

type MachineUpload =
  | { url: string; fields: Record<string, string>; method?: string; headers?: Record<string, string> }
  | { url: string; method: 'PUT'; headers?: Record<string, string>; fields?: Record<string, string> };
type MachinePresignResponse = { object_key: string; upload: MachineUpload };

export async function uploadMachineDocument(machineId: number, file: File, docType: string) {
  const presigned = await staffRequest<MachinePresignResponse>(
    `/admin/machines/${machineId}/documents/presign`,
    {
      method: 'POST',
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type || 'application/octet-stream',
      }),
    },
  );

  if (presigned.upload.method === 'PUT') {
    const response = await fetch(presigned.upload.url, {
      method: 'PUT', body: file, headers: presigned.upload.headers,
    });
    if (!response.ok) throw new Error(`Storage upload failed (${response.status})`);
  } else {
    const formData = new FormData();
    Object.entries(presigned.upload.fields ?? {}).forEach(([key, value]) =>
      formData.append(key, value),
    );
    formData.append('file', file);
    const response = await fetch(presigned.upload.url, { method: 'POST', body: formData });
    if (!response.ok) throw new Error(`Storage upload failed (${response.status})`);
  }

  return staffRequest<MachineDocument>(`/admin/machines/${machineId}/documents`, {
    method: 'POST',
    body: JSON.stringify({
      object_key: presigned.object_key,
      doc_type: docType,
      original_filename: file.name,
    }),
  });
}

export function getMachineDocuments(machineId: number) {
  return staffRequest<MachineCollection<MachineDocument>>(
    `/admin/machines/${machineId}/documents`,
  );
}

export function getMachineDocumentUrl(documentId: number) {
  return staffRequest<{ url: string }>(`/admin/machines/documents/${documentId}/url`);
}

export function deleteMachineDocument(documentId: number) {
  return staffRequest<void>(`/admin/machines/documents/${documentId}`, { method: 'DELETE' });
}
