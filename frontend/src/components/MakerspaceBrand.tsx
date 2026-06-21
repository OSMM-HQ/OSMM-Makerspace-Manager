type MakerspaceBrandProps = {
  name: string;
  logoUrl?: string | null;
  /** Visual size of the mark. */
  size?: "sm" | "md" | "lg";
  /** Hide the text name beside the logo (logo-only lockup). */
  hideName?: boolean;
  className?: string;
};

const LOGO_SIZE: Record<NonNullable<MakerspaceBrandProps["size"]>, string> = {
  sm: "h-8 w-8",
  md: "h-10 w-10",
  lg: "h-14 w-14",
};

const NAME_SIZE: Record<NonNullable<MakerspaceBrandProps["size"]>, string> = {
  sm: "text-base",
  md: "text-xl",
  lg: "text-2xl",
};

/**
 * Renders a makerspace's brand: its uploaded logo when present, otherwise the
 * makerspace NAME as a styled Clash Display wordmark (the design-system fallback,
 * so every makerspace page is always branded even with no logo on file).
 */
export function MakerspaceBrand({
  name,
  logoUrl,
  size = "md",
  hideName = false,
  className = "",
}: MakerspaceBrandProps) {
  return (
    <span className={`inline-flex items-center gap-3 ${className}`}>
      {logoUrl ? (
        <img
          src={logoUrl}
          alt={`${name} logo`}
          className={`${LOGO_SIZE[size]} shrink-0 rounded-lg border border-line object-contain bg-panel`}
        />
      ) : null}
      {!hideName || !logoUrl ? (
        <span
          className={`font-display font-bold tracking-tight text-ink ${NAME_SIZE[size]}`}
        >
          {name}
        </span>
      ) : null}
    </span>
  );
}
