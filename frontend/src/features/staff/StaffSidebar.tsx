import { OsmmBadge } from "../../components/OsmmLogo";
import type { Makerspace } from "./StaffPanels";
import { TAB_GROUPS, TAB_LABELS } from "./staffAccess";

export function StaffSidebar({
  activeMakerspace,
  activeTab,
  allowedTabs,
  collapsedGroups,
  guestOnly,
  isSuperadmin,
  makerspaces,
  printingOnly,
  selected,
  setSelected,
  setTab,
  singleTenantLocked,
  toggleGroup,
}: {
  activeMakerspace?: Makerspace;
  activeTab: string;
  allowedTabs: readonly string[];
  collapsedGroups: Set<string>;
  guestOnly: boolean;
  isSuperadmin: boolean;
  makerspaces: Makerspace[];
  printingOnly: boolean;
  selected: number | null;
  setSelected: (id: number) => void;
  setTab: (tab: string) => void;
  singleTenantLocked: boolean;
  toggleGroup: (label: string) => void;
}) {
  return (
    <aside className="min-w-0 border-b border-line bg-panel lg:min-h-screen lg:border-b-0 lg:border-r">
      <div className="flex min-w-0 items-center gap-3 border-b border-line px-5 py-4">
        <OsmmBadge className="shrink-0" />
        <div className="min-w-0">
          <p className="truncate font-mono text-xs uppercase text-muted">
            {guestOnly ? "Guest admin" : isSuperadmin ? "Super Admin" : printingOnly ? "Print Manager" : "Space Manager"}
          </p>
        </div>
      </div>
      <div className="p-4">
        {singleTenantLocked ? (
          <div className="break-words rounded-lg border border-line bg-tone-blue px-3 py-2 text-sm font-semibold text-tone-blue-ink dark:bg-[#0b2a38] dark:text-[#7dd3fc]">
            {activeMakerspace?.name ?? "Configured makerspace"}
          </div>
        ) : (
          <select
            className="desk-input w-full"
            value={selected ?? ""}
            onChange={(event) => setSelected(Number(event.target.value))}
          >
            {makerspaces.map((makerspace) => (
              <option key={makerspace.id} value={makerspace.id}>
                {makerspace.name}
              </option>
            ))}
          </select>
        )}
        <nav className="mt-4 space-y-3">
          {TAB_GROUPS.map((group) => {
            const tabs = group.tabs.filter((tab) => allowedTabs.includes(tab));
            if (tabs.length === 0) return null;
            const open = !collapsedGroups.has(group.label) || tabs.includes(activeTab);
            return (
              <div key={group.label}>
                <button
                  className="flex w-full items-center justify-between border-b border-line px-1 pb-1 font-display text-sm font-bold tracking-tight text-ink transition hover:text-accent-ink"
                  type="button"
                  onClick={() => toggleGroup(group.label)}
                >
                  <span className="min-w-0 truncate">{group.label}</span>
                  <span aria-hidden>{open ? "-" : "+"}</span>
                </button>
                {open ? (
                  <div className="mt-1 grid gap-1">
                    {tabs.map((item) => (
                      <button
                        key={item}
                        className={`desk-nav-item ${activeTab === item ? "desk-nav-item-active" : ""}`}
                        onClick={() => setTab(item)}
                      >
                        <span className="min-w-0 truncate">{TAB_LABELS[item] ?? item}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}

