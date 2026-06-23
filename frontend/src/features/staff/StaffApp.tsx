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
import { ChangePasswordGate } from "./ChangePasswordGate";
import { LoginPanel } from "./LoginPanel";
import { MakerspacePicker } from "./MakerspacePicker";
import { StaffAccessDenied } from "./StaffAccessDenied";
import { StaffHeader } from "./StaffHeader";
import { StaffSidebar } from "./StaffSidebar";
import { StaffTabContent } from "./StaffTabContent";
import { getStaffAccess } from "./staffAccess";
import { type Makerspace, useStaffGet } from "./StaffPanels";
import { useTenant } from "../../lib/tenant";

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
      <StaffAccessDenied
        makerspaceName={tenant.bootstrap?.makerspace.name}
        onSignOut={signOut}
      />
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
  const {
    allowedTabs,
    canChooseToBuyKind,
    canEditInventory,
    canManageMakerspace,
    canManageQr,
    canSeeHardware,
    canSeePrinting,
    canUseToBuy,
    canViewAudit,
    defaultTab,
    printingOnly,
  } = getStaffAccess(activeRole, isSuperadmin, singleTenantLocked);
  const visibleMakerspaces =
    singleTenantLocked && activeMakerspace
      ? [activeMakerspace]
      : makerspaces.data ?? [];
  const moduleAllowedTabs = filterTabsByEnabledModules(allowedTabs, activeMakerspace);
  // Derived (no useEffect): switching makerspace recomputes synchronously, and a
  // tab that is not allowed for the current role falls back to the role-appropriate
  // default landing tab (then the first allowed tab).
  const activeTab = moduleAllowedTabs.includes(tab)
    ? tab
    : moduleAllowedTabs.includes(defaultTab)
      ? defaultTab
      : moduleAllowedTabs[0];
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
      <StaffSidebar
        activeMakerspace={activeMakerspace}
        activeTab={activeTab}
        allowedTabs={moduleAllowedTabs}
        collapsedGroups={collapsedGroups}
        guestOnly={guestOnly}
        isSuperadmin={isSuperadmin}
        makerspaces={makerspaces.data ?? []}
        printingOnly={printingOnly}
        selected={selected}
        setSelected={setSelected}
        setTab={setTab}
        singleTenantLocked={singleTenantLocked}
        toggleGroup={toggleGroup}
      />

      <section className="min-w-0">
        <StaffHeader
          activeMakerspace={activeMakerspace}
          isSuperadmin={isSuperadmin}
          onSignOut={signOut}
          onSwitchMakerspace={() => setSelected(null)}
          singleTenantLocked={singleTenantLocked}
          user={user}
        />

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

const TAB_MODULES: Record<string, string[]> = {
  direct: ["self_checkout"],
  printing: ["printing"],
  tobuy: ["procurement"],
  transfers: ["stock_transfers"],
  stocktake: ["stocktake"],
  containers: ["containers"],
  bulk: ["bulk_import"],
  qr: ["qr_management"],
  scanner: ["scanner"],
  reports: ["reports", "printing"],
};

function filterTabsByEnabledModules(tabs: readonly string[], makerspace?: Makerspace) {
  const modules = makerspace?.enabled_modules;
  if (!modules) return tabs;
  const enabled = new Set(modules);
  return tabs.filter((tabName) => {
    const required = TAB_MODULES[tabName];
    return !required || required.some((moduleName) => enabled.has(moduleName));
  });
}


