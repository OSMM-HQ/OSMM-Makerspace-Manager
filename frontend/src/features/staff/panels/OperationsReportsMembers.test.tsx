import { render, screen } from "@testing-library/react";
import type React from "react";
import { describe, expect, it, vi } from "vitest";

import { OperationsReportsMembers } from "./OperationsReportsMembers";

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock("./shared", () => ({
  Panel: ({ title, children }: { title: string; children: React.ReactNode }) => <section aria-label={title}>{children}</section>,
  useStaffGet: query,
}));

describe("OperationsReportsMembers", () => {
  it("labels snapshot and lifecycle-timestamp metrics without member-level data", () => {
    query.mockReturnValue({
      isLoading: false,
      error: null,
      data: {
        rows: [["makerspace_name"], ["Community Lab"]],
        typed_rows: [{
          makerspace_name: "Community Lab",
          membership_policy: "request",
          referrals_enabled: true,
          new_members: 2,
          active_members: 8,
          revoked_members: 1,
          pending_requests: 3,
          open_invites: 4,
          referred_joins: 2,
          verified_members: 5,
        }],
      },
    });

    render(<OperationsReportsMembers makerspaceId={1} aggregate={false} startDate="2026-07-01" endDate="2026-07-31" enabled />);

    expect(screen.getByText("Active members (current)")).toBeTruthy();
    expect(screen.getByText("Activations (current timestamp in range)")).toBeTruthy();
    expect(screen.getByText("These are current lifecycle timestamps, not immutable event-history counts.")).toBeTruthy();
    expect(screen.getByText("This report contains aggregate makerspace counts only; it does not include member identities or contact details.")).toBeTruthy();
    expect(screen.queryByText(/@|email|phone/i)).toBeNull();
  });

  it("uses the shared report states for loading, errors, and empty results", () => {
    query.mockReturnValue({ isLoading: true, error: null, data: undefined });
    const view = render(<OperationsReportsMembers makerspaceId={1} aggregate={false} startDate="" endDate="" enabled />);
    expect(view.container.querySelector('[aria-hidden="true"]')).toBeTruthy();

    query.mockReturnValue({ isLoading: false, error: new Error("Report unavailable"), data: undefined });
    view.rerender(<OperationsReportsMembers makerspaceId={1} aggregate={false} startDate="" endDate="" enabled />);
    expect(screen.getByText("Report unavailable")).toBeTruthy();

    query.mockReturnValue({ isLoading: false, error: null, data: { rows: [["makerspace_name"]], typed_rows: [] } });
    view.rerender(<OperationsReportsMembers makerspaceId={1} aggregate={false} startDate="" endDate="" enabled />);
    expect(screen.getByText("No records.")).toBeTruthy();
  });
});
