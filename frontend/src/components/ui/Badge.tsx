import type { PropsWithChildren } from "react";

type BadgeTone = "success" | "warn" | "danger" | "neutral";

type BadgeProps = PropsWithChildren<{
  tone: BadgeTone;
}>;

const toneClasses: Record<BadgeTone, string> = {
  success: "border-success bg-success text-on-success",
  warn: "border-warn bg-warn text-on-warn",
  danger: "border-danger bg-danger text-bg",
  neutral: "border-outline bg-surface text-muted",
};

export function Badge({ tone, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-xs font-medium tracking-tight ${toneClasses[tone]}`}
    >
      {children}
    </span>
  );
}
