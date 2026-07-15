import { staffRequest } from "../../lib/api";

export type MachineStatus = "idle" | "running" | "reserved" | "maintenance" | "offline";
export type MachineAccessLevel = "operate" | "manage" | "full";

export type MachineType = {
  id: number;
  slug: string;
  name: string;
  icon: string;
  is_builtin: boolean;
  managing_action: string;
  makerspace: number;
};

export type Machine = {
  id: number;
  makerspace: number;
  machine_type: MachineType;
  name: string;
  location: string;
  notes: string;
  status: MachineStatus;
  firmware_version: string;
  camera_feed_url: string;
  is_active: boolean;
  linked_print_printer: number | null;
  usage_hours: string;
  can_operate: boolean;
  can_edit: boolean;
  can_delegate: boolean;
  can_retire: boolean;
  can_unretire: boolean;
  can_manage: boolean;
  created_at: string;
  updated_at: string;
};

export type MachineOperator = {
  id: number;
  user: number;
  username: string;
  access_level: MachineAccessLevel;
  assigned_by_username: string | null;
  assigned_at: string;
};

export type MachineOperatorCandidate = {
  user_id: number;
  username: string;
  display_name: string;
};

export type MachineUsageEntry = {
  id: number;
  hours: string;
  source: string;
  note: string;
  logged_by_username: string | null;
  created_at: string;
};

export type MachineDocument = {
  id: number;
  doc_type: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type MachineErrorLog = {
  id: number;
  severity: string;
  message: string;
  logged_by_username: string | null;
  created_at: string;
};

export type MachineListResponse<T> = {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
};
export type MachineCollection<T> = MachineListResponse<T> | T[];

export const machineKeys = {
  all: ["machines"] as const,
  list: (makerspaceId: number) => ["machines", makerspaceId] as const,
  types: (makerspaceId: number) => ["machine-types", makerspaceId] as const,
  detail: (machineId: number) => ["machine", machineId] as const,
  usage: (machineId: number) => ["machine-usage", machineId] as const,
  operators: (machineId: number) => ["machine-operators", machineId] as const,
  operatorCandidates: (machineId: number) => ["machine-operator-candidates", machineId] as const,
  documents: (machineId: number) => ["machine-documents", machineId] as const,
  errors: (machineId: number) => ["machine-errors", machineId] as const,
};

export function collectionResults<T>(data: MachineCollection<T> | undefined): T[] {
  if (!data) return [];
  return Array.isArray(data) ? data : data.results;
}

export type MachinePayload = {
  name: string;
  location: string;
  notes: string;
  firmware_version: string;
  camera_feed_url: string;
  machine_type_id: number;
};
export type MachinePatch = Partial<MachinePayload>;

export function getMachines(makerspaceId: number) {
  return staffRequest<MachineListResponse<Machine>>(`/admin/makerspace/${makerspaceId}/machines`);
}

export function createMachine(makerspaceId: number, payload: MachinePayload) {
  return staffRequest<Machine>(`/admin/makerspace/${makerspaceId}/machines`, {
    method: "POST", body: JSON.stringify(payload),
  });
}

export function getMachineTypes(makerspaceId: number) {
  return staffRequest<MachineCollection<MachineType>>(`/admin/makerspace/${makerspaceId}/machine-types`);
}

export function createMachineType(makerspaceId: number, payload: Pick<MachineType, "slug" | "name" | "icon">) {
  return staffRequest<MachineType>(`/admin/makerspace/${makerspaceId}/machine-types`, {
    method: "POST", body: JSON.stringify(payload),
  });
}

export function getMachine(machineId: number) {
  return staffRequest<Machine>(`/admin/machines/${machineId}`);
}

export function updateMachine(machineId: number, payload: MachinePatch) {
  return staffRequest<Machine>(`/admin/machines/${machineId}`, {
    method: "PATCH", body: JSON.stringify(payload),
  });
}

export function setMachineStatus(machineId: number, status: MachineStatus) {
  return staffRequest<Machine>(`/admin/machines/${machineId}/set-status`, {
    method: "POST", body: JSON.stringify({ status }),
  });
}

export function retireMachine(machineId: number) {
  return staffRequest<Machine>(`/admin/machines/${machineId}/retire`, {
    method: "POST", body: JSON.stringify({}),
  });
}

export function unretireMachine(machineId: number) {
  return staffRequest<Machine>(`/admin/machines/${machineId}/unretire`, {
    method: "POST", body: JSON.stringify({}),
  });
}

export function getMachineUsage(machineId: number) {
  return staffRequest<MachineCollection<MachineUsageEntry>>(`/admin/machines/${machineId}/usage`);
}

export function addMachineUsage(machineId: number, payload: { hours: string; note: string }) {
  return staffRequest<MachineUsageEntry>(`/admin/machines/${machineId}/usage`, {
    method: "POST", body: JSON.stringify(payload),
  });
}

export function getMachineOperators(machineId: number) {
  return staffRequest<MachineCollection<MachineOperator>>(`/admin/machines/${machineId}/operators`);
}

export function getOperatorCandidates(machineId: number) {
  return staffRequest<MachineOperatorCandidate[]>(`/admin/machines/${machineId}/operator-candidates`);
}

export function addMachineOperator(machineId: number, payload: { user_id: number; access_level: MachineAccessLevel }) {
  return staffRequest<MachineOperator>(`/admin/machines/${machineId}/operators`, {
    method: "POST", body: JSON.stringify(payload),
  });
}

export function updateMachineOperator(machineId: number, userPk: number, accessLevel: MachineAccessLevel) {
  return staffRequest<MachineOperator>(`/admin/machines/${machineId}/operators/${userPk}`, {
    method: "PATCH", body: JSON.stringify({ access_level: accessLevel }),
  });
}

export function deleteMachineOperator(machineId: number, userPk: number) {
  return staffRequest<void>(`/admin/machines/${machineId}/operators/${userPk}`, { method: "DELETE" });
}

type MachineUpload =
  | { url: string; fields: Record<string, string>; method?: string; headers?: Record<string, string> }
  | { url: string; method: "PUT"; headers?: Record<string, string>; fields?: Record<string, string> };
type MachinePresignResponse = { object_key: string; upload: MachineUpload };

export async function uploadMachineDocument(machineId: number, file: File, docType: string) {
  const presigned = await staffRequest<MachinePresignResponse>(`/admin/machines/${machineId}/documents/presign`, {
    method: "POST",
    body: JSON.stringify({ filename: file.name, content_type: file.type || "application/octet-stream" }),
  });

  if (presigned.upload.method === "PUT") {
    const res = await fetch(presigned.upload.url, {
      method: "PUT", body: file, headers: presigned.upload.headers,
    });
    if (!res.ok) throw new Error(`Storage upload failed (${res.status})`);
  } else {
    const formData = new FormData();
    Object.entries(presigned.upload.fields ?? {}).forEach(([key, value]) => formData.append(key, value));
    formData.append("file", file);
    const res = await fetch(presigned.upload.url, { method: "POST", body: formData });
    if (!res.ok) throw new Error(`Storage upload failed (${res.status})`);
  }

  return staffRequest<MachineDocument>(`/admin/machines/${machineId}/documents`, {
    method: "POST",
    body: JSON.stringify({ object_key: presigned.object_key, doc_type: docType, original_filename: file.name }),
  });
}

export function getMachineDocuments(machineId: number) {
  return staffRequest<MachineCollection<MachineDocument>>(`/admin/machines/${machineId}/documents`);
}

export function getMachineDocumentUrl(documentId: number) {
  return staffRequest<{ url: string }>(`/admin/machines/documents/${documentId}/url`);
}

export function deleteMachineDocument(documentId: number) {
  return staffRequest<void>(`/admin/machines/documents/${documentId}`, { method: "DELETE" });
}

export function getMachineErrorLogs(machineId: number) {
  return staffRequest<MachineCollection<MachineErrorLog>>(`/admin/machines/${machineId}/error-logs`);
}

export function addMachineErrorLog(machineId: number, payload: { severity: string; message: string }) {
  return staffRequest<MachineErrorLog>(`/admin/machines/${machineId}/error-logs`, {
    method: "POST", body: JSON.stringify(payload),
  });
}
