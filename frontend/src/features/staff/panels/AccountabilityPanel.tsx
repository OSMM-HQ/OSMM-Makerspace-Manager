import { useMutation, useQueryClient } from "@tanstack/react-query";

import { staffRequest } from "../../../lib/api";
import { Panel, type Makerspace, useStaffGet } from "./shared";

type Offender = {
  requester_id: number;
  username: string;
  access_status: string;
  restriction_reason: string;
  damaged: number;
  missing: number;
  total_issues: number;
  total_quantity: number;
};
type Overdue = {
  type: "request" | "direct";
  reference_id: number;
  requester_username: string;
  label: string;
  due_at: string;
  days_overdue: number;
};
type Restriction = { requester_id: number; username: string; access_status: string; restriction_reason: string };
type ProblemReport = { id: number; requester_username: string; label: string; note: string; created_at: string };
type AccountabilityResponse = {
  repeat_offenders: Offender[];
  overdue: Overdue[];
  restrictions: Restriction[];
  problem_reports: ProblemReport[];
  truncated: { repeat_offenders: boolean; overdue: boolean; problem_reports: boolean };
};

export function AccountabilityPanel({ makerspace, isSuperadmin }: { makerspace: Makerspace; isSuperadmin: boolean }) {
  const queryClient = useQueryClient();
  const report = useStaffGet<AccountabilityResponse>(["accountability", makerspace.id], `/admin/makerspace/${makerspace.id}/accountability`);
  const data = report.data;

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["accountability", makerspace.id] });
  };
  const restrict = useMutation({
    mutationFn: ({ userId, reason }: { userId: number; reason: string }) =>
      staffRequest(`/admin/users/${userId}/restrict`, {
        method: "POST",
        body: JSON.stringify({ status: "restricted", reason }),
      }),
    onSuccess: refresh,
  });
  const restore = useMutation({
    mutationFn: (userId: number) => staffRequest(`/admin/users/${userId}/restore-access`, { method: "POST" }),
    onSuccess: refresh,
  });
  const resolveReport = useMutation({
    mutationFn: (reportId: number) =>
      staffRequest(`/admin/makerspace/${makerspace.id}/problem-reports/${reportId}/resolve`, { method: "POST" }),
    onSuccess: refresh,
  });

  return (
    <div className="grid gap-4">
      {report.isLoading ? <p className="text-sm text-muted">Loading accountability...</p> : null}
      {report.error ? <p className="text-sm text-danger">{(report.error as Error).message}</p> : null}

      <Panel title="Overdue loans">
        {!data?.overdue.length ? (
          <p className="text-sm text-muted">No overdue loans.</p>
        ) : (
          <div className="grid gap-2">
            {data.overdue.map((row) => (
              <div key={`${row.type}-${row.reference_id}`} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line bg-surface p-2 text-sm">
                <div className="min-w-0">
                  <p className="font-medium text-ink">{row.label || "(unnamed)"}</p>
                  <p className="text-xs text-muted">{row.requester_username} | {row.type === "direct" ? "direct handout" : "request"}</p>
                </div>
                <span className="status-box status-box-danger">{row.days_overdue}d overdue</span>
              </div>
            ))}
            {data.truncated.overdue ? <p className="text-xs text-muted">Showing the earliest overdue loans only.</p> : null}
          </div>
        )}
      </Panel>

      <Panel title="Reported problems">
        {!data?.problem_reports.length ? (
          <p className="text-sm text-muted">No open problem reports from public returns.</p>
        ) : (
          <div className="grid gap-2">
            {data.problem_reports.map((row) => (
              <div key={row.id} className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-line bg-surface p-2 text-sm">
                <div className="min-w-0">
                  <p className="font-medium text-ink">{row.label || "(tool)"}</p>
                  <p className="text-xs text-muted">{row.requester_username} | {new Date(row.created_at).toLocaleString()}</p>
                  <p className="mt-1 break-words text-ink">{row.note}</p>
                </div>
                <button className="desk-button" type="button" disabled={resolveReport.isPending} onClick={() => resolveReport.mutate(row.id)}>
                  Resolve
                </button>
              </div>
            ))}
            {data.truncated.problem_reports ? <p className="text-xs text-muted">Showing the oldest open reports only.</p> : null}
          </div>
        )}
      </Panel>

      <Panel title="Repeat offenders">
        {!data?.repeat_offenders.length ? (
          <p className="text-sm text-muted">No damage or loss on record.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[36rem] text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-muted">
                  <th className="p-2">Requester</th>
                  <th className="p-2">Damaged</th>
                  <th className="p-2">Missing</th>
                  <th className="p-2">Total issues</th>
                  <th className="p-2">Status</th>
                  {isSuperadmin ? <th className="p-2">Action</th> : null}
                </tr>
              </thead>
              <tbody>
                {data.repeat_offenders.map((row) => (
                  <tr key={row.requester_id} className="border-t border-line">
                    <td className="p-2 font-medium text-ink">{row.username}</td>
                    <td className="p-2">{row.damaged}</td>
                    <td className="p-2">{row.missing}</td>
                    <td className="p-2">{row.total_issues} ({row.total_quantity} units)</td>
                    <td className="p-2 capitalize">{row.access_status}</td>
                    {isSuperadmin ? (
                      <td className="p-2">
                        {row.access_status === "active" ? (
                          <button
                            className="desk-button"
                            type="button"
                            disabled={restrict.isPending}
                            onClick={() => {
                              const reason = window.prompt("Reason for restricting this requester?");
                              if (reason && reason.trim()) restrict.mutate({ userId: row.requester_id, reason: reason.trim() });
                            }}
                          >
                            Restrict
                          </button>
                        ) : (
                          <button className="desk-button" type="button" disabled={restore.isPending} onClick={() => restore.mutate(row.requester_id)}>
                            Restore
                          </button>
                        )}
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
            {data.truncated.repeat_offenders ? <p className="mt-2 text-xs text-muted">Showing the top offenders only.</p> : null}
          </div>
        )}
      </Panel>

      <Panel title="Restricted requesters">
        {!data?.restrictions.length ? (
          <p className="text-sm text-muted">No restricted requesters with accountability records here.</p>
        ) : (
          <div className="grid gap-2">
            {data.restrictions.map((row) => (
              <div key={row.requester_id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line bg-surface p-2 text-sm">
                <div className="min-w-0">
                  <p className="font-medium text-ink">{row.username} <span className="text-xs capitalize text-muted">({row.access_status})</span></p>
                  {row.restriction_reason ? <p className="text-xs text-muted">{row.restriction_reason}</p> : null}
                </div>
                {isSuperadmin ? (
                  <button className="desk-button" type="button" disabled={restore.isPending} onClick={() => restore.mutate(row.requester_id)}>
                    Restore access
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </Panel>
      {restrict.error ? <p className="text-sm text-danger">{(restrict.error as Error).message}</p> : null}
      {restore.error ? <p className="text-sm text-danger">{(restore.error as Error).message}</p> : null}
      {resolveReport.error ? <p className="text-sm text-danger">{(resolveReport.error as Error).message}</p> : null}
    </div>
  );
}
