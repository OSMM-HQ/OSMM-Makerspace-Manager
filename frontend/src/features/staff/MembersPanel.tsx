import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { StructuredApiError, staffRequest } from "../../lib/api";
import { Panel } from "./panels/shared";

type Page<T> = { results: T[] };
type Member = { id: number; status: string; user: { username: string; email: string; display_name: string }; assigned_role: { id: number; name: string } | null; waiver_current: boolean };
type MembershipRequest = { id: number; kind: string; state: string; user: { username: string; email: string } | null; invite_email: string; assigned_role: { id: number; name: string } | null };
type Presence = { display_name: string; role_label: string; started_at: string; expires_at: string };
type Role = { id: number; name: string };

const errorText = (error: unknown) => error instanceof StructuredApiError ? error.detail ?? error.message : "Unable to update membership.";

export function MembersPanel({ makerspaceId }: { makerspaceId: number }) {
  const client = useQueryClient();
  const key = ["members", makerspaceId];
  const roster = useQuery({ queryKey: [...key, "roster"], queryFn: () => staffRequest<Page<Member>>(`/admin/memberships?makerspace_id=${makerspaceId}`) });
  const requests = useQuery({ queryKey: [...key, "requests"], queryFn: () => staffRequest<Page<MembershipRequest>>(`/admin/membership-requests?makerspace_id=${makerspaceId}`) });
  const presence = useQuery({ queryKey: [...key, "presence"], queryFn: () => staffRequest<Presence[]>(`/admin/makerspace/${makerspaceId}/presence-sessions/current`) });
  const roles = useQuery({ queryKey: [...key, "roles"], queryFn: () => staffRequest<Role[]>(`/admin/makerspaces/${makerspaceId}/roles`) });
  const [roleId, setRoleId] = useState<number | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [waiver, setWaiver] = useState({ version: "", body: "" });
  const refresh = () => client.invalidateQueries({ queryKey: key });
  const revoke = useMutation({ mutationFn: (id: number) => staffRequest(`/admin/memberships/${id}/revoke`, { method: "POST", body: JSON.stringify({}) }), onSuccess: refresh });
  const revokeRequest = useMutation({ mutationFn: (id: number) => staffRequest(`/admin/membership-requests/${id}/revoke`, { method: "POST", body: JSON.stringify({}) }), onSuccess: refresh });
  const approve = useMutation({ mutationFn: (id: number) => staffRequest(`/admin/membership-requests/${id}/approve`, { method: "POST", body: JSON.stringify({ role_id: roleId }) }), onSuccess: refresh });
  const changeRole = useMutation({ mutationFn: ({ id, nextRoleId }: { id: number; nextRoleId: number }) => staffRequest(`/admin/memberships/${id}/role`, { method: "PATCH", body: JSON.stringify({ role_id: nextRoleId }) }), onSuccess: refresh });
  const invite = useMutation({ mutationFn: () => staffRequest(`/admin/makerspace/${makerspaceId}/membership-invitations`, { method: "POST", body: JSON.stringify({ invite_email: inviteEmail, role_id: roleId }) }), onSuccess: () => { setInviteEmail(""); refresh(); } });
  const publishWaiver = useMutation({ mutationFn: () => staffRequest(`/admin/makerspaces/${makerspaceId}/waiver`, { method: "PUT", body: JSON.stringify(waiver) }), onSuccess: refresh });
  const error = revoke.error ?? revokeRequest.error ?? approve.error ?? changeRole.error ?? invite.error ?? publishWaiver.error;
  const selectedRole = roleId ?? roles.data?.[0]?.id ?? null;
  return <div className="grid gap-5">
    <Panel title="Members"><p className="mb-4 text-sm text-muted">Membership, waiver compliance, and active presence for this makerspace.</p>
      {roster.data?.results.map((row) => <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line py-3" key={row.id}><div><p className="font-semibold text-ink">{row.user.display_name || row.user.username}</p><p className="text-xs text-muted">{row.assigned_role?.name ?? "Member"} · {row.status} · waiver {row.waiver_current ? "current" : "needed"}</p></div><div className="flex gap-2">{row.status === "active" ? <><select className="desk-input" defaultValue={row.assigned_role?.id ?? ""} onChange={(event) => changeRole.mutate({ id: row.id, nextRoleId: Number(event.target.value) })}>{roles.data?.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}</select><button className="desk-button" onClick={() => revoke.mutate(row.id)} disabled={revoke.isPending}>Revoke</button></> : null}</div></div>)}
      {roster.isLoading ? <p className="text-sm text-muted">Loading members…</p> : null}</Panel>
    <Panel title="Membership requests"><div className="mb-3 flex flex-wrap gap-2"><select className="desk-input" value={selectedRole ?? ""} onChange={(event) => setRoleId(Number(event.target.value))}>{roles.data?.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}</select><input className="desk-input" type="email" placeholder="Invite email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} /><button className="desk-button" disabled={!inviteEmail || !selectedRole || invite.isPending} onClick={() => invite.mutate()}>Invite</button></div>
      {requests.data?.results.map((row) => <div className="flex items-center justify-between gap-3 border-t border-line py-3" key={row.id}><span className="text-sm text-ink">{row.user?.username ?? row.invite_email} · {row.kind} · {row.state}</span>{row.state === "pending" ? <div className="flex gap-2"><button className="desk-button-primary" disabled={!selectedRole || approve.isPending} onClick={() => approve.mutate(row.id)}>Approve</button><button className="desk-button" onClick={() => revokeRequest.mutate(row.id)} disabled={revokeRequest.isPending}>Revoke</button></div> : null}</div>)}
      {requests.isLoading ? <p className="text-sm text-muted">Loading requests…</p> : null}</Panel>
    <Panel title="Currently present">{presence.data?.length ? presence.data.map((row) => <p className="border-t border-line py-2 text-sm text-ink" key={`${row.display_name}-${row.started_at}`}>{row.display_name} <span className="text-muted">· {row.role_label} · until {new Date(row.expires_at).toLocaleTimeString()}</span></p>) : <p className="text-sm text-muted">No active member presence sessions.</p>}</Panel>
    <Panel title="Current waiver"><div className="grid gap-2"><input className="desk-input" placeholder="Version" value={waiver.version} onChange={(event) => setWaiver({ ...waiver, version: event.target.value })} /><textarea className="desk-input min-h-28" placeholder="Waiver text" value={waiver.body} onChange={(event) => setWaiver({ ...waiver, body: event.target.value })} /><button className="desk-button-primary w-fit" disabled={!waiver.version || !waiver.body || publishWaiver.isPending} onClick={() => publishWaiver.mutate()}>Publish waiver</button></div></Panel>
    {error ? <p className="text-sm text-danger" role="alert">{errorText(error)}</p> : null}
  </div>;
}
