import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PrinterServiceConsole } from "./PrinterServiceConsole";

const { staffRequest } = vi.hoisted(() => ({ staffRequest: vi.fn() }));

vi.mock("../../../../lib/api", () => ({ staffRequest }));

beforeEach(() => {
  staffRequest.mockReset();
  staffRequest.mockImplementation(async (path: string) => {
    if (path.endsWith("/machine-types")) {
      return [{ id: 1, slug: "3d_printer", name: "3D Printer", icon: "", is_builtin: true, managing_action: "", makerspace: null, capability_config: { metering_unit: "weight" } }];
    }
    if (path.endsWith("/machines")) return { count: 0, results: [] };
    if (path.includes("machine-service-report")) {
      return {
        printer_metrics: [{
          machine_id: 12,
          machine_name: "Demo Printer",
          model: "MK4",
          completed_hours: 2,
          failed_partial_hours: 0.25,
          manual_hours: 1,
          consumed_grams: "125.00",
          payment_due: "0.00",
          payment_paid: "0.00",
        }],
      };
    }
    return [];
  });
});

describe("PrinterServiceConsole", () => {
  it("renders the printer-specific report response without crashing the staff console", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PrinterServiceConsole makerspaceId={1} canManage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Demo Printer")).toBeVisible();
    expect(screen.getByText(/2h complete.*125.00g used/)).toBeVisible();
  });
});
