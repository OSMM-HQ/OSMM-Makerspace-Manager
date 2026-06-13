import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { Card } from "../../components/ui/Card";
import type { RequestCartItem } from "../../types/inventory";
import { BorrowRequestCard } from "./BorrowRequestCard";
import {
  fetchRequestsByIdentifier,
  submitPublicRequest,
  verifyCheckin,
} from "./api";
import { PublicToolScanPanel } from "./PublicToolScanPanel";
import { RequestSummary } from "./RequestSummary";

type PublicRequestPanelProps = {
  items: RequestCartItem[];
  makerspaceSlug: string;
  onClear: () => void;
  disabled?: boolean;
};

export function PublicRequestPanel({
  items,
  makerspaceSlug,
  onClear,
  disabled = false,
}: PublicRequestPanelProps) {
  const lookupStorageKey = `makerspace.request.lookup.${makerspaceSlug}`;
  const [identifier, setIdentifier] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [requestedFor, setRequestedFor] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [lookupValue, setLookupValue] = useState(
    () => localStorage.getItem(lookupStorageKey) ?? "",
  );
  const totalItems = useMemo(
    () => items.reduce((total, item) => total + item.quantity, 0),
    [items],
  );

  const verifyMutation = useMutation({
    mutationFn: () => verifyCheckin(makerspaceSlug, identifier.trim()),
  });
  const submitMutation = useMutation({
    mutationFn: () =>
      submitPublicRequest(makerspaceSlug, {
        identifier: identifier.trim(),
        contact_email: contactEmail.trim(),
        contact_phone: contactPhone.trim(),
        requested_for: requestedFor.trim(),
        items: items.map((item) => ({
          product_id: item.productId,
          quantity: item.quantity,
        })),
      }),
    onSuccess: (response) => {
      void response;
      setSubmitted(true);
      cacheLookup(contactEmail.trim() || contactPhone.trim());
      onClear();
    },
  });
  const requestsQuery = useQuery({
    queryKey: ["public-request-statuses", makerspaceSlug, lookupValue],
    queryFn: () => fetchRequestsByIdentifier(makerspaceSlug, lookupValue),
    enabled: Boolean(lookupValue),
    staleTime: 30_000,
  });
  const pendingLookup = contactEmail.trim() || contactPhone.trim() || identifier.trim();

  function cacheLookup(value: string) {
    localStorage.setItem(lookupStorageKey, value);
    setLookupValue(value);
  }

  const canSubmit =
    identifier.trim().length > 0 &&
    (contactEmail.trim().length > 0 || contactPhone.trim().length > 0) &&
    requestedFor.trim().length > 0 &&
    items.length > 0 &&
    !submitMutation.isPending;

  return (
    <aside className="space-y-4">
      {disabled ? (
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">
            Requests
          </p>
          <h2 className="mt-2 text-xl font-semibold text-ink">Unavailable</h2>
          <p className="mt-2 text-sm text-muted">
            This makerspace is publishing inventory without public requests.
          </p>
        </Card>
      ) : (
        <BorrowRequestCard
          canSubmit={canSubmit}
          contactEmail={contactEmail}
          contactPhone={contactPhone}
          identifier={identifier}
          items={items}
          requestedFor={requestedFor}
          submitError={submitMutation.error?.message}
          submitPending={submitMutation.isPending}
          submitted={submitted}
          totalItems={totalItems}
          verifyError={verifyMutation.error?.message}
          verifyPending={verifyMutation.isPending}
          verifySuccess={verifyMutation.isSuccess}
          onClear={onClear}
          onContactEmailChange={setContactEmail}
          onContactPhoneChange={setContactPhone}
          onIdentifierChange={setIdentifier}
          onRequestedForChange={setRequestedFor}
          onSubmit={() => submitMutation.mutate()}
          onVerify={() => verifyMutation.mutate()}
        />
      )}

      {disabled ? null : (
        <PublicToolScanPanel
          identifier={identifier}
          makerspaceSlug={makerspaceSlug}
        />
      )}

      <Card>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">
              My Requests
            </p>
            <h2 className="mt-2 text-xl font-semibold text-ink">
              Check by email or phone
            </h2>
          </div>
        </div>
        <button
          className="desk-button mt-4 w-full"
          disabled={!pendingLookup || requestsQuery.isFetching}
          type="button"
          onClick={() => cacheLookup(pendingLookup)}
        >
          {requestsQuery.isFetching ? "Checking..." : "Show my requests"}
        </button>
        {requestsQuery.isError ? (
          <p className="mt-3 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {requestsQuery.error.message}
          </p>
        ) : null}
        {requestsQuery.isSuccess ? (
          <div className="mt-4 space-y-3">
            {requestsQuery.data.length === 0 ? (
              <p className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-muted">
                No requests found for this email or phone.
              </p>
            ) : (
              requestsQuery.data.map((request) => (
                <RequestSummary
                  key={request.public_token ?? request.created_at}
                  request={request}
                />
              ))
            )}
          </div>
        ) : null}
      </Card>
    </aside>
  );
}
