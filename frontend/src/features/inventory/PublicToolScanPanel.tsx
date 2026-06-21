import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { Card } from "../../components/ui/Card";
import QrScanner from "../../components/ui/QrScanner";
import type { PublicToolLoan } from "../../types/inventory";
import { publicToolCheckout, publicToolReturn } from "./api";

type PublicToolScanPanelProps = {
  identifier: string;
  makerspaceSlug: string;
};

function LoanResult({ loan }: { loan: PublicToolLoan }) {
  return (
    <div className="rounded-xl border border-tone-mint bg-tone-mint px-3 py-2 text-tone-mint-ink dark:bg-[#06281a] dark:text-[#74dd9c]">
      <p className="text-sm font-semibold capitalize">
        {loan.status.replace(/_/g, " ")}: {loan.target_label}
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
  identifier,
  makerspaceSlug,
}: PublicToolScanPanelProps) {
  const [payload, setPayload] = useState("");
  const [scannerOpen, setScannerOpen] = useState(false);
  const checkout = useMutation({
    mutationFn: () =>
      publicToolCheckout(makerspaceSlug, {
        identifier: identifier.trim(),
        payload: payload.trim(),
      }),
  });
  const returnTool = useMutation({
    mutationFn: () =>
      publicToolReturn(makerspaceSlug, {
        identifier: identifier.trim(),
        payload: payload.trim(),
      }),
  });
  const disabled = !identifier.trim() || !payload.trim();
  const error = checkout.error?.message ?? returnTool.error?.message;
  const result = checkout.data ?? returnTool.data;

  return (
    <Card>
      <p className="text-xs font-semibold tracking-wide text-accent-ink">
        QR Tool Checkout
      </p>
      <h2 className="mt-2 text-xl font-semibold text-ink">Scan public tool</h2>
      <p className="mt-2 text-sm leading-6 text-muted">
        Use your Check-In email or phone above, then scan or paste the tool QR payload.
      </p>
      <button
        className="desk-button mt-4 w-full"
        disabled={!identifier.trim()}
        type="button"
        onClick={() => setScannerOpen(true)}
      >
        Scan QR with camera
      </button>
      <input
        className="desk-input mt-2 w-full"
        placeholder="…or paste a tool, asset, or box QR payload"
        value={payload}
        onChange={(event) => setPayload(event.target.value)}
      />
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          className="desk-button-primary disabled:cursor-not-allowed disabled:opacity-50"
          disabled={disabled || checkout.isPending}
          type="button"
          onClick={() => checkout.mutate()}
        >
          {checkout.isPending ? "Checking out..." : "Check out"}
        </button>
        <button
          className="desk-button"
          disabled={disabled || returnTool.isPending}
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
            setPayload(scanned);
            setScannerOpen(false);
          }}
        />
      ) : null}
    </Card>
  );
}
