import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { staffRequest } from "../../../lib/api";
import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { Pagination } from "../../../components/ui/Pagination";
import { useDebouncedValue } from "../../../lib/useDebouncedValue";
import { usePaginatedQuery } from "../../../lib/usePaginatedQuery";
import { Panel, type Makerspace, useStaffGet } from "./shared";
import { RequestList } from "./QueuesList";
import { actionInvalidationScope, invalidateRequestQueues } from "./QueuesInvalidation";
import {
  AssignIssueModal,
  RejectRequestModal,
  ReturnDueModal,
  ReturnRequestModal,
  type AssignIssueValues,
  type RejectRequestValues,
  type ReturnDueValues,
  type ReturnRequestValues,
} from "./QueuesModals";
import { RequestListSkeleton } from "./QueuesSkeleton";

export type RequestItem = {
  id: number;
  product_id: number;
  product_name: string;
  storage_location: string;
  tracking_mode: string;
  requires_asset_qr: boolean;
  requested_quantity: number;
  accepted_quantity: number;
  issued_quantity: number;
  returned_quantity: number;
  damaged_quantity: number;
  missing_quantity: number;
  needs_fix_quantity: number;
  issued_assets?: Array<{ asset_id: number; asset_tag: string; serial_number: string }>;
};
export type HardwareRequest = {
  id: number;
  status: string;
  requester_username: string;
  requester_display?: string;
  requester_contact_email?: string;
  requester_contact_phone?: string;
  rejection_reason?: string;
  issue_evidence_id?: number | null;
  return_evidence_ids?: number[];
  requested_for: string;
  return_due_at: string | null;
  return_reminder_sent_at: string | null;
  items: RequestItem[];
  // AdminRequestSerializer serializes the assigned container as the flat `assigned_box_label`.
  assigned_box_label?: string | null;
  assigned_box?: { code: string; label: string };
};

export function Queues({ makerspace, guestOnly }: { makerspace: Makerspace; guestOnly: boolean }) {
  const queryClient = useQueryClient();
  const [acceptRow, setAcceptRow] = useState<HardwareRequest | null>(null);
  const [dueRow, setDueRow] = useState<HardwareRequest | null>(null);
  const [rejectRow, setRejectRow] = useState<HardwareRequest | null>(null);
  const [assignIssueRow, setAssignIssueRow] = useState<HardwareRequest | null>(null);
  const [returnRow, setReturnRow] = useState<HardwareRequest | null>(null);
  const [modalError, setModalError] = useState("");
  const [defaultLoanDays, setDefaultLoanDays] = useState("7");
  const [showHistory, setShowHistory] = useState(false);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search);

  const policy = useStaffGet<{ id: number; default_loan_days: number }>(["return-policy", makerspace.id], `/admin/makerspace/${makerspace.id}/return-policy`, !guestOnly);
  const pending = usePaginatedQuery<HardwareRequest>({
    key: ["pending", makerspace.id],
    path: `/admin/makerspace/${makerspace.id}/pending-requests`,
    enabled: !guestOnly,
    search: debouncedSearch,
    resetKey: String(makerspace.id),
  });
  const accepted = usePaginatedQuery<HardwareRequest>({
    key: ["accepted", makerspace.id],
    path: `/admin/makerspace/${makerspace.id}/accepted-requests`,
    search: debouncedSearch,
    resetKey: String(makerspace.id),
  });
  const active = usePaginatedQuery<HardwareRequest>({
    key: ["active", makerspace.id],
    path: `/admin/makerspace/${makerspace.id}/active-loans`,
    search: debouncedSearch,
    resetKey: String(makerspace.id),
  });
  const history = usePaginatedQuery<HardwareRequest>({
    key: ["request-history", makerspace.id],
    path: `/admin/makerspace/${makerspace.id}/request-history`,
    enabled: showHistory,
    search: debouncedSearch,
    resetKey: String(makerspace.id),
  });

  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: object }) => staffRequest(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
    onSuccess: (_data, { path }) => invalidateRequestQueues(queryClient, makerspace.id, actionInvalidationScope(path)),
  });
  const savePolicy = useMutation({
    mutationFn: () => staffRequest(`/admin/makerspace/${makerspace.id}/return-policy`, { method: "PATCH", body: JSON.stringify({ default_loan_days: Number(defaultLoanDays) || 7 }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["return-policy", makerspace.id] }),
  });

  useEffect(() => {
    if (policy.data) setDefaultLoanDays(String(policy.data.default_loan_days));
  }, [policy.data]);

  const openModal = (setter: (row: HardwareRequest | null) => void, row: HardwareRequest) => {
    setModalError("");
    setter(row);
  };
  const closeModals = () => {
    if (action.isPending) return;
    setAcceptRow(null);
    setDueRow(null);
    setRejectRow(null);
    setAssignIssueRow(null);
    setReturnRow(null);
    setModalError("");
  };
  const runAction = async (path: string, body?: object, onDone = closeModals) => {
    setModalError("");
    try {
      await action.mutateAsync({ path, body });
      onDone();
    } catch (error) {
      setModalError(error instanceof Error ? error.message : "Action failed.");
    }
  };
  const submitReturnDue = (values: ReturnDueValues) => {
    if (dueRow) void runAction(`/admin/requests/${dueRow.id}/return-due`, { return_due_at: values.returnDueAt ? new Date(values.returnDueAt).toISOString() : null });
  };
  const submitReject = (values: RejectRequestValues) => {
    if (rejectRow) void runAction(`/admin/requests/${rejectRow.id}/reject`, { reason: values.reason });
  };
  const submitReturn = (values: ReturnRequestValues) => {
    if (returnRow) void runAction(`/admin/requests/${returnRow.id}/return`, { evidence_id: values.evidenceId, box_code: values.boxCode, remark: values.remark, resolutions: values.resolutions });
  };
  const submitAssignIssue = async (values: AssignIssueValues) => {
    if (!assignIssueRow) return;
    setModalError("");
    let boxAssigned = false;
    try {
      await action.mutateAsync({ path: `/admin/requests/${assignIssueRow.id}/assign-box`, body: { box_code: values.boxCode } });
      boxAssigned = true;
      await action.mutateAsync({
        path: `/admin/requests/${assignIssueRow.id}/issue`,
        body: { evidence_id: values.evidenceId, remark: values.remark, rejects: values.rejects, asset_qr_payloads: values.assetQrPayloads },
      });
      closeModals();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Action failed.";
      setModalError(boxAssigned ? `Box assigned, but issue failed: ${message} The request still needs the issue step; retry with the assigned box.` : message);
    }
  };

  return (
    <div className="grid gap-4">
      {!guestOnly ? <ReturnPolicyPanel policyDays={policy.data?.default_loan_days ?? 7} value={defaultLoanDays} pending={savePolicy.isPending} onChange={setDefaultLoanDays} onSave={() => savePolicy.mutate()} /> : null}
      <input
        className="desk-input"
        placeholder="Search requester name, email, phone, or purpose"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {!guestOnly ? (
        <Panel title="Pending review">
          {pending.isLoading ? <RequestListSkeleton /> : <RequestList rows={pending.results} actions={(row) => <PendingActions row={row} disabled={action.isPending} openModal={openModal} setAcceptRow={setAcceptRow} setRejectRow={setRejectRow} setDueRow={setDueRow} />} />}
          <Pagination page={pending.page} totalPages={pending.totalPages} onChange={pending.setPage} count={pending.count} pageSize={pending.pageSize} />
          {pending.error instanceof Error ? <p className="mt-2 text-sm text-danger">{pending.error.message}</p> : null}
        </Panel>
      ) : null}
      <Panel title="Ready for handover">
        {accepted.isLoading ? <RequestListSkeleton /> : <RequestList rows={accepted.results} actions={(row) => <AcceptedActions row={row} disabled={action.isPending} openModal={openModal} setAssignIssueRow={setAssignIssueRow} setDueRow={setDueRow} />} />}
        <Pagination page={accepted.page} totalPages={accepted.totalPages} onChange={accepted.setPage} count={accepted.count} pageSize={accepted.pageSize} />
        {accepted.error instanceof Error ? <p className="mt-2 text-sm text-danger">{accepted.error.message}</p> : null}
      </Panel>
      {!guestOnly ? (
        <Panel title="Active loans">
          {active.isLoading ? <RequestListSkeleton /> : <RequestList rows={active.results} actions={(row) => <ActiveActions row={row} disabled={action.isPending} openModal={openModal} setDueRow={setDueRow} setReturnRow={setReturnRow} />} />}
          <Pagination page={active.page} totalPages={active.totalPages} onChange={active.setPage} count={active.count} pageSize={active.pageSize} />
          {active.error instanceof Error ? <p className="mt-2 text-sm text-danger">{active.error.message}</p> : null}
        </Panel>
      ) : null}
      <HistoryPanel show={showHistory} loading={history.isLoading} rows={history.results} page={history.page} totalPages={history.totalPages} count={history.count} pageSize={history.pageSize} onPageChange={history.setPage} onToggle={() => setShowHistory((value) => !value)} />
      <ConfirmDialog open={Boolean(acceptRow)} title="Accept request" message={acceptRow ? `Accept request #${acceptRow.id} from ${acceptRow.requester_display || acceptRow.requester_username}?${modalError ? ` Error: ${modalError}` : ""}` : ""} confirmLabel="Accept" pending={action.isPending} onCancel={closeModals} onConfirm={() => { if (acceptRow) void runAction(`/admin/requests/${acceptRow.id}/accept`); }} />
      <ReturnDueModal row={dueRow} defaultValue={dueRow?.return_due_at ? localDateTimeValue(dueRow.return_due_at) : localDateTimeValue(defaultDueDate(Number(defaultLoanDays) || 7).toISOString())} open={Boolean(dueRow)} pending={action.isPending} error={modalError} onClose={closeModals} onSubmit={submitReturnDue} />
      <RejectRequestModal row={rejectRow} open={Boolean(rejectRow)} pending={action.isPending} error={modalError} onClose={closeModals} onSubmit={submitReject} />
      <AssignIssueModal row={assignIssueRow} open={Boolean(assignIssueRow)} pending={action.isPending} error={modalError} onClose={closeModals} onSubmit={submitAssignIssue} makerspaceId={makerspace.id} />
      <ReturnRequestModal row={returnRow} open={Boolean(returnRow)} pending={action.isPending} error={modalError} onClose={closeModals} onSubmit={submitReturn} makerspaceId={makerspace.id} />
    </div>
  );
}

function ReturnPolicyPanel({ policyDays, value, pending, onChange, onSave }: { policyDays: number; value: string; pending: boolean; onChange: (value: string) => void; onSave: () => void }) {
  return (
    <Panel title="Return policy">
      <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
        <input aria-label="Default loan days" className="desk-input" type="number" min="1" value={value} onChange={(event) => onChange(event.target.value)} />
        <button disabled={pending} onClick={onSave}>Save default days</button>
      </div>
      <p className="mt-2 text-sm text-muted">Default return time is used when a request is issued. Current default: {policyDays} days.</p>
    </Panel>
  );
}

function PendingActions({ row, disabled, openModal, setAcceptRow, setRejectRow, setDueRow }: QueueActionProps & { setAcceptRow: Setter; setRejectRow: Setter; setDueRow: Setter }) {
  return <><button disabled={disabled} onClick={() => openModal(setAcceptRow, row)}>Accept</button><button disabled={disabled} onClick={() => openModal(setRejectRow, row)}>Reject</button><button disabled={disabled} onClick={() => openModal(setDueRow, row)}>Set due</button></>;
}

function AcceptedActions({ row, disabled, openModal, setAssignIssueRow, setDueRow }: QueueActionProps & { setAssignIssueRow: Setter; setDueRow: Setter }) {
  return <><button disabled={disabled} onClick={() => openModal(setAssignIssueRow, row)}>Assign + issue</button><button disabled={disabled} onClick={() => openModal(setDueRow, row)}>Set due</button></>;
}

function ActiveActions({ row, disabled, openModal, setDueRow, setReturnRow }: QueueActionProps & { setDueRow: Setter; setReturnRow: Setter }) {
  return <><button disabled={disabled} onClick={() => openModal(setDueRow, row)}>Set due</button><button disabled={disabled} onClick={() => openModal(setReturnRow, row)}>Return</button></>;
}

function HistoryPanel({
  show,
  loading,
  rows,
  page,
  totalPages,
  count,
  pageSize,
  onPageChange,
  onToggle,
}: {
  show: boolean;
  loading: boolean;
  rows: HardwareRequest[];
  page: number;
  totalPages: number;
  count: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onToggle: () => void;
}) {
  return (
    <Panel title="History">
      <button type="button" className="text-sm text-accent-ink" onClick={onToggle}>{show ? "Hide history" : "Show history (returned / rejected / closed with issue)"}</button>
      {show ? (
        <div className="mt-3">
          {loading ? <p className="text-sm text-muted">Loading history...</p> : null}
          <RequestList rows={rows} actions={() => null} />
          <Pagination page={page} totalPages={totalPages} onChange={onPageChange} count={count} pageSize={pageSize} />
        </div>
      ) : null}
    </Panel>
  );
}

type Setter = (row: HardwareRequest | null) => void;
type QueueActionProps = { row: HardwareRequest; disabled: boolean; openModal: (setter: Setter, row: HardwareRequest) => void };

function defaultDueDate(days: number) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date;
}

function localDateTimeValue(value: string) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}
