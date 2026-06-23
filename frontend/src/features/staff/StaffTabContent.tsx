import { lazy, Suspense } from "react";

import { DirectLoans } from "./DirectLoans";
import { Skeleton } from "../../components/ui";
import { Inventory } from "./panels/Inventory";
import { Ledger } from "./panels/Ledger";
import { PrintingPanel } from "./panels/PrintingPanel";
import { QrTools } from "./panels/QrTools";
import { RequestsPanel } from "./panels/RequestsPanel";
import { Panel, type Makerspace } from "./panels/shared";
import { Users } from "./panels/Users";

const OperationsReports = lazy(() => import("./panels/OperationsReports").then((m) => ({ default: m.OperationsReports })));
const AuditLog = lazy(() => import("./panels/AuditLog").then((m) => ({ default: m.AuditLog })));
const BulkImport = lazy(() => import("./panels/BulkImport").then((m) => ({ default: m.BulkImport })));
const ScannerPanel = lazy(() => import("./panels/ScannerPanel").then((m) => ({ default: m.ScannerPanel })));
const EmailTemplatesPanel = lazy(() => import("./panels/EmailTemplatesPanel").then((m) => ({ default: m.EmailTemplatesPanel })));
const ContainersPanel = lazy(() => import("./panels/ContainersPanel").then((m) => ({ default: m.ContainersPanel })));
const StocktakePanel = lazy(() => import("./panels/StocktakePanel").then((m) => ({ default: m.StocktakePanel })));
const StockTransferPanel = lazy(() => import("./panels/StockTransferPanel").then((m) => ({ default: m.StockTransferPanel })));
const ProcurementPanel = lazy(() => import("./panels/ProcurementPanel").then((m) => ({ default: m.ProcurementPanel })));
const EmailLogPanel = lazy(() => import("./panels/EmailLogPanel").then((m) => ({ default: m.EmailLogPanel })));
const Categories = lazy(() => import("./panels/Categories").then((m) => ({ default: m.Categories })));
const NeedsFixShelf = lazy(() => import("./panels/NeedsFixShelf").then((m) => ({ default: m.NeedsFixShelf })));
const ApiClientsPanel = lazy(() => import("./ApiClientsPanel").then((m) => ({ default: m.ApiClientsPanel })));
const PlatformEmailPanel = lazy(() => import("./PlatformEmailPanel").then((m) => ({ default: m.PlatformEmailPanel })));
const MakerspaceSettingsPanel = lazy(() => import("./MakerspaceSettingsPanel").then((m) => ({ default: m.MakerspaceSettingsPanel })));

export function StaffTabContent({
  activeMakerspace,
  activeTab,
  guestOnly,
  makerspaces,
  isSuperadmin,
  printingOnly,
  canChooseToBuyKind,
  canEditInventory,
  canUseToBuy,
  canManageQr,
  canManageMakerspace,
  canSeeHardware,
  canSeePrinting,
  canViewAudit,
}: {
  activeMakerspace?: Makerspace;
  activeTab: string;
  guestOnly: boolean;
  makerspaces: Makerspace[];
  isSuperadmin: boolean;
  printingOnly: boolean;
  canChooseToBuyKind: boolean;
  canEditInventory: boolean;
  canUseToBuy: boolean;
  canManageQr: boolean;
  canManageMakerspace: boolean;
  canSeeHardware: boolean;
  canSeePrinting: boolean;
  canViewAudit: boolean;
}) {
  if (!activeMakerspace) {
    return <Panel title="No makerspace">Assign a makerspace to this account.</Panel>;
  }
  const makerspaceKey = activeMakerspace.id;
  return (
    <Suspense fallback={<div className="p-4"><Skeleton className="h-40 w-full" /></div>}>
      {activeTab === "requests" ? (
        <RequestsPanel
          key={makerspaceKey}
          makerspace={activeMakerspace}
          guestOnly={guestOnly}
          canSeeHardware={canSeeHardware}
          canSeePrinting={canSeePrinting}
        />
      ) : null}
      {activeTab === "inventory" ? (
        <Inventory
          key={makerspaceKey}
          makerspace={activeMakerspace}
          canViewAudit={canViewAudit}
          canUseToBuy={canUseToBuy}
        />
      ) : null}
      {activeTab === "needsfix" && canEditInventory ? <NeedsFixShelf key={makerspaceKey} makerspace={activeMakerspace} /> : null}
      {activeTab === "categories" && canEditInventory ? <Categories key={makerspaceKey} makerspace={activeMakerspace} /> : null}
      {activeTab === "printing" ? <PrintingPanel key={makerspaceKey} makerspace={activeMakerspace} /> : null}
      {activeTab === "tobuy" ? (
        <ProcurementPanel
          key={makerspaceKey}
          makerspace={activeMakerspace}
          canChooseKind={canChooseToBuyKind}
        />
      ) : null}
      {activeTab === "transfers" && (canEditInventory || isSuperadmin) ? (
        <StockTransferPanel
          key={makerspaceKey}
          makerspace={activeMakerspace}
          makerspaces={makerspaces}
          isSuperadmin={isSuperadmin}
          canEditInventory={canEditInventory}
        />
      ) : null}
      {activeTab === "stocktake" && canEditInventory ? <StocktakePanel key={makerspaceKey} makerspace={activeMakerspace} isSuperadmin={isSuperadmin} /> : null}
      {activeTab === "containers" && canManageQr ? <ContainersPanel key={makerspaceKey} makerspace={activeMakerspace} /> : null}
      {activeTab === "ledger" ? (
        <Ledger
          key={makerspaceKey}
          makerspace={activeMakerspace}
          isSuperadmin={isSuperadmin}
        />
      ) : null}
      {activeTab === "reports" ? (
        <OperationsReports
          key={makerspaceKey}
          makerspace={activeMakerspace}
          makerspaces={makerspaces}
          isSuperadmin={isSuperadmin}
          printingOnly={printingOnly}
          canViewAudit={canViewAudit}
          canSeePrinting={canSeePrinting}
        />
      ) : null}
      {activeTab === "direct" && canEditInventory ? <DirectLoans key={makerspaceKey} makerspace={activeMakerspace} /> : null}
      {activeTab === "bulk" && canEditInventory ? <BulkImport key={makerspaceKey} makerspace={activeMakerspace} /> : null}
      {activeTab === "qr" && canManageQr ? <QrTools key={makerspaceKey} makerspace={activeMakerspace} /> : null}
      {activeTab === "scanner" && canManageQr ? (
        <ScannerPanel
          key={makerspaceKey}
          makerspace={activeMakerspace}
          isSuperadmin={isSuperadmin}
          makerspaces={makerspaces}
        />
      ) : null}
      {activeTab === "api" ? (
        <ApiClientsPanel
          key={makerspaceKey}
          makerspace={activeMakerspace}
          isSuperadmin={isSuperadmin}
          canManageMakerspace={canManageMakerspace}
        />
      ) : null}
      {activeTab === "settings" ? (
        <MakerspaceSettingsPanel
          key={makerspaceKey}
          makerspace={activeMakerspace}
          isSuperadmin={isSuperadmin}
        />
      ) : null}
      {activeTab === "emailtemplates" ? (
        <EmailTemplatesPanel key={makerspaceKey} makerspace={activeMakerspace} />
      ) : null}
      {activeTab === "email-logs" && canManageMakerspace ? (
        <EmailLogPanel key={makerspaceKey} makerspace={activeMakerspace} />
      ) : null}
      {activeTab === "platform" ? <PlatformEmailPanel /> : null}
      {activeTab === "users" && canManageMakerspace ? (
        <Users makerspaces={makerspaces} isSuperadmin={isSuperadmin} />
      ) : null}
      {activeTab === "audit" && canViewAudit ? <AuditLog /> : null}
    </Suspense>
  );
}

