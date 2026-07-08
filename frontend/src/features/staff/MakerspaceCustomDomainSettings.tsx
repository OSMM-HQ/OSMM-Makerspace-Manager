import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../components/ui";
import type { ApiPath } from "../../generated/api";
import { staffRequest } from "../../lib/api";
import type { Makerspace } from "./StaffPanels";

type Props = {
  makerspace: Makerspace;
  settings?: Makerspace;
  loading: boolean;
};

type VerifyDomainResponse = {
  status: DomainStatus;
  token: string;
  expected_record: DomainRecord | null;
  verified_at: string | null;
  detail: string;
};

type DomainStatus = "pending" | "verified" | "failed";
type DomainRecord = { host: string; type: "TXT"; value: string };

const VERIFY_DOMAIN_API_PATH: ApiPath = "/api/v1/admin/makerspace/{makerspace_id}/verify-domain";

function verifyDomainStaffPath(makerspaceId: number) {
  return VERIFY_DOMAIN_API_PATH.replace("/api/v1", "").replace("{makerspace_id}", String(makerspaceId));
}

export function MakerspaceCustomDomainSettings({ makerspace, settings, loading }: Props) {
  const queryClient = useQueryClient();
  const [domainInput, setDomainInput] = useState("");
  const [hideFromDirectory, setHideFromDirectory] = useState(false);
  const [verifyDetail, setVerifyDetail] = useState("");

  const currentDomain = settings?.frontend_domain ?? makerspace.frontend_domain ?? null;
  const currentHidden =
    settings?.hidden_from_central_directory ?? makerspace.hidden_from_central_directory ?? false;
  const status = settings?.frontend_domain_status ?? makerspace.frontend_domain_status ?? "pending";
  const record = settings?.domain_verification_record ?? makerspace.domain_verification_record ?? null;
  const token = settings?.domain_verification_token ?? makerspace.domain_verification_token ?? "";

  useEffect(() => {
    setDomainInput(currentDomain ?? "");
    setHideFromDirectory(Boolean(currentDomain) && currentHidden);
    setVerifyDetail("");
  }, [currentDomain, currentHidden, makerspace.id]);

  const refreshSettings = () => {
    queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
    queryClient.invalidateQueries({ queryKey: ["makerspaces"] });
    queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
  };

  const trimmedDomain = domainInput.trim();
  const hasDomainInput = trimmedDomain.length > 0;
  const effectiveHidden = hasDomainInput ? hideFromDirectory : false;
  const domainChanged = trimmedDomain !== (currentDomain ?? "");
  const hiddenChanged = effectiveHidden !== currentHidden;
  const customDomainUrls = useMemo(
    () => [`https://${trimmedDomain}/`, `https://${trimmedDomain}/admin`],
    [trimmedDomain],
  );

  const updateCustomDomain = useMutation({
    mutationFn: () =>
      staffRequest<Makerspace>(`/admin/makerspaces/${makerspace.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          frontend_domain: trimmedDomain,
          hidden_from_central_directory: effectiveHidden,
        }),
      }),
    onSuccess: (updated) => {
      setDomainInput(updated.frontend_domain ?? "");
      setHideFromDirectory(
        Boolean(updated.frontend_domain) && updated.hidden_from_central_directory,
      );
      setVerifyDetail("");
      refreshSettings();
    },
  });

  const verifyDomain = useMutation({
    mutationFn: () =>
      staffRequest<VerifyDomainResponse>(verifyDomainStaffPath(makerspace.id), {
        method: "POST",
      }),
    onSuccess: (result) => {
      setVerifyDetail(result.detail);
      refreshSettings();
    },
  });

  const domainSaveDisabled =
    loading || updateCustomDomain.isPending || (!domainChanged && !hiddenChanged);
  const verifyDisabled = loading || verifyDomain.isPending || !currentDomain || domainChanged;
  const visibleRecord = domainChanged ? null : record;

  return (
    <div className="min-w-0 rounded-md border border-line bg-bg p-4">
      <form
        className="grid min-w-0 gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (!domainSaveDisabled) {
            updateCustomDomain.mutate();
          }
        }}
      >
        <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
          <div className="grid min-w-0 max-w-2xl gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold text-ink">Custom domain</h3>
              <Badge tone={domainStatusTone(status)}>{domainStatusLabel(status)}</Badge>
            </div>
            <p className="text-sm text-muted">
              Route this makerspace&apos;s public and staff surfaces through a dedicated domain.
            </p>
          </div>
          <button
            className="desk-button-primary w-full max-w-full justify-self-start sm:w-auto md:justify-self-end"
            type="submit"
            disabled={domainSaveDisabled}
          >
            {updateCustomDomain.isPending ? "Saving..." : "Save domain"}
          </button>
        </div>

        <div className="grid min-w-0 max-w-xl gap-2">
          <label className="text-sm font-semibold text-ink" htmlFor="custom-domain">
            Domain
          </label>
          <input
            id="custom-domain"
            className="desk-input"
            placeholder="alphamakerspace.com"
            value={domainInput}
            onChange={(event) => {
              const next = event.target.value;
              setDomainInput(next);
              if (!next.trim()) {
                setHideFromDirectory(false);
              }
            }}
          />
        </div>

        <label className="flex min-w-0 max-w-xl items-start gap-3 text-sm text-ink">
          <input
            className="mt-1 h-4 w-4"
            type="checkbox"
            checked={effectiveHidden}
            disabled={!hasDomainInput}
            onChange={(event) => setHideFromDirectory(event.target.checked)}
          />
          <span>
            <span className="font-semibold">Hide from central directory</span>
            <span className="block text-muted">Available only after a custom domain is set.</span>
          </span>
        </label>

        {hasDomainInput ? (
          <div className="grid min-w-0 gap-3 rounded-md border border-line bg-surface p-3 text-sm text-muted">
            <div className="min-w-0 overflow-x-auto">
              <p className="font-semibold text-ink">Resulting URLs</p>
              <ul className="mt-2 grid gap-1">
                {customDomainUrls.map((url) => (
                  <li className="break-all" key={url}>{url}</li>
                ))}
              </ul>
            </div>
            {visibleRecord ? <DnsRecord record={visibleRecord} /> : null}
            <p>
              TLS and reverse proxy routing must terminate HTTPS for this hostname and forward both
              the public site and <code>/admin</code> staff console to this deployment.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                className="desk-button w-full max-w-full sm:w-auto"
                type="button"
                disabled={verifyDisabled}
                onClick={() => verifyDomain.mutate()}
              >
                {verifyDomain.isPending ? "Checking..." : "Verify domain"}
              </button>
              {token ? <span className="break-all text-xs text-muted">Token: {token}</span> : null}
            </div>
          </div>
        ) : null}
        {domainChanged && currentDomain ? (
          <p className="text-sm text-muted">Save the new domain before verifying DNS.</p>
        ) : null}
        {verifyDetail ? <p className="text-sm text-ink">{verifyDetail}</p> : null}
        {updateCustomDomain.error ? (
          <p className="text-sm text-danger">{updateCustomDomain.error.message}</p>
        ) : null}
        {verifyDomain.error ? (
          <p className="text-sm text-danger">{verifyDomain.error.message}</p>
        ) : null}
      </form>
    </div>
  );
}

function DnsRecord({ record }: { record: DomainRecord }) {
  return (
    <div className="grid min-w-0 gap-2">
      <p className="font-semibold text-ink">DNS TXT record</p>
      <dl className="grid min-w-0 gap-2 sm:grid-cols-[96px_minmax(0,1fr)]">
        <dt className="font-mono text-xs uppercase text-muted">Host</dt>
        <dd className="break-all font-mono text-xs text-ink">{record.host}</dd>
        <dt className="font-mono text-xs uppercase text-muted">Type</dt>
        <dd className="font-mono text-xs text-ink">{record.type}</dd>
        <dt className="font-mono text-xs uppercase text-muted">Value</dt>
        <dd className="break-all font-mono text-xs text-ink">{record.value}</dd>
      </dl>
    </div>
  );
}

function domainStatusTone(status: DomainStatus) {
  return status === "verified" ? "success" : status === "failed" ? "danger" : "warn";
}

function domainStatusLabel(status: DomainStatus) {
  return {
    pending: "Pending",
    verified: "Verified",
    failed: "Failed",
  }[status];
}