import type { Makerspace } from "./panels/shared";
import { readStorage, removeStorage, writeStorage } from "../../lib/safeStorage";

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

const TAB_PATHS: Record<string, string> = {
  direct: "direct-handout",
  needsfix: "to-be-fixed",
  tobuy: "to-buy",
  bulk: "bulk-import",
  qr: "qr-tools",
  api: "api-access",
  emailtemplates: "email-templates",
  "email-logs": "email-log",
};

const PATH_TABS = Object.fromEntries(
  Object.entries(TAB_PATHS).map(([tab, path]) => [path, tab]),
);

export const STAFF_SELECTED_MAKERSPACE_KEY = "osmm.staff.selectedMakerspace";
export const STAFF_ACTIVE_TAB_KEY = "osmm.staff.activeTab";

export function filterTabsByEnabledModules(tabs: readonly string[], makerspace?: Makerspace) {
  const modules = makerspace?.enabled_modules;
  if (!modules) return tabs;
  const enabled = new Set(modules);
  return tabs.filter((tabName) => {
    const required = TAB_MODULES[tabName];
    return !required || required.some((moduleName) => enabled.has(moduleName));
  });
}

export function readStoredMakerspace() {
  const value = Number(readStorage(STAFF_SELECTED_MAKERSPACE_KEY));
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function readStoredStaffTab() {
  return pathToTab(readStorage(STAFF_ACTIVE_TAB_KEY));
}

export function persistSelectedMakerspace(value: number | null) {
  if (value === null) removeStorage(STAFF_SELECTED_MAKERSPACE_KEY);
  else writeStorage(STAFF_SELECTED_MAKERSPACE_KEY, String(value));
}

export function persistStaffTab(tab: string) {
  if (tab) writeStorage(STAFF_ACTIVE_TAB_KEY, tab);
  else removeStorage(STAFF_ACTIVE_TAB_KEY);
}

export function staffBasePath(guestOnly: boolean) {
  return guestOnly ? "/guest-admin" : "/admin";
}

export function staffTabPath(
  tab: string,
  guestOnly: boolean,
  makerspaceSlug?: string | null,
  singleTenantLocked = false,
) {
  const pagePath = tabToPath(tab);
  if (makerspaceSlug && !singleTenantLocked) {
    return `/m/${makerspaceSlug}/admin/${pagePath}`;
  }
  return `${staffBasePath(guestOnly)}/${pagePath}`;
}

export function staffPathState(pathname: string, guestOnly: boolean) {
  const scoped = /^\/m\/([^/]+)\/admin(?:\/([^/]+))?/.exec(pathname);
  if (scoped) {
    return { makerspaceSlug: scoped[1], tab: pathToTab(scoped[2] ?? "") };
  }

  const basePath = staffBasePath(guestOnly);
  if (!pathname.startsWith(basePath)) {
    return { makerspaceSlug: "", tab: "" };
  }
  const relative = pathname.slice(basePath.length).replace(/^\/+/, "");
  return { makerspaceSlug: "", tab: pathToTab(relative.split("/")[0] ?? "") };
}

export function staffMakerspaceSlugFromPath(pathname: string, guestOnly: boolean) {
  return staffPathState(pathname, guestOnly).makerspaceSlug;
}

export function tabFromStaffPath(pathname: string, guestOnly: boolean) {
  return staffPathState(pathname, guestOnly).tab;
}

export function tabToPath(tab: string) {
  return TAB_PATHS[tab] ?? tab;
}

function pathToTab(path: string | null) {
  if (!path) {
    return "";
  }
  return PATH_TABS[path] ?? path;
}
