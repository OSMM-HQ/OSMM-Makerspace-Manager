import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PlatformStripeConnectPanel } from "./PlatformStripeConnectPanel";

const { query, staffRequest } = vi.hoisted(() => ({
  query: vi.fn(),
  staffRequest: vi.fn(),
}));

vi.mock("../../lib/api", () => ({ staffRequest }));
vi.mock("./StaffPanels", async () => {
  const actual = await vi.importActual<typeof import("./StaffPanels")>("./StaffPanels");
  return { ...actual, useStaffGet: query };
});

describe("PlatformStripeConnectPanel", () => {
  beforeEach(() => {
    query.mockReset();
    staffRequest.mockReset();
  });

  it("submits a new publishable key without rendering a stored value", async () => {
    query.mockReturnValue({
      data: {
        id: 1,
        stripe_publishable_key: "pk_stored_never_returned",
        stripe_publishable_key_set: true,
        stripe_secret_key_set: true,
        stripe_webhook_secret_set: true,
        stripe_connect_client_id: "ca_platform",
        application_fee_bps: 125,
        updated_at: "2026-07-22T00:00:00Z",
      },
      isLoading: false,
      error: null,
    });
    staffRequest.mockResolvedValue({});
    render(
      <QueryClientProvider client={new QueryClient()}>
        <PlatformStripeConnectPanel />
      </QueryClientProvider>,
    );

    const input = screen.getByPlaceholderText("Platform publishable key set");
    expect(input).toHaveValue("");
    expect(screen.queryByDisplayValue("pk_stored_never_returned")).toBeNull();
    fireEvent.change(input, { target: { value: "pk_live_new" } });
    fireEvent.click(screen.getByRole("button", { name: /save stripe connect settings/i }));

    await waitFor(() => expect(staffRequest).toHaveBeenCalled());
    const lastCall = staffRequest.mock.calls[staffRequest.mock.calls.length - 1];
    const body = JSON.parse(lastCall[1]?.body as string);
    expect(body.stripe_publishable_key).toBe("pk_live_new");

    const clearButton = screen.getByRole("button", { name: /clear publishable key/i });
    await waitFor(() => expect(clearButton).not.toBeDisabled());
    fireEvent.click(clearButton);
    await waitFor(() => expect(staffRequest).toHaveBeenCalledTimes(2));
    const clearCall = staffRequest.mock.calls[1];
    const clearBody = JSON.parse(clearCall[1]?.body as string);
    expect(clearBody.stripe_publishable_key).toBe("");
  });

  it("revokes secret credentials explicitly without rendering returned secret-shaped fields", async () => {
    query.mockReturnValue({
      data: {
        id: 1,
        stripe_publishable_key_set: true,
        stripe_secret_key: "sk_stored_never_rendered",
        stripe_secret_key_set: true,
        stripe_webhook_secret: "whsec_stored_never_rendered",
        stripe_webhook_secret_set: true,
        stripe_connect_client_id: "ca_platform",
        application_fee_bps: 125,
        updated_at: "2026-07-22T00:00:00Z",
      },
      isLoading: false,
      error: null,
    });
    staffRequest.mockResolvedValue({});
    render(
      <QueryClientProvider client={new QueryClient()}>
        <PlatformStripeConnectPanel />
      </QueryClientProvider>,
    );

    expect(screen.queryByDisplayValue("sk_stored_never_rendered")).toBeNull();
    expect(screen.queryByDisplayValue("whsec_stored_never_rendered")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /clear secret key/i }));
    await waitFor(() => expect(staffRequest).toHaveBeenCalledTimes(1));
    expect(JSON.parse(staffRequest.mock.calls[0][1]?.body as string)).toEqual({
      stripe_secret_key: "",
    });

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /clear webhook secret/i })).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /clear webhook secret/i }));
    await waitFor(() => expect(staffRequest).toHaveBeenCalledTimes(2));
    expect(JSON.parse(staffRequest.mock.calls[1][1]?.body as string)).toEqual({
      stripe_webhook_secret: "",
    });
  });

  it("surfaces the pending-session safeguard when webhook revocation is rejected", async () => {
    query.mockReturnValue({
      data: {
        id: 1,
        stripe_publishable_key_set: true,
        stripe_secret_key_set: true,
        stripe_webhook_secret_set: true,
        stripe_connect_client_id: "ca_platform",
        application_fee_bps: 125,
        updated_at: "2026-07-22T00:00:00Z",
      },
      isLoading: false,
      error: null,
    });
    staffRequest.mockRejectedValueOnce(
      new Error("Cannot change the webhook secret while Connect sessions are pending."),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <PlatformStripeConnectPanel />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /clear webhook secret/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/sessions are pending/i);
    expect(screen.getByRole("button", { name: /clear webhook secret/i })).not.toBeDisabled();
  });
});
