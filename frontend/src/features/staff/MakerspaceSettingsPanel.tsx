import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../components/ui";
import { staffRequest } from "../../lib/api";
import { ImageUploader } from "./ImageUploader";
import { MakerspaceEmailSettings } from "./MakerspaceEmailSettings";
import { MakerspaceLocationSettings } from "./MakerspaceLocationSettings";
import { NotificationMuteMatrix } from "./NotificationMuteMatrix";
import { Panel, type Makerspace, useStaffGet } from "./StaffPanels";

type Props = {
  makerspace: Makerspace;
  isSuperadmin: boolean;
};

export function MakerspaceSettingsPanel({ makerspace, isSuperadmin }: Props) {
  const queryClient = useQueryClient();
  const [domainInput, setDomainInput] = useState("");
  const [hideFromDirectory, setHideFromDirectory] = useState(false);
  const [displayNameInput, setDisplayNameInput] = useState("");
  const settings = useStaffGet<Makerspace>(
    ["makerspace-settings", makerspace.id],
    `/admin/makerspaces/${makerspace.id}`,
  );
  const superadminAccessEnabled =
    settings.data?.superadmin_access_enabled ?? makerspace.superadmin_access_enabled ?? true;
  const staffNotificationsEnabled =
    settings.data?.staff_notifications_enabled ?? makerspace.staff_notifications_enabled ?? true;
  const publicStatsEnabled =
    settings.data?.public_stats_enabled ?? makerspace.public_stats_enabled ?? false;
  const publicPrintStatusLookupPolicy =
    settings.data?.public_print_status_lookup_policy ?? makerspace.public_print_status_lookup_policy ?? "email_unverified";
  const reEnableBlocked = isSuperadmin && !superadminAccessEnabled;

  const updateAccess = useMutation({
    mutationFn: (next: boolean) =>
      staffRequest<Makerspace>(`/admin/makerspaces/${makerspace.id}`, {
        method: "PATCH",
        body: JSON.stringify({ superadmin_access_enabled: next }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["makerspaces"] });
      queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
    },
  });

  const updateStaffNotifications = useMutation({
    mutationFn: (next: boolean) =>
      staffRequest<Makerspace>(`/admin/makerspaces/${makerspace.id}`, {
        method: "PATCH",
        body: JSON.stringify({ staff_notifications_enabled: next }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["makerspaces"] });
      queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
    },
  });

  const updatePublicStats = useMutation({
    mutationFn: (next: boolean) =>
      staffRequest<Makerspace>(`/admin/makerspaces/${makerspace.id}`, {
        method: "PATCH",
        body: JSON.stringify({ public_stats_enabled: next }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["makerspaces"] });
      queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
    },
  });
  const updatePrintStatusLookupPolicy = useMutation({
    mutationFn: (next: Makerspace["public_print_status_lookup_policy"]) =>
      staffRequest<Makerspace>(`/admin/makerspaces/${makerspace.id}`, {
        method: "PATCH",
        body: JSON.stringify({ public_print_status_lookup_policy: next }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["makerspaces"] });
      queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
    },
  });

  const currentDomain = settings.data?.frontend_domain ?? makerspace.frontend_domain ?? null;
  const currentHidden =
    settings.data?.hidden_from_central_directory ?? makerspace.hidden_from_central_directory ?? false;
  const currentDisplayName = settings.data?.branding_config?.display_name ?? "";

  useEffect(() => {
    setDomainInput(currentDomain ?? "");
    setHideFromDirectory(Boolean(currentDomain) && currentHidden);
  }, [currentDomain, currentHidden, makerspace.id]);

  useEffect(() => {
    setDisplayNameInput(currentDisplayName);
  }, [currentDisplayName, makerspace.id]);

  const updateDisplayName = useMutation({
    mutationFn: (value: string) =>
      staffRequest<Makerspace>(`/admin/makerspaces/${makerspace.id}`, {
        method: "PATCH",
        body: JSON.stringify({ public_display_name: value }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["makerspaces"] });
      queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
    },
  });

  const trimmedDisplayName = displayNameInput.trim();
  const displayNameChanged = trimmedDisplayName !== currentDisplayName.trim();
  const displayNameSaveDisabled =
    settings.isLoading || updateDisplayName.isPending || !displayNameChanged;

  const trimmedDomain = domainInput.trim();
  const hasDomain = trimmedDomain.length > 0;
  const effectiveHidden = hasDomain ? hideFromDirectory : false;
  const domainChanged = trimmedDomain !== (currentDomain ?? "");
  const hiddenChanged = effectiveHidden !== currentHidden;
  const customDomainUrls = useMemo(
    () => [`https://${trimmedDomain}/`, `https://${trimmedDomain}/admin`],
    [trimmedDomain],
  );

  const updateCustomDomain = useMutation({
    mutationFn: () =>
      staffRequest<Makerspace>(`/admin/makerspaces/${makerspace.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          frontend_domain: trimmedDomain,
          hidden_from_central_directory: effectiveHidden,
        }),
      }),
    onSuccess: (updated) => {
      setDomainInput(updated.frontend_domain ?? "");
      setHideFromDirectory(
        Boolean(updated.frontend_domain) && updated.hidden_from_central_directory,
      );
      queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
      queryClient.invalidateQueries({ queryKey: ["makerspaces"] });
      queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
    },
  });

  const nextValue = !superadminAccessEnabled;
  const disabled = settings.isLoading || updateAccess.isPending || reEnableBlocked;
  const notificationsDisabled = settings.isLoading || updateStaffNotifications.isPending;
  const domainSaveDisabled =
    settings.isLoading ||
    updateCustomDomain.isPending ||
    (!domainChanged && !hiddenChanged);

  const refreshBranding = () => {
    queryClient.invalidateQueries({ queryKey: ["makerspace-settings", makerspace.id] });
    queryClient.invalidateQueries({ queryKey: ["makerspaces"] });
    queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
  };

  return (
    <Panel title="Makerspace settings">
      <div className="grid min-w-0 gap-4">
        <div className="min-w-0 rounded-md border border-line bg-bg p-4">
          <h3 className="text-base font-semibold text-ink">Branding</h3>
          <p className="mt-1 text-sm text-muted">
            Logo and cover image shown on this makerspace&apos;s public pages. When no
            logo is set, the makerspace name is shown as the wordmark.
          </p>
          <div className="mt-4 grid min-w-0 gap-4 lg:grid-cols-2">
            <ImageUploader
              endpoint={`/admin/makerspace/${makerspace.id}/logo`}
              currentUrl={settings.data?.logo_url}
              label="Logo"
              fit="contain"
              onChanged={refreshBranding}
            />
            <ImageUploader
              endpoint={`/admin/makerspace/${makerspace.id}/cover`}
              currentUrl={settings.data?.cover_image_url}
              label="Cover image (wide banner)"
              shape="wide"
              onChanged={refreshBranding}
            />
          </div>
          <form
            className="mt-4 grid min-w-0 max-w-xl gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (!displayNameSaveDisabled) {
                updateDisplayName.mutate(trimmedDisplayName);
              }
            }}
          >
            <label className="text-sm font-semibold text-ink" htmlFor="public-display-name">
              Public display name
            </label>
            <input
              id="public-display-name"
              className="desk-input"
              placeholder={makerspace.name}
              value={displayNameInput}
              disabled={settings.isLoading}
              onChange={(event) => setDisplayNameInput(event.target.value)}
            />
            <p className="text-xs text-muted">
              Shown on this makerspace&apos;s public pages. Leave blank to use the registered
              name (<span className="font-semibold text-ink">{makerspace.name}</span>).
            </p>
            <div>
              <button
                className="desk-button-primary w-full max-w-full sm:w-auto"
                type="submit"
                disabled={displayNameSaveDisabled}
              >
                {updateDisplayName.isPending ? "Saving..." : "Save display name"}
              </button>
            </div>
            {updateDisplayName.error ? (
              <p className="text-sm text-danger">{updateDisplayName.error.message}</p>
            ) : null}
          </form>
        </div>
        <MakerspaceLocationSettings
          makerspace={makerspace}
          settings={settings.data}
          loading={settings.isLoading}
        />
        <div className="min-w-0 rounded-md border border-line bg-bg p-4">
          <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
            <div className="grid min-w-0 max-w-2xl gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold text-ink">Superadmin access</h3>
                <Badge tone={superadminAccessEnabled ? "success" : "warn"}>
                  {superadminAccessEnabled ? "On" : "Off"}
                </Badge>
              </div>
              <p className="text-sm text-muted">
                When off, this makerspace is hidden from the superadmin's reports, dashboards, audit,
                and admin lists. It does not revoke the superadmin's platform/database access. Only
                the makerspace admin can turn it back on.
              </p>
              {reEnableBlocked ? (
                <p className="text-sm text-muted">Re-enable is controlled by the makerspace admin.</p>
              ) : null}
              {updateAccess.error ? <p className="text-sm text-danger">{updateAccess.error.message}</p> : null}
            </div>
            <button
              className={`${superadminAccessEnabled ? "desk-button" : "desk-button-primary"} w-full max-w-full justify-self-start sm:w-auto md:justify-self-end`}
              type="button"
              disabled={disabled}
              onClick={() => updateAccess.mutate(nextValue)}
            >
              {updateAccess.isPending
                ? "Saving..."
                : superadminAccessEnabled
                  ? "Turn off access"
                  : "Turn on access"}
            </button>
          </div>
        </div>
        <div className="min-w-0 rounded-md border border-line bg-bg p-4">
          <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
            <div className="grid min-w-0 max-w-2xl gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold text-ink">Staff email notifications</h3>
                <Badge tone={staffNotificationsEnabled ? "success" : "neutral"}>
                  {staffNotificationsEnabled ? "On" : "Off"}
                </Badge>
              </div>
              <p className="text-sm text-muted">
                Email this makerspace&apos;s managers when hardware and print request statuses change.
              </p>
              {updateStaffNotifications.error ? (
                <p className="text-sm text-danger">{updateStaffNotifications.error.message}</p>
              ) : null}
            </div>
            <label className="flex min-w-0 items-start gap-3 text-sm text-ink sm:justify-self-start md:justify-self-end">
              <input
                className="mt-1 h-4 w-4"
                type="checkbox"
                checked={staffNotificationsEnabled}
                disabled={notificationsDisabled}
                onChange={(event) => updateStaffNotifications.mutate(event.target.checked)}
              />
              <span className="font-semibold">Send staff emails</span>
            </label>
          </div>
        </div>
        <div className="min-w-0 rounded-md border border-line bg-bg p-4">
          <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
            <div className="grid min-w-0 max-w-2xl gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold text-ink">Public stats page</h3>
                <Badge tone={publicStatsEnabled ? "success" : "neutral"}>
                  {publicStatsEnabled ? "On" : "Off"}
                </Badge>
              </div>
              <p className="text-sm text-muted">
                Publish a public activity page (print hours, popular hardware, who currently has tools
                out by name) at <code>/m/{makerspace.slug}/stats</code>. When off, the page and its API
                return 404 and the link is hidden.
              </p>
              {updatePublicStats.error ? (
                <p className="text-sm text-danger">{updatePublicStats.error.message}</p>
              ) : null}
            </div>
            <label className="flex min-w-0 items-start gap-3 text-sm text-ink sm:justify-self-start md:justify-self-end">
              <input
                className="mt-1 h-4 w-4"
                type="checkbox"
                checked={publicStatsEnabled}
                disabled={updatePublicStats.isPending}
                onChange={(event) => updatePublicStats.mutate(event.target.checked)}
              />
              <span className="font-semibold">Publish public stats</span>
            </label>
          </div>
        </div>
        <div className="min-w-0 rounded-md border border-line bg-bg p-4">
          <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_minmax(220px,280px)] md:items-start">
            <div className="grid min-w-0 max-w-2xl gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold text-ink">Public print status recovery</h3>
                <Badge tone={publicPrintStatusLookupPolicy === "token_only" ? "neutral" : "success"}>
                  {statusLookupLabel(publicPrintStatusLookupPolicy)}
                </Badge>
              </div>
              <p className="text-sm text-muted">
                Controls whether public print requests can be recovered from an email address when the status link is lost.
              </p>
              {updatePrintStatusLookupPolicy.error ? (
                <p className="text-sm text-danger">{updatePrintStatusLookupPolicy.error.message}</p>
              ) : null}
            </div>
            <select
              className="desk-input w-full"
              value={publicPrintStatusLookupPolicy}
              disabled={settings.isLoading || updatePrintStatusLookupPolicy.isPending}
              onChange={(event) => updatePrintStatusLookupPolicy.mutate(event.target.value as Makerspace["public_print_status_lookup_policy"])}
            >
              <option value="token_only">Token only</option>
              <option value="email_unverified">Email lookup</option>
              <option value="checkin_verified">Check-In verified</option>
            </select>
          </div>
        </div>
        <MakerspaceEmailSettings makerspace={makerspace} />
        <div className="min-w-0 rounded-md border border-line bg-bg p-4">
          <form
            className="grid min-w-0 gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (!domainSaveDisabled) {
                updateCustomDomain.mutate();
              }
            }}
          >
            <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
              <div className="grid min-w-0 max-w-2xl gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-semibold text-ink">Custom domain</h3>
                  <Badge tone={hasDomain ? "success" : "neutral"}>
                    {hasDomain ? "Set" : "Not set"}
                  </Badge>
                </div>
                <p className="text-sm text-muted">
                  Route this makerspace's public and staff surfaces through a dedicated domain.
                </p>
              </div>
              <button
                className="desk-button-primary w-full max-w-full justify-self-start sm:w-auto md:justify-self-end"
                type="submit"
                disabled={domainSaveDisabled}
              >
                {updateCustomDomain.isPending ? "Saving..." : "Save domain"}
              </button>
            </div>

            <div className="grid min-w-0 max-w-xl gap-2">
              <label className="text-sm font-semibold text-ink" htmlFor="custom-domain">
                Domain
              </label>
              <input
                id="custom-domain"
                className="desk-input"
                placeholder="alphamakerspace.com"
                value={domainInput}
                onChange={(event) => {
                  const next = event.target.value;
                  setDomainInput(next);
                  if (!next.trim()) {
                    setHideFromDirectory(false);
                  }
                }}
              />
            </div>

            <label className="flex min-w-0 max-w-xl items-start gap-3 text-sm text-ink">
              <input
                className="mt-1 h-4 w-4"
                type="checkbox"
                checked={effectiveHidden}
                disabled={!hasDomain}
                onChange={(event) => setHideFromDirectory(event.target.checked)}
              />
              <span>
                <span className="font-semibold">Hide from central directory</span>
                <span className="block text-muted">
                  Available only after a custom domain is set.
                </span>
              </span>
            </label>

            {hasDomain ? (
              <div className="min-w-0 overflow-x-auto rounded-md border border-line bg-surface p-3 text-sm text-muted">
                <p className="font-semibold text-ink">Resulting URLs</p>
                <ul className="mt-2 grid gap-1">
                  {customDomainUrls.map((url) => (
                    <li className="break-all" key={url}>{url}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {updateCustomDomain.error ? (
              <p className="text-sm text-danger">{updateCustomDomain.error.message}</p>
            ) : null}
          </form>
        </div>
        <div className="min-w-0 rounded-md border border-line bg-bg p-4">
          <h3 className="text-base font-semibold text-ink">Email notifications: mute matrix</h3>
          <NotificationMuteMatrix makerspaceId={makerspace.id} />
        </div>
      </div>
    </Panel>
  );
}

function statusLookupLabel(policy: Makerspace["public_print_status_lookup_policy"]) {
  return {
    token_only: "Token only",
    email_unverified: "Email lookup",
    checkin_verified: "Check-In verified",
  }[policy ?? "email_unverified"];
}
