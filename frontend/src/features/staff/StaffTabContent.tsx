import { ApiClientsPanel } from "./ApiClientsPanel";
import { DirectLoans } from "./DirectLoans";
import { MakerspaceSettingsPanel } from "./MakerspaceSettingsPanel";
import { PlatformEmailPanel } from "./PlatformEmailPanel";
import {
  AuditLog,
  BulkImport,
  Categories,
  ContainersPanel,
  Inventory,
  Ledger,
  NeedsFixShelf,
  OperationsReports,
  Panel,
  PrintingPanel,
  ProcurementPanel,
  QrTools,
  RequestsPanel,
  ScannerPanel,
  StocktakePanel,
  StockTransferPanel,
  TenantFrontendsPanel,
  Users,
  type Makerspace,
} from "./StaffPanels";

export function StaffTabContent({
  activeMakerspace,
  activeTab,
  guestOnly,
  makerspaces,
  isSuperadmin,
  printingOnly,
  canChooseToBuyKind,
  canEditInventory,
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
  canManageMakerspace: boolean;
  canSeeHardware: boolean;
  canSeePrinting: boolean;
  canViewAudit: boolean;
}) {
  if (!activeMakerspace) {
    return <Panel title="No makerspace">Assign a makerspace to this account.</Panel>;
  }
  return (
    <>
      {activeTab === "requests" ? (
        <RequestsPanel
          makerspace={activeMakerspace}
          guestOnly={guestOnly}
          canSeeHardware={canSeeHardware}
          canSeePrinting={canSeePrinting}
        />
      ) : null}
      {activeTab === "inventory" ? (
        <Inventory makerspace={activeMakerspace} canViewAudit={canViewAudit} />
      ) : null}
      {activeTab === "needsfix" ? <NeedsFixShelf makerspace={activeMakerspace} /> : null}
      {activeTab === "categories" ? <Categories makerspace={activeMakerspace} /> : null}
      {activeTab === "printing" ? <PrintingPanel makerspace={activeMakerspace} /> : null}
      {activeTab === "tobuy" ? (
        <ProcurementPanel makerspace={activeMakerspace} canChooseKind={canChooseToBuyKind} />
      ) : null}
      {activeTab === "transfers" ? (
        <StockTransferPanel
          makerspace={activeMakerspace}
          makerspaces={makerspaces}
          isSuperadmin={isSuperadmin}
          canEditInventory={canEditInventory}
        />
      ) : null}
      {activeTab === "stocktake" ? <StocktakePanel makerspace={activeMakerspace} /> : null}
      {activeTab === "containers" ? <ContainersPanel makerspace={activeMakerspace} /> : null}
      {activeTab === "ledger" ? (
        <Ledger makerspace={activeMakerspace} isSuperadmin={isSuperadmin} />
      ) : null}
      {activeTab === "reports" ? (
        <OperationsReports
          makerspace={activeMakerspace}
          isSuperadmin={isSuperadmin}
          printingOnly={printingOnly}
        />
      ) : null}
      {activeTab === "direct" ? <DirectLoans makerspace={activeMakerspace} /> : null}
      {activeTab === "bulk" ? <BulkImport makerspace={activeMakerspace} /> : null}
      {activeTab === "qr" ? <QrTools makerspace={activeMakerspace} /> : null}
      {activeTab === "scanner" ? (
        <ScannerPanel
          makerspace={activeMakerspace}
          isSuperadmin={isSuperadmin}
          makerspaces={makerspaces}
        />
      ) : null}
      {activeTab === "frontends" ? <TenantFrontendsPanel makerspace={activeMakerspace} /> : null}
      {activeTab === "api" ? (
        <ApiClientsPanel
          makerspace={activeMakerspace}
          isSuperadmin={isSuperadmin}
          canManageMakerspace={canManageMakerspace}
        />
      ) : null}
      {activeTab === "settings" ? (
        <MakerspaceSettingsPanel makerspace={activeMakerspace} isSuperadmin={isSuperadmin} />
      ) : null}
      {activeTab === "platform" ? <PlatformEmailPanel /> : null}
      {activeTab === "users" ? (
        <Users makerspaces={makerspaces} isSuperadmin={isSuperadmin} />
      ) : null}
      {activeTab === "audit" ? <AuditLog /> : null}
    </>
  );
}
