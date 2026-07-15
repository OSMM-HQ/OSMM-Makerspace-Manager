import { staffRequest } from "../../lib/api";

export type ConsumableMeasurement = "count" | "grams";

export type MachineConsumable = {
  id: number;
  measurement: ConsumableMeasurement;
  product: number | null;
  product_name: string | null;
  available: number | null;
  remaining: string | null;
  label: string;
  low_threshold: string | null;
  note: string;
  created_at: string;
};

export type ConsumableCandidate = {
  id: number;
  name: string;
  available: number;
};

export type LinkConsumablePayload = {
  measurement: ConsumableMeasurement;
  product_id?: number;
  label?: string;
  remaining?: string;
  low_threshold?: string | null;
  note?: string;
};

export function getMachineConsumables(machineId: number) {
  return staffRequest<MachineConsumable[]>(`/admin/machines/${machineId}/consumables`);
}

export function getConsumableCandidates(machineId: number) {
  return staffRequest<ConsumableCandidate[]>(`/admin/machines/${machineId}/consumable-candidates`);
}

export function linkMachineConsumable(machineId: number, payload: LinkConsumablePayload) {
  return staffRequest<MachineConsumable>(`/admin/machines/${machineId}/consumables`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function unlinkMachineConsumable(machineId: number, consumableId: number) {
  return staffRequest<void>(`/admin/machines/${machineId}/consumables/${consumableId}`, {
    method: "DELETE",
  });
}

export function logMachineConsumption(machineId: number, consumableId: number, quantity: string) {
  return staffRequest<MachineConsumable>(
    `/admin/machines/${machineId}/consumables/${consumableId}/log`,
    { method: "POST", body: JSON.stringify({ quantity }) },
  );
}
