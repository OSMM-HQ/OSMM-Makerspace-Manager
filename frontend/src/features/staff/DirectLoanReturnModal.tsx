import { useState } from "react";
import type React from "react";

import { Modal } from "../../components/ui/Modal";
import QrScanner from "../../components/ui/QrScanner";
import { EvidenceUpload } from "./panels/EvidenceUpload";

type ReturnLoan = {
  id: number;
  target_label: string;
  return_scan_required?: boolean;
};

type DirectLoanReturnModalProps = {
  loan: ReturnLoan | null;
  makerspaceId: number;
  evidenceId: number | null;
  notes: string;
  qrPayload: string;
  pending: boolean;
  error: string;
  onEvidenceUploaded: (evidenceId: number | null) => void;
  onNotesChange: (notes: string) => void;
  onQrPayloadChange: (payload: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
};

export function DirectLoanReturnModal({
  loan,
  makerspaceId,
  evidenceId,
  notes,
  qrPayload,
  pending,
  error,
  onEvidenceUploaded,
  onNotesChange,
  onQrPayloadChange,
  onCancel,
  onSubmit,
}: DirectLoanReturnModalProps) {
  const [showScanner, setShowScanner] = useState(false);
  const scanRequired = Boolean(loan?.return_scan_required);
  const canSubmit = evidenceId !== null && notes.trim().length > 0 && (!scanRequired || qrPayload.trim().length > 0) && !pending;

  return (
    <Modal
      open={Boolean(loan)}
      onClose={() => {
        if (!pending) onCancel();
      }}
      title={loan ? `Return ${loan.target_label}` : "Return direct handout"}
      footer={
        <div className="desk-actions flex flex-wrap justify-end gap-2">
          <button className="desk-button" type="button" disabled={pending} onClick={onCancel}>
            Cancel
          </button>
          <button className="desk-button" type="submit" form="direct-loan-return-form" disabled={!canSubmit}>
            {pending ? "Returning..." : "Submit return"}
          </button>
        </div>
      }
    >
      <form
        id="direct-loan-return-form"
        className="grid gap-3"
        onSubmit={(event: React.FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          if (canSubmit) onSubmit();
        }}
      >
        <div className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Return photo</span>
          <EvidenceUpload
            makerspaceId={makerspaceId}
            evidenceType="return"
            disabled={pending}
            onUploaded={onEvidenceUploaded}
          />
        </div>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Return QR scan{scanRequired ? "" : " (optional)"}</span>
          <div className="flex flex-col gap-2 md:flex-row">
            <input
              className="desk-input w-full font-mono text-sm"
              value={qrPayload}
              disabled={pending}
              onChange={(event) => onQrPayloadChange(event.target.value)}
            />
            <button className="desk-button" type="button" disabled={pending} onClick={() => setShowScanner(true)}>
              Scan QR
            </button>
          </div>
        </label>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Return notes</span>
          <textarea
            className="desk-input min-h-24 w-full resize-y"
            value={notes}
            disabled={pending}
            onChange={(event) => onNotesChange(event.target.value)}
          />
        </label>
        {error ? <p className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p> : null}
        {showScanner ? (
          <QrScanner
            onScan={(payload) => {
              onQrPayloadChange(payload.trim());
              setShowScanner(false);
            }}
            onClose={() => setShowScanner(false)}
          />
        ) : null}
      </form>
    </Modal>
  );
}
