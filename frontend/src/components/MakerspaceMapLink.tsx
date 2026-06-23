type MakerspaceLocation = {
  location?: string | null;
  map_url?: string | null;
};

type MakerspaceMapLinkProps = {
  makerspace?: MakerspaceLocation | null;
  className?: string;
  locationClassName?: string;
  linkClassName?: string;
};

export function MakerspaceMapLink({
  makerspace,
  className = "",
  locationClassName = "text-sm text-muted",
  linkClassName = "font-mono text-xs font-semibold text-secondary-ink hover:underline",
}: MakerspaceMapLinkProps) {
  const location = makerspace?.location?.trim() ?? "";
  const mapUrl = makerspace?.map_url?.trim() ?? "";

  if (!location && !mapUrl) {
    return null;
  }

  return (
    <div className={`flex flex-wrap items-center gap-x-2 gap-y-0.5 ${className}`}>
      {location ? <span className={locationClassName}>{location}</span> : null}
      {mapUrl ? (
        <a
          className={linkClassName}
          href={mapUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          📍 Open in Google Maps
        </a>
      ) : null}
    </div>
  );
}
