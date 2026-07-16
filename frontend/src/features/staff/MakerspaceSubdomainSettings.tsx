import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../components/ui";
import { staffRequest } from "../../lib/api";
import { type Makerspace, useStaffGet } from "./StaffPanels";

type Props = {
  makerspace: Makerspace;
  settings?: Makerspace;
};

type SubdomainRequest = {
  id: number;
  requested_label: string;
  status: "pending" | "approved" | "rejected";
  note: string;
  created_at: string;
};

type SubdomainRequestResponse = { results: SubdomainRequest[] };

export function MakerspaceSubdomainSettings({ makerspace, settings }: Props) {
  const queryClient = useQueryClient();
  const [requestedLabel, setRequestedLabel] = useState("");
  const managed = settings?.platform_hosting ?? makerspace.platform_hosting ?? false;
  const requests = useStaffGet<SubdomainRequestResponse>(
    ["subdomain-requests", makerspace.id],
    `/admin/makerspace/${makerspace.id}/subdomain-request`,
    managed,
  );

  const submitRequest = useMutation({
    mutationFn: () =>
      staffRequest<SubdomainRequest>(`/admin/makerspace/${makerspace.id}/subdomain-request`, {
        method: "POST",
        body: JSON.stringify({ requested_label: requestedLabel.trim() }),
      }),
    onSuccess: () => {
      setRequestedLabel("");
      queryClient.invalidateQueries({ queryKey: ["subdomain-requests", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
    },
  });

  if (!managed) return null;

  const history = requests.data?.results ?? [];
  const pendingRequest = history.find((request) => request.status === "pending");
  const currentDomain = settings?.frontend_domain ?? makerspace.frontend_domain;
  // Active state derives from the backend's authoritative is_platform_subdomain flag
  // (frontend_domain is a VERIFIED platform-suffix subdomain), NOT request history or
  // the presence of a TXT record — managed mode returns a TXT record for every domain,
  // so absence-of-record can't distinguish a provisioned subdomain.
  const hasActiveSubdomain =
    settings?.is_platform_subdomain ?? makerspace.is_platform_subdomain ?? false;
  const activeSubdomain = currentDomain;
  const submitDisabled =
    requests.isLoading || submitRequest.isPending || Boolean(pendingRequest) || !requestedLabel.trim();

  return (
    <div className="min-w-0 rounded-md border border-line bg-bg p-4">
      <div className="grid min-w-0 gap-4">
        <div className="grid min-w-0 max-w-2xl gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-ink">Request a subdomain</h3>
            {hasActiveSubdomain ? <Badge tone="success">Active</Badge> : null}
          </div>
          <p className="text-sm text-muted">
            Ask the platform team to provision a dedicated subdomain for this makerspace.
          </p>
        </div>

        {hasActiveSubdomain ? (
          <p className="text-sm text-ink">
            Active subdomain: <span className="font-semibold">{activeSubdomain}</span>
          </p>
        ) : (
          <form
            className="grid min-w-0 max-w-xl gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              if (!submitDisabled) submitRequest.mutate();
            }}
          >
            <label className="grid gap-2 text-sm font-semibold text-ink" htmlFor="subdomain-label">
              Desired subdomain label
              <input
                id="subdomain-label"
                className="desk-input"
                placeholder="alpha"
                value={requestedLabel}
                disabled={requests.isLoading || Boolean(pendingRequest)}
                onChange={(event) => setRequestedLabel(event.target.value)}
              />
            </label>
            <button className="desk-button-primary" type="submit" disabled={submitDisabled}>
              {submitRequest.isPending ? "Submitting..." : "Submit request"}
            </button>
          </form>
        )}

        {pendingRequest && !hasActiveSubdomain ? (
          <p className="text-sm text-muted">Request pending review</p>
        ) : null}
        {submitRequest.error ? (
          <p className="text-sm text-danger">{submitRequest.error.message}</p>
        ) : null}
        {requests.error ? <p className="text-sm text-danger">{requests.error.message}</p> : null}

        {requests.isLoading ? <p className="text-sm text-muted">Loading requests...</p> : null}
        {history.length > 0 ? (
          <ul className="grid gap-2">
            {history.map((request) => (
              <li
                className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-surface p-3 text-sm"
                key={request.id}
              >
                <span className="font-semibold text-ink">{request.requested_label}</span>
                <Badge tone={statusTone(request.status)}>{statusLabel(request.status)}</Badge>
                {request.note ? <span className="text-muted">{request.note}</span> : null}
                <time className="text-xs text-muted" dateTime={request.created_at}>
                  {new Date(request.created_at).toLocaleString()}
                </time>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

function statusTone(status: SubdomainRequest["status"]) {
  return status === "approved" ? "success" : status === "rejected" ? "danger" : "warn";
}

function statusLabel(status: SubdomainRequest["status"]) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}
