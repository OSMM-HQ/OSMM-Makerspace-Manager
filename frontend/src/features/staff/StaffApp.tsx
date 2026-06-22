import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  addAuthExpiredListener,
  clearAccessToken,
  fetchMe,
  logout as logoutStaff,
  refreshAccessToken,
  setAccessToken,
  staffRequest,
  type StaffAuthUser,
} from "../../lib/api";
import { OsmmBadge } from "../../components/OsmmLogo";
import { ThemeToggle } from "../../components/ThemeToggle";
import { ChangePasswordGate } from "./ChangePasswordGate";
import { LoginPanel } from "./LoginPanel";
import { MakerspacePicker } from "./MakerspacePicker";
import { StaffTabContent } from "./StaffTabContent";
import {
  type Makerspace,
  useStaffGet,
} from "./StaffPanels";
import { useTenant } from "../../lib/tenant";

const ALL_TABS = [
  "requests", "direct", "inventory", "needsfix", "categories", "printing", "tobuy", "transfers",
  "stocktake", "containers", "ledger", "reports", "bulk", "qr", "scanner", "api", "settings", "emailtemplates", "users", "platform", "audit",
  "email-logs",
] as const;
// Membership roles that get the full staff console. Anything else (print_manager,
// or an unknown role) is failed closed to the 3D-printing surfaces only.
const FULL_ACCESS_ROLES = ["space_manager", "inventory_manager", "guest_admin"];
// Print managers also get a To-Buy list (their items are auto-tagged "printing").
// "requests" is included so they reach the (printing-only) unified Requests tab.
const PRINTING_TABS = ["requests", "printing", "tobuy", "reports", "api", "emailtemplates"];

// Human labels for every tab key (single source — was an inline ternary in the nav).
const TAB_LABELS: Record<string, string> = {
  requests: "Requests",
  direct: "Direct handout",
  ledger: "Ledger",
  inventory: "Inventory",
  categories: "Categories",
  needsfix: "To-be-fixed",
  stocktake: "Stocktake",
  transfers: "Transfers",
  containers: "Containers",
  bulk: "Bulk import",
  qr: "QR Tools",
  scanner: "Scanner",
  printing: "3D Printing",
  tobuy: "To Buy",
  reports: "Reports",
  audit: "Audit log",
  users: "Users",
  settings: "Settings",
  emailtemplates: "Email templates",
  "email-logs": "Email log",
  api: "API access",
  platform: "Platform email",
};

// The flat 20-tab list, grouped into labelled sections (permissions unchanged —
// each section only renders the tabs the active role is allowed; empty sections
// are hidden). Reduces scan cost without changing what a role can reach.
const TAB_GROUPS: { label: string; tabs: string[] }[] = [
  { label: "Operate", tabs: ["requests", "direct", "ledger", "transfers", "stocktake", "tobuy"] },
  {
    label: "Inventory",
    tabs: ["inventory", "categories", "needsfix", "containers", "bulk", "qr", "scanner"],
  },
  { label: "3D Printing", tabs: ["printing"] },
  { label: "Insights", tabs: ["reports", "audit"] },
  // Rarely-used admin tabs collapsed behind one expander by default.
  { label: "Admin", tabs: ["users", "settings", "emailtemplates", "email-logs", "api", "platform"] },
];

export function StaffApp({ guestOnly = false }: { guestOnly?: boolean }) {
  const tenant = useTenant();
  const queryClient = useQueryClient();
  const [user, setUser] = useState<StaffAuthUser | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  // Empty until the user picks a tab, so the first render lands on the role-appropriate
  // default (computed below) instead of always "requests".
  const [tab, setTab] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    () => new Set(["Admin"]),
  );
  const [restoring, setRestoring] = useState(true);
  const hydrateUser = useCallback((nextUser: StaffAuthUser) => {
    setUser(nextUser);
    if (tenant.mode === "single" && tenant.makerspaceId !== null) {
      setSelected(tenant.makerspaceId);
      return;
    }
    // Superadmin operates one makerspace at a time and must pick it explicitly
    // first (the MakerspacePicker screen). Other staff drop into their first
    // membership directly.
    const superadmin = nextUser.is_superuser || nextUser.role === "superadmin";
    setSelected(superadmin ? null : nextUser.makerspaces[0]?.id ?? null);
  }, [tenant.makerspaceId, tenant.mode]);

  const expireSession = useCallback(() => {
    setUser(null);
    setSelected(null);
    setTab("");
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => addAuthExpiredListener(expireSession), [expireSession]);

  useEffect(() => {
    let active = true;

    async function restoreSession() {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        try {
          const currentUser = await fetchMe();
          if (active) {
            hydrateUser(currentUser);
          }
        } catch {
          clearAccessToken();
          if (active) {
            setUser(null);
          }
        }
      }
      if (active) {
        setRestoring(false);
      }
    }

    restoreSession();
    return () => {
      active = false;
    };
  }, [hydrateUser]);

  const login = useMutation({
    mutationFn: (payload: { username: string; password: string }) =>
      staffRequest<{ access: string; user: StaffAuthUser }>("/auth/login", {
        method: "POST",
        credentials: "include",
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => {
      setAccessToken(data.access);
      hydrateUser(data.user);
    },
  });

  const makerspaces = useStaffGet<Makerspace[]>(
    ["staff", "makerspaces"],
    "/admin/makerspaces",
    // Protected endpoints 403 while a forced password change is pending; keep this
    // query disabled until the gate is cleared so it doesn't cache an error.
    Boolean(user) && !user?.must_change_password,
  );
  const activeMakerspace = useMemo(
    () => {
      return makerspaces.data?.find((item) => item.id === selected);
    },
    [makerspaces.data, selected],
  );

  if (restoring) {
    return (
      <main className="desk-shell grid place-items-center px-5">
        <div className="desk-panel flex w-full max-w-md flex-col items-center gap-4 p-8 text-center text-sm font-semibold text-muted">
          <OsmmBadge />
          <span>Restoring session...</span>
        </div>
      </main>
    );
  }

  if (!user) {
    return (
      <LoginPanel
        error={login.error?.message}
        guestOnly={guestOnly}
        isPending={login.isPending}
        onSubmit={login.mutate}
      />
    );
  }

  // Force a password rotation before the console becomes usable. The backend
  // surfaces must_change_password (true for the default super123 seed); the
  // change-password endpoint clears it, after which we drop into the console.
  if (user.must_change_password) {
    return (
      <ChangePasswordGate
        username={user.username}
        onChanged={() => {
          // Clear the gate AND drop any error-cached protected queries so the
          // console opens with fresh data instead of a stale 403.
          queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
          setUser({ ...user, must_change_password: false });
        }}
        onSignOut={async () => {
          await logoutStaff();
          setUser(null);
          setSelected(null);
          queryClient.clear();
        }}
      />
    );
  }

  // Backend treats is_superuser OR role === "superadmin" as superadmin; mirror that.
  const isSuperadmin = user.is_superuser || user.role === "superadmin";
  const singleTenantLocked = tenant.mode === "single" && tenant.makerspaceId !== null;

  const signOut = async () => {
    await logoutStaff();
    setUser(null);
    setSelected(null);
    queryClient.clear();
  };

  if (singleTenantLocked && makerspaces.isLoading) {
    return (
      <main className="desk-shell grid place-items-center px-5">
        <div className="desk-panel w-full max-w-md p-6 text-sm font-semibold text-muted">
          <OsmmBadge className="mb-5" />
          Checking makerspace access...
        </div>
      </main>
    );
  }

  const hasSingleTenantAccess =
    !singleTenantLocked || Boolean(activeMakerspace);

  if (!hasSingleTenantAccess) {
    return (
      <main className="desk-shell grid place-items-center px-5">
        <section className="desk-panel w-full max-w-md bg-tone-yellow p-6 text-tone-yellow-ink dark:bg-[#332b00] dark:text-[#fcdf46]">
          <OsmmBadge className="mb-5" />
          <p className="text-xs font-semibold tracking-wide">
            Access denied
          </p>
          <h1 className="mt-2 text-xl font-bold">
            You do not have access to this makerspace.
          </h1>
          <p className="mt-2 text-sm leading-6">
            This branded admin dashboard is locked to{" "}
            {tenant.bootstrap?.makerspace.name ?? "this makerspace"}. Sign in with an
            account that has a membership for it.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <ThemeToggle />
            <button className="desk-button" type="button" onClick={signOut}>
              Sign out
            </button>
          </div>
        </section>
      </main>
    );
  }

  // Superadmin must choose which makerspace to operate before the console loads.
  // (Other roles auto-select their first membership at login.)
  if (!singleTenantLocked && isSuperadmin && selected === null) {
    return (
      <MakerspacePicker
        makerspaces={makerspaces.data ?? []}
        loading={makerspaces.isLoading}
        username={user.username}
        onSelect={setSelected}
        onSignOut={signOut}
      />
    );
  }

  // Authority is per active makerspace (a user can be print_manager in one and
  // space_manager in another), so recompute the nav from the selected membership.
  // Fail closed: only known full-access roles (or superadmin) see the full nav;
  // print managers + unknown roles get the 3D-printing surfaces only.
  const activeRole = user.makerspaces.find((item) => item.id === selected)?.role;
  const fullAccess = isSuperadmin || (!!activeRole && FULL_ACCESS_ROLES.includes(activeRole));
  const printingOnly = !fullAccess;
  // Request-stream visibility mirrors the backend RBAC matrix exactly:
  //   hardware (accept/reject/issue/return) -> space/inventory/guest admins + superadmin
  //   3D printing (MANAGE_PRINTING)         -> space + print managers + superadmin
  // Inventory Manager has no MANAGE_PRINTING, so it must NOT see the printing tab/section.
  const canSeeHardware = isSuperadmin || ["space_manager", "inventory_manager", "guest_admin"].includes(activeRole ?? "");
  const canSeePrinting = isSuperadmin || ["space_manager", "print_manager"].includes(activeRole ?? "");
  // To-Buy access mirrors the backend matrix: superadmin + space/inventory/print
  // managers. Guest admins (and unknown roles) have none, so hide the tab for them
  // rather than render an empty list whose actions 403.
  const canUseToBuy = isSuperadmin || ["space_manager", "inventory_manager", "print_manager"].includes(activeRole ?? "");
  // EDIT_INVENTORY roles only (guest admins can't repair/scrap stock).
  const canEditInventory = isSuperadmin || ["space_manager", "inventory_manager"].includes(activeRole ?? "");
  const canViewAudit = isSuperadmin || ["space_manager", "inventory_manager"].includes(activeRole ?? "");
  const canManageQr = isSuperadmin || ["space_manager", "inventory_manager"].includes(activeRole ?? "");
  // MANAGE_MAKERSPACE holders (Space Manager + superadmin) manage custom domains,
  // API clients, and makerspace settings.
  // Declared before allowedTabs because the filter callback below reads it immediately.
  const canManageMakerspace = isSuperadmin || activeRole === "space_manager";
  const allowedTabs: readonly string[] = (fullAccess ? ALL_TABS : PRINTING_TABS).filter((tabName) => {
    if (tabName === "tobuy") return canUseToBuy;
    if (tabName === "needsfix") return canEditInventory;
    if (tabName === "categories") return canEditInventory;
    if (tabName === "bulk") return canEditInventory;
    if (tabName === "stocktake") return canEditInventory;
    if (tabName === "direct") return canEditInventory;
    if (tabName === "transfers") return canEditInventory || isSuperadmin;
    if (tabName === "containers") return canManageQr;
    if (tabName === "qr") return canManageQr;
    if (tabName === "scanner") return canManageQr;
    if (tabName === "audit") return canViewAudit;
    if (tabName === "users") return canManageMakerspace;
    if (tabName === "settings") return canManageMakerspace;
    // Match the backend's edit-level gate: hardware templates need EDIT_INVENTORY/MANAGE_MAKERSPACE
    // (canEditInventory), printing needs MANAGE_PRINTING/MANAGE_MAKERSPACE (canSeePrinting). A guest
    // admin has neither, so the tab stays hidden instead of 404-ing on open.
    if (tabName === "emailtemplates") return canEditInventory || canSeePrinting;
    if (tabName === "email-logs") return canManageMakerspace;
    if (tabName === "platform") return isSuperadmin && !singleTenantLocked;
    if (tabName === "printing") return canSeePrinting; // hide printer/spool mgmt from inventory managers
    if (tabName === "requests") return canSeeHardware || canSeePrinting;
    return true;
  });
  // Only the makerspace admin (Space Manager) + superadmin may pick which stream
  // (hardware/printing) a To-Buy item goes to; other roles are auto-tagged.
  const canChooseToBuyKind = isSuperadmin || activeRole === "space_manager";
  const visibleMakerspaces =
    singleTenantLocked && activeMakerspace
      ? [activeMakerspace]
      : makerspaces.data ?? [];
  // Derived (no useEffect): switching makerspace recomputes synchronously, and a
  // tab that isn't allowed for the current role falls back to the role-appropriate
  // default landing tab (then the first allowed tab).
  const defaultTab = printingOnly ? "printing" : "requests";
  const activeTab = allowedTabs.includes(tab)
    ? tab
    : allowedTabs.includes(defaultTab)
      ? defaultTab
      : allowedTabs[0];
  const toggleGroup = (label: string) =>
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });

  return (
    <main className="desk-shell grid grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)]">
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
              {makerspaces.data?.map((makerspace) => (
                <option key={makerspace.id} value={makerspace.id}>
                  {makerspace.name}
                </option>
              ))}
            </select>
          )}
          <nav className="mt-4 space-y-3">
            {TAB_GROUPS.map((group) => {
              const tabs = group.tabs.filter((t) => allowedTabs.includes(t));
              if (tabs.length === 0) {
                return null;
              }
              // A group is open unless collapsed — but always open if it holds the
              // active tab, so the current section is never hidden.
              const open = !collapsedGroups.has(group.label) || tabs.includes(activeTab);
              return (
                <div key={group.label}>
                  <button
                    className="flex w-full items-center justify-between border-b border-line px-1 pb-1 font-display text-sm font-bold tracking-tight text-ink transition hover:text-accent-ink"
                    type="button"
                    onClick={() => toggleGroup(group.label)}
                  >
                    <span className="min-w-0 truncate">{group.label}</span>
                    <span aria-hidden>{open ? "−" : "+"}</span>
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

      <section className="min-w-0">
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
              {isSuperadmin && !singleTenantLocked ? (
                <button className="desk-button" onClick={() => setSelected(null)}>
                  Switch makerspace
                </button>
              ) : null}
              <ThemeToggle />
              <button className="desk-button" onClick={signOut}>
                Sign out
              </button>
            </div>
          </div>
        </header>

        <div className="min-w-0 p-5">
          <StaffTabContent
            activeMakerspace={activeMakerspace}
            activeTab={activeTab}
            guestOnly={guestOnly}
            makerspaces={visibleMakerspaces}
            isSuperadmin={isSuperadmin}
            printingOnly={printingOnly}
            canChooseToBuyKind={canChooseToBuyKind}
            canEditInventory={canEditInventory}
            canUseToBuy={canUseToBuy}
            canManageQr={canManageQr}
            canManageMakerspace={canManageMakerspace}
            canSeeHardware={canSeeHardware}
            canSeePrinting={canSeePrinting}
            canViewAudit={canViewAudit}
          />
        </div>
      </section>
    </main>
  );
}
