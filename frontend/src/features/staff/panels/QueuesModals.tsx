import type React from "react";
import { useEffect, useState } from "react";

import { Modal } from "../../../components/ui/Modal";
import QrScanner from "../../../components/ui/QrScanner";
import { staffRequest } from "../../../lib/api";
import { EvidenceUpload } from "./EvidenceUpload";
import type { HardwareRequest } from "./Queues";

export type ReturnDueValues = {
  returnDueAt: string;
};

export type RejectRequestValues = {
  reason: string;
};

export type IssueReject = {
  item_id: number;
  broken: number;
  disposition: "needs_fix" | "remove";
};

export type AssignIssueValues = {
  boxCode: string;
  evidenceId: number;
  remark: string;
  rejects: IssueReject[];
  assetQrPayloads: string[];
};

export type ReturnRequestValues = {
  evidenceId: number;
  boxCode: string;
  remark: string;
  resolutions: Array<{ item_id: number; returned: number; damaged: number; missing: number }>;
};

type FormModalProps<T> = {
  row: HardwareRequest | null;
  open: boolean;
  pending: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (values: T) => void;
};

export function ReturnDueModal({
  row,
  open,
  pending,
  error,
  defaultValue,
  onClose,
  onSubmit,
}: FormModalProps<ReturnDueValues> & { defaultValue: string }) {
  const [returnDueAt, setReturnDueAt] = useState(defaultValue);

  useEffect(() => {
    if (open) setReturnDueAt(defaultValue);
  }, [defaultValue, open]);

  return (
    <Modal open={open} onClose={onClose} title={row ? `Set due for request #${row.id}` : "Set due"} footer={<FormFooter formId="return-due-form" pending={pending} submitLabel="Save due date" onCancel={onClose} />}>
      <form id="return-due-form" className="grid gap-3" onSubmit={(event) => submitForm(event, () => onSubmit({ returnDueAt }))}>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Return due date and time</span>
          <input className="desk-input" type="datetime-local" value={returnDueAt} disabled={pending} onChange={(event) => setReturnDueAt(event.target.value)} />
        </label>
        <ErrorText message={error} />
      </form>
    </Modal>
  );
}

export function RejectRequestModal({ row, open, pending, error, onClose, onSubmit }: FormModalProps<RejectRequestValues>) {
  const [reason, setReason] = useState("");
  const [validationError, setValidationError] = useState("");

  useEffect(() => {
    if (open) {
      setReason("");
      setValidationError("");
    }
  }, [open]);

  return (
    <Modal open={open} onClose={onClose} title={row ? `Reject request #${row.id}` : "Reject request"} footer={<FormFooter formId="reject-request-form" pending={pending} submitLabel="Reject request" onCancel={onClose} tone="danger" />}>
      <form
        id="reject-request-form"
        className="grid gap-3"
        onSubmit={(event) =>
          submitForm(event, () => {
            if (!reason.trim()) {
              setValidationError("Reason is required.");
              return;
            }
            onSubmit({ reason: reason.trim() });
          })
        }
      >
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Reason</span>
          <textarea className="desk-input min-h-24 w-full resize-y" value={reason} disabled={pending} onChange={(event) => setReason(event.target.value)} />
        </label>
        <ErrorText message={validationError || error} />
      </form>
    </Modal>
  );
}

type ScannedAsset = { payload: string; label: string };

export function AssignIssueModal({ row, open, pending, error, onClose, onSubmit, makerspaceId }: FormModalProps<AssignIssueValues> & { makerspaceId: number }) {
  const [boxCode, setBoxCode] = useState(row?.assigned_box?.code ?? "");
  const [evidenceId, setEvidenceId] = useState<number | null>(null);
  const [remark, setRemark] = useState("Issued from staff app.");
  const [rejects, setRejects] = useState<Record<number, { broken: number; disposition: "needs_fix" | "remove" }>>({});
  const [scanned, setScanned] = useState<ScannedAsset[]>([]);
  const [showScanner, setShowScanner] = useState(false);
  const [validationError, setValidationError] = useState("");

  // Individual-tracked items must be issued with one AVAILABLE asset QR per accepted unit
  // (backend _issue_individual_assets expects exactly sum(accepted_quantity) payloads). The
  // count is aggregate across all such items; broken-reject is blocked for them server-side.
  const requiredScans = (row?.items ?? [])
    .filter((item) => item.requires_asset_qr)
    .reduce((sum, item) => sum + item.accepted_quantity, 0);

  useEffect(() => {
    if (open) {
      setBoxCode(row?.assigned_box?.code ?? "");
      setEvidenceId(null);
      setRemark("Issued from staff app.");
      setRejects({});
      setScanned([]);
      setShowScanner(false);
      setValidationError("");
    }
  }, [open, row]);

  const handleScan = async (payload: string) => {
    const clean = payload.trim();
    if (!clean || scanned.some((item) => item.payload === clean)) return;
    let label = clean;
    try {
      const result = await staffRequest<{ target: { type: string; product?: string; asset_tag?: string } }>("/admin/qr/resolve", {
        method: "POST",
        body: JSON.stringify({ payload: clean }),
      });
      label = result.target.product || result.target.asset_tag || clean;
    } catch {
      label = clean;
    }
    setScanned((items) => (items.some((item) => item.payload === clean) ? items : [...items, { payload: clean, label }]));
  };
  const removeScanned = (payload: string) => setScanned((items) => items.filter((item) => item.payload !== payload));

  const setBroken = (itemId: number, broken: number) =>
    setRejects((current) => ({
      ...current,
      [itemId]: { broken: Math.max(0, broken || 0), disposition: current[itemId]?.disposition ?? "needs_fix" },
    }));
  const setDisposition = (itemId: number, disposition: "needs_fix" | "remove") =>
    setRejects((current) => ({
      ...current,
      [itemId]: { broken: current[itemId]?.broken ?? 0, disposition },
    }));

  return (
    <Modal open={open} onClose={onClose} title={row ? `Assign and issue request #${row.id}` : "Assign and issue"} footer={<FormFooter formId="assign-issue-form" pending={pending} submitLabel="Assign + issue" onCancel={onClose} />}>
      <form
        id="assign-issue-form"
        className="grid gap-3"
        onSubmit={(event) =>
          submitForm(event, () => {
            if (!boxCode.trim()) {
              setValidationError("Box QR code is required.");
              return;
            }
            if (evidenceId === null) {
              setValidationError("Upload an issue photo before issuing.");
              return;
            }
            const overflow = (row?.items ?? []).find(
              (item) => (rejects[item.id]?.broken ?? 0) > item.accepted_quantity,
            );
            if (overflow) {
              setValidationError(`Can't reject more than ${overflow.accepted_quantity} of ${overflow.product_name}.`);
              return;
            }
            if (scanned.length !== requiredScans) {
              setValidationError(`Scan exactly ${requiredScans} asset QR code(s) for the individually-tracked items (scanned ${scanned.length}).`);
              return;
            }
            const rejectList = Object.entries(rejects)
              .filter(([, value]) => value.broken > 0)
              .map(([itemId, value]) => ({ item_id: Number(itemId), broken: value.broken, disposition: value.disposition }));
            onSubmit({ boxCode: boxCode.trim(), evidenceId, remark, rejects: rejectList, assetQrPayloads: scanned.map((item) => item.payload) });
          })
        }
      >
        {row?.assigned_box ? (
          <p className="text-xs text-muted">Box: <span className="font-medium text-ink">{row.assigned_box.label} ({row.assigned_box.code})</span></p>
        ) : null}
        <BoxCodeField value={boxCode} onChange={setBoxCode} makerspaceId={makerspaceId} pending={pending} />
        <div className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Issue photo</span>
          <EvidenceUpload makerspaceId={makerspaceId} evidenceType="issue" disabled={pending} onUploaded={setEvidenceId} />
        </div>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Remark</span>
          <textarea className="desk-input min-h-20 w-full resize-y" value={remark} disabled={pending} onChange={(event) => setRemark(event.target.value)} />
        </label>
        {requiredScans > 0 ? (
          <div className="grid gap-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium text-ink">Scan asset QR codes ({scanned.length}/{requiredScans})</p>
              <button className="desk-button" type="button" disabled={pending} onClick={() => setShowScanner(true)}>Scan asset QR</button>
            </div>
            <p className="text-xs text-muted">Individually-tracked items need one AVAILABLE asset QR scanned per accepted unit.</p>
            {scanned.length ? (
              <div className="flex flex-wrap gap-2">
                {scanned.map((item) => (
                  <span key={item.payload} className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-1 text-sm text-ink">
                    {item.label}
                    <button className="text-muted hover:text-danger" type="button" disabled={pending} onClick={() => removeScanned(item.payload)}>Remove</button>
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="grid gap-2">
          <p className="text-sm font-medium text-ink">Items — reject any broken units</p>
          {row?.items.map((item) => {
            const reject = rejects[item.id];
            const broken = reject?.broken ?? 0;
            // Individual-tracked items can't be rejected-as-broken at handover (backend rule):
            // they're issued as scanned asset rows and marked damaged on the specific unit at
            // return. Show them read-only here so staff aren't offered an action that 400s.
            if (item.requires_asset_qr) {
              return (
                <div key={item.id} className="rounded-md border border-line p-2">
                  <p className="text-sm font-medium text-ink">{item.product_name} <span className="text-muted">×{item.accepted_quantity}</span></p>
                  <p className="mt-1 text-xs text-muted">Individually tracked — issued by asset QR scan above.</p>
                </div>
              );
            }
            return (
              <div key={item.id} className="rounded-md border border-line p-2">
                <p className="text-sm font-medium text-ink">{item.product_name} <span className="text-muted">×{item.accepted_quantity}</span></p>
                <div className="mt-2 grid gap-2 sm:grid-cols-[auto_1fr] sm:items-end">
                  <label className="grid gap-1 text-xs text-muted">
                    <span>Reject as broken</span>
                    <input className="desk-input w-24" type="number" min="0" max={item.accepted_quantity} value={broken} disabled={pending} onChange={(event) => setBroken(item.id, Number(event.target.value))} />
                  </label>
                  {broken > 0 ? (
                    <label className="grid gap-1 text-xs text-muted">
                      <span>Send broken units to</span>
                      <select className="desk-input" value={reject?.disposition ?? "needs_fix"} disabled={pending} onChange={(event) => setDisposition(item.id, event.target.value as "needs_fix" | "remove")}>
                        <option value="needs_fix">To-be-fixed shelf</option>
                        <option value="remove">Remove from inventory</option>
                      </select>
                    </label>
                  ) : null}
                </div>
                {broken > 0 ? (
                  <p className="mt-1 text-xs text-muted">Issuing {Math.max(0, item.accepted_quantity - broken)}, {broken} not handed over.</p>
                ) : null}
              </div>
            );
          })}
        </div>
        {showScanner ? <QrScanner onScan={handleScan} onClose={() => setShowScanner(false)} /> : null}
        <ErrorText message={validationError || error} />
      </form>
    </Modal>
  );
}

export function ReturnRequestModal({ row, open, pending, error, onClose, onSubmit, makerspaceId }: FormModalProps<ReturnRequestValues> & { makerspaceId: number }) {
  const [evidenceId, setEvidenceId] = useState<number | null>(null);
  const [boxCode, setBoxCode] = useState(row?.assigned_box?.code ?? "");
  const [remark, setRemark] = useState("");
  const [resolutions, setResolutions] = useState<ReturnRequestValues["resolutions"]>([]);
  const [validationError, setValidationError] = useState("");
  const [issueUrl, setIssueUrl] = useState("");

  useEffect(() => {
    if (!open || !row) {
      setIssueUrl("");
      return;
    }
    setEvidenceId(null);
    setBoxCode(row.assigned_box?.code ?? "");
    setRemark("");
    setValidationError("");
    setIssueUrl("");
    setResolutions(row.items.map((item) => ({
      item_id: item.id,
      returned: item.issued_quantity - item.returned_quantity - item.damaged_quantity - item.missing_quantity,
      damaged: 0,
      missing: 0,
    })));
  }, [open, row]);

  useEffect(() => {
    if (!open || !row?.issue_evidence_id) {
      setIssueUrl("");
      return;
    }

    let cancelled = false;
    staffRequest<{ url: string }>(`/admin/evidence/${row.issue_evidence_id}`)
      .then((result) => {
        if (!cancelled) setIssueUrl(result.url);
      })
      .catch(() => {
        if (!cancelled) setIssueUrl("");
      });

    return () => {
      cancelled = true;
    };
  }, [open, row?.issue_evidence_id]);

  const updateResolution = (itemId: number, key: "returned" | "damaged" | "missing", value: string) => {
    setResolutions((current) => current.map((resolution) => (resolution.item_id === itemId ? { ...resolution, [key]: Number(value) || 0 } : resolution)));
  };

  return (
    <Modal open={open} onClose={onClose} title={row ? `Return request #${row.id}` : "Return request"} footer={<FormFooter formId="return-request-form" pending={pending} submitLabel="Submit return" onCancel={onClose} />}>
      <form
        id="return-request-form"
        className="grid gap-3"
        onSubmit={(event) =>
          submitForm(event, () => {
            if (evidenceId === null) {
              setValidationError("Upload a return photo before submitting.");
              return;
            }
            if (!remark.trim()) {
              setValidationError("Return remark is required.");
              return;
            }
            if (resolutions.some((resolution) => !Number.isFinite(resolution.returned) || !Number.isFinite(resolution.damaged) || !Number.isFinite(resolution.missing))) {
              setValidationError("Resolution quantities must be numbers.");
              return;
            }
            if (resolutions.some((resolution) => resolution.returned < 0 || resolution.damaged < 0 || resolution.missing < 0)) {
              setValidationError("Resolution quantities cannot be negative.");
              return;
            }
            onSubmit({ evidenceId, boxCode: boxCode.trim(), remark: remark.trim(), resolutions });
          })
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {issueUrl ? (
            <div className="grid gap-1 text-sm">
              <span className="font-medium text-ink">Issue photo (for comparison)</span>
              <img
                src={issueUrl}
                alt="Issue photo for comparison"
                className="max-h-56 w-full rounded-md border border-line object-contain"
              />
            </div>
          ) : null}
          <div className="grid gap-1 text-sm">
            <span className="font-medium text-ink">Return photo</span>
            <EvidenceUpload makerspaceId={makerspaceId} evidenceType="return" disabled={pending} onUploaded={setEvidenceId} />
          </div>
          <BoxCodeField value={boxCode} onChange={setBoxCode} makerspaceId={makerspaceId} pending={pending} />
        </div>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Remark</span>
          <textarea className="desk-input min-h-20 w-full resize-y" value={remark} disabled={pending} onChange={(event) => setRemark(event.target.value)} />
        </label>
        <div className="grid gap-2">
          <p className="text-sm font-medium text-ink">Resolution quantities</p>
          {row?.items.map((item) => {
            const resolution = resolutions.find((entry) => entry.item_id === item.id);
            return (
              <div key={item.id} className="rounded-md border border-line p-2">
                <p className="text-sm font-medium text-ink">{item.product_name}</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-3">
                  {(["returned", "damaged", "missing"] as const).map((key) => (
                    <label key={key} className="grid gap-1 text-xs text-muted">
                      <span className="capitalize">{key}</span>
                      <input className="desk-input" type="number" min="0" value={resolution?.[key] ?? 0} disabled={pending} onChange={(event) => updateResolution(item.id, key, event.target.value)} />
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <ErrorText message={validationError || error} />
      </form>
    </Modal>
  );
}

type ContainerOption = { id: number; code?: string | null; label: string; is_active?: boolean };

// Box QR code field shared by the assign-issue and return modals: manual entry, a camera
// scan that resolves a box QR to its code, and a dropdown of the makerspace's ACTIVE
// containers — all three write the same box code so staff can pick whichever is fastest.
function BoxCodeField({ value, onChange, makerspaceId, pending }: { value: string; onChange: (code: string) => void; makerspaceId: number; pending: boolean }) {
  const [containers, setContainers] = useState<ContainerOption[]>([]);
  const [scanOpen, setScanOpen] = useState(false);
  const [scanError, setScanError] = useState("");

  useEffect(() => {
    let cancelled = false;
    staffRequest<{ results: ContainerOption[] }>(`/admin/makerspace/${makerspaceId}/containers`)
      .then((res) => {
        if (!cancelled) setContainers((res.results ?? []).filter((c) => c.is_active !== false && c.code));
      })
      .catch(() => {
        if (!cancelled) setContainers([]);
      });
    return () => {
      cancelled = true;
    };
  }, [makerspaceId]);

  const handleScan = async (payload: string) => {
    setScanOpen(false);
    const clean = payload.trim();
    if (!clean) return;
    try {
      const res = await staffRequest<{ target: { type: string; code?: string } }>("/admin/qr/resolve", {
        method: "POST",
        body: JSON.stringify({ payload: clean }),
      });
      if (res.target.type === "box" && res.target.code) {
        onChange(res.target.code);
        setScanError("");
      } else {
        setScanError("Scanned QR is not a box/container.");
      }
    } catch {
      setScanError("Could not resolve the scanned QR.");
    }
  };

  return (
    <div className="grid gap-1 text-sm">
      <span className="font-medium text-ink">Box QR code</span>
      <div className="flex flex-wrap gap-2">
        <input className="desk-input min-w-0 flex-1" value={value} disabled={pending} onChange={(event) => onChange(event.target.value)} />
        <button className="desk-button" type="button" disabled={pending} onClick={() => setScanOpen(true)}>Scan</button>
      </div>
      {containers.length ? (
        <select
          className="desk-input"
          value=""
          disabled={pending}
          onChange={(event) => {
            if (event.target.value) onChange(event.target.value);
          }}
        >
          <option value="">Choose an available container…</option>
          {containers.map((container) => (
            <option key={container.id} value={container.code ?? ""}>
              {container.label}{container.code ? ` (${container.code})` : ""}
            </option>
          ))}
        </select>
      ) : null}
      {scanError ? <p className="text-xs text-danger">{scanError}</p> : null}
      {scanOpen ? <QrScanner onScan={handleScan} onClose={() => setScanOpen(false)} /> : null}
    </div>
  );
}

function FormFooter({ formId, pending, submitLabel, tone = "default", onCancel }: { formId: string; pending: boolean; submitLabel: string; tone?: "danger" | "default"; onCancel: () => void }) {
  return (
    <div className="desk-actions flex flex-wrap justify-end gap-2">
      <button className="desk-button" type="button" disabled={pending} onClick={onCancel}>
        Cancel
      </button>
      <button className={tone === "danger" ? "desk-button bg-danger text-bg hover:bg-danger/90 hover:text-bg" : "desk-button"} type="submit" form={formId} disabled={pending}>
        {pending ? "Working..." : submitLabel}
      </button>
    </div>
  );
}

function ErrorText({ message }: { message: string }) {
  return message ? <p className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{message}</p> : null;
}

function submitForm(event: React.FormEvent<HTMLFormElement>, submit: () => void) {
  event.preventDefault();
  submit();
}
