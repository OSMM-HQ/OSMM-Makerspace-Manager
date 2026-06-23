import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { MakerspaceBrand } from "../../components/MakerspaceBrand";
import { OsmmBadge } from "../../components/OsmmLogo";
import { Card } from "../../components/ui/Card";
import QrScanner from "../../components/ui/QrScanner";
import { useTenant, useTenantPath } from "../../lib/tenant";
import { formatSlug } from "./PublicInventoryParts";
import { checkoutTool, returnTool } from "./selfCheckoutApi";
import type { PublicToolLoanResult } from "./selfCheckoutApi";
import { invalidatePublicInventory } from "../staff/queryInvalidation";
import { useTenantBootstrap } from "./usePublicInventory";

type Mode = "checkout" | "return";

type MutationInput = {
  payload: string;
};

function formatStatus(status: string) {
  const normalized = status.replace(/_/g, " ");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function ResultCard({ result }: { result: PublicToolLoanResult }) {
  return (
    <div className="rounded-xl border border-tone-mint bg-tone-mint px-3 py-3 text-tone-mint-ink dark:bg-[#06281a] dark:text-[#74dd9c]">
      <p className="text-xs font-semibold tracking-wide">
        {formatStatus(result.status)}
      </p>
      <h2 className="mt-1 text-lg font-semibold">
        {result.items.map((item) => item.product_name).join(", ") || "Tool loan"}
      </h2>
      <div className="mt-3 space-y-2">
        {result.items.map((item) => (
          <div
            className="flex items-center justify-between gap-3 rounded-lg border border-tone-mint-ink/20 bg-panel/80 px-3 py-2 text-sm"
            key={item.product_name}
          >
            <span>{item.product_name}</span>
            <span className="font-semibold">x{item.quantity}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PublicSelfCheckoutPage() {
  const queryClient = useQueryClient();
  const { slug } = useParams();
  const tenant = useTenant();
  const makerspaceSlug = tenant.mode === "single" ? tenant.slug : slug ?? "";
  const tenantPath = useTenantPath(makerspaceSlug);
  const [mode, setMode] = useState<Mode>("checkout");
  const [requesterName, setRequesterName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [scannerOpen, setScannerOpen] = useState(false);

  const bootstrapQuery = useTenantBootstrap(makerspaceSlug, tenant.mode === "central");
  const bootstrap = tenant.mode === "single" ? tenant.bootstrap : bootstrapQuery.data;
  const modules = useMemo(
    () => (tenant.mode === "single" ? tenant.modules : new Set(bootstrap?.modules ?? [])),
    [bootstrap?.modules, tenant],
  );
  const displayName =
    bootstrap?.branding.display_name ||
    bootstrap?.makerspace.name ||
    formatSlug(makerspaceSlug) ||
    "Makerspace";
  const enabled = modules.has("self_checkout");

  const loanMutation = useMutation({
    mutationFn: ({ payload }: MutationInput) =>
      mode === "checkout"
        ? checkoutTool(makerspaceSlug, {
            payload,
            requester_name: requesterName.trim(),
            contact_email: contactEmail.trim(),
            contact_phone: contactPhone.trim(),
          })
        : returnTool(makerspaceSlug, contactEmail.trim(), payload),
    onSuccess: () => invalidatePublicInventory(queryClient, makerspaceSlug),
  });
  const canScan =
    mode === "checkout"
      ? requesterName.trim().length > 0 &&
        contactEmail.trim().length > 0 &&
        contactPhone.trim().length > 0
      : contactEmail.trim().length > 0;

  function scanTool(payload: string) {
    if (!canScan) {
      return;
    }
    setScannerOpen(false);
    loanMutation.mutate({ payload });
  }

  return (
    <main className="desk-shell">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-screen-xl flex-col gap-4 px-5 py-6 sm:px-8">
          <p className="text-sm font-semibold tracking-wide text-accent-ink">
            Public Tool Checkout
          </p>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0">
              <MakerspaceBrand
                name={displayName}
                logoUrl={bootstrap?.makerspace.logo_url}
                size="lg"
              />
              <p className="mt-2 text-sm text-muted">
                Scan a physical tool label to check it out or return it.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <OsmmBadge />
              <Link className="desk-button" to={tenantPath()}>
                Back to inventory
              </Link>
            </div>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-screen-sm px-5 py-6 sm:px-8">
        {bootstrapQuery.isLoading ? (
          <Card>
            <p className="text-sm text-muted">Loading checkout access...</p>
          </Card>
        ) : null}

        {bootstrapQuery.isError ? (
          <Card>
            <p className="text-sm text-danger">Could not load checkout access. Try again in a moment.</p>
          </Card>
        ) : null}
        {!bootstrapQuery.isLoading && !bootstrapQuery.isError && !enabled ? (
          <Card>
            <p className="text-xs font-semibold tracking-wide text-accent-ink">
              Self-checkout
            </p>
            <h2 className="mt-2 text-xl font-semibold text-ink">
              Self-checkout is not enabled for this makerspace.
            </h2>
            <Link className="desk-button mt-4" to={tenantPath()}>
              Back to inventory
            </Link>
          </Card>
        ) : null}

        {!bootstrapQuery.isLoading && !bootstrapQuery.isError && enabled ? (
          <Card>
            <div
              aria-label="Checkout mode"
              className="desk-panel mt-4 flex gap-1 p-1"
              role="tablist"
            >
              <button
                aria-selected={mode === "checkout"}
                className={
                  mode === "checkout" ? "desk-tab desk-tab-active" : "desk-tab"
                }
                role="tab"
                type="button"
                onClick={() => setMode("checkout")}
              >
                Use (check out)
              </button>
              <button
                aria-selected={mode === "return"}
                className={
                  mode === "return" ? "desk-tab desk-tab-active" : "desk-tab"
                }
                role="tab"
                type="button"
                onClick={() => setMode("return")}
              >
                Return
              </button>
            </div>

            {mode === "checkout" ? (
              <label className="mt-4 block">
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
            ) : null}

            <label className="mt-4 block">
              <span className="mb-1 block text-xs font-semibold tracking-wide text-muted">
                Email
              </span>
              <input
                className="desk-input w-full"
                placeholder="you@example.com"
                required
                type="email"
                value={contactEmail}
                onChange={(event) => setContactEmail(event.target.value)}
              />
            </label>

            {mode === "checkout" ? (
              <label className="mt-4 block">
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
            ) : null}

            <button
              className="desk-button-primary mt-4 w-full disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canScan || loanMutation.isPending}
              type="button"
              onClick={() => setScannerOpen(true)}
            >
              {loanMutation.isPending ? "Submitting..." : "Scan QR"}
            </button>

            {loanMutation.isError ? (
              <p className="mt-4 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
                {loanMutation.error.message}
              </p>
            ) : null}

            {loanMutation.isSuccess ? (
              <div className="mt-4">
                <ResultCard result={loanMutation.data} />
              </div>
            ) : null}
          </Card>
        ) : null}
      </section>

      {scannerOpen ? (
        <QrScanner onClose={() => setScannerOpen(false)} onScan={scanTool} />
      ) : null}
    </main>
  );
}
