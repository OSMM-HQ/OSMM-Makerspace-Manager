import { Card } from "../../components/ui/Card";
import type { RequestCartItem } from "../../types/inventory";

type BorrowRequestCardProps = {
  canSubmit: boolean;
  contactEmail: string;
  contactPhone: string;
  items: RequestCartItem[];
  requestedFor: string;
  submitError?: string;
  submitPending: boolean;
  submitted: boolean;
  totalItems: number;
  onClear: () => void;
  onContactEmailChange: (value: string) => void;
  onContactPhoneChange: (value: string) => void;
  onRequestedForChange: (value: string) => void;
  onSubmit: () => void;
};

export function BorrowRequestCard({
  canSubmit,
  contactEmail,
  contactPhone,
  items,
  requestedFor,
  submitError,
  submitPending,
  submitted,
  totalItems,
  onClear,
  onContactEmailChange,
  onContactPhoneChange,
  onRequestedForChange,
  onSubmit,
}: BorrowRequestCardProps) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold tracking-wide text-accent-ink">
            Borrow Request
          </p>
          <h2 className="mt-2 text-xl font-semibold text-ink">
            Selected equipment
          </h2>
        </div>
        <span className="rounded-lg border border-line bg-surface px-3 py-1 text-sm font-semibold text-ink">
          {totalItems}
        </span>
      </div>

      {items.length === 0 ? (
        <p className="mt-4 text-sm leading-6 text-muted">
          Add public items from the inventory list, then submit the request with
          your Check-In email or phone number.
        </p>
      ) : (
        <div className="mt-4 space-y-2">
          <div className="max-h-40 space-y-2 overflow-y-auto">
            {items.map((item) => (
              <div
                className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface px-3 py-2"
                key={item.productId}
              >
                <span className="text-sm font-medium text-ink">{item.name}</span>
                <span className="text-sm text-muted">x{item.quantity}</span>
              </div>
            ))}
          </div>
          <button className="desk-button w-full" type="button" onClick={onClear}>
            Clear selection
          </button>
        </div>
      )}

      <div className="mt-5 space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <ContactInput
            label="Email for updates"
            placeholder="you@example.com"
            value={contactEmail}
            onChange={onContactEmailChange}
            type="email"
          />
          <ContactInput
            label="Phone number"
            placeholder="+91 98765 43210"
            value={contactPhone}
            onChange={onContactPhoneChange}
            type="tel"
          />
        </div>

        <label className="block">
          <span className="mb-1 block text-xs font-semibold tracking-wide text-muted">
            Request purpose
          </span>
          <textarea
            className="desk-input min-h-24 w-full resize-y"
            placeholder="What do you need these items for?"
            value={requestedFor}
            onChange={(event) => onRequestedForChange(event.target.value)}
          />
        </label>
        <button
          className="desk-button-primary w-full disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!canSubmit}
          type="button"
          onClick={onSubmit}
        >
          {submitPending ? "Submitting..." : "Submit request"}
        </button>
        {submitError ? <Notice tone="danger" text={submitError} /> : null}
        {submitted ? (
          <div className="rounded-xl border border-tone-mint bg-tone-mint px-3 py-2 text-tone-mint-ink dark:bg-[#06281a] dark:text-[#74dd9c]">
            <p className="text-sm font-semibold">Request submitted</p>
            <p className="mt-1 text-xs">
              Check this page with your email or phone to follow the request.
            </p>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function ContactInput({
  label,
  onChange,
  placeholder,
  type,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  type: "email" | "tel";
  value: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold tracking-wide text-muted">
        {label}
      </span>
      <input
        className="desk-input w-full"
        inputMode={type}
        placeholder={placeholder}
        type={type === "email" ? "email" : "text"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function Notice({ text, tone }: { text: string; tone: "danger" | "success" }) {
  const colors =
    tone === "success"
      ? "border-success bg-success text-on-success"
      : "border-danger/40 bg-danger/10 text-danger";
  return <p className={`rounded-lg border px-3 py-2 text-sm ${colors}`}>{text}</p>;
}
