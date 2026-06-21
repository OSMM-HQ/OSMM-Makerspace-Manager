import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { staffRequest } from "../../../lib/api";
import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { Skeleton } from "../../../components/ui/Skeleton";
import { Panel, type Makerspace, useStaffGet } from "./shared";
import { RequestList } from "./QueuesList";
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

export type RequestItem = {
  id: number;
  product_id: number;
  product_name: string;
  tracking_mode: string;
  requires_asset_qr: boolean;
  requested_quantity: number;
  accepted_quantity: number;
  issued_quantity: number;
  returned_quantity: number;
  damaged_quantity: number;
  missing_quantity: number;
  needs_fix_quantity: number;
};
export type HardwareRequest = {
  id: number;
  status: string;
  requester_username: string;
  requester_contact_email?: string;
  requester_contact_phone?: string;
  rejection_reason?: string;
  issue_evidence_id?: number | null;
  return_evidence_ids?: number[];
  requested_for: string;
  return_due_at: string | null;
  return_reminder_sent_at: string | null;
  items: RequestItem[];
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
  const policy = useStaffGet<{ id: number; default_loan_days: number }>(
    ["return-policy", makerspace.id],
    `/admin/makerspace/${makerspace.id}/return-policy`,
    !guestOnly,
  );
  const [defaultLoanDays, setDefaultLoanDays] = useState("7");
  const pending = useStaffGet<{ results: HardwareRequest[] }>(
    ["pending", makerspace.id],
    `/admin/makerspace/${makerspace.id}/pending-requests`,
    !guestOnly,
  );
  const accepted = useStaffGet<{ results: HardwareRequest[] }>(
    ["accepted", makerspace.id],
    `/admin/makerspace/${makerspace.id}/accepted-requests`,
  );
  const active = useStaffGet<{ results: HardwareRequest[] }>(
    ["active", makerspace.id],
    `/admin/makerspace/${makerspace.id}/active-loans`,
  );
  const [showHistory, setShowHistory] = useState(false);
  // Terminal requests (returned/rejected/closed_with_issue) only load when the staffer
  // opens history — closed lists grow unbounded, so the third useStaffGet arg (enabled)
  // defers the fetch until needed.
  const history = useStaffGet<{ results: HardwareRequest[] }>(
    ["request-history", makerspace.id],
    `/admin/makerspace/${makerspace.id}/request-history`,
    showHistory,
  );
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: object }) =>
      staffRequest(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
    onSuccess: (_data, { path }) => {
      invalidateRequestQueues(queryClient, makerspace.id, actionInvalidationScope(path));
    },
  });
  const savePolicy = useMutation({
    mutationFn: () =>
      staffRequest(`/admin/makerspace/${makerspace.id}/return-policy`, {
        method: "PATCH",
        body: JSON.stringify({ default_loan_days: Number(defaultLoanDays) || 7 }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["return-policy", makerspace.id] }),
  });
  useEffect(() => {
    if (policy.data) {
      setDefaultLoanDays(String(policy.data.default_loan_days));
    }
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
    if (!dueRow) return;
    void runAction(`/admin/requests/${dueRow.id}/return-due`, {
      return_due_at: values.returnDueAt ? new Date(values.returnDueAt).toISOString() : null,
    });
  };
  const submitReject = (values: RejectRequestValues) => {
    if (!rejectRow) return;
    void runAction(`/admin/requests/${rejectRow.id}/reject`, { reason: values.reason });
  };
  const submitAssignIssue = async (values: AssignIssueValues) => {
    if (!assignIssueRow) return;
    setModalError("");
    let boxAssigned = false;
    try {
      await action.mutateAsync({
        path: `/admin/requests/${assignIssueRow.id}/assign-box`,
        body: { box_code: values.boxCode },
      });
      boxAssigned = true;
      await action.mutateAsync({
        path: `/admin/requests/${assignIssueRow.id}/issue`,
        body: {
          evidence_id: values.evidenceId,
          remark: values.remark,
          rejects: values.rejects,
          asset_qr_payloads: values.assetQrPayloads,
        },
      });
      closeModals();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Action failed.";
      setModalError(
        boxAssigned
          ? `Box assigned, but issue failed: ${message} The request still needs the issue step; retry with the assigned box.`
          : message,
      );
    }
  };
  const submitReturn = (values: ReturnRequestValues) => {
    if (!returnRow) return;
    void runAction(`/admin/requests/${returnRow.id}/return`, {
      evidence_id: values.evidenceId,
      box_code: values.boxCode,
      remark: values.remark,
      resolutions: values.resolutions,
    });
  };
  return (
    <div className="grid gap-4">
      {!guestOnly ? (
        <Panel title="Return policy">
          <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
            <input
              className="desk-input"
              type="number"
              min="1"
              value={defaultLoanDays}
              onChange={(event) => setDefaultLoanDays(event.target.value)}
            />
            <button disabled={savePolicy.isPending} onClick={() => savePolicy.mutate()}>
              Save default days
            </button>
          </div>
          <p className="mt-2 text-sm text-muted">
            Default return time is used when a request is issued. Current default: {policy.data?.default_loan_days ?? 7} days.
          </p>
        </Panel>
      ) : null}
      {!guestOnly ? (
        <Panel title="Pending review">
          {pending.isLoading ? (
            <RequestListSkeleton />
          ) : (
            <RequestList
              rows={pending.data?.results ?? []}
              actions={(row) => (
                <>
                  <button disabled={action.isPending} onClick={() => openModal(setAcceptRow, row)}>Accept</button>
                  <button disabled={action.isPending} onClick={() => openModal(setRejectRow, row)}>Reject</button>
                  <button disabled={action.isPending} onClick={() => openModal(setDueRow, row)}>Set due</button>
                </>
              )}
            />
          )}
        </Panel>
      ) : null}
      <Panel title="Ready for handover">
        {accepted.isLoading ? (
          <RequestListSkeleton />
        ) : (
          <RequestList
            rows={accepted.data?.results ?? []}
            actions={(row) => (
              <>
                <button disabled={action.isPending} onClick={() => openModal(setAssignIssueRow, row)}>Assign + issue</button>
                <button disabled={action.isPending} onClick={() => openModal(setDueRow, row)}>Set due</button>
              </>
            )}
          />
        )}
      </Panel>
      {!guestOnly ? (
        <Panel title="Active loans">
          {active.isLoading ? (
            <RequestListSkeleton />
          ) : (
            <RequestList
              rows={active.data?.results ?? []}
              actions={(row) => (
                <>
                  <button disabled={action.isPending} onClick={() => openModal(setDueRow, row)}>Set due</button>
                  <button disabled={action.isPending} onClick={() => openModal(setReturnRow, row)}>Return</button>
                </>
              )}
            />
          )}
        </Panel>
      ) : null}
      <Panel title="History">
        <button type="button" className="text-sm text-accent" onClick={() => setShowHistory((value) => !value)}>
          {showHistory ? "Hide history" : "Show history (returned / rejected / closed with issue)"}
        </button>
        {showHistory ? (
          <div className="mt-3">
            {history.isLoading ? <p className="text-sm text-muted">Loading history...</p> : null}
            <RequestList rows={history.data?.results ?? []} actions={() => null} />
          </div>
        ) : null}
      </Panel>
      <ConfirmDialog
        open={Boolean(acceptRow)}
        title="Accept request"
        message={acceptRow ? `Accept request #${acceptRow.id} from ${acceptRow.requester_username}?${modalError ? ` Error: ${modalError}` : ""}` : ""}
        confirmLabel="Accept"
        pending={action.isPending}
        onCancel={closeModals}
        onConfirm={() => {
          if (acceptRow) void runAction(`/admin/requests/${acceptRow.id}/accept`);
        }}
      />
      <ReturnDueModal
        row={dueRow}
        defaultValue={dueRow?.return_due_at ? localDateTimeValue(dueRow.return_due_at) : localDateTimeValue(defaultDueDate(Number(defaultLoanDays) || 7).toISOString())}
        open={Boolean(dueRow)}
        pending={action.isPending}
        error={modalError}
        onClose={closeModals}
        onSubmit={submitReturnDue}
      />
      <RejectRequestModal
        row={rejectRow}
        open={Boolean(rejectRow)}
        pending={action.isPending}
        error={modalError}
        onClose={closeModals}
        onSubmit={submitReject}
      />
      <AssignIssueModal
        row={assignIssueRow}
        open={Boolean(assignIssueRow)}
        pending={action.isPending}
        error={modalError}
        onClose={closeModals}
        onSubmit={submitAssignIssue}
        makerspaceId={makerspace.id}
      />
      <ReturnRequestModal
        row={returnRow}
        open={Boolean(returnRow)}
        pending={action.isPending}
        error={modalError}
        onClose={closeModals}
        onSubmit={submitReturn}
        makerspaceId={makerspace.id}
      />
    </div>
  );
}

function RequestListSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="grid gap-2" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="rounded-md border border-line bg-surface p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-7 w-32" />
          </div>
          <Skeleton className="mt-3 h-3 w-full" />
          <Skeleton className="mt-2 h-3 w-2/3" />
        </div>
      ))}
    </div>
  );
}

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

type InvalidationScope = {
  inventory: boolean;
  needsFix: boolean;
  ledger: boolean;
};

function actionInvalidationScope(path: string): InvalidationScope {
  const inventory = path.endsWith("/accept") || path.endsWith("/issue") || path.endsWith("/return");
  // Ledger rows show return_due_at, so a due-date change must refresh the ledger too.
  const ledger = path.endsWith("/issue") || path.endsWith("/return") || path.endsWith("/return-due");
  const needsFix = path.endsWith("/issue") || path.endsWith("/return");
  return { inventory, ledger, needsFix };
}

function invalidateRequestQueues(
  queryClient: ReturnType<typeof useQueryClient>,
  makerspaceId: number,
  scope: InvalidationScope,
) {
  queryClient.invalidateQueries({ queryKey: ["pending", makerspaceId] });
  queryClient.invalidateQueries({ queryKey: ["accepted", makerspaceId] });
  queryClient.invalidateQueries({ queryKey: ["active", makerspaceId] });
  queryClient.invalidateQueries({ queryKey: ["request-history", makerspaceId] });

  if (scope.inventory) {
    queryClient.invalidateQueries({ queryKey: ["inventory", makerspaceId] });
    queryClient.invalidateQueries({ queryKey: ["inventory-all", makerspaceId] });
    // Report metrics (summary, most-lent, top-borrowers, damaged-lost) derive from
    // request + inventory quantities, so refresh them too. Prefix-invalidating
    // ["operations-report"] covers every scopeKey (per-makerspace and the superadmin
    // "all" aggregate); it also touches the printing report, a negligible over-refetch.
    queryClient.invalidateQueries({ queryKey: ["operations-report"] });
  }
  if (scope.needsFix) {
    queryClient.invalidateQueries({ queryKey: ["needs-fix-shelf", makerspaceId] });
  }
  if (scope.ledger) {
    queryClient.invalidateQueries({ queryKey: ["ledger", makerspaceId] });
    queryClient.invalidateQueries({ queryKey: ["ledger", "all"] });
  }
}
