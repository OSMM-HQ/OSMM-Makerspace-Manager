import { Queues } from "./Queues";
import { type Makerspace } from "./shared";

export function RequestsPanel({ makerspace, guestOnly, canSeeHardware, canViewAudit }: { makerspace: Makerspace; guestOnly: boolean; canSeeHardware: boolean; canViewAudit: boolean }) {
  return canSeeHardware ? <Queues makerspace={makerspace} guestOnly={guestOnly} canViewAudit={canViewAudit} /> : <p className="text-sm text-muted">Machine-service queues are managed from Machines.</p>;
}
