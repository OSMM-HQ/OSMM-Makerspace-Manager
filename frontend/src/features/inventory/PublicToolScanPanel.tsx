import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Card } from "../../components/ui/Card";
import QrScanner from "../../components/ui/QrScanner";
import type { PublicToolLoan } from "../../types/inventory";
import { invalidatePublicInventory } from "../staff/queryInvalidation";
import { publicToolCheckout, publicToolReturn } from "./api";
import { PublicEvidenceUpload } from "./PublicEvidenceUpload";

type PublicToolScanPanelProps = {
  requesterName: string;
  contactEmail: string;
  contactPhone: string;
  makerspaceSlug: string;
};

function LoanResult({ loan }: { loan: PublicToolLoan }) {
  return (
    <div className="rounded-xl border border-tone-mint bg-tone-mint px-3 py-2 text-tone-mint-ink dark:bg-[#06281a] dark:text-[#74dd9c]">
      <p className="text-sm font-semibold capitalize">
        {loan.status.replace(/_/g, " ")}: {loan.items.map((item) => item.product_name).join(", ") || "Tool loan"}
      </p>
      <p className="mt-1 break-all text-xs">{loan.public_token}</p>
      <div className="mt-2 space-y-1">
        {loan.items.map((item) => (
          <div className="flex justify-between gap-3 text-xs" key={item.product_name}>
            <span>{item.product_name}</span>
            <span>x{item.quantity}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PublicToolScanPanel({
  requesterName,
  contactEmail,
  contactPhone,
  makerspaceSlug,
}: PublicToolScanPanelProps) {
  const queryClient = useQueryClient();
  const [scannedToken, setScannedToken] = useState("");
  const [scannerOpen, setScannerOpen] = useState(false);
  const [issueEvidenceId, setIssueEvidenceId] = useState<number | null>(null);
  const [returnEvidenceId, setReturnEvidenceId] = useState<number | null>(null);
  const [returnRemark, setReturnRemark] = useState("");
  const [uploadKey, setUploadKey] = useState(0);
  const effectivePayload = scannedToken.trim();
  const checkout = useMutation({
    mutationFn: () =>
      publicToolCheckout(makerspaceSlug, {
        payload: effectivePayload,
        requester_name: requesterName.trim(),
        contact_email: contactEmail.trim(),
        contact_phone: contactPhone.trim(),
        evidence_id: issueEvidenceId as number,
      }),
    onSuccess: () => {
      invalidatePublicInventory(queryClient, makerspaceSlug);
      setIssueEvidenceId(null);
      setUploadKey((key) => key + 1);
    },
  });
  const returnTool = useMutation({
    mutationFn: () =>
      publicToolReturn(makerspaceSlug, {
        identifier: contactEmail.trim(),
        payload: effectivePayload,
        evidence_id: returnEvidenceId as number,
        remark: returnRemark.trim(),
      }),
    onSuccess: () => {
      invalidatePublicInventory(queryClient, makerspaceSlug);
      setReturnEvidenceId(null);
      setReturnRemark("");
      setUploadKey((key) => key + 1);
    },
  });
  const checkoutDisabled =
    !requesterName.trim() ||
    !contactEmail.trim() ||
    !contactPhone.trim() ||
    !effectivePayload ||
    issueEvidenceId === null;
  const returnDisabled =
    !contactEmail.trim() ||
    !effectivePayload ||
    returnEvidenceId === null ||
    !returnRemark.trim();
  const error = checkout.error?.message ?? returnTool.error?.message;
  const result = checkout.data ?? returnTool.data;

  return (
    <Card>
      <p className="text-xs font-semibold tracking-wide text-accent-ink">
        QR Tool Checkout
      </p>
      <h2 className="mt-2 text-xl font-semibold text-ink">Scan public tool</h2>
      <p className="mt-2 text-sm leading-6 text-muted">
        Use your email above, upload the required photo, then scan the tool QR with your camera.
      </p>
      <button
        className="desk-button mt-4 w-full"
        disabled={!contactEmail.trim()}
        type="button"
        onClick={() => setScannerOpen(true)}
      >
        Scan QR with camera
      </button>
      {scannedToken ? (
        <p className="mt-2 inline-flex items-center gap-2 rounded-lg border border-tone-mint bg-tone-mint px-3 py-1 text-sm font-semibold text-tone-mint-ink dark:bg-[#06281a] dark:text-[#74dd9c]">
          Scanned OK
          <button
            type="button"
            className="text-xs font-normal underline"
            onClick={() => setScannedToken("")}
          >
            clear
          </button>
        </p>
      ) : null}
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border border-line p-3">
          <h3 className="text-sm font-semibold text-ink">Check out</h3>
          <div className="mt-3">
            <PublicEvidenceUpload
              key={`issue-${uploadKey}`}
              slug={makerspaceSlug}
              identifier={contactEmail}
              evidenceType="issue"
              disabled={!contactEmail.trim() || checkout.isPending}
              onUploaded={setIssueEvidenceId}
            />
          </div>
          <button
            className="desk-button-primary mt-3 w-full disabled:cursor-not-allowed disabled:opacity-50"
            disabled={checkoutDisabled || checkout.isPending}
            type="button"
            onClick={() => checkout.mutate()}
          >
            {checkout.isPending ? "Checking out..." : "Check out"}
          </button>
        </section>
        <section className="rounded-lg border border-line p-3">
          <h3 className="text-sm font-semibold text-ink">Return</h3>
          <div className="mt-3">
            <PublicEvidenceUpload
              key={`return-${uploadKey}`}
              slug={makerspaceSlug}
              identifier={contactEmail}
              evidenceType="return"
              disabled={!contactEmail.trim() || returnTool.isPending}
              onUploaded={setReturnEvidenceId}
            />
          </div>
          <label className="mt-3 block">
            <span className="mb-1 block text-xs font-semibold tracking-wide text-muted">
              Return condition notes
            </span>
            <textarea
              className="desk-input min-h-20 w-full"
              value={returnRemark}
              onChange={(event) => setReturnRemark(event.target.value)}
            />
          </label>
          <button
            className="desk-button mt-3 w-full disabled:cursor-not-allowed disabled:opacity-50"
            disabled={returnDisabled || returnTool.isPending}
            type="button"
            onClick={() => returnTool.mutate()}
          >
            {returnTool.isPending ? "Returning..." : "Return"}
          </button>
        </section>
      </div>
      {error ? (
        <p className="mt-3 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      ) : null}
      {result ? (
        <div className="mt-3">
          <LoanResult loan={result} />
        </div>
      ) : null}
      {scannerOpen ? (
        <QrScanner
          onClose={() => setScannerOpen(false)}
          onScan={(scanned) => {
            setScannedToken(scanned);
            setScannerOpen(false);
          }}
        />
      ) : null}
    </Card>
  );
}
