import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";

import type { ApiPath } from "../../generated/api";
import { StructuredApiError, tenantPublicRequest } from "../../lib/api";

type RegistrationIdentity = { name: string; email: string; phone: string };
type RegistrationResult = { status: "registered" | "waitlisted" };

const REGISTER_PATH: ApiPath = "/api/v1/public/{makerspace_slug}/events/{public_token}/register/";

function registerPath(slug: string, token: string) {
  return REGISTER_PATH.replace("/api/v1", "")
    .replace("{makerspace_slug}", encodeURIComponent(slug))
    .replace("{public_token}", encodeURIComponent(token));
}

function fieldError(error: unknown, field: keyof RegistrationIdentity) {
  if (!(error instanceof StructuredApiError)) return "";
  const value = error.body[field];
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string").join(" ");
  return "";
}

export function EventRegistrationForm({ makerspaceSlug, publicToken, waitlist }: {
  makerspaceSlug: string; publicToken: string; waitlist: boolean;
}) {
  const [identity, setIdentity] = useState<RegistrationIdentity>({ name: "", email: "", phone: "" });
  const [website, setWebsite] = useState("");
  const successRef = useRef<HTMLDivElement>(null);
  const registration = useMutation({
    mutationFn: async () => {
      // The honeypot is intentionally outside the validated identity and documented serializer shape.
      const rawTransportBody: RegistrationIdentity & { website: string } = {
        name: identity.name.trim(), email: identity.email.trim(), phone: identity.phone.trim(), website,
      };
      return tenantPublicRequest<RegistrationResult>(makerspaceSlug, registerPath(makerspaceSlug, publicToken), {
        method: "POST", body: JSON.stringify(rawTransportBody),
      });
    },
  });
  useEffect(() => { if (registration.data) successRef.current?.focus(); }, [registration.data]);

  if (registration.data) {
    return <div ref={successRef} className="rounded-lg border border-line bg-surface p-4 outline-none" role="status" tabIndex={-1}>
      <h3 className="font-semibold text-ink">{registration.data.status === "waitlisted" ? "You’re on the waitlist" : "Registration received"}</h3>
      <p className="mt-1 text-sm text-muted">{registration.data.status === "waitlisted" ? "The makerspace has recorded your waitlist request." : "The makerspace has recorded your registration."}</p>
    </div>;
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!registration.isPending) registration.mutate();
  };
  const apiError = registration.error instanceof StructuredApiError ? registration.error : null;
  const setField = (field: keyof RegistrationIdentity, value: string) => setIdentity((current) => ({ ...current, [field]: value }));

  return <form className="grid gap-3 rounded-lg border border-line bg-bg p-4" onSubmit={submit} noValidate>
    <h3 className="font-semibold text-ink">{waitlist ? "Join the waitlist" : "Register"}</h3>
    <label className="grid gap-1 text-sm font-semibold text-ink">Name
      <input className="desk-input" autoComplete="name" value={identity.name} onChange={(e) => setField("name", e.target.value)} required maxLength={200} aria-invalid={Boolean(fieldError(apiError, "name"))} />
      {fieldError(apiError, "name") ? <span className="text-xs text-danger">{fieldError(apiError, "name")}</span> : null}
    </label>
    <label className="grid gap-1 text-sm font-semibold text-ink">Email
      <input className="desk-input" type="email" autoComplete="email" value={identity.email} onChange={(e) => setField("email", e.target.value)} required maxLength={254} aria-invalid={Boolean(fieldError(apiError, "email"))} />
      {fieldError(apiError, "email") ? <span className="text-xs text-danger">{fieldError(apiError, "email")}</span> : null}
    </label>
    <label className="grid gap-1 text-sm font-semibold text-ink">Phone
      <input className="desk-input" type="tel" autoComplete="tel" value={identity.phone} onChange={(e) => setField("phone", e.target.value)} required maxLength={32} aria-invalid={Boolean(fieldError(apiError, "phone"))} />
      {fieldError(apiError, "phone") ? <span className="text-xs text-danger">{fieldError(apiError, "phone")}</span> : null}
    </label>
    <label className="absolute left-[-10000px] top-auto h-px w-px overflow-hidden" aria-hidden="true">Website
      <input name="website" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
    </label>
    {registration.error ? <p className="text-sm text-danger" role="alert">{apiError?.status === 429 ? "Too many registration attempts. Please wait and try again." : apiError?.detail ?? registration.error.message}</p> : null}
    <button className="desk-button-primary" type="submit" disabled={registration.isPending}>
      {registration.isPending ? "Submitting..." : waitlist ? "Join waitlist" : "Register"}
    </button>
  </form>;
}
