import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { staffRequest } from "../../lib/api";
import { Panel, type Makerspace, useStaffGet } from "./StaffPanels";

type ApiKeyRequest = {
  id: number;
  label: string;
  reason: string;
  status: "pending" | "approved" | "rejected";
  resolution_note: string;
  allowed_origins: string[];
  created_at: string;
  resolved_at: string | null;
};
type ApiSettings = {
  public_code: string;
  cors_allowed_origins: string[];
  telegram_group_chat_id: string;
  telegram_bot_token_set: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password_set: boolean;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  smtp_from_email: string;
};
type ApiSettingsForm = {
  telegram_group_chat_id: string;
  telegram_bot_token: string;
  smtp_host: string;
  smtp_port: string;
  smtp_username: string;
  smtp_password: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  smtp_from_email: string;
};

export function ApiClientsPanel({
  makerspace,
  isSuperadmin,
}: {
  makerspace: Makerspace;
  isSuperadmin: boolean;
}) {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState("");
  const [reason, setReason] = useState("");
  const [origins, setOrigins] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [settingsForm, setSettingsForm] = useState<ApiSettingsForm>({
    telegram_group_chat_id: "",
    telegram_bot_token: "",
    smtp_host: "",
    smtp_port: "587",
    smtp_username: "",
    smtp_password: "",
    smtp_use_tls: true,
    smtp_use_ssl: false,
    smtp_from_email: "",
  });
  const requests = useStaffGet<{ results: ApiKeyRequest[] }>(
    ["api-key-requests", makerspace.id],
    `/admin/api-key-requests?makerspace=${makerspace.id}`,
  );
  const settings = useStaffGet<ApiSettings>(
    ["api-settings", makerspace.id],
    `/admin/makerspace/${makerspace.id}/api-settings`,
    isSuperadmin,
  );
  useEffect(() => {
    if (!settings.data) return;
    setSettingsForm({
      telegram_group_chat_id: settings.data.telegram_group_chat_id ?? "",
      telegram_bot_token: "",
      smtp_host: settings.data.smtp_host ?? "",
      smtp_port: String(settings.data.smtp_port ?? 587),
      smtp_username: settings.data.smtp_username ?? "",
      smtp_password: "",
      smtp_use_tls: settings.data.smtp_use_tls,
      smtp_use_ssl: settings.data.smtp_use_ssl,
      smtp_from_email: settings.data.smtp_from_email ?? "",
    });
  }, [settings.data]);

  const requestKey = useMutation({
    mutationFn: () =>
      staffRequest<ApiKeyRequest>("/admin/api-key-requests", {
        method: "POST",
        body: JSON.stringify({
          makerspace: makerspace.id,
          label,
          reason,
          allowed_origins: splitOrigins(origins),
        }),
      }),
    onSuccess: () => {
      setLabel("");
      setReason("");
      setOrigins("");
      setSubmitted(true);
      queryClient.invalidateQueries({ queryKey: ["api-key-requests", makerspace.id] });
    },
  });
  const saveSettings = useMutation({
    mutationFn: () =>
      staffRequest<ApiSettings>(`/admin/makerspace/${makerspace.id}/api-settings`, {
        method: "PATCH",
        body: JSON.stringify(settingsPayload(settingsForm)),
      }),
    onSuccess: () => {
      setSettingsForm((current) => ({
        ...current,
        telegram_bot_token: "",
        smtp_password: "",
      }));
      queryClient.invalidateQueries({ queryKey: ["api-settings", makerspace.id] });
    },
  });
  const testTelegram = useMutation({
    mutationFn: () =>
      staffRequest<{ delivered: boolean }>("/integrations/telegram/test-alert", {
        method: "POST",
        body: JSON.stringify({
          makerspace_id: makerspace.id,
          message: `Test alert from ${makerspace.name}`,
        }),
      }),
  });

  return (
    <Panel title="API access">
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <article className="rounded-md border border-line bg-surface p-3">
            <h3 className="font-semibold text-ink">Request API access</h3>
            <div className="mt-3 grid gap-2">
              <input
                className="desk-input w-full"
                placeholder="Request label"
                value={label}
                onChange={(event) => {
                  setLabel(event.target.value);
                  setSubmitted(false);
                }}
              />
              <textarea
                className="desk-input min-h-24 w-full"
                placeholder="Reason for API access"
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value);
                  setSubmitted(false);
                }}
              />
              <textarea
                className="desk-input min-h-24 w-full"
                placeholder="Allowed browser origins, one per line. Example: https://lab.example.com"
                value={origins}
                onChange={(event) => {
                  setOrigins(event.target.value);
                  setSubmitted(false);
                }}
              />
            </div>
            <button
              className="desk-button-primary mt-3 w-full"
              disabled={!label.trim() || !reason.trim() || !splitOrigins(origins).length || requestKey.isPending}
              onClick={() => requestKey.mutate()}
            >
              {requestKey.isPending ? "Submitting..." : "Submit API access request"}
            </button>
            {submitted ? (
              <p className="mt-2 text-sm text-muted">
                Request submitted. A superadmin will review and share the key with you securely.
              </p>
            ) : null}
            {requestKey.error ? <p className="mt-2 text-sm text-danger">{requestKey.error.message}</p> : null}
          </article>

          {isSuperadmin ? (
            <div className="rounded-md border border-line bg-surface p-3">
              <h3 className="font-semibold text-ink">Integration settings</h3>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <input className="desk-input" placeholder="Telegram group chat ID" value={settingsForm.telegram_group_chat_id} onChange={(event) => setSettingsForm({ ...settingsForm, telegram_group_chat_id: event.target.value })} />
                <input className="desk-input" placeholder={settings.data?.telegram_bot_token_set ? "Telegram bot token set" : "Telegram bot token"} type="password" value={settingsForm.telegram_bot_token} onChange={(event) => setSettingsForm({ ...settingsForm, telegram_bot_token: event.target.value })} />
                <input className="desk-input" placeholder="SMTP host" value={settingsForm.smtp_host} onChange={(event) => setSettingsForm({ ...settingsForm, smtp_host: event.target.value })} />
                <input className="desk-input" inputMode="numeric" placeholder="SMTP port" value={settingsForm.smtp_port} onChange={(event) => setSettingsForm({ ...settingsForm, smtp_port: event.target.value })} />
                <input className="desk-input" placeholder="SMTP username" value={settingsForm.smtp_username} onChange={(event) => setSettingsForm({ ...settingsForm, smtp_username: event.target.value })} />
                <input className="desk-input" placeholder={settings.data?.smtp_password_set ? "SMTP password set" : "SMTP password"} type="password" value={settingsForm.smtp_password} onChange={(event) => setSettingsForm({ ...settingsForm, smtp_password: event.target.value })} />
                <input className="desk-input sm:col-span-2" placeholder="SMTP from email" value={settingsForm.smtp_from_email} onChange={(event) => setSettingsForm({ ...settingsForm, smtp_from_email: event.target.value })} />
              </div>
              <div className="mt-3 flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-sm text-muted">
                  <input type="checkbox" checked={settingsForm.smtp_use_tls} onChange={(event) => setSettingsForm({ ...settingsForm, smtp_use_tls: event.target.checked })} />
                  Use STARTTLS (587)
                </label>
                <label className="flex items-center gap-2 text-sm text-muted">
                  <input type="checkbox" checked={settingsForm.smtp_use_ssl} onChange={(event) => setSettingsForm({ ...settingsForm, smtp_use_ssl: event.target.checked })} />
                  Use implicit SSL (465)
                </label>
              </div>
              <button className="desk-button-primary mt-3 w-full" disabled={saveSettings.isPending} onClick={() => saveSettings.mutate()}>
                {saveSettings.isPending ? "Saving..." : "Save integration settings"}
              </button>
              <button className="desk-button mt-2 w-full" disabled={testTelegram.isPending} onClick={() => testTelegram.mutate()}>
                {testTelegram.isPending ? "Sending..." : "Send Telegram test alert"}
              </button>
              {saveSettings.error ? <p className="mt-2 text-sm text-danger">{saveSettings.error.message}</p> : null}
              {testTelegram.data ? (
                <p className="mt-2 text-sm text-muted">
                  Telegram delivered: {testTelegram.data.delivered ? "yes" : "no"}
                </p>
              ) : null}
              {testTelegram.error ? <p className="mt-2 text-sm text-danger">{testTelegram.error.message}</p> : null}
            </div>
          ) : null}
        </div>

        <div className="space-y-3">
          <article className="rounded-md border border-line bg-surface p-3">
            <h3 className="font-semibold text-ink">Makerspace API access</h3>
            <Config label="Makerspace code" value={settings.data?.public_code ?? makerspace.public_code} />
            <Config
              label="Allowed browser origins"
              value={
                isSuperadmin
                  ? (settings.data?.cors_allowed_origins ?? []).join(", ") || "No active client origins"
                  : "Managed by superadmin"
              }
            />
          </article>

          <article className="rounded-md border border-line bg-surface p-3">
            <h3 className="font-semibold text-ink">Your requests</h3>
            <div className="mt-3 space-y-2">
              {requests.data?.results?.map((request) => (
                <div key={request.id} className="rounded-md border border-line bg-bg p-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold text-ink">{request.label}</p>
                      <p className="mt-1 text-xs text-muted">{formatDate(request.created_at)}</p>
                    </div>
                    <span className="rounded-md border border-line bg-surface px-2 py-1 text-xs font-semibold uppercase text-muted">
                      {request.status}
                    </span>
                  </div>
                  {request.resolution_note ? (
                    <p className="mt-2 text-sm text-muted">{request.resolution_note}</p>
                  ) : null}
                </div>
              ))}
            </div>
          </article>
          {requests.data?.results?.length === 0 ? (
            <p className="rounded-md border border-line bg-surface p-3 text-sm text-muted">
              No API access requests yet.
            </p>
          ) : null}
        </div>
      </div>
    </Panel>
  );
}

function Config({ label, value }: { label: string; value: string }) {
  return (
    <div className="mt-3">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 break-all font-mono text-xs text-ink">{value}</p>
    </div>
  );
}

function splitOrigins(value: string) {
  return value
    .split(/\r?\n|,/)
    .map((origin) => origin.trim())
    .filter(Boolean);
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function settingsPayload(form: ApiSettingsForm) {
  const payload: Record<string, string | number | boolean> = {
    telegram_group_chat_id: form.telegram_group_chat_id,
    smtp_host: form.smtp_host,
    smtp_port: Number(form.smtp_port) || 587,
    smtp_username: form.smtp_username,
    smtp_use_tls: form.smtp_use_tls,
    smtp_use_ssl: form.smtp_use_ssl,
    smtp_from_email: form.smtp_from_email,
  };
  if (form.telegram_bot_token) payload.telegram_bot_token = form.telegram_bot_token;
  if (form.smtp_password) payload.smtp_password = form.smtp_password;
  return payload;
}
