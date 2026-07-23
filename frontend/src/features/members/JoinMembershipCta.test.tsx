import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JoinMembershipCta, joinCtaState } from "./JoinMembershipCta";
import { membershipErrorText } from "../staff/MembersPanel";
import { StructuredApiError } from "../../lib/api";

describe("join policy CTA", () => {
  it.each([
    ["open", true, "Join instantly"],
    ["request", true, "Request to join"],
    ["request", false, "Sign in to join"],
  ] as const)("renders the %s contract", (policy, signedIn, label) => {
    const onJoin = vi.fn();
    const onSignIn = vi.fn();
    render(<JoinMembershipCta policy={policy} signedIn={signedIn} pending={false} onJoin={onJoin} onSignIn={onSignIn} />);
    fireEvent.click(screen.getByRole("button", { name: label }));
    expect(signedIn ? onJoin : onSignIn).toHaveBeenCalledOnce();
  });

  it("renders invite-only without a self-join action", () => {
    render(<JoinMembershipCta policy="invite_only" signedIn={false} pending={false} onJoin={vi.fn()} onSignIn={vi.fn()} />);
    expect(screen.getByText("Invite-only makerspace")).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(joinCtaState("invite_only", true).action).toBe("none");
  });
});

describe("member management error rendering", () => {
  it("keeps a permission failure user-facing without exposing response values", () => {
    const error = new StructuredApiError(403, { detail: "Only a space manager can change capabilities.", code: "permission_denied" });
    expect(membershipErrorText(error)).toBe("Only a space manager can change capabilities.");
  });
});
