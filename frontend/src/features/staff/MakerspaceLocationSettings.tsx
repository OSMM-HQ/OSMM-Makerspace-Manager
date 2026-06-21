import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../components/ui";
import { staffRequest } from "../../lib/api";
import type { Makerspace } from "./StaffPanels";

type Props = {
  makerspace: Makerspace;
  settings?: Makerspace;
  loading: boolean;
};

export function MakerspaceLocationSettings({ makerspace, settings, loading }: Props) {
  const queryClient = useQueryClient();
  const currentLocation = settings?.location ?? makerspace.location ?? "";
  const currentMapUrl = settings?.map_url ?? makerspace.map_url ?? "";
  const [locationInput, setLocationInput] = useState(currentLocation);
  const [mapUrlInput, setMapUrlInput] = useState(currentMapUrl);

  useEffect(() => {
    setLocationInput(currentLocation);
    setMapUrlInput(currentMapUrl);
  }, [currentLocation, currentMapUrl, makerspace.id]);

  const updateLocation = useMutation({
    mutationFn: () =>
      staffRequest<Makerspace>(`/admin/makerspaces/${makerspace.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          location: locationInput.trim(),
          map_url: mapUrlInput.trim(),
        }),
      }),
    onSuccess: (updated) => {
      setLocationInput(updated.location ?? "");
      setMapUrlInput(updated.map_url ?? "");
      queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["makerspaces"] });
      queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
      queryClient.invalidateQueries({ queryKey: ["public-makerspaces"] });
      queryClient.invalidateQueries({ queryKey: ["tenant-bootstrap"] });
    },
  });

  const changed =
    locationInput.trim() !== currentLocation ||
    mapUrlInput.trim() !== currentMapUrl;
  const saveDisabled = loading || updateLocation.isPending || !changed;
  const savedMapUrl = currentMapUrl.trim();

  return (
    <div className="rounded-md border border-line bg-bg p-4">
      <form
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (!saveDisabled) {
            updateLocation.mutate();
          }
        }}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="grid max-w-2xl gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold text-ink">Location</h3>
              <Badge tone={savedMapUrl ? "success" : "neutral"}>
                {savedMapUrl ? "Maps link set" : "Text only"}
              </Badge>
            </div>
            <p className="text-sm text-muted">
              Public location label and optional Google Maps link shown on public pages.
            </p>
          </div>
          <button className="desk-button-primary" type="submit" disabled={saveDisabled}>
            {updateLocation.isPending ? "Saving..." : "Save location"}
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-2 text-sm font-semibold text-ink">
            <span>Location label</span>
            <input
              className="desk-input"
              value={locationInput}
              onChange={(event) => setLocationInput(event.target.value)}
              placeholder="Main lab, downtown campus"
            />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-ink">
            <span>Google Maps link</span>
            <input
              className="desk-input"
              value={mapUrlInput}
              onChange={(event) => setMapUrlInput(event.target.value)}
              placeholder="https://maps.app.goo.gl/..."
            />
            <span className="text-xs font-normal text-muted">
              Open Google Maps → Share → Copy link → paste here
            </span>
          </label>
        </div>

        {savedMapUrl ? (
          <a
            className="w-fit font-mono text-xs font-semibold uppercase text-secondary hover:underline"
            href={savedMapUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open in Maps ↗
          </a>
        ) : null}
        {updateLocation.error ? (
          <p className="text-sm text-danger">{updateLocation.error.message}</p>
        ) : null}
      </form>
    </div>
  );
}
