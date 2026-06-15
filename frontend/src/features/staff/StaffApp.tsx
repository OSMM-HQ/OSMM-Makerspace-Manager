import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  clearAccessToken,
  fetchMe,
  logout as logoutStaff,
  refreshAccessToken,
  setAccessToken,
  staffRequest,
  type StaffAuthUser,
} from "../../lib/api";
import { ThemeToggle } from "../../components/ThemeToggle";
import { ApiClientsPanel } from "./ApiClientsPanel";
import { DirectLoans } from "./DirectLoans";
import { ChangePasswordGate } from "./ChangePasswordGate";
import { LoginPanel } from "./LoginPanel";
import { MakerspacePicker } from "./MakerspacePicker";
import {
  AuditLog,
  BulkImport,
  Categories,
  Inventory,
  Ledger,
  OperationsReports,
  Panel,
  PrintingPanel,
  ProcurementPanel,
  QrTools,
  RequestsPanel,
  StocktakePanel,
  StockTransferPanel,
  Users,
  type Makerspace,
  useStaffGet,
} from "./StaffPanels";

const ALL_TABS = [
  "requests", "direct", "inventory", "categories", "printing", "tobuy", "transfers",
  "stocktake", "ledger", "reports", "bulk", "qr", "api", "users", "audit",
] as const;
// Membership roles that get the full staff console. Anything else (print_manager,
// or an unknown role) is failed closed to the 3D-printing surfaces only.
const FULL_ACCESS_ROLES = ["space_manager", "inventory_manager", "guest_admin"];
// Print managers also get a To-Buy list (their items are auto-tagged "printing").
// "requests" is included so they reach the (printing-only) unified Requests tab.
const PRINTING_TABS = ["requests", "printing", "tobuy", "reports", "api"];

export function StaffApp({ guestOnly = false }: { guestOnly?: boolean }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<StaffAuthUser | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [tab, setTab] = useState("requests");
  const [restoring, setRestoring] = useState(true);
  const hydrateUser = useCallback((nextUser: StaffAuthUser) => {
    setUser(nextUser);
    // Superadmin operates one makerspace at a time and must pick it explicitly
    // first (the MakerspacePicker screen). Other staff drop into their first
    // membership directly.
    const superadmin = nextUser.is_superuser || nextUser.role === "superadmin";
    setSelected(superadmin ? null : nextUser.makerspaces[0]?.id ?? null);
  }, []);

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
    () => makerspaces.data?.find((item) => item.id === selected),
    [makerspaces.data, selected],
  );

  if (restoring) {
    return (
      <main className="desk-shell grid place-items-center px-5">
        <div className="desk-panel w-full max-w-md p-6 text-sm font-semibold text-muted">
          Restoring session...
        </div>
      </main>
    );
  }

  if (!user) {
    return (
      <LoginPanel
        error={login.error?.message}
        guestOnly={guestOnly}
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

  const signOut = async () => {
    await logoutStaff();
    setUser(null);
    setSelected(null);
    queryClient.clear();
  };

  // Superadmin must choose which makerspace to operate before the console loads.
  // (Other roles auto-select their first membership at login.)
  if (isSuperadmin && selected === null) {
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
  const allowedTabs: readonly string[] = (fullAccess ? ALL_TABS : PRINTING_TABS).filter((tabName) => {
    if (tabName === "tobuy") return canUseToBuy;
    if (tabName === "printing") return canSeePrinting; // hide printer/spool mgmt from inventory managers
    if (tabName === "requests") return canSeeHardware || canSeePrinting;
    return true;
  });
  // Only the makerspace admin (Space Manager) + superadmin may pick which stream
  // (hardware/printing) a To-Buy item goes to; other roles are auto-tagged.
  const canChooseToBuyKind = isSuperadmin || activeRole === "space_manager";
  // Derived (no useEffect): switching makerspace recomputes synchronously, and a
  // tab that isn't allowed for the current role falls back to the first allowed.
  const activeTab = allowedTabs.includes(tab) ? tab : allowedTabs[0];

  return (
    <main className="desk-shell grid lg:grid-cols-[260px_1fr]">
      <aside className="border-b border-line bg-panel lg:min-h-screen lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <span className="grid h-9 w-9 place-items-center rounded-md bg-accent text-sm font-black text-bg">
            MM
          </span>
          <div>
            <p className="text-sm font-semibold text-ink">Makerspace Manager</p>
            <p className="text-xs text-muted">{guestOnly ? "Guest admin" : isSuperadmin ? "Super Admin" : printingOnly ? "Print Manager" : "Space Manager"}</p>
          </div>
        </div>
        <div className="p-4">
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
          <nav className="mt-4 grid gap-1">
            {allowedTabs.map((item) => (
              <button
                key={item}
                className={`rounded-md px-3 py-2 text-left text-sm font-medium transition ${
                  activeTab === item
                    ? "bg-accent text-bg"
                    : "text-muted hover:bg-surface hover:text-ink"
                }`}
                onClick={() => setTab(item)}
              >
                  {item === "qr" ? "QR Tools" : item === "direct" ? "Direct handout" : item === "api" ? "API access" : item === "stocktake" ? "Stocktake" : item === "printing" ? "3D Printing" : item === "tobuy" ? "To Buy" : item[0].toUpperCase() + item.slice(1)}
              </button>
            ))}
          </nav>
        </div>
      </aside>

      <section className="min-w-0">
        <header className="border-b border-line bg-bg/95 px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-accent">
                {activeMakerspace?.public_code ?? activeMakerspace?.slug ?? "No workspace"}
              </p>
              <h1 className="text-2xl font-bold text-ink">
                {activeMakerspace?.name ?? "Inventory Control"}
              </h1>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-muted">
                {user.username}
              </span>
              {isSuperadmin ? (
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
          {!activeMakerspace ? <Panel title="No makerspace">Assign a makerspace to this account.</Panel> : null}
          {activeMakerspace && activeTab === "requests" ? (
            <RequestsPanel
              makerspace={activeMakerspace}
              guestOnly={guestOnly}
              canSeeHardware={canSeeHardware}
              canSeePrinting={canSeePrinting}
            />
          ) : null}
          {activeMakerspace && activeTab === "inventory" ? (
            <Inventory makerspace={activeMakerspace} />
          ) : null}
          {activeMakerspace && activeTab === "categories" ? (
            <Categories makerspace={activeMakerspace} />
          ) : null}
          {activeMakerspace && activeTab === "printing" ? (
            <PrintingPanel makerspace={activeMakerspace} />
          ) : null}
          {activeMakerspace && activeTab === "tobuy" ? (
            <ProcurementPanel makerspace={activeMakerspace} canChooseKind={canChooseToBuyKind} />
          ) : null}
          {activeMakerspace && activeTab === "transfers" ? (
            <StockTransferPanel
              makerspace={activeMakerspace}
              makerspaces={makerspaces.data ?? []}
              isSuperadmin={isSuperadmin}
            />
          ) : null}
          {activeMakerspace && activeTab === "stocktake" ? (
            <StocktakePanel makerspace={activeMakerspace} />
          ) : null}
          {activeMakerspace && activeTab === "ledger" ? (
            <Ledger makerspace={activeMakerspace} isSuperadmin={isSuperadmin} />
          ) : null}
          {activeMakerspace && activeTab === "reports" ? (
            <OperationsReports makerspace={activeMakerspace} isSuperadmin={isSuperadmin} printingOnly={printingOnly} />
          ) : null}
          {activeMakerspace && activeTab === "direct" ? (
            <DirectLoans makerspace={activeMakerspace} />
          ) : null}
          {activeMakerspace && activeTab === "bulk" ? <BulkImport makerspace={activeMakerspace} /> : null}
          {activeMakerspace && activeTab === "qr" ? <QrTools makerspace={activeMakerspace} /> : null}
          {activeMakerspace && activeTab === "api" ? (
            <ApiClientsPanel makerspace={activeMakerspace} isSuperadmin={isSuperadmin} />
          ) : null}
          {activeMakerspace && activeTab === "users" ? (
            <Users makerspaces={makerspaces.data ?? []} isSuperadmin={isSuperadmin} />
          ) : null}
          {activeMakerspace && activeTab === "audit" ? <AuditLog /> : null}
        </div>
      </section>
    </main>
  );
}
