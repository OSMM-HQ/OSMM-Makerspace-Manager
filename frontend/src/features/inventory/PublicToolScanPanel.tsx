import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { Card } from "../../components/ui/Card";
import QrScanner from "../../components/ui/QrScanner";
import type { PublicToolLoan } from "../../types/inventory";
import { publicToolCheckout, publicToolReturn } from "./api";

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
  // A camera-scanned token is held here, NOT shown in the visible input - the QR
  // payload is an opaque physical-possession token, not something to render.
  const [scannedToken, setScannedToken] = useState("");
  const [scannerOpen, setScannerOpen] = useState(false);
  const effectivePayload = scannedToken.trim();
  const checkout = useMutation({
    mutationFn: () =>
      publicToolCheckout(makerspaceSlug, {
        payload: effectivePayload,
        requester_name: requesterName.trim(),
        contact_email: contactEmail.trim(),
        contact_phone: contactPhone.trim(),
      }),
  });
  const returnTool = useMutation({
    mutationFn: () =>
      publicToolReturn(makerspaceSlug, {
        identifier: contactEmail.trim(),
        payload: effectivePayload,
      }),
  });
  const checkoutDisabled =
    !requesterName.trim() ||
    !contactEmail.trim() ||
    !contactPhone.trim() ||
    !effectivePayload;
  const returnDisabled = !contactEmail.trim() || !effectivePayload;
  const error = checkout.error?.message ?? returnTool.error?.message;
  const result = checkout.data ?? returnTool.data;

  return (
    <Card>
      <p className="text-xs font-semibold tracking-wide text-accent-ink">
        QR Tool Checkout
      </p>
      <h2 className="mt-2 text-xl font-semibold text-ink">Scan public tool</h2>
      <p className="mt-2 text-sm leading-6 text-muted">
        Use your email above, then scan the tool QR with your camera.
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
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          className="desk-button-primary disabled:cursor-not-allowed disabled:opacity-50"
          disabled={checkoutDisabled || checkout.isPending}
          type="button"
          onClick={() => checkout.mutate()}
        >
          {checkout.isPending ? "Checking out..." : "Check out"}
        </button>
        <button
          className="desk-button"
          disabled={returnDisabled || returnTool.isPending}
          type="button"
          onClick={() => returnTool.mutate()}
        >
          {returnTool.isPending ? "Returning..." : "Return"}
        </button>
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
