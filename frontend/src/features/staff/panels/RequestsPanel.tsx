import { Queues } from "./Queues";
import { PrintQueueSection } from "./PrintQueueSection";
import { type Makerspace } from "./shared";

// Unified "Requests" surface. Admins (Space Manager) + Superadmin see both hardware
// and 3D-printing requests under separate headings; Inventory Manager + Guest Admin
// see hardware only; Print Manager sees printing only. The gating flags are computed
// in StaffApp from the active makerspace membership.
export function RequestsPanel({
  makerspace,
  guestOnly,
  canSeeHardware,
  canSeePrinting,
}: {
  makerspace: Makerspace;
  guestOnly: boolean;
  canSeeHardware: boolean;
  canSeePrinting: boolean;
}) {
  return (
    <div className="grid gap-8">
      {canSeeHardware ? (
        <section className="grid gap-4">
          <h2 className="text-lg font-semibold text-ink">Hardware requests</h2>
          <Queues makerspace={makerspace} guestOnly={guestOnly} />
        </section>
      ) : null}
      {canSeePrinting ? (
        <section className="grid gap-4">
          <h2 className="text-lg font-semibold text-ink">3D printing requests</h2>
          <PrintQueueSection makerspace={makerspace} />
        </section>
      ) : null}
      {!canSeeHardware && !canSeePrinting ? (
        <p className="text-sm text-muted">You don't have access to any request queues here.</p>
      ) : null}
    </div>
  );
}
