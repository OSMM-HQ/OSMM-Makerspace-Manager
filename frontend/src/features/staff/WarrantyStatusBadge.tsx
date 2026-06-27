import { Badge } from "../../components/ui";
import type { WarrantyStatus } from "./warrantyApi";

const statusTone: Record<WarrantyStatus, "success" | "warn" | "danger" | "neutral"> = {
  unknown: "neutral",
  active: "success",
  expiring_soon: "warn",
  expired: "danger",
};

const statusLabel: Record<WarrantyStatus, string> = {
  unknown: "No warranty info",
  active: "Active",
  expiring_soon: "Expiring soon",
  expired: "Expired",
};

export function WarrantyStatusBadge({ status }: { status: WarrantyStatus }) {
  return <Badge tone={statusTone[status]}>{statusLabel[status]}</Badge>;
}
