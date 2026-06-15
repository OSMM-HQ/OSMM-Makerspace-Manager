import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { staffRequest } from "../../../lib/api";
import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
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
  requested_quantity: number;
  issued_quantity: number;
  returned_quantity: number;
  damaged_quantity: number;
  missing_quantity: number;
};
export type HardwareRequest = {
  id: number;
  status: string;
  requester_username: string;
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
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: object }) =>
      staffRequest(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
    onSuccess: () => queryClient.invalidateQueries(),
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
    try {
      await action.mutateAsync({
        path: `/admin/requests/${assignIssueRow.id}/assign-box`,
        body: { box_code: values.boxCode },
      });
      await action.mutateAsync({
        path: `/admin/requests/${assignIssueRow.id}/issue`,
        body: { evidence_id: values.evidenceId, remark: values.remark },
      });
      closeModals();
    } catch (error) {
      setModalError(error instanceof Error ? error.message : "Action failed.");
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
        </Panel>
      ) : null}
      <Panel title="Ready for handover">
        <RequestList
          rows={accepted.data?.results ?? []}
          actions={(row) => (
            <>
              <button disabled={action.isPending} onClick={() => openModal(setAssignIssueRow, row)}>Assign + issue</button>
              <button disabled={action.isPending} onClick={() => openModal(setDueRow, row)}>Set due</button>
            </>
          )}
        />
      </Panel>
      {!guestOnly ? (
        <Panel title="Active loans">
          <RequestList
            rows={active.data?.results ?? []}
            actions={(row) => (
              <>
                <button disabled={action.isPending} onClick={() => openModal(setDueRow, row)}>Set due</button>
                <button disabled={action.isPending} onClick={() => openModal(setReturnRow, row)}>Return</button>
              </>
            )}
          />
        </Panel>
      ) : null}
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
