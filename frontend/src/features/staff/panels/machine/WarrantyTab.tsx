import { WarrantySection } from "../../WarrantySection";

export function WarrantyTab({ machineId }: { machineId: number }) {
  return <WarrantySection hostKind="machine" hostId={machineId} />;
}
