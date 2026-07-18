type Loan = { label: string; checked_out_at: string; due_at: string | null; overdue: boolean };
type PrintRequest = { title: string; status: string; queue_position: number | null };
type MachineServiceRequest = { title: string; status: string; queue_position: number | null };
type Booking = { space_name: string; starts_at: string; ends_at: string; status: string };
type Registration = { event_title: string; starts_at: string; status: string; waitlist_position: number | null };
type Presence = { started_at: string; expires_at: string; active: boolean };

export type MemberActivity = {
  active_hardware_loans: Loan[];
  print_requests?: PrintRequest[];
  machine_service_requests?: MachineServiceRequest[];
  bookings?: { upcoming: Booking[]; past: Booking[] };
  event_registrations?: Registration[];
  recent_presence_sessions: Presence[];
  currently_checked_in: boolean;
  accountability: { membership_active: boolean; waiver_acceptance_required: boolean; restriction_code: string | null };
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="desk-panel p-5"><h2 className="font-semibold text-ink">{title}</h2>{children}</section>;
}

function Empty({ children = "Nothing to show yet." }: { children?: React.ReactNode }) {
  return <p className="mt-2 text-sm text-muted">{children}</p>;
}

export function MemberActivityPanel({ activity }: { activity: MemberActivity }) {
  return <div className="space-y-5">
    <Section title="My activity">
      <p className="mt-1 text-sm text-muted">{activity.currently_checked_in ? "You are currently checked in." : "You are not currently checked in."}</p>
      {activity.accountability.waiver_acceptance_required ? <p className="mt-2 text-sm text-danger">Accept the current waiver before making facility requests.</p> : null}
    </Section>
    <Section title="Active hardware loans">
      {activity.active_hardware_loans.length ? <ul className="mt-3 space-y-2 text-sm text-muted">{activity.active_hardware_loans.map((loan) => <li key={`${loan.label}-${loan.checked_out_at}`}><span className="font-medium text-ink">{loan.label}</span>{loan.due_at ? ` · Due ${new Date(loan.due_at).toLocaleString()}` : " · No due date"}{loan.overdue ? " · Overdue" : ""}</li>)}</ul> : <Empty />}
    </Section>
    {activity.print_requests ? <Section title="3D print requests">{activity.print_requests.length ? <ul className="mt-3 space-y-2 text-sm text-muted">{activity.print_requests.map((item) => <li key={`${item.title}-${item.status}`}><span className="font-medium text-ink">{item.title}</span> · {item.status}{item.queue_position ? ` · Queue ${item.queue_position}` : ""}</li>)}</ul> : <Empty />}</Section> : null}
    {activity.machine_service_requests ? <Section title="Machine-service requests">{activity.machine_service_requests.length ? <ul className="mt-3 space-y-2 text-sm text-muted">{activity.machine_service_requests.map((item) => <li key={`${item.title}-${item.status}`}><span className="font-medium text-ink">{item.title}</span> · {item.status}{item.queue_position ? ` · Queue ${item.queue_position}` : ""}</li>)}</ul> : <Empty />}</Section> : null}
    {activity.bookings ? <Section title="Bookings"><div className="mt-3 grid gap-4 sm:grid-cols-2"><div><p className="text-sm font-medium text-ink">Upcoming</p>{activity.bookings.upcoming.length ? <ul className="mt-2 space-y-2 text-sm text-muted">{activity.bookings.upcoming.map((item) => <li key={`${item.space_name}-${item.starts_at}`}>{item.space_name} · {new Date(item.starts_at).toLocaleString()} · {item.status}</li>)}</ul> : <Empty />}</div><div><p className="text-sm font-medium text-ink">Past</p>{activity.bookings.past.length ? <ul className="mt-2 space-y-2 text-sm text-muted">{activity.bookings.past.map((item) => <li key={`${item.space_name}-${item.starts_at}`}>{item.space_name} · {new Date(item.starts_at).toLocaleString()} · {item.status}</li>)}</ul> : <Empty />}</div></div></Section> : null}
    {activity.event_registrations ? <Section title="Event registrations">{activity.event_registrations.length ? <ul className="mt-3 space-y-2 text-sm text-muted">{activity.event_registrations.map((item) => <li key={`${item.event_title}-${item.starts_at}`}><span className="font-medium text-ink">{item.event_title}</span> · {item.status}{item.waitlist_position ? ` · Waitlist ${item.waitlist_position}` : ""}</li>)}</ul> : <Empty />}</Section> : null}
    <Section title="Recent presence">{activity.recent_presence_sessions.length ? <ul className="mt-3 space-y-2 text-sm text-muted">{activity.recent_presence_sessions.map((item) => <li key={item.started_at}>{new Date(item.started_at).toLocaleString()} to {new Date(item.expires_at).toLocaleString()}{item.active ? " · Active" : ""}</li>)}</ul> : <Empty />}</Section>
  </div>;
}
