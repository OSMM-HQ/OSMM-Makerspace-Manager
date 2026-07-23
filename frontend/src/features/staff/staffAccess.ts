const ALL_TABS = [
  "dashboard", "notifications", "requests", "direct", "inventory", "needsfix", "categories", "machines", "events", "bookings", "members", "tobuy", "transfers",
  "stocktake", "containers", "ledger", "reports", "accountability", "warranty", "bulk", "qr", "scanner", "api", "settings", "emailtemplates", "users", "platform", "audit",
  "email-logs", "payments",
] as const;

export const STAFF_TAB_KEYS: readonly string[] = ALL_TABS;

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
  machines: "Machines",
  events: "Events",
  bookings: "Bookings",
  members: "Members",
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
  platform: "Platform settings",
  payments: "Payments",
};

export const TAB_GROUPS: { label: string; tabs: string[] }[] = [
  { label: "Operate", tabs: ["dashboard", "notifications", "requests", "direct", "payments", "ledger", "transfers", "stocktake", "tobuy"] },
  { label: "Inventory", tabs: ["inventory", "categories", "needsfix", "containers", "bulk", "qr", "scanner"] },
  { label: "Machines", tabs: ["machines"] },
  { label: "Events", tabs: ["events"] },
  { label: "Bookings", tabs: ["bookings"] },
  { label: "Members", tabs: ["members"] },
  { label: "Insights", tabs: ["reports", "accountability", "warranty", "audit"] },
  { label: "Admin", tabs: ["users", "settings", "emailtemplates", "email-logs", "api", "platform"] },
];

export function getStaffAccess(actions: readonly string[], isSuperadmin: boolean, singleTenantLocked: boolean, enabledModules: readonly string[] = []) {
  const has = (action: string) => isSuperadmin || actions.includes(action);
  const canEditInventory = has("edit_inventory");
  const canViewInventory = has("view_inventory");
  const canSeePrinting = has("manage_printing") || has("manage_machines");
  const canManageMachines = has("manage_machines");
  const canManageEvents = has("manage_events");
  const canManageBookings = has("manage_bookings");
  const canViewAudit = has("view_audit");
  const canManageQr = has("manage_qr");
  const canManageMakerspace = has("manage_makerspace");
  const canIssueDirectLoan = has("issue_direct_loan");
  const canSeeHardware = isSuperadmin || ["accept_request", "reject_request", "assign_box", "issue_request", "issue_direct_loan", "return_request"].some((action) => actions.includes(action));
  const canUseToBuy = has("edit_inventory") || has("manage_printing") || has("manage_machines") || has("manage_makerspace");
  const canChooseToBuyKind = has("manage_makerspace");
  const canSeeDashboard = has("view_inventory") || has("manage_printing") || has("manage_machines") || has("manage_makerspace");
  const HANDOUT = ["view_inventory", "assign_box", "issue_request", "issue_direct_loan", "return_request", "upload_evidence"];
  const HANDOUT_MUTATIONS = ["assign_box", "issue_request", "issue_direct_loan", "return_request", "upload_evidence"];
  const handoutOnly = !isSuperadmin && actions.length > 0 && actions.every((action) => HANDOUT.includes(action)) && actions.some((action) => HANDOUT_MUTATIONS.includes(action));
  const printingOnly = canSeePrinting && !canEditInventory && !canManageMakerspace;
  const baseTabs = handoutOnly ? (["requests", "direct"] as const) : ALL_TABS;
  const allowedTabs: readonly string[] = baseTabs.filter((tabName) => {
    if (tabName === "dashboard") return !handoutOnly && (isSuperadmin || canSeeDashboard);
    if (tabName === "notifications") return !handoutOnly && enabledModules.includes("notifications");
    if (tabName === "tobuy") return canUseToBuy;
    if (tabName === "needsfix") return canEditInventory;
    if (tabName === "categories") return canEditInventory;
    if (tabName === "bulk") return canEditInventory;
    if (tabName === "stocktake") return canEditInventory;
    if (tabName === "direct") return canIssueDirectLoan;
    if (tabName === "inventory") return canViewInventory;
    if (tabName === "ledger") return canViewInventory;
    if (tabName === "transfers") return canEditInventory || isSuperadmin;
    if (tabName === "containers") return canManageQr;
    if (tabName === "qr") return canManageQr;
    if (tabName === "scanner") return canManageQr;
    if (tabName === "audit") return canViewAudit;
    if (tabName === "accountability") return canViewAudit;
    if (tabName === "reports") return canViewAudit || canSeePrinting || canManageMachines;
    if (tabName === "warranty") return canEditInventory || canSeePrinting;
    if (tabName === "users") return canManageMakerspace;
    if (tabName === "settings") return canManageMakerspace;
    if (tabName === "emailtemplates") return canEditInventory || canSeePrinting;
    if (tabName === "email-logs") return canManageMakerspace;
    if (tabName === "platform") return isSuperadmin && !singleTenantLocked;
    if (tabName === "machines") return enabledModules.includes("machines") && canManageMachines;
    if (tabName === "events") return enabledModules.includes("events") && canManageEvents;
    if (tabName === "bookings") return enabledModules.includes("bookings") && canManageBookings;
    if (tabName === "members") return canManageMakerspace;
    if (tabName === "payments") return canManageMakerspace;
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
    canViewInventory,
    canIssueDirectLoan,
    canViewAudit,
    canManageQr,
    canManageMakerspace,
    canManageMachines,
    canManageEvents,
    canManageBookings,
    canChooseToBuyKind,
    allowedTabs,
    defaultTab: handoutOnly ? "requests" : (allowedTabs.includes("dashboard") ? "dashboard" : (allowedTabs[0] ?? "dashboard")),
  };
}
