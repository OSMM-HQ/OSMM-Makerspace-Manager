import type { ReactNode } from "react";
import { Link } from "react-router-dom";

type OsmmLogoProps = {
  size?: number;
  withWordmark?: boolean;
  className?: string;
};

function OsmmMark({ size, className }: { size: number; className?: string }) {
  return (
    <svg
      aria-label="OSMM"
      className={className}
      fill="none"
      height={size}
      role="img"
      viewBox="0 0 64 64"
      width={size}
    >
      <polygon
        points="8,22 2,10 28,10 32,22"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="3"
      />
      <polygon
        points="32,22 36,10 62,10 56,22"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="3"
      />
      <rect
        height="34"
        rx="5"
        stroke="currentColor"
        strokeWidth="3"
        width="48"
        x="8"
        y="22"
      />
      <rect fill="#7dd3fc" height="11" rx="2.5" width="18" x="12" y="27" />
      <rect fill="#fcdf46" height="11" rx="2.5" width="18" x="34" y="27" />
      <rect fill="#74dd9c" height="11" rx="2.5" width="18" x="12" y="42" />
      <rect fill="#f9a8d4" height="11" rx="2.5" width="18" x="34" y="42" />
    </svg>
  );
}

export function OsmmLogo({
  size = 28,
  withWordmark = false,
  className,
}: OsmmLogoProps) {
  if (withWordmark) {
    return (
      <span
        className={[
          "inline-flex items-center gap-2",
          className,
        ].filter(Boolean).join(" ")}
      >
        <OsmmMark className="shrink-0" size={size} />
        <span className="font-semibold tracking-wide">OSMM</span>
      </span>
    );
  }

  return <OsmmMark className={className} size={size} />;
}

export function OsmmHomeLink({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <Link
      aria-label="Open makerspace listing"
      className={[
        "inline-flex text-left transition hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
        className,
      ].filter(Boolean).join(" ")}
      to="/"
    >
      {children}
    </Link>
  );
}

export function OsmmBadge({ className }: { className?: string }) {
  return (
    <OsmmHomeLink
      className={[
        "text-muted",
        className,
      ].filter(Boolean).join(" ")}
    >
      <OsmmLogo size={22} withWordmark />
    </OsmmHomeLink>
  );
}
