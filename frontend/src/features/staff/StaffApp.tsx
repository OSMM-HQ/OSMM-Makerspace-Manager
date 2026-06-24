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
import { filterTabsByEnabledModules } from "./staffTabs";
import { type Makerspace, useStaffGet } from "./StaffPanels";
import { useTenant } from "../../lib/tenant";
import { readStorage, removeStorage, writeStorage } from "../../lib/safeStorage";

export function StaffApp({ guestOnly = false }: { guestOnly?: boolean }) {
  const tenant = useTenant();
  const queryClient = useQueryClient();
  const [user, setUser] = useState<StaffAuthUser | null>(null);
  const [selected, setSelectedState] = useState<number | null>(() => readNumber(STAFF_SELECTED_MAKERSPACE_KEY));
  const [tab, setTabState] = useState(() => readStorage(STAFF_ACTIVE_TAB_KEY));
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    () => new Set(["Admin"]),
  );
  const [restoring, setRestoring] = useState(true);
  const setSelected = useCallback((value: number | null) => {
    setSelectedState(value);
    if (value === null) removeStorage(STAFF_SELECTED_MAKERSPACE_KEY);
    else writeStorage(STAFF_SELECTED_MAKERSPACE_KEY, String(value));
  }, []);
  const setTab = useCallback((value: string) => {
    setTabState(value);
    if (value) writeStorage(STAFF_ACTIVE_TAB_KEY, value);
    else removeStorage(STAFF_ACTIVE_TAB_KEY);
  }, []);
  const hydrateUser = useCallback((nextUser: StaffAuthUser) => {
    setUser(nextUser);
    if (tenant.mode === "single" && tenant.makerspaceId !== null) {
      setSelected(tenant.makerspaceId);
      return;
    }
    const superadmin = nextUser.is_superuser || nextUser.role === "superadmin";
    const saved = readNumber(STAFF_SELECTED_MAKERSPACE_KEY);
    const staffSaved = nextUser.makerspaces.some((item) => item.id === saved) ? saved : null;
    setSelected(superadmin ? saved : staffSaved ?? nextUser.makerspaces[0]?.id ?? null);
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

  if (!singleTenantLocked && selected !== null && makerspaces.isLoading) {
    return (
      <main className="desk-shell grid place-items-center px-5">
        <div className="desk-panel w-full max-w-md p-6 text-sm font-semibold text-muted">
          <OsmmBadge className="mb-5" />
          Restoring makerspace...
        </div>
      </main>
    );
  }

  if (!singleTenantLocked && isSuperadmin && selected !== null && !activeMakerspace) {
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

const STAFF_SELECTED_MAKERSPACE_KEY = "osmm.staff.selectedMakerspace";
const STAFF_ACTIVE_TAB_KEY = "osmm.staff.activeTab";

function readNumber(key: string) {
  const value = Number(readStorage(key));
  return Number.isFinite(value) && value > 0 ? value : null;
}

