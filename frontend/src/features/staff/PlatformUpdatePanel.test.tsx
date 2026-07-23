import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PlatformUpdatePanel } from "./PlatformUpdatePanel";

const { staffRequest } = vi.hoisted(() => ({ staffRequest: vi.fn() }));
vi.mock("../../lib/api", () => ({ staffRequest }));

const settings = {
  automatic_updates_enabled: true,
  status: "idle",
  current_version: "0.5.0-main.42.abcdef123456",
  available_version: "0.5.0-main.43.123456abcdef",
  target_version: "",
  update_requested_at: null,
  last_checked_at: "2026-07-23T10:00:00Z",
  last_updated_at: "2026-07-22T10:00:00Z",
  last_backup_at: "2026-07-22T09:59:00Z",
  last_backup_name: "pre-update-20260722T095900Z.sql.gz",
  last_error: "",
  updated_at: "2026-07-23T10:00:00Z",
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PlatformUpdatePanel />
    </QueryClientProvider>,
  );
}

describe("PlatformUpdatePanel", () => {
  beforeEach(() => {
    staffRequest.mockReset();
    staffRequest.mockImplementation((path: string, options?: RequestInit) => {
      if (path.endsWith("update-now")) return Promise.resolve({ ...settings, status: "queued" });
      if (options?.method === "PATCH") {
        const body = JSON.parse(String(options.body));
        return Promise.resolve({ ...settings, automatic_updates_enabled: body.automatic_updates_enabled });
      }
      return Promise.resolve(settings);
    });
  });

  it("shows update state and explains both backup boundaries", async () => {
    renderPanel();

    expect(await screen.findByRole("switch", { name: "Automatic updates" })).toBeChecked();
    expect(screen.getAllByText(/0.5.0-main.43/)).toHaveLength(2);
    expect(screen.getByText(/checks every seven days/i)).toBeInTheDocument();
    expect(screen.getByText(/restore users, settings, inventory, requests, loans, and audit records/i)).toBeInTheDocument();
    expect(screen.getByText(/MinIO and are not inside this database backup/i)).toBeInTheDocument();
    expect(screen.getByText(/pre-update-20260722T095900Z.sql.gz/)).toBeInTheDocument();
  });

  it("persists the automatic-update toggle", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("switch", { name: "Automatic updates" }));

    await waitFor(() => expect(staffRequest).toHaveBeenCalledTimes(2));
    expect(staffRequest).toHaveBeenLastCalledWith(
      "/admin/platform/update-settings",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ automatic_updates_enabled: false }),
      }),
    );
  });

  it("queues a manual update without exposing host privileges", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: "Update now" }));

    await waitFor(() =>
      expect(staffRequest).toHaveBeenCalledWith(
        "/admin/platform/update-settings/update-now",
        { method: "POST" },
      ),
    );
    expect(await screen.findByRole("button", { name: "Update queued" })).toBeDisabled();
  });
});
