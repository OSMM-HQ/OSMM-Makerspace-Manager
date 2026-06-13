import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { staffRequest } from "../../lib/api";
import { Panel, type Makerspace, useStaffGet } from "./StaffPanels";

type ApiClient = {
  id: number;
  label: string;
  client_id: string;
  client_secret?: string;
  public_makerspace_code: string;
  allowed_origins: string[];
  backend_base_url: string;
  public_api_base_url: string;
  is_active: boolean;
};
type ApiSettings = {
  public_code: string;
  public_api_key: string;
  cors_allowed_origins: string[];
  telegram_group_chat_id: string;
  telegram_bot_token_set: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password_set: boolean;
  smtp_use_tls: boolean;
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
  smtp_from_email: string;
};

export function ApiClientsPanel({ makerspace }: { makerspace: Makerspace }) {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState("");
  const [origins, setOrigins] = useState("");
  const [issuedSecret, setIssuedSecret] = useState("");
  const [settingsForm, setSettingsForm] = useState<ApiSettingsForm>({
    telegram_group_chat_id: "",
    telegram_bot_token: "",
    smtp_host: "",
    smtp_port: "587",
    smtp_username: "",
    smtp_password: "",
    smtp_use_tls: true,
    smtp_from_email: "",
  });
  const clients = useStaffGet<{ results: ApiClient[] }>(
    ["api-clients", makerspace.id],
    `/admin/makerspace/${makerspace.id}/api-clients`,
  );
  const settings = useStaffGet<ApiSettings>(
    ["api-settings", makerspace.id],
    `/admin/makerspace/${makerspace.id}/api-settings`,
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
      smtp_from_email: settings.data.smtp_from_email ?? "",
    });
  }, [settings.data]);
  const create = useMutation({
    mutationFn: () =>
      staffRequest<ApiClient>(`/admin/makerspace/${makerspace.id}/api-clients`, {
        method: "POST",
        body: JSON.stringify({
          label,
          allowed_origins: splitOrigins(origins),
          is_active: true,
        }),
      }),
    onSuccess: (client) => {
      setIssuedSecret(client.client_secret ?? "");
      setLabel("");
      queryClient.invalidateQueries({ queryKey: ["api-clients", makerspace.id] });
    },
  });
  const toggle = useMutation({
    mutationFn: (client: ApiClient) =>
      staffRequest<ApiClient>(`/admin/api-clients/${client.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !client.is_active }),
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["api-clients", makerspace.id] }),
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
    <Panel title="API clients">
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <div className="rounded-md border border-line bg-surface p-3">
            <h3 className="font-semibold text-ink">Integration settings</h3>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <input
                className="desk-input"
                placeholder="Telegram group chat ID"
                value={settingsForm.telegram_group_chat_id}
                onChange={(event) =>
                  setSettingsForm({ ...settingsForm, telegram_group_chat_id: event.target.value })
                }
              />
              <input
                className="desk-input"
                placeholder={
                  settings.data?.telegram_bot_token_set
                    ? "Telegram bot token set"
                    : "Telegram bot token"
                }
                type="password"
                value={settingsForm.telegram_bot_token}
                onChange={(event) =>
                  setSettingsForm({ ...settingsForm, telegram_bot_token: event.target.value })
                }
              />
              <input
                className="desk-input"
                placeholder="SMTP host"
                value={settingsForm.smtp_host}
                onChange={(event) =>
                  setSettingsForm({ ...settingsForm, smtp_host: event.target.value })
                }
              />
              <input
                className="desk-input"
                inputMode="numeric"
                placeholder="SMTP port"
                value={settingsForm.smtp_port}
                onChange={(event) =>
                  setSettingsForm({ ...settingsForm, smtp_port: event.target.value })
                }
              />
              <input
                className="desk-input"
                placeholder="SMTP username"
                value={settingsForm.smtp_username}
                onChange={(event) =>
                  setSettingsForm({ ...settingsForm, smtp_username: event.target.value })
                }
              />
              <input
                className="desk-input"
                placeholder={settings.data?.smtp_password_set ? "SMTP password set" : "SMTP password"}
                type="password"
                value={settingsForm.smtp_password}
                onChange={(event) =>
                  setSettingsForm({ ...settingsForm, smtp_password: event.target.value })
                }
              />
              <input
                className="desk-input sm:col-span-2"
                placeholder="SMTP from email"
                value={settingsForm.smtp_from_email}
                onChange={(event) =>
                  setSettingsForm({ ...settingsForm, smtp_from_email: event.target.value })
                }
              />
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm text-muted">
              <input
                type="checkbox"
                checked={settingsForm.smtp_use_tls}
                onChange={(event) =>
                  setSettingsForm({ ...settingsForm, smtp_use_tls: event.target.checked })
                }
              />
              Use SMTP TLS
            </label>
            <button
              className="desk-button-primary mt-3 w-full"
              disabled={saveSettings.isPending}
              onClick={() => saveSettings.mutate()}
            >
              {saveSettings.isPending ? "Saving..." : "Save integration settings"}
            </button>
            <button
              className="desk-button mt-2 w-full"
              disabled={testTelegram.isPending}
              onClick={() => testTelegram.mutate()}
            >
              {testTelegram.isPending ? "Sending..." : "Send Telegram test alert"}
            </button>
            {saveSettings.error ? (
              <p className="mt-2 text-sm text-danger">{saveSettings.error.message}</p>
            ) : null}
            {testTelegram.data ? (
              <p className="mt-2 text-sm text-muted">
                Telegram delivered: {testTelegram.data.delivered ? "yes" : "no"}
              </p>
            ) : null}
            {testTelegram.error ? (
              <p className="mt-2 text-sm text-danger">{testTelegram.error.message}</p>
            ) : null}
          </div>

          <input
            className="desk-input w-full"
            placeholder="Client label"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
          />
          <textarea
            className="desk-input min-h-24 w-full"
            placeholder="Frontend origins, one per line. Example: https://lab.example.com"
            value={origins}
            onChange={(event) => setOrigins(event.target.value)}
          />
          <button
            className="desk-button-primary w-full"
            disabled={!label.trim() || !splitOrigins(origins).length || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Creating..." : "Create API client"}
          </button>
          {create.error ? <p className="text-sm text-danger">{create.error.message}</p> : null}
          {issuedSecret ? (
            <div className="rounded-md border border-warn/40 bg-warn/10 p-3">
              <p className="text-sm font-semibold text-warn">Server secret shown once</p>
              <p className="mt-2 break-all font-mono text-xs text-ink">{issuedSecret}</p>
            </div>
          ) : null}
        </div>

        <div className="space-y-3">
          <article className="rounded-md border border-line bg-surface p-3">
            <h3 className="font-semibold text-ink">Makerspace API keys</h3>
            <Config label="Makerspace code" value={settings.data?.public_code ?? makerspace.public_code} />
            <Config label="Legacy public API key" value={settings.data?.public_api_key ?? ""} />
            <Config
              label="Allowed browser origins"
              value={(settings.data?.cors_allowed_origins ?? []).join(", ") || "No active client origins"}
            />
          </article>
          {clients.data?.results?.map((client) => (
            <article key={client.id} className="rounded-md border border-line bg-surface p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold text-ink">{client.label}</h3>
                  <p className="mt-1 break-all font-mono text-xs text-muted">{client.client_id}</p>
                </div>
                <button className="desk-button" onClick={() => toggle.mutate(client)}>
                  {client.is_active ? "Disable" : "Enable"}
                </button>
              </div>
              <Config label="Makerspace code" value={client.public_makerspace_code} />
              <Config label="Public API" value={client.public_api_base_url} />
              <Config label="Frontend env" value={`VITE_PUBLIC_CLIENT_ID=${client.client_id}`} />
              <Config label="Origins" value={client.allowed_origins.join(", ")} />
            </article>
          ))}
          {clients.data?.results?.length === 0 ? (
            <p className="rounded-md border border-line bg-surface p-3 text-sm text-muted">
              No API clients yet.
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

function settingsPayload(form: ApiSettingsForm) {
  const payload: Record<string, string | number | boolean> = {
    telegram_group_chat_id: form.telegram_group_chat_id,
    smtp_host: form.smtp_host,
    smtp_port: Number(form.smtp_port) || 587,
    smtp_username: form.smtp_username,
    smtp_use_tls: form.smtp_use_tls,
    smtp_from_email: form.smtp_from_email,
  };
  if (form.telegram_bot_token) payload.telegram_bot_token = form.telegram_bot_token;
  if (form.smtp_password) payload.smtp_password = form.smtp_password;
  return payload;
}
