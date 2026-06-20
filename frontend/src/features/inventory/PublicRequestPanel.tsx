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

type ActiveTab = "borrow" | "scan" | "requests";

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
  const [activeTab, setActiveTab] = useState<ActiveTab>("borrow");
  const [identifier, setIdentifier] = useState("");
  const [verifiedIdentifier, setVerifiedIdentifier] = useState("");
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
    mutationFn: (id: string) => verifyCheckin(makerspaceSlug, id),
    onSuccess: (_data, id) => setVerifiedIdentifier(id),
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
  const verifySuccess =
    verifyMutation.isSuccess && identifier.trim() === verifiedIdentifier;

  function cacheLookup(value: string) {
    localStorage.setItem(lookupStorageKey, value);
    setLookupValue(value);
  }

  function tabClass(tab: ActiveTab) {
    // Tabs use the brutalist status-box rectangle but filled with the brand ACCENT
    // (red), not the blue "in-progress" status colour — a selected tab is navigation,
    // not a request status.
    return activeTab === tab
      ? "status-box border-ink bg-accent text-on-accent shadow-brutal-sm w-full py-2"
      : "status-box w-full py-2 hover:bg-surface hover:text-ink";
  }

  const canSubmit =
    identifier.trim().length > 0 &&
    (contactEmail.trim().length > 0 || contactPhone.trim().length > 0) &&
    requestedFor.trim().length > 0 &&
    items.length > 0 &&
    !submitMutation.isPending;

  return (
    <aside className="space-y-4 lg:sticky lg:top-0 lg:max-h-[100dvh] lg:flex lg:flex-col lg:overflow-hidden">
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
        <>
          <Card className="shrink-0" padding="sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">
              Check-In
            </p>
            <label className="mt-3 block">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">
                Check-In email or phone
              </span>
              <input
                className="desk-input w-full"
                placeholder="Email or phone used at Check-In"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
              />
            </label>
            <button
              className="desk-button mt-3 w-full"
              disabled={!identifier.trim() || verifyMutation.isPending}
              type="button"
              onClick={() => verifyMutation.mutate(identifier.trim())}
            >
              {verifyMutation.isPending ? "Verifying..." : "Verify Check-In"}
            </button>
            <div aria-live="polite" className="mt-3 space-y-2">
              {verifySuccess ? (
                <p className="rounded-md border border-success/40 bg-success/10 px-3 py-2 text-sm text-success">
                  Check-In verified
                </p>
              ) : null}
              {verifyMutation.error ? (
                <p className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
                  {verifyMutation.error.message}
                </p>
              ) : null}
            </div>
          </Card>

          <div
            aria-label="Request actions"
            className="grid shrink-0 grid-cols-3 gap-2"
            role="tablist"
          >
            <button
              aria-controls="public-request-borrow-panel"
              aria-selected={activeTab === "borrow"}
              className={tabClass("borrow")}
              id="public-request-borrow-tab"
              role="tab"
              type="button"
              onClick={() => setActiveTab("borrow")}
            >
              Borrow request
            </button>
            <button
              aria-controls="public-request-scan-panel"
              aria-selected={activeTab === "scan"}
              className={tabClass("scan")}
              id="public-request-scan-tab"
              role="tab"
              type="button"
              onClick={() => setActiveTab("scan")}
            >
              Scan a tool
            </button>
            <button
              aria-controls="public-request-status-panel"
              aria-selected={activeTab === "requests"}
              className={tabClass("requests")}
              id="public-request-status-tab"
              role="tab"
              type="button"
              onClick={() => setActiveTab("requests")}
            >
              My requests
            </button>
          </div>

          <div className="lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
            {activeTab === "borrow" ? (
              <div
                aria-labelledby="public-request-borrow-tab"
                id="public-request-borrow-panel"
                role="tabpanel"
              >
                <BorrowRequestCard
                  canSubmit={canSubmit}
                  contactEmail={contactEmail}
                  contactPhone={contactPhone}
                  items={items}
                  requestedFor={requestedFor}
                  submitError={submitMutation.error?.message}
                  submitPending={submitMutation.isPending}
                  submitted={submitted}
                  totalItems={totalItems}
                  onClear={onClear}
                  onContactEmailChange={setContactEmail}
                  onContactPhoneChange={setContactPhone}
                  onRequestedForChange={setRequestedFor}
                  onSubmit={() => submitMutation.mutate()}
                />
              </div>
            ) : null}

            {activeTab === "scan" ? (
              <div
                aria-labelledby="public-request-scan-tab"
                id="public-request-scan-panel"
                role="tabpanel"
              >
                <PublicToolScanPanel
                  identifier={identifier}
                  makerspaceSlug={makerspaceSlug}
                />
              </div>
            ) : null}

            {activeTab === "requests" ? (
              <div
                aria-labelledby="public-request-status-tab"
                id="public-request-status-panel"
                role="tabpanel"
              >
                <Card>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
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
              </div>
            ) : null}
          </div>
        </>
      )}
    </aside>
  );
}
