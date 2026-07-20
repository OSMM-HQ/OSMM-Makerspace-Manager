import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { staffRequest } from "../../lib/api";
import { NotificationChannelPreferences } from "./NotificationChannelPreferences";
import type {
  MuteChange,
  NotificationFeature,
  NotificationRulesResponse,
  RuleCatalogEntry,
  RuleMute,
} from "./notificationRuleTypes";

export function NotificationMuteMatrix({ makerspaceId }: { makerspaceId: number }) {
  const queryClient = useQueryClient();
  const path = `/admin/makerspace/${makerspaceId}/notification-rules`;
  const queryKey = ["notification-rules", makerspaceId] as const;

  const rules = useQuery({
    queryKey,
    queryFn: () => staffRequest<NotificationRulesResponse>(path),
  });

  const updateMute = useMutation({
    mutationFn: (change: MuteChange) =>
      staffRequest<NotificationRulesResponse>(path, {
        method: "PATCH",
        body: JSON.stringify({ changes: [change] }),
      }),
    onMutate: async (change) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<NotificationRulesResponse>(queryKey);
      queryClient.setQueryData<NotificationRulesResponse>(queryKey, (current) =>
        current ? { ...current, mutes: applyMuteChange(current.mutes, change) } : current,
      );
      return { previous };
    },
    onError: (_error, _change, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey });
    },
  });

  if (rules.isLoading) {
    return <p className="mt-3 text-sm text-muted">Loading notification rules...</p>;
  }

  if (rules.error) {
    return <p className="mt-3 text-sm text-danger">{rules.error.message}</p>;
  }

  if (!rules.data) return null;

  return (
    <div className="mt-4 grid min-w-0 gap-6">
      <NotificationChannelPreferences makerspaceId={makerspaceId} rules={rules.data} />
      <section
        className="min-w-0 border-t border-line pt-5"
        aria-labelledby="advanced-email-mutes-heading"
      >
        <h4 id="advanced-email-mutes-heading" className="text-sm font-semibold text-ink">
          Advanced email recipient/event mutes
        </h4>
        <p className="mt-2 text-sm text-muted">
          Checked = muted for that individual email recipient and event. These mutes apply only
          while the matching feature&apos;s Email channel above is enabled. Return reminders cannot
          be individually muted.
        </p>
        <div className="mt-4 grid min-w-0 gap-4">
          {rules.data.catalog.map((entry) => {
            const emailEnabled = isEmailEnabled(entry, rules.data);
            const disabledMessageId = `email-disabled-${entry.stream}-${entry.audience}`;
            return (
              <section
                key={`${entry.stream}:${entry.audience}`}
                className="min-w-0 rounded-md border border-line bg-surface p-3"
              >
                <h5 className="text-sm font-semibold text-ink">
                  {streamLabel(entry.stream)} &middot; {audienceLabel(entry.audience)}
                </h5>
                {!emailEnabled ? (
                  <p id={disabledMessageId} className="mt-2 text-xs text-warn-ink">
                    Advanced mutes are read-only while this feature&apos;s Email channel is disabled.
                  </p>
                ) : null}
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
                          <th
                            className="whitespace-nowrap px-3 py-2 text-left font-semibold text-ink"
                            scope="row"
                          >
                            {targetLabel(target)}
                          </th>
                          {entry.events.map((eventName) => {
                            const checked = isMuted(rules.data.mutes, {
                              target,
                              stream: entry.stream,
                              event: eventName,
                              audience: entry.audience,
                            });
                            return (
                              <td key={eventName} className="px-3 py-2 text-center">
                                <input
                                  aria-describedby={!emailEnabled ? disabledMessageId : undefined}
                                  aria-label={`${checked ? "Unmute" : "Mute"} ${targetLabel(target)} ${humanize(eventName)}`}
                                  className="h-4 w-4"
                                  type="checkbox"
                                  checked={checked}
                                  disabled={updateMute.isPending || !emailEnabled}
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
            );
          })}
        </div>
        {updateMute.error ? (
          <p className="mt-3 text-sm text-danger" role="alert" aria-live="assertive">
            {updateMute.error.message}
          </p>
        ) : null}
      </section>
    </div>
  );
}

function isEmailEnabled(entry: RuleCatalogEntry, rules: NotificationRulesResponse) {
  const feature = featureForEntry(entry, rules.features);
  if (!feature) return true;
  return (
    rules.preferences.find(
      (cell) => cell.feature === feature.key && cell.channel === "email",
    )?.enabled ?? true
  );
}

function featureForEntry(entry: RuleCatalogEntry, features: NotificationFeature[]) {
  const aliases: Record<string, string> = {
    hardware: "hardware_requests",
    hardware_request: "hardware_requests",
    hardware_requests: "hardware_requests",
    print: "printing",
    printing: "printing",
  };
  const expectedKey = aliases[entry.stream] ?? entry.stream;
  return (
    features.find((feature) => feature.key === expectedKey) ??
    features.find((feature) =>
      entry.events.some((eventName) => feature.events.includes(eventName)),
    )
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
      machine_manager: "Machine managers",
    }[target] ?? humanize(target)
  );
}

function humanize(value: string) {
  const label = value.replace(/_/g, " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}
