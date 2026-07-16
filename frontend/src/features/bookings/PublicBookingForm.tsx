import { cloneElement, useEffect, useRef, useState, type FormEvent, type ReactElement } from "react";

import { StructuredApiError } from "../../lib/api";
import { CustomFormFields } from "../forms/CustomFormFields";
import {
  customAnswerErrors,
  validateCustomAnswers,
  type CustomAnswers,
} from "../forms/customFormTypes";
import { AvailabilityCalendar } from "./AvailabilityCalendar";
import { useSubmitPublicBooking, type PublicBookableSpace } from "./publicBookingsApi";

type Identity = { name: string; email: string; phone: string };
type StandardErrors = Partial<Record<keyof Identity | "starts_at" | "ends_at", string>>;

function apiFieldError(error: StructuredApiError | null, field: keyof StandardErrors) {
  const value = error?.body[field];
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string").join(" ");
  return "";
}

function failureMessage(error: StructuredApiError | null) {
  if (!error) return "The booking could not be submitted. Please try again.";
  if (error.status === 409) return "That time now overlaps a confirmed booking. Choose another slot and try again.";
  if (error.status === 429) return "Too many booking attempts were made. Please wait before trying again.";
  if (error.status === 400) return error.detail ?? "Review the highlighted fields and try again.";
  return error.detail ?? "The booking service is unavailable. Please try again.";
}

export function PublicBookingForm({ makerspaceSlug, space }: {
  makerspaceSlug: string;
  space: PublicBookableSpace;
}) {
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [identity, setIdentity] = useState<Identity>({ name: "", email: "", phone: "" });
  const [answers, setAnswers] = useState<CustomAnswers>({});
  const [website, setWebsite] = useState("");
  const [standardErrors, setStandardErrors] = useState<StandardErrors>({});
  const [answerErrors, setAnswerErrors] = useState<Record<string, string>>({});
  const successRef = useRef<HTMLDivElement>(null);
  const booking = useSubmitPublicBooking(makerspaceSlug, space.public_token);
  const apiError = booking.error instanceof StructuredApiError ? booking.error : null;
  const serverAnswerErrors = customAnswerErrors(apiError?.body.custom_answers);

  useEffect(() => {
    if (booking.data) successRef.current?.focus();
  }, [booking.data]);

  if (booking.data) {
    const pending = booking.data.status === "pending";
    return (
      <div ref={successRef} className="rounded-lg border border-line bg-surface p-4 outline-none" role="status" tabIndex={-1}>
        <h3 className="font-semibold text-ink">{pending ? "Booking request received" : "Space booked"}</h3>
        <p className="mt-1 text-sm text-muted">
          {pending ? "Staff must approve this request before the slot is confirmed." : "Your selected slot is confirmed and booked."}
        </p>
      </div>
    );
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (booking.isPending) return;
    const nextStandard: StandardErrors = {};
    if (!startsAt) nextStandard.starts_at = "Choose a start time.";
    if (!endsAt) nextStandard.ends_at = "Choose an end time.";
    if (!identity.name.trim()) nextStandard.name = "Enter your name.";
    if (!identity.email.trim()) nextStandard.email = "Enter your email.";
    if (!identity.phone.trim()) nextStandard.phone = "Enter your phone number.";
    if (startsAt && endsAt && new Date(endsAt) <= new Date(startsAt)) nextStandard.ends_at = "End time must be after start time.";
    if (endsAt && new Date(endsAt) <= new Date()) nextStandard.ends_at = "End time must be in the future.";
    const nextAnswers = validateCustomAnswers(space.custom_form, answers);
    setStandardErrors(nextStandard);
    setAnswerErrors(nextAnswers);
    if (Object.keys(nextStandard).length || Object.keys(nextAnswers).length) return;

    booking.mutate({
      starts_at: new Date(startsAt).toISOString(),
      ends_at: new Date(endsAt).toISOString(),
      name: identity.name.trim(),
      email: identity.email.trim(),
      phone: identity.phone.trim(),
      custom_answers: Object.keys(answers).length ? answers : null,
      website,
    });
  };
  const setIdentityField = (field: keyof Identity, value: string) => setIdentity((current) => ({ ...current, [field]: value }));
  const errorFor = (field: keyof StandardErrors) => standardErrors[field] || apiFieldError(apiError, field);

  return (
    <div className="grid gap-4">
      <AvailabilityCalendar makerspaceSlug={makerspaceSlug} publicToken={space.public_token} />
      <form className="grid gap-4 rounded-lg border border-line bg-bg p-4" onSubmit={submit} noValidate>
        <div>
          <h3 className="font-semibold text-ink">Request this space</h3>
          <p className="mt-1 text-xs text-muted">Times are shown in your device timezone.</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Starts" error={errorFor("starts_at")}><input className="desk-input" type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} required /></Field>
          <Field label="Ends" error={errorFor("ends_at")}><input className="desk-input" type="datetime-local" value={endsAt} onChange={(event) => setEndsAt(event.target.value)} required /></Field>
          <Field label="Name" error={errorFor("name")}><input className="desk-input" autoComplete="name" maxLength={200} value={identity.name} onChange={(event) => setIdentityField("name", event.target.value)} required /></Field>
          <Field label="Email" error={errorFor("email")}><input className="desk-input" type="email" autoComplete="email" maxLength={254} value={identity.email} onChange={(event) => setIdentityField("email", event.target.value)} required /></Field>
          <Field label="Phone" error={errorFor("phone")}><input className="desk-input" type="tel" autoComplete="tel" maxLength={32} value={identity.phone} onChange={(event) => setIdentityField("phone", event.target.value)} required /></Field>
        </div>
        <CustomFormFields schema={space.custom_form} answers={answers} onChange={setAnswers} errors={{ ...answerErrors, ...serverAnswerErrors }} disabled={booking.isPending} />
        <label className="absolute left-[-10000px] top-auto h-px w-px overflow-hidden" aria-hidden="true">Website
          <input name="website" tabIndex={-1} autoComplete="off" value={website} onChange={(event) => setWebsite(event.target.value)} />
        </label>
        {booking.error ? <p className="text-sm text-danger" role="alert">{failureMessage(apiError)}</p> : null}
        <button className="desk-button-primary" type="submit" disabled={booking.isPending}>
          {booking.isPending ? "Submitting..." : space.approval_mode === "approve" ? "Submit booking request" : "Book this slot"}
        </button>
      </form>
    </div>
  );
}

function Field({ label, error, children }: { label: string; error: string; children: ReactElement<{ "aria-invalid"?: boolean }> }) {
  return (
    <label className="grid gap-1 text-sm font-semibold text-ink">
      {label}
      {error ? <span className="text-xs font-normal text-danger">{error}</span> : null}
      {cloneElement(children, { "aria-invalid": Boolean(error) })}
    </label>
  );
}
