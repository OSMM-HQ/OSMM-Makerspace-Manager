import { Link } from "react-router-dom";

import { ThemeToggle } from "../../components/ThemeToggle";
import type { StaffAuthUser } from "../../lib/api";
import type { Makerspace } from "./StaffPanels";

export function StaffHeader({
  activeMakerspace,
  isSuperadmin,
  onSignOut,
  onSwitchMakerspace,
  singleTenantLocked,
  user,
}: {
  activeMakerspace?: Makerspace;
  isSuperadmin: boolean;
  onSignOut: () => void;
  onSwitchMakerspace: () => void;
  singleTenantLocked: boolean;
  user: StaffAuthUser;
}) {
  const publicInventoryPath = activeMakerspace
    ? singleTenantLocked ? "/" : "/m/" + activeMakerspace.slug
    : null;

  return (
    <header className="border-b border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-mono text-xs font-semibold uppercase tracking-tight text-accent-ink">
            {activeMakerspace?.public_code ?? activeMakerspace?.slug ?? "No workspace"}
          </p>
          <h1 className="break-words font-display text-2xl font-bold uppercase tracking-tight text-ink">
            {activeMakerspace?.name ?? "Inventory Control"}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="max-w-full truncate rounded-lg border border-line bg-panel px-3 py-2 font-mono text-xs uppercase text-muted sm:max-w-56">
            {user.username}
          </span>
          {publicInventoryPath ? (
            <Link className="desk-button" to={publicInventoryPath}>
              Public inventory
            </Link>
          ) : null}
          {isSuperadmin && !singleTenantLocked ? (
            <button className="desk-button" type="button" onClick={onSwitchMakerspace}>
              Switch makerspace
            </button>
          ) : null}
          <ThemeToggle />
          <button className="desk-button" type="button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}