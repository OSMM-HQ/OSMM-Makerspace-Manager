import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../components/ui";
import { staffRequest } from "../../lib/api";
import type { Makerspace } from "./panels/shared";

export function MakerspaceBookingSettings({ makerspace, settings, loading }: {
  makerspace: Makerspace;
  settings?: Makerspace;
  loading: boolean;
}) {
  const queryClient = useQueryClient();
  const enabled = settings?.booking_requester_notifications_enabled
    ?? makerspace.booking_requester_notifications_enabled
    ?? false;
  const update = useMutation({
    mutationFn: (next: boolean) => staffRequest<Makerspace>("/admin/makerspaces/" + makerspace.id, {
      method: "PATCH",
      body: JSON.stringify({ booking_requester_notifications_enabled: next }),
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] }),
        queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] }),
        queryClient.invalidateQueries({ queryKey: ["bookings", makerspace.id] }),
      ]);
    },
  });

  return (
    <div className="min-w-0 rounded-md border border-line bg-bg p-4">
      <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
        <div className="grid min-w-0 max-w-2xl gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-ink">Booking requester emails</h3>
            <Badge tone={enabled ? "success" : "neutral"}>{enabled ? "On" : "Off"}</Badge>
          </div>
          <p className="text-sm text-muted">
            Set the default for booking submitted, confirmed, and rejected emails. Each space may inherit or override this setting.
          </p>
          {update.error ? <p className="text-sm text-danger" role="alert">{update.error.message}</p> : null}
        </div>
        <label className="flex min-w-0 items-start gap-3 text-sm text-ink md:justify-self-end">
          <input className="mt-1 h-4 w-4" type="checkbox" checked={enabled} disabled={loading || update.isPending} onChange={(event) => update.mutate(event.target.checked)} />
          <span className="font-semibold">Email booking requesters</span>
        </label>
      </div>
    </div>
  );
}
