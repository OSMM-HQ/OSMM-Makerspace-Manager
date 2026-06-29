import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import QrScanner from "../../components/ui/QrScanner";
import { Pagination } from "../../components/ui/Pagination";
import { staffRequest } from "../../lib/api";
import { usePaginatedQuery } from "../../lib/usePaginatedQuery";
import { DirectLoanList, type DirectLoan } from "./DirectLoanList";
import { invalidateInventoryViews } from "./queryInvalidation";
import { DirectLoanReturnModal } from "./DirectLoanReturnModal";
import { Panel, type Makerspace, useStaffGet } from "./StaffPanels";
import { EvidenceUpload } from "./panels/EvidenceUpload";

type ProductOption = {
  id: number;
  name: string;
  storage_location: string;
  available_quantity: number;
  tracking_mode: string;
  is_public: boolean;
  public_self_checkout_enabled: boolean;
  is_archived: boolean;
};
type ContainerOption = { id: number; label: string };
type ContainerResponse = ContainerOption[] | { results: ContainerOption[] };
type VerifyResponse = { username: string };
type LineDraft = { key: number; productId: string; quantity: string };
type ScannedPayload = { payload: string; label: string };
type ReturnLoanPayload = { loanId: number; evidenceId: number; notes: string; qrPayload: string };
type QrResolveResponse = {
  target:
    | { type: "product"; id: number; name: string }
    | { type: "asset"; id: number; asset_tag: string; product: string; status: string }
    | { type: "box"; id: number; label: string; code: string };
};

export function DirectLoans({ makerspace }: { makerspace: Makerspace }) {
  const queryClient = useQueryClient();
  const [requesterName, setRequesterName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [lineRows, setLineRows] = useState<LineDraft[]>([{ key: 1, productId: "", quantity: "1" }]);
  const [nextLineKey, setNextLineKey] = useState(2);
  const [scanned, setScanned] = useState<ScannedPayload[]>([]);
  const [showScanner, setShowScanner] = useState(false);
  const [qrPayloads, setQrPayloads] = useState("");
  const [containerId, setContainerId] = useState("");
  const [showContainerScanner, setShowContainerScanner] = useState(false);
  const [containerScanError, setContainerScanError] = useState("");
  // Track WHICH email was verified, not just a boolean: editing the field
  // mid-flight must never approve a stale, mismatched identity.
  const [verifiedIdentifier, setVerifiedIdentifier] = useState("");
  const [verifiedUsername, setVerifiedUsername] = useState("");
  const [returningLoan, setReturningLoan] = useState<DirectLoan | null>(null);
  const [issueEvidenceId, setIssueEvidenceId] = useState<number | null>(null);
  const [issueRemark, setIssueRemark] = useState("Issued from direct handout.");
  const [issueUploadKey, setIssueUploadKey] = useState(0);
  const [returnEvidenceId, setReturnEvidenceId] = useState<number | null>(null);
  const [returnNotes, setReturnNotes] = useState("");
  const [returnQrPayload, setReturnQrPayload] = useState("");
  useEffect(() => {
    setRequesterName("");
    setContactEmail("");
    setContactPhone("");
    setLineRows([{ key: 1, productId: "", quantity: "1" }]);
    setNextLineKey(2);
    setScanned([]);
    setShowScanner(false);
    setQrPayloads("");
    setContainerId("");
    setShowContainerScanner(false);
    setContainerScanError("");
    setVerifiedIdentifier("");
    setVerifiedUsername("");
    setReturningLoan(null);
    setIssueEvidenceId(null);
    setIssueRemark("Issued from direct handout.");
    setIssueUploadKey((key) => key + 1);
    setReturnEvidenceId(null);
    setReturnNotes("");
    setReturnQrPayload("");
  }, [makerspace.id]);
  const products = useStaffGet<{ results: ProductOption[] }>(
    ["inventory-all", makerspace.id],
    `/admin/makerspace/${makerspace.id}/inventory?page_size=1000`,
  );
  // Fetch ALL containers (distinct cache key from the shared ["containers"] entry so a
  // truncated first page can't leak in): the dropdown + the scan membership check both
  // need the complete list, else a valid container past page one falsely reads as "not found".
  const containers = useStaffGet<ContainerResponse>(
    ["containers-all", makerspace.id],
    `/admin/makerspace/${makerspace.id}/containers?page_size=1000`,
  );
  const containerOptions = Array.isArray(containers.data)
    ? containers.data
    : containers.data?.results ?? [];
  const activeProducts = (products.data?.results ?? []).filter((product) => !product.is_archived);
  const productById = new Map(activeProducts.map((product) => [product.id, product]));
  const loans = usePaginatedQuery<DirectLoan>({
    key: ["direct-loans", makerspace.id],
    path: `/admin/makerspace/${makerspace.id}/direct-loans`,
    resetKey: String(makerspace.id),
  });
  const verify = useMutation({
    mutationFn: (submitted: string) =>
      staffRequest<VerifyResponse>(`/admin/makerspace/${makerspace.id}/checkin/verify`, {
        method: "POST",
        body: JSON.stringify({ identifier: submitted }),
      }),
    onMutate: () => {
      setVerifiedIdentifier("");
      setVerifiedUsername("");
    },
    onSuccess: (result, submitted) => {
      // Bind the success to the exact identifier that was verified.
      setVerifiedIdentifier(submitted);
      setVerifiedUsername(result.username);
    },
  });
  const isVerified =
    verifiedIdentifier !== "" && verifiedIdentifier === contactEmail.trim();
  const issue = useMutation({
    mutationFn: () =>
      staffRequest(`/admin/makerspace/${makerspace.id}/direct-loans`, {
        method: "POST",
        body: JSON.stringify({
          requester_name: requesterName.trim(),
          contact_email: contactEmail.trim(),
          contact_phone: contactPhone.trim(),
          evidence_id: issueEvidenceId as number,
          remark: issueRemark.trim(),
          container_id: containerId ? Number(containerId) : null,
          qr_payloads: Array.from(new Set([
            ...scanned.map((item) => item.payload),
            ...pastedQrPayloads,
          ])),
          items: validManualLines
            .map((line) => ({ product_id: Number(line.productId), quantity: Number(line.quantity) })),
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["direct-loans", makerspace.id] });
      invalidateInventoryViews(queryClient, makerspace.id, makerspace.slug);
      setLineRows([{ key: 1, productId: "", quantity: "1" }]);
      setNextLineKey(2);
      setScanned([]);
      setQrPayloads("");
      setContainerId("");
      setShowContainerScanner(false);
      setContainerScanError("");
      setIssueEvidenceId(null);
      setIssueRemark("Issued from direct handout.");
      setIssueUploadKey((key) => key + 1);
    },
  });
  const pastedQrPayloads = qrPayloads.split("\n").map((value) => value.trim()).filter(Boolean);
  const validManualLines = lineRows.filter((line) => {
    const product = productById.get(Number(line.productId));
    return Boolean(product) && product?.tracking_mode !== "individual" && Number(line.quantity) > 0;
  });
  const hasIssueContent =
    validManualLines.length > 0 || scanned.length > 0 || pastedQrPayloads.length > 0 || Boolean(containerId);
  const canIssue =
    isVerified &&
    requesterName.trim().length > 0 &&
    contactEmail.trim().length > 0 &&
    contactPhone.trim().length > 0 &&
    hasIssueContent &&
    issueEvidenceId !== null &&
    !issue.isPending;
  const returnLoan = useMutation({
    mutationFn: ({ loanId, evidenceId, notes, qrPayload }: ReturnLoanPayload) =>
      staffRequest(`/admin/direct-loans/${loanId}/return`, {
        method: "POST",
        body: JSON.stringify({ evidence_id: evidenceId, notes, qr_payload: qrPayload.trim() }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["direct-loans", makerspace.id] });
      invalidateInventoryViews(queryClient, makerspace.id, makerspace.slug);
      resetReturnState();
    },
  });
  const resetReturnState = () => {
    setReturningLoan(null);
    setReturnEvidenceId(null);
    setReturnNotes("");
    setReturnQrPayload("");
  };
  const openReturnModal = (loan: DirectLoan) => {
    returnLoan.reset();
    setReturningLoan(loan);
    setReturnEvidenceId(null);
    setReturnNotes("");
    setReturnQrPayload("");
  };
  const closeReturnModal = () => {
    if (returnLoan.isPending) return;
    returnLoan.reset();
    resetReturnState();
  };
  const submitReturn = () => {
    if (!returningLoan || returnEvidenceId === null || !returnNotes.trim()) return;
    if (returningLoan.return_scan_required && !returnQrPayload.trim()) return;
    returnLoan.mutate({
      loanId: returningLoan.id,
      evidenceId: returnEvidenceId,
      notes: returnNotes.trim(),
      qrPayload: returnQrPayload,
    });
  };
  const addLine = () => {
    setLineRows((rows) => [...rows, { key: nextLineKey, productId: "", quantity: "1" }]);
    setNextLineKey((key) => key + 1);
  };
  const updateLine = (key: number, patch: Partial<LineDraft>) => {
    setLineRows((rows) => rows.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  };
  const removeLine = (key: number) => {
    setLineRows((rows) => rows.filter((line) => line.key !== key));
  };
  const removeScanned = (payload: string) => {
    setScanned((items) => items.filter((item) => item.payload !== payload));
  };
  const updateContactEmail = (value: string) => {
    setContactEmail(value);
    setVerifiedIdentifier("");
    setVerifiedUsername("");
    verify.reset();
  };
  const handleScan = async (payload: string) => {
    const cleanPayload = payload.trim();
    if (!cleanPayload || scanned.some((item) => item.payload === cleanPayload)) return;
    let label = cleanPayload;
    try {
      const result = await staffRequest<QrResolveResponse>("/admin/qr/resolve", {
        method: "POST",
        body: JSON.stringify({ payload: cleanPayload }),
      });
      label = labelForTarget(result.target, cleanPayload);
    } catch {
      label = cleanPayload;
    }
    setScanned((items) =>
      items.some((item) => item.payload === cleanPayload)
        ? items
        : [...items, { payload: cleanPayload, label }],
    );
  };
  const handleContainerScan = async (payload: string) => {
    try {
      const result = await staffRequest<QrResolveResponse>("/admin/qr/resolve", {
        method: "POST",
        body: JSON.stringify({ payload }),
      });
      const target = result.target;
      if (target.type !== "box") {
        setContainerScanError("Scanned QR is not a container.");
        return;
      }
      if (!containerOptions.some((container) => container.id === target.id)) {
        setContainerScanError("That container isn't available for handout (inactive or not found).");
        return;
      }
      setContainerId(String(target.id));
      setContainerScanError("");
    } catch {
      setContainerScanError("Could not resolve the scanned QR.");
    } finally {
      setShowContainerScanner(false);
    }
  };

  return (
    <div className="grid gap-4">
      <Panel title="Direct handout">
        <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
          <input
            className="desk-input"
            placeholder="Borrower name"
            required
            value={requesterName}
            onChange={(e) => setRequesterName(e.target.value)}
          />
          <input
            className="desk-input"
            placeholder="Borrower email"
            required
            type="email"
            value={contactEmail}
            onChange={(e) => updateContactEmail(e.target.value)}
          />
          <button className="desk-button" type="button" disabled={!contactEmail.trim() || verify.isPending} onClick={() => verify.mutate(contactEmail.trim())}>
            Verify check-in
          </button>
        </div>
        <input
          className="desk-input mt-2 w-full"
          placeholder="Borrower phone"
          required
          type="tel"
          value={contactPhone}
          onChange={(e) => setContactPhone(e.target.value)}
        />
        {isVerified && verifiedUsername ? <p className="mt-2 text-sm text-success-ink">Verified as {verifiedUsername}</p> : null}
        {verify.error ? <p className="mt-2 text-sm text-danger">{verify.error.message}</p> : null}
        <label className="mt-4 block text-sm font-medium text-ink" htmlFor="direct-loan-container">Container (optional)</label>
        <div className="mt-1 flex flex-col gap-2 md:flex-row">
          <select
            id="direct-loan-container"
            className="desk-input w-full"
            value={containerId}
            disabled={containers.isLoading}
            onChange={(e) => setContainerId(e.target.value)}
          >
            <option value="">No container</option>
            {containerOptions.map((container) => (
              <option key={container.id} value={container.id}>{container.label}</option>
            ))}
          </select>
          <button
            type="button"
            className="desk-button"
            onClick={() => {
              setContainerScanError("");
              setShowContainerScanner(true);
            }}
          >
            Scan container
          </button>
        </div>
        {containerScanError ? <p className="mt-1 text-sm text-danger">{containerScanError}</p> : null}
        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-ink">Items</h3>
            <button className="desk-button" type="button" onClick={addLine}>Add item</button>
          </div>
          <div className="grid gap-2">
            {lineRows.map((line) => {
              const selectedLineProduct = productById.get(Number(line.productId));
              const selectedIndividual = selectedLineProduct?.tracking_mode === "individual";
              return (
                <div key={line.key} className="grid gap-2 md:grid-cols-[1fr_120px_auto]">
                  <select aria-label="Product" className="desk-input" value={line.productId} disabled={products.isLoading} onChange={(e) => updateLine(line.key, { productId: e.target.value })}>
                    <option value="">Inventory item</option>
                    {activeProducts.map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.name} | {product.tracking_mode} | {product.available_quantity} available
                        {product.storage_location ? ` - Shelf: ${product.storage_location}` : ""}
                      </option>
                    ))}
                  </select>
                  <input aria-label="Quantity" className="desk-input" min={1} inputMode="numeric" type="number" value={line.quantity} disabled={selectedIndividual} onChange={(e) => updateLine(line.key, { quantity: e.target.value })} />
                  <button className="desk-button" type="button" onClick={() => removeLine(line.key)}>Remove</button>
                  {selectedLineProduct ? <p className="font-mono text-xs uppercase text-muted md:col-span-3">{selectedLineProduct.tracking_mode}{selectedIndividual ? " | scan unit QR" : ""}</p> : null}
                </div>
              );
            })}
          </div>
        </div>
        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-ink">QR payloads</h3>
            <button className="desk-button" type="button" onClick={() => setShowScanner(true)}>Scan QR</button>
          </div>
          {scanned.length ? (
            <div className="mb-3 flex flex-wrap gap-2">
              {scanned.map((item) => (
                <span key={item.payload} className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-1 text-sm text-ink">
                  {item.label}
                  <button className="text-muted hover:text-danger" type="button" onClick={() => removeScanned(item.payload)}>Remove</button>
                </span>
              ))}
            </div>
          ) : null}
        </div>
        <textarea
          aria-label="QR payloads"
          className="desk-input mt-3 h-24 w-full font-mono text-sm"
          placeholder="Optional QR payloads, one per line"
          value={qrPayloads}
          onChange={(e) => setQrPayloads(e.target.value)}
        />
        <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr]">
          <EvidenceUpload
            key={issueUploadKey}
            makerspaceId={makerspace.id}
            evidenceType="issue"
            disabled={issue.isPending}
            onUploaded={setIssueEvidenceId}
          />
          <label className="block">
            <span className="mb-1 block text-xs font-semibold tracking-wide text-muted">
              Issue remark
            </span>
            <textarea
              className="desk-input min-h-20 w-full"
              value={issueRemark}
              onChange={(event) => setIssueRemark(event.target.value)}
            />
          </label>
        </div>
        {issueEvidenceId === null ? <p className="mt-3 text-sm text-muted">Upload an issue photo before issuing.</p> : null}
        {!hasIssueContent ? <p className="mt-3 text-sm text-muted">Add at least one item, QR payload, or container before issuing.</p> : null}
        <button className="desk-button-primary mt-3" disabled={!canIssue} onClick={() => issue.mutate()}>
          Issue direct handout
        </button>
        {issue.error ? <p className="mt-3 text-sm text-danger">{issue.error.message}</p> : null}
        {products.error ? <p className="mt-3 text-sm text-danger">{products.error.message}</p> : null}
        {containers.error ? <p className="mt-3 text-sm text-danger">{containers.error.message}</p> : null}
        {showScanner ? <QrScanner onScan={handleScan} onClose={() => setShowScanner(false)} /> : null}
        {showContainerScanner ? <QrScanner onScan={handleContainerScan} onClose={() => setShowContainerScanner(false)} /> : null}
      </Panel>
      <DirectLoanList loans={loans.results} onReturn={openReturnModal} />
      <Pagination page={loans.page} totalPages={loans.totalPages} onChange={loans.setPage} count={loans.count} pageSize={loans.pageSize} />
      <DirectLoanReturnModal
        loan={returningLoan}
        makerspaceId={makerspace.id}
        evidenceId={returnEvidenceId}
        notes={returnNotes}
        qrPayload={returnQrPayload}
        pending={returnLoan.isPending}
        error={returnLoan.error?.message ?? ""}
        onEvidenceUploaded={setReturnEvidenceId}
        onNotesChange={setReturnNotes}
        onQrPayloadChange={setReturnQrPayload}
        onCancel={closeReturnModal}
        onSubmit={submitReturn}
      />
    </div>
  );
}

function labelForTarget(target: QrResolveResponse["target"], fallback: string) {
  if (target.type === "product") return `Item: ${target.name || fallback}`;
  if (target.type === "asset") return `Unit: ${target.product} | ${target.asset_tag} | ${target.status}`;
  return `Container: ${target.label || target.code || fallback}`;
}
