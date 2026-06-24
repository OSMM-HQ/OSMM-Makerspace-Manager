import type { Makerspace } from "./StaffPanels";

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

export function filterTabsByEnabledModules(tabs: readonly string[], makerspace?: Makerspace) {
  const modules = makerspace?.enabled_modules;
  if (!modules) return tabs;
  const enabled = new Set(modules);
  return tabs.filter((tabName) => {
    const required = TAB_MODULES[tabName];
    return !required || required.some((moduleName) => enabled.has(moduleName));
  });
}

