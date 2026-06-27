import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { Card } from "../../components/ui/Card";
import { StatusResult } from "./PublicPrintRequestParts";
import type { FormState } from "./PublicPrintRequestForm";
import type { PrintStatus } from "./publicApi";

type PrintCheckInCardProps = {
  form: FormState;
  verified: boolean;
  verifiedName: string;
  verifyPending: boolean;
  verifyError: Error | null;
  onRequesterNameChange: (value: string) => void;
  onContactEmailChange: (value: string) => void;
  onContactPhoneChange: (value: string) => void;
  onVerify: () => void;
};

export function PrintCheckInCard({
  form,
  verified,
  verifiedName,
  verifyPending,
  verifyError,
  onRequesterNameChange,
  onContactEmailChange,
  onContactPhoneChange,
  onVerify,
}: PrintCheckInCardProps) {
  const canVerify = Boolean(
    form.requesterName.trim() &&
      form.contactEmail.trim() &&
      form.contactPhone.trim(),
  );

  return (
    <Card className="bg-tone-yellow text-tone-yellow-ink dark:bg-[#332b00] dark:text-[#fcdf46]">
      <p className="text-xs font-semibold tracking-wide">Check-In</p>
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold tracking-wide opacity-80">
            Name
          </span>
          <input
            className="desk-input w-full"
            placeholder="Your full name"
            required
            value={form.requesterName}
            onChange={(event) => onRequesterNameChange(event.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-semibold tracking-wide opacity-80">
            Email
          </span>
          <input
            className="desk-input w-full"
            placeholder="you@example.com"
            required
            type="email"
            value={form.contactEmail}
            onChange={(event) => onContactEmailChange(event.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-semibold tracking-wide opacity-80">
            Phone
          </span>
          <input
            className="desk-input w-full"
            placeholder="+91 98765 43210"
            required
            type="tel"
            value={form.contactPhone}
            onChange={(event) => onContactPhoneChange(event.target.value)}
          />
        </label>
      </div>
      <button
        className="desk-button mt-3"
        disabled={!canVerify || verifyPending}
        type="button"
        onClick={onVerify}
      >
        {verifyPending ? "Verifying..." : "Verify Check-In"}
      </button>
      {verified ? (
        <p className="mt-3 rounded-lg border border-tone-mint bg-tone-mint px-3 py-2 text-sm font-medium text-tone-mint-ink dark:bg-[#06281a] dark:text-[#74dd9c]">
          Check-In verified{verifiedName ? ` for ${verifiedName}` : ""}
        </p>
      ) : null}
      {verifyError ? (
        <p className="mt-3 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {verifyError.message}
        </p>
      ) : null}
    </Card>
  );
}

type PrintStatusPanelProps = {
  submitted: boolean;
  statusEmail: string;
  statusEmailPending: boolean;
  statusEmailError: Error | null;
  statusEmailResults?: PrintStatus[];
  tokenStatus?: PrintStatus;
  tokenStatusPending: boolean;
  tokenStatusError: Error | null;
  onStatusEmailChange: (value: string) => void;
  onSubmitStatusEmail: (event: FormEvent<HTMLFormElement>) => void;
};

export function PrintStatusPanel({
  submitted,
  statusEmail,
  statusEmailPending,
  statusEmailError,
  statusEmailResults,
  tokenStatus,
  tokenStatusPending,
  tokenStatusError,
  onStatusEmailChange,
  onSubmitStatusEmail,
}: PrintStatusPanelProps) {
  return (
    <Card className="bg-tone-pink text-tone-pink-ink dark:bg-[#3a1326] dark:text-[#f9a8d4]">
      <p className="text-xs font-semibold tracking-wide">Status Tracker</p>
      {submitted ? (
        <p className="mt-3 rounded-lg border border-tone-mint bg-tone-mint px-3 py-2 text-sm font-medium text-tone-mint-ink dark:bg-[#06281a] dark:text-[#74dd9c]">
          Request submitted. Check its status anytime with your email below.
        </p>
      ) : null}
      <form className="mt-3 space-y-3" onSubmit={onSubmitStatusEmail}>
        <label className="block">
          <span className="mb-1 block text-xs font-semibold tracking-wide opacity-80">
            Request email
          </span>
          <input
            className="desk-input w-full"
            type="email"
            value={statusEmail}
            onChange={(event) => onStatusEmailChange(event.target.value)}
          />
        </label>
        <button
          className="desk-button"
          disabled={!statusEmail.trim() || statusEmailPending}
          type="submit"
        >
          {statusEmailPending ? "Checking..." : "Check status"}
        </button>
      </form>
      <div className="mt-4">
        <StatusResult
          error={tokenStatusError}
          isPending={tokenStatusPending}
          status={tokenStatus}
        />
      </div>
      <div className="mt-4 space-y-4">
        {statusEmailError ? (
          <p className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {statusEmailError.message}
          </p>
        ) : null}
        {statusEmailResults?.map((status) => (
          <StatusResult
            error={null}
            isPending={false}
            key={status.public_token}
            status={status}
          />
        ))}
        {statusEmailResults?.length === 0 ? (
          <p className="rounded-lg border border-line bg-panel/80 px-3 py-2 text-sm">
            No requests found for that email.
          </p>
        ) : null}
      </div>
    </Card>
  );
}

export function PrintAccessLoadingPanel() {
  return (
    <section className="mx-auto max-w-screen-sm px-5 py-6 sm:px-8">
      <Card>
        <p className="text-sm text-muted">Loading printing access...</p>
      </Card>
    </section>
  );
}

export function PrintAccessErrorPanel() {
  return (
    <section className="mx-auto max-w-screen-sm px-5 py-6 sm:px-8">
      <Card>
        <p className="text-sm text-danger">
          Could not load printing access. Try again in a moment.
        </p>
      </Card>
    </section>
  );
}
type PrintUnavailablePanelProps = {
  catalogPath: string;
  tokenStatus?: PrintStatus;
  tokenStatusPending: boolean;
  tokenStatusError: Error | null;
};

export function PrintUnavailablePanel({
  catalogPath,
  tokenStatus,
  tokenStatusPending,
  tokenStatusError,
}: PrintUnavailablePanelProps) {
  return (
    <section className="mx-auto max-w-screen-sm px-5 py-6 sm:px-8">
      <Card>
        <p className="text-xs font-semibold tracking-wide text-accent-ink">
          3D printing
        </p>
        <h2 className="mt-2 text-xl font-semibold text-ink">
          3D printing is not enabled for this makerspace.
        </h2>
        {tokenStatus || tokenStatusPending || tokenStatusError ? (
          <div className="mt-4">
            <StatusResult
              error={tokenStatusError}
              isPending={tokenStatusPending}
              status={tokenStatus}
            />
          </div>
        ) : null}
        <Link className="desk-button mt-4" to={catalogPath}>
          Back to inventory
        </Link>
      </Card>
    </section>
  );
}
