import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { staffRequest } from "../../lib/api";
import { Panel, useStaffGet } from "./StaffPanels";

type PlatformEmailSettings = {
  id: number;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password_set: boolean;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  from_email: string;
  updated_at: string;
};

type PlatformEmailForm = {
  smtp_host: string;
  smtp_port: string;
  smtp_username: string;
  smtp_password: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  from_email: string;
};

export function PlatformEmailPanel() {
  const queryClient = useQueryClient();
  const settings = useStaffGet<PlatformEmailSettings>(
    ["platform-email"],
    "/admin/platform/email-settings",
  );
  const [form, setForm] = useState<PlatformEmailForm>({
    smtp_host: "",
    smtp_port: "587",
    smtp_username: "",
    smtp_password: "",
    smtp_use_tls: true,
    smtp_use_ssl: false,
    from_email: "",
  });

  useEffect(() => {
    if (!settings.data) return;
    setForm({
      smtp_host: settings.data.smtp_host ?? "",
      smtp_port: String(settings.data.smtp_port ?? 587),
      smtp_username: settings.data.smtp_username ?? "",
      smtp_password: "",
      smtp_use_tls: settings.data.smtp_use_tls,
      smtp_use_ssl: settings.data.smtp_use_ssl,
      from_email: settings.data.from_email ?? "",
    });
  }, [settings.data]);

  const save = useMutation({
    mutationFn: () =>
      staffRequest<PlatformEmailSettings>("/admin/platform/email-settings", {
        method: "PATCH",
        body: JSON.stringify(platformEmailPayload(form)),
      }),
    onSuccess: () => {
      setForm((current) => ({ ...current, smtp_password: "" }));
      queryClient.invalidateQueries({ queryKey: ["platform-email"] });
    },
  });

  const formDisabled = settings.isLoading || save.isPending;

  return (
    <Panel title="Platform email">
      <p className="text-sm text-muted">
        Instance-wide SMTP for password resets and makerspace notifications when a makerspace has no SMTP configured.
      </p>

      <div className="mt-4 rounded-md border border-line bg-surface p-3">
        <div className="grid gap-2 sm:grid-cols-2">
          <input
            className="desk-input"
            disabled={formDisabled}
            placeholder="SMTP host"
            value={form.smtp_host}
            onChange={(event) => setForm({ ...form, smtp_host: event.target.value })}
          />
          <input
            className="desk-input"
            disabled={formDisabled}
            inputMode="numeric"
            placeholder="SMTP port"
            value={form.smtp_port}
            onChange={(event) => setForm({ ...form, smtp_port: event.target.value })}
          />
          <input
            className="desk-input"
            disabled={formDisabled}
            placeholder="SMTP username"
            value={form.smtp_username}
            onChange={(event) => setForm({ ...form, smtp_username: event.target.value })}
          />
          <input
            className="desk-input"
            disabled={formDisabled}
            placeholder={settings.data?.smtp_password_set ? "SMTP password set" : "SMTP password"}
            type="password"
            value={form.smtp_password}
            onChange={(event) => setForm({ ...form, smtp_password: event.target.value })}
          />
          <input
            className="desk-input sm:col-span-2"
            disabled={formDisabled}
            placeholder="From email"
            value={form.from_email}
            onChange={(event) => setForm({ ...form, from_email: event.target.value })}
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              disabled={formDisabled}
              checked={form.smtp_use_tls}
              onChange={(event) => setForm({ ...form, smtp_use_tls: event.target.checked })}
            />
            Use STARTTLS (587)
          </label>
          <label className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              disabled={formDisabled}
              checked={form.smtp_use_ssl}
              onChange={(event) => setForm({ ...form, smtp_use_ssl: event.target.checked })}
            />
            Use implicit SSL (465)
          </label>
        </div>
        <button
          className="desk-button-primary mt-3 w-full"
          disabled={formDisabled}
          onClick={() => save.mutate()}
        >
          {settings.isLoading ? "Loading..." : save.isPending ? "Saving..." : "Save platform email settings"}
        </button>
        {save.error ? <p className="mt-2 text-sm text-danger">{save.error.message}</p> : null}
        {settings.error ? <p className="mt-2 text-sm text-danger">{settings.error.message}</p> : null}
      </div>
    </Panel>
  );
}

function platformEmailPayload(form: PlatformEmailForm) {
  const payload: Record<string, string | number | boolean> = {
    smtp_host: form.smtp_host,
    smtp_port: Number(form.smtp_port) || 587,
    smtp_username: form.smtp_username,
    smtp_use_tls: form.smtp_use_tls,
    smtp_use_ssl: form.smtp_use_ssl,
    from_email: form.from_email,
  };
  if (form.smtp_password) payload.smtp_password = form.smtp_password;
  return payload;
}


