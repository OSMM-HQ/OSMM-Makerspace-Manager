import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PaymentReconcileActions } from "./PaymentReconcileActions";

const { staffRequest } = vi.hoisted(() => ({ staffRequest: vi.fn() }));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return { ...actual, staffRequest };
});

function renderActions(status: "pending" | "paid_online" = "pending") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  render(
    <QueryClientProvider client={queryClient}>
      <PaymentReconcileActions
        makerspaceId={7}
        payment={{ id: 41, status, amount: "12.50", currency: "usd" }}
        invalidateKeys={[["events", 7]]}
      />
    </QueryClientProvider>,
  );
  return invalidate;
}

beforeEach(() => {
  staffRequest.mockReset();
  staffRequest.mockResolvedValue({ id: 41, status: "waived" });
});

describe("PaymentReconcileActions", () => {
  it("reconciles a pending payment and invalidates shared and domain views", async () => {
    const invalidate = renderActions();

    fireEvent.click(screen.getByRole("button", { name: "Waive" }));

    await waitFor(() => expect(staffRequest).toHaveBeenCalledWith(
      "/admin/makerspace/7/payments/41/waive",
      { method: "POST" },
    ));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["payments", 7] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["events", 7] });
  });

  it("shows terminal payment status without mutation controls", () => {
    renderActions("paid_online");

    expect(screen.getByText(/Payment/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Waive" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark offline" })).not.toBeInTheDocument();
  });
});
