import { useStaffGet } from "./shared";
import type { ReportCell } from "./OperationsReportsParts";

export type MemberActivityRow = {
  makerspace_id?: number;
  makerspace_name: string;
  membership_policy: string;
  referrals_enabled: boolean;
  new_members: number;
  active_members: number;
  revoked_members: number;
  pending_requests: number;
  open_invites: number;
  referred_joins: number;
  verified_members: number;
};

export type MemberActivityReport = {
  rows: ReportCell[][];
  typed_rows: MemberActivityRow[];
};

export type MemberActivityReportProps = {
  makerspaceId: number;
  aggregate: boolean;
  startDate: string;
  endDate: string;
  enabled: boolean;
};

export function useMemberActivityReport({ makerspaceId, aggregate, startDate, endDate, enabled }: MemberActivityReportProps) {
  const scope = aggregate ? "all" : makerspaceId;
  const base = aggregate ? "/admin/analytics" : `/admin/makerspace/${makerspaceId}/analytics`;
  const query = new URLSearchParams({ limit: "100" });
  if (startDate) query.set("start", startDate);
  if (endDate) query.set("end", endDate);
  return useStaffGet<MemberActivityReport>(
    ["member-activity-report", scope, startDate, endDate],
    `${base}/member-activity?${query.toString()}`,
    enabled,
  );
}
