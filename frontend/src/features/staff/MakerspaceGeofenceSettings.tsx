import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../components/ui";
import { staffRequest } from "../../lib/api";
import type { Makerspace } from "./StaffPanels";

type Props = { makerspace: Makerspace; settings?: Makerspace; loading: boolean };

export function MakerspaceGeofenceSettings({ makerspace, settings, loading }: Props) {
  const queryClient = useQueryClient();
  const current = settings ?? makerspace;
  const [enabled, setEnabled] = useState(current.geofence_enabled ?? false);
  const [latitude, setLatitude] = useState(String(current.geofence_latitude ?? ""));
  const [longitude, setLongitude] = useState(String(current.geofence_longitude ?? ""));
  const [radius, setRadius] = useState(String(current.geofence_radius_m ?? 25));

  useEffect(() => {
    setEnabled(current.geofence_enabled ?? false);
    setLatitude(String(current.geofence_latitude ?? ""));
    setLongitude(String(current.geofence_longitude ?? ""));
    setRadius(String(current.geofence_radius_m ?? 25));
  }, [current.geofence_enabled, current.geofence_latitude, current.geofence_longitude, current.geofence_radius_m, makerspace.id]);

  const save = useMutation({
    mutationFn: () => staffRequest<Makerspace>(`/admin/makerspaces/${makerspace.id}`, { method: "PATCH", body: JSON.stringify({
      geofence_enabled: enabled,
      geofence_latitude: latitude.trim() || null,
      geofence_longitude: longitude.trim() || null,
      geofence_radius_m: Number(radius),
    }) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["makerspaces"] });
      queryClient.invalidateQueries({ queryKey: ["tenant-bootstrap"] });
    },
  });
  const changed = enabled !== (current.geofence_enabled ?? false) || latitude !== String(current.geofence_latitude ?? "") || longitude !== String(current.geofence_longitude ?? "") || radius !== String(current.geofence_radius_m ?? 25);

  return <div className="min-w-0 rounded-md border border-line bg-bg p-4"><form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); if (changed) save.mutate(); }}>
    <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><h3 className="text-base font-semibold text-ink">Presence geofence</h3><Badge tone={enabled ? "success" : "neutral"}>{enabled ? "On" : "Off"}</Badge></div><p className="mt-1 max-w-2xl text-sm text-muted">Require member location only when a presence session starts. Browsers require HTTPS or localhost for location access.</p></div><label className="flex items-center gap-2 text-sm font-semibold text-ink"><input type="checkbox" checked={enabled} disabled={loading || save.isPending} onChange={(event) => setEnabled(event.target.checked)} /> Enable geofence</label></div>
    <div className="grid gap-3 md:grid-cols-3"><label className="grid gap-1 text-sm font-semibold text-ink">Latitude<input className="desk-input" inputMode="decimal" value={latitude} onChange={(event) => setLatitude(event.target.value)} placeholder="12.971599" /></label><label className="grid gap-1 text-sm font-semibold text-ink">Longitude<input className="desk-input" inputMode="decimal" value={longitude} onChange={(event) => setLongitude(event.target.value)} placeholder="77.594566" /></label><label className="grid gap-1 text-sm font-semibold text-ink">Radius (metres)<input className="desk-input" type="number" min="1" value={radius} onChange={(event) => setRadius(event.target.value)} /></label></div>
    {save.error ? <p className="text-sm text-danger" role="alert">{save.error.message}</p> : null}<button className="desk-button-primary w-fit" type="submit" disabled={loading || save.isPending || !changed}>{save.isPending ? "Saving..." : "Save geofence"}</button>
  </form></div>;
}
