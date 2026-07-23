import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PlatformSocialAuthPanel } from "./PlatformSocialAuthPanel";

const { query, staffRequest } = vi.hoisted(() => ({
  query: vi.fn(),
  staffRequest: vi.fn(),
}));

vi.mock("../../lib/api", () => ({ staffRequest }));
vi.mock("./StaffPanels", async () => {
  const actual = await vi.importActual<typeof import("./StaffPanels")>("./StaffPanels");
  return { ...actual, useStaffGet: query };
});

describe("PlatformSocialAuthPanel", () => {
  beforeEach(() => {
    query.mockReset();
    staffRequest.mockReset();
    query.mockReturnValue({
      data: {
        google_web_client_id: "google-web",
        google_ios_client_id: "google-ios",
        google_android_client_id: "google-android",
        apple_service_id: "org.spaceworks.web",
        apple_native_app_ids: ["org.spaceworks.app"],
        apple_team_id: "TEAMID",
        apple_key_id: "KEYID",
        apple_private_key_set: true,
      },
      isLoading: false,
      error: null,
    });
  });

  it("never renders a stored Apple key and omits a blank replacement", async () => {
    staffRequest.mockResolvedValue({});
    render(
      <QueryClientProvider client={new QueryClient()}>
        <PlatformSocialAuthPanel />
      </QueryClientProvider>,
    );

    const keyInput = screen.getByPlaceholderText(/private key set/i);
    expect(keyInput).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: /save social sign-in settings/i }));

    await waitFor(() => expect(staffRequest).toHaveBeenCalledTimes(1));
    const body = JSON.parse(staffRequest.mock.calls[0][1]?.body as string);
    expect(body.apple_private_key).toBeUndefined();
    expect(body.apple_native_app_ids).toEqual(["org.spaceworks.app"]);
  });

  it("sends a newly entered Apple key only as a write value", async () => {
    staffRequest.mockResolvedValue({});
    render(
      <QueryClientProvider client={new QueryClient()}>
        <PlatformSocialAuthPanel />
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByPlaceholderText(/private key set/i), {
      target: { value: "-----BEGIN PRIVATE KEY-----\nsecret" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save social sign-in settings/i }));

    await waitFor(() => expect(staffRequest).toHaveBeenCalledTimes(1));
    const body = JSON.parse(staffRequest.mock.calls[0][1]?.body as string);
    expect(body.apple_private_key).toContain("BEGIN PRIVATE KEY");
  });
});
