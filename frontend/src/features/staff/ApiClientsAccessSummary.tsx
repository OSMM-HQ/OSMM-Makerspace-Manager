import { type Makerspace } from "./StaffPanels";

type ApiSettingsSummary = {
  public_code: string;
  cors_allowed_origins: string[];
};

export function ApiClientsAccessSummary({
  makerspace,
  isSuperadmin,
  settings,
}: {
  makerspace: Makerspace;
  isSuperadmin: boolean;
  settings?: ApiSettingsSummary;
}) {
  return (
    <article className="rounded-md border border-line bg-surface p-3">
      <h3 className="font-semibold text-ink">Makerspace API access</h3>
      <Config label="Makerspace code" value={settings?.public_code ?? makerspace.public_code} />
      <Config
        label="Allowed browser origins"
        value={
          isSuperadmin
            ? (settings?.cors_allowed_origins ?? []).join(", ") || "No active client origins"
            : "Managed by superadmin"
        }
      />
    </article>
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
