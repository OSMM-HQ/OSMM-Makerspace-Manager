const ALL_TABS = [
  "dashboard", "notifications", "requests", "direct", "inventory", "needsfix", "categories", "printing", "machines", "events", "bookings", "tobuy", "transfers",
  "stocktake", "containers", "ledger", "reports", "accountability", "warranty", "bulk", "qr", "scanner", "api", "settings", "emailtemplates", "users", "platform", "audit",
  "email-logs",
] as const;

export const STAFF_TAB_KEYS: readonly string[] = ALL_TABS;

const FULL_ACCESS_ROLES = ["space_manager", "inventory_manager"];
const PRINTING_TABS = ["dashboard", "notifications", "requests", "printing", "machines", "tobuy", "reports", "warranty", "api", "emailtemplates"];
const GUEST_ADMIN_TABS = ["requests", "direct"];
// Machine Manager: makerspace-wide machine authority (machines + maintenance/warranty/usage
// live inside the Machines drawer). Deliberately narrow — no Dashboard (DashboardView requires
// VIEW_INVENTORY/MANAGE_PRINTING/MANAGE_MAKERSPACE, none of which this role holds).
const MACHINE_MANAGER_TABS = ["machines"];

export const TAB_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  notifications: "Notifications",
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
  machines: "Machines",
  events: "Events",
  bookings: "Bookings",
  tobuy: "To Buy",
  reports: "Reports",
  accountability: "Accountability",
  warranty: "Warranties",
  audit: "Audit log",
  users: "Users",
  settings: "Settings",
  emailtemplates: "Email templates",
  "email-logs": "Email log",
  api: "API access",
  platform: "Platform email",
};

export const TAB_GROUPS: { label: string; tabs: string[] }[] = [
  { label: "Operate", tabs: ["dashboard", "notifications", "requests", "direct", "ledger", "transfers", "stocktake", "tobuy"] },
  { label: "Inventory", tabs: ["inventory", "categories", "needsfix", "containers", "bulk", "qr", "scanner"] },
  { label: "3D Printing", tabs: ["printing"] },
  { label: "Machines", tabs: ["machines"] },
  { label: "Events", tabs: ["events"] },
  { label: "Bookings", tabs: ["bookings"] },
  { label: "Insights", tabs: ["reports", "accountability", "warranty", "audit"] },
  { label: "Admin", tabs: ["users", "settings", "emailtemplates", "email-logs", "api", "platform"] },
];

export function getStaffAccess(activeRole: string | undefined, isSuperadmin: boolean, singleTenantLocked: boolean, enabledModules: readonly string[] = []) {
  const fullAccess = isSuperadmin || (!!activeRole && FULL_ACCESS_ROLES.includes(activeRole));
  const handoutOnly = activeRole === "guest_admin" && !isSuperadmin;
  const machineOnly = activeRole === "machine_manager" && !isSuperadmin;
  const printingOnly = !fullAccess && !handoutOnly && !machineOnly;
  const canSeeHardware = isSuperadmin || ["space_manager", "inventory_manager", "guest_admin"].includes(activeRole ?? "");
  const canSeePrinting = isSuperadmin || ["space_manager", "print_manager"].includes(activeRole ?? "");
  const canUseToBuy = isSuperadmin || ["space_manager", "inventory_manager", "print_manager"].includes(activeRole ?? "");
  const canEditInventory = isSuperadmin || ["space_manager", "inventory_manager"].includes(activeRole ?? "");
  const canIssueDirectLoan = isSuperadmin || ["space_manager", "inventory_manager", "guest_admin"].includes(activeRole ?? "");
  const canViewAudit = isSuperadmin || ["space_manager", "inventory_manager"].includes(activeRole ?? "");
  const canManageQr = isSuperadmin || ["space_manager", "inventory_manager"].includes(activeRole ?? "");
  const canManageMakerspace = isSuperadmin || activeRole === "space_manager";
  const canManageMachines = isSuperadmin || ["space_manager", "machine_manager"].includes(activeRole ?? "");
  const canManageEvents = isSuperadmin || activeRole === "space_manager";
  const canManageBookings = isSuperadmin || activeRole === "space_manager";
  const canChooseToBuyKind = isSuperadmin || activeRole === "space_manager";
  const baseTabs = handoutOnly
    ? GUEST_ADMIN_TABS
    : machineOnly
      ? MACHINE_MANAGER_TABS
      : fullAccess
        ? ALL_TABS
        : PRINTING_TABS;
  const allowedTabs: readonly string[] = baseTabs.filter((tabName) => {
    if (tabName === "dashboard") return !handoutOnly;
    if (tabName === "notifications") return !handoutOnly && enabledModules.includes("notifications");
    if (tabName === "tobuy") return canUseToBuy;
    if (tabName === "needsfix") return canEditInventory;
    if (tabName === "categories") return canEditInventory;
    if (tabName === "bulk") return canEditInventory;
    if (tabName === "stocktake") return canEditInventory;
    if (tabName === "direct") return canIssueDirectLoan;
    if (tabName === "inventory") return !handoutOnly;
    if (tabName === "ledger") return !handoutOnly;
    if (tabName === "transfers") return canEditInventory || isSuperadmin;
    if (tabName === "containers") return canManageQr;
    if (tabName === "qr") return canManageQr;
    if (tabName === "scanner") return canManageQr;
    if (tabName === "audit") return canViewAudit;
    if (tabName === "accountability") return canViewAudit;
    if (tabName === "reports") return canViewAudit || canSeePrinting;
    if (tabName === "warranty") return canEditInventory || canSeePrinting;
    if (tabName === "users") return canManageMakerspace;
    if (tabName === "settings") return canManageMakerspace;
    if (tabName === "emailtemplates") return canEditInventory || canSeePrinting;
    if (tabName === "email-logs") return canManageMakerspace;
    if (tabName === "platform") return isSuperadmin && !singleTenantLocked;
    if (tabName === "printing") return canSeePrinting;
    if (tabName === "machines") return enabledModules.includes("machines") && (canManageMachines || canSeePrinting);
    if (tabName === "events") return enabledModules.includes("events") && canManageEvents;
    if (tabName === "bookings") return enabledModules.includes("bookings") && canManageBookings;
    if (tabName === "requests") return canSeeHardware || canSeePrinting;
    return true;
  });
  return {
    handoutOnly,
    printingOnly,
    canSeeHardware,
    canSeePrinting,
    canUseToBuy,
    canEditInventory,
    canIssueDirectLoan,
    canViewAudit,
    canManageQr,
    canManageMakerspace,
    canManageMachines,
    canManageEvents,
    canManageBookings,
    canChooseToBuyKind,
    allowedTabs,
    defaultTab: handoutOnly ? "requests" : machineOnly ? "machines" : "dashboard",
  };
}
