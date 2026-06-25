import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { staffRequest } from "../../lib/api";

type RuleCatalogEntry = {
  stream: string;
  audience: string;
  targets: string[];
  events: string[];
};

type RuleMute = {
  target: string;
  stream: string;
  event: string;
  audience: string;
};

type NotificationRulesResponse = {
  catalog: RuleCatalogEntry[];
  mutes: RuleMute[];
};

type MuteChange = RuleMute & {
  muted: boolean;
};

export function NotificationMuteMatrix({ makerspaceId }: { makerspaceId: number }) {
  const queryClient = useQueryClient();
  const path = `/admin/makerspace/${makerspaceId}/notification-rules`;

  const rules = useQuery({
    queryKey: ["notification-rules", makerspaceId],
    queryFn: () => staffRequest<NotificationRulesResponse>(path),
  });

  const updateMute = useMutation({
    mutationFn: (change: MuteChange) =>
      staffRequest<NotificationRulesResponse>(path, {
        method: "PATCH",
        body: JSON.stringify({ changes: [change] }),
      }),
    onMutate: async (change) => {
      const queryKey = ["notification-rules", makerspaceId] as const;
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<NotificationRulesResponse>(queryKey);
      queryClient.setQueryData<NotificationRulesResponse>(queryKey, (current) =>
        current ? { ...current, mutes: applyMuteChange(current.mutes, change) } : current,
      );
      return { queryKey, previous };
    },
    onError: (_error, _change, context) => {
      if (context?.previous) queryClient.setQueryData(context.queryKey, context.previous);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["notification-rules", makerspaceId] });
    },
  });

  if (rules.isLoading) {
    return <p className="mt-3 text-sm text-muted">Loading notification rules...</p>;
  }

  if (rules.error) {
    return <p className="mt-3 text-sm text-danger">{rules.error.message}</p>;
  }

  const mutes = rules.data?.mutes ?? [];

  return (
    <div className="mt-4 grid min-w-0 gap-4">
      <p className="text-sm text-muted">
        Checked = muted (that email is not sent). Return reminders are always sent and
        can&apos;t be muted.
      </p>
      {rules.data?.catalog.map((entry) => (
        <section
          key={`${entry.stream}:${entry.audience}`}
          className="min-w-0 rounded-md border border-line bg-surface p-3"
        >
          <h4 className="text-sm font-semibold text-ink">
            {streamLabel(entry.stream)} &middot; {audienceLabel(entry.audience)}
          </h4>
          <div className="mt-3 max-w-full overflow-x-auto rounded-md border border-line bg-bg">
            <table className="w-max min-w-full border-collapse text-sm">
              <caption className="sr-only">
                Checked boxes mute emails for {streamLabel(entry.stream)}{" "}
                {audienceLabel(entry.audience)}.
              </caption>
              <thead className="bg-surface text-xs uppercase text-muted">
                <tr className="border-b border-line">
                  <th className="px-3 py-2 text-left font-semibold" scope="col">
                    Target
                  </th>
                  {entry.events.map((eventName) => (
                    <th
                      key={eventName}
                      className="min-w-32 max-w-40 whitespace-normal px-3 py-2 text-center font-semibold leading-snug"
                      scope="col"
                    >
                      {humanize(eventName)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {entry.targets.map((target) => (
                  <tr key={target} className="border-b border-line last:border-b-0">
                    <th className="whitespace-nowrap px-3 py-2 text-left font-semibold text-ink" scope="row">
                      {targetLabel(target)}
                    </th>
                    {entry.events.map((eventName) => {
                      const checked = isMuted(mutes, {
                        target,
                        stream: entry.stream,
                        event: eventName,
                        audience: entry.audience,
                      });
                      return (
                        <td key={eventName} className="px-3 py-2 text-center">
                          <input
                            aria-label={`${checked ? "Unmute" : "Mute"} ${targetLabel(target)} ${humanize(eventName)}`}
                            className="h-4 w-4"
                            type="checkbox"
                            checked={checked}
                            disabled={updateMute.isPending}
                            onChange={(event) =>
                              updateMute.mutate({
                                target,
                                stream: entry.stream,
                                event: eventName,
                                audience: entry.audience,
                                muted: event.target.checked,
                              })
                            }
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      {updateMute.error ? (
        <p className="text-sm text-danger">{updateMute.error.message}</p>
      ) : null}
    </div>
  );
}

function applyMuteChange(mutes: RuleMute[], change: MuteChange) {
  const withoutCurrent = mutes.filter((mute) => !matchesMute(mute, change));
  return change.muted ? [...withoutCurrent, change] : withoutCurrent;
}

function isMuted(mutes: RuleMute[], candidate: RuleMute) {
  return mutes.some((mute) => matchesMute(mute, candidate));
}

function matchesMute(mute: RuleMute, candidate: RuleMute) {
  return (
    mute.target === candidate.target &&
    mute.stream === candidate.stream &&
    mute.event === candidate.event &&
    mute.audience === candidate.audience
  );
}

function streamLabel(stream: string) {
  return humanize(stream);
}

function audienceLabel(audience: string) {
  if (audience === "requester") return "Requester emails";
  if (audience === "staff") return "Staff emails";
  return `${humanize(audience)} emails`;
}

function targetLabel(target: string) {
  return (
    {
      requester: "Requesters",
      space_manager: "Space managers",
      inventory_manager: "Inventory managers",
      print_manager: "Print managers",
    }[target] ?? humanize(target)
  );
}

function humanize(value: string) {
  const label = value.replace(/_/g, " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}
