import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Card } from "../../components/ui/Card";
import type { RequestCartItem } from "../../types/inventory";
import { BorrowRequestCard } from "./BorrowRequestCard";
import {
  fetchRequestsByIdentifier,
  submitPublicRequest,
  verifyCheckin,
} from "./api";
import { invalidatePublicInventory } from "../staff/queryInvalidation";
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
  const queryClient = useQueryClient();
  const lookupStorageKey = `makerspace.request.lookup.${makerspaceSlug}`;
  const [activeTab, setActiveTab] = useState<ActiveTab>("borrow");
  const [requesterName, setRequesterName] = useState("");
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
    mutationFn: (email: string) => verifyCheckin(makerspaceSlug, email),
    onSuccess: (_data, email) => setVerifiedIdentifier(email),
  });
  const submitMutation = useMutation({
    mutationFn: () =>
      submitPublicRequest(makerspaceSlug, {
        requester_name: requesterName.trim(),
        contact_email: contactEmail.trim(),
        contact_phone: contactPhone.trim(),
        requested_for: requestedFor.trim(),
        items: items.map((item) => ({
          product_id: item.productId,
          quantity: item.quantity,
        })),
      }),
    onSuccess: (response) => {
      invalidatePublicInventory(queryClient, makerspaceSlug);
      void response;
      setSubmitted(true);
      cacheLookup(contactEmail.trim());
      onClear();
    },
  });
  const requestsQuery = useQuery({
    queryKey: ["public-request-statuses", makerspaceSlug, lookupValue],
    queryFn: () => fetchRequestsByIdentifier(makerspaceSlug, lookupValue),
    enabled: Boolean(lookupValue),
    staleTime: 30_000,
  });
  const pendingLookup = contactEmail.trim();
  const verifySuccess =
    verifyMutation.isSuccess && contactEmail.trim() === verifiedIdentifier;

  function updateContactEmail(value: string) {
    setContactEmail(value);
    if (value.trim() !== verifiedIdentifier) {
      setVerifiedIdentifier("");
      verifyMutation.reset();
    }
  }

  function cacheLookup(value: string) {
    localStorage.setItem(lookupStorageKey, value);
    setLookupValue(value);
  }

  // Each tab carries its own palette tone — a touch of colour so the action row
  // doesn't read as flat. Active = filled pastel (+ dark deep-tint); idle = neutral
  // with a faint tone hover hint.
  const tabTone: Record<ActiveTab, { active: string; idle: string }> = {
    borrow: {
      active:
        "border-tone-blue bg-tone-blue text-tone-blue-ink dark:bg-[#0b2a38] dark:text-[#7dd3fc]",
      idle: "hover:bg-tone-blue/40 hover:text-tone-blue-ink",
    },
    scan: {
      active:
        "border-tone-mint bg-tone-mint text-tone-mint-ink dark:bg-[#06281a] dark:text-[#74dd9c]",
      idle: "hover:bg-tone-mint/40 hover:text-tone-mint-ink",
    },
    requests: {
      active:
        "border-tone-pink bg-tone-pink text-tone-pink-ink dark:bg-[#3a1326] dark:text-[#f9a8d4]",
      idle: "hover:bg-tone-pink/40 hover:text-tone-pink-ink",
    },
  };

  function tabClass(tab: ActiveTab) {
    const tone = tabTone[tab];
    return activeTab === tab
      ? `status-box w-full py-2 shadow-soft ${tone.active}`
      : `status-box w-full py-2 ${tone.idle}`;
  }

  const canSubmit =
    requesterName.trim().length > 0 &&
    contactEmail.trim().length > 0 &&
    contactPhone.trim().length > 0 &&
    requestedFor.trim().length > 0 &&
    verifySuccess &&
    items.length > 0 &&
    !submitMutation.isPending;

  return (
    <aside className="space-y-4 lg:sticky lg:top-0 lg:max-h-[100dvh] lg:flex lg:flex-col lg:overflow-hidden">
      {disabled ? (
        <Card>
          <p className="text-xs font-semibold tracking-wide text-accent-ink">
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
            <p className="text-xs font-semibold tracking-wide text-accent-ink">
              Your Details
            </p>
            <label className="mt-3 block">
              <span className="mb-1 block text-xs font-semibold tracking-wide text-muted">
                Name
              </span>
              <input
                className="desk-input w-full"
                placeholder="Your full name"
                required
                value={requesterName}
                onChange={(event) => setRequesterName(event.target.value)}
              />
            </label>
            <label className="mt-3 block">
              <span className="mb-1 block text-xs font-semibold tracking-wide text-muted">
                Email
              </span>
              <input
                className="desk-input w-full"
                placeholder="you@example.com"
                required
                type="email"
                value={contactEmail}
                onChange={(event) => updateContactEmail(event.target.value)}
              />
            </label>
            <label className="mt-3 block">
              <span className="mb-1 block text-xs font-semibold tracking-wide text-muted">
                Phone
              </span>
              <input
                className="desk-input w-full"
                placeholder="+91 98765 43210"
                required
                type="tel"
                value={contactPhone}
                onChange={(event) => setContactPhone(event.target.value)}
              />
            </label>
            <button
              className="desk-button mt-3 w-full"
              disabled={!contactEmail.trim() || verifyMutation.isPending}
              type="button"
              onClick={() => verifyMutation.mutate(contactEmail.trim())}
            >
              {verifyMutation.isPending ? "Verifying..." : "Verify Check-In"}
            </button>
            <div aria-live="polite" className="mt-3 space-y-2">
              {verifySuccess ? (
                <p className="rounded-lg border border-tone-mint bg-tone-mint px-3 py-2 text-sm font-medium text-tone-mint-ink dark:bg-[#06281a] dark:text-[#74dd9c]">
                  Check-In verified
                </p>
              ) : null}
              {verifyMutation.error ? (
                <p className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
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
                  items={items}
                  requestedFor={requestedFor}
                  submitError={submitMutation.error?.message}
                  submitPending={submitMutation.isPending}
                  submitted={submitted}
                  totalItems={totalItems}
                  onClear={onClear}
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
                  requesterName={requesterName}
                  contactEmail={contactEmail}
                  contactPhone={contactPhone}
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
                      <p className="text-xs font-semibold tracking-wide text-accent-ink">
                        My Requests
                      </p>
                      <h2 className="mt-2 text-xl font-semibold text-ink">
                        Check by email
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
                    <p className="mt-3 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
                      {requestsQuery.error.message}
                    </p>
                  ) : null}
                  {requestsQuery.isSuccess ? (
                    <div className="mt-4 space-y-3">
                      {requestsQuery.data.length === 0 ? (
                        <p className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-muted">
                          No requests found for this email.
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
