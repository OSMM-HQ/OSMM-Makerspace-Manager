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
    <div className={`grid gap-1 ${className}`}>
      {location ? <p className={locationClassName}>{location}</p> : null}
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
