import { useMutation, useQueryClient } from "@tanstack/react-query";

import { staffRequest } from "../../lib/api";
import type { Makerspace } from "./panels/shared";

type Props = {
  makerspace: Makerspace;
  settings?: Makerspace;
  loading: boolean;
};

const KNOWN_MODULES = [
  ["public_inventory", "Public inventory"],
  ["request_workflow", "Request workflow"],
  ["self_checkout", "Self checkout"],
  ["staff_admin", "Staff admin"],
  ["guest_handover", "Guest handover"],
  ["scanner", "Scanner"],
  ["printing", "Printing"],
  ["telegram", "Telegram"],
  ["evidence_uploads", "Evidence uploads"],
  ["qr_management", "QR management"],
  ["bulk_import", "Bulk import"],
  ["containers", "Containers"],
  ["stock_transfers", "Stock transfers"],
  ["stocktake", "Stocktake"],
  ["reports", "Reports"],
  ["qr_print_batches", "QR print batches"],
  ["asset_units", "Asset units"],
  ["procurement", "Procurement"],
  ["machines", "Machines"],
  ["events", "Events"],
  ["bookings", "Bookings"],
  ["maintenance", "Maintenance"],
  ["notifications", "Notifications"],
] as const;

export function MakerspaceModuleSettings({ makerspace, settings, loading }: Props) {
  const queryClient = useQueryClient();
  const enabledModules = settings?.enabled_modules ?? makerspace.enabled_modules ?? [];
  const updateModules = useMutation({
    mutationFn: (next: string[]) =>
      staffRequest<Makerspace>(`/admin/makerspaces/${makerspace.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled_modules: next }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["makerspaces"] });
      queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
    },
  });

  const toggleModule = (key: string, checked: boolean) => {
    const next = enabledModules.filter((moduleKey) => moduleKey !== key);
    if (checked) next.push(key);
    updateModules.mutate(Array.from(new Set(next)));
  };

  return (
    <div className="min-w-0 rounded-md border border-line bg-bg p-4">
      <h3 className="text-base font-semibold text-ink">Modules</h3>
      <p className="mt-1 text-sm text-muted">
        Disabling a module hides and gates its features and tabs; it does not delete stored data.
      </p>
      <div className="mt-4 grid min-w-0 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {KNOWN_MODULES.map(([key, label]) => (
          <label
            className="flex min-w-0 items-center gap-3 rounded-md border border-line p-3 text-sm text-ink"
            key={key}
          >
            <input
              className="h-4 w-4"
              type="checkbox"
              checked={enabledModules.includes(key)}
              disabled={loading || updateModules.isPending}
              onChange={(event) => toggleModule(key, event.target.checked)}
            />
            <span className="font-semibold">{label}</span>
          </label>
        ))}
      </div>
      {updateModules.error ? (
        <p className="mt-3 text-sm text-danger">{updateModules.error.message}</p>
      ) : null}
    </div>
  );
}
