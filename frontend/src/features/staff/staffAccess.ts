const ALL_TABS = [
  "requests", "direct", "inventory", "needsfix", "categories", "printing", "tobuy", "transfers",
  "stocktake", "containers", "ledger", "reports", "warranty", "bulk", "qr", "scanner", "api", "settings", "emailtemplates", "users", "platform", "audit",
  "email-logs",
] as const;

const FULL_ACCESS_ROLES = ["space_manager", "inventory_manager"];
const PRINTING_TABS = ["requests", "printing", "tobuy", "reports", "warranty", "api", "emailtemplates"];
const GUEST_ADMIN_TABS = ["requests", "direct"];

export const TAB_LABELS: Record<string, string> = {
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
  { label: "Operate", tabs: ["requests", "direct", "ledger", "transfers", "stocktake", "tobuy"] },
  { label: "Inventory", tabs: ["inventory", "categories", "needsfix", "containers", "bulk", "qr", "scanner"] },
  { label: "3D Printing", tabs: ["printing"] },
  { label: "Insights", tabs: ["reports", "warranty", "audit"] },
  { label: "Admin", tabs: ["users", "settings", "emailtemplates", "email-logs", "api", "platform"] },
];

export function getStaffAccess(activeRole: string | undefined, isSuperadmin: boolean, singleTenantLocked: boolean) {
  const fullAccess = isSuperadmin || (!!activeRole && FULL_ACCESS_ROLES.includes(activeRole));
  const handoutOnly = activeRole === "guest_admin" && !isSuperadmin;
  const printingOnly = !fullAccess && !handoutOnly;
  const canSeeHardware = isSuperadmin || ["space_manager", "inventory_manager", "guest_admin"].includes(activeRole ?? "");
  const canSeePrinting = isSuperadmin || ["space_manager", "print_manager"].includes(activeRole ?? "");
  const canUseToBuy = isSuperadmin || ["space_manager", "inventory_manager", "print_manager"].includes(activeRole ?? "");
  const canEditInventory = isSuperadmin || ["space_manager", "inventory_manager"].includes(activeRole ?? "");
  const canIssueDirectLoan = isSuperadmin || ["space_manager", "inventory_manager", "guest_admin"].includes(activeRole ?? "");
  const canViewAudit = isSuperadmin || ["space_manager", "inventory_manager"].includes(activeRole ?? "");
  const canManageQr = isSuperadmin || ["space_manager", "inventory_manager"].includes(activeRole ?? "");
  const canManageMakerspace = isSuperadmin || activeRole === "space_manager";
  const canChooseToBuyKind = isSuperadmin || activeRole === "space_manager";
  const baseTabs = handoutOnly ? GUEST_ADMIN_TABS : fullAccess ? ALL_TABS : PRINTING_TABS;
  const allowedTabs: readonly string[] = baseTabs.filter((tabName) => {
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
    if (tabName === "reports") return canViewAudit || canSeePrinting;
    if (tabName === "warranty") return canEditInventory || canSeePrinting;
    if (tabName === "users") return canManageMakerspace;
    if (tabName === "settings") return canManageMakerspace;
    if (tabName === "emailtemplates") return canEditInventory || canSeePrinting;
    if (tabName === "email-logs") return canManageMakerspace;
    if (tabName === "platform") return isSuperadmin && !singleTenantLocked;
    if (tabName === "printing") return canSeePrinting;
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
    canChooseToBuyKind,
    allowedTabs,
    defaultTab: printingOnly ? "printing" : "requests",
  };
}
