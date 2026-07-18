import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { bootstrapTenant, refreshAccessToken, setAccessToken, StructuredApiError, staffRequest } from "../../lib/api";
import { LoginPanel } from "../staff/LoginPanel";

type Membership = { makerspace: { slug: string; name: string }; membership_status: string; role: string; waiver_acceptance_required: boolean };
type Memberships = { memberships: Membership[]; requests: { makerspace: { slug: string; name: string }; state: string; kind: string }[] };
type Waiver = { has_waiver: boolean; body?: string; version?: string };
type Presence = { active: boolean; session: { expires_at: string } | null };

function message(error: unknown) {
  if (error instanceof StructuredApiError && error.status === 401) return "Sign in to manage your membership.";
  return error instanceof Error ? error.message : "Unable to complete that action.";
}

export function MemberArea() {
  const { slug = "" } = useParams();
  const client = useQueryClient();
  const [restoring, setRestoring] = useState(true);
  useEffect(() => {
    refreshAccessToken().then(() => client.invalidateQueries({ queryKey: ["member"] })).finally(() => setRestoring(false));
  }, [client]);
  const memberships = useQuery({ queryKey: ["member", "memberships"], queryFn: () => staffRequest<Memberships>("/memberships/me"), retry: false });
  const membership = memberships.data?.memberships.find((row) => row.makerspace.slug === slug);
  const bootstrap = useQuery({ queryKey: ["member", slug, "bootstrap"], queryFn: () => bootstrapTenant({ slug }), enabled: Boolean(slug), retry: false });
  const makerspaceId = bootstrap.data?.makerspace.id ?? -1;
  const waiver = useQuery({ queryKey: ["member", slug, "waiver"], queryFn: () => staffRequest<Waiver>(`/member/makerspaces/${makerspaceId}/waiver`), enabled: makerspaceId >= 0, retry: false });
  const presence = useQuery({ queryKey: ["member", slug, "presence"], queryFn: () => staffRequest<Presence>(`/public/${slug}/presence-sessions/current`), enabled: Boolean(slug), retry: false });
  const refresh = () => client.invalidateQueries({ queryKey: ["member"] });
  const request = useMutation({ mutationFn: () => staffRequest(`/public/${slug}/membership-requests`, { method: "POST", body: JSON.stringify({}) }), onSuccess: refresh });
  const accept = useMutation({ mutationFn: () => staffRequest(`/member/makerspaces/${makerspaceId}/waiver/accept`, { method: "POST" }), onSuccess: refresh });
  const start = useMutation({ mutationFn: () => staffRequest(`/public/${slug}/presence-sessions`, { method: "POST", body: JSON.stringify({ duration_minutes: 120 }) }), onSuccess: refresh });
  const end = useMutation({ mutationFn: () => staffRequest(`/public/${slug}/presence-sessions/current/end`, { method: "POST" }), onSuccess: refresh });
  const error = memberships.error ?? request.error ?? accept.error ?? start.error ?? end.error;
  const login = useMutation({ mutationFn: (payload: { username: string; password: string }) => staffRequest<{ access: string }>("/auth/login", { method: "POST", credentials: "include", body: JSON.stringify(payload) }), onSuccess: (data) => { setAccessToken(data.access); client.invalidateQueries({ queryKey: ["member"] }); } });

  if (restoring) return <main className="desk-shell grid place-items-center px-5 text-sm text-muted">Restoring session…</main>;
  if (memberships.error instanceof StructuredApiError && memberships.error.status === 401) return <LoginPanel guestOnly={false} isPending={login.isPending} error={login.error?.message} onSubmit={login.mutate} />;

  return <main className="desk-shell mx-auto max-w-3xl space-y-5 px-5 py-8"><header><p className="text-xs font-semibold uppercase tracking-wide text-accent-ink">Member area</p><h1 className="mt-2 text-3xl font-bold text-ink">Your makerspace access</h1></header>
    {memberships.isError ? <div className="desk-panel p-5"><p className="text-sm text-muted">{message(error)}</p><Link className="desk-button-primary mt-4 inline-flex" to="/admin">Sign in</Link></div> : null}
    {memberships.data && !membership ? <section className="desk-panel p-5"><h2 className="font-semibold text-ink">Join this makerspace</h2><p className="mt-1 text-sm text-muted">Send a membership request for staff approval.</p><button className="desk-button-primary mt-4" disabled={request.isPending} onClick={() => request.mutate()}>{request.isPending ? "Sending…" : "Request membership"}</button></section> : null}
    {membership ? <><section className="desk-panel p-5"><h2 className="font-semibold text-ink">Membership</h2><p className="mt-1 text-sm text-muted">{membership.makerspace.name} · {membership.membership_status} · {membership.role}</p></section>
      {waiver.data?.has_waiver ? <section className="desk-panel p-5"><h2 className="font-semibold text-ink">Current waiver ({waiver.data.version})</h2><p className="mt-3 whitespace-pre-wrap text-sm text-muted">{waiver.data.body}</p><button className="desk-button-primary mt-4" disabled={accept.isPending} onClick={() => accept.mutate()}>Accept waiver</button></section> : null}
      <section className="desk-panel p-5"><h2 className="font-semibold text-ink">Presence</h2><p className="mt-1 text-sm text-muted">{presence.data?.active ? `Active until ${new Date(presence.data.session?.expires_at ?? "").toLocaleTimeString()}` : "No active session."}</p><button className="desk-button-primary mt-4" disabled={start.isPending || end.isPending} onClick={() => presence.data?.active ? end.mutate() : start.mutate()}>{presence.data?.active ? "End presence" : "Start 2-hour presence"}</button></section></> : null}
    {error && !memberships.isError ? <p className="text-sm text-danger" role="alert">{message(error)}</p> : null}
  </main>;
}
